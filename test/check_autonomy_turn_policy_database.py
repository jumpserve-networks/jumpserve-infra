"""Actual local upgrade/admission checks; synthetic turns, no provider calls."""
import copy,hashlib,json,traceback
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy,autonomy_model as model,autonomy_fixtures as fixture,workflow

MIGRATION='202610200008_remove_autonomy_turn_cap.sql'

def main():
 f.report.update(protocol='autonomy-turn-policy-v1',real_model_calls=0,cloud_instances=0,
  design='Exposed synthetic upgrade regression against actual local PostgreSQL and controller RPCs; no scientific or held-out model validation.')
 try:
  f.bootstrap(apply_turn_policy=False)
  for name in ('202610200003_runtime_pilot_audit.sql','202610200005_subscription_pilot.sql'):
   raw=(f.ROOT/'database'/name).read_bytes();f.report['migration_sha256'][name]=hashlib.sha256(raw).hexdigest();f.query(raw.decode())
  publication=fixture.publish_fixture();f.rpc('publish_agent_prompt',publication)
  def lease():return f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
  def begin(t):
   request=model.request('Synthetic local upgrade fixture',dict(task='discover'))
   return autonomy.control(t,'begin',dict(id=f.uid(),request=request,request_raw=workflow.canonical(request).decode(),request_sha256=workflow.digest(workflow.canonical(request)),reserved_cents=1,prompt_version_id=publication['p_version_id'],model_id=model.MODEL))
  cases={}
  def old_campaigns():
   for name in ('eligible','budget','deadline','cancelled','unknown','blocked','completed'):
    study=f.uid();paper=workflow.paper_details(dict(title='Synthetic '+name+' turn-policy upgrade',paper_url=fixture.URL,domain='Software verification',scope='Synthetic policy admission only',study_kind='paper'))
    payload=autonomy.start_payload(study,paper);initial=json.loads(payload['initial_prompt']);initial['defaults']['attempts_per_claim']=25
    payload['initial_prompt']=workflow.canonical(initial).decode()
    f.rpc('research_autonomy_control',dict(p_operation='start',p_actor=f.ACTOR,p_study=study,p_payload=payload))
    task=lease();assert task['study_id']==study
    for i in range(25):
     turn=begin(task);assert turn['number']==i+1
     autonomy.control(task,'finish',dict(id=turn['id'],status='unknown' if name=='unknown' and i==24 else 'invalid-output',raw_response=None if name=='unknown' and i==24 else '{}',output=None,usage={},estimated_cents=None,reason='Explicit synthetic upgrade fixture, no model request'))
    assert begin(task)==dict(denied='attempt-limit')
    autonomy.advance(task,'blocked' if name=='blocked' else 'attempt-limit',reason='Synthetic retained historical stop')
    if name=='budget':f.query('update research_autonomy_workflows set committed_cents=10000 where study_id='+f.sql_text(study))
    if name=='deadline':f.query("alter table research_autonomy_workflows disable trigger research_autonomy_workflow_immutable; update research_autonomy_workflows set created_at=clock_timestamp()-interval '8 days',deadline_at=clock_timestamp()-interval '1 day' where study_id="+f.sql_text(study)+"; alter table research_autonomy_workflows enable trigger research_autonomy_workflow_immutable")
    if name in ('cancelled','completed'):f.query('update research_autonomy_workflows set status='+f.sql_text(name)+' where study_id='+f.sql_text(study))
    before=f.store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0]
    turns=f.store.rows('autonomy_turns',dict(study_id='eq.'+study,order='number.asc',limit=100))
    cases[name]=dict(study=study,task=task,paper=paper,before=before,turns=turns)
   return dict(campaigns=len(cases),numbered_synthetic_turns=175,legacy_26th_admission_denied=True,real_model_calls=0)
  f.check('retain real legacy admission records before changing policy',old_campaigns)
  audit_ids={}
  def audit_turn(relation,number):
   raw=workflow.canonical(dict(synthetic_turn=number));sha=workflow.digest(raw);blob="decode('"+raw.hex()+"','hex')"
   base='id,pilot_id,number,request_raw,request_sha256,status,reserved_cents'
   values=[f.sql_text(f.uid()),f.sql_text(audit_ids[relation]),str(number),blob,f.sql_text(sha),f.sql_text('failed'),'1']
   if relation=='research_runtime_pilot_calls':base+=',arm,logical_request_sha256';values.extend([f.sql_text('openclaw-runtime'),f.sql_text(sha)])
   else:base+=',logical_raw,logical_sha256,transport_raw,transport_sha256';values.extend([blob,f.sql_text(sha),blob,f.sql_text(sha)])
   f.query('insert into '+relation+'('+base+') values('+','.join(values)+')',role='service_role')
  def audit_setup():
   raw=b'{"scope":"synthetic future-campaign audit"}';blob="decode('"+raw.hex()+"','hex')";sha=f.sql_text(workflow.digest(raw))
   runtime=f.uid();subscription=f.uid();audit_ids.update(research_runtime_pilot_calls=runtime,research_subscription_calls=subscription)
   f.query("insert into research_runtime_pilots(id,protocol_raw,protocol_sha256,configuration,status,maximum_cents,overhead_cents) values("+f.sql_text(runtime)+','+blob+','+sha+",'{}','prepared',10000,0)",role='service_role')
   f.query("insert into research_subscription_pilots(id,study_id,protocol_raw,protocol_sha256,configuration,prior_committed_cents,overhead_cents,maximum_cents,status) values("+f.sql_text(subscription)+','+f.sql_text(cases['eligible']['study'])+','+blob+','+sha+",'{}',0,0,10000,'prepared')",role='service_role')
   for relation in audit_ids:
    audit_turn(relation,25);f.rejects(lambda:audit_turn(relation,26))
   return dict(private_audit_relations=2,legacy_26th_row_denied=True,actual_provider_calls=0)
  f.check('retain original private audit ceiling as the pre-upgrade control',audit_setup)
  def migration():
   raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.report['migration_sha256'][MIGRATION]=hashlib.sha256(raw).hexdigest();f.query(raw.decode())
   for case in cases.values():
    w=f.store.rows('autonomy_workflows',dict(study_id='eq.'+case['study']))[0];assert w['max_attempts'] is None
    for key in ('initial_prompt','initial_sha256','created_at','deadline_at','committed_cents','max_spend_cents','status'):assert w[key]==case['before'][key],key
    assert f.store.rows('autonomy_turns',dict(study_id='eq.'+case['study'],order='number.asc',limit=100))==case['turns']
    assert f.query("select status from research_autonomy_tasks where id="+f.sql_text(case['task']['id']))==('blocked' if case is cases['blocked'] else 'attempt-limit')
    event=json.loads(f.query("select details from research_autonomy_events where event='turn-policy-changed' and study_id="+f.sql_text(case['study'])))
    assert event['previous_max_attempts']==25 and event['max_attempts'] is None
   return dict(original_prompts_turns_costs_deadlines_unchanged=True,policy_change_audited=True,migration_does_not_dispatch=True)
  f.check('upgrade removes ceilings with immutable audit and no automatic dispatch',migration)
  def audit_upgrade():
   for relation in audit_ids:
    audit_turn(relation,26);f.rejects(lambda:audit_turn(relation,0))
    assert f.query('select count(*) from '+relation)=="2"
    for role in ('anon','authenticated'):assert f.query("select has_table_privilege(current_user,"+f.sql_text(relation)+",'SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
   return dict(number_26_stored=True,zero_rejected=True,browser_access_denied=True,frozen_pilot_protocols_not_modified=True)
  f.check('private audit storage accepts future turn numbers while retaining security',audit_upgrade)
  def recovery():
   f.rejects(lambda:f.rpc('research_autonomy_resume_turns',dict(p_policy='unreviewed-policy')))
   resumed=f.rpc('research_autonomy_resume_turns',dict(p_policy=model.TURN_POLICY['version']))
   assert resumed==[dict(task_id=cases['eligible']['task']['id'],status='queued',attempts=25)],resumed
   assert f.rpc('research_autonomy_resume_turns',dict(p_policy=model.TURN_POLICY['version']))==[]
   for name,case in cases.items():
    if name!='eligible':assert f.query('select status from research_autonomy_tasks where id='+f.sql_text(case['task']['id']))==('blocked' if name=='blocked' else 'attempt-limit')
   task=lease();assert task['id']==cases['eligible']['task']['id'] and task['attempts']==25
   turn=begin(task);assert turn['number']==26
   autonomy.control(task,'finish',dict(id=turn['id'],status='invalid-output',raw_response='{}',output=None,usage={},estimated_cents=None,reason='Synthetic 26th turn, no provider request'))
   autonomy.advance(task,'blocked',reason='Synthetic upgrade check finished')
   history=autonomy.history(task['study_id'],task['id'],27);assert history['turns'][0]['number']==26 and history['coverage']['total']==26
   f.rejects(lambda:f.query("update research_autonomy_turns set request_raw='{}' where id="+f.sql_text(cases['eligible']['turns'][0]['id'])))
   return dict(resumed_once=True,next_number=26,blocked_unknown_cancelled_completed_budget_deadline_not_resumed=True,history_verified=True)
  f.check('eligible cap stops resume once with original numbering and uncertainty gates',recovery)
  def replay_security():
   case=cases['eligible'];payload=autonomy.start_payload(case['study'],case['paper'])
   result=f.rpc('research_autonomy_control',dict(p_operation='start',p_actor=f.ACTOR,p_study=case['study'],p_payload=payload))
   assert result['autonomy']['initial_prompt']==case['before']['initial_prompt']
   changed=copy.deepcopy(payload);initial=json.loads(changed['initial_prompt']);initial['paper']['title']='Different paper';changed['initial_prompt']=workflow.canonical(initial).decode()
   f.rejects(lambda:f.rpc('research_autonomy_control',dict(p_operation='start',p_actor=f.ACTOR,p_study=case['study'],p_payload=changed)))
   for role in ('anon','authenticated'):
    assert f.query("select has_function_privilege(current_user,'research_autonomy_resume_turns(text)','EXECUTE')",role=role)=='f'
    assert f.query("select has_table_privilege(current_user,'research_autonomy_turns','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
   f.rejects(lambda:f.query('update research_autonomy_workflows set max_attempts=25 where study_id='+f.sql_text(case['study'])))
   # Fresh intake also stores the explicit unlimited default.
   with patch.object(autonomy,'wake',return_value={}):new=autonomy.start(f.ACTOR,dict(request_id=f.uid(),paper=case['paper'],autonomous=True))
   assert new['autonomy']['max_attempts'] is None
   return dict(same_request_replay_preserves_original=True,altered_source_rejected=True,browser_access_denied=True,ceiling_cannot_be_reinstated=True,new_intake_unlimited=True)
  f.check('legacy replay new defaults ownership RLS and immutable history remain correct',replay_security)
  f.report['passed']=True
 except Exception as error:
  f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  path=f.DIRECTORY/'turn-policy-validation-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'))))

if __name__=='__main__':main()
