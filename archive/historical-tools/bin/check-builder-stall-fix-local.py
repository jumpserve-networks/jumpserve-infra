"""Counterfactual wire-fit checks on exact retained parents; no live model calls."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sys.path.insert(0,str(BACK/'research_workflow'))
import experiment_builder as builder
from workflow import canonical,digest


def main():
    base=ROOT/'.test-artifacts/assessment-4055396e'
    matched_path=sorted(base.glob('*/matched-checkpoints.json'))[-1]
    matched=json.loads(matched_path.read_bytes());source=ROOT/matched['source_capture'];data=json.loads(source.read_bytes())
    supplement_path=ROOT/matched['supplement'];supplement=json.loads(supplement_path.read_bytes())
    out=ROOT/'.test-artifacts/builder-stall-fix'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    report=dict(version='builder-stall-work-packet-replay-v1',status='running',cases=[],new_live_model_calls=0,new_experiments=0,production_writes=0,kind='Counterfactual development regression, not held-out or scientific validation',transformation='Retain original developer message, schemas, call identities and all other outputs. Substitute the new bootstrap and server-generated index/continuation outputs using the exact completed parent checkpoint. Post-slot history is retained as a new continuation; no original request or result is overwritten.',reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False))
    try:
        for item in matched['checkpoints']:
            checkpoint=(matched_path.parent/item['file']).read_bytes();assert digest(checkpoint)==item['sha256']
            parent=next(d for d in data['dispatches'] if d['id']==item['dispatch_id']);assert parent['provenance']['checkpoint']['sha256']==item['sha256']
            request_item=next(r for r in supplement['requests'] if r['dispatch_id']==parent['id']);raw=(supplement_path.parent/request_item['file']).read_bytes();assert digest(raw)==request_item['sha256'];request=json.loads(raw)
            task_ref=next(a for a in data['artifact_reads'] if a['role']=='parent:'+parent['id']+':task.txt');old_boot=(source.parent/task_ref['file']).read_bytes();assert digest(old_boot)==task_ref['sha256']
            with tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp)/'workspace';work.mkdir();builder.restore(checkpoint,work)
                context=json.loads((work/'research-context.json').read_bytes());before_context=canonical(context);history=builder.load_history(work)
                old_files={name:(work/name).read_bytes() for name in ('context-index.json','builder-continuation.json')}
                logical=json.loads(parent['request_raw']);logical=copy.deepcopy(logical);logical['builder']['context']=context
                text,manifest=builder.bootstrap(logical,work,Path(tmp),history)
                packet=(work/'work-packet.json').read_bytes()
                changed=copy.deepcopy(request);replacements={old_boot.decode():text,**{value.decode():(work/name).read_text() for name,value in old_files.items()}}
                applied=[]
                for entry in changed['input']:
                    if entry.get('role')=='user':
                        for part in entry.get('content',[]) if isinstance(entry.get('content'),list) else []:
                            if isinstance(part.get('text'),str) and old_boot.decode() in part['text']:part['text']=part['text'].replace(old_boot.decode(),text);applied.append('bootstrap')
                    if entry.get('type')=='function_call_output':
                        value=entry['output']
                        for old,new in list(replacements.items())[1:]:
                            if old in value:value=value.replace(old,new);applied.append('metadata')
                        entry['output']=value
                assert 'bootstrap' in applied,'Original complete bootstrap must match the retained native user message'
                assert canonical(json.loads((work/'research-context.json').read_bytes()))==before_context and builder.load_history(work)==history
                assert changed['tools']==request['tools']
                assert [x for x in changed['input'] if x.get('type')=='function_call']==[x for x in request['input'] if x.get('type')=='function_call']
                original_bytes=len(canonical(request));counterfactual_bytes=len(canonical(changed))
                fresh=copy.deepcopy(changed);fresh['input']=[x for x in changed['input'] if x.get('role') in ('developer','system','user')]
                # An explicit synthetic packet-read result in a new native
                # session, not a claim that the real model selected this tool.
                fresh['input'].extend([dict(type='function_call',call_id='synthetic-packet-read',name='read',arguments='{"path":"work-packet.json"}'),dict(type='function_call_output',call_id='synthetic-packet-read',output=packet.decode())])
                fresh_bytes=len(canonical(fresh))
                case=dict(task_id=item['task_id'],dispatch_id=parent['id'],checkpoint_sha256=digest(checkpoint),original_request_sha256=digest(raw),original_bytes=original_bytes,counterfactual_bytes=counterfactual_bytes,historical_counterfactual_fits=counterfactual_bytes<=builder.CONTEXT_CHECKPOINT_BYTES,fresh_packet_request_bytes=fresh_bytes,fresh_request_kind='Synthetic first packet-read request; real native overhead retained. No model behavior implied.',maximum_bytes=builder.CONTEXT_CHECKPOINT_BYTES,remaining_bytes=builder.CONTEXT_CHECKPOINT_BYTES-counterfactual_bytes,replacements=applied,work_packet_bytes=len(packet),work_packet_sha256=digest(packet),context_sha256=digest(before_context),full_original_history_preserved=True)
                report['cases'].append(case)
                (out/(item['task_id']+'-work-packet.json')).write_bytes(packet)
                (out/(item['task_id']+'-counterfactual-request.json')).write_bytes(canonical(changed))
                assert original_bytes>builder.CONTEXT_CHECKPOINT_BYTES and counterfactual_bytes<original_bytes and fresh_bytes<builder.CONTEXT_CHECKPOINT_BYTES,case
        release_base=ROOT/'.test-artifacts/builder-stall-release-v1'
        if (release_base/'selected.txt').exists():
            selected=release_base/(release_base/'selected.txt').read_text().strip();frozen=json.loads((selected/'frozen.json').read_bytes());followup=frozen.get('packaging_followup',{})
            if followup.get('metadata_repair'):
                ref=followup['checkpoints']['retained-paper-implementation']
                with zipfile.ZipFile(selected/'candidate.zip') as archive:checkpoint=archive.read(ref['file'])
                assert digest(checkpoint)==ref['sha256']
                with tempfile.TemporaryDirectory() as tmp:
                    work=Path(tmp)/'workspace';work.mkdir();builder.restore(checkpoint,work);context=copy.deepcopy(frozen['paper_context']);context['builder_feedback']=followup['metadata_repair'];history=builder.load_history(work)
                    prompt=next(p for p in frozen['prompts'] if p['module_id']==builder.MODULE)
                    logical=dict(system=[dict(text=prompt['system_prompt']+'\n\n'+prompt['research_context']),dict(text=context['qualification_instruction']),dict(text=builder.action_policy()['document']['instruction']),dict(text=followup['metadata_repair'])],builder=dict(context=context))
                    bootstrap,delivery=builder.bootstrap(logical,work,Path(tmp),history);packet=(work/'work-packet.json').read_bytes();assert len(packet)<=builder.WORK_PACKET_BYTES and len(bootstrap.encode())<=builder.BOOTSTRAP_BYTES
                    assert json.loads((work/'research-context.json').read_bytes())==context and builder.load_history(work)==history
                    (out/'dense-metadata-work-packet.json').write_bytes(packet);(out/'dense-metadata-bootstrap.txt').write_text(bootstrap)
                    report['dense_metadata_repair']=dict(checkpoint_sha256=digest(checkpoint),work_packet_bytes=len(packet),bootstrap_bytes=len(bootstrap.encode()),original_context_preserved=True,original_history_preserved=True,scope='Exact recorded metadata-repair context with current code; local pre-provider control, no model behavior implied.')
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,reason=str(error));raise
    finally:
        report['source_files']={n:digest((BACK/'research_workflow'/n).read_bytes()) for n in ('experiment_builder.py','autonomy.py','autonomous_repair.py','autonomy_inputs.py','autonomy_costs.py','network_spec.py','netem_iperf.py')}
        report['amendment']=json.loads((BACK/'research_workflow/policies/builder-stall-fix-validation-v2.json').read_bytes())
        (out/'report.json').write_bytes(canonical(report))
        print(json.dumps(dict(directory=str(out),status=report['status'],cases=report['cases'],new_model_calls=0)))


if __name__=='__main__':main()
