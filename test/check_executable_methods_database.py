"""Actual isolated Postgres/controller/worker; synthetic paper and Storage.

Two distinct claim protocols must share one executable arithmetic job and one
budget reservation. No scientific review, live model call or AWS launch occurs.
"""
import copy,json,sys,traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import check_research_ideas_database as f
sys.path.insert(0,str(f.ROOT.parent/'jumpserve-back-end/research_workflow/tests'))
from test_executable_methods import arithmetic_fixture
import autonomy,autonomy_model,autonomy_methods,network_spec,network_execution,store,worker,workflow
import autonomy_fixtures

def main():
    f.report.update(protocol='builder-continuation-validation-v2',parent_protocol='executable-methods-database-v1',amendment='artifact-backed-decision-followup-v1',design=__doc__,new_model_calls=0,new_cloud_instances=0)
    f.report['runtime_source_sha256']={}
    for name in ('autonomy.py','autonomy_methods.py','autonomy_model.py','shared_campaigns.py','store.py','worker.py','network_spec.py','network_execution.py','source_arithmetic.py','workflow.py'):
        original=f.ROOT.parent/'jumpserve-back-end/research_workflow'/name;raw=original.read_bytes()
        dest=f.DIRECTORY/'original-source'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        f.report['runtime_source_sha256'][name]=workflow.digest(raw)
    raw=Path(__file__).read_bytes();(f.DIRECTORY/'original-check_executable_methods_database.py').write_bytes(raw);f.report['test_source_sha256']=workflow.digest(raw)
    try:
        f.bootstrap()
        with patch.object(autonomy,'wake',return_value={}):
            study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Executable-method development fixture',paper_url='https://example.org/synthetic.pdf',domain='Software verification',scope='Synthetic source arithmetic and shared acquisition races only')))['id']
        initial=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
        cfg,raw=arithmetic_fixture();source=copy.deepcopy(autonomy_fixtures.plan()['records'][0]['record']);source['id']=cfg['source_id'];source['sha256']='a'*64
        source.update(citation='Synthetic arithmetic fixture',findings='Synthetic table arithmetic only; no empirical or paper validation.')
        claims=[dict(id=f.uid(),source_id=source['id'],location='Synthetic page 3',description='Synthetic reported arithmetic '+str(i),claim_type='numerical',scope=dict(origin='software-fixture'),metrics=[],priority=3) for i in range(2)]
        store.append_bundle(study,f.ACTOR,[dict(kind='sources',record=source)]+[dict(kind='claims',record=c) for c in claims])
        artifact=store.artifact(study,f.ACTOR,raw,cfg['text_artifact_id'],'application/json',dict(kind='derived-pdf-text',transformation='Explicit synthetic text fixture, not a parsed real PDF'))
        store.append(study,f.ACTOR,'artifacts',artifact)
        autonomy.seed(initial,claims,dict(source_id=source['id'],text_artifact_id=artifact['id']))
        autonomy.advance(initial,'finished',reason='Synthetic intake fixture; no AI invoked.')
        tasks=[f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={})) for _ in range(2)]
        for task in tasks:
            claim=next(c for c in claims if c['id']==task['claim_id'])
            p=workflow.numerical_protocol('a'*64,'gain','%',0,[dict(identity='claim-label-'+claim['id'][:6],details=dict(test_config=cfg))])
            p.update(hypotheses=claim['description'],data_origin='archived-data',stage='pilot',planned_units=1,prior_exposure='Exposed development fixture, no blind or scientific evaluation.')
            p['metrics']=[dict(name='gain',units='%',planned_observations=1),dict(name='delta',units='Mbit/s',planned_observations=1)]
            p['resource_limits'].update(wall_seconds=60,max_observations=2,max_input_bytes=256000)
            p['input_versions'].append(dict(identity='text',sha256=cfg['text_sha256']))
            p['execution']=dict(version=network_spec.VERSION,runner='source-arithmetic-v1',replications=1,limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=100000,max_network_bytes=1024),exclusive_resources=[])
            p['decision']=dict(version=autonomy_methods.DECISION_VERSION,claim_id=claim['id'],kind='source-arithmetic',coverage='complete-under-tested-conditions',rationale='Synthetic fixture source consistency only; not an empirical paper result.',groups=[],rules=[])
            task['context']['proposal']=autonomy.validate_proposal(task,dict(protocol=p,experiment_type='independent-check'))
        # Persist actual numbered requests and responses for both review roles.
        # Their judgments are explicitly synthetic; the controller, request
        # hashes, frozen protocols, SQL and artifact reader are real code.
        prompt=f.uid()
        # Test-only active prompt, as in the builder database fixture. This is
        # not a prompt publication/evaluation check and never runs remotely.
        f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-autonomy','synthetic-artifact-reader-review','Synthetic software fixture review','No scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-autonomy'")
        response=dict(stopReason='tool_use',output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(name='submit_assessment_step',input=dict(action='review',reason='ready-within-scope',blockers=[],claims=[],check_id=None,proposal=None,ready=True,coverage_complete=True,assessment_label=None,evidence_ids=[])))])),usage={})
        for role in ('comprehension','critic'):
            for task in tasks:autonomy.advance(task,'queued',stage=role,context=task['context'],reason='Explicit synthetic review fixture; no live model or human review.')
            tasks=[f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={})) for _ in range(2)]
            for task in tasks:
                assert task['stage']==role
                with patch.object(autonomy_model,'OPENCLAW',False),patch.object(autonomy_model,'load_prompt',return_value=({'id':prompt},'Synthetic software fixture review; no scientific validation.')):
                    answer=autonomy_model.call(task,dict(task=role,candidate=task['context']['proposal'],scope='Synthetic software review fixture; no original PDF review.'),autonomy.control,lambda request:copy.deepcopy(response))
                assert answer['status']=='complete',answer
                task['context'].setdefault('reviews',[]).append(dict(turn_id=answer['id'],role=role,coverage_complete=True))
        before_cents=int(f.query('select committed_cents from research_autonomy_workflows'))
        queued=[]
        def race():
            with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(autonomy.enqueue,tasks))
            queued.extend(results)
            assert results[0]['context']['job_ids']==results[1]['context']['job_ids']
            assert int(f.query('select count(*) from research_campaigns'))==1
            assert int(f.query('select count(*) from research_shared_campaign_members'))==2
            assert int(f.query('select count(*) from research_protocols'))==2
            assert int(f.query('select count(*) from research_claim_checks'))==2
            assert int(f.query('select count(*) from research_queue_jobs'))==1
            assert int(f.query('select count(*) from research_autonomy_job_commitments'))==1
            assert int(f.query('select committed_cents from research_autonomy_workflows'))==before_cents+1
            return dict(claims=2,claim_protocols=2,campaigns=1,jobs=1,experiment_reservations=1,experiment_reserved_cents=1)
        f.check('concurrent claims share identical acquisition jobs and retain separate protocols',race)
        def execution():
            original_advance=network_execution.advance;errors=[]
            def traced(*args):
                try:return original_advance(*args)
                except Exception:errors.append(traceback.format_exc());raise
            with patch.object(network_execution,'advance',side_effect=traced):result=worker.handler({})
            if errors:raise AssertionError(errors[0])
            job=store.rows('queue_jobs',dict(study_id='eq.'+study))[0]
            assert job['status']=='awaiting-review',result
            rows=store.rows('measurements',dict(study_id='eq.'+study));assert {x['metric']:x['value'] for x in rows}=={'gain':'35.0','delta':'25.2'},rows
            assert all(x['status']=='recorded' for x in rows)
            assert len(store.rows('published_values',dict(study_id='eq.'+study)))==2
            assert len(store.rows('runs',dict(study_id='eq.'+study)))==1
            assert all(x['statistics']['numerical_consistency']['consistent']==1 for x in store.rows('summaries',dict(study_id='eq.'+study)))
            assert all('Source numerical consistency only' in x['details']['producer']['scope'] for x in rows)
            return dict(measurements=2,published_values=2,runs=1,measured_values={x['metric']:x['value'] for x in rows},empirical_measurements=0)
        f.check('actual worker computes source arithmetic and persists separate published values',execution)
        def decisions():
            jobs=store.rows('queue_jobs',dict(study_id='eq.'+study));assert len(jobs)==1
            job=jobs[0];assert 'raw_input' not in job['request']
            original=store.queue_input_bytes(study,job)
            assert workflow.digest(original)==job['request']['input_sha256']
            findings=[]
            for record in queued:
                task=store.rows('autonomy_tasks',dict(study_id='eq.'+study,id='eq.'+record['id'],limit=1))[0]
                finding=autonomy.numeric_finding(task);assert finding and finding[0]=='reproduced',finding
                assert finding[2]['decision_runs']==1 and finding[2]['required_runs']==1
                findings.append(dict(task_id=task['id'],label=finding[0],rules=finding[2]['rules']))
            with patch.object(store,'artifact_bytes',side_effect=store.StoreError('Synthetic unavailable Storage input')):
                assert autonomy.numeric_finding(task) is None
            return dict(persisted_input_representation='hash-verified artifact reference; no inline raw_input',shared_runs=1,claim_decisions=2,findings=findings,missing_input='No conclusive decision; never zero',review_judgments='Synthetic test responses persisted through real numbered begin/finish RPCs, not scientific review')
        f.check('artifact-backed queue input reaches both frozen claim-specific numerical decisions',decisions)
        def access():
            signature='research_shared_campaign_bind(uuid,uuid,uuid,uuid,text,jsonb,uuid,uuid,jsonb)'
            for role in ('anon','authenticated'):
                for table in ('research_shared_campaigns','research_shared_campaign_members'):
                    assert f.query("select has_table_privilege(current_user,'"+table+"','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
                assert f.query("select has_function_privilege(current_user,'"+signature+"','EXECUTE')",role=role)=='f'
            f.rejects(lambda:f.query("update research_shared_campaigns set acquisition='{}'"))
            f.rejects(lambda:f.query('delete from research_shared_campaign_members'))
            return dict(browser_writes_denied=True,private_coordinator_rls=True,append_only=True)
        f.check('shared coordination retains RLS browser denial and immutable history',access)
        # Export the unchanged published builder template reconstructed by the
        # original local migrations for the credential-free native CLI check.
        # No production query, publication or active-pointer change occurs.
        prompt=json.loads(f.query("select row_to_json(t) from (select id,module_id,version,system_prompt,research_context,content_sha256 from agent_prompt_versions where id='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27') t"))
        assert workflow.digest((prompt['system_prompt']+'\n\n'+prompt['research_context']).encode())==prompt['content_sha256']
        fixture=f.ROOT.parent/'jumpserve-back-end/.test-artifacts/builder-image/published-prompt-v2.json';fixture.parent.mkdir(parents=True,exist_ok=True)
        original=workflow.canonical(prompt)
        if fixture.exists():assert fixture.read_bytes()==original,'Retained prompt fixture changed; preserve and version it.'
        else:fixture.write_bytes(original)
        f.report['native_prompt_fixture']=dict(path=str(fixture),sha256=workflow.digest(original),origin='Reconstructed by original local SQL migrations; not a live production query or model-quality evaluation.')
        f.report['passed']=True
    except Exception:
        f.report['passed']=False;f.report['failure']=traceback.format_exc();raise
    finally:
        (f.DIRECTORY/'report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(report=str(f.DIRECTORY/'report.json'),passed=f.report.get('passed'))))

if __name__=='__main__':main()
