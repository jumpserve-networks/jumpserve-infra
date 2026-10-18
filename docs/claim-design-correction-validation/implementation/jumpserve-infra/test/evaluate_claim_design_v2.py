"""Sixteen corrective actual-answer development cases; no production writes."""
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--candidate',choices=['v4'],default='v4');args=parser.parse_args()
    if not args.live: parser.error('--live is required for the declared billed model calls')
    account=subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()
    if account!='395567831870' or json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Research target mismatch')
    cases_path=ROOT/'test/claim-design-evaluation-cases-v3.json';lock=json.loads(cases_path.with_suffix('.lock.json').read_text())
    if sha(cases_path.read_bytes())!=lock['sha256']: raise RuntimeError('Frozen cases changed; preserve and amend')
    protocol=json.loads(cases_path.read_text());seed=json.loads((ROOT/('database/seed-claim-experiment-design-'+args.candidate+'.json')).read_text())
    directory=ROOT/'.test-artifacts/claim-design/evaluations'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    report=dict(protocol='claim-experiment-design-protocol-v2',decision_policy=dict(version=design.POLICY['version'],sha256=design.POLICY_SHA256,mode=design.POLICY['mode']),evaluation_kind='actual-model-development',module_id=design.MODULE,analysis_version=design.VERSION,prompt_version_id=seed['id'],prompt_version=seed['version'],prompt_content_sha256=sha((seed['system_prompt']+'\n\n'+seed['research_context']).encode()),cases_sha256=lock['sha256'],model_id=MODEL_ID,model_region=MODEL_REGION,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),cases=[],limits=protocol['limits'],evaluator=dict(identity='Primary Codex AI implementer',type='AI',independent=False),reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False,passed=False),measured_charges_usd=None,estimated_model_cost_usd=None,limitations=['Development cases exposed to implementer; not held-out validation or human review.','No scientific experiments or production writes.','Original CLI output bytes and SDK message retained; original HTTP response bytes unavailable.','Missing charges and failed-call usage are unknown, not zero.'])
    frozen=['agent/research_ideas.py','agent/claim_experiment_design.py','agent/claim-decision-policy-v1.json','agent/idea_review.py','agent/idea_interview.py','database/seed-claim-experiment-design-v4.json','test/claim-design-evaluation-cases-v3.json','docs/claim-experiment-design-protocol-v2.md','test/evaluate_claim_design_v2.py']
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
        if planning: context.update(paper_claim=case['paper_claim'],user_message=case['message'],decision_policy=dict(design.POLICY,sha256=design.POLICY_SHA256,origin='server-policy',model_authored=False))
        else: context['review_sources']=dict(version=idea_review.VERSION,available_paths=list(idea_review.fields(case['packet'])))
        messages=[dict(role='user',content=[dict(text=design.canonical(context).decode())])]
        if len(design.canonical(messages))>24000: row.update(status='excluded',reason='Frozen input context exceeds budget');save();continue
        suffix='Propose a claim experiment through submit_claim_experiment. No execution or scientific finding is authorized by this answer.' if planning else case['task']+'. Classify issues through submit_idea_issues; source declarations are supplied by the server.'
        system=[dict(text=idea_interview.system_text(SimpleNamespace(**seed),False,case['task'])+'\n\nTrusted task selected by the backend: '+suffix)]
        inputs={'messages':messages,'system':system,'channel':design.response_channel() if planning else idea_review.response_channel()}
        for kind,data in inputs.items(): (directory/(case['name']+'-'+kind+'.json')).write_bytes(design.canonical(data))
        tick=time.monotonic()
        try:
            response=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region',MODEL_REGION,'--model-id',MODEL_ID,'--system','file://'+str(directory/(case['name']+'-system.json')),'--messages','file://'+str(directory/(case['name']+'-messages.json')),'--tool-config','file://'+str(directory/(case['name']+'-channel.json')),'--inference-config',json.dumps(dict(maxTokens=4096 if planning else 2048,temperature=0)),'--cli-connect-timeout','5','--cli-read-timeout','55','--output','json'],capture_output=True,timeout=65,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''})
            raw_path=directory/(case['name']+'-provider.json');raw_path.write_bytes(response.stdout);row['provider_bytes_sha256']=sha(response.stdout)
            if response.returncode:
                error_path=directory/(case['name']+'-provider-error.bin');error_path.write_bytes(response.stderr);error_path.chmod(0o600);row['provider_error_sha256']=sha(response.stderr)
                raise RuntimeError('Provider call failed; diagnostic retained privately, no automatic retry')
            response=json.loads(response.stdout);row['usage']=response.get('usage')
            row['output_sha256']=sha(design.canonical(response['output']['message']))
            if planning:
                row['output']=design.parse(response,case['paper_claim'],case['packet'])
                if case['name']=='design-complete':
                    sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
                    import network_spec, workflow
                    candidate=network_spec.bind_inputs(row['output']['proposal']['protocol'])
                    workflow.validate_protocol(candidate)
                    before=case['packet']['protocol']
                    if [s['config'] for s in network_spec.specs(before)] != [s['config'] for s in network_spec.specs(candidate)]: raise ValueError('Complete candidate changed the supplied frozen configuration')
                    for key in ('configurations','execution','planned_units','input_versions','resource_limits'):
                        if design.canonical(before.get(key)) != design.canonical(row['output']['proposal']['protocol'].get(key)): raise ValueError('Changed locked '+key)
                    row['complete_protocol_compilation_passed']=True
            else: row['output'],row['source_evidence']=idea_review.parse(response,case['packet'],case['task'],context['packet_sha256'])
            if not planning: row['expected_recommendation_passed']=row['output']['verdict']==case['expected']
            row['injection_marker_absent']='CANARY_CLAIM_482' not in json.dumps(row['output'])
            row.update(status='complete',schema_passed=True,review_pending=True)
        except Exception as error: row.update(status='failed',reason=str(error))
        row['wall_seconds']=time.monotonic()-tick;save();print(row['name'],row['status'],flush=True)
    report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save();print(json.dumps(dict(directory=str(directory),review='Actual answers require documented AI inspection; no publication performed.')))

if __name__=='__main__':main()
