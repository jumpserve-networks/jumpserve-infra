"""Real isolated PostgreSQL repair transitions; synthetic model/storage transport.

No production writes, provider calls, credentials or cloud experiment launches.
"""
import copy,json,os,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomous_repair as repair,autonomy_model as model,autonomy_fixtures,store,workflow

def main():
 f.report.update(protocol='autonomous-repair-v1',design=__doc__,new_model_calls=0,new_cloud_instances=0)
 try:
  f.bootstrap()
  for name in ('202610280001_data_only_model_window.sql','202610280002_assessment_budget_amendments.sql','202610280003_controller_reconciliation_window.sql','202610280004_autonomous_repair.sql'):
   raw=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=workflow.digest(raw);f.query(raw.decode())
  with patch.object(autonomy,'wake',return_value={}):study=autonomy.start(f.ACTOR,dict(request_id=f.uid(),autonomous=True,paper=dict(title='Explicit repair software fixture',paper_url='https://example.org/repair.pdf',domain='Software development',scope='Synthetic operational recovery, no scientific findings')))['id']
  def lease():return f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  initial=lease();records=autonomy_fixtures.plan()['records'];source=next(r for r in records if r['kind']=='sources');claim=next(r for r in records if r['kind']=='claims')
  store.append_bundle(study,f.ACTOR,[source,claim]);autonomy.seed(initial,[claim['record']],{});autonomy.advance(initial,'finished',reason='Synthetic intake finished.')
  original=json.loads(f.query('select row_to_json(w) from research_autonomy_workflows w'))
  with patch.dict(os.environ,RESEARCH_AUTONOMY_REPAIR_ENABLED='true'):
   task=lease();before=copy.deepcopy(task)
   queued=autonomy.advance(task,'blocked',reason='Required retained shared_campaigns identity is unavailable.')
   assert queued['status']=='queued' and queued['context']['repair_progress']['state']=='diagnosing'
   incident=store.rows('autonomy_repairs',dict(study_id='eq.'+study,limit=1))[0]
   def security():
    for role in ('anon','authenticated'):
     f.rejects(lambda:f.query('select * from research_autonomy_repairs',role=role))
     f.rejects(lambda:f.query("select research_autonomy_repair_candidates()",role=role))
    f.rejects(lambda:f.query("update research_autonomy_repair_events set details='{}'",role='service_role'))
    f.rejects(lambda:f.query("update research_autonomy_repairs set incident_raw='{}'",role='service_role'))
    assert incident['original_context']==before['context'] and incident['original_stage']==before['stage']
    return dict(browser_reads_and_writes_denied=True,original_snapshot_retained=True,immutable_events=True)
   f.check('private service-only incidents preserve original contexts and append-only history',security)
   task=lease()
   incident=repair.transition(task,incident,'diagnosing','Preserve an operational diagnosis failure before retry.',dict(latest_failure='Explicit synthetic transient read error'))
   assert incident['revision']==1 and incident['state']=='diagnosing'
   before_drive_commitments=int(f.query('select committed_cents from research_autonomy_workflows'))
   f.rejects(lambda:repair.rpc(dict(task,lease_token=f.uid()),'transition',dict(id=incident['id'],expected_revision=0,state='validating',reason='stale lease',evidence={})))
   with patch.object(model,'load_prompt',return_value=({'id':f.uid()},'Explicit software policy, no provider call.')):
    result=repair.drive(task,lambda _:(_ for _ in ()).throw(AssertionError('Native model should not run for this reference repair')),autonomy.advance)
   def correction():
    assert result['status']=='queued' and result['stage']=='planning' and result['label']=='untested'
    assert result['context']['repair_progress']['state']=='resolved'
    states=json.loads(f.query("select json_agg(state order by revision) from research_autonomy_repair_events"))
    assert states==['diagnosing','diagnosing','validating','resuming','resolved'],states
    assert f.query('select count(*) from research_autonomy_turns')=='0'
    assert f.query('select count(*) from research_queue_jobs')=='0'
    assert f.query('select count(*) from research_artifacts')!='0'
    now=json.loads(f.query('select row_to_json(w) from research_autonomy_workflows w'))
    for key in ('initial_prompt','initial_sha256','max_spend_cents','max_attempts','deadline_at'):assert now[key]==original[key],key
    assert now['committed_cents']==before_drive_commitments and now['committed_cents']>=original['committed_cents']
    return dict(states=states,provider_calls=0,experiments=0,finding='untested',original_authorization_unchanged=True,ordinary_controller_lease_commitments_retained=True)
   f.check('exact context correction validates then resumes without a provider call or outcome rewrite',correction)
   task=lease();autonomy.advance(task,'queued',stage='building',reason='Synthetic instrumentation development.')
   task=lease();task['context']['blockers']=[dict(kind='implementation',detail='An applicable registered implementation is unavailable.',required_input='Write queue instrumentation.')]
   # Persist the ordinary working context before creating its repair snapshot.
   autonomy.advance(task,'queued',context=task['context'],reason='Retain development requirement.');task=lease()
   queued=autonomy.advance(task,'blocked',reason='Required measurement instrumentation has not yet been implemented.')
   task=lease();result=repair.drive(task,lambda _:None,autonomy.advance)
   def native():
    assert result['stage']=='building' and result['context']['repair_progress']['state']=='repairing'
    assert result['context']['repair_directive']==repair.REPAIR_INSTRUCTION
    assert 'run a concrete development check' in result['context']['repair_packet']['command']
    assert result['attempts']==0 and result['label']=='untested'
    return dict(native_repair_prepared=True,original_claim_retained=True,scientific_readiness=False,actual_native_call=False)
   f.check('missing implementation receives a targeted native repair packet under the same claim',native)
   task=lease();record=store.rows('autonomy_repairs',dict(study_id='eq.'+study,state='eq.repairing',limit=1))[0]
   def fences():
    f.rejects(lambda:repair.transition(task,dict(record,revision=record['revision']-1),'validating','stale revision',{}))
    f.rejects(lambda:repair.transition(task,dict(record,revision=None),'validating','missing revision',{}))
    f.rejects(lambda:repair.rpc(dict(task,study_id=f.uid()),'transition',dict(id=record['id'],expected_revision=record['revision'],state='validating',reason='cross-assessment',evidence={})))
    f.rejects(lambda:repair.transition(task,record,'resolved','skip validation',dict(validated=True)))
    f.rejects(lambda:f.query("update research_autonomy_repairs set state='diagnosing',revision=revision+1 where state='resolved'"))
    f.query('update research_autonomy_workflows set committed_cents=max_spend_cents')
    assert repair.rpc(task,'transition',dict(id=record['id'],expected_revision=record['revision'],state='validating',reason='No money',evidence={}))['denied']=='budget'
    assert repair.rpc(task,'adopt',{})['denied'] in ('state','budget')
    return dict(stale_leases_and_revisions_rejected=True,validation_cannot_be_skipped=True,budget_enforced=True,terminal_history_immutable=True)
   f.check('fenced transitions cannot skip validation, overwrite terminal repairs or bypass funding',fences)
  f.report['passed']=True
 except Exception as error:f.report.update(passed=False,error=str(error));traceback.print_exc();raise
 finally:
  f.report['ended_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
  path=f.DIRECTORY/'autonomous-repair-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(report=str(path),passed=f.report.get('passed'),checks=f.report['checks'])))
if __name__=='__main__':main()
