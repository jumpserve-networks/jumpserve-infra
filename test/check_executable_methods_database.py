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
import autonomy,network_spec,network_execution,store,worker,workflow
import autonomy_fixtures

def main():
    f.report.update(protocol='executable-methods-database-v1',design=__doc__,new_model_calls=0,new_cloud_instances=0)
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
            task['context']['proposal']=autonomy.validate_proposal(task,dict(protocol=p,experiment_type='independent-check'))
        before_cents=int(f.query('select committed_cents from research_autonomy_workflows'))
        def race():
            with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(autonomy.enqueue,tasks))
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
        f.report['passed']=True
    except Exception:
        f.report['passed']=False;f.report['failure']=traceback.format_exc();raise
    finally:
        (f.DIRECTORY/'report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(report=str(f.DIRECTORY/'report.json'),passed=f.report.get('passed'))))

if __name__=='__main__':main()
