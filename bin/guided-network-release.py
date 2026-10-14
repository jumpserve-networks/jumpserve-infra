"""Fixed-target networking release; receipts preserve failed and successful actions."""
import argparse, base64, datetime as dt, hashlib, importlib.util, io, json, os
from pathlib import Path
import subprocess, urllib.error, urllib.request, zipfile, uuid

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

def require_package_evidence():
    revision=json.loads((ROOT/'research-workflow-runtime.json').read_text())['source_revision']
    passed={}
    for path in sorted((ROOT/'.test-artifacts/guided-network/operational').glob('*/receipt.json')):
        value=json.loads(path.read_text())
        if value.get('status')=='passed' and value.get('runtime_source_revision')==revision:
            passed[value.get('case')]=str(path.relative_to(ROOT))
    if not {'success','deadline','cancellation'}<=passed.keys():
        raise RuntimeError('Custom package admission is blocked: matching startup/ingest, deadline and independent cancellation evidence is incomplete. Preserve failed checks; do not bypass reviewed-plan gates.')
    return passed
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

def archive(directory):
    # Fixed release evidence only. No env files, credential caches, cookies or
    # arbitrary user-selected paths are accepted by this command.
    frontend=ROOT.parent/'jumpserve-front-end'
    entries=[]
    for base,prefix,patterns in [
        (ROOT,'infrastructure',['docs/guided-network-release-*.json','research-workflow-runtime.json','real-world-runtime.json','.release-*.log','.test-artifacts/guided-network/release/*/*','.test-artifacts/guided-network/operational/*/*','.test-artifacts/network-execution/database/**/*','.test-artifacts/research-ideas/production/**/*']),
        (frontend,'frontend',['docs/idea-guided-interface-*.json','.release-*.log','.release-runtime-audit.json','.test-artifacts/idea-guide/browser/2026-10-14T20-01-40.014Z/*','.test-artifacts/research-ideas/production/2026-10-14T22-*/*'])]:
        seen=set()
        for pattern in patterns:
            for path in sorted(base.glob(pattern)):
                if not path.is_file() or path in seen or directory in path.parents: continue
                if prefix=='infrastructure' and '/release/' in str(path):
                    receipt=path.parent/'receipt.json'
                    if receipt.exists() and json.loads(receipt.read_text()).get('mode')=='archive': continue
                seen.add(path);entries.append((prefix+'/'+str(path.relative_to(base)),path.read_bytes()))
    # Preserve the exact failed-verifier and verification-source revisions too.
    for revision,name in [('3afe6a8','bin/check-network-package-production.py'),('b2a18ba','bin/check-network-package-production.py')]:
        raw=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        entries.append(('source-revisions/'+revision+'/'+name,raw))
    entries.append(('source-revisions/current-archiver.py',Path(__file__).read_bytes()))
    entries.append(('source-revisions/current-production-browser.mjs',(frontend/'scripts/verify-research-ideas-production.mjs').read_bytes()))
    manifest=[dict(path=name,bytes=len(raw),sha256=sha(raw),container='separate-original' if len(raw)>10_000_000 else 'main-zip') for name,raw in entries]
    (directory/'raw-artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for name,raw in [(name,raw) for name,raw in entries if len(raw)<=10_000_000]+[('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
            item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(item,raw)
    raw=output.getvalue()
    large=[(name,data) for name,data in entries if len(data)>10_000_000]
    if len(raw)>15_000_000 or any(len(data)>15_000_000 for _,data in large) or len(raw)+sum(len(data) for _,data in large)>20_000_000: raise RuntimeError('Release archive exceeds amended per-object or total storage bound')
    (directory/'raw-evidence.zip').write_bytes(raw)
    import sys
    sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
    import store,workflow
    os.environ.update(SUPABASE_URL='https://regphejnlvfpyokpniny.supabase.co',SUPABASE_SERVICE_ROLE_KEY=aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'],SSL_CERT_FILE='/etc/ssl/cert.pem')
    actor=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:service-only:guided-network-release:2026-10-14:v2'))
    study=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:guided-network-release-evidence:2026-10-14:v1'))
    identifier=str(uuid.uuid5(uuid.UUID(study),'raw-release-archive-v2'))
    store.rpc('research_create_study',dict(p_actor=actor,p_id=study,p_document=workflow.paper_details(dict(title='Private production release evidence: guided networking 2026-10-14',domain='Software release evidence',scope='Private deployment evidence only; no scientific claim, Google session or model review is asserted.',study_kind='idea',paper_url=None))))
    separate=[]
    for name,data in large:
        item_id=str(uuid.uuid5(uuid.UUID(study),'separate-original:'+sha(data)))
        item=store.artifact(study,actor,data,item_id,'application/zip',dict(kind='original-deployed-runtime',original_archive_path=name,transformation='none; original deployed ZIP bytes'))
        store.append(study,actor,'artifacts',item)
        if store.artifact_bytes(study,item_id,maximum=15_000_000)!=data: raise RuntimeError('Separate original ZIP retrieval differs')
        separate.append(dict(path=name,artifact_id=item_id,storage_path=item['storage_path'],bytes=len(data),sha256=sha(data),retrieved_hash_verified=True))
    record=store.artifact(study,actor,raw,identifier,'application/zip',dict(kind='production-release-evidence',protocol='guided-network-release-protocol-v1',closure_scope='guided-network-release-closure-scope-v4',archive_amendment='guided-network-release-archive-amendment-v5',separate_originals=separate,original_files=len(entries),transformation='ZIP container of original bytes with per-file manifest; large unchanged original referenced as a separate private artifact'))
    store.append(study,actor,'artifacts',record)
    restored=store.artifact_bytes(study,identifier,maximum=15_000_000)
    if restored!=raw: raise RuntimeError('Release archive retrieval differs')
    public=json.loads((ROOT/'cdk.json').read_text())['context']['supabaseAnonKey']
    request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+record['storage_path'],headers={'apikey':public,'Authorization':'Bearer '+public})
    try:
        with previous.OPEN.open(request,timeout=20) as response: status=response.status
    except urllib.error.HTTPError as error: status=error.code
    if status==200: raise RuntimeError('Private evidence was anonymously readable')
    return dict(study_id=study,artifact_id=identifier,storage_bucket=store.BUCKET,storage_path=record['storage_path'],sha256=sha(raw),bytes=len(raw),files=len(entries),separate_originals=separate,total_stored_bytes=len(raw)+sum(item['bytes'] for item in separate),retrieved_hash_verified=True,anonymous_status=status)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['inspect','backup','migrate','diff','deploy-disabled','deploy-enabled','verify','archive'])
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
        elif args.mode=='archive': report['archive']=archive(directory)
        else:
            if args.mode.startswith('deploy'): verify()
            if args.mode=='deploy-enabled': report['operational_evidence']=require_package_evidence();save()
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
