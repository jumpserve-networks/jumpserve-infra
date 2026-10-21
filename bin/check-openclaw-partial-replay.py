"""Replay one retained production answer through original and corrected controllers.

No provider or database writes. The exact request/output are exposed development
evidence; all other calls are declared fixtures around the controller handoff.
"""
import copy,hashlib,importlib.util,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import autonomy,autonomy_model as model,preparation
sha=lambda raw:hashlib.sha256(raw).hexdigest()
SNAPSHOT=ROOT/'.test-artifacts/openclaw-study-verification/20261021T162228304741Z/private-snapshot.json'
OLD=ROOT/'.test-artifacts/openclaw-evaluation/20261021T004429580770Z/inputs/runtime/autonomy.py'
def main():
 raw=SNAPSHOT.read_bytes();assert sha(raw)=='b65a36fbef12028c6b5e2d0732fde9687e2b4fb855c31d118a6caaea3a63b9ee'
 data=json.loads(raw);task=next(t for t in data['autonomy_tasks'] if t['id']=='7842ae5a-c516-5495-ad98-4df571163f05')
 answer=next(t for t in data['autonomy_turns'] if t['id']==task['context']['last_turn_id']);assert answer['number']==16 and answer['status']=='complete'
 assert sha(answer['request_raw'].encode())==answer['request_sha256'] and sha(answer['raw_response'].encode())==answer['response_sha256']
 plan_raw=(ROOT.parent/'jumpserve-back-end/research_workflow/plans/ipv6-archive-v1.json').read_bytes();plan=preparation.parse(plan_raw)
 compiled=preparation.compile_plan(plan,plan_raw,dict(id=task['study_id'],paper_url=plan['paper_urls'][0]))
 assert compiled['id']==task['context']['prepared_id']
 campaigns={v['record']['campaign_id'] for v in compiled['records'] if v['kind']=='claim_checks' and v['record']['claim_id']==task['claim_id']}
 jobs=[j for j in compiled['jobs'] if j['campaign_id'] in campaigns and j['execution_mode']=='automatic'];assert len(jobs)==6
 completed=task['context']['completed_job_ids']+task['context']['job_ids'];assert len(set(completed))==4
 assert len(data['measurements'])==768 and all(m['status']=='recorded' and m['units']=='percent' for m in data['measurements'])
 assert all(n['status']=='complete' for n in data['runs']) and len(data['runs'])==4
 spec=importlib.util.spec_from_file_location('original_partial_controller',OLD);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 assert sha(OLD.read_bytes())=='5ec4d7fdd2ba1f4da7c43d44c817eba78759fcfda92c9bbe41ab2149bdc4f771'
 context=json.loads(answer['request']['messages'][0]['content'][0]['text'])
 results={}
 for name,module in [('original',old),('corrected',autonomy)]:
  with patch.object(module,'build_context',return_value=context),patch.object(model,'call',return_value=answer),patch.object(module,'numeric_finding',return_value=None),patch.object(module,'inventory',return_value=jobs),patch.object(module,'advance',side_effect=lambda t,status,**kw:dict(status=status,**kw)),patch.object(module,'enqueue') as enqueue:
   result=module.step(copy.deepcopy(task));enqueue.assert_not_called();results[name]=result
 assert results['original']['status']=='blocked'
 fixed=results['corrected'];assert fixed['status']=='queued' and fixed['stage']=='planning' and fixed['label']=='inconclusive'
 assert fixed['context']['completed_job_ids']==completed and fixed['context']['blockers']==answer['output']['blockers']
 remaining=sorted(j['id'] for j in jobs if j['id'] not in completed)
 assert remaining==sorted(['554fe12f-b1db-5f8e-a261-f7840b997bfc','fc051c0a-3fb6-53e1-860e-7608e77cba7e'])
 report=dict(version='openclaw-partial-answer-replay-v1',status='passed',study_id=task['study_id'],task_id=task['id'],turn_number=16,snapshot_sha256=sha(raw),request_sha256=answer['request_sha256'],response_sha256=answer['response_sha256'],original_controller_sha256=sha(OLD.read_bytes()),corrected_controller_sha256=sha(Path(autonomy.__file__).read_bytes()),original_status=results['original']['status'],corrected_status=fixed['status'],corrected_stage=fixed['stage'],scientific_label=fixed['label'],completed_checks=4,required_checks=6,recorded_cells=768,required_cells=1152,remaining_check_ids=remaining,model_calls=0,database_writes=0,fixtures=['Request construction replaced by exact retained request context','Model invocation replaced by exact completed answer','numeric_finding=None for four of six required checks; no full-coverage decision exists','Inventory independently recompiled from unchanged original plan','Persistence captured without writes'],reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),limitations='Exposed controller regression, not an independent model or scientific validation.')
 (ROOT/'docs/openclaw-production-partial-replay-v1.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
