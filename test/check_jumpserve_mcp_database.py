"""Apply the connector migration on an isolated PostgreSQL database and exercise its grants."""
import json
from concurrent.futures import ThreadPoolExecutor

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
    """)
    for name in ("202611110001_next_paper_intake.sql", "202611110002_assessment_deletion.sql",
                 "202611210001_jumpserve_mcp_assessments.sql"):
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
    query(f"select jumpserve_mcp_revoke({actor},{resource})", role="service_role")
    assert not query(f"select jumpserve_mcp_actor({next_access},{resource})", role="service_role")
    for role in ("anon", "authenticated"):
        fixture.rejects(lambda: query(f"select jumpserve_mcp_actor({access},{resource})", role=role))
        fixture.rejects(lambda: query("select * from public.jumpserve_mcp_tokens", role=role))
    print("PASS code, PKCE, token audience, refresh, revocation and credential visibility", flush=True)

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


if __name__ == "__main__":
    main()
