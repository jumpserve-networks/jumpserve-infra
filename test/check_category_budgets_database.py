"""Current category policies against actual isolated PostgreSQL admissions.

Synthetic identities/storage only. No production, cloud or provider calls.
"""
import json,os,uuid
from unittest.mock import patch
import check_unlimited_assessment_defaults_database as previous
import check_research_ideas_database as f
import autonomy,workflow

MIGRATION='202610310003_category_budgets.sql'

def main():
    previous.main()
    f.report.update(protocol='autonomy-category-budgets-v1',passed=False)
    q=f.sql_text
    def query(sql,role=None):return f.query(sql,role=role)
    def js(sql,role=None):
        value=query(sql,role);return json.loads(value) if value else None
    def count(table,where='true'):return int(query('select count(*) from '+table+' where '+where))
    def check(name,action):f.check(name,lambda:(action() or dict(passed=True)))
    def assert_true(value):
        if not value:raise AssertionError('Category budget invariant failed.')
    def snapshot():return js('select public.autonomy_budget_snapshot()',role='service_role')
    def configure(category,cents=-1,calls=-1):
        query('update autonomy_budget_categories set max_spend_cents='+str(cents)+',max_model_calls='+str(calls)+",change_reason='Explicit synthetic policy update' where category="+q(category))
    def allowed(category,spent=0,calls=0,cents=100,delta=1):
        return query('select public.autonomy_budget_allows('+','.join([q(category),str(spent),str(calls),str(cents),str(delta)])+')')=='t'
    def operator(sql,actor=None,google=True):
        claims=dict(sub=actor or f.ACTOR,app_metadata=dict(provider='google' if google else 'email'))
        return query('do $jwt$ begin perform set_config(\'request.jwt.claims\','+f.sql_json(claims)+"::text,true);end $jwt$;"+sql,role='authenticated')

    query("""create schema if not exists auth;
create table if not exists auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
create or replace function auth.jwt() returns jsonb language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb$$;
create or replace function auth.uid() returns uuid language sql stable as $$select (auth.jwt()->>'sub')::uuid$$;
grant usage on schema auth to anon,authenticated,service_role;
""")
    for name in ('202610300004_platform_supervisor.sql','202610300005_platform_worker.sql','202610300006_platform_host_coordination.sql','202610310002_assessment_blocker_repairs.sql'):
        query((f.ROOT/'database'/name).read_text())
    query('insert into auth.users values('+q(f.ACTOR)+",'owner@example.invalid',now());insert into platform_operator_enrollments(email,role) values('owner@example.invalid','owner')")
    operator('select public.platform_enroll_operator()')
    raw=(f.ROOT/'database'/MIGRATION).read_bytes()
    f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
    query(raw.decode())
    check('all four categories seed spending and model-call budgets as explicit unlimited -1',lambda:assert_true(len(snapshot()['categories'])==4 and all(b['max_spend_cents']==b['max_model_calls']==-1 for b in snapshot()['categories'])))
    check('unlimited policy retains usage without imposing a zero or historical cap',lambda:assert_true(allowed('research_assessment',2000000,5000,10000,1)))
    def finite():
        configure('research_assessment',1000,2)
        assert allowed('research_assessment',900,1,100,1)
        assert not allowed('research_assessment',901,1,100,1)
        assert not allowed('research_assessment',900,2,0,1)
        assert allowed('research_assessment',900,2,0,0)
        configure('research_assessment',0,0)
        assert not allowed('research_assessment')
        configure('research_assessment')
        assert allowed('research_assessment',2000000,5000,10000,1)
    check('finite zero and unlimited policies take effect without code changes or counter resets',finite)
    def security():
        for role in ('anon','service_role'):
            f.rejects(lambda:query("update autonomy_budget_categories set max_spend_cents=100 where category='platform_manual'",role))
        assert operator('select count(*) from autonomy_budget_categories')=='4'
        assert operator("select count(*) from autonomy_budget_categories",actor=f.OTHER)=='0'
        assert operator("select count(*) from autonomy_budget_categories",google=False)=='0'
        f.rejects(lambda:operator('update autonomy_budget_categories set revision=1'))
        f.rejects(lambda:query("update autonomy_budget_categories set max_spend_cents=-2"))
        f.rejects(lambda:query("update autonomy_budget_categories set max_model_calls=null"))
        f.rejects(lambda:query("delete from autonomy_budget_categories"))
        f.rejects(lambda:query("update autonomy_budget_history set current='{}'"))
        f.rejects(lambda:query("select public.autonomy_budget_allows('platform_manual',0,0,100,1)",role='service_role'))
        f.rejects(lambda:query("select public.autonomy_budget_allows('missing',0,0,100,1)"))
        f.rejects(lambda:query("select public.autonomy_budget_allows('platform_manual',-1,0,100,1)"))
        operator("update autonomy_budget_categories set max_model_calls=3,change_reason='Google owner fixture' where category='platform_manual'")
        record=js("select current from autonomy_budget_history where category='platform_manual' order by revision desc limit 1")
        assert record['max_model_calls']==3
        assert query("select actor_id from autonomy_budget_history where category='platform_manual' order by revision desc limit 1")==f.ACTOR
        configure('platform_manual')
    check('owners can edit audited policy while workers cannot raise budgets or forge history',security)

    worker=f.uid();policy='a'*64
    query("insert into platform_authorizations(version,policy_sha256,document,source_instruction) values('fixture-category-policy',"+q(policy)+",'{}','Explicit synthetic software test');update platform_settings set authorization_version='fixture-category-policy',paused=false where id")
    def work(operation,task=None,token=None,payload=None):
        return js('select public.platform_worker('+','.join([q(operation),q(worker),'null' if task is None else q(task),'null' if token is None else q(token),f.sql_json(payload or {})])+')',role='service_role')
    def enqueue():
        ident=f.uid();payload=dict(title='Category budget fixture',objective='Synthetic admission only; never call a provider.',repositories=['jumpserve-networks/jumpserve-front-end'])
        return enqueue_result(ident,payload)
    def enqueue_result(ident,payload):
        return json.loads(operator('select public.platform_control(\'enqueue\','+q(f.uid())+','+q(ident)+','+f.sql_json(payload)+')'))
    manual=enqueue()['task_id']
    check('new owner tasks inherit the current category and -1 without per-task overrides',lambda:assert_true(js('select to_jsonb(t) from platform_tasks t where id='+q(manual))['max_reserved_cents']==-1))
    claimed=work('claim',payload=dict(policy_sha256=policy))
    assert claimed and claimed['id']==manual,claimed
    token=claimed['lease_token'];artifact=f.uid()
    work('artifact',manual,token,dict(id=artifact,name='synthetic-request',sha256='c'*64,byte_count=0,storage_path=manual+'/'+'c'*64,media_type='application/json',provenance=dict(fixture=True)))
    def begin():return work('begin-run',manual,token,dict(id=f.uid(),request_artifact_id=artifact,request_sha256='c'*64))
    def finish(run):return work('finish-run',manual,token,dict(id=run['id'],status='complete',response_artifact_id=artifact,usage=None,reason='Synthetic transport fixture; no provider called.'))
    first=begin();finish(first)
    original=js('select to_jsonb(t) from platform_tasks t where id='+q(manual))
    def platform_admission():
        configure('platform_manual',100,1)
        flags=work('lease',manual,token)
        assert flags['max_reserved_cents']==100 and flags['model_calls']==1 and flags['max_model_calls']==1
        assert begin()['denied']=='budget'
        configure('platform_manual',0,0)
        assert begin()['denied']=='budget'
        configure('platform_manual')
        second=begin();assert not second.get('denied');finish(second)
        after=js('select to_jsonb(t) from platform_tasks t where id='+q(manual))
        assert after['committed_cents']==200 and after['max_reserved_cents']==-1
        assert after['deadline_at']==original['deadline_at'] and after['checkpoint']==original['checkpoint']
    check('actual fenced platform admission uses category spending and call limits dynamically',platform_admission)
    work('checkpoint',manual,token,dict(status='budget',reason='Explicit software fixture; no in-flight action.'))
    work('maintenance',payload=dict(policy_sha256=policy))
    check('safe platform budget stops resume with retained usage and deadlines',lambda:assert_true(query('select status from platform_tasks where id='+q(manual))=='implementing'))
    check('private dashboard projection exposes complete current category policy',lambda:assert_true(len(json.loads(operator('select public.platform_snapshot()'))['budget_categories'])==4))
    # Preserve the existing unknown-call and release boundary after unlimited.
    query("update platform_tasks set status='cancelled' where id="+q(manual))
    def scoped_qualification_claim():
        ident=enqueue()['task_id']
        selected=work('claim',payload=dict(policy_sha256=policy,only_task=ident))
        assert selected['id']==ident
        work('checkpoint',ident,selected['lease_token'],dict(status='cancelled',reason='Synthetic scoped claim complete; no provider or release.'))
        assert work('claim',payload=dict(policy_sha256=policy,only_task=f.uid())) is None
        unresolved=enqueue()['task_id'];target=enqueue()['task_id']
        query("update platform_tasks set status='reconciling' where id="+q(unresolved))
        assert work('claim',payload=dict(policy_sha256=policy,only_task=target)) is None
        query("update platform_tasks set status='cancelled' where id="+q(unresolved))
        selected=work('claim',payload=dict(policy_sha256=policy,only_task=target));assert selected['id']==target
        work('checkpoint',target,selected['lease_token'],dict(status='cancelled',reason='Synthetic reconciliation fence check complete.'))
    check('qualification can claim only its exact task without consuming another queued repair',scoped_qualification_claim)
    with patch.object(autonomy,'wake',return_value={}):
        study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Category-controlled research fixture',paper_url='https://example.org/fixture.pdf',domain='Software test',scope=__doc__)))['id']
    before=js('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(study))
    configure('research_assessment',600,3)
    query('select public.autonomy_budget_sync_assessments()')
    capped=js('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(study))
    assert capped['max_spend_cents']==600 and capped['committed_cents']==before['committed_cents']
    configure('research_assessment')
    query('select public.autonomy_budget_sync_assessments()')
    after=js('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(study))
    check('active research budgets follow the table with same-transaction audit and unchanged originals',lambda:assert_true(after['max_spend_cents'] is None and all(after[k]==before[k] for k in ('initial_prompt','initial_sha256','deadline_at','committed_cents','max_attempts'))))
    research_task=js('select to_jsonb(t) from research_autonomy_tasks t where study_id='+q(study))
    lease_token=f.uid()
    query("update research_autonomy_tasks set status='running',lease_token="+q(lease_token)+",lease_until=clock_timestamp()+interval '10 minutes' where id="+q(research_task['id']))
    research_task.update(lease_token=lease_token,actor_id=f.ACTOR,workflow=after)
    prompt=query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
    raw_request=workflow.canonical(dict(builder=dict(scope='Synthetic category admission, no provider called.'))).decode()
    def research_begin():return autonomy.control(research_task,'begin',dict(id=f.uid(),request=json.loads(raw_request),request_raw=raw_request,request_sha256=workflow.digest(raw_request.encode()),reserved_cents=100,prompt_version_id=prompt,model_id='gpt-6.1-sol'))
    def research_finish(turn,status='invalid-output'):
        return autonomy.control(research_task,'finish',dict(id=turn['id'],status=status,raw_response=None if status=='unknown' else '{}',output=None,reason='Synthetic SQL transport; no provider called.',usage={},estimated_cents=None))
    def research_admission():
        configure('research_assessment',-1,1)
        first=research_begin();assert not first.get('denied');research_finish(first)
        current=js('select to_jsonb(w) from research_autonomy_workflows w where study_id='+q(study))
        assert current['committed_cents']==600 and research_begin()['denied']=='budget'
        assert count('research_autonomy_turns','study_id='+q(study))==1
        autonomy.advance(research_task,'budget',context={},reason='Paper admission stopped by budget.')
        query('select public.autonomy_budget_sync_assessments()')
        assert query('select status from research_autonomy_tasks where id='+q(research_task['id']))=='budget'
        configure('research_assessment')
        query('select public.autonomy_budget_sync_assessments()')
        task_now=js('select to_jsonb(t) from research_autonomy_tasks t where id='+q(research_task['id']))
        assert task_now['status']=='queued' and task_now['attempts']==1
        assert query('select committed_cents from research_autonomy_workflows where study_id='+q(study))=='600'
        assert query('select deadline_at from research_autonomy_workflows where study_id='+q(study))==query('select '+q(before['deadline_at'])+'::timestamptz')
    check('actual assessment model admissions enforce call budgets and safely resume after unlimited policy',research_admission)
    def uncertainty():
        query("update research_autonomy_tasks set status='running',lease_token="+q(lease_token)+",lease_until=clock_timestamp()+interval '10 minutes' where id="+q(research_task['id']))
        turn=research_begin();research_finish(turn,'unknown')
        configure('research_assessment',-1,2)
        assert query('select public.research_category_budget_allows('+q(study)+','+q(research_task['id'])+',100,1)')=='f'
        autonomy.advance(research_task,'budget',context={},reason='Explicit synthetic budget stop with retained unknown turn.')
        configure('research_assessment')
        query('select public.autonomy_budget_sync_assessments()')
        assert query('select status from research_autonomy_tasks where id='+q(research_task['id']))=='budget'
        assert query('select status from research_autonomy_turns where id='+q(turn['id']))=='unknown'
        assert query('select attempts from research_autonomy_tasks where id='+q(research_task['id']))=='2'
    check('unlimited settings cannot replay or resume an unresolved original provider turn',uncertainty)
    def live_defaults_and_replay():
        request_id=f.uid();paper=dict(title='Dynamic default fixture',paper_url='https://example.org/fixture.pdf',domain='Software',scope=__doc__)
        def start(identifier):
            # Exercise the deployed SQL with an explicit policy-derived request.
            # Backend RPC parsing/default generation has separate unit checks.
            policy=next(row for row in snapshot()['categories'] if row['category']=='research_assessment')
            details=workflow.paper_details(paper);details['study_kind']='paper'
            payload=autonomy.start_payload(identifier,details);initial=json.loads(payload['initial_prompt'])
            initial['defaults']['maximum_spend_usd']=None if policy['max_spend_cents']==-1 else policy['max_spend_cents']/100
            payload['initial_prompt']=workflow.canonical(initial).decode()
            return f.rpc('research_autonomy_control',dict(p_operation='start',p_actor=f.ACTOR,p_study=identifier,p_payload=payload))
        configure('research_assessment',1000,3)
        first=start(request_id)
        initial=first['autonomy']['initial_prompt'];assert json.loads(initial)['defaults']['maximum_spend_usd']==10
        assert first['autonomy']['budget_policy']['max_model_calls']==3
        configure('research_assessment')
        replay=start(request_id)
        assert replay['autonomy']['initial_prompt']==initial and replay['autonomy']['max_spend_cents'] is None
        assert replay['id']==request_id and count('research_autonomy_workflows','study_id='+q(request_id))==1
        configure('research_assessment',0,0)
        assert start(f.uid())['denied']=='budget'
        configure('research_assessment')
    check('SQL intake inherits live policy and changed defaults preserve exact original request bytes',live_defaults_and_replay)
    f.report['passed']=True
    path=f.DIRECTORY/'category-budgets-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),production_mutations=0,provider_calls=0)))

if __name__=='__main__':main()
