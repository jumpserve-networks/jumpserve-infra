"""Purpose-specific, resumable HTTP/2 evidence import into verified JumpServe."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT.parent/'jumpserve-back-end/experiments/http2_compliance'
spec=importlib.util.spec_from_file_location('prompt_admin',ROOT/'bin/agent-prompts.py')
admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
SCHEMAS={
 'protocols':'id text,version integer,stage text,document jsonb,sha256 text,code_sha256 text,locked_at timestamptz',
 'campaigns':'id text,title text,status text,protocol jsonb,protocol_sha256 text,artifact_commit text,analysis_sha256 text,planned_runs integer,recorded_runs integer,planned_measurements integer,limitations jsonb,provenance jsonb,costs jsonb',
 'configurations':'campaign_id text,id text,proxy text,version text,mode text,tls boolean,details jsonb,requested_resources jsonb,actual_resources jsonb',
 'runs':'campaign_id text,id text,configuration_id text,protocol_id text,stage text,status text,reason text,source_path text,raw_sha256 text,analysis_sha256 text,analysis_version text,started_at timestamptz,ended_at timestamptz,original_execution_at timestamptz,wall_seconds numeric,units text',
 'measurements':'campaign_id text,run_id text,test_id integer,side text,description text,rfc_section text,expected text,expected_scope text,author_outcome text,outcome text,status text,reason text,error_code bigint,observed_scope text,scope_compatible boolean,author_rule_conformant boolean,preserved_rule_conformant boolean',
 'summaries':'campaign_id text,run_id text,configuration_id text,planned integer,recorded integer,missing integer,unknown integer,recoded integer,author_counts jsonb,preserved_counts jsonb,published_counts jsonb,published_source text,assessment text,differences jsonb,scope_observed integer,scope_mismatches integer,scope_compatible integer,comparisons jsonb',
 'sources':'campaign_id text,reference_number integer,citation text,doi text,kind text,source_url text,retrieved_url text,download_status text,review_status text,retrieved_version text,sha256 text,pages integer,findings text,limitations text,retrieval_audit jsonb',
 'claims':'campaign_id text,claim_id text,location text,description text,assessment text,evidence text,limitation text',
 'followups':'id text,campaign_id text,stage text,provenance jsonb,processes jsonb,planned integer,recorded integer,summary jsonb,costs jsonb',
 'frame_measurements':'followup_id text,id text,replication integer,case_name text,window_seconds numeric,expected text,expected_error_code integer,outcome text,error_code bigint,status text,reason text,agrees boolean,started_at timestamptz,ended_at timestamptz,elapsed_seconds numeric,raw_sha256 text,trace jsonb',
 'artifacts':'campaign_id text,id text,sha256 text,source_path text,byte_count bigint,payload jsonb',
}
CONFLICT={k:'campaign_id,id' for k in SCHEMAS}
CONFLICT.update(protocols='id',campaigns='id',measurements='campaign_id,run_id,test_id',summaries='campaign_id,run_id',sources='campaign_id,reference_number',claims='campaign_id,claim_id',followups='id',frame_measurements='followup_id,id')
def insert(name,rows):
    schema=SCHEMAS[name];columns=[f.split()[0] for f in schema.split(',')]
    changes=','.join(f'{c}=excluded.{c}' for c in columns if c not in CONFLICT[name].split(','))
    batch=1 if name=='artifacts' else 300
    for start in range(0,len(rows),batch):
        admin.query(f"insert into public.http2_study_{name} ({','.join(columns)}) select {','.join(columns)} from jsonb_to_recordset({admin.literal(json.dumps(rows[start:start+batch]))}::jsonb) as r({schema}) on conflict ({CONFLICT[name]}) do update set {changes}",read_only=False)
def verify():
    return admin.query("""select c.id,c.status,c.planned_runs,c.recorded_runs,c.planned_measurements,
      (select count(*) from http2_study_runs r where r.campaign_id=c.id) saved_runs,
      (select count(*) from http2_study_measurements m where m.campaign_id=c.id) saved_measurements,
      (select count(*) from http2_study_artifacts a where a.campaign_id=c.id) private_artifacts,
      (select count(*) from http2_study_sources s where s.campaign_id=c.id) sources,
      (select count(*) from http2_study_claims s where s.campaign_id=c.id) claims
      from http2_study_campaigns c"""
    )
def prepare():
    admin.query((ROOT/'database/202610040006_agent_answer_provenance.sql').read_text(),read_only=False)
    admin.query((ROOT/'database/202610040007_http2_manual_prompt_review.sql').read_text(),read_only=False)
    admin.query((ROOT/'database/202610040008_agent_model_usage.sql').read_text(),read_only=False)
    admin.query((ROOT/'database/202610040009_agent_evidence_rendering.sql').read_text(),read_only=False)
    for filename in ('seed-http2-agent-prompt.json','seed-http2-agent-prompt-v2.json','seed-http2-agent-prompt-v3.json','seed-http2-agent-prompt-v4.json','seed-http2-agent-prompt-v5.json','seed-http2-agent-prompt-v6.json','seed-http2-agent-prompt-v7.json','seed-http2-agent-prompt-v8.json','seed-http2-agent-prompt-v9.json'):
        seed=json.loads((ROOT/'database'/filename).read_text());keys=('id','version','module_id','system_prompt','research_context','created_by')
        admin.query(f"insert into agent_prompt_versions ({','.join(keys)},updated_by) values ({','.join(admin.literal(seed[k]) for k in keys)},{admin.literal(seed['created_by'])}) on conflict(id) do nothing",read_only=False)
    # v3 passed the automatic rubric, but manual inspection found false negative
    # claims about paper coverage. Retain its immutable publication, disable it.
    admin.query("update agent_prompt_settings set active_version_id=null where module_id='http2-compliance-study' and active_version_id='656c8453-939d-4597-a31a-6b2e4e6ccebc'",read_only=False)
    return {'project':admin.PROJECT_REF,'prepared':'provenance, review, usage and renderer migrations; immutable draft prompts through v9; v3 disabled after manual review'}
def save_evaluations():
    rows=[];reports=[]
    for path in sorted((ROOT/'.test-artifacts').glob('http2-agent-evaluation-*.json')):
        data=json.loads(path.read_text())
        if data.get('module_id')!='http2-compliance-study':raise RuntimeError('Wrong evaluation module')
        reports.append(data)
        rows.append(dict(campaign_id='http2-compliance-artifact-v2',id='evaluation-'+data['id'],sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_path='private-evaluation/'+path.name,byte_count=len(path.read_bytes()),payload=data))
    insert('artifacts',rows)
    calls=[u for d in reports for c in d['cases'] for key in ('answer_usage','judge_usage') if (u:=c.get(key))]
    models={}
    for report in reports:
        entry=models.setdefault(report['model_id'],dict(evaluation_records=0,input_tokens=0,output_tokens=0,estimated_usd=0,pricing=report['pricing']))
        entry['evaluation_records']+=1
        for case in report['cases']:
            for key in ('answer_usage','judge_usage'):
                usage=case.get(key)
                if usage:
                    entry['input_tokens']+=usage['tokens'].get('inputTokens',0)
                    entry['output_tokens']+=usage['tokens'].get('outputTokens',0)
                    entry['estimated_usd']+=usage['estimated_usd']
    cost={'local_experiment_incremental_usd':0,'aws_experiment_instances':0,'evaluation_records':len(reports),'model_calls_without_recorded_usage':sum(c.get('status')=='failed' and not c.get('answer_usage') for r in reports for c in r['cases']),'model_tokens':{'input':sum(u['tokens'].get('inputTokens',0) for u in calls),'output':sum(u['tokens'].get('outputTokens',0) for u in calls)},'estimated_model_cost_usd':sum(u['estimated_usd'] for u in calls),'models':models,'limitation':'Estimate from returned tokens and per-model standard list prices; no billing reconciliation. Codex orchestration, existing hosting and build costs are not available. Model usage missing from a failed call is unavailable, not a verified zero charge; the estimate excludes those unrecorded calls.'}
    admin.query("update http2_study_campaigns set costs="+admin.literal(json.dumps(cost))+"::jsonb where id='http2-compliance-artifact-v2'",read_only=False)
    return {'project':admin.PROJECT_REF,'costs':cost}
def export_chat_release():
    rows=admin.query("select v.id,v.version,v.module_id,v.system_prompt,v.research_context,v.content_sha256,v.published_at,p.evaluation_report from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id join agent_prompt_publications p on p.prompt_version_id=v.id where s.module_id='http2-compliance-study' order by p.published_at desc limit 1")
    if len(rows)!=1:raise RuntimeError('No active published HTTP2 prompt')
    row=rows[0];report=row['evaluation_report']
    if report.get('human_review',{}).get('passed') is not True or len(report['cases'])!=8 or not all(c.get('passed') is True for c in report['cases']):raise RuntimeError('Answer reviews did not pass')
    if report['prompt_content_sha256']!=row['content_sha256']:raise RuntimeError('Publication hash differs')
    public={k:v for k,v in row.items() if k!='evaluation_report'}
    public['evaluation']={k:v for k,v in report.items() if k not in ('evidence','literature')}
    public['scope']='Eight fixed regression scenarios; typed AI evidence selection and versioned backend rendering. Not a reliability sample or complete scientific validation.'
    directory=ROOT.parent/'jumpserve-front-end/public/module/http2-compliance-study';directory.mkdir(parents=True,exist_ok=True)
    path=directory/'chat-release.json';path.write_text(json.dumps(public,indent=2)+'\n')
    return {'project':admin.PROJECT_REF,'export':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'prompt_version':row['version']}
def apply():
    data=json.loads((STUDY/'results/assessment-v3.json').read_text());c=data['campaign'];cid=c['id']
    if cid!='http2-compliance-artifact-v2' or len(data['measurements'])!=7176 or len(data['runs'])!=60:raise RuntimeError('Unexpected or truncated evidence')
    lock=json.loads((STUDY/'protocol-lock-v2.json').read_text())
    if hashlib.sha256((STUDY/'analyze_v2.py').read_bytes()).hexdigest()!=lock['analysis_sha256']:raise RuntimeError('Frozen analysis changed')
    exists=admin.query("select to_regclass('public.http2_study_campaigns') is not null present")[0]['present']
    if not exists:admin.query((ROOT/'database/202610040003_http2_study.sql').read_text(),read_only=False)
    admin.query((ROOT/'database/202610040004_http2_prompt_publication.sql').read_text(),read_only=False)
    signed=admin.query("select data_type from information_schema.columns where table_schema='public' and table_name='http2_study_measurements' and column_name='error_code'")[0]['data_type']=='integer'
    if signed:admin.query((ROOT/'database/202610040005_http2_unsigned_error_codes.sql').read_text(),read_only=False)
    prior=admin.query("select protocol_sha256,analysis_sha256 from http2_study_campaigns where id="+admin.literal(cid))
    if prior and (prior[0]['protocol_sha256']!=c['protocol_sha256'] or prior[0]['analysis_sha256']!=c['analysis_sha256']):raise RuntimeError('Existing campaign provenance differs')
    for name in ('protocols','campaigns','configurations','runs','measurements','summaries','sources','claims','followups','frame_measurements','artifacts'):
        if name=='campaigns':rows=[c]
        elif name=='frame_measurements':rows=[dict(row,followup_id=f['id'],case_name=row['case'],trace={k:row.get(k) for k in ('sent_hex','received_hex','sent_bytes','received_bytes','frames','trailing_hex','ended')}) for f in data['followups'] for row in f['measurements']]
        else:rows=[dict(row,campaign_id=cid) for row in data[name]]
        insert(name,rows);print(name+': '+str(len(rows)),flush=True)
    prepare()
    return dict(project=admin.PROJECT_REF,evidence_sha256=hashlib.sha256((STUDY/'results/assessment-v3.json').read_bytes()).hexdigest(),counts=verify(),prompt_status='draft until live evaluations pass')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--verify',action='store_true');p.add_argument('--prepare',action='store_true');p.add_argument('--save-evaluations',action='store_true');p.add_argument('--export-chat-release',action='store_true');a=p.parse_args()
    print(json.dumps(apply() if a.apply else prepare() if a.prepare else save_evaluations() if a.save_evaluations else export_chat_release() if a.export_chat_release else verify() if a.verify else {'project':admin.PROJECT_REF,'schema_present':admin.query("select to_regclass('public.http2_study_campaigns') is not null present")},indent=2))
if __name__=='__main__':main()
