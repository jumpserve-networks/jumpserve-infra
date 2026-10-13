"""Guarded, bounded release of the researched idea feature; no synthetic studies."""
import argparse,datetime as dt,hashlib,importlib.util,json,os,ssl,subprocess,sys,urllib.request,zipfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('research_admin',ROOT/'bin/research-workflow-database.py');db=importlib.util.module_from_spec(spec);spec.loader.exec_module(db)
admin=db.admin
MODULE='research-verification';CANDIDATE='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8'
MIGRATIONS=('202610120001_research_ideas.sql','202610120002_research_idea_prompt.sql','202610120003_research_idea_prompt_seed.sql','202610120004_research_idea_prompt_seed_v2.sql','202610130001_research_idea_review_roles.sql')
PRIVATE=('research_idea_packets','research_idea_sessions','research_idea_runs','research_idea_readiness','research_idea_campaign_links')
OPEN=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform=='darwin' else None)))
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def target():
 t=db.targets()
 request=urllib.request.Request('https://api.supabase.com/v1/projects/'+admin.PROJECT_REF,headers={'Authorization':'Bearer '+admin.credential()})
 with OPEN.open(request,timeout=20) as response:p=json.load(response)
 if p.get('id')!=admin.PROJECT_REF:raise RuntimeError('Supabase project identity mismatch')
 t['supabase_project_identity_verified']=True
 return t

def inspect():
 return dict(relations=admin.query("select c.relname,c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'research_%' and c.relkind='r' order by relname"),
  columns=admin.query("select column_name,is_nullable from information_schema.columns where table_schema='public' and table_name='research_studies' order by ordinal_position"),
  pointers=admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id'),
  publication_guard=admin.query("select pg_get_functiondef('public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text)'::regprocedure) as definition"),
  scientific_counts=admin.query("select 'research_measurements' relation,count(*) from research_measurements union all select 'research_published_values',count(*) from research_published_values union all select 'research_assessments',count(*) from research_assessments"))

def verify():
 rows=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ("+','.join(map(admin.literal,PRIVATE))+") order by relname")
 if len(rows)!=5 or any(not r['relrowsecurity'] or r['anon_access'] or r['browser_access'] for r in rows):raise RuntimeError('Idea private relation grants/RLS differ')
 names=['research_save_idea_packet','research_begin_idea_run','research_finish_idea_run','research_accept_idea_plan','research_prepare_idea_campaign','research_idea_ready','research_idea_owner']
 funcs=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ("+','.join(map(admin.literal,names))+") order by proname")
 if len(funcs)!=len(names) or any(r['anon_execute'] or r['browser_execute'] for r in funcs):raise RuntimeError('Browser privileged RPC access or missing functions')
 if admin.query("select count(*) count from research_studies where (study_kind='idea' and paper_url is not null) or (study_kind='paper' and paper_url is null)")[0]['count']!=0:raise RuntimeError('Invalid study origin data')
 bucket=admin.query("select public from storage.buckets where id='research-workflow-raw'")
 if bucket!=[{'public':False}]:raise RuntimeError('Original artifact bucket must remain private')
 return dict(passed=True,security=rows,rpc=funcs,private_originals=bucket,pointers=admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id'))

def artifact_bundle(directory):
 # Retain original successful AND failed provider output bytes in private Storage.
 entries=[]
 for folder in ('20261012T234854600560Z','20261013T002350223340Z'):
  for path in sorted((ROOT/'.test-artifacts/research-ideas/evaluations'/folder).glob('*')):
   if path.is_file():entries.append(('evaluations/'+folder+'/'+path.name,path.read_bytes()))
 if not entries:raise RuntimeError('Original evaluated artifact bytes are unavailable')
 for name in ('research-ideas-protocol-v1.json','research-ideas-amendment-v2.json'):
  entries.append(('protocols/'+name,(ROOT/'docs'/name).read_bytes()))
 manifest=[dict(path=n,sha256=sha(b),byte_count=len(b)) for n,b in entries]
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for name,data in entries+[('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
   z=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));z.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(z,data)
 raw=out.getvalue()
 if len(raw)>2000000:raise RuntimeError('Original evaluation archive exceeds the declared release budget')
 digest=sha(raw);(directory/'evaluation-artifacts.zip').write_bytes(raw)
 key=json.loads(subprocess.check_output(['aws','secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key','--profile','jumpserve','--region','us-east-1','--output','json']))['SecretString']
 base='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'
 path='release-verification/research-ideas-20261013/'+digest+'.zip'
 headers={'apikey':key,'Authorization':'Bearer '+key}
 try:
  req=urllib.request.Request(base+path,data=raw,method='POST',headers={**headers,'Content-Type':'application/zip','x-upsert':'false'})
  with OPEN.open(req,timeout=20) as response:response.read()
 except urllib.error.HTTPError as e:
  if e.code!=409:raise RuntimeError('Private artifact upload failed (HTTP '+str(e.code)+')') from None
 with OPEN.open(urllib.request.Request(base+path,headers=headers),timeout=20) as response:stored=response.read(2_000_001)
 if stored!=raw or sha(stored)!=digest:raise RuntimeError('Stored original artifact hash differs after retrieval')
 config=json.loads((ROOT/'cdk.json').read_text())['context'];public_key=config['supabaseAnonKey']
 with OPEN.open(urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/auth/v1/settings',headers={'apikey':public_key}),timeout=20) as response:
  if response.status!=200:raise RuntimeError('Public credential validation failed')
 public_status=200
 try:
  with OPEN.open(urllib.request.Request(base+path,headers={'apikey':public_key}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as e:public_status=e.code
 if public_status==200:raise RuntimeError('Private original artifact became public')
 return dict(storage_bucket='research-workflow-raw',storage_path=path,sha256=digest,byte_count=len(raw),stored_bytes_verified_after_retrieval=True,original_file_manifest=manifest,anonymous_read_status=public_status,data_origin='model-output and software development fixtures; no scientific measurements',measured_charges_usd=None)

def publish(directory):
 report=json.loads((ROOT/'docs/research-ideas-release-evidence/evaluation-reviewed-v2.json').read_text())
 if report['prompt_version_id']!=CANDIDATE or report['reviewer']['passed'] is not True or len(report['cases'])!=8 or not all(c['passed'] for c in report['cases']):raise RuntimeError('Candidate evaluation/review failed')
 for name,digest in report['runtime_hashes'].items():
  if sha((ROOT/name).read_bytes())!=digest:raise RuntimeError('Evaluated model runtime changed: '+name)
 for case in report['cases']:
  path=ROOT/'.test-artifacts/research-ideas/evaluations/20261013T002350223340Z'/(case['name']+'-output.txt')
  if sha(path.read_bytes())!=case['output_sha256']:raise RuntimeError('Original answer hash differs')
 report['release_artifacts']=artifact_bundle(directory)
 rows=admin.query("select active_version_id from agent_prompt_settings where module_id='research-verification'")
 if len(rows)!=1:raise RuntimeError('Prompt settings missing')
 previous=rows[0]['active_version_id']
 if previous==CANDIDATE:return dict(replayed=True,active_version_id=CANDIDATE,artifact=report['release_artifacts'])
 if previous is not None:raise RuntimeError('Unexpected prior idea prompt; inspect before replacement')
 sql='select publish_agent_prompt('+','.join([admin.literal(CANDIDATE)+'::uuid','null::uuid',admin.literal(report['prompt_content_sha256']),admin.literal(json.dumps(report))+'::jsonb',admin.literal('Codex AI release implementer; user-authorized production release'),admin.literal(MODULE)])+')'
 result=admin.query(sql,read_only=False)
 active=admin.query("select v.id,v.version,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id='research-verification'")
 if len(active)!=1 or active[0]['id']!=CANDIDATE or active[0]['content_sha256']!=report['prompt_content_sha256']:raise RuntimeError('Published pointer differs from evaluated candidate')
 return dict(active=active,publication_result=result,artifact=report['release_artifacts'],reviewer=report['reviewer'])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','migrate','verify','publish','diff','deploy']);a=p.parse_args()
 directory=ROOT/'.test-artifacts/research-ideas/release'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
 report=dict(mode=a.mode,started_at=stamp(),status='running',authorization='User requested merge to main and production deployment on 2026-10-13',measured_charges_usd=None)
 def save():(directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  report['targets']=target();save()
  if a.mode=='inspect':report['inspection']=inspect()
  elif a.mode=='verify':report['verification']=verify()
  elif a.mode=='migrate':
   before=inspect();report['before']=before;save()
   if any(r['relname'] in PRIVATE for r in before['relations']):raise RuntimeError('Idea schema already exists; inspect receipts before any reapplication')
   report['migrations']=[]
   for name in MIGRATIONS:
    raw=(ROOT/'database'/name).read_bytes();entry=dict(name=name,sha256=sha(raw),byte_count=len(raw),status='running');report['migrations'].append(entry);save()
    admin.query(raw.decode(),read_only=False);entry.update(status='complete',ended_at=stamp());save()
   report['verification']=verify();after=inspect();report['scientific_counts_after']=after['scientific_counts']
   if before['scientific_counts']!=after['scientific_counts']:raise RuntimeError('Scientific record counts changed during migration; inspect concurrency')
   old={r['module_id']:r['active_version_id'] for r in before['pointers']};new={r['module_id']:r['active_version_id'] for r in after['pointers']}
   if any(new.get(k)!=v for k,v in old.items()):raise RuntimeError('Existing chat prompt pointers changed')
  elif a.mode=='publish':report['publication']=publish(directory)
  else:
   if a.mode=='deploy':
    verify();active=admin.query("select active_version_id from agent_prompt_settings where module_id='research-verification'")
    if active!=[{'active_version_id':CANDIDATE}]:raise RuntimeError('Evaluated idea prompt not active')
   credentials=json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile','jumpserve','--format','process']))
   env=dict(os.environ,AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1');env.pop('AWS_PROFILE',None)
   command=['npx','cdk',a.mode,'JumpServeBenchmarkStack','JumpServeAgentStack']
   if a.mode=='diff':command+=['--no-change-set']
   if a.mode=='deploy':command+=['--require-approval','never','--outputs-file',str(directory/'outputs.json')]
   report['command']=command;save()
   with (directory/'cdk.log').open('w') as logfile:
    result=subprocess.run(command,cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT)
   if result.returncode:raise RuntimeError('Scoped CDK '+a.mode+' failed; retained cdk.log')
  report['status']='complete'
 except Exception as error:
  report.update(status='failed',reason=str(error));raise
 finally:report['ended_at']=stamp();save();print(json.dumps(dict(directory=str(directory),mode=a.mode,status=report['status'],reason=report.get('reason'))))
if __name__=='__main__':main()
