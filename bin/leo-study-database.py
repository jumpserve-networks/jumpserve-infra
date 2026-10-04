"""Inspect or import the LEO study into the verified JumpServe Supabase project.

This is a purpose-specific importer, not an arbitrary SQL command runner.
"""
import argparse
import importlib.util
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT.parent / 'jumpserve-back-end/experiments/leo_failover'
spec = importlib.util.spec_from_file_location('prompt_admin', ROOT / 'bin/agent-prompts.py')
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)

SCHEMAS = {
    'campaigns': 'id text,title text,status text,protocol jsonb,protocol_sha256 text,artifact_commit text,paper_sha256 text,planned_samples integer,recorded_samples integer,limitations jsonb,provenance jsonb',
    'configurations': 'id text,campaign_id text,country text,constellation text,satellites integer,requested_terminals integer,deployed_terminals integer,placement text,beam_policy text,ku_gbps numeric,variant text,cells integer,lost_capacity_gbps numeric,published_capacity_gbps numeric',
    'samples': 'id text,campaign_id text,configuration_id text,second integer,capacity_gbps numeric,rf_demand_gbps numeric,cell_bound_gbps numeric,failover_percent numeric,served_cells integer,allocated_beams integer,validation_errors jsonb,graph_sha256 text,demands_sha256 text,terminal_sha256 text,runner_sha256 text,wall_seconds numeric',
    'summaries': 'campaign_id text,country text,published_gbps numeric,mean_gbps numeric,min_gbps numeric,max_gbps numeric,relative_difference_percent numeric,failover_percent numeric,snapshots integer,assessment text',
    'papers': 'campaign_id text,reference_number integer,citation text,kind text,source_url text,download_status text,reading_status text,pages integer,sha256 text,version_note text,reading_notes text,retrieval_audit jsonb',
    'claims': 'campaign_id text,claim_id text,figure text,description text,coverage text,limitation text',
}
CONFLICT = {'campaigns':'id','configurations':'id','samples':'id','summaries':'campaign_id,country','papers':'campaign_id,reference_number','claims':'campaign_id,claim_id'}

def apply(saturation=False):
    payload=json.loads((STUDY/('results/saturation/relational.json' if saturation else 'results/relational.json')).read_text())
    campaign=payload['campaign']; identifier=campaign['id']
    if identifier!=('leo-failover-imc2025-saturation-v1' if saturation else 'leo-failover-imc2025-v1') or campaign['status']!='complete' or len(payload['samples'])!=campaign['planned_samples']:
        raise RuntimeError('Refusing incomplete or unexpected campaign')
    if hashlib.sha256((STUDY/'run.py').read_bytes()).hexdigest()!=campaign['provenance']['runner_sha256']:
        raise RuntimeError('Runner changed since recorded analysis')
    exists=admin.query("select to_regclass('public.leo_study_campaigns') is not null as present")[0]['present']
    if not exists:
        admin.query((ROOT/'database/202610040001_leo_study.sql').read_text(),read_only=False)
    admin.query((ROOT/'database/202610040002_leo_prompt_publication.sql').read_text(),read_only=False)
    prior=admin.query(f"select protocol_sha256,artifact_commit from public.leo_study_campaigns where id={admin.literal(identifier)}")
    if prior and (prior[0]['protocol_sha256']!=campaign['protocol_sha256'] or prior[0]['artifact_commit']!=campaign['artifact_commit']):
        raise RuntimeError('Registered study has different provenance; refusing replacement')
    sql=['begin;']
    for name,schema in SCHEMAS.items():
        rows=[campaign] if name=='campaigns' else [dict(row,campaign_id=identifier) for row in payload[name]]
        columns=[field.split()[0] for field in schema.split(',')]
        update=','.join(f'{field}=excluded.{field}' for field in columns if field not in CONFLICT[name].split(','))
        sql.append(f"insert into public.leo_study_{name} ({','.join(columns)}) select {','.join(columns)} from jsonb_to_recordset({admin.literal(json.dumps(rows))}::jsonb) as r({schema}) on conflict ({CONFLICT[name]}) do update set {update};")
    seed=json.loads((ROOT/'database/seed-leo-agent-prompt.json').read_text())
    keys=('id','version','module_id','system_prompt','research_context','created_by')
    sql.append(f"insert into public.agent_prompt_versions ({','.join(keys)},updated_by) values ({','.join(admin.literal(seed[k]) for k in keys)},{admin.literal(seed['created_by'])}) on conflict(id) do nothing;")
    sql.append('commit;')
    admin.query('\n'.join(sql),read_only=False)
    prompt=admin.query("select v.id, v.version, case when s.active_version_id=v.id then 'active' when v.published_at is not null then 'published' else 'draft' end as status from public.agent_prompt_versions v join public.agent_prompt_settings s using(module_id) where v.id="+admin.literal(seed['id'])+"::uuid")[0]
    return {'project':admin.PROJECT_REF,'campaign':identifier,'samples':len(payload['samples']),'configurations':len(payload['configurations']),'references':len(payload['papers']),'prompt':prompt}

def inspect():
    return admin.query("""select c.relname as table_name, a.attname as column_name,
      format_type(a.atttypid,a.atttypmod) as type from pg_class c
      join pg_namespace n on n.oid=c.relnamespace join pg_attribute a on a.attrelid=c.oid
      where n.nspname='public' and c.relname in ('agent_prompt_versions','agent_prompt_settings','agent_sessions')
      and a.attnum>0 and not a.attisdropped order by c.relname,a.attnum""")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--verify',action='store_true')
    p.add_argument('--saturation',action='store_true')
    args=p.parse_args()
    if args.verify:
        print(json.dumps(admin.query("select id,status,planned_samples,recorded_samples,(select count(*) from leo_study_samples where campaign_id=c.id) as saved_samples,(select count(*) from leo_study_configurations where campaign_id=c.id) as configurations,(select count(*) from leo_study_papers where campaign_id=c.id and kind='research' and reading_status='reviewed') as supporting_sources_reviewed,(select count(*) from leo_study_papers where campaign_id=c.id and kind='research' and download_status='unavailable') as supporting_sources_unavailable from leo_study_campaigns c order by id"),indent=2))
    elif not args.apply:
        print(json.dumps(inspect(),indent=2))
        print(json.dumps(admin.query("select conrelid::regclass::text as table_name,conname,pg_get_constraintdef(oid) as definition from pg_constraint where conrelid in ('public.agent_prompt_versions'::regclass,'public.agent_prompt_settings'::regclass,'public.agent_sessions'::regclass) and contype='c'"),indent=2))
    else:
        print(json.dumps(apply(args.saturation),indent=2))

if __name__=='__main__': main()
