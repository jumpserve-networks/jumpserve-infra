"""Record actual primary-AI answer/failure inspection; never publishes a prompt."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT.parent/'jumpserve-back-end/research_workflow')]
import autonomy_model as model
from workflow import canonical
from autonomy_trajectory_evidence import publication_status
BASE=ROOT/'.test-artifacts/autonomy-followups/application-trajectory-v3'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record-ai-review',action='store_true');args=parser.parse_args()
 if not args.record_ai_review:parser.error('Use only after actual raw/rendered answer and failure inspection.')
 original=BASE/'evaluation-report.json';output=BASE/'evaluation-reviewed.json'
 if output.exists():raise RuntimeError('Preserve the original review; use a new version for corrections.')
 report=json.loads(original.read_bytes());result=copy.deepcopy(report)
 if publication_status(report)!='eligible-for-review':raise RuntimeError('Trajectory is incomplete or failed under its declared policy.')
 for case in result['cases']:
  request=(BASE/(case['name']+'-request.json')).read_bytes();raw=(BASE/(case['name']+'-provider.json')).read_bytes()
  if sha(request)!=case['request_sha256'] or sha(raw)!=case['provider_response_sha256']:raise RuntimeError('Original request/provider bytes changed')
  if case['status']=='provider-rejected':
   error=(BASE/(case['name']+'-error.bin')).read_bytes()
   if raw or b'ThrottlingException' not in error or sha(error)!=case['failure_sha256'] or not case['no_answer_received'] or not case['provider_attempt_not_replayed']:raise RuntimeError('Known rejection provenance differs')
   case.update(failure_reviewed=True,raw_answer_reviewed=False,rendered_answer_reviewed=False,review_judgment='Explicit provider rejection, absent answer and missing usage reviewed; safe stop and next numbered operator-reconciled attempt, not an answer-accuracy pass.')
  else:
   message=(BASE/(case['name']+'-message.json')).read_bytes();rendered=(BASE/(case['name']+'-rendered.json')).read_bytes();value=json.loads(raw)
   if sha(message)!=case['output_sha256'] or canonical(value['output']['message'])!=message or canonical(model.parse(value))!=rendered or json.loads(rendered)!=case['output']:raise RuntimeError('Actual raw/rendered answer differs')
   case.update(raw_answer_reviewed=True,rendered_answer_reviewed=True,review_judgment='Primary AI inspected actual structured and rendered output: phase action, readiness/coverage scope, no unsupported conclusive label, and retained evidence identity.')
  if case.get('tool_result_sha256') and sha((BASE/(case['name']+'-tool-result.json')).read_bytes())!=case['tool_result_sha256']:raise RuntimeError('Original read result differs')
 result.update(original_evaluation_report_sha256=sha(original.read_bytes()),reviewer=dict(identity='Primary Codex AI implementer; actual raw/rendered answers and explicit rejection inspected',type='AI',independent=False,passed=True),
  review_limitations=['Exposed development/release trajectory; no human, independent or held-out review.','Application limit stops can be correct without scientific closure.','One explicit throttle was operator-reconciled in isolated SQL, not automatic production recovery.','Original CLI stdout/canonical SDK bytes retained; provider HTTP wire bytes unavailable.'])
 output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(path=str(output),terminal_status=result['terminal_status'],attempts=result['attempts_used'],reviewer_type='AI',independent=False)))


if __name__=='__main__':main()
