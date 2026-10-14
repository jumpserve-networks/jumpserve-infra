"""Fixed local actual Postgres/API/worker/package campaign; no AWS or model calls.

Google identity and Supabase Storage transport are synthetic. HTTP observations
are produced by actual loopback requests, not mocked timing values. Retain raw
bytes, failures and database state for inspection.
"""
import datetime as dt
import hashlib
import http.server
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_research_ideas_database as f
sys.path.insert(0,str(f.ROOT.parent/'jumpserve-back-end/research_workflow/tests'))
from test_network_execution import document,SOURCE
import network_execution,network_spec,package_runtime,worker

DIRECTORY=f.ROOT/'.test-artifacts/network-execution/database'/f.STAMP;DIRECTORY.mkdir(parents=True,exist_ok=False)
report=dict(protocol='docs/network-execution-validation-protocol-v1.json',started_at=dt.datetime.now(dt.timezone.utc).isoformat(),database=f.DATABASE,checks=[],
    new_model_calls=0,cloud_experiments=0,measured_charges_usd=None,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),
    scope='Actual local API/queue SQL and package HTTP measurements; synthetic Google identity, Storage transport and AWS dispatch.',
    conditional_gaps=['Legitimate Google session','AWS VM and independent cleanup','Docker execution','Mullvad/CDN origin credentials'])
requests=[];launches=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):requests.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'local-network-development-fixture')
    def log_message(self,*args):pass

def check(name,action):
    tick=time.monotonic()
    try:result=action();report['checks'].append(dict(name=name,passed=True,evidence=result,wall_seconds=time.monotonic()-tick));print('PASS '+name,flush=True)
    except Exception as error:report['checks'].append(dict(name=name,passed=False,reason=str(error)));raise

def fixture(server,source=None):
    study=f.uid();campaign=f.uid();protocol=f.uid();claim=f.uid();src=f.uid()
    f.store.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=f.workflow.paper_details(dict(title='Local networking execution development fixture',domain='Networking software verification',scope='Actual loopback HTTP development observations; no CDN scientific validation',study_kind='idea',paper_url=None))))
    code=SOURCE.read_text() if source is None else source
    package=network_execution.upload(study,f.ACTOR,dict(request_id=f.uid(),source=code,version='local-development-v1'))
    p=document('custom-package-v1');p['configurations'][0]['details']['test_config']['package']=package
    p['execution']['exclusive_resources']=['development:http-server']
    p['configurations'][0]['details']['test_config']['parameters']['url']=f'http://127.0.0.1:{server.server_port}/development'
    p=network_spec.bind_inputs(p);f.workflow.validate_protocol(p)
    value=dict({field:'Explicit software development fixture; no substantive AI review or scientific validation.' for field in f.ideas.FIELDS},protocol=p)
    packet=f.ideas.save(study,f.ACTOR,dict(action='save',request_id=f.uid(),supersedes_id=None,document=value,reason='Local networking software fixture'))
    reviews={}
    for task in ('comprehension','critic'):
        r=f.rpc('research_begin_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_user='software-fixture@example.invalid',p_id=f.uid(),p_packet=packet['id'],p_task=task,p_session=None,
            p_prompt=PROMPT,p_model='synthetic-software-provider',p_request=dict(task=task,fixture=True),p_provenance=dict(packet_sha256=packet['sha256'],context_policy='fresh-packet-only',history_messages=0)))
        answer=dict(summary='Synthetic development response only',questions=[],findings=[],verdict='ready')
        f.rpc('research_finish_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_id=r['id'],p_status='complete',p_reason=None,p_raw=f.workflow.canonical(answer).decode(),p_output=answer,p_usage=dict(tokens=None,measured_charges_usd=None),p_provenance={},p_messages=None))
        reviews[task]=r['id']
    f.ideas.accept(study,f.ACTOR,dict(action='accept',request_id=f.uid(),packet_id=packet['id'],comprehension_run_id=reviews['comprehension'],critic_run_id=reviews['critic'],reason='Synthetic readiness declaration for software verification; no actual AI review'))
    prepared=f.ideas.prepare_campaign(dict(id=study,title='Local networking development fixture'),f.ACTOR,dict(action='prepare-campaign',request_id=f.uid(),packet_id=packet['id'],title='Loopback package development pilot',stage='pilot',claim_type='operational',experiment_type='new-measurement',planned_units=1))
    body=prepared['queue_requests'][0];spec=network_spec.specs(p)[0]
    frozen=f.store.rows('protocols',{'id':'eq.'+prepared['link']['protocol_id'],'study_id':'eq.'+study,'limit':1})[0]
    result=f.scheduler.enqueue(study,f.ACTOR,body)
    return dict(study=study,job=result['job'],request=body,protocol=frozen,spec=spec,source=code)

def claim():return f.store.rpc('research_queue_claim',dict(p_worker=f.uid()))
def provider(spec,job,action):
    n=f.rpc('research_network_launch',dict(p_job=job,p_runner='custom-package-v1',p_claim=action=='launch'))
    if action=='launch':
        if n is None:return dict(status='launch-already-authorized')
        launches.append(job);root=DIRECTORY/job;root.mkdir(exist_ok=False)
        (root/'spec.json').write_bytes(f.workflow.canonical(spec));(root/'package.py').write_bytes(f.store.artifact_bytes(n['study_id'],spec['config']['package']['artifact_id'],12000))
        receipt=package_runtime.run(root,time.time()+10,allow_container=False)
        data=dict(root=str(root),runtime_receipt=receipt)
        f.rpc('research_network_update',dict(p_job=job,p_phase='running',p_data=data,p_ingest_hash=None))
        return dict(status='running')
    n=f.rpc('research_network_launch',dict(p_job=job,p_runner='custom-package-v1',p_claim=False))
    if action=='cancel':return dict(status='cancelled',started_at=n['started_at'],ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),reason='Owner cancelled before dispatch.',resources={})
    root=Path(n['data']['root']);receipt=n['data']['runtime_receipt'];output=json.loads((root/'output.json').read_bytes()) if (root/'output.json').exists() else None
    for name in ('stdout.bin','stderr.bin','output.json','runtime-receipt.json'):
        path=root/name
        if path.exists():
            artifact=f.store.artifact(n['study_id'],f.ACTOR,path.read_bytes(),str(uuid.uuid5(uuid.UUID(job),'original:'+name)),'application/octet-stream',dict(job_id=job,original_filename=name,transformation='none; original local package bytes'))
            f.store.append(n['study_id'],f.ACTOR,'artifacts',artifact)
    return dict(status='completed' if receipt['exit_code']==0 else 'failed',started_at=n['started_at'],ended_at=receipt['ended_at'],output=output,reason=None if receipt['exit_code']==0 else 'Package exited with nonzero status; original stdout/stderr retained.',resources=dict(execution='actual local loopback package; synthetic cloud host',network_bytes=receipt['network_bytes']))

server=None
PROMPT='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8'
if __name__=='__main__':
    try:
        f.bootstrap();f.store.request=f.transport;report['migration_sha256']=f.report['migration_sha256']
        hash_value=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(PROMPT))
        names=['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']
        declaration=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version='research-ideas-v1',prompt_version_id=PROMPT,prompt_version='research-ideas-v2',prompt_content_sha256=hash_value,model_id='synthetic-software-provider',cases_sha256='a'*64,cases=[dict(name=name,status='complete',passed=True,output_sha256='b'*64) for name in names],reviewer=dict(identity='Synthetic SQL development declaration; no actual model evaluation',type='AI',independent=False,passed=True))
        f.rpc('publish_agent_prompt',dict(p_version_id=PROMPT,p_expected_active_version_id=None,p_expected_content_sha256=hash_value,p_report=declaration,p_actor='Synthetic local software fixture only',p_module_id='research-verification'))
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        os.environ['NETWORK_PACKAGE_FUNCTION']='arn:aws:lambda:us-east-1:395567831870:function:local-development-fixture'
        def security():
            for role in ('anon','authenticated'):
                assert f.query("select relrowsecurity from pg_class where relname='research_network_executions'",role=role)=='t'
                assert f.query("select has_table_privilege(current_user,'research_network_executions','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
                assert f.query("select has_function_privilege(current_user,'research_network_launch(uuid,text,boolean)','EXECUTE')",role=role)=='f'
            return dict(private_rls=True,browser_access=False)
        check('private networking RLS and browser RPC denial',security)
        success=fixture(server);running=claim();spec=success['spec']
        def frozen_identity():
            f.rejects(lambda:f.rpc('research_network_begin',dict(p_job=running['id'],p_token=f.uid(),p_spec=spec,p_sha=f.workflow.digest(f.workflow.canonical(spec)))))
            changed=dict(spec,replication=99)
            f.rejects(lambda:f.rpc('research_network_begin',dict(p_job=running['id'],p_token=running['lease_token'],p_spec=changed,p_sha=f.workflow.digest(f.workflow.canonical(spec)))))
            n=f.rpc('research_network_begin',dict(p_job=running['id'],p_token=running['lease_token'],p_spec=spec,p_sha=f.workflow.digest(f.workflow.canonical(spec))))
            assert n['phase']=='pending';assert (dt.datetime.fromisoformat(running['lease_until'])-dt.datetime.now(dt.timezone.utc)).total_seconds()>3600
            return dict(stale_lease_refused=True,changed_replication_refused=True,lease_covers_long_test=True)
        check('frozen networking identity and long-lived queue lease',frozen_identity)
        with patch.object(network_execution,'invoke',side_effect=provider):
            def success_case():
                answer=worker.execute_job(running);assert answer['status']=='awaiting-review';assert len(requests)==3;assert launches.count(running['id'])==1
                replay=f.scheduler.enqueue(success['study'],f.ACTOR,success['request']);assert replay['replayed'];assert launches.count(running['id'])==1
                rows=f.store.rows('measurements',{'study_id':'eq.'+success['study'],'run_id':'eq.'+running['id']});assert len(rows)==3 and all(row['status']=='recorded' for row in rows)
                assert not f.store.rows('assessments',{'study_id':'eq.'+success['study']});assert not f.store.rows('published_values',{'study_id':'eq.'+success['study']})
                run=f.store.rows('runs',{'study_id':'eq.'+success['study'],'id':'eq.'+running['id']})[0];assert run['usage']['measured_charges_usd'] is None
                return dict(actual_http_requests=len(requests),measurement_rows=len(rows),job_status=answer['status'],hypothesis_assessments=0,measured_charges_usd=None)
            check('actual HTTP package dispatch persists original bytes and measurements',success_case)
            def failed_case():
                case=fixture(server,'print("original failure output",flush=True)\nraise RuntimeError("development failure")\n');job=claim()
                answer=worker.execute_job(job);assert answer['status']=='failed'
                run=f.store.rows('runs',{'study_id':'eq.'+case['study'],'id':'eq.'+job['id']})[0];assert run['status']=='failed' and run['reason']
                assert (DIRECTORY/job['id']/'stderr.bin').read_bytes();assert not f.store.rows('measurements',{'study_id':'eq.'+case['study']})
                return dict(run_status='failed',stderr_retained=True,fabricated_measurements=0)
            check('failed packages retain their original output and terminal run',failed_case)
            def cancelled_case():
                case=fixture(server);job=claim();n=f.rpc('research_network_begin',dict(p_job=job['id'],p_token=job['lease_token'],p_spec=case['spec'],p_sha=f.workflow.digest(f.workflow.canonical(case['spec']))))
                cancel=dict(request_id=f.uid(),job_id=job['id'],reason='Local owner cancellation regression')
                f.rejects(lambda:network_execution.cancel(case['study'],f.OTHER,cancel));network_execution.cancel(case['study'],f.ACTOR,cancel)
                assert f.rpc('research_network_launch',dict(p_job=job['id'],p_runner='custom-package-v1',p_claim=True)) is None
                count=len(launches);answer=worker.execute_job(job);assert answer['status']=='cancelled' and len(launches)==count
                return dict(cross_owner_denied=True,launch_after_cancel_refused=True,job_status='cancelled')
            check('owner cancellation prevents launch and keeps excluded run evidence',cancelled_case)
        def exactly_once():
            case=fixture(server);job=claim();f.rpc('research_network_begin',dict(p_job=job['id'],p_token=job['lease_token'],p_spec=case['spec'],p_sha=f.workflow.digest(f.workflow.canonical(case['spec']))))
            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes=list(pool.map(lambda _:f.rpc('research_network_launch',dict(p_job=job['id'],p_runner='custom-package-v1',p_claim=True)),range(8)))
            assert sum(result is not None for result in outcomes)==1
            f.rejects(lambda:f.rpc('research_network_launch',dict(p_job=job['id'],p_runner='emulated-netem-v1',p_claim=True)))
            return dict(simultaneous_clients=8,launch_authorizations=1,cross_runner_denied=True)
        check('eight simultaneous requests authorize one launch without replay',exactly_once)
        def expired_reservation():
            # The prior exactly-once case is still dispatching. Expiry must keep
            # its shared endpoint reserved until cleanup is confirmed.
            f.query("update research_queue_jobs set lease_until=clock_timestamp()-interval '1 second' where status='running'")
            waiting=fixture(server)
            assert claim() is None
            retained=json.loads(f.query("select json_agg(t) from (select q.status,n.phase from research_queue_jobs q join research_network_executions n on n.job_id=q.id where q.status='expired')t"))
            assert any(row['phase']=='dispatching' for row in retained)
            return dict(expired_attempt_retained=True,unconfirmed_cleanup_preserves_resource_reservation=True)
        check('expired launch keeps shared resources reserved until cleanup is known',expired_reservation)
        report['passed']=True
    except Exception as error:report['passed']=False;report['error']=str(error);traceback.print_exc()
    finally:
        if server:server.shutdown();server.server_close()
        report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();report['raw_artifacts']=[dict(path=str(p.relative_to(DIRECTORY)),byte_count=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in DIRECTORY.rglob('*') if p.is_file()]
        (DIRECTORY/'validation-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(DIRECTORY),passed=report['passed'])))
    if not report['passed']:raise SystemExit(1)
