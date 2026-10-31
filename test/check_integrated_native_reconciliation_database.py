"""Native reconciliation after deployed category and maintenance wrappers."""
import json
import check_runtime_handoff_database as previous
import check_research_ideas_database as f
import workflow

MIGRATION='202610300002_native_call_reconciliation.sql'

def main():
 previous.main();f.report.update(protocol='integrated-native-reconciliation-v1',passed=False)
 signatures=['public.research_builder_call(text,jsonb)','public.research_autonomy_repair(text,uuid,uuid,uuid,jsonb)','public.research_model_reconcile(uuid,uuid,text,jsonb)','public.research_autonomy_set_budget(uuid,uuid,integer,boolean,text,text)']
 definitions={s:f.query('select pg_get_functiondef('+f.sql_text(s)+'::regprocedure)') for s in signatures}
 def snapshot():
  return f.query("select jsonb_build_object('categories',(select jsonb_agg(to_jsonb(c) order by category) from autonomy_budget_categories c),'workflows',(select jsonb_agg(to_jsonb(w) order by study_id) from research_autonomy_workflows w),'claims',(select jsonb_agg(to_jsonb(c) order by id) from research_claims c))")
 before=snapshot();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 def retained():
  assert snapshot()==before
  for signature,definition in definitions.items():
   current=f.query('select pg_get_functiondef('+f.sql_text(signature)+'::regprocedure)')
   assert 'public.research_builder_unresolved(t.id)' in current
   assert current!=definition
  for role in ('anon','authenticated'):
   f.rejects(lambda role=role:f.query('select * from public.research_builder_call_reconciliations',role=role))
   assert f.query("select has_function_privilege(current_user,'public.research_builder_call_reconcile(uuid,uuid,text,jsonb)','EXECUTE')",role=role)=='f'
  return dict(current_wrappers_preserved=True,categories_claims_and_workflows_unchanged=True,browser_access_denied=True,production_mutations=0,provider_calls=0)
 f.check('native migration applies after current wrappers without altering budgets or scientific state',retained)
 f.report['passed']=True;path=f.DIRECTORY/'integrated-native-reconciliation-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,report=str(path),checks=len(f.report['checks']))))

if __name__=='__main__':main()
