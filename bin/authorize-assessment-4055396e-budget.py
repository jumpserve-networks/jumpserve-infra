"""Record the explicit $1000 authorization, pending a compatible release.

This fixed-target command cannot apply migrations, change effective limits,
resume a task, start an experiment or call a model.
"""
import datetime as dt,importlib.util,json,pathlib,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
STUDY='4055396e-35c0-4962-ba39-cf23e443ad8d';REQUEST=str(uuid.uuid5(uuid.UUID(STUDY),'operator-budget-authorization-1000-20261028'))
def main():
 target=r.target();out=ROOT/'.test-artifacts/assessment-4055396e-budget'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
 sql='select to_jsonb(w) record from research_autonomy_workflows w where study_id='+r.admin.literal(STUDY)+'::uuid';before=r.admin.query(sql)[0]['record']
 details=dict(version='assessment-budget-authorization-v1',max_spend_cents=100000,scope='This assessment only; $100 new-assessment default unchanged.',authorization='User instruction: Let us fix those problems and also increase the budget to $1000.',authorized_by='Lab operator via Codex conversation, 2026-10-28',state='authorized-pending-compatible-release',effective_max_spend_cents_at_authorization=before['max_spend_cents'],deadline_at=before['deadline_at'],committed_cents=before['committed_cents'],initial_sha256=before['initial_sha256'],reason='Release compatible frontend and corrected backend before applying the audited budget-amendment RPC and separately reconciling any stopped tasks. Do not spend additional funds on the unchanged stopped workflow.')
 literal=r.admin.literal(json.dumps(details,sort_keys=True,separators=(',',':')))
 r.admin.query('insert into research_autonomy_events(id,study_id,event,details) values('+r.admin.literal(REQUEST)+'::uuid,'+r.admin.literal(STUDY)+"::uuid,'budget-increase-authorized',"+literal+'::jsonb) on conflict(id) do nothing',read_only=False)
 retained=r.admin.query('select study_id,event,details from research_autonomy_events where id='+r.admin.literal(REQUEST)+'::uuid')[0]
 assert retained['study_id']==STUDY and retained['event']=='budget-increase-authorized' and retained['details']['max_spend_cents']==100000 and retained['details']['initial_sha256']==before['initial_sha256']
 after=r.admin.query(sql)[0]['record'];assert after==before,'Authorization must not change workflow state or effective limits.'
 report=dict(target=target,request_id=REQUEST,state=details['state'],assessment=STUDY,authorized_maximum_usd=1000,effective_maximum_usd=after['max_spend_cents']/100,workflow_unchanged=True,retained=retained,new_model_calls=0,new_experiments=0)
 (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(out),**report)))
if __name__=='__main__':main()
