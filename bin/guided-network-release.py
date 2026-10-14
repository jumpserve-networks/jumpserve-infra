"""Fixed-target networking release; receipts preserve failed and successful actions."""
import argparse, base64, datetime as dt, hashlib, importlib.util, io, json, os
from pathlib import Path
import subprocess, urllib.error, urllib.request, zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('previous_release', ROOT/'bin/research-ideas-release.py')
previous = importlib.util.module_from_spec(spec); spec.loader.exec_module(previous)
admin = previous.admin
MIGRATION = ROOT/'database/202610130002_network_execution.sql'
NAMES = ['research_network_begin','research_network_launch','research_network_update','research_network_pending','research_network_cancel','research_network_token']
API = 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research'

def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def aws(*args):
    return json.loads(subprocess.check_output(['aws',*args,'--profile','jumpserve','--region','us-east-1','--output','json']))
def counts():
    return admin.query("select 'measurements' kind,count(*) from research_measurements union all select 'published_values',count(*) from research_published_values union all select 'assessments',count(*) from research_assessments")
def inspect():
    stack=aws('cloudformation','describe-stacks','--stack-name','JumpServeBenchmarkStack')['Stacks'][0]
    return dict(network_exists=admin.query("select to_regclass('public.research_network_executions') is not null present")[0]['present'],scientific_counts=counts(),pointers=admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id'),active_queue_jobs=admin.query("select status,count(*) from research_queue_jobs where status in ('queued','running') group by status"),benchmark_stack=dict(status=stack['StackStatus'],parameters=stack.get('Parameters',[]),outputs=stack.get('Outputs',[])))
def verify():
    previous.verify()
    rows=admin.query("select relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c where c.oid='public.research_network_executions'::regclass")
    if len(rows)!=1 or not rows[0]['relrowsecurity'] or rows[0]['anon_access'] or rows[0]['browser_access']: raise RuntimeError('Private networking table RLS/grants differ')
    rpc=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ("+','.join(map(admin.literal,NAMES))+") order by proname")
    if len(rpc)!=len(NAMES) or any(r['anon_execute'] or r['browser_execute'] for r in rpc): raise RuntimeError('Private networking RPC grants differ')
    active=admin.query("select active_version_id from agent_prompt_settings where module_id='research-verification'")
    if active!=[{'active_version_id':previous.CANDIDATE}]: raise RuntimeError('Previously evaluated idea prompt differs')
    return dict(passed=True,table=rows,rpc=rpc,prompt_unchanged=True)
def deployed(directory):
    expected=json.loads((ROOT/'research-workflow-runtime.json').read_text())['files']
    resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
    report=[]
    for item in resources:
        if item['ResourceType']!='AWS::Lambda::Function' or not item['LogicalResourceId'].startswith('ResearchWorkflow'): continue
        obj=aws('lambda','get-function','--function-name',item['PhysicalResourceId'])
        config=obj['Configuration'];env=config['Environment']['Variables']
        if ':395567831870:' not in config['FunctionArn'] or env.get('SUPABASE_URL')!='https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Lambda target differs')
        with previous.OPEN.open(obj['Code']['Location'],timeout=30) as response: raw=response.read()
        if base64.b64encode(hashlib.sha256(raw).digest()).decode()!=config['CodeSha256']: raise RuntimeError('Deployed ZIP hash differs')
        (directory/(item['PhysicalResourceId']+'.zip')).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for path,digest in expected.items():
                if sha(archive.read(path))!=digest: raise RuntimeError('Deployed runtime file differs: '+path)
        report.append(dict(function=item['PhysicalResourceId'],handler=config['Handler'],zip_sha256=sha(raw),source_files=len(expected),memory_mb=config['MemorySize'],timeout_seconds=config['Timeout'],custom_admission=bool(env.get('NETWORK_PACKAGE_FUNCTION'))))
    if len(report)!=5: raise RuntimeError('Expected API, worker, package executor, ingest and independent reaper')
    with previous.OPEN.open(API+'/capabilities',timeout=30) as response: capabilities=json.load(response)
    if capabilities['networking']['version']!='network-execution-v1' or not capabilities['queue']['workers_enabled']: raise RuntimeError('New execution capability not deployed')
    denials=[]
    for path,body in [('/network-ingest',{'job_id':'00000000-0000-4000-8000-000000000000','files':{}}),('/studies/00000000-0000-4000-8000-000000000000/network',{'action':'upload-package'})]:
        request=urllib.request.Request(API+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with previous.OPEN.open(request,timeout=20) as response: status=response.status
        except urllib.error.HTTPError as error: status=error.code
        if status not in (401,403): raise RuntimeError('Anonymous privileged action was not denied')
        denials.append(dict(path=path,status=status))
    return dict(runtime=report,capabilities=capabilities,anonymous_denials=denials,database=verify())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['inspect','backup','migrate','diff','deploy-disabled','deploy-enabled','verify'])
    args=parser.parse_args()
    directory=ROOT/'.test-artifacts/guided-network/release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
    report=dict(protocol='docs/guided-network-release-protocol-v1.json',mode=args.mode,status='running',started_at=stamp(),measured_charges_usd=None)
    def save(): (directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        report['targets']=previous.target();save()
        if args.mode=='inspect': report['inspection']=inspect()
        elif args.mode=='backup':
            report['before']=inspect();report['original_functions']=[]
            resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
            for item in resources:
                if item['ResourceType']!='AWS::Lambda::Function' or not item['LogicalResourceId'].startswith(('ResearchWorkflow','RealWorldTests','LaunchBenchmarkFn')): continue
                obj=aws('lambda','get-function','--function-name',item['PhysicalResourceId'])
                with previous.OPEN.open(obj['Code']['Location'],timeout=30) as response: raw=response.read()
                if base64.b64encode(hashlib.sha256(raw).digest()).decode()!=obj['Configuration']['CodeSha256']: raise RuntimeError('Original ZIP hash differs')
                (directory/(item['PhysicalResourceId']+'.zip')).write_bytes(raw)
                report['original_functions'].append(dict(function=item['PhysicalResourceId'],zip_sha256=sha(raw),handler=obj['Configuration']['Handler']))
                save()
        elif args.mode=='migrate':
            before=inspect();report['before']=before;save()
            if before['network_exists']: raise RuntimeError('Network schema already exists; verify instead of reapplying')
            raw=MIGRATION.read_bytes();(directory/MIGRATION.name).write_bytes(raw)
            report['migration']=dict(path=MIGRATION.name,sha256=sha(raw),bytes=len(raw));save()
            admin.query(raw.decode(),read_only=False)
            report['verification']=verify();after=inspect();report['after']=after
            if before['scientific_counts']!=after['scientific_counts'] or before['pointers']!=after['pointers']: raise RuntimeError('Scientific counts or prompt pointers changed during migration; inspect concurrent changes')
        elif args.mode=='verify': report['verification']=deployed(directory)
        else:
            if args.mode.startswith('deploy'): verify()
            credentials=aws('configure','export-credentials','--format','process')
            env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
            command=['npx','cdk','diff' if args.mode=='diff' else 'deploy','JumpServeBenchmarkStack','--app','npx ts-node --prefer-ts-exts bin/benchmark.ts','-c','networkExecutionEnabled=true','-c','networkPackagesEnabled='+str(args.mode=='deploy-enabled').lower()]
            if args.mode=='diff': command+=['--no-change-set']
            else: command+=['--require-approval','never','--outputs-file',str(directory/'outputs.json')]
            report['command']=command;save()
            with (directory/'cdk.log').open('w') as stream: result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode: raise RuntimeError('Scoped CDK command failed; original cdk.log retained')
        report['status']='complete'
    except BaseException as error:
        report.update(status='failed',reason=str(error));raise
    finally:
        report['ended_at']=stamp();save();print(json.dumps(dict(directory=str(directory),mode=args.mode,status=report['status'],reason=report.get('reason'))))
if __name__=='__main__': main()
