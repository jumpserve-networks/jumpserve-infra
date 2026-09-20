#!/usr/bin/env python3
"""Audit, apply, and verify JumpServe's fixed authenticated-table-access migration."""
import base64
import argparse
import json
import os
from pathlib import Path
import subprocess
import ssl
import urllib.error
import urllib.parse
import urllib.request

PROJECT_REF = "regphejnlvfpyokpniny"
ROOT = Path(__file__).resolve().parents[1]
MIGRATION_NAME = "202609200002_authenticated_table_access.sql"


def access_token():
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if token:
        return token
    for account in ("supabase", "access-token"):
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Supabase CLI", "-a", account, "-w"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value.startswith("go-keyring-encoded:"):
                return bytes.fromhex(value.split(":", 1)[1]).decode()
            if value.startswith("go-keyring-base64:"):
                return base64.b64decode(value.split(":", 1)[1]).decode()
            return value
    raise SystemExit("Set SUPABASE_ACCESS_TOKEN or log in with the Supabase CLI.")


def query(sql, *, read_only=True):
    request = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": sql, "read_only": read_only}).encode(),
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
    )
    try:
        # The python.org macOS build may not have its own CA bundle installed.
        ca_file = os.environ.get("SSL_CERT_FILE")
        if not ca_file and Path("/etc/ssl/cert.pem").is_file():
            ca_file = "/etc/ssl/cert.pem"
        with urllib.request.urlopen(request, timeout=90, context=ssl.create_default_context(cafile=ca_file)) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Supabase SQL request failed ({error.code}): {error.read().decode()}") from None


def verify(*, apply=False):
    checks = (ROOT / "test/database_rls_assertions.sql").read_text()
    if apply:
        migration = (ROOT / "database" / MIGRATION_NAME).read_text()
        # All access checks run before COMMIT; any failure rolls back the change.
        sql = migration.rsplit("commit;", 1)[0] + checks + "\ncommit;"
    else:
        sql = "begin; set local statement_timeout='60s';\n" + checks + "\nrollback;"
    query(sql, read_only=False)
    print(json.dumps({"project": PROJECT_REF, "migration": MIGRATION_NAME,
                      "applied": apply, "database_access_checks": "passed"}))


def http_check(env_path):
    # Read only the public browser configuration. Never load or print secret keys.
    config = {}
    for line in Path(env_path).read_text().splitlines():
        key, _, value = line.partition("=")
        if key in ("NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"):
            config[key] = value.strip().strip("\"'")
    url = config["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    if url != f"https://{PROJECT_REF}.supabase.co":
        raise SystemExit("Frontend configuration does not point to JumpServe; refusing HTTP checks.")
    key = config["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
    audit = query(AUDIT_SQL)[0]["audit"]
    tables = [t["name"] for t in audit["tables"] if t["schema"] == "public"]
    context = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or
        ("/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").is_file() else None))
    for table in tables:
        request = urllib.request.Request(f"{url}/rest/v1/{urllib.parse.quote(table, safe='')}?select=*&limit=0",
            headers={"apikey": key, "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                raise SystemExit(f"Anonymous API access unexpectedly succeeded for {table}: {response.status}")
        except urllib.error.HTTPError as error:
            body = json.loads(error.read())
            if error.code not in (401, 403) or body.get("code") != "42501":
                raise SystemExit(f"Unexpected API response for {table}: HTTP {error.code}, code {body.get('code')}") from None
            print(json.dumps({"table": table, "anonymous_http_status": error.code, "sqlstate": body["code"]}))
    print(json.dumps({"anonymous_rest_access": "blocked", "tables_checked": len(tables)}))


AUDIT_SQL = """
select jsonb_build_object(
 'tables', (select jsonb_agg(to_jsonb(t)) from (
   select n.nspname as schema, c.relname as name, c.relkind as kind,
     c.relrowsecurity as rls, c.relforcerowsecurity as force_rls,
     pg_get_userbyid(c.relowner) as owner,
     has_table_privilege('anon',c.oid,'select') as anon_select,
     has_table_privilege('authenticated',c.oid,'select') as authenticated_select,
     c.relacl::text as acl, c.reloptions
   from pg_class c join pg_namespace n on n.oid=c.relnamespace
   where c.relkind in ('r','p','v','m','f') and n.nspname not like 'pg_%'
     and n.nspname <> 'information_schema' order by n.nspname,c.relname
 ) t),
 'policies', (select jsonb_agg(to_jsonb(p)) from pg_policies p where schemaname='public'),
 'functions', (select jsonb_agg(to_jsonb(f)) from (
   select p.oid::regprocedure::text as name, p.prosecdef as security_definer,
     p.proconfig, p.proacl::text as acl,
     has_function_privilege('anon',p.oid,'execute') as anon_execute,
     has_function_privilege('authenticated',p.oid,'execute') as authenticated_execute
   from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' order by p.proname
 ) f),
 'defaults', (select jsonb_agg(to_jsonb(d)) from (
   select pg_get_userbyid(defaclrole) as owner, n.nspname as schema,
     defaclobjtype as kind, defaclacl::text as acl
   from pg_default_acl a left join pg_namespace n on n.oid=a.defaclnamespace
 ) d),
 'api_settings', (select jsonb_agg(to_jsonb(s)) from (
   select r.rolname, s.setconfig from pg_db_role_setting s
     join pg_roles r on r.oid=s.setrole where r.rolname='authenticator'
 ) s),
 'schemas', (select jsonb_agg(to_jsonb(s)) from (
   select nspname, nspacl::text, has_schema_privilege('anon',oid,'usage') as anon_usage
   from pg_namespace where nspname not like 'pg_%' and nspname<>'information_schema'
 ) s),
 'managed_policies', (select jsonb_agg(to_jsonb(p)) from pg_policies p where schemaname<>'public')
) as audit;
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-schemas", action="store_true")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--verify", action="store_true", help="Run role-based assertions; roll back temporary test objects")
    operation.add_argument("--apply", action="store_true", help="Apply only the fixed migration, verifying before COMMIT")
    operation.add_argument("--http-check", metavar="FRONTEND_ENV", help="Verify anonymous REST rejection using frontend public keys")
    args = parser.parse_args()
    if args.apply or args.verify:
        verify(apply=args.apply)
        raise SystemExit(0)
    if args.http_check:
        http_check(args.http_check)
        raise SystemExit(0)
    audit = query(AUDIT_SQL)[0]["audit"]
    if not args.all_schemas:
        audit["tables"] = [t for t in audit["tables"] if t["schema"] == "public"]
        audit["defaults"] = [d for d in audit["defaults"] if d["schema"] in (None, "public")]
    print(json.dumps({"project": PROJECT_REF, **audit}, indent=2))
