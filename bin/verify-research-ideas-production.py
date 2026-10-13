"""Fixed, read-only production code/capability/privacy verification; no fake session."""
import base64,hashlib,importlib.util,io,json,ssl,subprocess,urllib.request,urllib.error,uuid,zipfile,datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/research-ideas-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
r=ROOT/'.test-artifacts/research-ideas/production'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');r.mkdir(parents=True,exist_ok=False)
report=dict(started_at=dt.datetime.now(dt.timezone.utc).isoformat(),checks=[],conditional_gaps=['Legitimate Google owner request and deployed cross-owner write denial require available authenticated sessions','Independent human/held-out scientific review'],new_model_calls=0,measured_charges_usd=None)
try:
 report['targets']=release.target()
 backend=json.loads((ROOT/'research-workflow-runtime.json').read_text())['files']
 agent=json.loads((ROOT/'docs/research-ideas-release-evidence/evaluation-reviewed-v2.json').read_text())['runtime_hashes']
 for name,expected in [('JumpServeBenchmarkStack-ResearchWorkflowApiE04EBDA-mGlPl5tGRx2X',backend),('JumpServeBenchmarkStack-ResearchWorkflowQueueWorke-82Gxm08dQQsP',backend),('JumpServeAgentStack-AgentFnC1FD126F-MG2xfZrwsBNg',{n.removeprefix('agent/'):h for n,h in agent.items()})]:
  obj=json.loads(subprocess.check_output(['aws','lambda','get-function','--function-name',name,'--profile','jumpserve','--output','json']))
  if ':395567831870:' not in obj['Configuration']['FunctionArn'] or obj['Configuration']['Environment']['Variables']['SUPABASE_URL']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Deployed Lambda target differs')
  with release.OPEN.open(obj['Code']['Location'],timeout=30) as response:raw=response.read()
  digest=hashlib.sha256(raw).digest()
  if base64.b64encode(digest).decode()!=obj['Configuration']['CodeSha256']:raise RuntimeError('Deployed ZIP hash mismatch')
  (r/(name+'.zip')).write_bytes(raw)
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   for path,sha in expected.items():
    if hashlib.sha256(archive.read(path)).hexdigest()!=sha:raise RuntimeError('Deployed source differs: '+name+'/'+path)
  report['checks'].append(dict(name='deployed Lambda original ZIP and source hashes',function=name,passed=True,source_files=len(expected),zip_sha256=digest.hex(),memory_mb=obj['Configuration']['MemorySize'],timeout_seconds=obj['Configuration']['Timeout']))
 report['database']=release.verify()
 role=release.admin.query("select pg_get_constraintdef(oid) definition from pg_constraint where conname='research_idea_distinct_review_roles'")
 if len(role)!=1 or '<>' not in role[0]['definition']:raise RuntimeError('Distinct review-role gate missing')
 report['checks'].append(dict(name='distinct review-role database constraint',passed=True,definition=role[0]['definition']))
 url='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research';agent_url='https://idk3jouyc6g2uolmge5ctuizwq0kpgcf.lambda-url.us-east-1.on.aws/'
 with release.OPEN.open(url+'/capabilities',timeout=20) as response:cap=json.load(response)
 if cap['ideas']!={'version':'research-ideas-v1','paper_required':False,'packet_bytes':24000}:raise RuntimeError('Deployed idea capability differs')
 report['checks'].append(dict(name='public idea capability',passed=True,capability=cap['ideas']))
 for endpoint,body in [(url+'/studies/'+str(uuid.uuid4())+'/idea',None),(url+'/studies/'+str(uuid.uuid4())+'/idea',{'action':'save'}),(agent_url,{'action':'idea'})]:
  request=urllib.request.Request(endpoint,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
  try:
   with release.OPEN.open(request,timeout=20) as response:status=response.status
  except urllib.error.HTTPError as e:status=e.code
  if status not in (401,403):raise RuntimeError('Anonymous owner/model action not denied: '+str(status))
  report['checks'].append(dict(name='anonymous private/model request denial',passed=True,status=status,method='POST' if body is not None else 'GET',endpoint=endpoint))
 report['passed']=True
except Exception as error:report['passed']=False;report['error']=str(error);raise
finally:
 report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();(r/'validation-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(r),passed=report['passed'],error=report.get('error'))))
