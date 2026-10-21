"""Actual isolated SQL recovery and controller continuation; synthetic provider."""
import copy,hashlib,importlib.util,json,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,worker
import autonomy_fixtures as fixture

ORIGINAL_PLAN=fixture.plan
def partial_plan():
 value=ORIGINAL_PLAN()
 for campaign in value['campaigns']:
  old=campaign['raw_input'].encode();data=json.loads(old);trial=campaign['key'][-1]
  # Each check completely measures one different required synthetic cell. The
  # first clean run is partial claim coverage, matching the production handoff.
  if not data['observed']:data['observed']=[{k:v for k,v in data['published'][0].items() if k not in ('source_id','location','extraction')}]
  for row in data['published']+data['observed']:row['observation_id']+='-trial-'+trial
  raw=fixture.workflow.canonical(data);campaign['raw_input']=raw.decode()
  for source in campaign['protocol']['input_versions']:
   if source.get('sha256')==fixture.workflow.digest(old):source['sha256']=fixture.workflow.digest(raw)
 return value

def main():
 f.report.update(protocol='openclaw-production-amendment-v6',design='Actual local SQL, original/corrected controller and numerical worker; explicit synthetic model/source/Storage/auth. No real model or scientific validation.')
 try:
  f.bootstrap();name='202610210003_partial_assessment_recovery.sql';raw=(f.ROOT/'database'/name).read_bytes();f.query(raw.decode());f.report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest()
  f.rpc('publish_agent_prompt',fixture.publish_fixture())
  oldpath=f.ROOT/'.test-artifacts/openclaw-evaluation/20261021T004429580770Z/inputs/runtime/autonomy.py'
  spec=importlib.util.spec_from_file_location('legacy_partial_database_controller',oldpath);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
  def provider(request):
   result=fixture.provider(request);context=json.loads(request['messages'][-1]['content'][0]['text'])
   if context['task']=='assessment' and not context.get('controller_numeric_check'):
    out=result['output']['message']['content'][0]['toolUse']['input'];out['blockers']=[dict(kind='missing-data',detail='missing-source-data',required_input='Execute the remaining original synthetic check.')]
   return result
  body=dict(request_id=f.uid(),autonomous=True,paper=dict(title='Explicit partial-assessment SQL software fixture',paper_url=fixture.URL,domain='Software',scope='Synthetic cells only; no scientific result',study_kind='paper'))
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,body)['id']
  def tick(controller):
   f.query("update research_autonomy_tasks set next_at=clock_timestamp() where study_id="+f.sql_text(study)+" and status='waiting'")
   with patch.object(autonomy,'step',side_effect=controller),patch.object(fixture,'plan',side_effect=partial_plan),patch.object(fixture.preparation,'registered',side_effect=fixture.registered),patch.object(model,'invoke',side_effect=provider):
    value=autonomy.handler({});worker.handler({})
   assert all(v.get('status')!='unconfirmed' for v in value['outcomes']),value
  def original_pause():
   for _ in range(24):
    tick(old.step);tasks=f.store.rows('autonomy_tasks',dict(study_id='eq.'+study))
    matching=[t for t in tasks if t['stage']=='assessment' and t['status']=='blocked']
    if matching:break
   else:raise AssertionError('Original controller failed to demonstrate partial pause')
   return dict(partial_pauses=len(matching),real_provider_calls=0,original_controller_sha256=hashlib.sha256(oldpath.read_bytes()).hexdigest())
  f.check('original controller pauses on missing results despite retained executable evidence',original_pause)
  task=next(t for t in f.store.rows('autonomy_tasks',dict(study_id='eq.'+study)) if t['stage']=='assessment' and t['status']=='blocked')
  def resume(implementation='continue-retained-checks-v1',task_id=task['id']):
   return json.loads(f.query('select research_autonomy_resume_partial('+','.join([f.sql_text(study)+'::uuid',f.sql_text(task_id)+'::uuid',f.sql_text(implementation)])+')',role='service_role'))
  def gates():
   for role in ('anon','authenticated'):assert f.query("select has_function_privilege(current_user,'research_autonomy_resume_partial(uuid,uuid,text)','EXECUTE')",role=role)=='f'
   f.rejects(lambda:resume('reset-budget'));f.rejects(lambda:resume(task_id=f.uid()))
   equipment=next(t for t in f.store.rows('autonomy_tasks',dict(study_id='eq.'+study)) if t['stage']=='planning' and t['status']=='blocked');f.rejects(lambda:resume(task_id=equipment['id']))
   return dict(browser_rpc_denied=True,wrong_implementation_and_identity_rejected=True,genuine_equipment_pause_not_resumed=True)
  f.check('recovery is service-only and rejects wrong authorization or genuine external pause',gates)
  before=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0];turns=copy.deepcopy(f.store.rows('autonomy_turns',dict(study_id='eq.'+study)))
  def preservation():
   result=resume();assert result['status']=='queued' and not result['replayed'] and result['attempts']==task['attempts']
   now=f.store.rows('autonomy_tasks',dict(study_id='eq.'+study,id='eq.'+task['id']))[0];assert now['context']==task['context'] and now['stage']==task['stage'] and now['label']==task['label'] and now['attempts']==task['attempts']
   after=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
   assert all(after[k]==before[k] for k in ('created_at','deadline_at','committed_cents','max_spend_cents','max_attempts','initial_prompt','initial_sha256'))
   assert f.store.rows('autonomy_turns',dict(study_id='eq.'+study))==turns
   assert resume()['replayed'] is True
   return dict(old_turns_immutable=True,counters_resources_deadline_and_context_preserved=True,remaining_checks=len(result['remaining_check_ids']),audited_idempotent=True)
  f.check('audited recovery preserves original prompts counters resources context and deadline',preservation)
  def continuation():
   # Resume another numerical fixture if the parallel old controller already paused it.
   for t in f.store.rows('autonomy_tasks',dict(study_id='eq.'+study)):
    if t['id']!=task['id'] and t['status']=='blocked' and t['stage']=='assessment':resume(task_id=t['id'])
   for _ in range(32):
    tick(autonomy.step)
    w=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
    if w['status']!='running':break
   tasks=f.store.rows('autonomy_tasks',dict(study_id='eq.'+study));assert sum(t['status']=='resolved' for t in tasks)==2,tasks
   jobs=f.store.rows('queue_jobs',dict(study_id='eq.'+study));assert len(jobs)==4 and len({j['id'] for j in jobs})==4
   assert {t['label'] for t in tasks if t['status']=='resolved'}=={'reproduced','discrepant'}
   assert resume()['replayed'] is True and w['committed_cents']>before['committed_cents'] and w['deadline_at']==before['deadline_at']
   return dict(numerical_fixture_claims_resolved=2,genuine_equipment_claim_still_blocked=True,original_unique_jobs=4,duplicate_executions=0,original_budget_and_deadline=True,real_provider_calls=0)
  f.check('corrected controller completes remaining frozen fixture checks without duplicate execution',continuation)
  f.report['status']='passed'
 except Exception as e:f.report.update(status='failed',error=str(e),traceback=traceback.format_exc());raise
 finally:(f.DIRECTORY/'partial-report.json').write_text(json.dumps(f.report,indent=2)+'\n');print(str(f.DIRECTORY/'partial-report.json'))
if __name__=='__main__':main()
