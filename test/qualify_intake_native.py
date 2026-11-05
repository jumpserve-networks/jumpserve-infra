"""Real pinned warm Gateway, synthetic upstream only; no cloud or provider calls."""
import argparse,json,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--backend',type=Path,default=ROOT.parent/'jumpserve-back-end')
 parser.add_argument('--directory',type=Path,default=ROOT/'.test-artifacts/intake-native')
 args=parser.parse_args();sys.path[:0]=[str(args.backend/'research_workflow'),str(args.backend/'research_workflow/tests')]
 import intake_worker as worker,openclaw_runtime as runtime
 from test_openclaw import request,Response,stream
 from workflow import canonical,digest
 native=ROOT/'.test-artifacts/slack-setup-v1';runtime.NODE=native/'node/bin/node';runtime.PACKAGE=native/'vendor/node_modules/openclaw'
 runtime.verify_runtime();directory=args.directory/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());directory.mkdir(mode=0o700,parents=True)
 gateway=worker.WarmGateway(directory/'gateway');calls=[]
 def upstream(method,url,token,body):
  assert token=='synthetic-intake-access' and url=='https://api.openai.com/v1/responses'
  calls.append(body);time.sleep(0.25);return Response(stream())
 def turn(index):
  logical=request();logical['messages'][0]['content'][0]['text']=canonical(dict(task='planning',independent_chunk=index)).decode()
  answer,receipt=runtime.execute(logical,directory/('turn-'+str(index)),token_source=lambda:'synthetic-intake-access',transport=upstream,native_runner=gateway.run)
  assert receipt['status']=='complete',receipt
  assert receipt['provider_calls']==1 and answer
  import siwc_protocol
  assert (directory/('turn-'+str(index))/'provider-request.json').read_bytes()==canonical(siwc_protocol.response_request(logical))
  return receipt['wall_seconds']
 try:
  began=time.monotonic()
  with ThreadPoolExecutor(max_workers=2) as pool:times=list(pool.map(turn,range(2)))
  assert len(calls)==2 and len(set(calls))==2 and not gateway.routes
  # A subsequent turn reuses the SAME running native process, with a fresh
  # session/ticket and no history or previous source text in its provider input.
  pid=gateway.process.pid;turn(2);assert gateway.process.pid==pid and len(calls)==3
  # A ticket disappears at completion. A retained native request cannot use
  # it again, even with the correct private bridge bearer.
  import urllib.request,urllib.error
  raw=(directory/'turn-0/openclaw-http-body.bin').read_bytes()
  req=urllib.request.Request('http://127.0.0.1:'+str(gateway.bridge.server_address[1])+'/v1/chat/completions',data=raw,headers={'Authorization':'Bearer '+gateway.bridge_token,'Content-Type':'application/json'})
  try:gateway.opener.open(req,timeout=3);raise AssertionError('Expired native ticket was accepted.')
  except urllib.error.HTTPError as error:assert error.code==409
  assert len(calls)==3
  report=dict(passed=True,version=worker.VERSION,native_version='2026.10.5',node_version='24.16.0',
   concurrent_turns=2,synthetic_inferences=3,process_reused=True,exact_provider_requests=True,
   wall_seconds=time.monotonic()-began,parallel_turn_seconds=times,provider_calls=0,production_mutations=0,
   runtime_sha256={name:digest((args.backend/'research_workflow'/name).read_bytes()) for name in ('intake_worker.py','intake_parallel.py','openclaw_runtime.py')})
  (directory/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(directory/'qualification.json'),**report)))
 finally:gateway.close()

if __name__=='__main__':main()
