"""Explicit, target-guarded migration and security verification. Never imports paper data."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py')
admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
MIGRATION=ROOT/'database/202610070001_research_workflow.sql'
QUEUE_MIGRATION=ROOT/'database/202610070002_research_queue.sql'
PREPARATION_MIGRATION=ROOT/'database/202610070003_research_preparation.sql'
PRIVATE=('research_study_owners','research_artifacts','research_audit_events','research_queue_jobs','research_queue_events','research_prepared_plans')

def targets():
    account=json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve'],timeout=15))['Account']
    url=json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']
    if account!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny' or url!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Target mismatch; no migration applied.')
    # This request uses the exact guarded Management API project path.
    database=admin.query('select current_database() as database')[0]['database']
    return dict(aws_account=account,supabase_project=admin.PROJECT_REF,database=database)

def verify(target, queue=False, preparation=False):
    security=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_read,has_table_privilege('authenticated',c.oid,'SELECT') browser_read,has_table_privilege('anon',c.oid,'INSERT,UPDATE,DELETE') anon_write,has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'research_%' and c.relkind='r'")
    expected=21 if preparation else 20 if queue else 18
    if len(security)!=expected:raise RuntimeError('Research relation coverage differs; inspect before release. Use --queue or --preparation for that schema version.')
    for row in security:
        readable=row['relname'] not in PRIVATE
        if not row['relrowsecurity'] or row['anon_read']!=readable or row['browser_read']!=readable or row['anon_write'] or row['browser_write']:raise RuntimeError('RLS or browser grants failed: '+row['relname'])
    bucket=admin.query("select public from storage.buckets where id='research-workflow-raw'")
    if bucket!=[{'public':False}]:raise RuntimeError('Research originals bucket is not private.')
    policy=admin.query("select permissive,roles,cmd from pg_policies where schemaname='storage' and tablename='objects' and policyname='research_private_raw'")
    if len(policy)!=1 or policy[0]['permissive']!='RESTRICTIVE':raise RuntimeError('Private raw-object restriction missing.')
    rpc=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ('research_create_study','research_append','research_append_bundle','research_publish','research_evidence_manifest')")
    if len(rpc)!=5 or any(row['anon_execute'] or row['browser_execute'] for row in rpc):raise RuntimeError('Browser research RPC writes or private manifest access enabled.')
    queue_rpc=[];preparation_rpc=[]
    if queue:
        queue_rpc=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ('research_queue_enqueue','research_queue_claim','research_queue_finish','research_queue_action','research_queue_snapshot')")
        if len(queue_rpc)!=5 or any(row['anon_execute'] or row['browser_execute'] for row in queue_rpc):raise RuntimeError('Browser queue RPC access enabled or queue functions missing.')
    if preparation:
        preparation_rpc=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname='research_prepare_plan'")
        if len(preparation_rpc)!=1 or any(row['anon_execute'] or row['browser_execute'] for row in preparation_rpc):raise RuntimeError('Browser preparation RPC access enabled or preparation function missing.')
    return dict(targets=target,passed=True,security=security,bucket=bucket,private_policy=policy,rpc=rpc,queue_rpc=queue_rpc,preparation_rpc=preparation_rpc,local_migration_sha256=hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),local_queue_migration_sha256=hashlib.sha256(QUEUE_MIGRATION.read_bytes()).hexdigest() if queue else None,local_preparation_migration_sha256=hashlib.sha256(PREPARATION_MIGRATION.read_bytes()).hexdigest() if preparation else None,deployed_migration_original_bytes_verified=False,limitation='Catalog/grant verification does not recover or hash the originally executed SQL. Save the apply receipt and versioned migration bytes.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--queue',action='store_true');parser.add_argument('--apply-queue',action='store_true');parser.add_argument('--preparation',action='store_true');parser.add_argument('--apply-preparation',action='store_true');parser.add_argument('--inspect',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():raise SystemExit('Preserve the prior migration report; choose a new version.')
    target=targets()
    if args.inspect:
        if args.apply or args.apply_queue or args.apply_preparation:raise SystemExit('Inspection cannot apply migrations.')
        result=dict(targets=target,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),read_only=True,
                    relations=admin.query("select c.relname,c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'research_%' and c.relkind='r' order by c.relname"))
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));return
    if args.apply:
        if admin.query("select to_regclass('public.research_studies') is not null as present")[0]['present']:raise RuntimeError('Research schema already exists; verify it or create a new migration, never replace it.')
        admin.query(MIGRATION.read_text(),read_only=False)
    if args.apply_queue:
        if not admin.query("select to_regclass('public.research_studies') is not null as present")[0]['present']:raise RuntimeError('Apply the original workflow migration first.')
        if admin.query("select to_regclass('public.research_queue_jobs') is not null as present")[0]['present']:raise RuntimeError('Queue schema already exists; verify it or append a migration, never replace it.')
        admin.query(QUEUE_MIGRATION.read_text(),read_only=False)
    if args.apply_preparation:
        if not admin.query("select to_regclass('public.research_queue_jobs') is not null as present")[0]['present']:raise RuntimeError('Apply the queue migration first.')
        if admin.query("select to_regclass('public.research_prepared_plans') is not null as present")[0]['present']:raise RuntimeError('Preparation schema already exists; verify it or append a migration, never replace it.')
        admin.query(PREPARATION_MIGRATION.read_text(),read_only=False)
    result=verify(target,queue=args.queue or args.apply_queue or args.preparation or args.apply_preparation,preparation=args.preparation or args.apply_preparation);result['migration_applied_by_this_call']=args.apply;result['queue_migration_applied_by_this_call']=args.apply_queue;result['preparation_migration_applied_by_this_call']=args.apply_preparation;result['created_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
