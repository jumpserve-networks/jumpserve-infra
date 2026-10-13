"""Import immutable ReliableSketch evidence into verified JumpServe only."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STUDY=ROOT.parent/'jumpserve-back-end/experiments/reliable_sketch'
spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
SCHEMAS={
'protocols':'id text,version integer,stage text,document jsonb,sha256 text,locked_at timestamptz',
'campaigns':'id text,protocol_id text,title text,stage text,status text,planned_runs integer,recorded_runs integer,experiment_type text,elapsed_seconds numeric,limitations jsonb,provenance jsonb,usage jsonb',
'configurations':'id text,campaign_id text,algorithm text,skewness numeric,budget_bytes integer,budget_regime text,input_sha256 text,details jsonb,requested_resources jsonb,actual_resources jsonb',
'runs':'id text,campaign_id text,configuration_id text,protocol_id text,stage text,status text,reason text,algorithm text,seed integer,input_sha256 text,raw_sha256 text,analysis_sha256 text,analysis_version text,started_at timestamptz,ended_at timestamptz,measurements jsonb',
'measurements':'run_id text,metric text,value numeric,status text,reason text,units text',
'summaries':'configuration_id text,campaign_id text,planned integer,recorded integer,failed integer,excluded integer,statistics jsonb,interval_kind text,observed_keys integer,query_population text,zero_outlier_runs integer,lossless_runs integer,interval_valid_runs integer',
'sources':'reference_number integer,citation text,doi text,kind text,role text,source_url text,retrieved_url text,access_status text,review_status text,retrieved_version text,sha256 text,byte_count bigint,pages integer,findings text,limitations text,retrieval_attempts jsonb,reviewer jsonb',
'claims':'id text,location text,description text,assessment text,evidence text,limitation text,proposed_check text,required_inputs text,feasibility text',
'published':'id text,source_number integer,location text,metric text,values jsonb,units text',
'controls':'id text,protocol_id text,stage text,payload jsonb',
'control_runs':'id text,control_id text,implementation text,seed integer,key integer,weight integer,status text,reason text,raw_sha256 text,payload jsonb',
'meta':'id text,analysis_version text,assessment_sha256 text,review_definition text,label_definitions jsonb,validation jsonb,counts jsonb,provenance jsonb,costs jsonb',
'artifacts':'id text,sha256 text,byte_count bigint,manifest jsonb,storage_path text,payload jsonb'
}
KEYS={k:'id' for k in SCHEMAS};KEYS.update(measurements='run_id,metric',summaries='configuration_id',sources='reference_number')
def targets():
 account=json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve']))['Account']
 if account!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny':raise RuntimeError('Target identity mismatch')
 url=json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']
 if url!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Supabase URL mismatch')
 return dict(aws_account=account,supabase_project=admin.PROJECT_REF)
def insert(name,rows):
 columns=[f.split()[0] for f in SCHEMAS[name].split(',')];changes=','.join(f'{c}=excluded.{c}' for c in columns if c not in KEYS[name].split(','))
 for offset in range(0,len(rows),200):
  admin.query(f"insert into public.reliable_study_{name} ({','.join(columns)}) select {','.join(columns)} from jsonb_to_recordset({admin.literal(json.dumps(rows[offset:offset+200]))}::jsonb) r({SCHEMAS[name]}) on conflict({KEYS[name]}) do update set {changes}",read_only=False)
def verify():
 t=targets();counts={n:admin.query(f'select count(*) n from public.reliable_study_{n}')[0]['n'] for n in SCHEMAS}
 security=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_select,has_table_privilege('authenticated',c.oid,'SELECT') browser_select,has_table_privilege('anon',c.oid,'INSERT') anon_insert,has_table_privilege('authenticated',c.oid,'INSERT') browser_insert,has_table_privilege('anon',c.oid,'UPDATE') anon_update,has_table_privilege('authenticated',c.oid,'UPDATE') browser_update,has_table_privilege('anon',c.oid,'DELETE') anon_delete,has_table_privilege('authenticated',c.oid,'DELETE') browser_delete from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'reliable_study_%' and c.relkind='r'")
 if len(security)!=13:raise RuntimeError('Study relation security coverage differs')
 for row in security:
  public=row['relname']!='reliable_study_artifacts'
  if row['relrowsecurity'] is not True or row['anon_select']!=public or row['browser_select']!=public:raise RuntimeError('Study read security differs')
  if any(row[k] for k in ('anon_insert','browser_insert','anon_update','browser_update','anon_delete','browser_delete')):raise RuntimeError('Study browser writes allowed')
 return dict(targets=t,counts=counts,security=security,passed=True)
def apply():
 t=targets();path=STUDY/'evidence/assessment-v1.json';data=json.loads(path.read_text());sha=hashlib.sha256(path.read_bytes()).hexdigest()
 if len(data['runs'])!=1080 or len(data['measurements'])!=18360 or len(data['sources'])!=47:raise RuntimeError('Evidence coverage mismatch')
 for item in data['manifest']:
  if hashlib.sha256((STUDY/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Original bytes changed')
 present=admin.query("select to_regclass('public.reliable_study_meta') is not null present")[0]['present']
 if not present:admin.query((ROOT/'database/202610050001_reliable_study.sql').read_text(),read_only=False)
 prior=admin.query("select assessment_sha256 from reliable_study_meta where id='assessment-v1'")
 if prior and prior[0]['assessment_sha256']!=sha:raise RuntimeError('Existing assessment differs; version it')
 data['control_runs']=[]
 for c in data['controls']:
  c['protocol_id']=c['id'];payload=dict(c);c['payload']=payload
  for implementation,rows in payload['weighted'].items():
   for r in rows:
    parsed=r.get('parsed') or {};key=parsed.get('key')
    data['control_runs'].append(dict(id=f'{c["id"]}-{implementation}-{r["seed"]}-{key}',control_id=c['id'],implementation=implementation,seed=r['seed'],key=key,weight=5,status=r['status'],reason=None if r['status']=='complete' else 'Failed weighted control',raw_sha256=r['stdout_sha256'],payload=r))
 for c in data['campaigns']:
  c['usage']={k:c.get(k) for k in ('costs','requested_resources','actual_resources','started_at','ended_at')}
 for n in ('protocols','campaigns','configurations','runs','measurements','summaries','sources','claims','published','controls','control_runs'):
  insert(n,data[n]);print(n,len(data[n]),flush=True)
 costs=dict(local_campaign_wall_seconds=sum(c['elapsed_seconds'] for c in data['campaigns']),aws_experiment_instances=0,aws_experiment_compute_estimate_usd=0,local_power_allocation_usd=None,model_evaluation_usage=None,storage_bytes=sum(m['bytes'] for m in data['manifest']),storage_charges_usd=None,hosting_build_charges_usd=None,codex_orchestration_usage=None,limitation='No billing reconciliation; missing usage is not zero. AWS experiment estimate excludes existing hosting, storage, deployment, model and orchestration costs.')
 meta=dict(id='assessment-v1',analysis_version=data['analysis_version'],assessment_sha256=sha,review_definition=data['review_definition'],label_definitions=data['label_definitions'],validation=data['validation'],counts={n:len(data[n]) for n in ('protocols','campaigns','configurations','runs','measurements','summaries','sources','claims','published','controls','control_runs')},provenance=dict(manifest=data['manifest'],reviewer=dict(identity='Codex primary assistant',type='AI',independence='Same implementer; no human review'),direct_references=45,artifact_commit='5a83f03c775142401d23a78e7e81b163ddf7b604'),costs=costs)
 insert('meta',[meta]);insert('artifacts',[dict(id='assessment-v1',sha256=sha,byte_count=path.stat().st_size,manifest=data['manifest'],storage_path=None,payload=dict(analysis_version=data["analysis_version"],original_assessment_sha256=sha,raw_bytes_location="pending private content-addressed storage"))])
 return dict(targets=t,assessment_sha256=sha,verification=verify())
def prepare():
 t=targets()
 for name in ('202610050002_reliable_prompt_publication.sql','202610050003_reliable_prompt_seed.sql','202610050004_reliable_prompt_seed_v2.sql','202610050005_reliable_evaluation_v3.sql','202610050006_reliable_integrity.sql','202610050007_agent_research_provenance.sql'):
  if name=='202610050006_reliable_integrity.sql' and admin.query("select exists(select1from pg_constraint where conname='reliable_finite_value') applied".replace('select1from','select 1 from'))[0]['applied']:continue
  admin.query((ROOT/'database'/name).read_text(),read_only=False)
 return dict(targets=t,prompt='immutable draft, inactive until reviewed evaluation passes')
def export_release():
 targets();path=ROOT/'docs/reliable-study-validation/chat-evaluation-v3.json';report=json.loads(path.read_text())
 sha=hashlib.sha256(path.read_bytes()).hexdigest();insert('artifacts',[dict(id='chat-evaluation-v3',sha256=sha,byte_count=path.stat().st_size,manifest=[],storage_path=None,payload=report)])
 rows=admin.query("select v.id,v.version,v.module_id,v.system_prompt,v.research_context,v.content_sha256,v.published_at,p.evaluation_report from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id join agent_prompt_publications p on p.prompt_version_id=v.id where s.module_id='reliable-sketch-study' order by p.published_at desc limit 1")
 if len(rows)!=1 or rows[0]['evaluation_report']['id']!=report['id']:raise RuntimeError('No matching publication')
 out=ROOT.parent/'jumpserve-front-end/public/module/reliable-sketch-study';out.mkdir(parents=True,exist_ok=True)
 (out/'chat-release.json').write_text(json.dumps(rows[0],indent=2)+'\n')
 reports=[]
 for evaluation in sorted((ROOT/'docs/reliable-study-validation').glob('chat-evaluation-v*.json')):
  r=json.loads(evaluation.read_text());reports.append(r)
  insert('artifacts',[dict(id=evaluation.stem,sha256=hashlib.sha256(evaluation.read_bytes()).hexdigest(),byte_count=evaluation.stat().st_size,manifest=[],storage_path=None,payload=r)])
 costs=dict(estimated_model_cost_usd=sum(r['estimated_model_cost_usd'] for r in reports),evaluation_records=len(reports),model_evaluation_usage=[dict(evaluation=r.get('protocol_id',r['id']),cases=[{k:c.get(k) for k in ('name','status','passed','answer_usage','judge_usage')} for c in r['cases']]) for r in reports],model_failed_calls_without_usage=sum(c['status']=='failed' and not c.get('judge_usage') for r in reports for c in r['cases']),pricing=report['pricing'],measured_model_charges_usd=None,usage_limitation='Failed grader calls without returned usage are unavailable, not zero cost. All successful and failed evaluation records retained; estimates exclude those unknown calls and Codex/orchestration charges.')
 admin.query('update reliable_study_meta set costs=costs||'+admin.literal(json.dumps(costs))+"::jsonb where id='assessment-v1'",read_only=False)
 return dict(export=str(out/'chat-release.json'),prompt=rows[0]['version'],costs=costs)
def record_release():
 t=targets();path=ROOT/'docs/reliable-study-validation/production-validation-v1.json'
 raw=path.read_bytes();report=json.loads(raw);sha=hashlib.sha256(raw).hexdigest()
 if report['targets']!=t or report['release_blocking_checks_passed'] is not True:raise RuntimeError('Release targets or blocking checks differ')
 if report['deployment']['frontend']['status']!='SUCCEED' or report['deployment']['agent']['status']!='UPDATE_COMPLETE':raise RuntimeError('Deployment incomplete')
 if report['production']['exports']['passed'] is not True or report['production']['browser']['passed'] is not True:raise RuntimeError('Production verification incomplete')
 prior=admin.query("select sha256 from reliable_study_artifacts where id='production-validation-v1'")
 if prior and prior[0]['sha256']!=sha:raise RuntimeError('Existing release record differs; preserve it and version the amendment')
 insert('artifacts',[dict(id='production-validation-v1',sha256=sha,byte_count=len(raw),manifest=[],storage_path=None,payload=dict(raw_utf8=raw.decode('utf-8'),parsed=report))])
 saved=admin.query("select payload->>'raw_utf8' raw_utf8,sha256 from reliable_study_artifacts where id='production-validation-v1'")[0]
 if saved['sha256']!=sha or hashlib.sha256(saved['raw_utf8'].encode('utf-8')).hexdigest()!=sha:raise RuntimeError('Stored release original bytes differ')
 public=dict(report,artifact_sha256=sha,artifact_bytes=len(raw),artifact_round_trip_verified=True)
 admin.query('update reliable_study_meta set provenance=provenance||'+admin.literal(json.dumps(dict(software_release=public)))+"::jsonb where id='assessment-v1'",read_only=False)
 return dict(targets=t,release=report['id'],sha256=sha,original_bytes_round_trip_verified=True,authenticated_chat=report['conditional_verification']['authenticated_chat'])
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--verify',action='store_true');p.add_argument('--prepare',action='store_true');p.add_argument('--export-release',action='store_true');p.add_argument('--record-release',action='store_true');a=p.parse_args();print(json.dumps(apply() if a.apply else prepare() if a.prepare else export_release() if a.export_release else record_release() if a.record_release else verify(),indent=2))
