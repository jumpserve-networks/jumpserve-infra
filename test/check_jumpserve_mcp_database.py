"""Apply the connector migration on an isolated PostgreSQL database and exercise its grants."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import check_research_ideas_database as fixture


def main():
    fixture.bootstrap(include_deleted_at=False)
    query = fixture.query
    quote = fixture.sql_text
    actor, other = map(quote, (fixture.ACTOR, fixture.OTHER))
    query(f"""
      create schema auth;
      create table auth.users(id uuid primary key, is_anonymous boolean, banned_until timestamptz);
      create table auth.identities(user_id uuid references auth.users(id), provider text);
      insert into auth.users values ({actor}, false, null), ({other}, false, null);
      insert into auth.identities values ({actor}, 'google'), ({other}, 'email');
      alter table storage.objects add column name text, add column created_at timestamptz;
    """)
    for name in ("202611110001_next_paper_intake.sql", "202611110002_assessment_deletion.sql",
                 "202611210001_jumpserve_mcp_assessments.sql", "202611220001_jumpserve_skill_pdf_copies.sql",
                 "202611220002_jumpserve_assessment_sources.sql", "202611220003_jumpserve_mcp_source_access.sql"):
        query((fixture.ROOT / "database" / name).read_text())

    resource = quote("https://jumpserve.example.test/mcp")
    redirect = quote("http://127.0.0.1:17651/callback")
    code, access, refresh, next_access, next_refresh = [quote(c * 64) for c in "12345"]
    client = quote("jumpserve-codex")
    challenge = quote("Z" * 43)
    query(f"""insert into jumpserve_mcp_codes(code_hash, owner_id, client_id, redirect_uri, resource, challenge)
      values ({code}, {actor}, {client}, {redirect}, {resource}, {challenge})""", role="service_role")

    def exchange(value, verifier):
        return query(f"""select jumpserve_mcp_exchange('authorization_code',
          {code}, {client}, {value}, {access}, {refresh}, {redirect}, {verifier})""", role="service_role")

    assert exchange(resource, quote("Y" * 43)) == "f"
    assert exchange(quote("https://elsewhere.example.test/mcp"), challenge) == "f"
    assert exchange(resource, challenge) == "t"
    assert exchange(resource, challenge) == "f"
    assert query(f"select jumpserve_mcp_actor({access},{resource})", role="service_role") == fixture.ACTOR
    assert query(f"""select jumpserve_mcp_exchange('refresh_token',
      {refresh},{client},{resource},{next_access},{next_refresh})""", role="service_role") == "t"
    assert not query(f"select jumpserve_mcp_actor({access},{resource})", role="service_role")
    assert query(f"select jumpserve_mcp_actor({next_access},{resource})", role="service_role") == fixture.ACTOR
    allowed = lambda key: query(f"select jumpserve_mcp_can_read_sources({key},{resource})", role="service_role")
    assert allowed(next_access) == "f"
    scoped_code, scoped_access, scoped_refresh, rotated_access, rotated_refresh = [quote(c * 64) for c in "6789a"]
    def scoped_exchange(grant, proof, access_key, refresh_key, callback="null", verifier="null", requested="null"):
        return query(f"select jumpserve_mcp_exchange_scoped('{grant}',{proof},{client},{resource},{access_key},{refresh_key},{callback},{verifier},{requested})", role="service_role")

    assert not scoped_exchange("refresh_token", next_refresh, scoped_access, scoped_refresh, requested="true")
    assert query(f"select jumpserve_mcp_actor({next_access},{resource})", role="service_role") == fixture.ACTOR
    query(f"""insert into jumpserve_mcp_codes(code_hash,owner_id,client_id,redirect_uri,resource,challenge,read_sources)
      values ({scoped_code},{actor},{client},{redirect},{resource},{challenge},true)""", role="service_role")
    assert not scoped_exchange("authorization_code", scoped_code, scoped_access, scoped_refresh, redirect, quote("Y" * 43))
    assert scoped_exchange("authorization_code", scoped_code, scoped_access, scoped_refresh, redirect, challenge) == "source"
    assert allowed(scoped_access) == "t"
    assert scoped_exchange("refresh_token", scoped_refresh, rotated_access, rotated_refresh) == "source"
    assert allowed(scoped_access) == "f"
    assert allowed(rotated_access) == "t"
    assert query(f"select jumpserve_mcp_can_read_sources({rotated_access},'https://other.example.test/mcp')", role="service_role") == "f"
    query(f"select jumpserve_mcp_revoke({actor},{resource})", role="service_role")
    assert not query(f"select jumpserve_mcp_actor({next_access},{resource})", role="service_role")
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query(f"select jumpserve_mcp_can_read_sources({rotated_access},{resource})", role=role))
        fixture.rejects(lambda: query(f"select jumpserve_mcp_actor({access},{resource})", role=role))
        fixture.rejects(lambda: query("select * from public.jumpserve_mcp_tokens", role=role))
    print("PASS code, PKCE, token audience, refresh, revocation and credential visibility", flush=True)
    assert allowed(rotated_access) == "f"
    print("PASS explicit PDF download consent, non-escalating refresh and revocable source access", flush=True)

    bundle = {
        "version": "jumpserve-assessment-v1",
        "paper": {"title": "Synthetic MCP paper", "domain": "Networking", "sha256": "a" * 64, "byte_count": 10},
        "summary": "Synthetic persistence fixture.",
        "claims": [{"id": "c1", "page": 1, "claim": "Count events.", "criterion": "Match the setup.",
                    "outcome": "inconclusive", "finding": "A counter was observed."}],
        "runs": [{
            "id": "r1", "configuration": "Synthetic development test",
            "started_at": "2026-10-01T12:00:00Z", "artifact_sha256": "b" * 64,
            "measurements": [{"claim_id": "c1", "metric": "Synthetic counter", "units": "count",
                              "paper_value": None, "observed_value": 0}],
        }],
    }
    stage = f"select research_skill_preview({actor},{quote('c' * 64)},{fixture.sql_json(bundle)})"
    preview = json.loads(query(stage, role="service_role"))
    assert json.loads(query(stage, role="service_role")) == preview
    pid = quote(preview["preview_id"])
    assert not query(f"select research_skill_shared({pid})", role="anon")
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query(stage, role=role))
        fixture.rejects(lambda: query("select bundle from research_skill_submissions", role=role))
    fixture.rejects(lambda: query(f"select research_skill_submit({actor},{pid})", role="service_role"))
    fixture.rejects(lambda: query(f"select research_skill_submit({other},{pid})", role="service_role"))
    query(f"update research_skill_submissions set approved_at=now() where id={pid}", role="service_role")
    assert not query(f"select research_skill_shared({pid})", role="anon")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: query(f"select research_skill_submit({actor},{pid})", role="service_role"), range(3)))
    assert results == [preview["preview_id"]] * 3
    assert json.loads(query(f"select research_skill_shared({pid})", role="anon")) == bundle
    assert query(f"select paper_value is null and observed_value = 0 from research_skill_measurements where study_id={pid}") == "t"
    assert query(f"select scope from research_studies where id={pid}") == bundle["summary"]
    assert query(f"select count(*) from research_audit_events where study_id={pid} and action='share-local-assessment'") == "1"
    assert query(f"select count(*) from research_queue_jobs where study_id={pid}") == "0"
    query(f"update research_studies set deleted_at=now() where id={pid}")
    assert not query(f"select research_skill_shared({pid})", role="anon")
    fixture.rejects(lambda: query(f"select research_skill_submit({actor},{pid})", role="service_role"))
    print("PASS owner approval, private previews, concurrent idempotency, relational results and deletion", flush=True)

    attached = {**bundle, "paper": {**bundle["paper"], "pdf_copy": True}}
    stage_pdf = f"select research_skill_preview({actor},{quote('d' * 64)},{fixture.sql_json(attached)})"
    pdf_id = json.loads(query(stage_pdf, role="service_role"))["preview_id"]
    pdf = quote(pdf_id)
    approval = f"update research_skill_submissions set approved_at=now() where id={pdf}"
    fixture.rejects(lambda: query(approval, role="service_role"))
    fixture.rejects(lambda: query(f"select research_skill_submit({actor},{pdf})", role="service_role"))
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query("select research_skill_expired_pdfs()", role=role))
        fixture.rejects(lambda: query(f"update research_skill_submissions set pdf_verified_at=now() where id={pdf}", role=role))
    assert not query(f"select research_skill_shared({pdf})", role="anon")
    query(f"update research_skill_submissions set pdf_verified_at=now() where id={pdf}", role="service_role")
    query(approval, role="service_role")
    assert query(f"select research_skill_submit({actor},{pdf})", role="service_role") == pdf_id
    assert json.loads(query(f"select research_skill_shared({pdf})", role="anon")) == attached
    query(f"""
      insert into storage.objects values
        (1,'research-paper-uploads','jumpserve-mcp/{pdf_id}.pdf',now()-interval '4 hours'),
        (2,'research-paper-uploads','jumpserve-mcp/11111111-1111-4111-8111-111111111111.pdf',now()-interval '4 hours'),
        (3,'research-paper-uploads','jumpserve-mcp/22222222-2222-4222-8222-222222222222.pdf',now()-interval '1 hour'),
        (4,'research-paper-uploads','jumpserve-mcp/not-a-preview.pdf',now()-interval '4 hours'),
        (5,'other-bucket','jumpserve-mcp/33333333-3333-4333-8333-333333333333.pdf',now()-interval '4 hours')
    """)
    assert query("select research_skill_expired_pdfs()", role="service_role") == "jumpserve-mcp/11111111-1111-4111-8111-111111111111.pdf"
    print("PASS PDF verification gate and abandoned object cleanup selection", flush=True)

    source_ids = [str(uuid4()) for _ in range(11)]
    checksum, bundle_hash = quote(bundle["paper"]["sha256"]), quote('d' * 64)
    for source_id in source_ids:
        query(f"""insert into research_skill_sources(id,owner_id,sha256,byte_count)
          values ({quote(source_id)},{actor},{checksum},10)""", role="service_role")
    missing_attachment = quote(source_ids[-1])
    query(f"select research_skill_preview_for_source({actor},{bundle_hash},{fixture.sql_json(attached)},{missing_attachment})", role="service_role")
    query(f"""update research_skill_submissions
      set expires_at=now()-interval '1 day',pdf_verified_at=now()-interval '2 days'
      where id={missing_attachment}""")

    old_preview, abandoned_pdf = map(quote, (str(uuid4()), str(uuid4())))
    query(f"""
      insert into research_skill_submissions(id,owner_id,bundle_sha256,bundle,expires_at)
      values ({old_preview},{actor},{quote('0' * 64)},{fixture.sql_json(bundle)},now()-interval '1 day'),
        ({abandoned_pdf},{actor},{quote('f' * 64)},{fixture.sql_json(attached)},now()-interval '1 day')
    """)
    query((fixture.ROOT / "database" / "202611220004_jumpserve_private_assessments.sql").read_text())
    assert query(f"select completed_at is not null from research_skill_submissions where id={old_preview}") == "t"
    assert query(f"select completed_at is null from research_skill_submissions where id={missing_attachment}") == "t"
    assert json.loads(query(f"select research_skill_shared({pdf})", role="anon")) == attached
    fixture.rejects(lambda: query(stage_pdf, role="service_role"))

    query((fixture.ROOT / "database" / "202611230001_jumpserve_private_evaluation_results.sql").read_text())
    assert query(f"select count(*) from research_skill_generator_results where assessment_id={old_preview}") == "1"
    assert query(f"select count(*) from research_skill_generator_results where assessment_id={missing_attachment}") == "0"

    def stage_source(source_id, owner=actor, document=attached, digest=bundle_hash, role="service_role"):
        sql = f"select research_skill_save_from_source({owner},{digest},{fixture.sql_json(document)},{quote(source_id)})"
        return json.loads(query(sql, role=role))

    source_id = source_ids[0]
    source = quote(source_id)
    fixture.rejects(lambda: stage_source(source_id))
    assert query(f"select count(*) from research_skill_submissions where id={source}") == "0"
    objects = [
        f"({index},'research-paper-uploads','jumpserve-mcp/{source_id}.pdf',now()-interval '4 hours')"
        for index, source_id in enumerate(source_ids, start=6)
    ]
    query("insert into storage.objects values " + ",".join(objects))
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query("select * from research_skill_sources", role=role))
        fixture.rejects(lambda: stage_source(source_id, role=role))
    fixture.rejects(lambda: query(f"update research_skill_sources set byte_count=11 where id={source}", role="service_role"))
    fixture.rejects(lambda: stage_source(source_id, owner=other))
    fixture.rejects(lambda: stage_source(source_id, document=bundle))
    differing_pdf = {**attached, "paper": {**attached["paper"], "byte_count": 11}}
    fixture.rejects(lambda: stage_source(source_id, document=differing_pdf))
    assert stage_source(source_id) == stage_source(source_id) == {"preview_id": source_id, "study_id": None}
    assert query(f"select completed_at is not null and pdf_verified_at is not null from research_skill_submissions where id={source}") == "t"
    original = query(f"select id from research_skill_generator_results where assessment_id={source}", role="service_role")
    assert query(f"select paper_value is null and observed_value=0 from research_skill_generator_measurements where result_id={quote(original)}") == "t"
    assert not query(f"select research_skill_shared({source})", role="anon")

    revised = {**attached, "summary": "Additional version with the same source."}
    revision_hash = quote('9' * 64)

    def save_generator(owner=actor, document=revised, digest=revision_hash, role="service_role"):
        return query(f"select research_skill_save_generator_result({owner},{source},{digest},{fixture.sql_json(document)})", role=role)

    fixture.rejects(lambda: save_generator(owner=other))
    fixture.rejects(lambda: save_generator(document={**revised, "paper": {**revised["paper"], "sha256": "8" * 64}}))
    revision = save_generator()
    assert revision != original and save_generator() == revision
    fixture.rejects(lambda: save_generator(document=attached))

    scorecard = {"version": "jumpserve-verifier-scorecard-v1", "paper_id": "fixture", "paper_sha256": "a" * 64,
                 "assessment_sha256": "1" * 64, "answer_key_sha256": "2" * 64,
                 "split": "held_out", "mode": "fresh", "scenario": None, "evidence_integrity": {"status": "verified"},
                 "status": "scored", "score": {"earned": 2, "applicable_maximum": 2, "rubric_maximum": 2},
                 "claims": [{"key_claim_id": "C1", "assessment_claim_id": "c1", "reported_outcome": "inconclusive",
                             "supported_outcome": "inconclusive", "assessment": "correct", "evidence": ["data/trace.csv"],
                             "finding": "The comparable evidence is insufficient."}]}

    def save_score(owner=actor, artifact=revised, digest=revision_hash, card=scorecard, version='1.0.0', role="service_role"):
        return query(f"select research_skill_save_verifier_result({owner},{source},{digest},{fixture.sql_json(artifact)},"
                     f"{quote(version)},{quote('3' * 64)},{fixture.sql_json(card)})", role=role)

    fixture.rejects(lambda: save_score(owner=other))
    fixture.rejects(lambda: save_score(artifact=attached))
    fixture.rejects(lambda: save_score(digest=quote('6' * 64)))
    fixture.rejects(lambda: save_score(card={**scorecard, "claims": [{**scorecard["claims"][0], "reported_outcome": "reproduced"}]}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        scores = list(pool.map(lambda _: save_score(), range(3)))
    assert len(set(scores)) == 1 and save_score(version='1.1.0') != scores[0]
    assert query(f"select generator_result_id from research_skill_verifier_results where id={quote(scores[0])}") == revision
    assert query(f"select grade from research_skill_verifier_claims where verification_id={quote(scores[0])}") == "correct"

    replay = {"version": "jumpserve-replay-analysis-v1", "paper": {"sha256": "a" * 64},
              "scenario": "synthetic", "claims": bundle["claims"]}
    replay_hash = quote('5' * 64)
    replay_id = save_generator(document=replay, digest=replay_hash)
    assert query(f"select count(*) from research_skill_generator_measurements where result_id={quote(replay_id)}") == "0"
    fixture.rejects(lambda: save_score(artifact=replay, digest=replay_hash))
    assert save_score(artifact=replay, digest=replay_hash, card={**scorecard, "mode": "replay", "scenario": "synthetic",
                      "evidence_integrity": {"status": "fixture_only"}})
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query("select * from research_skill_generator_results", role=role))
        fixture.rejects(lambda: query("select * from research_skill_verifier_results", role=role))
        fixture.rejects(lambda: save_generator(role=role))
        fixture.rejects(lambda: save_score(role=role))
    print("PASS private projections, review binding, scoped access, replay isolation and concurrent retries", flush=True)
    fixture.rejects(lambda: stage_source(source_id, digest=quote('e' * 64)))
    assert stage_source(source_ids[1])["preview_id"] == source_ids[1]
    assert not query(f"select research_skill_shared({source})", role="anon")
    query(f"update research_skill_submissions set approved_at=now() where id={source}", role="service_role")
    assert query(f"select research_skill_submit({actor},{source})", role="service_role") == source_id
    assert stage_source(source_id)["study_id"] == source_id
    assert json.loads(query(f"select research_skill_shared({source})", role="anon")) == attached
    print("PASS private and immutable source ownership, exact PDF binding, and stable assessment IDs", flush=True)

    remaining_source = quote(source_ids[1])
    query(f"update research_skill_submissions set expires_at=now()-interval '1 day' where id={remaining_source}")
    for assessment_id in source_ids[2:]:
        assert stage_source(assessment_id)["preview_id"] == assessment_id
    assert query(f"""select completed_at = pdf_verified_at and completed_at < now()-interval '1 day'
      from research_skill_submissions where id={missing_attachment}""") == "t"
    assert query(f"select count(*) from research_skill_submissions where id={abandoned_pdf}") == "0"
    assert query(f"""select count(*) from research_skill_submissions
        where owner_id={actor} and study_id is null and completed_at is not null""") == "11"
    assert query("select research_skill_expired_pdfs()", role="service_role") == "jumpserve-mcp/11111111-1111-4111-8111-111111111111.pdf"
    fixture.rejects(lambda: query(f"select research_skill_submit({actor},{remaining_source})", role="service_role"))
    assert not query(f"select research_skill_shared({remaining_source})", role="anon")
    fixture.rejects(lambda: query(
        f"update research_skill_submissions set expires_at=now() where id={remaining_source}", role="service_role"))
    query(f"""update research_skill_submissions set approved_at=now()-interval '2 days'
      where owner_id={actor} and id={remaining_source} and bundle_sha256={bundle_hash} and completed_at is not null""", role="service_role")
    assert not query(f"select research_skill_shared({remaining_source})", role="anon")
    fixture.rejects(lambda: query(f"select research_skill_submit({other},{remaining_source})", role="service_role"))
    assert query(f"select research_skill_submit({actor},{remaining_source})", role="service_role") == source_ids[1]
    assert json.loads(query(f"select research_skill_shared({remaining_source})", role="anon")) == attached
    print("PASS completed assessments, PDFs and exact owner approvals survive the old deadline", flush=True)

    query(f"update research_studies set deleted_at=now() where id={source}")
    fixture.rejects(lambda: save_generator())
    fixture.rejects(lambda: save_score())
    assert query(f"select count(*) from research_skill_verifier_results where generator_result_id={quote(revision)}") == "2"
    assert not query(f"select research_skill_shared({source})", role="anon")
    print("PASS deletion blocks new private writes while retaining evidence", flush=True)


if __name__ == "__main__":
    main()
