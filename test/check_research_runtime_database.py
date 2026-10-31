"""Actual production-proof and resumption guards in isolated PostgreSQL."""
import json
from unittest.mock import patch
import check_research_controller_health_database as previous
import check_research_ideas_database as f
import workflow,autonomy
MIGRATION='202610310005_research_runtime_recovery.sql'
def main():
 previous.main();f.report.update(protocol='research-controller-recovery-v1',passed=False)
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 q=f.sql_text
 def js(sql,role=None):return json.loads(f.query(sql,role=role))
 f.query('select public.autonomy_budget_sync_assessments()')
 seed=js('select to_jsonb(c) from research_claims c limit 1')
 with patch.object(autonomy,'wake',return_value={}):
  study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Runtime recovery software fixture',paper_url='https://example.org/recovery-fixture.pdf',domain='Software',scope=__doc__)))['id']
 source=f.uid()
 f.query('insert into research_sources select (jsonb_populate_record(null::research_sources,to_jsonb(s)||'+f.sql_json(dict(id=source,study_id=study))+')).* from research_sources s where id='+q(seed['source_id']))
 platform=f.query('select id from platform_tasks limit 1');release,pin=f.uid(),f.uid();binding='e'*64
 proof=dict(passed=True,revision='a'*40,component='research-runtime',pin_revision='b'*40,source_binding=binding,all_other_template_content_preserved=True,scientific_and_request_content_unchanged=True,existing_tests_unchanged=True)
 f.query('insert into platform_releases(id,task_id,component,repository,revision,status,verification) values('+','.join([q(release),q(platform),q('research-runtime'),q('jumpserve-networks/jumpserve-back-end'),q('a'*40),q('verified'),f.sql_json(proof)])+')')
 def resume(role='service_role'):return js('select public.research_runtime_resume('+q(release)+')',role)
 def task(reason='A UUID identifier is required.'):
  claim,ident=f.uid(),f.uid()
  f.query('insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) select '+','.join([q(claim),q(study),q(source)])+',location,description,claim_type,scope,metrics,priority from research_claims where id='+q(seed['id']))
  f.query('insert into research_autonomy_tasks(id,study_id,claim_id,stage,status,label,attempts,context,reason) values('+','.join([q(ident),q(study),q(claim),q('planning'),q('blocked'),q('inconclusive'),'3',f.sql_json(dict(frozen='retained')),q(reason)])+')')
  return ident
 target=task()
 def access():
  for role in ('anon','authenticated'):f.rejects(lambda:f.query('select public.research_runtime_resume('+q(release)+')',role=role))
  f.rejects(resume)
  f.query('insert into platform_releases(id,task_id,component,repository,revision,status,verification) values('+','.join([q(pin),q(platform),q('research-runtime-pin'),q('jumpserve-networks/jumpserve-infra'),q('b'*40),q('verified'),f.sql_json(dict(source_binding=binding))])+')')
  return dict(service_only=True,verified_pin_required=True)
 f.check('resumption requires actual verified production and matching versioned pin',access)
 unknown=task('Worker lease expired; reconcile retained provider/experiment identity before more work.');unrelated=task('Unreviewed scientific or external blocker')
 prompt=f.query("select active_version_id from agent_prompt_settings where module_id='research-autonomy'")
 f.query('insert into research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,status,reserved_cents,reason) values('+','.join([q(f.uid()),q(study),q(unknown),'1',q('planning'),q(prompt),q('gpt-6.1-sol'),"'{}'::jsonb",q('{}'),q(workflow.digest(b'{}')),q('unknown'),'100',q('Original incomplete call remains unknown')])+')')
 def safety():
  f.query('update platform_settings set paused=true where id');assert resume()['resumed_task_ids']==[]
  f.query('update platform_settings set paused=false where id')
  before=js('select to_jsonb(t) from research_autonomy_tasks t where id='+q(target))
  result=resume();assert target in result['resumed_task_ids'] and unknown not in result['resumed_task_ids'] and unrelated not in result['resumed_task_ids']
  after=js('select to_jsonb(t) from research_autonomy_tasks t where id='+q(target))
  for key in ('id','study_id','claim_id','stage','label','attempts','context','created_at'):assert after[key]==before[key],key
  f.query("update research_autonomy_tasks set status='blocked',reason='A UUID identifier is required.' where id="+q(target))
  assert target not in resume()['resumed_task_ids']
  assert f.query('select status from research_autonomy_turns where task_id='+q(unknown))=='unknown'
  return dict(originals_retained=True,once_per_binding=True,unknown_fenced=True,unrelated_blockers_unchanged=True)
 f.check('qualified resumption preserves originals and never replays unknown calls or relabels findings',safety)
 def limits():
  ident=task()
  f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(study));assert ident not in resume()['resumed_task_ids']
  f.query("update research_autonomy_workflows set status='running' where study_id="+q(study))
  f.query("update autonomy_budget_categories set max_model_calls=0,change_reason='Explicit synthetic recovery fence' where category='research_assessment'");assert ident not in resume()['resumed_task_ids']
  return dict(cancellation=True,current_category_limits=True)
 f.check('release cannot bypass cancellation or current category budgets',limits)
 f.report['passed']=True;path=f.DIRECTORY/'research-runtime-recovery-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),production_mutations=0,provider_calls=0)))
if __name__=='__main__':main()
