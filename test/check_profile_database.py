"""Isolated profile SQL checks and optional fixed loopback Supabase transport.

Synthetic auth is accepted only by this local fixture, never by production.
The actual profile migration and PostgreSQL RLS are exercised. No remote writes.
"""
import argparse
import base64
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
PSQL = '/opt/homebrew/opt/postgresql@17/bin/psql'
ORIGIN = 'postgresql://michael@127.0.0.1:54477/'
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
DATABASE = 'jumpserve_profile_test_' + STAMP.lower()
DIRECTORY = ROOT / '.test-artifacts/profiles' / STAMP
ACTOR = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
PORT = 4105
MODE = 'normal'
WRITES = 0


def literal(value):
    return 'null' if value is None else "'" + str(value).replace("'", "''") + "'"


def query(sql, database=DATABASE, actor=None):
    if database != 'postgres' and database != DATABASE:
        raise ValueError('Only the new isolated local database is permitted.')
    if actor:
        if actor not in (ACTOR, OTHER):
            raise ValueError('Fixed synthetic actor required.')
        sql = 'begin; set local role authenticated; set local request.jwt.claims=' + literal(json.dumps(dict(sub=actor))) + '; ' + sql + '; commit;'
    result = subprocess.run([PSQL, ORIGIN + database, '-X', '-v', 'ON_ERROR_STOP=1', '-q', '-t', '-A'], input=sql, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def bootstrap():
    DIRECTORY.mkdir(parents=True)
    report = dict(protocol='private-profile-database-v1', status='running', database=DATABASE, synthetic_auth=True, remote_writes=0)
    migration = (ROOT / 'database/202610230001_user_profiles.sql').read_bytes()
    report['migration_sha256'] = hashlib.sha256(migration).hexdigest()
    try:
        query('create database ' + DATABASE + " with template template0 encoding 'UTF8'", 'postgres')
        query("""
        do $$ begin create role anon; exception when duplicate_object then null; end $$;
        do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
        do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
        create schema auth;
        create table auth.users(id uuid primary key);
        grant usage on schema auth,public to anon,authenticated,service_role;
        create function auth.uid() returns uuid language sql stable as $$
          select (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid
        $$;
        alter default privileges in schema public grant all on tables to anon,authenticated;
        alter default privileges in schema public grant execute on functions to anon,authenticated;
        insert into auth.users values ('""" + ACTOR + "'),('" + OTHER + "');")
        query(migration.decode())
        checks = """
        begin;
        set local role authenticated;
        set local request.jwt.claims='{"sub":"ACTOR"}';
        insert into profiles values ('ACTOR','Ada','Lovelace','America/New_York');
        insert into profiles values ('ACTOR','Ada','Updated','Asia/Tokyo')
          on conflict(id) do update set id=excluded.id,last_name=excluded.last_name,timezone=excluded.timezone;
        do $$ begin
          if (select timezone from profiles where id='ACTOR') <> 'Asia/Tokyo' then raise exception 'Own upsert did not persist'; end if;
          begin insert into profiles values ('OTHER','','','UTC'); raise exception 'Cross-owner insert allowed'; exception when insufficient_privilege then null; end;
          begin update profiles set id='OTHER' where id='ACTOR'; raise exception 'Ownership transfer allowed'; exception when insufficient_privilege then null; end;
          begin update profiles set timezone='not/a-zone'; raise exception 'Invalid zone accepted'; exception when check_violation then null; end;
          begin update profiles set first_name=repeat('x',101); raise exception 'Long name accepted'; exception when check_violation then null; end;
          begin update profiles set last_name=E'line\\nbreak'; raise exception 'Control character accepted'; exception when check_violation then null; end;
        end $$;
        set local request.jwt.claims='{"sub":"OTHER"}';
        do $$ begin
          if exists(select 1 from profiles) then raise exception 'Cross-owner read allowed'; end if;
          update profiles set timezone='UTC' where id='ACTOR';
          if found then raise exception 'Cross-owner update allowed'; end if;
          begin delete from profiles; raise exception 'Browser delete allowed'; exception when insufficient_privilege then null; end;
        end $$;
        set local role anon;
        do $$ begin
          begin perform * from profiles; raise exception 'Anonymous read allowed'; exception when insufficient_privilege then null; end;
          begin insert into profiles values ('OTHER','','','UTC'); raise exception 'Anonymous write allowed'; exception when insufficient_privilege then null; end;
        end $$;
        rollback;
        """.replace('ACTOR', ACTOR).replace('OTHER', OTHER)
        query(checks)
        query("insert into profiles values ('" + ACTOR + "','Ada','Lovelace','America/New_York'),('" + OTHER + "','Other','Researcher','Europe/London')")
        report.update(status='passed', checks=11, coverage=['own insert/update/upsert', 'cross-owner read/insert/update', 'identity transfer', 'anonymous read/write', 'browser delete', 'invalid timezone/name/control character'])
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (DIRECTORY / 'database-report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def token(actor):
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    return encode(dict(alg='HS256', typ='JWT')) + '.' + encode(dict(sub=actor, role='authenticated', exp=4102444800)) + '.explicit-local-fixture'


def user(actor):
    return dict(id=actor, aud='authenticated', role='authenticated', email='fixture@example.invalid', app_metadata=dict(provider='google', providers=['google']), user_metadata=dict(given_name='Fixture', family_name='User'), identities=[], is_anonymous=False, created_at='2026-01-01T00:00:00Z')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status)
        for key, value in {'Content-Type': 'application/json', 'Content-Length': str(len(raw)), 'Access-Control-Allow-Origin': 'http://127.0.0.1:6105', 'Access-Control-Allow-Headers': 'authorization,apikey,content-type,x-client-info,prefer,accept', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Cache-Control': 'no-store'}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.respond(200, {})

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        global MODE, WRITES
        path = urllib.parse.urlsplit(self.path)
        actor = next((identity for identity in (ACTOR, OTHER) if self.headers.get('Authorization') == 'Bearer ' + token(identity)), None)
        body = self.rfile.read(min(int(self.headers.get('Content-Length', 0)), 10000))
        if path.path == '/fixture/metadata':
            return self.respond(200, dict(port=PORT, database=DATABASE, sql_report=str(DIRECTORY / 'database-report.json'), sessions={identity: dict(access_token=token(identity), token_type='bearer', refresh_token='explicit-local-refresh', expires_in=3600, expires_at=4102444800, user=user(identity)) for identity in (ACTOR, OTHER)}))
        if path.path == '/fixture/state':
            return self.respond(200, dict(rows=json.loads(query("select coalesce(json_agg(p order by id),'[]') from profiles p")), writes=WRITES))
        if path.path == '/fixture/mode' and self.command == 'POST':
            mode = json.loads(body)['mode']
            if mode not in ('normal', 'unavailable'):
                return self.respond(400, {})
            MODE = mode
            return self.respond(200, {})
        if path.path == '/auth/v1/user':
            return self.respond(200, user(actor)) if actor else self.respond(401, dict(message='Explicit local fixture session required.'))
        if path.path == '/research/papers':
            return self.respond(200, dict(version='research-paper-catalog-v1', access='public-read-only', papers=[dict(id='33333333-3333-4333-8333-333333333333', title='Synthetic timezone paper', created_at='2026-10-23T18:00:00Z', workflow_status='completed-with-blockers', published=False)], coverage=dict(papers=1), next_cursor=None))
        if path.path != '/rest/v1/profiles':
            return self.respond(404, dict(message='Unsupported isolated fixture route.'))
        if not actor:
            return self.respond(401, dict(message='Explicit local fixture session required.'))
        if MODE == 'unavailable':
            return self.respond(503, dict(message='Synthetic profile storage outage.'))
        try:
            if self.command == 'POST':
                value = json.loads(body)
                if set(value) != {'id', 'first_name', 'last_name', 'timezone'} or value['id'] not in (ACTOR, OTHER):
                    return self.respond(400, dict(message='Invalid fixture projection.'))
                sql = 'insert into profiles(id,first_name,last_name,timezone) values (' + ','.join(literal(value[key]) for key in ('id', 'first_name', 'last_name', 'timezone')) + ') on conflict(id) do update set id=excluded.id,first_name=excluded.first_name,last_name=excluded.last_name,timezone=excluded.timezone returning *'
                result = query('with changed as (' + sql + ') select row_to_json(changed) from changed', actor=actor)
                WRITES += 1
                return self.respond(200, json.loads(result))
            identity = urllib.parse.parse_qs(path.query).get('id', ['eq.' + actor])[0].removeprefix('eq.')
            if identity not in (ACTOR, OTHER):
                return self.respond(400, dict(message='Invalid fixture identity.'))
            result = query("select coalesce(json_agg(p),'[]') from profiles p where id=" + literal(identity), actor=actor)
            return self.respond(200, json.loads(result))
        except RuntimeError:
            return self.respond(403, dict(message='Profile fixture database rejected the operation.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    report = bootstrap()
    print(json.dumps(dict(port=PORT if args.serve else None, **report)), flush=True)
    if args.serve:
        ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
