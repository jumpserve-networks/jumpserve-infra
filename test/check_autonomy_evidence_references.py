"""Reproduce the corrected, typed provenance whitelist without another model call."""
import json
from pathlib import Path
def references(context):
 result={}
 for i,run in enumerate(context.get('runs',[])):
  for key in ('id','campaign_id','input_sha256','output_sha256'):
   if run.get(key):result.setdefault(run[key],[]).append('$.runs['+str(i)+'].'+key)
 for key in ('id','document_sha256'):
  value=context.get('candidate',{}).get('protocol_reference',{}).get(key)
  if value:result.setdefault(value,[]).append('$.candidate.protocol_reference.'+key)
 value=context.get('measurements',{}).get('original_records_sha256')
 if value:result.setdefault(value,[]).append('$.measurements.original_records_sha256')
 return result
def main():
 root=Path(__file__).resolve().parents[1];path=next((root/'.test-artifacts/autonomy-evidence').glob('*/evidence-report.json'));report=json.loads(path.read_bytes());context=json.loads((path.parent/'inputs.json').read_bytes())['cases'][0]['model_context'];known=references(context)
 assert 'not-supplied' not in known
 assert 'invented' not in references(dict(prior_attempts=[dict(output=dict(evidence_ids=['invented']))]))
 answer=report['cases'][0]['output'];paths={value:known.get(value,[]) for value in answer['evidence_ids']};assert all(paths.values());print(json.dumps(dict(original_reference_check=report['cases'][0]['deterministic_checks']['actual_evidence_references'],corrected_reference_check=True,paths=paths),indent=2))
if __name__=='__main__':main()
