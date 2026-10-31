"""Platform control plane regression checks in a fresh, retained local database.

Only loopback PostgreSQL is accepted. Google JWTs, Storage and owner addresses are
explicit synthetic fixtures; no production credentials or model calls are used.
"""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
PSQL = shutil.which('psql') or '/opt/homebrew/opt/postgresql@17/bin/psql'
ORIGIN = os.environ.get('PLATFORM_TEST_DATABASE_URL', 'postgresql://michael@127.0.0.1:54477/postgres')
if urllib.parse.urlsplit(ORIGIN).hostname not in ('localhost', '127.0.0.1', '::1'):
    raise ValueError('Platform database checks require loopback PostgreSQL.')
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ').lower()
DATABASE = 'jumpserve_platform_test_' + STAMP
DIRECTORY = ROOT / '.test-artifacts/platform-database' / STAMP
DIRECTORY.mkdir(parents=True)
checks = []

def quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def js(value):
    return quote(json.dumps(value, allow_nan=False)) + '::jsonb'

def sql(statement, role=None, actor=None, google=True, database=DATABASE, fail=False):
    url = urllib.parse.urlsplit(ORIGIN)._replace(path='/' + database).geturl()
    if role:
        claims = dict(sub=actor, app_metadata=dict(provider='google')) if google else dict(sub=actor)
        statement = 'begin; set local role ' + role + '; do $jwt$ begin perform set_config(\'request.jwt.claims\',' + js(claims) + "::text,true); end $jwt$; " + statement + '; commit;'
    result = subprocess.run([PSQL, url, '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-c', statement], capture_output=True, text=True)
    if fail:
        if result.returncode == 0:
            raise AssertionError('Expected denial: ' + statement[:100])
        return
    if result.returncode:
        raise AssertionError(result.stderr)
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else ''

def rpc(name, values, role='service_role', actor=None, google=True, fail=False):
    args = []
    for key, value in values.items():
        arg = js(value) if isinstance(value, (dict, list)) else 'null' if value is None else quote(value)
        args.append(key + '=>' + arg)
    raw = sql('select public.' + name + '(' + ','.join(args) + ')', role, actor, google, fail=fail)
    return json.loads(raw) if raw and not fail else None

def check(name, action):
    action()
    checks.append(name)
    print('PASS ' + name, flush=True)

def main():
    sql('create database ' + DATABASE + " template template0 encoding 'UTF8'", database=urllib.parse.urlsplit(ORIGIN).path.strip('/') or 'postgres')
    sql("""do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
create schema auth; create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
create function auth.jwt() returns jsonb language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb$$;
create function auth.uid() returns uuid language sql stable as $$select (auth.jwt()->>'sub')::uuid$$;
grant usage on schema auth to anon,authenticated,service_role;
create schema storage; create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint);
create table storage.objects(id uuid primary key,bucket_id text);alter table storage.objects enable row level security;
grant usage on schema storage to authenticated;grant select on storage.objects to authenticated;
create table public.research_model_dispatches(id uuid primary key,status text);
create function public.research_model_dispatch(p_operation text,p_payload jsonb) returns jsonb language sql security definer set search_path='' as $$select '{"claimed":true}'::jsonb$$;
""")
    for migration in ('202610300004_platform_supervisor.sql', '202610300005_platform_worker.sql', '202610300006_platform_host_coordination.sql'):
        sql((ROOT / 'database' / migration).read_text())
    owners = [str(uuid.uuid4()) for _ in range(4)]
    outsider, unconfirmed = str(uuid.uuid4()), str(uuid.uuid4())
    for i, actor in enumerate(owners):
        sql('insert into auth.users values(' + quote(actor) + ',' + quote(f'owner{i}@example.invalid') + ',now()); insert into public.platform_operator_enrollments values(' + quote(f'owner{i}@example.invalid') + ",'owner',now())")
    sql('insert into auth.users values(' + quote(outsider) + ",'stranger@example.invalid',now()),(" + quote(unconfirmed) + ",'owner0@example.invalid',null)")
    worker = str(uuid.uuid4())
    def work(operation, task=None, token=None, payload=None, fail=False, role='service_role'):
        return rpc('platform_worker', dict(p_operation=operation, p_worker=worker, p_task=task, p_token=token, p_payload=payload or {}), role=role, actor=owners[0], fail=fail)
    def control(action, task=None, payload=None, request=None, actor=owners[0], fail=False, google=True):
        return rpc('platform_control', dict(p_action=action,p_request=request or str(uuid.uuid4()),p_task=task,p_payload=payload or {}),role='authenticated',actor=actor,fail=fail,google=google)
    def snapshot(actor, google=True, fail=False):
        return rpc('platform_snapshot', {}, role='authenticated',actor=actor,google=google,fail=fail)
    check('anonymous snapshot denied', lambda: rpc('platform_snapshot', {}, role='anon', fail=True))
    check('unlisted Google account denied', lambda: snapshot(outsider, fail=True))
    check('unconfirmed email cannot enroll', lambda: snapshot(unconfirmed, fail=True))
    check('missing Google provider cannot enroll', lambda: snapshot(owners[0], google=False, fail=True))
    for i, actor in enumerate(owners):
        check('configured owner ' + str(i+1) + ' enrolls privately', lambda actor=actor: snapshot(actor)['operator_role']=='owner' or (_ for _ in ()).throw(AssertionError()))
    check('enrolled owner without Google JWT denied', lambda: snapshot(owners[0], google=False, fail=True))
    check('browser cannot read private task SQL', lambda: sql('select * from public.platform_tasks', 'authenticated', owners[0], fail=True))
    check('browser cannot self grant access', lambda: sql('insert into public.platform_operators values(' + quote(outsider) + ",'owner',now())", 'authenticated', owners[0], fail=True))
    check('browser cannot invoke worker', lambda: work('heartbeat', payload=dict(status='ready'), role='authenticated', fail=True))
    check('service credential cannot invoke operator controls', lambda: rpc('platform_control',dict(p_action='resume',p_request=str(uuid.uuid4())),fail=True))
    policy = 'a'*64
    sql('insert into public.platform_authorizations(version,policy_sha256,document,source_instruction) values(\'test-v1\',' + quote(policy) + ",'{}','Synthetic test authorization'); update public.platform_settings set authorization_version='test-v1' where id")
    check('worker paused by default', lambda: work('claim',payload=dict(policy_sha256=policy)) is None or (_ for _ in ()).throw(AssertionError()))
    control('resume')
    check('policy mismatch denied', lambda: work('claim',payload=dict(policy_sha256='b'*64),fail=True))
    task, request = str(uuid.uuid4()), str(uuid.uuid4())
    payload = dict(title='Synthetic test',objective='Validate durable platform actions.',repositories=['jumpserve-networks/jumpserve-front-end'],max_reserved_cents=100,elapsed_seconds=3600)
    control('enqueue',task,payload,request)
    check('lost control acknowledgement replays original task', lambda: control('enqueue',task,payload,request)['replayed'] or (_ for _ in ()).throw(AssertionError()))
    check('reused control identity cannot change payload', lambda: control('enqueue',task,{**payload,'title':'changed'},request,fail=True))
    check('repository outside scope denied', lambda: control('enqueue',str(uuid.uuid4()),{**payload,'repositories':['other/repo']},fail=True))
    research_id=str(uuid.uuid4());sql('insert into public.research_model_dispatches values('+quote(research_id)+",'queued')")
    check('queued research has host priority',lambda: work('claim',payload=dict(policy_sha256=policy)) is None or (_ for _ in ()).throw(AssertionError()))
    sql('delete from public.research_model_dispatches')
    claimed=work('claim',payload=dict(policy_sha256=policy)); token=claimed['lease_token']
    check('platform tools fence concurrent research tools',lambda: rpc('research_model_dispatch',dict(p_operation='claim',p_payload={})) is None or (_ for _ in ()).throw(AssertionError()))
    check('legacy research claim cannot bypass host coordination',lambda: rpc('research_model_dispatch_before_platform_v1',dict(p_operation='claim',p_payload={}),fail=True))
    check('one concurrent task lease', lambda: work('claim',payload=dict(policy_sha256=policy)) is None or (_ for _ in ()).throw(AssertionError()))
    check('missing lease token denied', lambda: work('event',task,payload=dict(id=str(uuid.uuid4()),kind='test',message='test'),fail=True))
    artifact_id=str(uuid.uuid4())
    artifact=dict(id=artifact_id,name='original.json',sha256='c'*64,byte_count=0,storage_path=task+'/'+'c'*64,media_type='application/json',provenance=dict(fixture=True))
    work('artifact',task,token,artifact)
    check('zero-byte artifact preserved', lambda: rpc('platform_snapshot',dict(p_task=task),role='authenticated',actor=owners[0])['artifacts'][0]['byte_count']==0 or (_ for _ in ()).throw(AssertionError()))
    run_id=str(uuid.uuid4())
    work('begin-run',task,token,dict(id=run_id,request_artifact_id=artifact_id,request_sha256='c'*64))
    check('concurrent model call denied', lambda: work('begin-run',task,token,dict(id=str(uuid.uuid4()),request_artifact_id=artifact_id,request_sha256='c'*64))['denied']=='unconfirmed-model-call' or (_ for _ in ()).throw(AssertionError()))
    work('finish-run',task,token,dict(id=run_id,status='unknown',response_artifact_id=None,reason='Synthetic lost acknowledgement'))
    op_id=str(uuid.uuid4()); intent=dict(id=op_id,kind='publish',request_sha256='d'*64,request=dict(repository=payload['repositories'][0]))
    check('unknown model outcome fences publication', lambda: work('begin-operation',task,token,intent,fail=True))
    work('reconcile-run',task,token,dict(id=run_id,artifact_id=artifact_id,proof=dict(request_sha256='c'*64,status='complete')))
    check('reconciliation retains original unknown result', lambda: sql('select status from public.platform_runs where id='+quote(run_id))=='unknown' or (_ for _ in ()).throw(AssertionError()))
    check('reservation limit enforced', lambda: work('begin-run',task,token,dict(id=str(uuid.uuid4()),request_artifact_id=artifact_id,request_sha256='c'*64))['denied']=='budget' or (_ for _ in ()).throw(AssertionError()))
    work('begin-operation',task,token,intent)
    check('external intent replay returns same operation', lambda: work('begin-operation',task,token,intent)['replayed'] or (_ for _ in ()).throw(AssertionError()))
    check('external identity cannot change', lambda: work('begin-operation',task,token,{**intent,'request_sha256':'e'*64},fail=True))
    work('finish-operation',task,token,dict(id=op_id,request_sha256='d'*64,status='unknown',result=dict(acknowledged=False)))
    check('unverified work cannot complete', lambda: work('checkpoint',task,token,dict(status='completed',reason='must fail'),fail=True))
    work('finish-operation',task,token,dict(id=op_id,request_sha256='d'*64,status='confirmed',result=dict(reconciled=True)))
    check('confirmed external receipt is immutable', lambda: work('finish-operation',task,token,dict(id=op_id,request_sha256='d'*64,status='failed',result={}),fail=True))
    control('disable-releases')
    check('remote release disable fences merge', lambda: work('begin-operation',task,token,dict(id=str(uuid.uuid4()),kind='merge',request_sha256='f'*64,request={}),fail=True))
    control('enable-releases')
    release=dict(id=str(uuid.uuid4()),component='frontend',repository=payload['repositories'][0],revision='1'*40,status='verified',verification=dict(passed=True,revision='2'*40))
    check('wrong production revision denied', lambda: work('release',task,token,release,fail=True))
    work('release',task,token,{**release,'verification':dict(passed=True,revision='1'*40)})
    sql('update public.platform_tasks set lease_until=now()-interval \'1 second\' where id='+quote(task))
    claimed2=work('claim',payload=dict(policy_sha256=policy))
    check('expired lease enters reconciliation with a new token', lambda: claimed2['status']=='reconciling' and claimed2['lease_token']!=token or (_ for _ in ()).throw(AssertionError()))
    check('stale worker cannot write', lambda: work('event',task,token,dict(id=str(uuid.uuid4()),kind='test',message='stale'),fail=True))
    token=claimed2['lease_token']
    work('checkpoint',task,token,dict(status='completed',reason='Exact revision verified by synthetic release adapter.'))
    check('research admission resumes after confirmed platform cleanup',lambda: rpc('research_model_dispatch',dict(p_operation='claim',p_payload={}))['claimed'] or (_ for _ in ()).throw(AssertionError()))
    check('history cannot be rewritten by worker credential', lambda: sql("update public.platform_events set message='altered'", 'service_role', fail=True))
    check('history cannot be rewritten by database owner', lambda: sql("update public.platform_events set message='altered'", fail=True))
    events=snapshot(owners[0])['events']
    check('event cursors preserve bigint as text', lambda: isinstance(events[0]['sequence'],str) or (_ for _ in ()).throw(AssertionError()))
    check('event history stays in numeric sequence order beyond single digits',lambda: all(int(a['sequence'])>int(b['sequence']) for a,b in zip(events,events[1:])) or (_ for _ in ()).throw(AssertionError()))
    maintenance=work('maintenance',payload=dict(policy_sha256=policy))
    check('daily maintenance uses the fixed bounded defaults',lambda: sql('select max_reserved_cents::text||\':\'||extract(epoch from deadline_at-created_at)::integer::text from public.platform_tasks where id='+quote(maintenance['task_id']))=='10000:21600' or (_ for _ in ()).throw(AssertionError()))
    control('cancel',maintenance['task_id'])
    check('cancelling maintenance cannot reset its daily admission limit',lambda: work('maintenance',payload=dict(policy_sha256=policy)) is None or (_ for _ in ()).throw(AssertionError()))
    from platform_assessment_blocker_checks import run as check_assessment_blockers
    check_assessment_blockers(globals(), work, control, policy)
    sql("update public.platform_operators set role='revoked' where user_id="+quote(owners[-1]))
    check('revoked owner cannot self reenroll or read retained history',lambda: snapshot(owners[-1],fail=True))
    (DIRECTORY/'report.json').write_text(json.dumps(dict(passed=True,database=DATABASE,checks=checks,limitations=['Synthetic authentication and Storage; production release adapters tested separately.']),indent=2)+'\n')
    print(str(DIRECTORY/'report.json'))

if __name__=='__main__':
    main()
