"""Actual local SQL/API funding-default checks; no model, AWS or production calls."""
import json,os,shutil,urllib.parse
from unittest.mock import patch
import check_optional_budget_database as legacy
import check_research_ideas_database as f
import autonomy,workflow

MIGRATION='202610310001_unlimited_assessment_defaults.sql'

def main():
    url=os.environ.get('UNLIMITED_DEFAULTS_TEST_DATABASE_URL')
    if url:
        target=urllib.parse.urlsplit(url)
        if target.scheme!='postgresql' or target.hostname not in ('127.0.0.1','localhost') or target.path not in ('/postgres','/'):
            raise ValueError('Only an explicitly configured isolated localhost database is permitted.')
        f.ORIGIN=urllib.parse.urlunsplit((target.scheme,target.netloc,'/','',''))
        f.PSQL=shutil.which('psql') or f.PSQL
    # Retain and execute the existing amendment, unknown-call, restored-cap,
    # cancellation and ledger checks before changing the creation default.
    legacy.main()
    f.report.update(protocol='unlimited-assessment-defaults-v1',passed=False)
    def start(title):
        with patch.object(autonomy,'wake',return_value={}):
            return autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title=title,paper_url='https://example.org/fixture.pdf',domain='Software validation',scope=__doc__)))['id']
    budget=start('Synthetic budget-stopped assessment')
    blocked=start('Synthetic separately blocked assessment')
    cancelled=start('Synthetic cancelled assessment')
    f.query("update research_autonomy_workflows set committed_cents=10000,status='budget' where study_id="+f.sql_text(budget)+";update research_autonomy_tasks set status='budget' where study_id="+f.sql_text(budget))
    f.query("update research_autonomy_tasks set status='blocked',reason='Independent missing-input fixture' where study_id="+f.sql_text(blocked))
    f.query("update research_autonomy_workflows set status='cancelled' where study_id="+f.sql_text(cancelled)+";update research_autonomy_tasks set status='cancelled' where study_id="+f.sql_text(cancelled))
    identities=','.join(map(f.sql_text,[budget,blocked,cancelled]))
    def snapshots():return json.loads(f.query('select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w where study_id in ('+identities+')'))
    before=snapshots()
    functions=json.loads(f.query("select jsonb_object_agg(p.proname,pg_get_functiondef(p.oid)) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'research_autonomy%'"))
    raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.report['migration_sha256'][MIGRATION]=workflow.digest(raw);f.query(raw.decode())

    def existing():
        after=snapshots()
        for old,new in zip(before,after):
            for key in ('study_id','initial_prompt','initial_sha256','max_attempts','committed_cents','created_at','deadline_at'):assert old[key]==new[key],key
            assert new['max_spend_cents'] == (10000 if old['study_id']==cancelled else None)
        assert f.query('select status from research_autonomy_workflows where study_id='+f.sql_text(budget))=='running'
        assert f.query('select status from research_autonomy_tasks where study_id='+f.sql_text(budget))=='queued'
        assert f.query('select status from research_autonomy_tasks where study_id='+f.sql_text(blocked))=='blocked'
        assert f.query('select status from research_autonomy_tasks where study_id='+f.sql_text(cancelled))=='cancelled'
        for name,body in functions.items():
            current=f.query('select pg_get_functiondef(oid) from pg_proc where proname='+f.sql_text(name)+" and pronamespace='public'::regnamespace")
            if name=='research_autonomy_initial_budget':continue
            assert current==body.replace("'maximum_spend_usd',100,","'maximum_spend_usd',null,").strip(),name
        return dict(existing_active_unlimited=True,budget_only_resume=True,blocked_and_cancelled_preserved=True,original_limits_counters_and_prompts_preserved=True,existing_admission_functions_preserved=True)
    f.check('global funding amendment preserves existing evidence and safe admission',existing)

    def future():
        study=start('Synthetic future unlimited assessment')
        original=json.loads(f.query('select to_jsonb(w) from research_autonomy_workflows w where study_id='+f.sql_text(study)))
        assert original['max_spend_cents'] is None and original['max_attempts'] is None and original['committed_cents']==500
        assert json.loads(original['initial_prompt'])['defaults']['maximum_spend_usd'] is None
        event=json.loads(f.query("select details from research_autonomy_events where study_id="+f.sql_text(study)+" and event='budget-policy-inherited'"))
        assert event['max_spend_cents'] is None and event['authorization']=='All active and future assessments' and event['initial_sha256']==original['initial_sha256']
        assert json.loads(f.query("select details from research_autonomy_events where study_id="+f.sql_text(study)+" and event='initial-prompt'"))['maximum_spend_usd'] is None
        public=f.api.dispatch(dict(rawPath='/research/studies/'+study+'/queue',requestContext=dict(http=dict(method='GET')),queryStringParameters=dict(public='1',diagnostics='1')),None)
        assert public['autonomy']['defaults']['maximum_spend_usd'] is None and public['autonomy']['workflows'][0]['max_spend_cents'] is None
        assert 'initial_prompt' not in public['autonomy']['workflows'][0]
        (f.DIRECTORY/'unlimited-defaults-public-queue.json').write_text(json.dumps(public,indent=2)+'\n')
        return dict(future_default_unlimited=True,initial_prompt_and_event_match=True,inherited_operator_authority_recorded=True,actual_public_api_preserves_null=True,retained_overhead_cents=500,deadline=original['deadline_at'])
    f.check('new intake inherits explicit unlimited funding through actual SQL and API',future)

    def security():
        for role in ('anon','authenticated'):
            f.rejects(lambda:f.query('select * from research_assessment_budget_policies',role=role))
        for role in ('service_role','authenticated'):
            f.rejects(lambda:f.query("update research_assessment_budget_policies set authorization_text='Unauthorized replacement'",role=role))
        assert f.query("select relrowsecurity from pg_class where oid='research_assessment_budget_policies'::regclass")=='t'
        paper=workflow.paper_details(dict(title='Synthetic override guard',domain='Software validation',scope=__doc__,study_kind='paper',paper_url='https://example.org/fixture.pdf'))
        study=f.uid();f.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=paper))
        prompt='Synthetic initial default guard';sha=workflow.digest(prompt.encode())
        insert='insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256,max_spend_cents) values('+','.join([f.sql_text(study),f.sql_text(prompt),f.sql_text(sha),'10000'])+')'
        f.rejects(lambda:f.query(insert,role='service_role'))
        f.query(insert.replace(',10000)',',null)'),role='service_role')
        return dict(policy_private_and_immutable=True,browser_policy_writes_denied=True,finite_initial_override_rejected=True,explicit_null_authorized=True)
    f.check('standing authorization remains private and cannot be overwritten by runtime roles',security)
    f.report['passed']=True
    path=f.DIRECTORY/'unlimited-defaults-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(path),checks=f.report['checks'],new_provider_calls=0,new_cloud_instances=0)))

if __name__=='__main__':
    try:main()
    except Exception as error:
        f.report.update(passed=False,error_type=type(error).__name__,error=str(error))
        (f.DIRECTORY/'unlimited-defaults-failed-report.json').write_text(json.dumps(f.report,indent=2)+'\n')
        raise
