"""Independent arithmetic/identity check of retained production software output."""
import argparse,hashlib,json
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
QUOTE='In the specified loopback test, both of two 256-byte payload exchanges complete with 256 received bytes.'
SHA='8069a701e935332d20925cfa166c494299de245a4efddeeae582b25818fedd7f'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);args=p.parse_args();snapshot=args.snapshot.resolve()
 if not snapshot.is_relative_to(ROOT/'.test-artifacts/openclaw-study-verification'):raise ValueError('Retained private verification snapshot required')
 raw=snapshot.read_bytes();data=json.loads(raw);assert data['autonomy_workflows'][0]['study_id']=='2c80d382-f8a4-453c-8691-adfa3bcb5970'
 w=data['autonomy_workflows'][0];assert w['status']=='cancelled' and w['committed_cents']<=2000 and w['max_attempts'] is None
 assert len(data['claims'])==1 and data['claims'][0]['description']==QUOTE and not data['assessments']
 turns=data['autonomy_turns'];assert len(turns)==4 and all(t['status']=='complete' for t in turns)
 assert sorted(t['stage'] for t in turns)==['comprehension','critic','intake','planning']
 for t in turns:
  assert sha(t['request_raw'].encode())==t['request_sha256'] and sha(t['raw_response'].encode())==t['response_sha256']
  c=json.loads(t['request_raw'])['messages'][0]['content'][0]['text'];c=json.loads(c)
  if t['stage']!='intake':assert c['source_material']['original_pdf_sha256']==SHA and QUOTE in c['source_material']['inline_passage']['text']
  if t['stage'] in ('comprehension','critic'):assert 'prior_attempts' not in c and 'previous_feedback' not in c and t['output']['ready'] is True
 proposal=next(t['output']['proposal']['protocol'] for t in turns if t['stage']=='planning')
 assert proposal['hypotheses']==QUOTE and len(proposal['configurations'])==1 and proposal['configurations'][0]['details']['test_config']==dict(payload_bytes=256,exchanges=2,application_delay_ms=3)
 assert proposal['execution']['runner']=='bounded-tcp-v1' and proposal['execution']['replications']==1
 assert len(data['queue_jobs'])==len(data['runs'])==1 and data['runs'][0]['status']=='complete' and len(data['measurements'])==4
 assert all(m['configuration_identity']==proposal['configurations'][0]['identity'] and m['run_id']==data['runs'][0]['id'] and m['details']['replication']==0 for m in data['measurements'])
 artifacts=data['artifacts'];cache=ROOT/'.test-artifacts/openclaw-study-verification/original-byte-cache'
 for a in artifacts:assert sha((cache/a['sha256']).read_bytes())==a['sha256']
 assert any(a['sha256']==SHA for a in artifacts)
 originals=[a for a in artifacts if a['provenance'].get('kind')=='bounded-tcp-original-lambda-response'];assert len(originals)==1
 original=json.loads((cache/originals[0]['sha256']).read_bytes(),parse_float=Decimal)
 actual={(o['observation_key'],o['metric']):(o['units'],Decimal(str(o['value'])),o['status']) for o in original['observations']}
 saved={(o['observation_id'],o['metric']):(o['units'],Decimal(o['value']),o['status']) for o in data['measurements']}
 assert len(actual)==len(saved)==4 and actual==saved
 expected={(str(i),metric) for i in range(2) for metric in ('received_bytes','round_trip_time_ms')};assert set(actual)==expected
 for (identity,metric),(units,value,status) in saved.items():
  assert status=='recorded' and value.is_finite() and value>=0
  assert (units,value)==('bytes',Decimal(256)) if metric=='received_bytes' else units=='ms'
 report=dict(version='planning-context-production-measurement-check-v1',status='passed',snapshot_sha256=sha(raw),source_sha256=SHA,original_executor_sha256=originals[0]['sha256'],original_artifacts_hashed=len(artifacts),turns=4,actual_fresh_ai_reviews=2,executions=1,measurements=4,received_bytes=[256,256],rtt_ms=[str(saved[(str(i),'round_trip_time_ms')][1]) for i in range(2)],committed_cents=w['committed_cents'],actual_charges_usd=None,academic_assessments=0,method='Standard-library JSON/Decimal, hash and exact matched-identity checks, without application parsers or numeric finding code. Shared original inputs and AI implementer; not independent scientific validation.',uncertainty='Two exchanges share a single host/run/connection; descriptive values only, no inferential interval.',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False))
 (ROOT/'docs/planning-context-production-measurement-check-v1.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
