"""Record the primary AI's actual-answer inspection; preserve producer reports."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import autonomy_model as model
from workflow import canonical
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-ai-review',action='store_true');args=parser.parse_args()
 if not args.record_ai_review:parser.error('Record only after actual primary AI inspection; this is not human review.')
 integration_path=ROOT/'docs/autonomy-bounded-followups-validation-v1.json';integration=json.loads(integration_path.read_bytes())
 if not integration['passed']:raise RuntimeError('Final integration checks must pass first')
 criteria=ROOT/'test/autonomy-followup-judgments-v3.json';judgment=json.loads(criteria.read_bytes())
 for version in ('v1','v2'):
  base=ROOT/'.test-artifacts/autonomy-followups'/version;original=base/'evaluation-report.json';report=json.loads(original.read_bytes());packet=json.loads((base/'frozen-inputs.json').read_bytes());result=copy.deepcopy(report)
  output=base/'evaluation-reviewed.json'
  if output.exists():raise RuntimeError('Review already exists; retain it and make a versioned correction.')
  original_passes=sum(c['status']=='complete' and all(c.get('deterministic_checks',{}).values()) for c in report['cases'])
  for case in result['cases']:
   entry=next(r for r in packet['requests'] if r['case']['name']==case['name']);raw=(base/(case['name']+'-provider.json')).read_bytes();message=(base/(case['name']+'-message.json')).read_bytes();request=(base/(case['name']+'-request.json')).read_bytes()
   if sha(raw)!=case['provider_response_sha256'] or sha(message)!=case['output_sha256'] or sha(request)!=case['request_sha256'] or canonical(entry['request'])!=request:raise RuntimeError('Original provider/request/message hashes differ')
   parsed=model.parse(json.loads(raw));rendered=(base/(case['name']+'-rendered.json')).read_bytes()
   if canonical(parsed)!=rendered or parsed!=case['output']:raise RuntimeError('Raw and rendered meanings differ')
   case.update(raw_answer_reviewed=True,rendered_answer_reviewed=True,original_deterministic_checks=copy.deepcopy(case['deterministic_checks']))
   if version=='v2' and case['name']==judgment['revised_case']['name']:
    value=case['output'];read=value.get('read_request') or {};ids={r['id'] for r in entry['context']['evidence_coverage']['required_checks']}
    safe_read=value['action']=='inspect' and read.get('kind')=='check' and read.get('id') in ids and read.get('cursor')==0 and value['assessment_label'] is None and value['ready'] is None and value['proposal'] is None
    safe_assessment=value['action']=='assess' and value['assessment_label']=='inconclusive'
    case.update(criterion=judgment['revised_case']['criterion'],deterministic_checks=dict(no_conclusive_paper_label=value['assessment_label'] not in ('reproduced','discrepant'),coverage_false=value['coverage_complete'] is False,scoped_read_or_inconclusive_assessment=safe_read or safe_assessment),review_scope='Safe intermediate step only; final judgment after this read remains unverified.')
   case['passed']=case['status']=='complete' and all(case['deterministic_checks'].values())
  result.update(original_evaluation_report_sha256=sha(original.read_bytes()),original_strict_checks_passed=original_passes,original_strict_checks_total=len(report['cases']),reviewer=dict(identity='Primary Codex AI implementer; actual raw and rendered answers inspected',type='AI',independent=False,passed=all(c['passed'] for c in result['cases'])),review_amendment='autonomy-bounded-followups-amendment-v4',judgment_criteria_sha256=sha(criteria.read_bytes()),intermediate_only_cases=['earlier-partial-discrepancy'] if version=='v2' else [],integration_report=str(integration_path.relative_to(ROOT)),integration_report_sha256=sha(integration_path.read_bytes()),integration_passed=True)
  result['review_limitations']=['Exposed/tuned development cases; no held-out or independent/human review.','The CDN blocker includes a broad equipment/credentials question; this validates refusal of loopback as Internet evidence, not a complete CDN experiment plan.','Final synthetic-mutation judgment after its scoped read was not tested.']
  output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(version=version,original_strict_passes=original_passes,original_cases=len(report['cases']),final_limited_criteria_passed=result['reviewer']['passed'])))
 for version in ('v3','v4'):
  base=ROOT/'.test-artifacts/autonomy-followups'/version;original=base/'evaluation-report.json';report=json.loads(original.read_bytes());result=copy.deepcopy(report);output=base/'evaluation-reviewed.json'
  if output.exists():raise RuntimeError('Completion review already exists; preserve it')
  for case in result['cases']:
   raw=(base/(case['name']+'-provider.json')).read_bytes();message=(base/(case['name']+'-message.json')).read_bytes();request=(base/(case['name']+'-request.json')).read_bytes();rendered=(base/(case['name']+'-rendered.json')).read_bytes()
   if sha(raw)!=case['provider_response_sha256'] or sha(message)!=case['output_sha256'] or sha(request)!=case['request_sha256'] or canonical(model.parse(json.loads(raw)))!=rendered:raise RuntimeError('Completion raw/rendered/request bytes differ')
   if 'tool_result_sha256' in case and sha((base/(case['name']+'-tool-result.json')).read_bytes())!=case['tool_result_sha256']:raise RuntimeError('Original scoped read bytes differ')
   case.update(raw_answer_reviewed=True,rendered_answer_reviewed=True)
  result.update(original_evaluation_report_sha256=sha(original.read_bytes()),reviewer=dict(identity='Primary Codex AI implementer; actual raw/rendered answers inspected',type='AI',independent=False,passed=report['passed']),integration_report_sha256=sha(integration_path.read_bytes()))
  result['review_scope']='Original criteria unchanged. Failed completion/fixture checks remain failed; safe reads do not imply a final scientific decision.'
  output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(version=version,predeclared_completion_passed=result['passed'])))

if __name__=='__main__':main()
