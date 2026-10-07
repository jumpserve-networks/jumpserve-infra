"""Actual concurrent queue RPCs against a fresh local isolated PostgreSQL DB.

Retains the database and timestamped reports, including failed runs. No production
transport, Google session, AWS or model call is used. Raw Storage is a local-byte
transport fixture; database/worker algorithms are the actual implementations.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import api, preparation, runner, scheduler, store, worker, workflow
PSQL='/opt/homebrew/opt/postgresql@17/bin/psql'
ORIGIN='postgresql://michael@127.0.0.1:54477/'
STAMP=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
DATABASE='jumpserve_research_queue_test_'+STAMP.lower()
DIRECTORY=ROOT/'.test-artifacts/research-queue'/STAMP
DIRECTORY.mkdir(parents=True,exist_ok=False)
ACTOR=str(uuid.uuid4()); OTHER=str(uuid.uuid4()); files={}; file_lock=threading.Lock()
report=dict(protocol='research-queue-protocol-v1',amendment='research-queue-amendment-v2',preparation_protocol='research-preparation-protocol-v1',
 database=DATABASE,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),checks=[],
 reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent'),
 design='Synthetic software development regressions, not scientific or held-out validation.',
 conditional_gaps=['Remote Supabase Storage','Real Google-authenticated owner request','Scheduled workers deployed in AWS'],
 measured_charges_usd=None,model_usage=None)

def sql_text(value):return "'"+str(value).replace("'","''")+"'"
def sql_json(value):return sql_text(json.dumps(value,allow_nan=False))+'::jsonb'
def query(sql,database=DATABASE,role=None):
    if not database.startswith('jumpserve_research_queue_test_') and database!='postgres':raise ValueError('Local isolated DB required')
    if role:sql='begin; set local role '+role+'; '+sql+'; commit;'
    result=subprocess.run([PSQL,ORIGIN+database,'-X','-v','ON_ERROR_STOP=1','-q','-t','-A'],input=sql,text=True,capture_output=True,timeout=20)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def rpc(name,payload):
    signatures={
      'research_create_study':dict(p_actor='uuid',p_id='uuid',p_document='jsonb'),
      'research_append':dict(p_study='uuid',p_actor='uuid',p_kind='text',p_record='jsonb'),
      'research_append_bundle':dict(p_study='uuid',p_actor='uuid',p_records='jsonb'),
      'research_queue_enqueue':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_request='jsonb',p_sha256='text'),
      'research_queue_claim':dict(p_worker='uuid'),
      'research_queue_finish':dict(p_job='uuid',p_token='uuid',p_records='jsonb',p_run='uuid',p_error='text',p_usage='jsonb'),
      'research_queue_action':dict(p_study='uuid',p_actor='uuid',p_job='uuid',p_id='uuid',p_action='text',p_reason='text',p_assessments='jsonb',p_run='uuid'),
      'research_queue_snapshot':dict(p_study='uuid',p_actor='uuid'),
      'research_prepare_plan':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_request='uuid',p_plan='jsonb',p_records='jsonb')}
    if name not in signatures or set(payload)!=set(signatures[name]):raise ValueError('Unsupported fixture RPC')
    arguments=[]
    for key,kind in signatures[name].items():
        value=payload[key]
        argument='null::'+kind if value is None else sql_json(value) if kind=='jsonb' else sql_text(value)+'::'+kind
        arguments.append(key+' => '+argument)
    result=query('select public.'+name+'('+','.join(arguments)+')',role='service_role')
    return json.loads(result) if result else None

def transport(path,method='GET',body=None,public=False,raw=False):
    parsed=urllib.parse.urlsplit(path)
    if parsed.path.startswith('/storage/v1/object/'):
        if not raw and method!='POST':raise store.StoreError('Raw fixture access required')
        with file_lock:
            if method=='POST':
                if path in files:raise store.StoreError('Research persistence request failed (HTTP 409)')
                files[path]=body
                target=DIRECTORY/('raw-'+hashlib.sha256(path.encode()).hexdigest())
                target.write_bytes(body);return None
            if path not in files:raise store.StoreError('Research persistence request failed (HTTP 404)')
            return files[path]
    if parsed.path.startswith('/rest/v1/rpc/'):
        return rpc(parsed.path.removeprefix('/rest/v1/rpc/'),body)
    if method!='GET' or body is not None:raise ValueError('Unexpected transport mutation')
    table=parsed.path.removeprefix('/rest/v1/')
    allowed=['research_'+k for k in (*workflow.FIELDS,'studies','study_owners','queue_jobs','queue_events','prepared_plans')]
    if table not in allowed:raise ValueError('Unsupported relation')
    params=dict(urllib.parse.parse_qsl(parsed.query));columns=params.pop('select').split(',')
    if any(not c.replace('_','').isalnum() for c in columns):raise ValueError('Unsafe projection')
    limit=int(params.pop('limit','1000'));offset=int(params.pop('offset','0'))
    order=params.pop('order',None);ordering=[]
    if order:
        for entry in order.split(','):
            column,direction=entry.split('.')
            if column not in ('created_at','id','version') or direction not in ('asc','desc'):raise ValueError('Unsafe order')
            ordering.append(column+' '+direction)
    predicates=[]
    for column,value in params.items():
        if column not in ('id','study_id','owner_id','created_at'):raise ValueError('Unsafe filter')
        operator,argument=value.split('.',1)
        if operator!='eq':raise ValueError('Unsupported filter')
        predicates.append(column+'='+sql_text(argument))
    where=' where '+' and '.join(predicates) if predicates else ''
    order_sql=' order by '+','.join(ordering) if ordering else ''
    return json.loads(query("select coalesce(json_agg(t),'[]'::json) from (select "+','.join(columns)+' from public.'+table+where+order_sql+f' limit {limit} offset {offset}) t',role='anon' if public else 'service_role'))

def check(name,action):
    tick=time.monotonic()
    try:
        evidence=action();report['checks'].append(dict(name=name,passed=True,wall_seconds=time.monotonic()-tick,evidence=evidence));print('PASS '+name,flush=True)
    except Exception as error:
        report['checks'].append(dict(name=name,passed=False,wall_seconds=time.monotonic()-tick,reason=str(error)));raise

def make_study(observed=4):
    study,source,claim,campaign_id,protocol_id=[str(uuid.uuid4()) for _ in range(5)]
    row=dict(observation_id='day-1',configuration_identity='fixed',metric='latency',units='ms',value=0,status='recorded',reason=None)
    raw=workflow.canonical(dict(published=[dict(row,source_id=source,location='Software fixture row 1',extraction='Synthetic reference; no paper result')],observed=[dict(row,value=observed)]))
    document=workflow.numerical_protocol(workflow.digest(raw),'latency','ms',0.1,[dict(identity='fixed',details={'purpose':'Software fixture'})]);document['prior_exposure']='Development fixture; all values inspected before freezing.';document['data_origin']='software-fixture'
    protocol=workflow.protocol_record(document,protocol_id)
    campaign=dict(id=campaign_id,protocol_id=protocol_id,followup_of=None,title='Synthetic queue campaign',stage='pilot',experiment_type='independent-check',adapter='matched-numeric-v1',planned_units=1,coverage_limits='Software fixture only')
    store.rpc('research_create_study',dict(p_actor=ACTOR,p_id=study,p_document=dict(title='Queue development fixture',paper_url='https://example.org/fixture',domain='Software checks',scope='No scientific validation',origin_module=None)))
    source_row=dict(id=source,citation='Synthetic fixture',source_url=None,retrieved_url=None,kind='dataset',role='Software checks',retrieved_version='v1',sha256=workflow.digest(raw),byte_count=len(raw),access_status='locally-generated',review_status='retrieved-unreviewed',review_definition='No literature review claimed',examined='None',unexamined='Inapplicable software fixture',retrieval_attempts=[],reviewer={'identity':'AI test fixture','type':'AI','independence':'Not independent'},findings='Test only',limitations='No empirical evidence')
    records=[dict(kind='sources',record=source_row),dict(kind='claims',record=dict(id=claim,source_id=source,location='Fixture',description='Software claim fixture',claim_type='numerical',scope={},metrics=['latency'],priority=1)),dict(kind='protocols',record=protocol),dict(kind='campaigns',record=campaign),dict(kind='claim_checks',record=dict(id=str(uuid.uuid4()),claim_id=claim,campaign_id=campaign_id,method='Synthetic numerical check',applicability='applicable',rationale='Development only'))]
    store.append_bundle(study,ACTOR,records)
    return dict(study=study,claim=claim,raw=raw,campaign=campaign,protocol=protocol)

def enqueue(f,dependencies=None,resources=None,mode='automatic',priority=3):
    body=dict(request_id=str(uuid.uuid4()),campaign_id=f['campaign']['id'],execution_mode=mode,priority=priority,dependencies=dependencies or [],exclusive_resources=resources or [],raw_input=f['raw'].decode() if mode=='automatic' else None,rationale='Software queue regression',followup_of=None)
    result=scheduler.enqueue(f['study'],ACTOR,body);return result['job'],body
def claim():return store.rpc('research_queue_claim',dict(p_worker=str(uuid.uuid4())))
def action(f,j,kind,assessments=None,run=None):
    return scheduler.action(f['study'],ACTOR,dict(request_id=str(uuid.uuid4()),job_id=j['id'],action=kind,reason='Software fixture action',assessment_ids=assessments or [],run_id=run))
def fail(j):return store.rpc('research_queue_finish',dict(p_job=j['id'],p_token=j['lease_token'],p_records=[],p_run=None,p_error='Synthetic transport failure',p_usage={'measured_charges_usd':None}))
def drain():
    rows=json.loads(query("select coalesce(json_agg(t),'[]') from (select * from research_queue_jobs where status in ('queued','manual','running')) t"))
    for j in rows:
        if j['status']=='running':fail(j)
        else:scheduler.action(j['study_id'],ACTOR,dict(request_id=str(uuid.uuid4()),job_id=j['id'],action='cancel',reason='End of isolated regression group',assessment_ids=[]))
def rejects(callback):
    try:callback()
    except (ValueError,RuntimeError,store.StoreError):return
    raise AssertionError('Expected operation rejection')

try:
    query('create database '+DATABASE,'postgres')
    query("""do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to anon,authenticated,service_role;
create schema storage; create table storage.buckets(id text primary key,name text,public boolean); create table storage.objects(id int primary key,bucket_id text); alter table storage.objects enable row level security;
grant usage on schema storage to anon,authenticated,service_role; grant all on storage.objects to service_role;""")
    report['migration_sha256']={}
    for name in ('202610070001_research_workflow.sql','202610070002_research_queue.sql','202610070003_research_preparation.sql'):
        raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    store.request=transport
    def security():
        for role in ('anon','authenticated'):
            results=json.loads(query("select json_agg(t) from (select c.relname,c.relrowsecurity,has_table_privilege(current_user,c.oid,'SELECT,INSERT,UPDATE,DELETE') access from pg_class c where c.relname in ('research_queue_jobs','research_queue_events','research_prepared_plans')) t",role=role))
            assert len(results)==3 and all(r['relrowsecurity'] and not r['access'] for r in results)
            rejects(lambda:query("select public.research_queue_claim('"+str(uuid.uuid4())+"')",role=role))
            assert query("select has_function_privilege(current_user,'public.research_prepare_plan(uuid,uuid,uuid,uuid,jsonb,jsonb)','EXECUTE')",role=role)=='f'
        return dict(private_tables=3,browser_writes=False,browser_rpc=False)
    check('queue RLS and browser read/write/RPC denial',security)
    def concurrent():
        fixtures=[make_study() for _ in range(3)]
        for f in fixtures:
            for _ in range(3):enqueue(f)
        with ThreadPoolExecutor(max_workers=8) as pool:claimed=list(pool.map(lambda _:claim(),range(8)))
        active=[j for j in claimed if j];assert len(active)==4 and len({j['id'] for j in active})==4
        assert all(sum(j['study_id']==f['study'] for j in active)<=2 for f in fixtures)
        assert query("select count(*) from research_queue_jobs where status='running'")=='4'
        drain();return dict(clients=8,distinct_active_jobs=4,global_cap=4,study_cap=2)
    check('eight simultaneous claim clients enforce global and study caps',concurrent)
    def resources():
        a,b=make_study(),make_study();enqueue(a,resources=['machine:shared']);enqueue(b,resources=['machine:shared'])
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
        active=[j for j in results if j];assert len(active)==1
        fail(active[0]);assert claim() is not None;drain();return dict(shared_resource='machine:shared',overlap=False)
    check('shared resources serialize jobs across different studies',resources)
    def dependencies():
        f=make_study();first,body=enqueue(f);dependent,_=enqueue(f,[dict(job_id=first['id'],requirement='reviewed-evidence')]);complete_dep,_=enqueue(f,[dict(job_id=first['id'],requirement='complete-run')])
        assert scheduler.enqueue(f['study'],ACTOR,body)['replayed'];rejects(lambda:scheduler.enqueue(f['study'],ACTOR,dict(body,rationale='Changed')))
        running=claim();assert running['id']==first['id'];assert claim() is None
        result=worker.execute_job(running);assert result['status']=='awaiting-review';assert result['run_id']==first['id']
        # A scientific discrepancy is still an entirely complete numerical run.
        measurement=store.rows('measurements',{'study_id':'eq.'+f['study'],'limit':1000})[0]
        assert measurement['details']['label']=='discrepant'
        assert query("select count(*) from research_assessments where study_id="+sql_text(f['study']))=='0'
        ready=claim();assert ready['id']==complete_dep['id'];assert claim() is None
        fail(ready);rejects(lambda:action(f,first,'review'))
        assessment=dict(id=str(uuid.uuid4()),claim_id=f['claim'],campaign_id=f['campaign']['id'],supersedes_id=None,label='discrepant',tested_conditions={'units':'ms','fixture':True},evidence=[{'kind':'runs','id':first['id']}],justification='Synthetic discrepancy reviewed',limitations='Not scientific evidence',reviewer={'identity':'AI test fixture','type':'AI','independence':'Not independent'})
        store.append(f['study'],ACTOR,'assessments',assessment);action(f,first,'review',[assessment['id']]);assert claim()['id']==dependent['id']
        snapshot=scheduler.snapshot(f['study'],ACTOR);assert snapshot['coverage']['events']==len(snapshot['events']);assert all('lease_token' not in j for j in snapshot['jobs']);assert all('actor_id' not in e['details'] for e in snapshot['events'])
        rejects(lambda:store.rpc('research_queue_snapshot',dict(p_study=f['study'],p_actor=OTHER)))
        (DIRECTORY/'completed-discrepant-queue.json').write_bytes(workflow.canonical(snapshot))
        drain();return dict(complete_run_unlocks=True,review_requires_assessment=True,scientific_discrepancy_is_failure=False,assessment_automatic=False,original_observation_identity=measurement['observation_id'])
    check('dependencies, original persistence, discrepancy and claim review gates',dependencies)
    def cancellation():
        f=make_study();j,_=enqueue(f);action(f,j,'cancel');assert claim() is None
        rejects(lambda:query("update research_queue_jobs set priority=1 where id="+sql_text(j['id'])))
        rejects(lambda:query("delete from research_queue_events where job_id="+sql_text(j['id'])))
        rejects(lambda:scheduler.enqueue(f['study'],OTHER,dict(request_id=str(uuid.uuid4()),campaign_id=f['campaign']['id'],execution_mode='manual',priority=3,dependencies=[],exclusive_resources=[],raw_input=None,rationale='Cross owner',followup_of=None)))
        return dict(cancelled=True,definitions_immutable=True,history_immutable=True,owner_isolation=True)
    check('cancellation, immutable definitions/history and owner isolation',cancellation)
    def expiry():
        f=make_study();j,_=enqueue(f);running=claim();query("update research_queue_jobs set lease_until=clock_timestamp()-interval '1 second' where id="+sql_text(j['id']))
        assert claim() is None;rejects(lambda:worker.execute_job(running))
        snapshot=scheduler.snapshot(f['study'],ACTOR);assert snapshot['jobs'][0]['status']=='expired';assert any(e['event']=='lease-expired' for e in snapshot['events']);assert snapshot['jobs'][0]['run_id'] is None
        return dict(expired=True,stale_completion_refused=True,automatic_retry=False)
    check('expired leases fence stale completions without automatic retries',expiry)
    def missing():
        f=make_study();j,_=enqueue(f);running=claim()
        with file_lock:files.clear()
        result=worker.execute_job(running);assert result['status']=='failed';assert result['run_id'] is None
        events=scheduler.snapshot(f['study'],ACTOR)['events'];assert events[-1]['details']['usage']['measured_charges_usd'] is None
        return dict(failed_attempt_preserved=True,missing_charges=None)
    check('missing original artifact preserves failed attempt and missing costs',missing)
    def manual():
        f=make_study(observed=0);j,_=enqueue(f,mode='manual');assert claim() is None
        result=runner.execute(f['raw'],f['protocol'],f['campaign'],str(uuid.uuid4()))
        records=[dict(kind='runs',record=result['run'])]
        for kind in ('published_values','measurements','summaries'):records.extend(dict(kind=kind,record=row) for row in result[kind])
        store.append_bundle(f['study'],ACTOR,records);attached=action(f,j,'attach-run',run=result['run']['id']);assert attached['status']=='awaiting-review'
        return dict(manual_execution_inapplicable=True,recorded_run_attached=True,automatic_scientific_assessment=False)
    check('manual work attaches an existing domain run without invented execution',manual)
    def graph():
        f=make_study();other=make_study();foreign,_=enqueue(other,mode='manual')
        rejects(lambda:enqueue(f,[dict(job_id=foreign['id'],requirement='complete-run')]))
        rejects(lambda:enqueue(f,[dict(job_id=str(uuid.uuid4()),requirement='complete-run')]))
        drain();return dict(cross_study_rejected=True,unknown_predecessor_rejected=True,cycles_prevented='immutable dependencies reference existing jobs only')
    check('unknown/cross-study dependencies rejected and cycles prevented',graph)
    def preparation_flow():
        study_id=str(uuid.uuid4())
        paper=dict(title='IPv6 archived recheck development campaign',paper_url='https://pure.mpg.de/pubman/item/item_3670144_1',domain='Networking',scope='Exposed archived numerical cells and follow-up preparation only',origin_module=None)
        study=store.rpc('research_create_study',dict(p_actor=ACTOR,p_id=study_id,p_document=paper))
        body=dict(action='prepare',request_id=str(uuid.uuid4()))
        def prepare_api(data=None,actor=ACTOR):
            event=dict(rawPath='/research/studies/'+study_id+'/prepare',requestContext={'http':{'method':'POST' if data is not None else 'GET'}},body=json.dumps(data) if data is not None else None)
            return api.dispatch(event,actor)
        result=prepare_api(body); prepared=result['prepared']
        assert prepared['planned_jobs']==20 and prepared['queued_jobs']==0
        assert preparation.prepare(study,ACTOR,body)['replayed']
        metadata=store.rows('prepared_plans',{'study_id':'eq.'+study_id})[0]
        original=store.artifact_bytes(study_id,metadata['original_artifact_id'],maximum=1500000)
        _,registered=preparation.registered(study);assert original==registered
        compiled=preparation.compiled(study_id,metadata)
        for job in compiled['jobs'][:2]:prepare_api(dict(action='enqueue',prepared_id=prepared['id'],job_id=job['id']))
        partial=prepare_api()['prepared'][0];assert partial['queued_jobs']==2 and partial['status']=='partially-queued'
        # Resume the entire retained plan; the two original jobs replay, and all
        # later jobs are created once without refreezing any protocol.
        for job in compiled['jobs']:prepare_api(dict(action='enqueue',prepared_id=prepared['id'],job_id=job['id']))
        complete=prepare_api()['prepared'][0];assert complete['queued_jobs']==20
        outcomes=[]
        while True:
            active=claim()
            if active is None:break
            assert active['study_id']==study_id
            outcomes.append(worker.execute_job(active))
        assert len(outcomes)==6 and all(o['status']=='awaiting-review' for o in outcomes)
        def count(kind):return int(query('select count(*) from research_'+kind+' where study_id='+sql_text(study_id)))
        assert count('sources')==74 and count('claims')==15 and count('configurations')==144
        assert count('protocols')==20 and count('campaigns')==20 and count('claim_checks')==20
        assert count('runs')==6 and count('published_values')==1152 and count('measurements')==1152 and count('assessments')==15
        assert query("select count(*) from research_measurements where study_id="+sql_text(study_id)+" and (status<>'recorded' or value is null)")=='0'
        assert query("select count(*) from research_measurements where study_id="+sql_text(study_id)+" and details->>'label'<>'reproduced'")=='0'
        assert query("select count(*) from research_queue_jobs where study_id="+sql_text(study_id)+" and status='manual'")=='14'
        rejects(lambda:query('update research_prepared_plans set plan_id=plan_id where id='+sql_text(prepared['id'])))
        rejects(lambda:rpc('research_prepare_plan',dict(p_study=study_id,p_actor=OTHER,p_id=prepared['id'],p_request=str(uuid.uuid4()),p_plan=metadata,p_records=[])))
        frozen=[(p['id'],p['sha256'],p['frozen_at']) for p in store.rows('protocols',{'study_id':'eq.'+study_id})]
        assert preparation.prepare(study,ACTOR,body)['replayed']
        assert frozen==[(p['id'],p['sha256'],p['frozen_at']) for p in store.rows('protocols',{'study_id':'eq.'+study_id})]
        evidence=dict(study_id=study_id,prepared_id=prepared['id'],manifest_sha256=workflow.digest(original),original_bytes=len(original),jobs=20,automatic_runs=6,manual_tasks=14,matched_cells=1152,assessments_before_and_after=15,prior_exposure='Previously examined archive',new_measurements=False,archived_numerical_agreement=True,protocols_unchanged_on_resume=True)
        drain();return evidence
    check('paper preparation to campaigns, interrupted/resumed enqueueing and six actual workers',preparation_flow)
    def atomic_preparation():
        f=make_study();id_=str(uuid.uuid4()); record=dict(kind='configurations',record=dict(id=str(uuid.uuid4()),identity='must-rollback',details={},input_versions=[],requested_resources={}))
        bad=dict(plan_id='invalid-plan',manifest_sha256='a'*64,original_artifact_id=str(uuid.uuid4()),compiled_artifact_id=str(uuid.uuid4()),jobs=[dict(id=str(uuid.uuid4()),campaign_id=f['campaign']['id'],title='Missing originals',execution_mode='manual')],provenance={})
        rejects(lambda:rpc('research_prepare_plan',dict(p_study=f['study'],p_actor=ACTOR,p_id=id_,p_request=str(uuid.uuid4()),p_plan=bad,p_records=[record])))
        assert query('select count(*) from research_configurations where id='+sql_text(record['record']['id']))=='0'
        return dict(invalid_originals_rejected=True,record_bundle_rolled_back=True)
    check('invalid preparation transaction rolls back its appended records',atomic_preparation)
    def concurrent_preparation():
        sid=str(uuid.uuid4());study=store.rpc('research_create_study',dict(p_actor=ACTOR,p_id=sid,p_document=dict(title='Concurrent software fixture',paper_url='https://pure.mpg.de/pubman/item/item_3670144_1',domain='Software development',scope='No independent validation',origin_module=None)))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:preparation.prepare(study,ACTOR,dict(action='prepare',request_id=str(uuid.uuid4()))),range(2)))
        assert results[0]['prepared']==results[1]['prepared']
        assert query('select count(*) from research_prepared_plans where study_id='+sql_text(sid))=='1'
        assert query('select count(*) from research_campaigns where study_id='+sql_text(sid))=='20'
        artifacts=store.rows('artifacts',{'study_id':'eq.'+sid})
        for a in artifacts:store.artifact_bytes(sid,a['id'],maximum=4000000)
        return dict(concurrent_clients=2,prepared_plans=1,campaigns=20,first_saved_protocols_preserved=True,attempt_artifacts_verified=len(artifacts))
    check('concurrent preparation atomically retains one immutable plan',concurrent_preparation)
    report['passed']=True
except Exception as error:
    report['passed']=False;report['error']=str(error);report['traceback']=traceback.format_exc();print(report['traceback'],file=sys.stderr)
finally:
    report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();report['retained_database']=True
    (DIRECTORY/'database-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));sys.exit(0 if report.get('passed') else 1)
