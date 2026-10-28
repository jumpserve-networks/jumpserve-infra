"""Offline replay of retained stalled-request bytes; zero provider/database calls."""
import importlib.util,io,json,pathlib,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import experiment_builder as builder,openclaw_runtime as runtime,siwc_protocol as wire
from workflow import canonical,digest
def main():
 source=sorted((ROOT/'.test-artifacts/assessment-4055396e').glob('*/checkpoint-history.json'))[-1].parent
 snapshot=json.loads((source/'snapshot.json').read_bytes());results=[]
 for row in snapshot['autonomy_tasks']:
  task=row['record'];checkpoint=task['context'].get('builder_checkpoint')
  if not checkpoint:continue
  raw=(source/(task['id']+'-checkpoint.zip')).read_bytes();assert digest(raw)==checkpoint['sha256']
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   context=json.loads(z.read('research-context.json'));history=json.loads(z.read('native-tool-history.json'));old=json.loads(z.read('context-index.json'))
   new=builder.delivered_pages(context,history)
   old_count=sum(len(v['delivered_pages']) for v in old['fields']);new_count=sum(len(v) for v in new.values())
   results.append(dict(task=task['id'],checkpoint_sha256=digest(raw),original_index_pages=old_count,corrected_exact_pages=new_count,working_files=[n for n in z.namelist() if n.startswith('project/')],complete_source_review=False))
 assert all(r['corrected_exact_pages']>r['original_index_pages'] for r in results)
 turn='75f9b315-e1e2-5499-8c59-8c3bf6c58193';logical=json.loads((source/(turn+'-logical.json')).read_bytes());native=json.loads((source/(turn+'-openclaw-http-body.bin')).read_bytes())
 old=canonical(wire.response_request(runtime.translate(native,logical)));new=canonical(wire.response_request(logical))
 assert len(old)>96000 and len(new)<=96000
 dispatch=next(r['record'] for r in snapshot['model_dispatches'] if r['record']['id']==turn)
 assert not any(a['name'] in ('provider-request.json','provider-response.bin') for a in dispatch['provenance']['artifacts'])
 report=dict(protocol='assessment-recovery-v1',kind='offline-original-request-and-checkpoint-replay',passed=True,new_model_calls=0,new_experiments=0,scientific_completion=False,
  pages=results,request=dict(dispatch_id=turn,original_logical_sha256=digest(canonical(logical)),original_derived_provider_bytes=len(old),corrected_provider_bytes=len(new),original_derived_sha256=digest(old),corrected_provider_sha256=digest(new),original_provider_transport_files_present=False,
    scope='Exact reconstructed preflight reproduces rejection before the provider-request write/transport. Original unknown receipt is preserved; this replay is evidence for reconciliation, not a rewritten outcome.'),
  reviewer=dict(identity='Implementing Codex assistant',type='AI',independent=False,human=False))
 path=source/'offline-replay.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(path),**report)))
if __name__=='__main__':main()
