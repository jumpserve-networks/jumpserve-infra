"""Guarded, version-preserving IPv6 assessment import and database verification."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STUDY=ROOT.parent/'jumpserve-back-end/experiments/ipv6_dns'
spec=importlib.util.spec_from_file_location('admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
SCHEMAS={
'protocols':'id text,version integer,stage text,document jsonb,sha256 text,locked_at timestamptz',
'campaigns':'id text,protocol_id text,title text,stage text,status text,planned_runs integer,recorded_runs integer,experiment_type text,limitations jsonb,provenance jsonb,usage jsonb',
'configurations':'id text,case_id text,cohort text,mtu text,upstream text,family text,edns_bytes integer,details jsonb,requested_resources jsonb,actual_resources jsonb',
'runs':'id text,protocol_id text,stage text,epoch text,status text,reason text,original_execution_date date,started_at timestamptz,ended_at timestamptz,analysis_version text,analysis_sha256 text,raw_sha256 jsonb,source_urls jsonb,requested_resources jsonb,actual_resources jsonb',
'measurements':'run_id text,configuration_id text,metric text,numerator numeric,denominator numeric,value numeric,status text,reason text,units text',
'summaries':'id text,configuration_id text,epoch text,statistics jsonb,interval_kind text',
'sources':'reference_number integer,citation text,doi text,kind text,role text,source_url text,retrieved_url text,access_status text,review_status text,retrieved_version text,sha256 text,byte_count bigint,pages integer,findings text,limitations text,retrieval_attempts jsonb,reviewer jsonb',
'claims':'id text,location text,description text,assessment text,evidence text,limitation text,proposed_check text,required_inputs text,feasibility text',
'published':'id text,source_number integer,location text,configuration_id text,epoch text,metric text,value numeric,units text,extraction text,paper_sha256 text',
'comparisons':'id text,published_id text,configuration_id text,epoch text,metric text,reproduced numeric,published numeric,difference_pp numeric,assessment text,valid_days integer,planned_days integer',
'controls':'id text,protocol_id text,stage text,status text,reason text,raw_sha256 text,payload jsonb',
'meta':'id text,analysis_version text,assessment_sha256 text,review_definition text,label_definitions jsonb,validation jsonb,counts jsonb,provenance jsonb,costs jsonb',
'artifacts':'id text,sha256 text,byte_count bigint,manifest jsonb,storage_path text,payload jsonb'}
KEYS={k:'id' for k in SCHEMAS};KEYS.update(measurements='run_id,configuration_id,metric',sources='reference_number')
def targets():
 account=json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve']))['Account']
 if account!='395567831870' or admin.PROJECT_REF!='regphejnlvfpyokpniny' or json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Target mismatch')
 return dict(aws_account=account,supabase_project=admin.PROJECT_REF)
def insert(name,rows):
 columns=[f.split()[0] for f in SCHEMAS[name].split(',')];keys=KEYS[name].split(',');updates=','.join(f'{c}=excluded.{c}' for c in columns if c not in keys)
 for start in range(0,len(rows),1000):
  admin.query(f"insert into public.ipv6_study_{name}({','.join(columns)}) select {','.join(columns)} from jsonb_to_recordset({admin.literal(json.dumps(rows[start:start+1000],allow_nan=False))}::jsonb) r({SCHEMAS[name]}) on conflict({KEYS[name]}) do update set {updates}",read_only=False)
def verify():
 t=targets();counts=admin.query("select jsonb_object_agg(name,n) counts from ("+' union all '.join(f"select '{n}' name,count(*) n from ipv6_study_{n}" for n in SCHEMAS)+") x")[0]['counts']
 security=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_select,has_table_privilege('authenticated',c.oid,'SELECT') browser_select,has_table_privilege('anon',c.oid,'INSERT,UPDATE,DELETE') anon_write,has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname like 'ipv6_study_%' and c.relkind='r'")
 if len(security)!=13:raise RuntimeError('Security coverage mismatch')
 for r in security:
  readable=r['relname']!='ipv6_study_artifacts'
  if not r['relrowsecurity'] or r['anon_select']!=readable or r['browser_select']!=readable or r['anon_write'] or r['browser_write']:raise RuntimeError('Invalid browser grants/RLS')
 bucket=admin.query("select public from storage.buckets where id='ipv6-study-raw'")
 if bucket!=[{'public':False}]:raise RuntimeError('Raw bucket is not private')
 d=json.loads((STUDY/'evidence/assessment-v1.json').read_text())
 for n in ('protocols','campaigns','configurations','runs','measurements','summaries','sources','claims','published','comparisons','controls'):
  if counts[n]!=len(d[n]):raise RuntimeError('Stored count mismatch: '+n)
 invariants=admin.query("select count(*) filter(where status='recorded' and (value is null or denominator<=0)) invalid_recorded,count(*) filter(where status<>'recorded' and value is not null) invalid_missing from ipv6_study_measurements")[0]
 if any(invariants.values()):raise RuntimeError('Missing-value invariants failed')
 return dict(targets=t,counts=counts,security=security,bucket=bucket,invariants=invariants,passed=True)
def apply():
 t=targets();p=STUDY/'evidence/assessment-v1.json';d=json.loads(p.read_text());sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if (len(d['measurements']),len(d['published']),len(d['sources']))!=(136512,1152,74):raise RuntimeError('Evidence coverage mismatch')
 for m in d['manifest']:
  if hashlib.sha256((STUDY/m['path']).read_bytes()).hexdigest()!=m['sha256']:raise RuntimeError('Source bytes changed: '+m['path'])
 if not admin.query("select to_regclass('public.ipv6_study_meta') is not null present")[0]['present']:admin.query((ROOT/'database/202610050101_ipv6_dns_study.sql').read_text(),read_only=False)
 prior=admin.query("select assessment_sha256 from ipv6_study_meta where id='assessment-v1'")
 if prior and prior[0]['assessment_sha256']!=sha:raise RuntimeError('Existing assessment differs; version amendment')
 for n in ('protocols','campaigns','configurations','runs','measurements','summaries','sources','claims','published','comparisons','controls'):
  insert(n,d[n]);print(n,len(d[n]),flush=True)
 meta={k:d[k] for k in ('analysis_version','review_definition','label_definitions','validation','provenance','costs')};meta.update(id='assessment-v1',assessment_sha256=sha,counts={n:len(d[n]) for n in SCHEMAS if n in d})
 insert('meta',[meta]);insert('artifacts',[dict(id='assessment-v1',sha256=sha,byte_count=p.stat().st_size,manifest=d['manifest'],storage_path=None,payload={'original_assessment_sha256':sha})]);return dict(targets=t,assessment_sha256=sha,verification=verify())
def amend():
 t=targets();p=STUDY/'evidence/assessment-v2.json';d=json.loads(p.read_text());sha=hashlib.sha256(p.read_bytes()).hexdigest()
 prior=admin.query("select assessment_sha256 from ipv6_study_meta where id='assessment-v2'")
 if prior and prior[0]['assessment_sha256']!=sha:raise RuntimeError('Preserve amendment version')
 for m in d['manifest']:
  if hashlib.sha256((STUDY/m['path']).read_bytes()).hexdigest()!=m['sha256']:raise RuntimeError('Amended input bytes differ')
 insert('sources',d['sources']);meta={k:d[k] for k in ('analysis_version','review_definition','label_definitions','validation','provenance','costs')};meta.update(id='assessment-v2',assessment_sha256=sha,counts={n:len(d[n]) for n in SCHEMAS if n in d})
 previous=admin.query("select provenance from ipv6_study_meta where id='assessment-v1'")[0]['provenance'];meta['provenance'].update({k:v for k,v in previous.items() if k.endswith('_raw_storage')})
 insert('meta',[meta]);insert('artifacts',[dict(id='assessment-v2',sha256=sha,byte_count=p.stat().st_size,manifest=d['manifest'],storage_path=None,payload={'supersedes':'assessment-v1','source_identity_correction_only':True})]);return dict(targets=t,amendment_sha256=sha,verification=verify())
def prepare(version=2):
 t=targets();admin.query((ROOT/'database/202610050103_ipv6_evaluation_v2.sql').read_text(),read_only=False)
 seed=json.loads((ROOT/f'database/seed-ipv6-agent-prompt-v{version}.json').read_text());keys=('id','version','module_id','system_prompt','research_context','created_by');values=','.join(admin.literal(seed[k]) for k in keys)
 admin.query(f"insert into agent_prompt_versions ({','.join(keys)},updated_by) values({values},{admin.literal(seed['created_by'])}) on conflict(id) do nothing",read_only=False)
 return dict(targets=t,prompt_id=seed['id'],status='inactive draft until evaluation passes')
def harden():
 t=targets();admin.query((ROOT/'database/202610050104_ipv6_publication_review_guard.sql').read_text(),read_only=False)
 return dict(targets=t,publication_review_names='All14 case names required as array; missing JSON cannot bypass guard')
def record():
 t=targets();reports=[]
 for p in sorted((ROOT/'docs/ipv6-study-validation').glob('*.json')):
  raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest();prior=admin.query('select sha256 from ipv6_study_artifacts where id='+admin.literal(p.stem))
  if prior and prior[0]['sha256']!=sha:raise RuntimeError('Preserve release history; version '+p.name)
  insert('artifacts',[dict(id=p.stem,sha256=sha,byte_count=len(raw),manifest=[],storage_path=None,payload={'raw_utf8':raw.decode(),'parsed':json.loads(raw)})])
  stored=admin.query('select payload->>\'raw_utf8\' raw from ipv6_study_artifacts where id='+admin.literal(p.stem))[0]['raw']
  if hashlib.sha256(stored.encode()).hexdigest()!=sha:raise RuntimeError('Evidence round trip differs')
  reports.append(dict(id=p.stem,sha256=sha,bytes=len(raw)))
 admin.query('update ipv6_study_meta set provenance=provenance||'+admin.literal(json.dumps({'validation_reports':reports}))+"::jsonb where id='assessment-v2'",read_only=False)
 return dict(targets=t,reports=reports,round_trip_verified=True)
def context():
 t=targets();p=STUDY/'evidence/paper-context-v1.json';raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest();doc=json.loads(raw)
 prior=admin.query("select sha256 from ipv6_study_artifacts where id='paper-context-v1'")
 if prior and prior[0]['sha256']!=sha:raise RuntimeError('Preserve original paper context')
 insert('artifacts',[dict(id='paper-context-v1',sha256=sha,byte_count=len(raw),manifest=[],storage_path=None,payload={'raw_utf8':raw.decode(),'parsed':doc})])
 stored=admin.query("select payload->>'raw_utf8' raw from ipv6_study_artifacts where id='paper-context-v1'")[0]['raw']
 if hashlib.sha256(stored.encode()).hexdigest()!=sha:raise RuntimeError('Context retrieval differs')
 admin.query('update ipv6_study_meta set provenance=provenance||'+admin.literal(json.dumps({'published_context':dict(sha256=sha,url='/module/ipv6-dns-study/paper-context.json',document=doc)}))+"::jsonb where id='assessment-v2'",read_only=False)
 return dict(targets=t,context_sha256=sha,published_context_records=len(doc['published_values']),figure_mappings=len(doc['figure_coverage']),round_trip_verified=True)
def release():
 t=targets();p=ROOT/'docs/ipv6-study-validation/production-validation-v1.json';raw=p.read_bytes();doc=json.loads(raw);sha=hashlib.sha256(raw).hexdigest()
 if doc['targets']!=t or not doc['release_blocking_checks_passed'] or doc['software_status']!='deployed and production verified':raise RuntimeError('Release report is not publishable')
 if doc['frontend']['status']!='SUCCEED' or not doc['agent']['passed'] or doc['browser']['status']!='passed':raise RuntimeError('Production checks incomplete')
 active=admin.query("select v.version from agent_prompt_versions v join agent_prompt_settings s on s.active_version_id=v.id where s.module_id='ipv6-dns-study'")
 if active!=[{'version':'ipv6-evidence-v3'}]:raise RuntimeError('Published prompt mismatch')
 record()
 usage=json.loads((ROOT/'docs/ipv6-study-validation/usage-v1.json').read_text())
 public=dict(doc,report_sha256=sha,usage=usage)
 storage=admin.query("select provenance->'release-v1_raw_storage' report from ipv6_study_meta where id='assessment-v2'")[0]['report']
 if storage:public['release_evidence_storage']=storage
 admin.query('update ipv6_study_meta set provenance=provenance||'+admin.literal(json.dumps({'software_release':public}))+"::jsonb,costs=costs||"+admin.literal(json.dumps({'release_usage':usage}))+"::jsonb where id='assessment-v2'",read_only=False)
 stored=admin.query("select provenance->'software_release' report from ipv6_study_meta where id='assessment-v2'")[0]['report']
 if stored!=public:raise RuntimeError('Published release record differs')
 return dict(targets=t,release_report_sha256=sha,round_trip_verified=True,status=doc['software_status'])
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--record',action='store_true');p.add_argument('--release',action='store_true');p.add_argument('--context',action='store_true');p.add_argument('--harden-publication',action='store_true');p.add_argument('--prepare',action='store_true');p.add_argument('--prepare-v3',action='store_true');p.add_argument('--save-validation',action='store_true');p.add_argument('--amend',action='store_true');a=p.parse_args();result=apply() if a.apply else amend() if a.amend else prepare(3) if a.prepare_v3 else prepare() if a.prepare else harden() if a.harden_publication else context() if a.context else release() if a.release else record() if a.record else verify()
 if a.save_validation:
  path=ROOT/'docs/ipv6-study-validation/database-validation-v1.json'
  if path.exists():raise RuntimeError('Preserve prior database validation')
  path.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
