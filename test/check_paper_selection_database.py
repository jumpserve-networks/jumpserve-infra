"""Actual isolated SQL/controller: synthetic 184-statement organization/selection."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
import sys
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy, autonomy_model as model, paper_uploads, store, workflow
import autonomy_fixtures as fixture

def main():
 f.report.update(protocol='paper-review-selection-development-v1',synthetic_auth=True,synthetic_provider=True,synthetic_storage=True,actual_postgres=True,new_model_calls=0,new_cloud_experiments=0)
 try:
  f.bootstrap();sys.path.insert(0,str(f.ROOT/'.runtime-autonomy-python/python'))
  f.rpc('publish_agent_prompt',fixture.publish_fixture())
  raw=fixture.pdf_bytes();study=f.uid();initial=dict(action='reserve',request_id=study,filename='Selection software fixture.pdf',sha256=workflow.digest(raw),byte_count=len(raw))
  os.environ['RESEARCH_AUTONOMY_ENABLED']='true'
  with patch.object(autonomy,'wake',return_value=dict(status='deferred')),patch.object(fixture.preparation,'registered',side_effect=fixture.registered),patch.object(model,'invoke',side_effect=fixture.provider):
   paper_uploads.submit(f.ACTOR,initial);f.transport('/storage/v1/object/'+paper_uploads.BUCKET+'/'+study+'/'+initial['sha256'],'POST',raw)
   paper_uploads.submit(f.ACTOR,dict(action='prepare',request_id=study))
   initial_limits=store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
   task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
   autonomy.step(task)
   task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
   originals=store.rows('claims',dict(study_id='eq.'+study));assert len(originals)==3
   sample=originals[0];extra=[]
   for i in range(181):
    row={key:copy.deepcopy(sample[key]) for key in ['id',*workflow.FIELDS['claims']]};row.update(id=f.uid(),description='Explicit synthetic statement '+str(i+4)+': latency is 10 ms.',location='Synthetic original record '+str(i+4));extra.append(row)
   store.append_bundle(study,f.ACTOR,[dict(kind='claims',record=c) for c in extra]);autonomy.seed(task,extra,{})
   before=store.rows('claims',dict(study_id='eq.'+study));before_hash=workflow.digest(workflow.canonical(before))
   def rejects_invalid_groups():
    current=f.query('select revision from research_paper_reviews where study_id='+f.sql_text(study))
    good=dict(version='paper-review-selection-v1',status='preparing',cursor=8,candidate_count=184,central_claims=[dict(claim_id=before[0]['id'],label='Synthetic contribution')],testable_findings=[])
    for change in [dict(cursor=None),dict(candidate_count=185),dict(central_claims=[dict(claim_id=f.uid(),label='Foreign')]),dict(testable_findings=good['central_claims']),dict(central_claims=[dict(claim_id=before[0]['id'],label=None)])]:
     f.rejects(lambda change=change:f.rpc('research_paper_review',dict(p_operation='organization',p_actor=f.ACTOR,p_study=study,p_payload=dict(task_id=task['id'],token=task['lease_token'],selection=dict(good,**change)))))
    assert current==f.query('select revision from research_paper_reviews where study_id='+f.sql_text(study))
    return dict(invalid_cases=5,review_unchanged=True)
   f.check('organization rejects invalid source identities coverage and overlapping categories atomically',rejects_invalid_groups)
   autonomy.step(task)
   def organize_all():
    for _ in range(30):
     r=paper_uploads.submit(f.ACTOR,dict(action='review',request_id=study))
     if r['status']=='ready':break
     item=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
     assert item and item['study_id']==study
     autonomy.step(item)
    assert r['status']=='ready',r
    assert r['organization']['cursor']==184 and r['organization']['candidate_count']==184
    assert len(r['organization']['central_claims'])==1 and len(r['organization']['testable_findings'])==15
    turns=store.rows('autonomy_turns',dict(study_id='eq.'+study));group_turns=[t for t in turns if json.loads(t['request_raw'])['messages'][0]['content'][0]['text'].find('paper-review-selection')>=0]
    assert len(group_turns)==23 and all(t['status']=='complete' and t['raw_response'] for t in group_turns)
    assert all(len(t['request_raw'].encode())<=96000 for t in group_turns)
    assert f.query('select count(*) from research_autonomy_tasks where study_id='+f.sql_text(study)+' and claim_id is not null')=='0'
    assert workflow.digest(workflow.canonical(store.rows('claims',dict(study_id='eq.'+study))))==before_hash
    return dict(retained_candidates=184,central_suggestions=1,finding_suggestions=15,organization_turns=23,raw_prompts_and_answers_saved=True,original_claims_unchanged=True)
   f.check('all 184 candidates are organized in bounded recorded turns without starting experiments',organize_all)
   r=paper_uploads.submit(f.ACTOR,dict(action='review',request_id=study))
   def owner_backfill():
    f.rejects(lambda:paper_uploads.submit(f.OTHER,dict(action='organize',request_id=study)))
    first=paper_uploads.submit(f.ACTOR,dict(action='organize',request_id=study));second=paper_uploads.submit(f.ACTOR,dict(action='organize',request_id=study))
    assert first['status']=='preparing' and first['organization']['cursor']==0
    assert first['revision']==second['revision']
    w=store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
    assert w['max_spend_cents']==initial_limits['max_spend_cents'] and w['deadline_at']==initial_limits['deadline_at']
    # The backfill admission is tested; restore readiness through the actual
    # organization controller rather than modifying the retained review by SQL.
    for _ in range(30):
     value=paper_uploads.submit(f.ACTOR,dict(action='review',request_id=study))
     if value['status']=='ready':break
     item=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}));assert item;autonomy.step(item)
    assert value['status']=='ready'
    return dict(owner_only=True,duplicate_request_idempotent=True,budget_and_deadline_preserved=True)
   f.check('existing unconfirmed inventories can be organized without resetting authorization',owner_backfill)
   r=paper_uploads.submit(f.ACTOR,dict(action='review',request_id=study))
   chosen=[r['claims'][0]['id'],r['claims'][-1]['id']]
   payload=dict(action='confirm',request_id=study,title='Owner selected original statements',domain='Software verification',claim_ids=chosen,revision=r['revision'],selection=dict(central_claims=chosen[:1],testable_findings=chosen[1:]))
   def confirmation():
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(payload,selection=dict(central_claims=chosen,testable_findings=chosen[:1]))))
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(payload,claim_ids=[f.uid()])))
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:paper_uploads.submit(f.ACTOR,payload),range(3)))
    assert all(v['status']=='confirmed' and v['confirmation']['selection']==payload['selection'] for v in results)
    assert f.query('select count(*) from research_autonomy_tasks where study_id='+f.sql_text(study)+' and claim_id is not null')=='2'
    assert workflow.digest(workflow.canonical(store.rows('claims',dict(study_id='eq.'+study))))==before_hash
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(payload,selection=dict(central_claims=chosen[1:],testable_findings=chosen[:1]))))
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(action='organize',request_id=study)))
    return dict(parallel_confirmations=3,selected_tasks=2,retained_candidates=184,owner_categories_persisted=True,confirmed_review_cannot_be_reorganized=True)
   f.check('grouped confirmation saves exactly the chosen identities and remains idempotent',confirmation)
   def security():
    for role in ('anon','authenticated'):
     assert f.query("select has_function_privilege(current_user,'research_paper_review(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
     for table in ('research_paper_reviews','research_paper_review_events'):
      assert f.query('select has_table_privilege(current_user,'+f.sql_text(table)+",'SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
    events=f.query('select count(*) from research_paper_review_events where study_id='+f.sql_text(study));assert int(events)>46
    return dict(browser_sql_access=False,versioned_review_events=int(events))
   f.check('private review history and SQL browser-write denial remain intact',security)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error));raise
 finally:
  f.report['ended_at']=workflow.now();(f.DIRECTORY/'paper-selection-validation-report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'),checks=len(f.report['checks']))))

if __name__=='__main__':main()
