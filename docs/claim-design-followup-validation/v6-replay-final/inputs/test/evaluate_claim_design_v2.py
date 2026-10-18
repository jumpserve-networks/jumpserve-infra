"""Twenty clarification-first actual-answer development cases; no production writes."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import claim_experiment_design as design
import idea_interview, idea_review
from settings import MODEL_ID, MODEL_REGION

def sha(raw): return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--replay-v6',action='store_true');parser.add_argument('--campaign',choices=['v3'],required=True);parser.add_argument('--candidate',choices=['v5','v6'],required=True);args=parser.parse_args()
    if args.replay_v6:
        if args.live or args.candidate!='v6':parser.error('Replay is offline and restricted to the retained v6 answers')
        replay_v6();return
    if not args.live: parser.error('--live is required for the declared billed model calls')
    account=subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()
    if account!='395567831870' or json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Research target mismatch')
    cases_path=ROOT/'test/claim-design-evaluation-cases-v4.json';lock=json.loads(cases_path.with_suffix('.lock.json').read_text())
    if sha(cases_path.read_bytes())!=lock['sha256']: raise RuntimeError('Frozen cases changed; preserve and amend')
    protocol=json.loads(cases_path.read_text());seed=json.loads((ROOT/('database/seed-claim-experiment-design-'+args.candidate+'.json')).read_text())
    previous=[]
    for file in (ROOT/'.test-artifacts/claim-design/evaluations').glob('*/evaluation-report.json'):
        prior=json.loads(file.read_text())
        if prior.get('protocol')=='claim-experiment-design-protocol-v3':previous.append(prior)
    if any(prior['prompt_version']==seed['version'] for prior in previous) or len(previous)>=2:
        raise RuntimeError('This candidate was already attempted or the two-candidate budget is exhausted; preserve evidence and declare a follow-up')
    directory=ROOT/'.test-artifacts/claim-design/evaluations'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    report=dict(protocol='claim-experiment-design-protocol-v3',response_version=design.RESPONSE_VERSION,runner_context_sha256=sha(design.canonical(design.RUNNER_CONTEXT)),response_channel_sha256=sha(design.canonical(design.response_channel())),aws_account=account,supabase_project='regphejnlvfpyokpniny',decision_policy=dict(version=design.POLICY['version'],sha256=design.POLICY_SHA256,mode=design.POLICY['mode']),evaluation_kind='actual-model-development',module_id=design.MODULE,analysis_version=design.VERSION,prompt_version_id=seed['id'],prompt_version=seed['version'],prompt_content_sha256=sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode()),cases_sha256=lock['sha256'],model_id=MODEL_ID,model_region=MODEL_REGION,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),cases=[],limits=protocol['limits'],evaluator=dict(identity='Primary Codex AI implementer',type='AI',independent=False),reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False,passed=False),measured_charges_usd=None,estimated_model_cost_usd=None,limitations=['Development cases exposed to implementer; not held-out validation or human review.','No scientific experiments or production writes.','Original CLI output bytes and SDK message retained; original HTTP response bytes unavailable.','Missing charges and failed-call usage are unknown, not zero.'])
    frozen=['agent/research_ideas.py','agent/claim_experiment_design.py','agent/claim-decision-policy-v1.json','agent/idea_review.py','agent/idea_interview.py','database/seed-claim-experiment-design-'+args.candidate+'.json','test/claim-design-evaluation-cases-v4.json','test/claim-design-evaluation-cases-v4.lock.json','docs/claim-experiment-design-protocol-v3.md','test/evaluate_claim_design_v2.py']
    if args.candidate=='v6':frozen.append('docs/claim-experiment-design-v3-amendment-v6.md')
    report['input_sha256']={}
    for name in frozen:
        raw=(ROOT/name).read_bytes();target=directory/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);report['input_sha256'][name]=sha(raw)
    for name in ('network_spec.py','workflow.py','claim_design.py','policies/claim-decision-policy-v1.json'):
        raw=(ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes();target=directory/'inputs/backend'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);report['input_sha256']['backend/'+name]=sha(raw)
    def save(): (directory/'evaluation-report.json').write_text(json.dumps(report,indent=2)+'\n')
    save();started=time.monotonic()
    for case in protocol['cases']:
        row=dict(name=case['name'],task=case['task'],rubric=case['rubric'],status='running',passed=False,usage=None);report['cases'].append(row);save()
        if time.monotonic()-started>=protocol['limits']['wall_seconds']: row.update(status='excluded',reason='Frozen total wall budget exhausted');save();continue
        planning=case['task']=='planning'
        context=dict(task=case['task'],packet=case['packet'],packet_sha256=sha(design.canonical(case['packet'])))
        if planning: context.update(paper_claim=case['paper_claim'],user_message=case['message'],**design.planning_context())
        else: context['review_sources']=dict(version=idea_review.VERSION,available_paths=list(idea_review.fields(case['packet'])))
        messages=[dict(role='user',content=[dict(text=design.canonical(context).decode())])]
        if len(design.canonical(messages))>24000: row.update(status='excluded',reason='Frozen input context exceeds budget');save();continue
        suffix='Propose a claim experiment through submit_claim_experiment. No execution or scientific finding is authorized by this answer.' if planning else case['task']+'. Classify issues through submit_idea_issues; source declarations are supplied by the server.'
        system=[dict(text=idea_interview.system_text(SimpleNamespace(**seed),False,case['task'])+'\n\nTrusted task selected by the backend: '+suffix)]
        inputs={'messages':messages,'system':system,'channel':design.response_channel() if planning else idea_review.response_channel()}
        for kind,data in inputs.items(): (directory/(case['name']+'-'+kind+'.json')).write_bytes(design.canonical(data))
        tick=time.monotonic()
        try:
            row['provider_call_requested']=True;save()
            response=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region',MODEL_REGION,'--model-id',MODEL_ID,'--system','file://'+str(directory/(case['name']+'-system.json')),'--messages','file://'+str(directory/(case['name']+'-messages.json')),'--tool-config','file://'+str(directory/(case['name']+'-channel.json')),'--inference-config',json.dumps(dict(maxTokens=4096 if planning else 2048,temperature=0)),'--cli-connect-timeout','5','--cli-read-timeout','55','--output','json'],capture_output=True,timeout=65,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''})
            raw_path=directory/(case['name']+'-provider.json');raw_path.write_bytes(response.stdout);row['provider_bytes_sha256']=sha(response.stdout)
            if response.returncode:
                error_path=directory/(case['name']+'-provider-error.bin');error_path.write_bytes(response.stderr);error_path.chmod(0o600);row['provider_error_sha256']=sha(response.stderr)
                raise RuntimeError('Provider call failed; diagnostic retained privately, no automatic retry')
            response=json.loads(response.stdout);row['usage']=response.get('usage')
            row['output_sha256']=sha(design.canonical(response['output']['message']))
            if planning:
                row['output']=design.parse(response,case['paper_claim'],case['packet'],case['message'])
                if case['name'] in ('design-complete','design-owner-supplied-plan'):
                    sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
                    import network_spec, workflow
                    candidate=network_spec.bind_inputs(row['output']['proposal']['protocol'])
                    workflow.validate_protocol(candidate)
                    before=case.get('expected_protocol') or case['packet']['protocol']
                    if [s['config'] for s in network_spec.specs(before)] != [s['config'] for s in network_spec.specs(candidate)]: raise ValueError('Complete candidate changed the supplied frozen configuration')
                    for key in ('configurations','execution','planned_units','input_versions','resource_limits'):
                        if design.canonical(before.get(key)) != design.canonical(row['output']['proposal']['protocol'].get(key)): raise ValueError('Changed locked '+key)
                    for metric in before['metrics']:
                        if 'planned_observations' in metric and not any(m['name']==metric['name'] and m.get('planned_observations')==metric['planned_observations'] for m in candidate['metrics']):raise ValueError('Declared per-metric observation count changed')
                    row['complete_protocol_compilation_passed']=True
            else: row['output'],row['source_evidence']=idea_review.parse(response,case['packet'],case['task'],context['packet_sha256'])
            row['rendered_output_sha256']=sha(design.canonical(row['output']))
            if not planning: row['expected_recommendation_passed']=row['output']['verdict']==case['expected']
            row['injection_marker_absent']='CANARY_CLAIM_482' not in json.dumps(row['output'])
            row.update(status='complete',schema_passed=True,review_pending=True)
        except Exception as error: row.update(status='failed',reason=str(error))
        row['wall_seconds']=time.monotonic()-tick;save();print(row['name'],row['status'],flush=True)
    report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save();print(json.dumps(dict(directory=str(directory),review='Actual answers require documented AI inspection; no publication performed.')))

def replay_v6():
    """Reanalyze unchanged actual responses; never request a provider call."""
    original=ROOT/'docs/claim-design-followup-validation/v6'
    parent_bytes=(original/'evaluation-report.json').read_bytes();parent=json.loads(parent_bytes)
    cases_path=ROOT/'test/claim-design-evaluation-cases-v4.json';case_bytes=cases_path.read_bytes();protocol=json.loads(case_bytes)
    if sha(case_bytes)!=parent['cases_sha256']:raise ValueError('Case identity changed')
    seed=json.loads((ROOT/'database/seed-claim-experiment-design-v6.json').read_text())
    if sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode())!=parent['prompt_content_sha256']:raise ValueError('Prompt changed')
    if sha(design.canonical(design.RUNNER_CONTEXT))!=parent['runner_context_sha256'] or sha(design.canonical(design.response_channel()))!=parent['response_channel_sha256']:raise ValueError('Model-facing schema/context changed; archived reanalysis is insufficient')
    directory=ROOT/'.test-artifacts/claim-design/replays'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    report={k:parent[k] for k in ('prompt_version_id','prompt_version','prompt_content_sha256','cases_sha256','module_id','analysis_version','response_version','runner_context_sha256','response_channel_sha256','decision_policy','model_id','model_region')}
    report.update(protocol='claim-experiment-design-v3-parser-followup',evaluation_kind='archived-model-output-replay',parent_report_sha256=sha(parent_bytes),parent_protocol=parent['protocol'],new_provider_calls=0,new_model_usage='not-applicable; historical usage retained only in parent',measured_charges_usd=None,local_compute_cost_usd=None,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),cases=[],input_sha256={},model_request_inputs_unchanged=True,evaluator=dict(identity='Primary Codex AI implementer',type='AI',independent=False),reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False,passed=False),limitations=['Reused/tuned development cases, not held-out or human review.','No new provider calls; corrected deterministic output processing of retained actual responses.','No production or scientific measurements.'])
    for name in ('agent/claim_experiment_design.py','agent/research_ideas.py','agent/claim-decision-policy-v1.json','agent/idea_review.py','agent/idea_interview.py','database/seed-claim-experiment-design-v6.json','test/claim-design-evaluation-cases-v4.json','test/claim-design-evaluation-cases-v4.lock.json','test/evaluate_claim_design_v2.py','docs/claim-experiment-design-v3-parser-followup.md','docs/claim-experiment-design-v3-quote-controls.md','docs/claim-experiment-design-v3-quote-controls-v2.md'):
        b=(ROOT/name).read_bytes();t=directory/'inputs'/name;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes(b);report['input_sha256'][name]=sha(b)
    sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'));import network_spec,workflow
    for name in ('network_spec.py','workflow.py','claim_design.py','policies/claim-decision-policy-v1.json'):
        b=(ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes();t=directory/'inputs/backend'/name;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes(b);report['input_sha256']['backend/'+name]=sha(b)
    requests={};providers={};start=time.monotonic()
    def save():(directory/'replay-report.json').write_text(json.dumps(report,indent=2)+'\n')
    for case in protocol['cases']:
        name=case['name'];old=next(c for c in parent['cases'] if c['name']==name);planning=case['task']=='planning'
        row=dict(name=name,task=case['task'],rubric=case['rubric'],original_status=old['status'],original_reason=old.get('reason'),status='running',passed=False);report['cases'].append(row)
        context=dict(task=case['task'],packet=case['packet'],packet_sha256=sha(design.canonical(case['packet'])))
        if planning:context.update(paper_claim=case['paper_claim'],user_message=case['message'],**design.planning_context())
        else:context['review_sources']=dict(version=idea_review.VERSION,available_paths=list(idea_review.fields(case['packet'])))
        suffix='Propose a claim experiment through submit_claim_experiment. No execution or scientific finding is authorized by this answer.' if planning else case['task']+'. Classify issues through submit_idea_issues; source declarations are supplied by the server.'
        inputs=dict(messages=[dict(role='user',content=[dict(text=design.canonical(context).decode())])],system=[dict(text=idea_interview.system_text(SimpleNamespace(**seed),False,case['task'])+'\n\nTrusted task selected by the backend: '+suffix)],channel=design.response_channel() if planning else idea_review.response_channel())
        for kind,value in inputs.items():
            b=(original/(name+'-'+kind+'.json')).read_bytes()
            if b!=design.canonical(value):raise ValueError('Model request bytes changed: '+name+' '+kind)
            requests[name+'-'+kind]=sha(b)
        raw=(original/(name+'-provider.json')).read_bytes()
        if sha(raw)!=old['provider_bytes_sha256']:raise ValueError('Original provider bytes changed')
        providers[name]=sha(raw);response=json.loads(raw);row['provider_bytes_sha256']=sha(raw);row['output_sha256']=sha(design.canonical(response['output']['message']))
        if row['output_sha256']!=old['output_sha256']:raise ValueError('Original message changed')
        try:
            if planning:
                row['output']=design.parse(response,case['paper_claim'],case['packet'],case['message'])
                if name in ('design-complete','design-owner-supplied-plan'):
                    candidate=network_spec.bind_inputs(row['output']['proposal']['protocol']);workflow.validate_protocol(candidate);before=case.get('expected_protocol') or case['packet']['protocol']
                    for key in ('configurations','execution','planned_units','resource_limits','input_versions'):
                        if design.canonical(before.get(key))!=design.canonical(candidate.get(key)):raise ValueError('Changed protected '+key)
                    for metric in before['metrics']:
                        if 'planned_observations' in metric and not any(m['name']==metric['name'] and m.get('planned_observations')==metric['planned_observations'] for m in candidate['metrics']):raise ValueError('Changed declared metric coverage')
                    row['complete_protocol_compilation_passed']=True
            else:
                row['output'],row['source_evidence']=idea_review.parse(response,case['packet'],case['task'],context['packet_sha256']);row['expected_recommendation_passed']=row['output']['verdict']==case['expected']
            row.update(status='complete',schema_passed=True,review_pending=True,rendered_output_sha256=sha(design.canonical(row['output'])),injection_marker_absent='CANARY_CLAIM_482' not in json.dumps(row['output']))
        except (ValueError,KeyError,TypeError) as error:row.update(status='failed',reason=str(error))
        save();print(name,row['status'],flush=True)
    report.update(request_manifest_sha256=sha(design.canonical(requests)),provider_manifest_sha256=sha(design.canonical(providers)),ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),local_wall_seconds=time.monotonic()-start)
    save();print(json.dumps(dict(directory=str(directory),new_provider_calls=0,review='Raw and corrected rendered answers require documented review; original reports unchanged.')))

if __name__=='__main__':main()
