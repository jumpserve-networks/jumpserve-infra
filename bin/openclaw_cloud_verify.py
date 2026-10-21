"""Retrieve and independently check the one retained cloud software-control result."""
import io,json,sys,time,urllib.error,urllib.request,zipfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(release,directory):
 candidates=[]
 for p in (ROOT/'.test-artifacts/openclaw-release').glob('*/receipt.json'):
  value=json.loads(p.read_bytes())
  if value.get('mode')=='cloud-control' and value.get('status')=='complete':candidates.append((p,value))
 if len(candidates)!=1:raise ValueError('Exactly one original cloud control is required; preserve attempts before amending')
 path,original=candidates[0];result=release.aws('ssm','get-command-invocation','--command-id',original['ssm']['command_id'],'--instance-id',original['ssm']['instance_id'])
 if result['Status']!='Success':raise ValueError('Cloud control did not complete; do not replay it')
 report=json.loads(result['StandardOutputContent']);frozen=original['frozen']
 if not report['passed'] or report['id']!=frozen['id'] or report['source_files_verified']!=31:raise ValueError('Retained cloud control differs')
 archive=report['archive'];key=release.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+archive['path']
 if not archive['path'].startswith('release-verification/openclaw-cloud-control/'+frozen['id']+'/'):raise ValueError('Unexpected cloud artifact path')
 with release.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':key,'Authorization':'Bearer '+key}),timeout=30) as response:raw=response.read(1000001)
 if release.sha(raw)!=archive['sha256']:raise ValueError('Retrieved cloud original archive differs')
 os.environ['RESEARCH_AI_RUNTIME']='openclaw-production-v1';sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
 import autonomy_model as model,siwc_protocol as wire
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  for entry in archive['originals']:
   if release.sha(z.read(entry['path']))!=entry['sha256']:raise ValueError('Retrieved original file differs')
  if release.sha(z.read('logical.json'))!=frozen['request_sha256']:raise ValueError('Cloud request differs from frozen original')
  response=wire.read_stream(io.BytesIO(z.read('provider-response.bin')),io.BytesIO(),time.monotonic()+10,1048576);typed=model.parse(wire.structured_response(response))
  if typed!=report['output'] or json.loads(json.loads(z.read('stdout.bin'))['payloads'][0]['text'])!=typed:raise ValueError('Original SSE, native output and reported decision differ')
  model.validate_phase(typed,dict(task='planning'))
 (directory/'cloud-originals.zip').write_bytes(raw)
 anon=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
 try:
  with release.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':anon}),timeout=20) as response:response.read(1)
 except urllib.error.HTTPError as error:status=error.code
 if status not in (400,401,403,404):raise ValueError('Cloud originals must not be public')
 report.update(independent_retrieval_hash_verified=True,anonymous_archive_status=status,raw_answer_reviewed=True,rendered_answer_reviewed=True,reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False,passed=True),review_notes='Actual planning answer identifies missing source records and an applicable implementation. Empty finding and evidence fields, false coverage, no fabricated measurement. Reused synthetic software case; not paper evidence or independent validation.')
 (ROOT/'docs/openclaw-production-cloud-control-v1.json').write_text(json.dumps(report,indent=2)+'\n');return report
