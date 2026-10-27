"""Fixed-target OpenClaw release operations; no arbitrary SQL or shell arguments."""
import argparse,datetime as dt,hashlib,importlib.util,json,os,re,shlex,subprocess,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('openclaw_prior',ROOT/'bin/autonomy-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
admin=prior.admin
def aws(*args):
 raw=subprocess.check_output(['aws',*args,'--profile','jumpserve','--region','us-east-1','--output','json'],timeout=60)
 return json.loads(raw) if raw.strip() else {}
MIGRATIONS=[('202610200002_context_budget_recovery.sql',"select to_regprocedure('public.research_autonomy_resume_budget(uuid,uuid,uuid,text,integer)') is not null present"),('202610200008_remove_autonomy_turn_cap.sql',"select exists(select 1 from pg_proc where proname='research_autonomy_resume_turns') present"),('202610200009_openclaw_dispatch.sql',"select to_regclass('public.research_model_dispatches') is not null present"),('202610200010_openclaw_prompt_candidate.sql',"select exists(select 1 from agent_prompt_versions where version='research-autonomy-v9') present"),('202610210001_openclaw_prompt_v10.sql',"select exists(select 1 from agent_prompt_versions where version='research-autonomy-v10') present"),('202610210002_openclaw_publication_guard.sql',"select to_regprocedure('public.publish_agent_prompt_before_openclaw_v10(uuid,uuid,text,jsonb,text,text)') is not null present")]
stamp=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
sha=lambda raw:hashlib.sha256(raw).hexdigest()
MIGRATIONS.append(('202610210003_partial_assessment_recovery.sql',"select to_regprocedure('public.research_autonomy_resume_partial(uuid,uuid,text)') is not null present"))

def target():
 account=aws('sts','get-caller-identity')['Account']
 if account!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny':raise RuntimeError('Release target mismatch')
 result=prior.guard.target()
 return dict(result,aws_account=account,supabase_project=admin.PROJECT_REF)

def instance():
 stack=aws('cloudformation','describe-stacks','--stack-name','JumpServeOpenClawStack')['Stacks'][0]
 result=next(r['OutputValue'] for r in stack['Outputs'] if r['OutputKey']=='OpenClawWorkerInstanceId')
 if not re.fullmatch(r'i-[a-f0-9]+',result):raise RuntimeError('Invalid worker identity')
 return result

def ssm(commands):
 result=aws('ssm','send-command','--instance-ids',instance(),'--document-name','AWS-RunShellScript','--parameters',json.dumps(dict(commands=commands)))
 return dict(command_id=result['Command']['CommandId'],instance_id=instance())

def functions():
 resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 return {kind:next(r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Lambda::Function' and r['LogicalResourceId'].startswith(prefix)) for kind,prefix in [('api','ResearchWorkflowApi'),('autonomy','ResearchWorkflowAutonomyWorker')]}

def auth_maintenance_guard():
 # Native interactive login does not acquire our Python refresh-owner lock by
 # itself. Require held admission/polling and drained calls before stopping it.
 config=aws('lambda','get-function-configuration','--function-name',functions()['api'])
 resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 rules=[r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')]
 if config['Environment']['Variables'].get('RESEARCH_AUTONOMY_ENABLED')!='false' or len(rules)!=1 or aws('events','describe-rule','--name',rules[0])['State']!='DISABLED':raise RuntimeError('Hold new admission and autonomous polling before native authorization maintenance.')
 if admin.query("select (select count(*) from research_autonomy_tasks where status='running')+(select count(*) from research_model_dispatches where status in ('queued','running') or (status='unknown' and greatest(created_at,coalesce(lease_until,created_at),coalesce(ended_at,created_at))>clock_timestamp()-interval '10 minutes')) count")[0]['count']:raise RuntimeError('Drain active or recent uncertain model work before authorization maintenance; preserve original outcomes.')

def auth_maintenance_script(login):
 # login is an internal fixed command, never a caller-supplied CLI argument.
 return "set -eu; task_worker_active=0; if systemctl is-active --quiet jumpserve-openclaw.service; then task_worker_active=1; systemctl stop jumpserve-openclaw.service; fi; trap 'if test \"$task_worker_active\" = 1; then systemctl start jumpserve-openclaw.service; fi' EXIT; "+login

def native_auth_command():
 login='runuser -u jumpserve -- env HOME=/var/lib/jumpserve-openclaw OPENCLAW_STATE_DIR=/var/lib/jumpserve-openclaw/auth OPENCLAW_CONFIG_PATH=/var/lib/jumpserve-openclaw/auth/config.json PATH=/opt/jumpserve/node/bin:/usr/bin:/bin flock -x /var/lib/jumpserve-openclaw/auth/refresh.lock /opt/jumpserve/node/bin/node /opt/jumpserve/openclaw/node_modules/openclaw/openclaw.mjs models auth login --provider openai --method siwc'
 return 'stty cols 2000; sudo -n /bin/bash -c '+shlex.quote(auth_maintenance_script(login))

def host_refresh_command():
 program="import json,sys\nsys.path.insert(0,'/opt/jumpserve/runtime')\nimport openclaw_runtime as r\nr.verify_runtime()\nr.credential(force_refresh=True)\nprint(json.dumps(dict(native_refresh_verified=True,credential_contents_emitted=False)))"
 return 'runuser -u jumpserve -- env RESEARCH_AI_RUNTIME=openclaw-production-v1 /opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)

def benchmark_image():
 resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
 name=next(r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::Lambda::Function' and r['LogicalResourceId'].startswith('LaunchBenchmarkFn'))
 env=aws('lambda','get-function-configuration','--function-name',name)['Environment']['Variables']
 return dict(function=name,ami_id=env['AMI_ID'],mode=env['BENCHMARK_IMAGE_MODE'])

def compare_parameters(before,after,image):
 old={p['ParameterKey']:p for p in before['parameters']};new={p['ParameterKey']:p for p in after['parameters']}
 if {k:v['ParameterValue'] for k,v in old.items()}!={k:v['ParameterValue'] for k,v in new.items()}:raise RuntimeError('Literal benchmark parameters changed')
 if image['mode']!='prebaked' or image['ami_id']!=old['BenchmarkAmiId']['ParameterValue']:raise RuntimeError('Active benchmark image changed')
 drift=[dict(key=k,before=old[k].get('ResolvedValue'),after=new[k].get('ResolvedValue')) for k in old if old[k].get('ResolvedValue')!=new[k].get('ResolvedValue')]
 fallback='/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id'
 if any(old[d['key']]['ParameterValue']!=fallback for d in drift):raise RuntimeError('Unexpected active or non-fallback lookup resolution changed')
 return dict(literal_parameters_unchanged=True,active_benchmark_image=image,resolved_lookup_changes=drift,inactive_fallback_only=True)

def cdk(mode,directory,host=False,activate=False):
 manifest=prior.queue.source()
 if mode=='deploy' and not host:
  backend=ROOT.parent/'jumpserve-back-end'
  if subprocess.check_output(['git','status','--porcelain'],cwd=backend,text=True).strip() or subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=manifest['source_revision']:raise RuntimeError('Exact clean committed backend revision required')
 credentials=aws('configure','export-credentials','--format','process');env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
 command=['npm','run','cdk:openclaw' if host else 'cdk:benchmark','--',mode,'JumpServeOpenClawStack' if host else 'JumpServeBenchmarkStack']
 if not host:command+=['-c','researchAutonomyEnabled=true','-c','researchOpenClawEnabled=true','-c','researchAutonomyAdmissionEnabled='+str(activate).lower()]
 command+=['--no-change-set'] if mode=='diff' else ['--require-approval','never','--outputs-file',str(directory/'outputs.json')]
 before=prior.queue.state() if not host else None
 if before:(directory/'stack-before.json').write_text(json.dumps(before,indent=2)+'\n')
 with (directory/'cdk.log').open('w') as stream:result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
 if result.returncode:raise RuntimeError('Scoped CDK command failed; original log retained')
 if mode=='deploy' and before:
  after=prior.queue.state();(directory/'stack-after.json').write_text(json.dumps(after,indent=2)+'\n');comparison=compare_parameters(before,after,benchmark_image());(directory/'parameter-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
 return dict(command=command,log_sha256=sha((directory/'cdk.log').read_bytes()),source_revision=manifest['source_revision'])

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['inspect','parameters','migrate','hold','host-diff','host-deploy','host-status','host-repair','host-update','auth-correct','auth-start','auth-status','native-auth','host-check','host-refresh','cloud-control','cloud-verify','diff','deploy','activate','verify','publish','frontend-status','partial-resume','record-result']);parser.add_argument('--command-id');args=parser.parse_args()
 directory=ROOT/'.test-artifacts/openclaw-release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
 receipt=dict(protocol='openclaw-production-v1',mode=args.mode,started_at=stamp(),status='running',measured_charges_usd=None)
 def save():(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 save()
 try:
  receipt['targets']=target();save()
  if args.mode=='inspect':
   receipt['inspection']=dict(prompts=prior.pointers(),active=admin.query("select stage,status,count(*) from research_autonomy_tasks where status in ('queued','running','waiting') group by stage,status"),limits=admin.query('select max_attempts,count(*) from research_autonomy_workflows group by max_attempts'),migrations=[dict(name=n,present=admin.query(q)[0]['present']) for n,q in MIGRATIONS])
  elif args.mode=='parameters':
   baseline=ROOT/'.test-artifacts/autonomy-release/20261018T232558867708Z/receipt.json';before=json.loads(baseline.read_bytes())['stack_after'];after=prior.queue.state();receipt['parameter_review']=compare_parameters(before,after,benchmark_image());receipt['comparison_baseline']=dict(path=str(baseline.relative_to(ROOT)),sha256=sha(baseline.read_bytes()),limitation='Last retained historical baseline; the failed first post-deploy guard did not persist its immediate before-state.')
  elif args.mode in ('host-diff','host-deploy'):receipt['cdk']=cdk('diff' if args.mode=='host-diff' else 'deploy',directory,host=True)
  elif args.mode=='hold':
   receipt['before']={};names=functions()
   for kind,name in names.items():
    config=aws('lambda','get-function-configuration','--function-name',name);receipt['before'][kind]=dict(name=name,revision_id=config['RevisionId'])
    if kind=='api':
     variables=config['Environment']['Variables'];variables['RESEARCH_AUTONOMY_ENABLED']='false';aws('lambda','update-function-configuration','--function-name',name,'--revision-id',config['RevisionId'],'--environment',json.dumps(dict(Variables=variables)))
   resources=aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
   for r in resources:
    if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll'):aws('events','disable-rule','--name',r['PhysicalResourceId'])
   receipt['held']=True
   for r in resources:
    if r['ResourceType']=='AWS::Events::Rule' and r['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll') and aws('events','describe-rule','--name',r['PhysicalResourceId'])['State']!='DISABLED':raise RuntimeError('Autonomy poll rule was not held')
  elif args.mode=='migrate':
   if admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count']:raise RuntimeError('Drain active autonomous leases before migration')
   receipt['migrations']=[]
   for name,query in MIGRATIONS:
    present=admin.query(query)[0]['present'];raw=(ROOT/'database'/name).read_bytes();entry=dict(name=name,sha256=sha(raw),bytes=len(raw),status='present-before-release' if present else 'applying');receipt['migrations'].append(entry);save()
    if not present:admin.query(raw.decode(),read_only=False);entry['status']='applied';save()
  elif args.mode in ('diff','deploy','activate'):
   if args.mode=='activate' and admin.query("select version from agent_prompt_versions v join agent_prompt_settings s on s.active_version_id=v.id where s.module_id='research-autonomy'")!=[{'version':'research-autonomy-v10'}]:raise RuntimeError('Evaluated OpenClaw prompt must be active before admission')
   receipt['cdk']=cdk('diff' if args.mode=='diff' else 'deploy',directory,activate=args.mode=='activate')
  elif args.mode=='host-status':
   if args.command_id:
    if not re.fullmatch(r'[a-f0-9-]{36}',args.command_id):raise RuntimeError('Invalid SSM receipt ID')
    result=aws('ssm','get-command-invocation','--command-id',args.command_id,'--instance-id',instance())
    # This mode inspects only our fixed administrative commands, never login logs.
    receipt['command']=dict(status=result['Status'],stdout=result.get('StandardOutputContent','')[-6000:],stderr=result.get('StandardErrorContent','')[-1500:])
   else:receipt['ssm']=ssm(['test -f /opt/jumpserve/dependencies/installed-node.txt && cat /opt/jumpserve/dependencies/installed-node.txt','systemctl is-active jumpserve-openclaw.service || true','tail -n 12 /var/log/cloud-init-output.log','journalctl -u jumpserve-openclaw-setup-recovery --no-pager -n 10'])
  elif args.mode=='host-repair':
   # Exact diagnosed bootstrap failure only; preserve the original user-data bytes.
   receipt['ssm']=ssm(["python3 - <<'PY'\nfrom pathlib import Path\np=Path('/var/lib/cloud/instance/scripts/part-001');raw=p.read_bytes();assert raw.count(b'awscli2')==1\nbackup=Path('/var/lib/jumpserve-openclaw-user-data-original.sh');assert not backup.exists();backup.write_bytes(raw)\nPath('/var/lib/jumpserve-openclaw-user-data-recovery.sh').write_bytes(raw.replace(b'awscli2',b'awscli-2'))\nPY","systemd-run --unit=jumpserve-openclaw-setup-recovery --property=RuntimeMaxSec=1800 /bin/bash /var/lib/jumpserve-openclaw-user-data-recovery.sh"])
  elif args.mode=='host-update':
   if admin.query("select count(*) count from research_model_dispatches where status in ('queued','running','unknown')")[0]['count']:raise RuntimeError('Drain or reconcile dispatched model calls before updating the host')
   values={r['OutputKey']:r['OutputValue'] for r in aws('cloudformation','describe-stacks','--stack-name','JumpServeOpenClawStack')['Stacks'][0]['Outputs']};bucket=values['OpenClawRuntimeBucket'];key=values['OpenClawRuntimeObject']
   if bucket!='cdk-hnb659fds-assets-395567831870-us-east-1' or not re.fullmatch(r'[a-f0-9]{64}\.zip',key):raise RuntimeError('Unexpected pinned runtime asset')
   suffix='before-'+directory.name;backup='/opt/jumpserve/runtime-'+suffix;archive='/opt/jumpserve/runtime-'+key
   receipt['runtime_backup']=backup
   receipt['ssm']=ssm(['set -eu','systemctl stop jumpserve-openclaw.service','test ! -e '+backup,'cp -a /opt/jumpserve/runtime '+backup,'aws s3 cp s3://'+bucket+'/'+key+' '+archive+' --region us-east-1','unzip -o -q '+archive+' -d /opt/jumpserve/runtime','chmod -R a+rX /opt/jumpserve/runtime','systemctl start jumpserve-openclaw.service'])
  elif args.mode=='native-auth':
   # Interactive native login avoids a background pseudo-terminal losing stdin.
   auth_maintenance_guard();login=native_auth_command()
   env=dict(os.environ);env['PATH']=str(ROOT/'.test-artifacts/openclaw-release/tools/sessionmanager-bundle/bin')+':'+env.get('PATH','')
   command=['aws','ssm','start-session','--profile','jumpserve','--region','us-east-1','--target',instance(),'--document-name','AWS-StartInteractiveCommand','--parameters',json.dumps(dict(command=[login]))]
   completed=subprocess.run(command,env=env,timeout=900)
   if completed.returncode:raise RuntimeError('Native host authorization did not complete; preserve its host-specific state and retry sign-in, never inference.')
   receipt['native_session_closed']=True
   receipt['authorization_verified']=False # host-check verifies actual stored consent/catalog separately.
  elif args.mode=='host-refresh':
   receipt['ssm']=ssm([host_refresh_command()])
  elif args.mode=='cloud-verify':
   from openclaw_cloud_verify import verify
   receipt['cloud_control']=verify(__import__('sys').modules[__name__],directory)
  elif args.mode=='cloud-control':
   from openclaw_cloud_control import prepare
   frozen,command=prepare(directory)
   receipt['frozen']=frozen;save();receipt['ssm']=ssm([command])
  elif args.mode=='host-check':
   expected=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['files']
   program="import json,sys,subprocess\nfrom pathlib import Path\nsys.path.insert(0,'/opt/jumpserve/runtime')\nimport openclaw_runtime as r\nr.verify_runtime()\ncatalog=r.catalog(r.credential())\nprint(json.dumps(dict(runtime=r.VERSION,native_refresh_interface_verified=True,catalog=catalog,api_key_fallback=False,credential_contents_emitted=False)))"
   program="import hashlib\nfrom pathlib import Path\nexpected="+repr(expected)+"\nactual={n:hashlib.sha256((Path('/opt/jumpserve/runtime')/n).read_bytes()).hexdigest() for n in expected}\nassert actual==expected,'Pinned host source hashes differ'\nprint('Pinned host source hashes verified: '+str(len(actual)))\n"+program
   command="runuser -u jumpserve -- env RESEARCH_AI_RUNTIME=openclaw-production-v1 /opt/jumpserve/python/bin/python -B -c "+__import__('shlex').quote(program)
   receipt['ssm']=ssm([command])
  elif args.mode=='auth-correct':
   patch=json.loads((ROOT/'assets/openclaw/auth-patch.json').read_bytes())
   program="from pathlib import Path\nimport hashlib,json\np=Path('/opt/jumpserve/openclaw/node_modules/openclaw')/"+repr(patch['path'])+"\nr=p.read_bytes();h=hashlib.sha256(r).hexdigest()\nif h=="+repr(patch['original_sha256'])+":\n b=p.with_suffix(p.suffix+'.original');assert not b.exists() or b.read_bytes()==r;b.write_bytes(r);r=r.replace("+repr(patch['before'].encode())+","+repr(patch['after'].encode())+");assert hashlib.sha256(r).hexdigest()=="+repr(patch['corrected_sha256'])+";p.write_bytes(r)\nassert hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(patch['corrected_sha256'])+"\nprint(json.dumps(dict(callback_patch='openclaw-loopback-ipv4-v1',original_sha256=h,current_sha256=hashlib.sha256(p.read_bytes()).hexdigest())))"
   receipt['ssm']=ssm(['systemctl stop jumpserve-openclaw-login.service || true',"python3.12 - <<'PY'\n"+program+"\nPY",'chmod a+r /opt/jumpserve/openclaw/node_modules/openclaw/dist/token-sharing-CmBELw8t.mjs','systemctl reset-failed jumpserve-openclaw-login.service || true'])
  elif args.mode=='auth-start':
   auth_maintenance_guard();login=native_auth_command()
   receipt['ssm']=ssm(["systemd-run --unit=jumpserve-openclaw-login --property=RuntimeMaxSec=900 /usr/bin/script -q -c "+__import__('shlex').quote('stty cols 2000; exec '+login)+" /var/lib/jumpserve-openclaw/auth-login.log"])
  elif args.mode=='auth-status':
   commands=["python3.12 - <<'PY'\nfrom pathlib import Path\nimport re,json,urllib.parse,subprocess\np=Path('/var/lib/jumpserve-openclaw/auth-login.log');s=p.read_text(errors='replace') if p.exists() else ''\ns=re.sub(r'\\x1b\\[[0-?]*[ -/]*[@-~]','',s)\nurls=re.findall(r'https://auth.openai.com/[^\\s\\x1b]+',s)\nurl=next((u for u in reversed(urls) if urllib.parse.urlsplit(u).path.endswith('/authorize') and {'state','code_challenge'}<=set(urllib.parse.parse_qs(urllib.parse.urlsplit(u).query))),None)\nif url and {'id_token_hint','code','access_token','refresh_token'}&set(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)):url=None\nerrors=[line.strip()[:300] for line in s.splitlines() if re.search(r'Error:|EACCES|ENOENT|Cannot find|already in use',line) and not re.search(r'https?://|token|code=|secret',line,re.I)]\nprint(json.dumps(dict(authorization_url=url,log_bytes=p.stat().st_size if p.exists() else 0,errors=errors[-3:],service_active=subprocess.run(['systemctl','is-active','--quiet','jumpserve-openclaw-login.service']).returncode==0,url_paths=[urllib.parse.urlsplit(u).path for u in urls],credential_store_exists=Path('/var/lib/jumpserve-openclaw/auth/state/openclaw.sqlite').exists())))\nPY"]
   receipt['ssm']=ssm(commands)
  elif args.mode=='verify':
   receipt['pointers']=prior.pointers();receipt['capability']=json.load(prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30))
   cap=receipt['capability']['autonomy']
   if cap['version']!='research-autonomy-v3' or cap['defaults']['attempts_per_claim'] is not None or cap['runtime']['runtime']!='openclaw-production-v1':raise RuntimeError('Deployed runtime/default capabilities differ')
   receipt['functions']=prior.functions(directory,True)
   prior.PRIVATE|={'research_model_workers','research_model_dispatches'}
   receipt['database_security']=prior.security()
   rows=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c where c.oid='public.agent_prompt_evaluations'::regclass")
   if len(rows)!=1 or not rows[0]['relrowsecurity'] or rows[0]['anon_access'] or rows[0]['browser_access']:raise RuntimeError('Evaluation records must remain private with RLS')
   receipt['evaluation_security']=rows;receipt['runtime_iam']=[]
   receipt['partial_recovery_security']=admin.query("select has_function_privilege('anon','research_autonomy_resume_partial(uuid,uuid,text)','EXECUTE') anon_execute,has_function_privilege('authenticated','research_autonomy_resume_partial(uuid,uuid,text)','EXECUTE') browser_execute,has_function_privilege('service_role','research_autonomy_resume_partial(uuid,uuid,text)','EXECUTE') service_execute")
   if receipt['partial_recovery_security']!=[dict(anon_execute=False,browser_execute=False,service_execute=True)]:raise RuntimeError('Partial recovery RPC access differs')
   for kind,name in functions().items():
    config=aws('lambda','get-function-configuration','--function-name',name)
    if config['Environment']['Variables'].get('RESEARCH_AI_RUNTIME')!='openclaw-production-v1':raise RuntimeError('Unexpected production AI runtime')
    if kind=='autonomy':
     role=config['Role'].rsplit('/',1)[1];names=aws('iam','list-role-policies','--role-name',role)['PolicyNames'];policies=[aws('iam','get-role-policy','--role-name',role,'--policy-name',p)['PolicyDocument'] for p in names]
     if 'bedrock:' in json.dumps(policies).lower():raise RuntimeError('OpenClaw worker must not retain Bedrock fallback permission')
     receipt['runtime_iam'].append(dict(role=role,policy_sha256=sha(json.dumps(policies,sort_keys=True).encode()),bedrock_permission=False))
  elif args.mode=='publish':
   from openclaw_evaluation import publication
   receipt['publication']=publication(admin)
  elif args.mode=='partial-resume':
   # Fixed, exposed release-control identity only; no operator-supplied SQL/IDs.
   receipt['deployed_sources']=prior.functions(directory,True)
   replay=json.loads((ROOT/'docs/openclaw-production-partial-replay-v1.json').read_bytes());manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
   if replay['status']!='passed' or replay['corrected_controller_sha256']!=manifest['files']['autonomy.py']:raise RuntimeError('Corrected controller replay does not match deployed source')
   raw=(ROOT/'docs/openclaw-production-controller-validation-v1.json').read_text()
   admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([admin.literal('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e')+'::uuid',admin.literal('passed'),admin.literal(raw),admin.literal(sha(raw.encode())),admin.literal(json.dumps(dict(kind='controller-only-follow-up',original_prompt_evaluation_unchanged=True,replay=replay)))+'::jsonb',admin.literal('Primary Codex AI implementer; nonindependent controller regression, zero new model calls')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
   receipt['resumption']=admin.query("select research_autonomy_resume_partial('5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74'::uuid,'7842ae5a-c516-5495-ad98-4df571163f05'::uuid,'continue-retained-checks-v1') result",read_only=False)
  elif args.mode=='record-result':
   release=json.loads((ROOT/'docs/openclaw-production-release-status-v1.json').read_bytes());manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
   archive=release['private_archives']['completed_paper_control']
   if release['software_status']!='deployed-and-verified' or release['backend_revision']!=manifest['source_revision'] or archive['sha256']!=archive['retrieved_sha256']:raise RuntimeError('Verified exact release and retrieved private evidence required')
   actual=admin.query("select (select count(*) from research_autonomy_turns where study_id='5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74' and status='complete') turns,(select count(*) from research_runs where study_id='5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74' and status='complete') runs,(select count(*) from research_measurements where study_id='5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74' and status='recorded') measurements")
   if actual!=[dict(turns=66,runs=6,measurements=1152)]:raise RuntimeError('Retained production result changed; record a new follow-up rather than this frozen report')
   receipt['database_results']=[]
   for name in ('openclaw-production-authenticated-result-v1.json','openclaw-production-arithmetic-v1.json','openclaw-production-claim-coverage-v1.json','openclaw-production-release-status-v1.json'):
    raw=(ROOT/'docs'/name).read_text();digest=sha(raw.encode())
    admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([admin.literal('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e')+'::uuid',admin.literal('passed'),admin.literal(raw),admin.literal(digest),admin.literal(json.dumps(dict(kind='production-end-to-end-follow-up',prompt_publication_unchanged=True,private_archive=archive)))+'::jsonb',admin.literal('Primary Codex AI implementer; nonindependent production follow-up, not a new sixteen-case prompt evaluation')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
    rows=admin.query('select report_sha256,encode(sha256(convert_to(report_raw,\'UTF8\')),\'hex\') retrieved_sha256 from agent_prompt_evaluations where prompt_version_id=\'6117e5c5-84ce-5c31-aaa7-0d1d3522e62e\' and report_sha256='+admin.literal(digest))
    if rows!=[dict(report_sha256=digest,retrieved_sha256=digest)]:raise RuntimeError('Stored original report hash differs')
    receipt['database_results'].append(dict(name=name,sha256=digest,retrieved_sha256=digest))
  elif args.mode=='frontend-status':receipt['jobs']=aws('amplify','list-jobs','--app-id','d24jvguj7brnkj','--branch-name','main','--max-results','3')['jobSummaries']
  receipt.update(status='complete',ended_at=stamp());save();print(json.dumps(dict(directory=str(directory),**receipt),indent=2))
 except Exception as error:receipt.update(status='failed',reason=str(error),ended_at=stamp());save();print(json.dumps(dict(directory=str(directory),status='failed',reason=str(error))));raise
if __name__=='__main__':main()
