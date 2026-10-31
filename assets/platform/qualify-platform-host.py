"""One bounded cloud bootstrap control; original calls persist in Supabase."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

def qualification_store(base):
    class QualificationStore(base):
        def rpc(self,operation,payload=None):
            if operation=='claim':payload=dict(payload or {},only_task=self.qualification_task)
            # This is the prospective software trial size, independent of the
            # production category budget. All actual admissions stay recorded.
            if operation=='begin-run' and len(self.rows('runs'))>=6:return dict(denied='budget')
            return super().rpc(operation,payload)
    return QualificationStore

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--task',required=True);args=parser.parse_args()
    root=args.root.resolve();sys.path.insert(0,str(root/'source'))
    from platform_supervisor import native
    from platform_supervisor.common import canonical,digest,identity,save,POLICY_SHA256
    from platform_supervisor.credentials import Credentials
    from platform_supervisor.store import Store
    image=json.loads((root/'image.json').read_bytes())
    credentials=Credentials();store=qualification_store(Store)(credentials.supabase,root/'spool',str(uuid.uuid5(uuid.UUID(args.task),'cloud-control')))
    store.qualification_task=str(uuid.UUID(args.task))
    stop=threading.Event();thread=None;report=dict(version='platform-cloud-control-v1',passed=False,live=True,image=image['image'],recipe_sha256=image['recipe_sha256'],maximum_actual_provider_calls=6,maximum_reservation_cents=600,maximum_elapsed_seconds=600,scientific_claim=False,independent_review=False)
    save(root/'prospective.json',canonical(report))
    for _ in range(20):
        store.rpc('heartbeat',dict(status='qualifying',reason='Bounded cloud bootstrap control; no repository publishing is admitted.'))
        task=store.rpc('claim',dict(policy_sha256=POLICY_SHA256))
        if task:break
        time.sleep(15)
    else:raise ValueError('Research priority or admission prevents this bounded bootstrap control.')
    if task['id']!=str(uuid.UUID(args.task)) or not (task['max_reserved_cents']==-1 or task['max_reserved_cents']>=600):raise ValueError('Bootstrap task identity or allowance differs.')
    store.task=task
    store.artifact('cloud-control-prospective.json',canonical(report))
    store.event('cloud-control-started','Six-call software fixture admitted on the AWS host; no repository publishing is permitted.')
    def renew():
        while not stop.wait(30):
            try:store.rpc('lease')
            except Exception:return
    thread=threading.Thread(target=renew,daemon=True);thread.start()
    workspace=root/'workspace';workspace.mkdir(mode=0o700);(workspace/'project').mkdir()
    (workspace/'project/calc.py').write_text('def double(value):\n    return value\n')
    test='from calc import double\nassert double(7)==14\nassert double(0)==0\nassert double(None) is None\nprint("three controls passed")\n'
    (workspace/'project/check.py').write_text(test)
    save(workspace/'task.json',canonical(dict(objective='Explicit software fixture. Fix project/calc.py so double multiplies numeric values by two and preserves None. Run python3 project/check.py with the real sandbox exec tool. Preserve check.py unchanged. Write proposal.json version platform-proposal-v1, summary, ready true only after the actual test passes. No research paper, network experiment, repository publishing or new production deployment is authorized by this coding objective.')))
    try:
        result=native.execute(store,workspace,root/'slice',image['image'])
        report['result']=result
        assert result['ready'], 'Bounded coding control did not complete.'
        assert (workspace/'project/check.py').read_text()==test,'Existing acceptance check changed.'
        checked=subprocess.run(['docker','run','--rm','--network','none','--cap-drop','ALL','--mount','type=bind,source='+str(workspace)+',target=/workspace','--workdir','/workspace',image['image'],'python3','project/check.py'],capture_output=True,timeout=30)
        store.artifact('cloud-control-check-stdout.txt',checked.stdout);store.artifact('cloud-control-check-stderr.txt',checked.stderr)
        assert checked.returncode==0 and checked.stdout.strip()==b'three controls passed'
        runs=store.rows('runs');assert 0<len(runs)<=6 and all(r['status']=='complete' for r in runs)
        report.update(passed=True,actual_provider_calls=len(runs),existing_test_unchanged=True,container_check_passed=True,task_id=task['id'],bundle_sha256=root.name,verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        artifact=store.artifact('cloud-control-report.json',canonical(report));report['artifact_id']=artifact['id']
        proof=json.loads((root/'production-verification.json').read_bytes())
        assert proof['passed'] and proof['component']=='frontend' and proof['repository']=='jumpserve-networks/jumpserve-front-end'
        store.rpc('release',dict(id=identity(task['id'],'bootstrap-frontend-verification'),component=proof['component'],repository=proof['repository'],revision=proof['revision'],status='verified',external_id=proof['operation_id'],verification=proof,details=dict(origin='Initial deployment workflow; separate from isolated coding control.')))
        store.checkpoint('completed','Bounded cloud sandbox control passed; initial frontend revision independently verified by the scoped OIDC workflow. The control made no repository changes.',dict(cloud_control=report))
    except Exception as error:
        report['actual_provider_calls']=len(store.rows('runs'))
        store.artifact('cloud-control-unsuccessful-report.json',canonical(report))
        store.checkpoint('blocked','Cloud bootstrap control did not pass. Original calls and evidence remain retained; no replacement call or installation is admitted.',dict(cloud_control=report,cleanup_unknown=isinstance(error,native.CleanupUnknown)))
        raise
    finally:
        stop.set()
        if thread:thread.join(timeout=2)
        save(root/'report.json',canonical(report))
    print(json.dumps(report))

if __name__=='__main__':main()
