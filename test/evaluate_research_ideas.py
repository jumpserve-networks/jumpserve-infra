"""Predeclared, bounded actual-answer development evaluations; no DB writes."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from research_ideas import canonical, parse_response, response_channel, VERSION, MAX_OUTPUT_TOKENS
from settings import MODEL_ID, MODEL_REGION

def digest(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--interview',action='store_true');parser.add_argument('--source-review',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('--live is required for these bounded billed calls')
    account=subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--query','Account','--output','text'],text=True).strip()
    if account!='395567831870':raise RuntimeError('Wrong AWS account')
    if json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Wrong Supabase project')
    seed_path=ROOT/'database'/('seed-research-ideas-prompt-v11.json' if args.source_review else 'seed-research-ideas-prompt-v8.json' if args.interview else 'seed-research-ideas-prompt-v2.json');seed=json.loads(seed_path.read_text())
    protocol_path=ROOT/'test'/('idea-review-source-cases-v1.json' if args.source_review else 'idea-interview-evaluation-cases-v1.json' if args.interview else 'research-idea-evaluation-cases-v2.json');protocol=json.loads(protocol_path.read_text())
    lock=json.loads(protocol_path.with_suffix('.lock.json').read_text())
    if digest(protocol_path.read_bytes())!=lock['sha256']:raise RuntimeError('Frozen cases changed; preserve and amend the protocol')
    directory=ROOT/'.test-artifacts/research-ideas/evaluations'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True,exist_ok=False)
    text=seed['system_prompt']+'\n\n'+seed['research_context']
    report=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version=VERSION,
        prompt_version_id=seed['id'],prompt_version=seed['version'],prompt_content_sha256=digest(text.encode()),
        seed_original_sha256=digest(seed_path.read_bytes()),cases_sha256=lock['sha256'],model_id=MODEL_ID,model_region=MODEL_REGION,
        evaluator=dict(identity='Primary Codex AI implementer',type='AI',independent=False),
        reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False,passed=False),
        limits=protocol['limits'],started_at=dt.datetime.now(dt.timezone.utc).isoformat(),cases=[],
        runtime_hashes={name:digest((ROOT/name).read_bytes()) for name in ('agent/research_ideas.py','agent/idea_interview.py','agent/idea_review.py','agent/handler.py','agent/prompt.py','agent/modules.py','agent/settings.py')},
        measured_charges_usd=None,estimated_model_cost_usd=None,
        limitations=['Development cases exposed to implementer; no held-out or human validation.','Synthetic planning inputs; model outputs are not empirical research measurements.','No production Supabase writes, prompt publication or Google-authenticated owner request.','AWS CLI Converse exercises the same provider API/messages; Google auth and persistence are separate software tests.','Missing costs/failed-call usage are not zero.'],supabase_project='regphejnlvfpyokpniny')
    def save(): (directory/'evaluation-report.json').write_text(json.dumps(report,indent=2)+'\n')
    for name in report["runtime_hashes"]:
        target=directory/"runtime"/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
    save();started=time.monotonic()
    for case in protocol['cases']:
        row=dict(name=case['name'],task=case['task'],rubric=case['rubric'],status='running',passed=False);report['cases'].append(row);save()
        if time.monotonic()-started>=protocol['limits']['wall_seconds']:row.update(status='excluded',reason='Frozen wall-time budget exhausted');save();continue
        context=dict(task=case['task'],packet=case['packet'],packet_id=str(uuid4()),packet_version=1,packet_sha256=digest(canonical(case['packet'])),user_message=case['message'])
        if case["task"] != "planning": context.pop("user_message")
        import idea_interview, idea_review
        source_review=args.source_review and case["task"] in ("comprehension","critic")
        if source_review:context["review_sources"]=dict(version=idea_review.VERSION,available_paths=list(idea_review.fields(case["packet"])))
        if case.get('interview'):context['interview']=dict(version=idea_interview.VERSION,preferred_field=case.get('preferred_field'),allowed_fields=list(idea_interview.FIELDS))
        messages=[{'role':'user','content':[{'text':canonical(context).decode()}]}]
        suffix=case['task']+'. Classify issues through submit_idea_issues; source declarations are supplied by the server.' if source_review else 'planning interview. Submit exactly one tailored question through submit_idea_question.' if case.get('interview') else case['task']+'. Submit exactly one structured review through submit_idea_review.'
        from types import SimpleNamespace
        selected=idea_interview.system_text(SimpleNamespace(version=seed['version'],system_prompt=seed['system_prompt'],research_context=seed['research_context'],text=text),bool(case.get('interview')),case["task"])
        system=[{'text':selected+'\n\nTrusted task selected by the backend: '+suffix}]
        system_path=directory/(case['name']+'-system.json');system_path.write_bytes(canonical(system))
        input_path=directory/(case['name']+'-input.json');input_path.write_bytes(canonical(messages));row['input_sha256']=digest(input_path.read_bytes())
        channel_path=directory/(case['name']+'-channel.json');channel_path.write_bytes(canonical(idea_review.response_channel() if source_review else idea_interview.response_channel() if case.get("interview") else response_channel()))
        if args.source_review:time.sleep(3)
        tick=time.monotonic()
        try:
            result=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region',MODEL_REGION,'--model-id',MODEL_ID,
                '--system','file://'+str(system_path),'--messages','file://'+str(input_path),'--tool-config','file://'+str(channel_path),'--inference-config',json.dumps({'maxTokens':MAX_OUTPUT_TOKENS,'temperature':0}),
                '--cli-connect-timeout','5','--cli-read-timeout','55','--output','json'],capture_output=True,timeout=65,
                env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''})
            (directory/(case['name']+'-provider.json')).write_bytes(result.stdout)
            if result.returncode:
                diagnostic=directory/(case['name']+'-provider-error.bin');diagnostic.write_bytes(result.stderr);diagnostic.chmod(0o600)
                row['provider_error_sha256']=digest(result.stderr)
                known=('ThrottlingException','ExpiredTokenException','AccessDeniedException','ServiceUnavailableException','ValidationException','ModelTimeoutException','read timeout','Could not connect')
                row['provider_error_class']=next((name for name in known if name.lower() in result.stderr.decode(errors='replace').lower()),'unclassified')
                raise RuntimeError('Provider CLI call failed ('+row['provider_error_class']+'); original diagnostic retained privately')
            response=json.loads(result.stdout);raw=canonical(response['output']['message']).decode()
            raw_path=directory/(case['name']+'-output.txt');raw_path.write_bytes(raw.encode());row['output_sha256']=digest(raw_path.read_bytes())
            row['usage']=response.get('usage');row['provider_stop_reason']=response.get('stopReason')
            if source_review:
                row['output'],row['source_evidence']=idea_review.parse(response,case['packet'],case['task'],context['packet_sha256'])
                parse_response(dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(name='submit_idea_review',input=row['output']))])),stopReason='tool_use'),case['task'])
                # Independent path traversal checks the renderer, sharing only the original packet.
                for field in row['source_evidence']['fields']:
                    if not field['present']:continue
                    actual=case['packet']
                    for part in field['path'].lstrip('/').split('/'):actual=actual[part]
                    if field['value']!=actual or field['value_sha256']!=digest(canonical(actual)):raise ValueError('Source evidence failed independent exact-value verification')
                required=case.get('required_reference')
                cited={ref for issue in row['source_evidence']['issues'] for ref in issue['references']}
                row['required_reference_passed']=not required or required in cited
            else:row['output']=idea_interview.parse(response,case.get('preferred_field')) if case.get('interview') else parse_response(response,case['task'])
            rendered=directory/(case['name']+'-rendered.json');rendered.write_bytes(canonical(dict(output=row['output'],source_evidence=row.get('source_evidence'))));row['rendered_sha256']=digest(rendered.read_bytes())
            row['schema_passed']=True
            row['expected_recommendation_passed']=case['expected'] is None or row['output']['verdict']==case['expected']
            row['injection_marker_absent']='CANARY_IDEA_971' not in raw
            row['status']='complete';row['review_pending']=True
        except Exception as error:row.update(status='failed',reason=str(error),usage=row.get('usage'))
        row['wall_seconds']=time.monotonic()-tick;save();print(row['name'],row['status'],flush=True)
    report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();save()
    print(json.dumps({'directory':str(directory),'calls':len(report['cases']),'review_status':'Actual answers require recorded implementer AI inspection before publication; no human or held-out review asserted.'}))
    if any(row['status']!='complete' for row in report['cases']):sys.exit(1)

if __name__=='__main__':main()
