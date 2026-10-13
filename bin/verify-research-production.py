"""Fixed-target release checks; private synthetic operator fixtures, never Google impersonation."""
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import time
import traceback
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com'
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
DIRECTORY = ROOT/'.test-artifacts/research-release'/STAMP
DIRECTORY.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import scheduler, store, workflow, preparation
PREPARATION_FOLLOWUP = sys.argv[1:] == ['--preparation-followup']
PREPARATION_RELEASE = sys.argv[1:] == ['--preparation'] or PREPARATION_FOLLOWUP
if sys.argv[1:] and not PREPARATION_RELEASE: raise SystemExit('Only --preparation or --preparation-followup is supported.')
spec = importlib.util.spec_from_file_location('research_database', ROOT/'bin/research-workflow-database.py')
database = importlib.util.module_from_spec(spec); spec.loader.exec_module(database)
report = dict(version=1, started_at=workflow.now(), protocol='research-workflow-release-protocol-v1',
 amendment='research-workflow-release-amendment-v2', checks=[], passed=False,
 reviewer=dict(identity='Primary Codex AI implementer', type='AI', independence='Not independent'),
 design='Release development regressions; private synthetic numerical data, no paper assessment or held-out evaluation.',
 authenticated_google_request_verified=False, measured_charges_usd=None, model_usage=None)
if PREPARATION_RELEASE:
    report['protocol']='research-preparation-production-protocol-v1'
    report['design']='Production preparation and scheduled archived-value rechecks in a private operator fixture; not a Google session or independent scientific validation.'
if PREPARATION_FOLLOWUP:report['amendment']='research-preparation-production-amendment-v2'

def check(name, action):
    tick=time.monotonic()
    try:
        evidence=action();report['checks'].append(dict(name=name,passed=True,evidence=evidence,wall_seconds=time.monotonic()-tick));print('PASS '+name,flush=True)
    except Exception as error:
        report['checks'].append(dict(name=name,passed=False,error_type=type(error).__name__,wall_seconds=time.monotonic()-tick));raise

def http(path, method='GET', token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(ORIGIN+'/research'+path,method=method,headers=headers,data=b'{}' if method=='POST' else None)
    try:
        with urllib.request.urlopen(req,timeout=25) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as error:return error.code,json.load(error)

def public_checks():
    status,cap=http('/capabilities');assert status==200 and cap['queue']['workers_enabled'] and not cap['arbitrary_code_execution'] and not cap['queue']['claim_labels_automatic']
    (DIRECTORY/'capabilities.json').write_bytes(workflow.canonical(cap))
    status,data=http('/studies');assert status==200 and data['access']=='published'
    missing=str(uuid.uuid4());assert http('/studies/'+missing)[0]==404
    for path,method in [('/studies?mine=1','GET'),('/studies','POST'),('/studies/'+missing+'/queue','GET'),('/studies/'+missing+'/queue','POST'),('/studies/'+missing+'/publish','POST')]:assert http(path,method)[0]==401
    assert http('/studies','POST','deliberately-invalid-release-test-token')[0]==401
    if PREPARATION_RELEASE:
        assert cap['preparation']['version']==preparation.VERSION
        assert cap['preparation']['source_grounded_plans'] and not cap['preparation']['automatic_claim_extraction']
        for method in ('GET','POST'):
            assert http('/studies/'+missing+'/prepare',method)[0]==401
            assert http('/studies/'+missing+'/prepare',method,'deliberately-invalid-release-test-token')[0]==401
    return dict(capabilities=cap,public_studies=len(data['studies']),unauthenticated_operations_denied=5,forged_bearer_denied=True)

def configuration_checks():
    import boto3
    # Older installed botocore cannot use the CLI's login_session provider.
    # Export temporary credentials only into this process's memory; never print/save.
    credentials=json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile','jumpserve','--format','process'],timeout=20))
    session=boto3.Session(aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],aws_session_token=credentials['SessionToken'],region_name='us-east-1')
    assert session.client('sts').get_caller_identity()['Account']==store.ACCOUNT
    cfn=session.client('cloudformation');stack=cfn.describe_stacks(StackName='JumpServeBenchmarkStack')['Stacks'][0];assert stack['StackStatus']=='UPDATE_COMPLETE'
    inventory=cfn.get_paginator('list_stack_resources').paginate(StackName='JumpServeBenchmarkStack',PaginationConfig={'MaxItems':500}).build_full_result()
    assert not inventory.get('NextToken'), 'Stack resource inventory was truncated'
    resources=inventory['StackResourceSummaries']
    functions=[r for r in resources if r['LogicalResourceId'] in ('ResearchWorkflowApiE04EBDAC','ResearchWorkflowQueueWorker702E601D')]
    assert len(functions)==2
    manifest=json.loads((ROOT/'research-workflow-runtime.json').read_text())
    configurations=[];client=session.client('lambda')
    for resource in functions:
        name=resource['PhysicalResourceId'];configuration=client.get_function_configuration(FunctionName=name)
        assert configuration['Runtime']=='python3.12' and configuration['MemorySize']==512
        assert configuration['Timeout']==(180 if configuration['Handler']=='worker.handler' else 29)
        concurrency=client.get_function_concurrency(FunctionName=name);assert 'ReservedConcurrentExecutions' not in concurrency
        # Signed code URLs are used only in memory and never retained in evidence.
        response=client.get_function(FunctionName=name)
        with urllib.request.urlopen(response['Code']['Location'],timeout=30) as download:raw=download.read(1_000_001)
        assert len(raw)<=1_000_000
        archive=zipfile.ZipFile(io.BytesIO(raw))
        hashes={filename:workflow.digest(archive.read(filename)) for filename in manifest['files']};assert hashes==manifest['files']
        (DIRECTORY/(configuration['Handler'].split('.')[0]+'-lambda.zip')).write_bytes(raw)
        configurations.append(dict(name=name,handler=configuration['Handler'],memory_mb=512,timeout_seconds=configuration['Timeout'],reserved_concurrency=None,code_sha256=response['Configuration']['CodeSha256'],zip_original_sha256=workflow.digest(raw),runtime_file_hashes=hashes))
    rule=next(r['PhysicalResourceId'] for r in resources if r['LogicalResourceId']=='ResearchWorkflowQueuePoll49F7FA3B')
    event=session.client('events');details=event.describe_rule(Name=rule);assert details['State']=='ENABLED' and details['ScheduleExpression']=='rate(1 minute)'
    targets=event.list_targets_by_rule(Rule=rule)['Targets'];assert len(targets)==1 and targets[0]['RetryPolicy']==dict(MaximumRetryAttempts=0,MaximumEventAgeInSeconds=60)
    limit=client.get_account_settings()['AccountLimit']
    os.environ['SUPABASE_URL']='https://regphejnlvfpyokpniny.supabase.co'
    os.environ['SUPABASE_ANON_KEY']=json.loads((ROOT/'cdk.json').read_text())['context']['supabaseAnonKey']
    secret=session.client('secretsmanager').get_secret_value(SecretId='jumpserve/supabase-service-key')
    os.environ['SUPABASE_SERVICE_ROLE_KEY']=secret['SecretString']
    report['targets']=dict(aws_account=store.ACCOUNT,supabase_project=store.PROJECT,stack_id=stack['StackId'],frontend='https://jumpserve.quaint-lab.org')
    return dict(functions=configurations,schedule=dict(name=rule,state=details['State'],expression=details['ScheduleExpression'],retry_policy=targets[0]['RetryPolicy']),account_concurrency=limit['ConcurrentExecutions'],unreserved_pool=limit['UnreservedConcurrentExecutions'],scope='Shared hosting pool includes other functions; database queued-work limits are separate.')

def scheduled_fixture():
    # An explicit service-operator fixture identity is NOT a Supabase/Google user.
    actor=str(uuid.uuid4());study=str(uuid.uuid4());source=str(uuid.uuid4());config=str(uuid.uuid4())
    report['private_fixture']=dict(study_id=study,actor_identity_kind='Generated trusted operator fixture identity; not an authenticated user',data_origin='synthetic software release fixture',published=False)
    (DIRECTORY/'fixture-definition.json').write_bytes(workflow.canonical(report['private_fixture']))
    store.rpc('research_create_study',dict(p_actor=actor,p_id=study,p_document=workflow.paper_details(dict(title='Private production release software fixture '+STAMP,paper_url='https://jumpserve.quaint-lab.org/module/research-verification/methods',domain='Synthetic software verification',scope='Private operator fixture only. No paper claims, scientific findings or human review.',origin_module=None))))
    reviewer=dict(identity='Primary Codex release fixture implementer',type='AI',independence='Not independent')
    source_record=dict(id=source,citation='Generated release fixture; no research paper',source_url=None,retrieved_url=None,kind='software',role='Synthetic software control',retrieved_version=STAMP,sha256=None,byte_count=None,access_status='Generated locally; not an external retrieval',review_status='partial-review',review_definition='Examine fixed numerical fixture identities/units and expected software states',examined='Two fixed numerical cases inspected before freezing',unexamined='No external literature or empirical system examined',retrieval_attempts=[],reviewer=reviewer,findings='Zero, discrepancy and missingness software controls',limitations='Not scientific evidence, independent review or a legitimate owner request')
    store.append(study,actor,'sources',source_record)
    raws=[]
    for index in range(2):
        rows=[dict(observation_id='zero',configuration_identity='release-fixture',metric='latency',units='ms',value=0,status='recorded',reason=None),dict(observation_id='difference',configuration_identity='release-fixture',metric='latency',units='ms',value=1,status='recorded',reason=None)]
        published=[dict(row,source_id=source,location='Synthetic row '+str(i+1),extraction='Generated software control; not a paper value') for i,row in enumerate(rows)]
        observed=rows if index==0 else [dict(rows[0],value=2)]
        raws.append(workflow.canonical(dict(published=published,observed=observed)))
    doc=workflow.numerical_protocol(workflow.digest(raws[0]),'latency','ms',0.1,[dict(identity='release-fixture',details=dict(epoch=STAMP,algorithm='Synthetic numerical controls'))])
    doc['input_versions']=[dict(identity='release-input-'+str(i)+'.json',sha256=workflow.digest(raw)) for i,raw in enumerate(raws)]
    doc['resource_limits']['max_input_bytes']=256000;doc['prior_exposure']='Generated and examined development fixtures before freeze; no held-out validation.'
    protocol=workflow.protocol_record(doc,str(uuid.uuid4()));store.append(study,actor,'protocols',protocol)
    store.append(study,actor,'configurations',dict(id=config,identity='release-fixture',details=dict(data_origin='synthetic software fixture'),input_versions=doc['input_versions'],requested_resources=dict(experiment_instances=0,model_calls=0)))
    campaigns=[];jobs=[]
    for i,raw in enumerate(raws):
        campaign=str(uuid.uuid4());claim=str(uuid.uuid4());job=str(uuid.uuid4());campaigns.append(campaign);jobs.append(job)
        store.append(study,actor,'claims',dict(id=claim,source_id=source,location='Private synthetic release case '+str(i),description='Synthetic numeric software behavior; no paper claim',claim_type='numerical',scope=dict(data_origin='synthetic software fixture'),metrics=[dict(name='latency',units='ms')],priority=3))
        store.append(study,actor,'campaigns',dict(id=campaign,protocol_id=protocol['id'],followup_of=None,title='Synthetic release case '+str(i),stage='pilot',experiment_type='independent-check',adapter='matched-numeric-v1',planned_units=2,coverage_limits='Two software observations; no independent scientific validation'))
        store.append(study,actor,'claim_checks',dict(id=str(uuid.uuid4()),claim_id=claim,campaign_id=campaign,method='matched-numeric-v1',applicability='applicable',rationale='Production software control only'))
        (DIRECTORY/('fixture-input-'+str(i)+'.json')).write_bytes(raw)
    # Prepare both campaigns before either job becomes eligible for scheduling.
    for i,raw in enumerate(raws):
        scheduler.enqueue(study,actor,dict(request_id=jobs[i],campaign_id=campaigns[i],execution_mode='automatic',priority=3,dependencies=[],exclusive_resources=[],raw_input=raw.decode(),rationale='Private synthetic production release control; not scientific evidence',followup_of=None))
    report['private_fixture']['job_ids']=jobs
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        snapshot=scheduler.snapshot(study,actor)
        statuses=[job['status'] for job in snapshot['jobs']]
        if len(statuses)==2 and all(status in ('awaiting-review','failed','expired') for status in statuses):break
        time.sleep(5)
    assert all(job['status']=='awaiting-review' for job in snapshot['jobs']) and len(snapshot['jobs'])==2
    results=store.rows('runs',{'study_id':'eq.'+study});assert sorted(r['status'] for r in results)==['complete','partial']
    measurements=store.rows('measurements',{'study_id':'eq.'+study});assert len(measurements)==4
    assert sum(m['status']=='missing' and m['value'] is None for m in measurements)==1
    assert sum(m['status']=='recorded' and m['value']=='0' for m in measurements)==1
    assert not store.rows('assessments',{'study_id':'eq.'+study}) and not store.rows('publications',{'study_id':'eq.'+study})
    assert not store.rows('studies',{'id':'eq.'+study},public=True)
    assert http('/studies/'+study)[0]==404 and http('/studies/'+study+'/queue')[0]==401
    artifacts=store.rows('artifacts',{'study_id':'eq.'+study});assert len(artifacts)==4
    verified=[]
    for i,artifact in enumerate(artifacts):
        raw=store.artifact_bytes(study,artifact['id']);assert workflow.digest(raw)==artifact['sha256'] and len(raw)==artifact['byte_count']
        (DIRECTORY/('retrieved-artifact-'+str(i)+'.bin')).write_bytes(raw)
        verified.append(dict(id=artifact['id'],sha256=artifact['sha256'],byte_count=len(raw),retrieved_hash_verified=True))
    (DIRECTORY/'private-queue-snapshot.json').write_bytes(workflow.canonical(snapshot))
    (DIRECTORY/'recorded-runs.json').write_bytes(workflow.canonical(results))
    (DIRECTORY/'recorded-measurements.json').write_bytes(workflow.canonical(measurements))
    worker_ids={event['details']['worker_id'] for event in snapshot['events'] if event['event']=='claimed'}
    return dict(jobs=len(jobs),statuses=['awaiting-review','awaiting-review'],run_statuses=['complete','partial'],measurements=4,missing=1,recorded_zero=1,assessments_created=0,published=False,artifacts=verified,claiming_invocations=len(worker_ids),trigger='Existing one-minute EventBridge schedule; no direct worker invocation',scope='Actual scheduled worker, database and remote original-byte round trips; service-operator setup, not authenticated Google actions')

def preparation_fixture():
    existing='76c70fd9-0217-464e-8c26-0a47832409a3'
    kinds=('sources','claims','protocols','configurations','campaigns','claim_checks','runs','queue_jobs','prepared_plans')
    def coverage(study_id):return {kind:len(store.rows(kind,{'study_id':'eq.'+study_id})) for kind in kinds}
    tick=time.monotonic()
    if PREPARATION_FOLLOWUP:
        previous=ROOT/'.test-artifacts/research-release/20261007T221548717353Z/production-server-report.json'
        original=previous.read_bytes();baseline=json.loads(original)
        assert baseline['protocol']=='research-preparation-production-protocol-v1' and not baseline['passed']
        study_id=baseline['preparation_fixture']['study_id'];before=baseline['existing_user_workspace']['before']
        owners=store.rows('study_owners',{'study_id':'eq.'+study_id,'limit':1});assert len(owners)==1
        actor=owners[0]['owner_id']
        retained=store.rows('prepared_plans',{'study_id':'eq.'+study_id});assert len(retained)==1
        value=preparation.compiled(study_id,retained[0])
        frozen=store.rows('protocols',{'study_id':'eq.'+study_id});assessments=store.rows('assessments',{'study_id':'eq.'+study_id})
        for kind,rows in [('protocols',frozen),('assessments',assessments)]:
            expected={entry['record']['id']:entry['record'] for entry in value['records'] if entry['kind']==kind}
            assert {row['id'] for row in rows}==set(expected)
            keys=['document','sha256'] if kind=='protocols' else workflow.FIELDS[kind]
            assert all(row[key]==expected[row['id']][key] for row in rows for key in keys)
        report['followup_of']=dict(path=str(previous.relative_to(ROOT)),sha256=workflow.digest(original),experiment_repeated=False,production_writes=False)
    else:
        before=coverage(existing);actor=str(uuid.uuid4());study_id=str(uuid.uuid4())
        store.rpc('research_create_study',dict(p_actor=actor,p_id=study_id,p_document=workflow.paper_details(dict(title='Private preparation release copy of IPv6 archive '+STAMP,paper_url='https://pure.mpg.de/pubman/item/item_3670144_1',domain='Networking',scope='Private production preparation regression; archived evidence only; no new claim assessment.',origin_module=None))))
        study=store.rows('studies',{'id':'eq.'+study_id,'limit':1})[0]
        initial=preparation.status(study)
        assert initial['available_plan']['automatic_jobs']==6 and initial['available_plan']['manual_jobs']==14
        result=preparation.prepare(study,actor,dict(action='prepare',request_id=str(uuid.uuid4())))
        frozen=store.rows('protocols',{'study_id':'eq.'+study_id});assessments=store.rows('assessments',{'study_id':'eq.'+study_id})
        jobs=result['prepared']['jobs'];assert len(jobs)==20
        replay=preparation.prepare(study,actor,dict(action='prepare',request_id=str(uuid.uuid4())))
        assert replay['replayed'] and replay['prepared']['id']==result['prepared']['id']
        def enqueue(job):return preparation.enqueue(study,actor,dict(action='enqueue',prepared_id=result['prepared']['id'],job_id=job['id']))
        for job in jobs[:2]:enqueue(job)
        partial=preparation.status(study)['prepared'][0];assert partial['queued_jobs']==2 and partial['status']=='partially-queued'
        (DIRECTORY/'preparation-partial-status.json').write_bytes(workflow.canonical(partial))
        for job in partial['jobs']:
            if job['status']=='not-queued':enqueue(job)
    report['existing_user_workspace']=dict(study_id=existing,before=before)
    report['preparation_fixture']=dict(study_id=study_id,actor_identity_kind='Generated trusted operator fixture, not a Google account',published=False)
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        snapshot=scheduler.snapshot(study_id,actor)
        automatic=[job for job in snapshot['jobs'] if job['execution_mode']=='automatic']
        if len(automatic)==6 and all(job['status'] in ('awaiting-review','failed','expired') for job in automatic):break
        time.sleep(5)
    (DIRECTORY/'preparation-queue-snapshot.json').write_bytes(workflow.canonical(snapshot))
    assert len(snapshot['jobs'])==20 and len(automatic)==6
    assert all(job['status']=='awaiting-review' for job in automatic)
    manual=[job for job in snapshot['jobs'] if job['execution_mode']=='manual'];assert len(manual)==14 and all(job['status']=='manual' for job in manual)
    assert len(store.rows('prepared_plans',{'study_id':'eq.'+study_id}))==1
    assert store.rows('protocols',{'study_id':'eq.'+study_id})==frozen
    assert store.rows('assessments',{'study_id':'eq.'+study_id})==assessments and len(assessments)==15
    runs=store.rows('runs',{'study_id':'eq.'+study_id});assert len(runs)==6 and all(r['status']=='complete' for r in runs)
    def cells(kind):
        first=store.rows(kind,{'study_id':'eq.'+study_id,'limit':1000})
        second=store.rows(kind,{'study_id':'eq.'+study_id,'limit':1000,'offset':1000})
        assert len(second)<1000, 'Production fixture coverage exceeds two bounded pages'
        return first+second
    measurements=cells('measurements')
    published=cells('published_values')
    assert len(measurements)==len(published)==1152 and all(m['status']=='recorded' for m in measurements)
    assert {m['published_id'] for m in measurements}=={p['id'] for p in published}
    assert not store.rows('publications',{'study_id':'eq.'+study_id}) and not store.rows('studies',{'id':'eq.'+study_id},public=True)
    assert http('/studies/'+study_id)[0]==404 and http('/studies/'+study_id+'/prepare')[0]==401
    verified=[]
    for index,artifact in enumerate(store.rows('artifacts',{'study_id':'eq.'+study_id})):
        raw=store.artifact_bytes(study_id,artifact['id'],maximum=4_000_000);assert workflow.digest(raw)==artifact['sha256'] and len(raw)==artifact['byte_count']
        (DIRECTORY/('preparation-artifact-'+str(index)+'.bin')).write_bytes(raw)
        verified.append(dict(id=artifact['id'],sha256=artifact['sha256'],byte_count=len(raw),retrieved_hash_verified=True))
    for name,rows in [('preparation-runs',runs),('preparation-measurements',measurements),('preparation-published-values',published)]:
        (DIRECTORY/(name+'.json')).write_bytes(workflow.canonical(rows))
    after=coverage(existing);report['existing_user_workspace']['after']=after;assert before==after
    counts={label:sum(m['details']['label']==label for m in measurements) for label in ('reproduced','discrepant','inconclusive')}
    return dict(study_id=study_id,jobs=20,automatic_runs=6,manual_tasks=14,cells=1152,numerical_cell_labels=counts,artifacts=verified,assessments_imported=15,assessments_changed=0,publication=False,user_workspace_unchanged=True,wall_seconds=time.monotonic()-tick,trigger='Existing EventBridge schedule',authenticated_google_request=False,limitation='Rechecking previously exposed archived means; not independent reproduction or new empirical measurements.')

try:
    if sys.platform=='darwin':os.environ.setdefault('SSL_CERT_FILE','/etc/ssl/cert.pem')
    check('deployed resources and original Lambda byte identities',configuration_checks)
    check('public API and unauthorized request denial',public_checks)
    if not PREPARATION_FOLLOWUP:check('scheduled private controls and remote original-byte hash verification',scheduled_fixture)
    if PREPARATION_RELEASE:check('registered preparation, interrupted/resumed queue and six scheduled archived panels',preparation_fixture)
    report['passed']=True
except Exception as error:
    report['failure_type']=type(error).__name__
    site=traceback.extract_tb(error.__traceback__)[-1]
    report['failure_site']=dict(file=site.filename,line=site.lineno,function=site.name)
finally:
    report['ended_at']=workflow.now()
    report['artifacts']=[dict(path=str(p.relative_to(ROOT)),sha256=workflow.digest(p.read_bytes()),byte_count=p.stat().st_size) for p in sorted(DIRECTORY.iterdir()) if p.is_file()]
    (DIRECTORY/'production-server-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],report=str(DIRECTORY/'production-server-report.json'),checks=report['checks']),indent=2))
    if not report['passed']:sys.exit(1)
