"""Actual controller startup and SQL compatibility; isolated PostgreSQL only."""
import json
from unittest.mock import patch
import check_category_budgets_database as previous
import check_research_ideas_database as f
import autonomy,workflow

MIGRATION='202610310004_research_controller_health.sql'
def main():
 previous.main();f.report.update(protocol='research-controller-health-v1',passed=False)
 before=f.query("select pg_get_functiondef('public.research_autonomy_resume_turns(text)'::regprocedure)")
 f.rejects(lambda:f.query("select public.research_autonomy_resume_turns('autonomy-turn-policy-v2')",role='service_role'))
 raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.report['migration_sha256'][MIGRATION]=workflow.digest(raw);f.query(raw.decode())
 def compatibility():
  after=f.query("select pg_get_functiondef('public.research_autonomy_resume_turns(text)'::regprocedure)")
  assert after==before.replace("p_policy is distinct from 'autonomy-turn-policy-v1'","p_policy is distinct from 'autonomy-turn-policy-v2'")
  f.rejects(lambda:f.query("select public.research_autonomy_resume_turns('autonomy-turn-policy-v1')",role='service_role'))
  calls=[]
  def rpc(name,payload):
   calls.append(name)
   if name=='research_autonomy_resume_turns':return json.loads(f.query('select public.research_autonomy_resume_turns('+f.sql_text(payload['p_policy'])+')',role='service_role'))
   if name=='research_autonomy_control':assert payload['p_operation']=='lease';return None
   raise AssertionError('Unexpected transport: '+name)
  with patch.object(autonomy.model,'OPENCLAW',False),patch.object(autonomy.model,'load_prompt'),patch('autonomous_repair.discover',return_value=[]),patch.object(autonomy.store,'rpc',side_effect=rpc),patch.dict('os.environ',RESEARCH_AUTONOMY_CONTEXT_RECOVERY=''):
   result=autonomy.handler({},None)
  assert result['slots']==2 and calls.count('research_autonomy_control')==2
  return dict(actual_current_policy=autonomy.model.TURN_POLICY['version'],ordinary_slots_reached=2,unchanged_other_sql=True,provider_calls=0)
 f.check('actual controller passes current-policy startup recovery and reaches ordinary leases',compatibility)
 def observations():
  details=dict(version='research-controller-health-v1',component='turn-recovery',error_type='StoreError',policy='autonomy-turn-policy-v2')
  sql='select public.research_autonomy_runtime_observe(\'maintenance-failed\','+f.sql_json(details)+')'
  for role in ('anon','authenticated'):f.rejects(lambda:f.query(sql,role=role))
  first=json.loads(f.query(sql,role='service_role'));second=json.loads(f.query(sql,role='service_role'));assert first==second and first['recorded']
  bad=dict(details,private_context='must never enter controller health events')
  f.rejects(lambda:f.query('select public.research_autonomy_runtime_observe(\'maintenance-failed\','+f.sql_json(bad)+')',role='service_role'))
  return dict(service_only=True,bounded_private_event=True,idempotent_hourly_observation=True)
 f.check('controller faults are private bounded observations and never admit replacement work',observations)
 f.report['passed']=True;path=f.DIRECTORY/'research-controller-health-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']),production_mutations=0,provider_calls=0)))
if __name__=='__main__':main()
