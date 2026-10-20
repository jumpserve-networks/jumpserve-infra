"""Idea workflow RPCs against a fresh local isolated PostgreSQL DB.

Retains the database and timestamped reports, including failed runs. No production
transport, Google session, AWS or model call is used. Raw Storage is a local-byte
transport fixture; database/worker algorithms are the actual implementations.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import api, ideas, scheduler, store, workflow
PSQL='/opt/homebrew/opt/postgresql@17/bin/psql'
ORIGIN='postgresql://michael@127.0.0.1:54477/'
STAMP=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
DATABASE='jumpserve_research_ideas_test_'+STAMP.lower()
DIRECTORY=ROOT/'.test-artifacts/research-ideas/database'/STAMP
DIRECTORY.mkdir(parents=True,exist_ok=False)
ACTOR=str(uuid.uuid4()); OTHER=str(uuid.uuid4()); files={}; file_lock=threading.Lock()
report=dict(protocol='research-ideas-protocol-v1',amendment='research-ideas-amendment-v2',
 database=DATABASE,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),checks=[],
 reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent'),
 design='Synthetic software development regressions, not scientific or held-out validation.',
 conditional_gaps=['Remote Supabase Storage','Real Google-authenticated owner request','Production migrations and live prompt publication', 'Actual provider-to-Supabase storage roundtrip'],
 measured_charges_usd=None,model_usage=None)

def sql_text(value):return "'"+str(value).replace("'","''")+"'"
def sql_json(value):return sql_text(json.dumps(value,allow_nan=False))+'::jsonb'
def query(sql,database=DATABASE,role=None):
    if not database.startswith('jumpserve_research_ideas_test_') and database!='postgres':raise ValueError('Local isolated DB required')
    if role:sql='begin; set local role '+role+'; '+sql+'; commit;'
    result=subprocess.run([PSQL,ORIGIN+database,'-X','-v','ON_ERROR_STOP=1','-q','-t','-A'],input=sql,text=True,capture_output=True,timeout=20)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def rpc(name,payload):
    signatures={
      'research_autonomy_control':dict(p_operation='text',p_actor='uuid',p_study='uuid',p_payload='jsonb'),
      'research_autonomy_resume_context':dict(p_study='uuid',p_actor='uuid',p_task='uuid',p_version='text'),
      'research_autonomy_context_candidates':{},
      'research_initialize_claim_design':dict(p_study='uuid',p_actor='uuid',p_document='jsonb',p_raw='text',p_sha256='text',p_source='jsonb',p_claim='jsonb'),
      'research_reuse_claim_packet':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_packet='uuid',p_run='uuid'),
      'research_create_study':dict(p_actor='uuid',p_id='uuid',p_document='jsonb'),
      'research_append':dict(p_study='uuid',p_actor='uuid',p_kind='text',p_record='jsonb'),
      'research_append_bundle':dict(p_study='uuid',p_actor='uuid',p_records='jsonb'),
      'research_queue_enqueue':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_request='jsonb',p_sha256='text'),
      'research_queue_claim':dict(p_worker='uuid'),
      'research_queue_finish':dict(p_job='uuid',p_token='uuid',p_records='jsonb',p_run='uuid',p_error='text',p_usage='jsonb'),
      'research_queue_action':dict(p_study='uuid',p_actor='uuid',p_job='uuid',p_id='uuid',p_action='text',p_reason='text',p_assessments='jsonb',p_run='uuid'),
      'research_queue_snapshot':dict(p_study='uuid',p_actor='uuid'),
      'research_prepare_plan':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_request='uuid',p_plan='jsonb',p_records='jsonb'),
      'research_save_idea_packet':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_previous='uuid',p_document='jsonb',p_raw='text',p_sha256='text',p_reason='text'),
      'research_begin_idea_run':dict(p_study='uuid',p_actor='uuid',p_user='text',p_id='uuid',p_packet='uuid',p_task='text',p_session='uuid',p_prompt='uuid',p_model='text',p_request='jsonb',p_provenance='jsonb'),
      'research_finish_idea_run':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_status='text',p_reason='text',p_raw='text',p_output='jsonb',p_usage='jsonb',p_provenance='jsonb',p_messages='jsonb'),
      'research_accept_idea_plan':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_packet='uuid',p_comprehension='uuid',p_critic='uuid',p_reason='text'),
      'research_prepare_idea_campaign':dict(p_study='uuid',p_actor='uuid',p_id='uuid',p_packet='uuid',p_request='jsonb',p_records='jsonb',p_campaign='uuid',p_protocol='uuid'),
      'research_network_begin':dict(p_job='uuid',p_token='uuid',p_spec='jsonb',p_sha='text'),
      'research_network_pending':{},
      'research_network_launch':dict(p_job='uuid',p_runner='text',p_claim='boolean'),
      'research_network_update':dict(p_job='uuid',p_phase='text',p_data='jsonb',p_ingest_hash='text'),
      'research_network_cancel':dict(p_study='uuid',p_actor='uuid',p_job='uuid',p_id='uuid',p_reason='text'),
      'research_network_token':dict(p_job='uuid',p_hash='text'),
      'publish_agent_prompt':dict(p_version_id='uuid',p_expected_active_version_id='uuid',p_expected_content_sha256='text',p_report='jsonb',p_actor='text',p_module_id='text')}
    if name not in signatures or set(payload)!=set(signatures[name]):raise ValueError('Unsupported fixture RPC')
    arguments=[]
    for key,kind in signatures[name].items():
        value=payload[key]
        argument='null::'+kind if value is None else sql_json(value) if kind=='jsonb' else sql_text(value)+'::'+kind
        arguments.append(key+' => '+argument)
    result=query('select public.'+name+'('+','.join(arguments)+')',role='service_role')
    return result if name=='publish_agent_prompt' else json.loads(result) if result else None

def transport(path,method='GET',body=None,public=False,raw=False):
    parsed=urllib.parse.urlsplit(path)
    if parsed.path.startswith('/storage/v1/object/'):
        if not raw and method!='POST':raise store.StoreError('Raw fixture access required')
        with file_lock:
            if method=='POST':
                if path in files:raise store.StoreError('Research persistence request failed (HTTP 409)')
                files[path]=body
                target=DIRECTORY/('raw-'+hashlib.sha256(path.encode()).hexdigest())
                target.write_bytes(body);return None
            if path not in files:raise store.StoreError('Research persistence request failed (HTTP 404)')
            return files[path]
    if parsed.path=='/rest/v1/rpc/get_active_agent_prompt' and method=='GET':
        module=dict(urllib.parse.parse_qsl(parsed.query))['p_module_id']
        return json.loads(query("select coalesce(json_agg(t),'[]') from public.get_active_agent_prompt("+sql_text(module)+")t",role='service_role'))
    if parsed.path.startswith('/rest/v1/rpc/'):
        return rpc(parsed.path.removeprefix('/rest/v1/rpc/'),body)
    if method!='GET' or body is not None:raise ValueError('Unexpected transport mutation')
    table=parsed.path.removeprefix('/rest/v1/')
    allowed=['research_'+k for k in (*workflow.FIELDS,'studies','study_owners','queue_jobs','queue_events','prepared_plans','idea_packets','idea_runs','idea_readiness','idea_campaign_links','claim_designs','autonomy_workflows','autonomy_tasks','autonomy_turns')]
    if table not in allowed:raise ValueError('Unsupported relation')
    params=dict(urllib.parse.parse_qsl(parsed.query));columns=params.pop('select').split(',')
    if any(not c.replace('_','').isalnum() and c not in ('value::text','evidence_progress:context->evidence_progress') for c in columns):raise ValueError('Unsafe projection')
    columns=["context->'evidence_progress' as evidence_progress" if c=='evidence_progress:context->evidence_progress' else c for c in columns]
    limit=int(params.pop('limit','1000'));offset=int(params.pop('offset','0'))
    order=params.pop('order',None);ordering=[]
    if order:
        for entry in order.split(','):
            column,direction=entry.split('.')
            if column not in ('created_at','id','version','number','study_id') or direction not in ('asc','desc'):raise ValueError('Unsafe order')
            ordering.append(column+' '+direction)
    predicates=[]
    for column,value in params.items():
        if column=='and':
            if not value.startswith('(id.gt.') or not value.endswith(')'):raise ValueError('Unsafe keyset cursor')
            predicates.append('id>'+sql_text(str(uuid.UUID(value[7:-1]))));continue
        if column not in ('id','study_id','owner_id','created_at','packet_id','task','run_id','campaign_id','protocol_id','task_id','number','claim_id'):raise ValueError('Unsafe filter')
        operator,argument=value.split('.',1)
        if operator=='eq':predicates.append(column+'='+sql_text(argument))
        elif operator=='in':
            if not argument.startswith('(') or not argument.endswith(')'):raise ValueError('Invalid fixed list filter')
            predicates.append(column+' in ('+','.join(sql_text(str(uuid.UUID(v))) for v in argument[1:-1].split(','))+')')
        elif operator=='lt' and column=='number':
            if not argument.isdigit():raise ValueError('Invalid turn cursor')
            predicates.append(column+'<'+str(int(argument)))
        elif operator=='lte' and column=='created_at':predicates.append(column+'<='+sql_text(argument))
        else:raise ValueError('Unsupported filter')
    where=' where '+' and '.join(predicates) if predicates else ''
    order_sql=' order by '+','.join(ordering) if ordering else ''
    return json.loads(query("select coalesce(json_agg(t),'[]'::json) from (select "+','.join(columns)+' from public.'+table+where+order_sql+f' limit {limit} offset {offset}) t',role='anon' if public else 'service_role'))

def check(name,action):
    tick=time.monotonic()
    try:
        evidence=action();report['checks'].append(dict(name=name,passed=True,wall_seconds=time.monotonic()-tick,evidence=evidence));print('PASS '+name,flush=True)
    except Exception as error:
        report['checks'].append(dict(name=name,passed=False,wall_seconds=time.monotonic()-tick,reason=str(error)));raise


def rejects(callback):
    try: callback()
    except (ValueError,RuntimeError,store.StoreError): return
    raise AssertionError('Expected rejection')
def uid(): return str(uuid.uuid4())
def bootstrap():
    query('create database '+DATABASE+" with template template0 encoding 'UTF8'",'postgres')
    query("""do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to anon,authenticated,service_role;
create schema storage; create table storage.buckets(id text primary key,name text,public boolean); create table storage.objects(id int primary key,bucket_id text); alter table storage.objects enable row level security;
grant usage on schema storage to anon,authenticated,service_role; grant all on storage.objects to service_role;
create table public.agent_sessions(id uuid primary key,user_id text not null,messages jsonb not null default '[]',created_at timestamptz default now(),updated_at timestamptz default now());
grant all on public.agent_sessions to service_role;""")
    report['migration_sha256']={}
    for name in ('202609200001_agent_prompts.sql','202609290001_real_world_agent.sql','202610040009_agent_evidence_rendering.sql','202610050104_ipv6_publication_review_guard.sql','202610070001_research_workflow.sql','202610070002_research_queue.sql','202610070003_research_preparation.sql','202610120001_research_ideas.sql','202610120002_research_idea_prompt.sql','202610120003_research_idea_prompt_seed.sql','202610120004_research_idea_prompt_seed_v2.sql','202610130001_research_idea_review_roles.sql','202610140001_idea_interview_prompt.sql','202610140002_idea_interview_prompt_v4.sql','202610140003_idea_interview_prompt_v5.sql','202610140004_idea_interview_prompt_v6.sql','202610140005_idea_interview_prompt_v7.sql','202610140006_idea_interview_prompt_v8.sql','202610140007_idea_review_sources_v9.sql','202610140008_idea_review_sources_v10.sql','202610140009_idea_review_sources_v11.sql'):
        raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    for name in ('202610130002_network_execution.sql','202610170001_claim_experiment_design.sql','202610170002_claim_design_prompt.sql','202610170003_claim_design_prompt_v2.sql','202610170004_claim_design_prompt_v3.sql','202610170005_claim_design_prompt_v4.sql','202610170006_claim_design_policy_guard.sql','202610170007_claim_design_prompt_v5.sql','202610170008_claim_design_v5_publication_guard.sql','202610170009_claim_design_prompt_v6.sql','202610170010_claim_design_v6_publication_guard.sql','202610170011_claim_design_replay_publication_guard.sql','202610170012_claim_design_quote_publication_guard.sql','202610170013_claim_design_exact_units_publication_guard.sql'):
        raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    name='202610180001_claim_packet_reuse.sql';raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    for name in ('202610180002_autonomous_assessments.sql','202610180003_autonomy_prompt_candidate.sql','202610180004_autonomy_publication_guard.sql','202610180005_autonomy_prompt_v2.sql','202610180006_autonomy_v2_publication_guard.sql','202610180007_autonomy_prompt_v3.sql','202610180008_autonomy_v3_publication_guard.sql','202610180009_autonomy_prompt_v4.sql','202610180010_autonomy_v4_publication_guard.sql','202610180011_autonomy_prompt_v5.sql','202610180012_autonomy_v5_publication_guard.sql','202610180013_autonomy_provider_recovery_guard.sql','202610180014_autonomy_prompt_v6.sql','202610180015_autonomy_phase_publication_guard.sql','202610180016_autonomy_context_integration_guard.sql','202610180017_autonomy_evidence_publication_guard.sql'):
        raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    for name in ('202610190001_bounded_followups.sql','202610190002_autonomy_prompt_v7.sql','202610190003_autonomy_v7_publication_guard.sql','202610190004_bounded_tcp_queue.sql','202610190005_autonomy_prompt_v8.sql','202610190006_autonomy_v8_publication_guard.sql','202610190007_autonomy_v8_review_criteria.sql','202610190008_autonomy_completion_publication_guard.sql','202610190009_application_trajectory_guard.sql','202610190010_rejected_turn_review.sql'):
        raw=(ROOT/'database'/name).read_bytes();report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();query(raw.decode())
    report['bootstrap_limit']='Legacy agent_sessions base table synthesized; listed prompt/research migrations executed as original files. Historical study-table migrations outside this feature are not replayed.'
    store.request=transport

if __name__=='__main__':
    try:
        bootstrap()
        from research_idea_fixtures import packet
        study=uid(); paper=uid(); prompt='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8'
        def security():
            tables=['research_idea_packets','research_idea_sessions','research_idea_runs','research_idea_readiness','research_idea_campaign_links']
            for role in ('anon','authenticated'):
                rows=json.loads(query("select json_agg(t) from (select relname,relrowsecurity,has_table_privilege(current_user,oid,'SELECT,INSERT,UPDATE,DELETE') access from pg_class where relname in ("+','.join(map(sql_text,tables))+") )t",role=role))
                assert len(rows)==5 and all(r['relrowsecurity'] and not r['access'] for r in rows)
                rejects(lambda:rpc('research_save_idea_packet',dict(p_study=study,p_actor=OTHER,p_id=uid(),p_previous=None,p_document={},p_raw='{}',p_sha256='0'*64,p_reason='Test')))
                assert query("select has_function_privilege(current_user,'public.research_accept_idea_plan(uuid,uuid,uuid,uuid,uuid,uuid,text)','EXECUTE')",role=role)=='f'
            return dict(private_tables=5,browser_reads=False,browser_writes=False,browser_rpc=False)
        check('private idea RLS and browser RPC denial',security)
        def intake():
            doc=dict(title='Software idea fixture',paper_url=None,domain='Software',scope='No scientific validation',origin_module=None,study_kind='idea')
            s=rpc('research_create_study',dict(p_actor=ACTOR,p_id=study,p_document=doc));assert s['study_kind']=='idea' and s['paper_url'] is None
            assert rpc('research_create_study',dict(p_actor=ACTOR,p_id=study,p_document=doc))==s
            rejects(lambda:rpc('research_create_study',dict(p_actor=OTHER,p_id=study,p_document=doc)))
            rejects(lambda:rpc('research_create_study',dict(p_actor=ACTOR,p_id=uid(),p_document=dict(doc,paper_url='https://example.org/fake'))))
            old=dict(doc,paper_url='https://example.org/old');old.pop('study_kind');p=rpc('research_create_study',dict(p_actor=ACTOR,p_id=paper,p_document=old))
            assert p==rpc('research_create_study',dict(p_actor=ACTOR,p_id=paper,p_document=old))
            return dict(idea_origin='null paper URL',legacy_paper_replay=True)
        check('explicit idea intake and old paper replay',intake)
        value=packet(); body=dict(action='save',request_id=uid(),supersedes_id=None,document=value,reason='Software fixture initial plan')
        selected=ideas.save(study,ACTOR,body)
        def versions():
            assert ideas.save(study,ACTOR,body)==selected
            rejects(lambda:ideas.save(study,OTHER,body))
            rejects(lambda:ideas.save(study,ACTOR,dict(body,request_id=uid(),supersedes_id=selected['id'])))
            rejects(lambda:ideas.save(study,ACTOR,dict(body,request_id=uid(),document=dict(value,question='Changed'),supersedes_id=None)))
            rejects(lambda:query("update research_idea_packets set reason='Mutate' where id="+sql_text(selected['id']),role='service_role'))
            rejects(lambda:rpc('research_save_idea_packet',dict(p_study=study,p_actor=ACTOR,p_id=uid(),p_previous=selected['id'],p_document=dict(value,question='New'),p_raw=workflow.canonical(dict(value,question='New')).decode(),p_sha256='0'*64,p_reason='Wrong hash')))
            return dict(raw_sha256=selected['sha256'],immutable=True,stale_rejected=True,identical_revision_rejected=True)
        check('original packet bytes idempotence stale edits hashes and immutable history',versions)
        names=['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']
        hash_value=query('select content_sha256 from agent_prompt_versions where id='+sql_text(prompt))
        declaration=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version='research-ideas-v1',prompt_version_id=prompt,prompt_version='research-ideas-v2',prompt_content_sha256=hash_value,model_id='synthetic-test-provider',cases_sha256='a'*64,cases=[dict(name=n,status='complete',passed=True,output_sha256='b'*64) for n in names],reviewer=dict(identity='Synthetic SQL fixture, not an actual evaluation',type='AI',independent=False,passed=True))
        pub=dict(p_version_id=prompt,p_expected_active_version_id=None,p_expected_content_sha256=hash_value,p_report=declaration,p_actor='Software fixture',p_module_id='research-verification')
        def publication():
            rejects(lambda:rpc('publish_agent_prompt',dict(pub,p_report=dict(declaration,reviewer={}))))
            bad=json.loads(json.dumps(declaration));bad['cases'][0]['passed']=False;rejects(lambda:rpc('publish_agent_prompt',dict(pub,p_report=bad)))
            assert rpc('publish_agent_prompt',pub)==prompt
            rejects(lambda:query("update agent_prompt_versions set system_prompt='Mutation' where id="+sql_text(prompt)))
            return dict(test_declarations='Synthetic fixtures only; not actual-model evidence',failed_report_refused=True,missing_reviewer_refused=True,published_bytes_immutable=True)
        check('publication refuses failures missing reviewers and preserves original prompt',publication)
        def begin(task='critic',session=None,packet_id=None,actor=ACTOR,provenance=None):
            params=dict(p_study=study,p_actor=actor,p_user='fixture@example.invalid',p_id=uid(),p_packet=packet_id or selected['id'],p_task=task,p_session=session,p_prompt=prompt,p_model='synthetic-test-provider',p_request=dict(task=task,unique=uid()),p_provenance=provenance or dict(packet_sha256=selected['sha256'],context_policy='fresh-packet-only',history_messages=0))
            return rpc('research_begin_idea_run',params),params
        def finish(run,output=None,status='complete',reason=None,messages=None):
            output=output or dict(summary='Software fixture review',questions=[],findings=[],verdict='ready')
            return rpc('research_finish_idea_run',dict(p_study=study,p_actor=ACTOR,p_id=run['id'],p_status=status,p_reason=reason,p_raw=workflow.canonical(output).decode(),p_output=output,p_usage=dict(tokens=None,measured_charges_usd=None),p_provenance=dict(stop_reason='tool_use',tool_events=[],data_origin='model-output'),p_messages=messages))
        def scopes():
            rejects(lambda:begin(actor=OTHER))
            rejects(lambda:begin(provenance=dict(history_messages=2,context_policy='fresh-packet-only')))
            rejects(lambda:begin(session=uid()))
            session=uid();r,params=begin('planning',session,provenance=dict(packet_sha256=selected['sha256'],context_policy='bounded-planning-history',history_messages=0))
            assert rpc('research_begin_idea_run',params)['replayed']
            rejects(lambda:begin('planning',session))
            finish(r,messages=[dict(role='user',content=[dict(text='Fixture')]),dict(role='assistant',content=[dict(text='Fixture answer')])])
            assert query('select count(*) from agent_answers where session_id='+sql_text(session))=='1'
            rejects(lambda:query("update research_idea_runs set output='{}'::jsonb where id="+sql_text(r['id']),role='service_role'))
            return dict(planning_answers_persisted=1,fresh_history_override_refused=True,terminal_immutable=True)
        check('model request scope replay history and terminal preservation',scopes)
        c,_=begin('comprehension');c=finish(c);k,_=begin();k=finish(k)
        acceptance=dict(action='accept',request_id=uid(),packet_id=selected['id'],comprehension_run_id=c['id'],critic_run_id=k['id'],reason='Explicit software-fixture owner acceptance, not scientific validation')
        def roles():
            duplicate=dict(acceptance,request_id=uid(),critic_run_id=c['id'])
            # Controlled old-schema counterexample rolls back all changes. The
            # same comprehension invocation satisfied both identifiers before
            # the additive constraint; it cannot pass the released gate.
            sql="begin; alter table research_idea_readiness drop constraint research_idea_distinct_review_roles; select research_accept_idea_plan("+','.join([sql_text(study)+'::uuid',sql_text(ACTOR)+'::uuid',sql_text(duplicate['request_id'])+'::uuid',sql_text(selected['id'])+'::uuid',sql_text(c['id'])+'::uuid',sql_text(c['id'])+'::uuid',sql_text('Controlled old-schema counterexample; software fixture only')])+"); rollback;"
            assert '"decision": "ready"' in query(sql)
            rejects(lambda:ideas.accept(study,ACTOR,duplicate))
            return dict(old_schema_counterexample='One comprehension invocation admitted as both roles; rolled back',new_gate='Duplicate invocation IDs refused',independent_scientific_review=False)
        check('both fresh review roles need distinct model invocations',roles)
        decision=ideas.accept(study,ACTOR,acceptance)
        assert ideas.status(study)['ready']
        s=json.loads(query('select row_to_json(s) from research_studies s where id='+sql_text(study)))
        campaign_body=dict(action='prepare-campaign',request_id=uid(),packet_id=selected['id'],title='Scoped software fixture pilot',stage='pilot',claim_type='numerical',experiment_type='independent-check',planned_units=1)
        prepared=ideas.prepare_campaign(s,ACTOR,campaign_body)
        def campaign():
            assert prepared['queue_request']['raw_input'] is None and prepared['queue_request']['execution_mode']=='manual'
            resumed=ideas.resume_campaign(s,ACTOR,dict(action='resume-campaign',prepared_id=prepared['link']['id']));assert resumed['queue_request']==prepared['queue_request']
            j=scheduler.enqueue(study,ACTOR,prepared['queue_request'])['job'];assert j['status']=='manual'
            assert scheduler.enqueue(study,ACTOR,prepared['queue_request'])['job']['id']==j['id']
            for table in ('research_published_values','research_measurements','research_runs','research_assessments','research_publications'):
                assert query('select count(*) from '+table+' where study_id='+sql_text(study))=='0'
            sources=json.loads(query('select json_agg(t) from (select kind,source_url from research_sources where study_id='+sql_text(study)+')t'));assert sources==[dict(kind='unpublished-proposal',source_url=None)]
            return dict(campaign_id=prepared['link']['campaign_id'],job_id=j['id'],status=j['status'],source='unpublished-proposal',empirical_rows_created=0,archival_bytes_verified=True)
        check('atomic reviewed protocol campaign and resumable manual queue',campaign)
        def later_critical():
            r,_=begin();finish(r,dict(summary='Later critic found unresolved issue',questions=['Resolve unit ambiguity'],findings=[],verdict='needs-clarification'))
            assert not ideas.status(study)['ready']
            rejects(lambda:ideas.accept(study,ACTOR,dict(acceptance,request_id=uid())))
            rejects(lambda:ideas.prepare_campaign(s,ACTOR,dict(campaign_body,request_id=uid())))
            q=dict(prepared['queue_request'],request_id=uid());rejects(lambda:scheduler.enqueue(study,ACTOR,q))
            return dict(prior_favorable_review_cannot_be_selected=True,existing_readiness_invalidated=True,new_campaign_and_queue_blocked=True)
        check('later critical review invalidates accepted readiness without deleting history',later_critical)
        check('review budgets count all attempts',lambda: (finish(begin()[0],status='failed',reason='Synthetic provider failure'),rejects(lambda:begin()),dict(attempt_cap=3,failed_attempt_counted=True))[-1])
        revised=ideas.save(study,ACTOR,dict(body,request_id=uid(),supersedes_id=selected['id'],document=dict(value,question='Changed exact-input wording; new reviews required'),reason='Software-fixture revised plan'))
        check('revisions retain previous packet reviews and invalidate current readiness',lambda: dict(versions=len(ideas.status(study)['packets']),ready=ideas.status(study)['ready'],old_review_count=len(ideas.status(study)['runs'])))
        assert revised['version']==2 and not ideas.status(study)['ready']
        def interview_publication():
            previous=prompt
            for version,candidate in [('v3','9f62d4b8-8eed-45c4-9c74-f1a964c5c217'),('v4','11439f38-79d5-47ba-8278-b26ad5811667'),('v5','4ab45b43-7f7d-4942-ac10-dc6a828b9c27'),('v6','82cc0c9e-9ad0-44d0-9dda-66757ccf536c'),('v7','782b9c80-120a-4196-956b-100282aa811b'),('v8','fc6d637f-0d6b-405c-a626-471a075efba0'),('v9','7d25f214-12cd-44b9-89d2-e37eb02c8bad'),('v10','9d024ab6-6dad-4cba-ae1b-33b616c857c8'),('v11','ba16759e-ff38-4491-ae21-5766261e710b')]:
                h=query('select content_sha256 from agent_prompt_versions where id='+sql_text(candidate))
                seed=json.loads((ROOT/('database/seed-research-ideas-prompt-'+version+'.json')).read_text())
                assert h==hashlib.sha256((seed['system_prompt']+'\n\n'+seed['research_context']).encode()).hexdigest()
                report_next=dict(declaration,prompt_version_id=candidate,prompt_version='research-ideas-'+version,prompt_content_sha256=h)
                payload=dict(pub,p_version_id=candidate,p_expected_active_version_id=previous,p_expected_content_sha256=h,p_report=report_next)
                rejects(lambda:rpc('publish_agent_prompt',payload))
                extra=[dict(name='interview-'+n,status='complete',passed=True,output_sha256='b'*64) for n in ('cdn','congestion','known','vague','unknown','untrusted','pilot','complete')]
                report_next=dict(report_next,cases=declaration['cases']+extra)
                if version in ('v9','v10','v11'):
                    rejects(lambda:rpc('publish_agent_prompt',dict(payload,p_report=report_next)))
                    names=['review-complete-critic','review-controls-only','review-statistics-only','review-consistent-percent','review-untrusted-metadata']
                    report_next=dict(report_next,cases=report_next['cases']+[dict(name=n,status='complete',passed=True,output_sha256='b'*64) for n in names])
                    if version in ('v10','v11'):
                        rejects(lambda:rpc('publish_agent_prompt',dict(payload,p_report=report_next)))
                        report_next['cases']=[dict(c,rendered_sha256='c'*64) for c in report_next['cases']]
                payload=dict(payload,p_report=report_next)
                bad=json.loads(json.dumps(report_next));bad['cases'][-1]['passed']=False
                rejects(lambda:rpc('publish_agent_prompt',dict(payload,p_report=bad)))
                assert rpc('publish_agent_prompt',payload)==candidate
                previous=candidate
            return dict(required_cases_up_to=21,candidates_checked=9,source_perturbations_required=True,rendered_hashes_required=True,seed_and_database_hashes_match=True,old_eight_cases_insufficient=True,failed_interview_refused=True,evidence='Synthetic SQL contract test only; no actual-model pass asserted')
        check('interview publication requires original reviews and all eight additional cases',interview_publication)
        report['passed']=True
    except Exception as error:
        report['passed']=False;report['error']=str(error);traceback.print_exc()
    finally:
        report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        (DIRECTORY/'validation-report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(directory=str(DIRECTORY),database=DATABASE,passed=report['passed'])))
    if not report['passed']:sys.exit(1)
