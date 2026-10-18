"""Isolated SQL/API planning-to-queue checks; no real auth, model or cloud tests."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch
import check_research_ideas_database as f
import claim_design
from research_idea_fixtures import packet

def main():
    f.report.update(protocol='claim-experiment-design-protocol-v3')
    try:
        f.bootstrap()
        uid=lambda:str(f.uuid.uuid4())
        study=uid();value=packet()
        paper=f.workflow.paper_details(dict(title='Paper-claim software fixture, not scientific evidence',paper_url='https://example.org/software-fixture',domain='Software verification',scope='Synthetic source and claim; no real paper was assessed.',study_kind='paper'))
        f.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=paper))
        source=dict(id=uid(),citation='Synthetic paper-shaped source for software tests',source_url=paper['paper_url'],retrieved_url=None,kind='software-fixture',role='Exercise source binding only',retrieved_version='fixture-v1',sha256='a'*64,byte_count=1,access_status='retrieved',review_status='retrieved-unreviewed',review_definition='No substantive review',examined='Synthetic metadata only',unexamined='No actual full text exists for this software fixture',retrieval_attempts=[],reviewer=dict(identity='Software fixture',type='AI',independence='Not independent'),findings='No scientific findings',limitations='Not a scientific source')
        claim=dict(id=uid(),source_id=source['id'],location='Synthetic claim fixture',description=value['hypothesis'],claim_type='numerical',scope={},metrics=value['protocol']['metrics'],priority=3)
        f.rpc('research_append_bundle',dict(p_study=study,p_actor=f.ACTOR,p_records=[dict(kind='sources',record=source),dict(kind='claims',record=claim)]))
        preview,_=claim_design.selection(study,f.ACTOR,claim['id'])
        body=dict(action='design',request_id=uid(),claim_id=claim['id'],claim_sha256=preview['claim_sha256'])
        target=claim_design.start(study,f.ACTOR,body)['study_id']
        f.check('every recorded claim can start a private design with no preexisting gap',lambda:dict(study_id=target,original_gap_count=0,paper_origin=True))
        assert claim_design.start(study,f.ACTOR,dict(body,request_id=uid()))['study_id']==target
        retained=claim_design.context(target)
        def security():
            for role in ('anon','authenticated'):
                assert f.query("select has_table_privilege(current_user,'research_claim_designs','SELECT')",role=role)=='f'
                assert f.query("select has_function_privilege(current_user,'research_initialize_claim_design(uuid,uuid,jsonb,text,text,jsonb,jsonb)','EXECUTE')",role=role)=='f'
            f.rejects(lambda:f.query("update research_claim_designs set sha256=repeat('b',64) where study_id="+f.sql_text(target)))
            f.rejects(lambda:f.ideas.save(target,f.OTHER,dict(action='save',request_id=uid(),supersedes_id=None,document=value,reason='Wrong owner')))
            return dict(browser_read_and_write_denied=True,immutable_context=True,other_owner_denied=True)
        f.check('private ownership RLS and immutable context',security)
        value['protocol']['input_versions'].append(dict(identity='Original selected source bytes',sha256=source['sha256']))
        value['protocol'].update(stage='pilot',experiment_type='independent-check',decision_policy=claim_design.POLICY_IDENTITY,statistics=claim_design.POLICY['statistics'])
        value['falsification']=claim_design.POLICY['decision_rule']
        initial=f.ideas.status(target)['current_packet_id']
        selected=claim_design.save(target,f.ACTOR,dict(action='save',request_id=uid(),supersedes_id=initial,document=value,reason='Complete finite software test plan'))
        def binding():
            f.rejects(lambda:claim_design.save(target,f.ACTOR,dict(action='save',request_id=uid(),supersedes_id=selected['id'],document=dict(value,hypothesis='Weaker claim'),reason='Bad revision')))
            # SQL also enforces it if a service implementation bypasses Python.
            changed=dict(value,hypothesis='Weaker claim');raw=f.workflow.canonical(changed).decode()
            f.rejects(lambda:f.rpc('research_save_idea_packet',dict(p_study=target,p_actor=f.ACTOR,p_id=uid(),p_previous=selected['id'],p_document=changed,p_raw=raw,p_sha256=f.workflow.digest(raw.encode()),p_reason='Bad bypass')))
            bad=json.loads(json.dumps(value));bad['protocol']['statistics']='p > .05 proves no effect';raw=f.workflow.canonical(bad).decode()
            f.rejects(lambda:f.rpc('research_save_idea_packet',dict(p_study=target,p_actor=f.ACTOR,p_id=uid(),p_previous=selected['id'],p_document=bad,p_raw=raw,p_sha256=f.workflow.digest(raw.encode()),p_reason='Bad inference bypass')))
            assert f.query('select count(*) from research_assessments')=='0'
            return dict(exact_claim_enforced_twice=True,source_hash_retained=True,assessments_created=0)
        f.check('original claim cannot be weakened and original assessment is untouched',binding)
        prompt='3da220d0-cde0-5ab5-b8cd-ccbd23ece025'
        sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(prompt))
        cases=json.loads((f.ROOT/'test/claim-design-evaluation-cases-v4.json').read_text())
        names=[c['name'] for c in cases['cases']]
        cases_sha=json.loads((f.ROOT/'test/claim-design-evaluation-cases-v4.lock.json').read_text())['sha256']
        report=dict(protocol='claim-experiment-design-protocol-v3',decision_policy=claim_design.POLICY_IDENTITY,evaluation_kind='actual-model-development',module_id='research-claim-design',analysis_version=claim_design.VERSION,prompt_version_id=prompt,prompt_version='research-claim-design-v6',prompt_content_sha256=sha,model_id='synthetic-test-provider',cases_sha256=cases_sha,cases=[dict(name=n,status='complete',passed=True,raw_answer_reviewed=True,rendered_answer_reviewed=True,output_sha256='b'*64) for n in names],evaluator=dict(identity='Synthetic SQL contract fixture',type='AI',independent=False),reviewer=dict(identity='Synthetic SQL contract fixture',type='AI',independent=False,passed=True))
        sys.path.insert(0,str(f.ROOT/'agent'));import claim_experiment_design as model_design
        report.update(response_version=model_design.RESPONSE_VERSION,runner_context_sha256=f.workflow.digest(model_design.canonical(model_design.RUNNER_CONTEXT)),response_channel_sha256=f.workflow.digest(model_design.canonical(model_design.response_channel())),input_sha256={n:f.workflow.digest((f.ROOT/n).read_bytes()) for n in ('agent/claim_experiment_design.py','agent/research_ideas.py')})
        for row in report['cases']:row['rendered_output_sha256']='c'*64
        report=json.loads((f.ROOT/'docs/claim-design-followup-validation/v6-replay-exact-final/evaluation-reviewed.json').read_text())
        pub=dict(p_version_id=prompt,p_expected_active_version_id=None,p_expected_content_sha256=sha,p_report=report,p_actor='Software fixture only',p_module_id='research-claim-design')
        def publication():
            failed=copy.deepcopy(report);failed['cases'][0]['passed']=False
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=failed)))
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=dict(report,cases=report['cases'][:-1]))))
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=dict(report,decision_policy={}))))
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=dict(report,cases=[dict(c,raw_answer_reviewed=False) for c in report['cases']]))))
            actual=json.loads((f.ROOT/'docs/claim-design-correction-validation/evaluation-v4/evaluation-reviewed.json').read_text())
            assert sum(c['passed'] for c in actual['cases'])==9
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=actual)))
            wrong=copy.deepcopy(report);wrong['cases'][0]['provider_bytes_sha256']='e'*64
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=wrong)))
            f.rejects(lambda:f.rpc('publish_agent_prompt',dict(pub,p_report=dict(report,parent_report_sha256='e'*64))))
            assert f.rpc('publish_agent_prompt',pub)==prompt
            return dict(failed_and_incomplete_cases_rejected=True,publication='Local synthetic contract fixture only')
        f.check('prompt publication requires all twenty raw and rendered actual-answer cases',publication)
        reuse_request={}
        def unchanged_reuse():
            # The production failure: reuse points to the already-saved packet.
            # A duplicate version remains forbidden so review budgets cannot reset.
            f.rejects(lambda:claim_design.save(target,f.ACTOR,dict(action='save',request_id=uid(),supersedes_id=selected['id'],document=value,reason='Identical duplicate must stay forbidden')))
            for role in ('anon','authenticated'):
                assert f.query("select has_function_privilege(current_user,'research_reuse_claim_packet(uuid,uuid,uuid,uuid,uuid)','EXECUTE')",role=role)=='f'
            run_id=uid()
            f.rpc('research_begin_idea_run',dict(p_study=target,p_actor=f.ACTOR,p_user='fixture@example.invalid',p_id=run_id,p_packet=selected['id'],p_task='planning',p_session=uid(),p_prompt=prompt,p_model='synthetic-test-provider',p_request=dict(task='planning',test='unchanged-reuse'),p_provenance=dict(packet_sha256=selected['sha256'])))
            output=dict(response_version=claim_design.RESPONSE_VERSION,response_mode='reuse',summary='Synthetic reuse fixture only',questions=[],proposal=value,decision_policy=dict(claim_design.POLICY_IDENTITY,origin='server-policy',model_authored=False,protocol_reused=True))
            f.rpc('research_finish_idea_run',dict(p_study=target,p_actor=f.ACTOR,p_id=run_id,p_status='complete',p_reason=None,p_raw=f.workflow.canonical(output).decode(),p_output=output,p_usage=None,p_provenance=dict(data_origin='software-fixture'),p_messages=[]))
            request=dict(action='adopt',request_id=uid(),run_id=run_id,packet_id=selected['id'])
            reuse_request.update(request)
            before=f.query('select count(*) from research_idea_packets where study_id='+f.sql_text(target))
            answer=claim_design.adopt(target,f.ACTOR,request)
            assert answer['id']==selected['id'] and answer['adoption']['new_packet_created'] is False
            assert claim_design.adopt(target,f.ACTOR,request)==answer
            assert f.query('select count(*) from research_idea_packets where study_id='+f.sql_text(target))==before
            assert f.query("select count(*) from research_audit_events where study_id="+f.sql_text(target)+" and action='claim:reuse-packet'")=='1'
            assert not f.ideas.status(target)['ready']
            f.rejects(lambda:f.rpc('research_reuse_claim_packet',dict(p_study=target,p_actor=f.OTHER,p_id=uid(),p_packet=selected['id'],p_run=run_id)))
            f.rejects(lambda:f.rpc('research_reuse_claim_packet',dict(p_study=target,p_actor=f.ACTOR,p_id=request['request_id'],p_packet=selected['id'],p_run=uid())))
            return dict(identical_version_still_rejected=True,reuse_audited_once=True,new_packets=0,readiness_remains_false=True,browser_rpc_denied=True)
        f.check('unchanged reuse is audited without creating a packet or resetting review limits',unchanged_reuse)
        runs=[]
        for task in ('comprehension','critic'):
            run=f.rpc('research_begin_idea_run',dict(p_study=target,p_actor=f.ACTOR,p_user='fixture@example.invalid',p_id=uid(),p_packet=selected['id'],p_task=task,p_session=None,p_prompt=prompt,p_model='synthetic-test-provider',p_request=dict(task=task),p_provenance=dict(packet_sha256=selected['sha256'],context_policy='fresh-packet-only',history_messages=0)))
            output=dict(summary='Synthetic contract test only',questions=[],findings=[],verdict='ready')
            f.rpc('research_finish_idea_run',dict(p_study=target,p_actor=f.ACTOR,p_id=run['id'],p_status='complete',p_reason=None,p_raw=f.workflow.canonical(output).decode(),p_output=output,p_usage=dict(tokens=None,measured_charges_usd=None),p_provenance=dict(data_origin='model-output'),p_messages=None));runs.append(run)
        s=f.store.rows('studies',{'id':'eq.'+target})[0]
        prepare=dict(action='prepare-campaign',request_id=uid(),packet_id=selected['id'],title='Scoped software fixture campaign',stage='pilot',claim_type='numerical',experiment_type='independent-check',planned_units=1)
        f.rejects(lambda:f.ideas.prepare_campaign(s,f.ACTOR,prepare,retained=retained))
        f.ideas.accept(target,f.ACTOR,dict(action='accept',request_id=uid(),packet_id=selected['id'],comprehension_run_id=runs[0]['id'],critic_run_id=runs[1]['id'],reason='Synthetic owner acceptance only'))
        prepared=f.ideas.prepare_campaign(s,f.ACTOR,prepare,retained=retained)
        def queue():
            job=f.scheduler.enqueue(target,f.ACTOR,prepared['queue_request'])['job']
            assert job['status']=='manual'
            assert f.scheduler.enqueue(target,f.ACTOR,prepared['queue_request'])['job']['id']==job['id']
            assert f.ideas.resume_campaign(s,f.ACTOR,dict(action='resume-campaign',prepared_id=prepared['link']['id']),retained=retained)['queue_request']==prepared['queue_request']
            assert f.query('select count(*) from research_sources where study_id='+f.sql_text(target)+" and kind='unpublished-proposal'")=='0'
            assert f.query('select count(*) from research_measurements')=='0'
            return dict(job_id=job['id'],execution_mode='manual',source='Original paper-shaped fixture preserved',measurements_created=0)
        f.check('reviewed paper plan freezes and queues idempotently without fabricating results',queue)
        f.rejects(lambda:f.ideas.prepare_campaign(s,f.ACTOR,dict(prepare,request_id=uid(),stage='main'),retained=retained))
        revised=claim_design.save(target,f.ACTOR,dict(action='save',request_id=uid(),supersedes_id=selected['id'],document=dict(value,conditions=value['conditions']+' Revised scope.'),reason='Material scope revision'))
        assert not f.ideas.status(target)['ready']
        f.rejects(lambda:f.scheduler.enqueue(target,f.ACTOR,dict(prepared['queue_request'],request_id=uid())))
        # A new adoption of an obsolete packet fails. Replaying its already
        # audited request remains idempotent and cannot restore readiness.
        f.rejects(lambda:f.rpc('research_reuse_claim_packet',dict(p_study=target,p_actor=f.ACTOR,p_id=uid(),p_packet=selected['id'],p_run=reuse_request['run_id'])))
        replay=f.rpc('research_reuse_claim_packet',dict(p_study=target,p_actor=f.ACTOR,p_id=reuse_request['request_id'],p_packet=selected['id'],p_run=reuse_request['run_id']))
        assert replay['id']==selected['id'] and f.ideas.status(target)['current_packet_id']==revised['id']
        assert not f.ideas.status(target)['ready']
        f.check('material revisions invalidate readiness and block new queue work',lambda:dict(version=revised['version'],ready=False))
        f.report['passed']=True
    except Exception as error:
        f.report.update(passed=False,error=str(error));f.traceback.print_exc()
    finally:
        f.report['ended_at']=f.dt.datetime.now(f.dt.timezone.utc).isoformat()
        (f.DIRECTORY/'claim-design-validation-report.json').write_text(json.dumps(f.report,indent=2)+'\n')
        print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report['passed'])))
    if not f.report['passed']:sys.exit(1)

if __name__=='__main__':main()
