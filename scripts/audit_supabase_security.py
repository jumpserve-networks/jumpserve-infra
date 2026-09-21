#!/usr/bin/env python3
"""Read-only JumpServe incident audit; never print API keys or raw log bodies."""
import base64
import argparse
import datetime
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request

PROJECT = "regphejnlvfpyokpniny"


def access_token():
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not token:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Supabase CLI", "-a", "supabase", "-w"],
            capture_output=True, text=True, check=True,
        )
        token = result.stdout.strip()
        if token.startswith("go-keyring-encoded:"):
            token = bytes.fromhex(token.split(":", 1)[1]).decode()
        elif token.startswith("go-keyring-base64:"):
            token = base64.b64decode(token.split(":", 1)[1]).decode()
    if not token.startswith("sbp_"):
        raise RuntimeError("Supabase CLI management credential is unavailable")
    return token


def management(path, payload=None, method=None):
    request = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT}/{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        ca_file = os.environ.get("SSL_CERT_FILE") or ("/etc/ssl/cert.pem" if os.path.isfile("/etc/ssl/cert.pem") else None)
        with urllib.request.urlopen(request, timeout=45, context=ssl.create_default_context(cafile=ca_file)) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode(errors="replace")
        detail = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+|sb(?:p|_secret|_publishable)_[\w-]+", "[redacted]", detail)
        raise RuntimeError(f"Management API {path.split('?')[0]} returned HTTP {error.code}: {detail}") from None


def query(sql):
    return management("database/query", {"query": sql})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", nargs="?", choices=("all", "schema", "logs"), default="all")
    section = parser.parse_args().section
    if section == "schema":
        print(json.dumps(query("""
            select table_name, column_name, data_type, column_default, is_nullable
            from information_schema.columns where table_schema='public'
            and table_name in ('benchmark_jobs','emulated_parent_runs','emulated_runs','emulated_snapshot_stats','runs')
            order by table_name, ordinal_position
        """), indent=2))
        return
    if section == "logs":
        end = datetime.datetime.now(datetime.timezone.utc)
        for days_ago in range(7):
            stop = end - datetime.timedelta(days=days_ago)
            start = stop - datetime.timedelta(hours=24)
            window = {"iso_timestamp_start": start.isoformat().replace("+00:00", "Z"),
                      "iso_timestamp_end": stop.isoformat().replace("+00:00", "Z"),
                      "sql": """select log_attributes['request.method'] as method,
                        log_attributes['request.path'] as path,
                        log_attributes['response.status_code'] as status, count(*) as count
                        from logs where source='edge_logs'
                        group by method,path,status order by method,path,status limit 500"""}
            print("Activity window:", window["iso_timestamp_start"], window["iso_timestamp_end"])
            print(json.dumps(management("analytics/endpoints/logs?" + urllib.parse.urlencode(window)), indent=2))
        return
    keys = management("api-keys?reveal=false")
    print("API key metadata:", json.dumps([
        {name: key.get(name) for name in ("id", "name", "type", "disabled", "created_at")}
        for key in keys
    ], indent=2))
    print("RLS:", json.dumps(query("""
        select n.nspname as schema, c.relname as table, c.relrowsecurity as rls_enabled,
               c.relforcerowsecurity as force_rls
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where c.relkind in ('r','p') and n.nspname in ('public','storage') order by 1,2
    """), indent=2))
    print("Public role table grants:", json.dumps(query("""
        select table_name, grantee, privilege_type from information_schema.role_table_grants
        where table_schema='public' and grantee in ('anon','authenticated')
        order by 1,2,3
    """), indent=2))
    print("Result table columns:", json.dumps(query("""
        select table_name, column_name, data_type, column_default, is_nullable
        from information_schema.columns where table_schema='public'
        and table_name in ('benchmark_jobs','emulated_parent_runs','emulated_runs','emulated_snapshot_stats','runs')
        order by table_name, ordinal_position
    """), indent=2))
    advisors = management("advisors/security")
    print("Security advisors:", json.dumps(advisors, indent=2))
    end = datetime.datetime.now(datetime.timezone.utc)
    window = {
        "iso_timestamp_start": (end - datetime.timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "iso_timestamp_end": end.isoformat().replace("+00:00", "Z"),
        "sql": "select source, count(*) as count from logs group by source order by source",
    }
    print("Log window:", window["iso_timestamp_start"], window["iso_timestamp_end"])
    print("Log counts:", json.dumps(management("analytics/endpoints/logs?" + urllib.parse.urlencode(window)), indent=2))


if __name__ == "__main__":
    main()
