"""Exact retained planner/native CLI regression. Synthetic upstream, no credentials."""
import argparse,datetime as dt,hashlib,importlib.util,io,json,pathlib,subprocess,sys,types
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sys.path.insert(0,str(BACK/'research_workflow'))
import openclaw_runtime as current,siwc_protocol as wire
from workflow import canonical,digest
BASELINE='52abe168691afb678ecfcbd91f3f07b70fb7ca04'
class Response(io.BytesIO):
 status=200;headers={}
 def read1(self,n):return self.read(n)
def synthetic_stream():
 decision=dict(action='blocked',reason='missing-required-inputs',blockers=[dict(kind='missing-data',detail='missing-source-data',required_input='Explicit synthetic transport response; not a scientific judgment')],claims=[],check_id=None,proposal=None,ready=None,coverage_complete=False,assessment_label=None,evidence_ids=[])
 return b'data: '+canonical(dict(type='response.completed',response=dict(status='completed',model=current.MODEL,output=[dict(type='message',role='assistant',content=[dict(type='output_text',text=canonical(decision).decode())])],usage=dict(input_tokens=100,output_tokens=30,total_tokens=130))))+b'\n\n'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('baseline','compare'));args=parser.parse_args()
 source=sorted((ROOT/'.test-artifacts/autonomy-completion-v1').glob('*/retrieval.json'))[-1].parent
 refs=json.loads((source/'retrieval.json').read_bytes());raw=(source/'logical.json').read_bytes();assert next(a for a in refs['artifacts'] if a['name']=='logical.json')['sha256']==digest(raw)
 logical=json.loads(raw);assert canonical(logical)==raw
 package=BACK/'experiments/openclaw_pilot/runtime/node_modules/openclaw';node=package.parent/'node/bin/node'
 assert node.exists() and json.loads((package/'package.json').read_bytes())['version']=='2026.10.5'
 original=subprocess.check_output(['git','show',BASELINE+':research_workflow/openclaw_runtime.py'],cwd=BACK)
 corrected_source=pathlib.Path(current.__file__).read_bytes()
 baseline=types.ModuleType('baseline_planner_runtime');baseline.__file__=str(BACK/'research_workflow/openclaw_runtime.py');exec(compile(original,baseline.__file__,'exec'),baseline.__dict__)
 out=ROOT/'.test-artifacts/autonomy-completion-v1/native'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
 (out/'protocol.json').write_bytes((ROOT/'docs/autonomy-completion-protocol-v1.json').read_bytes())
 report=dict(version='autonomy-native-planner-check-v2',status='running',source_capture='Runtime source captured before native execution; unchanged-file assertion after each case.',platform=sys.platform,node_version=subprocess.check_output([str(node),'--version'],text=True).strip(),logical_sha256=digest(raw),logical_bytes=len(raw),provider_wire_bytes=len(canonical(wire.response_request(logical))),live_provider_calls=0,synthetic_provider_calls=0,production_writes=0,cases=[],scope='Real native CLI and original retained input; upstream replies and their token usage are explicitly synthetic. Exposed development regression, not model or scientific validation.')
 try:
  for name,runtime in [('baseline',baseline)]+([('corrected',current)] if args.mode=='compare' else []):
   calls=[];trace=[];server_type=runtime.ThreadingHTTPServer;directory=out/name
   def transport(method,url,token,body):
    assert method=='POST' and url=='https://api.openai.com/v1/responses' and token=='synthetic-not-a-credential'
    assert body==canonical(wire.response_request(logical));calls.append(dict(bytes=len(body),sha256=digest(body)));return Response(synthetic_stream())
   def server(address,handler):
    class Trace(handler):
     def do_POST(self):
      length=int(self.headers.get('Content-Length','0'));item=dict(path=self.path,content_length=length);trace.append(item)
      if 0<length<=1000000:
       incoming=self.rfile.read(length);item.update(actual_bytes=len(incoming),sha256=digest(incoming));directory.mkdir(exist_ok=True);(directory/'captured-native-body.bin').write_bytes(incoming);self.rfile=io.BytesIO(incoming)
      return super().do_POST()
    return server_type(address,Trace)
   with patch.object(runtime,'NODE',node),patch.object(runtime,'PACKAGE',package),patch.object(runtime,'ThreadingHTTPServer',side_effect=server):
    answer,receipt=runtime.execute(logical,directory,token_source=lambda:'synthetic-not-a-credential',transport=transport)
   assert pathlib.Path(current.__file__).read_bytes()==corrected_source,'Runtime changed during native check; preserve results and freeze a new run'
   result=dict(name=name,source_sha256=digest(original if name=='baseline' else corrected_source),bridge=trace,upstream=calls,status=receipt['status'],error_code=receipt.get('error_code'),receipt=receipt)
   report['cases'].append(result);report['synthetic_provider_calls']+=len(calls)
   (out/'report.json').write_bytes(canonical(report))
   if name=='baseline':assert answer is None and not calls and receipt['provider_request_sent'] is False,'Retained baseline failure must reproduce before correction'
   else:assert answer is not None and len(calls)==1 and receipt['status']=='complete' and receipt['provider_calls']==1
  report['status']='baseline-reproduced' if args.mode=='baseline' else 'passed'
 except Exception as error:
  report.update(status='failed',error_type=type(error).__name__,reason=str(error));raise
 finally:
  (out/'report.json').write_bytes(canonical(report));print(json.dumps(dict(directory=str(out),status=report['status'],logical_bytes=report['logical_bytes'],provider_wire_bytes=report['provider_wire_bytes'],cases=[{k:c[k] for k in ('name','bridge','upstream','status','error_code')} for c in report['cases']],live_provider_calls=0)))
if __name__=='__main__':main()
