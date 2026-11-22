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

    source_ids = [str(uuid4()), str(uuid4())]
    checksum, bundle_hash = quote(bundle["paper"]["sha256"]), quote('d' * 64)
    for source_id in source_ids:
        query(f"""insert into research_skill_sources(id,owner_id,sha256,byte_count)
          values ({quote(source_id)},{actor},{checksum},10) on conflict (id) do nothing""", role="service_role")

    def stage_source(source_id, owner=actor, document=attached, digest=bundle_hash):
        sql = f"select research_skill_preview_for_source({owner},{digest},{fixture.sql_json(document)},{quote(source_id)})"
        return json.loads(query(sql, role="service_role"))

    source_id = source_ids[0]
    source = quote(source_id)
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query("select * from research_skill_sources", role=role))
        fixture.rejects(lambda: query(f"select research_skill_preview_for_source({actor},{bundle_hash},{fixture.sql_json(attached)},{source})", role=role))
    fixture.rejects(lambda: query(f"update research_skill_sources set byte_count=11 where id={source}", role="service_role"))
    fixture.rejects(lambda: stage_source(source_id, owner=other))
    fixture.rejects(lambda: stage_source(source_id, document=bundle))
    differing_pdf = {**attached, "paper": {**attached["paper"], "byte_count": 11}}
    fixture.rejects(lambda: stage_source(source_id, document=differing_pdf))
    assert stage_source(source_id) == stage_source(source_id) == {"preview_id": source_id, "study_id": None}
    fixture.rejects(lambda: stage_source(source_id, digest=quote('e' * 64)))
    assert stage_source(source_ids[1])["preview_id"] == source_ids[1]
    assert json.loads(query(stage_pdf, role="service_role"))["preview_id"] == pdf_id
    assert not query(f"select research_skill_shared({source})", role="anon")
    query(f"update research_skill_submissions set pdf_verified_at=now(), approved_at=now() where id={source}", role="service_role")
    assert query(f"select research_skill_submit({actor},{source})", role="service_role") == source_id
    assert stage_source(source_id)["study_id"] == source_id
    assert json.loads(query(f"select research_skill_shared({source})", role="anon")) == attached
    print("PASS private and immutable source ownership, exact PDF binding, and stable assessment IDs", flush=True)


if __name__ == "__main__":
    main()
