"""Derive one private, complete assessment input from the declared control snapshot."""
import copy,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];BACKEND=ROOT.parent/'jumpserve-back-end/research_workflow';sys.path.insert(0,str(BACKEND))
import autonomy,autonomy_model as model,preparation,workflow
def main():
 sid='b7bc978d-9a6a-4fc8-97fd-179be9989d24';snapshots=sorted((ROOT/'.test-artifacts/autonomy-positive-control').glob('*/private-parsed-snapshot.json'));sp=next(p for p in reversed(snapshots) if json.loads(p.read_bytes())['autonomy_workflows'][0]['study_id']==sid and 'protocols' in json.loads(p.read_bytes()));data=json.loads(sp.read_bytes())
 task=copy.deepcopy(next(t for t in data['autonomy_tasks'] if t['stage']=='assessment'));task['workflow']=data['autonomy_workflows'][0]
 raw=(BACKEND/'plans/ipv6-archive-v1.json').read_bytes();plan=json.loads(raw);compiled=preparation.compile_plan(plan,raw,dict(id=sid,paper_url=plan['paper_urls'][0]));campaigns={r['campaign_id'] for r in data['claim_checks'] if r['claim_id']==task['claim_id']};available=[j for j in compiled['jobs'] if j['campaign_id'] in campaigns]
 def one(kind,study,key):return next(r for r in data[kind] if r['id']==key)
 def rows(kind,study,**params):
  result=data[kind]
  if params.get('task_id'):result=[r for r in result if r['task_id']==params['task_id'][3:]]
  if params.get('order')=='number.desc':result=sorted(result,key=lambda r:r['number'],reverse=True)
  return result[:params.get('limit',1000)]
 with patch.object(autonomy,'one',side_effect=one),patch.object(autonomy,'rows',side_effect=rows),patch.object(autonomy,'choices',return_value=(compiled,available)):context=autonomy.build_context(task)
 assert workflow.canonical(autonomy.evidence_records(context['measurements']))==workflow.canonical(data['measurements'])
 folder=ROOT/'.test-artifacts/autonomy-evidence';folder.mkdir(exist_ok=True);pilot=folder/('pilot-'+str(len(list(folder.glob('pilot-*.json')))+1)+'.json');sizes={k:len(workflow.canonical(v)) for k,v in context.items()};pilot.write_text(json.dumps(dict(context_bytes=len(workflow.canonical(context)),sizes=sizes,source_sha256=workflow.digest((BACKEND/'autonomy.py').read_bytes()),record_count=192),indent=2)+'\n');print(json.dumps(dict(pilot=str(pilot),context_bytes=len(workflow.canonical(context)),sizes=sizes)),flush=True)
 seed=json.loads((ROOT/'database/seed-autonomy-v6.json').read_bytes());request=model.request(seed['system_prompt']+'\n\n'+seed['research_context'],context)
 p=folder/'inputs-v1.json'
 if p.exists():raise RuntimeError('Frozen evidence input already exists')
 p.write_text(json.dumps(dict(protocol='autonomous-assessment-production-amendment-v10',source_snapshot_sha256=workflow.digest(sp.read_bytes()),source_snapshot=str(sp.relative_to(ROOT)),privacy='Private operational-control identities; original recorded rows retained without numerical changes.',cases=[dict(name='lossless-192-record-assessment',criterion='Assess the same archived run as inconclusive with coverage_complete=false; all 192 original records are reversibly present and one figure cannot close the six-figure claim.',model_context=context)]),indent=2)+'\n');p.chmod(0o600)
 lock=json.loads((ROOT/'test/autonomy-integration-lock-v1.json').read_bytes());updated=dict(protocol='autonomous-assessment-production-amendment-v10',files={n:workflow.digest((BACKEND/n).read_bytes()) for n in lock['files']},prior_builder_input_sha256=lock['files'],inputs_sha256=workflow.digest(p.read_bytes()),source_snapshot_sha256=workflow.digest(sp.read_bytes()),record_count=192,record_set_sha256=context['measurements']['original_records_sha256'],model_request_bytes=len(workflow.canonical(request)),original_record_bytes=len(workflow.canonical(data['measurements'])),encoded_packet_bytes=len(workflow.canonical(context['measurements'])))
 for n in lock['files']:
  if n!='autonomy.py':assert updated['files'][n]==lock['files'][n]
 (ROOT/'test/autonomy-evidence-lock-v1.json').write_text(json.dumps(updated,indent=2)+'\n');print(json.dumps({k:updated[k] for k in ('record_count','model_request_bytes','original_record_bytes','encoded_packet_bytes')}))
if __name__=='__main__':main()
