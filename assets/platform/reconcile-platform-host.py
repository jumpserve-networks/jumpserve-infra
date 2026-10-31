"""Verify retained cloud work after a definite local admission stop; no model calls."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--original-root',type=Path,required=True);parser.add_argument('--original-task',required=True);parser.add_argument('--task',required=True);args=parser.parse_args()
    root=args.root.resolve();old=args.original_root.resolve();sys.path.insert(0,str(root/'source'))
    from platform_supervisor import native
    from platform_supervisor.common import canonical,digest,identity,save,POLICY_SHA256
    from platform_supervisor.credentials import Credentials
    from platform_supervisor.store import Store,BUCKET
    def forbidden(*args,**kwargs):raise AssertionError('Provider calls are forbidden in retained-work reconciliation.')
    native.runtime.http_request=forbidden;native.runtime.credential=forbidden
    credentials=Credentials();store=Store(credentials.supabase,root/'spool',str(uuid.uuid5(uuid.UUID(args.task),'retained-control')))
    for _ in range(20):
        store.rpc('heartbeat',dict(status='reconciling',reason='Verifying retained cloud fixture and original six responses; no new provider call is permitted.'))
        task=store.rpc('claim',dict(policy_sha256=POLICY_SHA256))
        if task:break
        time.sleep(15)
    else:raise ValueError('Admission is unavailable; no control was repeated.')
    assert task['id']==str(uuid.UUID(args.task)) and task['committed_cents']==0
    store.task=task;original=Store(credentials.supabase,old/'spool',str(uuid.uuid5(uuid.UUID(args.original_task),'cloud-control')));original.task=dict(id=args.original_task)
    try:
        prospective=dict(version='platform-cloud-readiness-reconciliation-v1',original_task_id=args.original_task,original_source_bundle=old.name,new_provider_calls=0,provider_transport_disabled=True)
        store.artifact('retained-control-prospective.json',canonical(prospective))
        ledger=original.request('/rest/v1/platform_tasks?id=eq.'+args.original_task+'&select=committed_cents,max_reserved_cents,status')[0]
        runs=original.rows('runs');assert len(runs)==6 and all(r['status']=='complete' for r in runs) and ledger['committed_cents']==ledger['max_reserved_cents']==600
        candidates=[a for a in original.rows('artifacts') if a['name']=='native-stdout-slice.json'];assert len(candidates)==1
        artifact=candidates[0];raw=original.request('/storage/v1/object/'+BUCKET+'/'+artifact['storage_path'],raw=True);assert digest(raw)==artifact['sha256']
        envelope=json.loads(raw);assert envelope['error']['kind']=='incomplete_turn' and envelope['assistantTurns']>len(runs) and envelope['toolSummary']['failures']==0
        original_report=json.loads((old/'report.json').read_bytes());assert original_report['passed'] is False
        native.containers('js-platform-'+args.original_task.replace('-','')+'-')
        workspace=old/'workspace';test='from calc import double\nassert double(7)==14\nassert double(0)==0\nassert double(None) is None\nprint("three controls passed")\n'
        assert (workspace/'project/check.py').read_text()==test
        result=native.readiness(workspace,envelope,['budget'],known_complete=True);assert result['ready']
        image=json.loads((root/'image.json').read_bytes());assert image['recipe_sha256']==digest((root/'source/Dockerfile').read_bytes())==original_report['recipe_sha256']
        checked=subprocess.run(['docker','run','--rm','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,source='+str(workspace)+',target=/workspace,readonly','--workdir','/workspace',image['image'],'python3','-B','project/check.py'],capture_output=True,timeout=30)
        stdout=store.artifact('retained-control-check-stdout.txt',checked.stdout);store.artifact('retained-control-check-stderr.txt',checked.stderr)
        assert checked.returncode==0 and checked.stdout.strip()==b'three controls passed'
        assert (workspace/'project/check.py').read_text()==test
        report=dict(prospective,version='platform-cloud-control-reconciled-v1',passed=True,live=True,actual_provider_calls=len(runs),maximum_actual_provider_calls=6,image=image['image'],recipe_sha256=image['recipe_sha256'],result=result,existing_test_unchanged=True,container_check_passed=True,task_id=task['id'],bundle_sha256=root.name,original_report_sha256=digest((old/'report.json').read_bytes()),original_native_artifact_id=artifact['id'],verification_stdout_artifact_id=stdout['id'],scientific_claim=False,independent_review=False,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        saved=store.artifact('cloud-control-readiness-reconciliation.json',canonical(report));report['artifact_id']=saved['id']
        proof=json.loads((root/'production-verification.json').read_bytes());assert proof['passed'] is True
        store.rpc('release',dict(id=identity(task['id'],'bootstrap-frontend-verification'),component=proof['component'],repository=proof['repository'],revision=proof['revision'],status='verified',external_id=proof['operation_id'],verification=proof,details=dict(origin='Initial OIDC deployment verification; the retained software control made no repository changes.')))
        store.checkpoint('completed','Retained cloud fixture passed unchanged controls after completion handling repair. Six original responses retained; zero new provider calls. The original failed bootstrap report and task remain unchanged.',dict(cloud_control=report))
        save(root/'report.json',canonical(report));print(json.dumps(report))
    except Exception as error:
        store.checkpoint('blocked','Retained cloud control could not be reconciled. No provider call was issued and no installation is admitted.',dict(prospective,cleanup_unknown=isinstance(error,native.CleanupUnknown)))
        raise

if __name__=='__main__':main()
