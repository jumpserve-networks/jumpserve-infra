"""Fixed production-host qualification; staged source, no runtime replacement."""
import importlib.util,io,json,os,subprocess,sys,time,traceback,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'research_workflow'))
import autonomy_model as model,openclaw_runtime as runtime,siwc_protocol as wire
from workflow import canonical,digest
packet=json.loads((ROOT/'frozen.json').read_bytes())
assert os.getuid()!=0 and os.environ['SUPABASE_URL']=='https://regphejnlvfpyokpniny.supabase.co'
for name,sha in packet['source_files'].items():assert digest((ROOT/name).read_bytes())==sha,name
def save(name,value):(ROOT/name).write_bytes(canonical(value))
class Response(io.BytesIO):
 status=200;headers={}
 def read1(self,n):return self.read(n)
def decision():return dict(action='blocked',reason='missing-required-inputs',blockers=[dict(kind='missing-data',detail='missing-source-data',required_input='Explicit synthetic transport response; not a scientific judgment')],claims=[],check_id=None,proposal=None,ready=None,coverage_complete=False,assessment_label=None,evidence_ids=[])
def synthetic():return b'data: '+canonical(dict(type='response.completed',response=dict(status='completed',model=runtime.MODEL,output=[dict(type='message',role='assistant',content=[dict(type='output_text',text=canonical(decision()).decode())])],usage=dict(input_tokens=100,output_tokens=30,total_tokens=130))))+b'\n\n'
def prepare():
 runtime.verify_runtime()
 inventory=json.loads(subprocess.check_output(['docker','image','inspect',packet['image']],timeout=20))[0];assert inventory['Architecture']=='amd64' and inventory['Os']=='linux'
 modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True)
 for name,target in [('openclaw',runtime.PACKAGE),('node',runtime.NODE.parents[1])]: (modules/name).symlink_to(target,target_is_directory=True)
 save('prepared.json',dict(status='passed',image=packet['image'],platform=sys.platform,node_version=subprocess.check_output([str(runtime.NODE),'--version'],text=True).strip(),openclaw_version='2026.10.5',source_revision=packet['source_revision']))
def native():
 assert not (ROOT/'native.json').exists();assert json.loads((ROOT/'prepared.json').read_bytes())['status']=='passed'
 raw=(ROOT/'retained-logical.json').read_bytes();assert digest(raw)==packet['logical_sha256'];logical=json.loads(raw)
 old=types.ModuleType('old_data_runtime');old.__file__=str(ROOT/'research_workflow/openclaw_runtime.py');exec(compile((ROOT/'baseline-runtime.py').read_bytes(),old.__file__,'exec'),old.__dict__)
 result=dict(status='running',cases=[],live_provider_calls=0,source_revision=packet['source_revision']);save('native.json',result)
 for name,implementation in [('baseline',old),('corrected',runtime)]:
  calls=[];trace=[];server_type=implementation.ThreadingHTTPServer;directory=ROOT/('native-'+name)
  def transport(method,url,token,body):
   assert method=='POST' and url=='https://api.openai.com/v1/responses' and token=='synthetic-no-credential' and body==canonical(wire.response_request(logical));calls.append(dict(bytes=len(body),sha256=digest(body)));return Response(synthetic())
  def server(address,handler):
   class Capture(handler):
    def do_POST(self):
     length=int(self.headers.get('Content-Length','0'));trace.append(dict(content_length=length))
     if 0<length<=1000000:
      raw=self.rfile.read(length);(directory/'captured-native-body.bin').write_bytes(raw);self.rfile=io.BytesIO(raw)
     return super().do_POST()
   return server_type(address,Capture)
  with patch.object(implementation,'ThreadingHTTPServer',side_effect=server): answer,receipt=implementation.execute(logical,directory,token_source=lambda:'synthetic-no-credential',transport=transport)
  if name=='baseline':assert answer is None and not calls and not receipt['provider_request_sent'] and trace[0]['content_length']>96000
  else:assert receipt['status']=='complete' and len(calls)==1 and calls[0]['bytes']<=96000 and trace[0]['content_length']<=96000
  result['cases'].append(dict(name=name,receipt=receipt,bridge=trace,upstream=calls));save('native.json',result)
 sys.path.insert(0,str(ROOT/'research_workflow/tests'));suite=unittest.defaultTestLoader.discover(str(ROOT/'research_workflow/tests'),pattern='test_openclaw.py')
 with (ROOT/'native-tests.log').open('w') as stream:tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 result['tests']=dict(run=tests.testsRun,failures=len(tests.failures),errors=len(tests.errors),skipped=len(tests.skipped));save('native.json',result);assert tests.wasSuccessful() and not tests.skipped and tests.testsRun>=14
 result['status']='passed';save('native.json',result)
def live():
 assert json.loads((ROOT/'native.json').read_bytes())['status']=='passed' and not (ROOT/'live.json').exists()
 limits=packet['protocol']['resources'];began=time.monotonic();report=dict(status='running',actual_calls=0,reserved_cents=0,cases=[],measured_charges_usd=None,subscription_allocation_usd=None);save('live.json',report)
 logical=packet['live_logical'];raw=canonical(logical)
 def transport(method,url,token,body):
  assert report['actual_calls']<limits['maximum_actual_provider_calls'] and time.monotonic()-began<limits['maximum_elapsed_seconds']-65
  assert body==canonical(wire.response_request(logical));report.update(actual_calls=report['actual_calls']+1,reserved_cents=100);save('live.json',report)
  save('live-admission.json',dict(request_sha256=digest(body),bytes=len(body),kind='conservative qualification reservation; not paper spending or measured charges',reserved_cents=100))
  return runtime.http_request(method,url,token,body)
 answer,receipt=runtime.execute(logical,ROOT/'live-turn',transport=transport);report['cases'].append(dict(name='live-data-only-response',receipt=receipt,answer=answer));save('live.json',report)
 assert receipt['status']=='complete' and report['actual_calls']==1,receipt
 value=model.parse(answer);model.validate_phase(value,packet['live_context']);assert value['action']=='blocked' and value['assessment_label'] is None and not value['coverage_complete']
 report.update(status='awaiting-substantive-review',wall_seconds=time.monotonic()-began);save('live.json',report)
def evidence():
 spec=importlib.util.spec_from_file_location('base_qualification',ROOT/'base_qualification.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.evidence()
if __name__=='__main__':
 action=sys.argv[1];assert action in ('prepare','native','live','evidence')
 try:globals()[action]()
 except Exception:save(action+'-failure.json',dict(status='failed',traceback=traceback.format_exc()));raise
