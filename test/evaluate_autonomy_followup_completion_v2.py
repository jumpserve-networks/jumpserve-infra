"""Fixed, two-turn development completion campaign; no execution or publication."""
import argparse,copy,datetime as dt,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT.parent/'jumpserve-back-end/research_workflow'
sys.path[:0]=[str(BACKEND),str(BACKEND/'tests')]
import autonomy,autonomy_model as model,workflow
from test_autonomy_followups import Retained
sha=lambda raw:hashlib.sha256(raw).hexdigest()
BASE=ROOT/'.test-artifacts/autonomy-followups/v4'
AMENDMENT=ROOT/'docs/autonomy-bounded-followups-amendment-v6.md'

def prepare():
 BASE.mkdir(parents=True,exist_ok=True)
 destination=BASE/'frozen-inputs.json'
 if destination.exists():raise RuntimeError('Frozen completion campaign already exists; no overwrite')
 original=ROOT/'.test-artifacts/autonomy-followups/v2/frozen-inputs.json';packet=json.loads(original.read_bytes());db=Retained().partial_alternative();a,b,c=db.mocks()
 with a,b,c:context=autonomy.build_context(db.task)
 context['evaluation_only_controlled_mutation']='An exposed development mutation tests prior-discrepancy preservation. This is not a new scientific paper finding.'
 if context['controller_numeric_check']['label']!='discrepant' or context['controller_numeric_check']['coverage']['covered_cells']!=1152:raise RuntimeError('Controlled arithmetic fixture differs')
 fixture=workflow.canonical(dict(task=db.task,compiled=db.compiled,data=db.data,claim=db.claim,jobs=db.jobs));(BASE/'frozen-fixture.json').write_bytes(fixture)
 profile=dict(version='autonomy-followup-completion-v2',amendment=AMENDMENT.name,amendment_sha256=sha(AMENDMENT.read_bytes()),decision_protocol_sha256=sha((ROOT/'docs/autonomy-bounded-followups-amendment-v5.md').read_bytes()),fixture_sha256=sha(fixture),seed=packet['seed'],context=context,input_sha256=packet['input_sha256'],original_frozen_inputs_sha256=sha(original.read_bytes()),producer_sha256=sha(Path(__file__).read_bytes()),maximum_calls=2,maximum_aggregate_reserved_cents=1000,maximum_elapsed_seconds=600,criteria=dict(permitted_actions=['inspect','assess'],coverage_complete=False,readiness=None,conclusive_label_forbidden=True,final_label='inconclusive'))
 for name,digest in profile['input_sha256'].items():
  raw=(BACKEND/name).read_bytes()
  if sha(raw)!=digest:raise RuntimeError('Candidate changed: '+name)
  path=BASE/'inputs/backend'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 for source in (AMENDMENT,ROOT/'docs/autonomy-bounded-followups-amendment-v5.md',Path(__file__),BACKEND/'tests/test_autonomy_followups.py',BACKEND/'tests/test_autonomy.py'):
  name=source.relative_to(ROOT) if source.is_relative_to(ROOT) else Path('backend-tests')/source.name
  path=BASE/'inputs'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.read_bytes())
 destination.write_bytes(workflow.canonical(profile));print(json.dumps(dict(frozen=str(destination),sha256=sha(destination.read_bytes()))))

def live():
 frozen=BASE/'frozen-inputs.json';packet=json.loads(frozen.read_bytes());destination=BASE/'evaluation-report.json'
 if destination.exists():raise RuntimeError('Completion campaign attempted; never replay uncertain calls')
 if sha(AMENDMENT.read_bytes())!=packet['amendment_sha256'] or sha(Path(__file__).read_bytes())!=packet['producer_sha256']:raise RuntimeError('Frozen protocol/producer changed')
 for name,digest in packet['input_sha256'].items():
  if sha((BACKEND/name).read_bytes())!=digest:raise RuntimeError('Frozen implementation changed')
 account=subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve','--region','us-east-1','--query','Account','--output','text'],text=True).strip()
 if account!='395567831870' or json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Fixed account/project differs')
 reserved=sum(json.loads((BASE.parent/v/'evaluation-report.json').read_bytes())['reserved_cents'] for v in ('v1','v2','v3'))
 report=dict(version=packet['version'],protocol_sha256=packet['amendment_sha256'],frozen_inputs_sha256=sha(frozen.read_bytes()),input_sha256=packet['input_sha256'],prompt_version_id=packet['seed']['id'],prompt_version=packet['seed']['version'],maximum_calls=2,live_provider_calls=0,reserved_cents=0,prior_reserved_cents=reserved,cases=[],passed=False,measured_charges_usd=None,reviewer=dict(identity='Primary Codex AI implementer; inspection pending',type='AI',independent=False,passed=False),limitations=['Exposed development follow-up; no independent/human/held-out validation.','Provider HTTP bytes unavailable; original CLI stdout and canonical SDK message bytes retained.','Controlled mutation is not a paper finding.'])
 def save():destination.write_text(json.dumps(report,indent=2)+'\n')
 fixture=(BASE/'frozen-fixture.json').read_bytes()
 if sha(fixture)!=packet['fixture_sha256'] or sha((ROOT/'docs/autonomy-bounded-followups-amendment-v5.md').read_bytes())!=packet['decision_protocol_sha256']:raise RuntimeError('Frozen fixture/decision criteria differ')
 context=copy.deepcopy(packet['context']);db=Retained.__new__(Retained);db.__dict__.update(json.loads(fixture));a,b,c=db.mocks()
 with a,b,c:rebuilt=autonomy.build_context(db.task)
 rebuilt['evaluation_only_controlled_mutation']=context['evaluation_only_controlled_mutation']
 if workflow.canonical(rebuilt)!=workflow.canonical(context):raise RuntimeError('Actual reader state differs from the frozen prompt')
 report['fixture_sha256']=packet['fixture_sha256'];report['decision_protocol_sha256']=packet['decision_protocol_sha256'];began=time.monotonic();save()
 for index in range(2):
  row=dict(name='completion-turn-'+str(index+1),status='pending',passed=False,raw_answer_reviewed=False,rendered_answer_reviewed=False);report['cases'].append(row);save()
  try:
   if time.monotonic()-began>600:raise RuntimeError('Declared elapsed limit')
   request=model.request(packet['seed']['system_prompt']+'\n\n'+packet['seed']['research_context'],context);raw=workflow.canonical(request);cost=model.reservation(request)
   if len(raw)>96000 or reserved+report['reserved_cents']+cost>1000:raise RuntimeError('Declared byte/reservation limit; no call dispatched')
   request_path=BASE/(row['name']+'-request.json');request_path.write_bytes(raw);row['request_sha256']=sha(raw);row['request_bytes']=len(raw);row['reserved_cents']=cost;report['reserved_cents']+=cost;report['live_provider_calls']+=1;row['status']='running';save()
   response=subprocess.run(['aws','bedrock-runtime','converse','--profile','jumpserve','--region','us-east-1','--cli-input-json','file://'+str(request_path),'--cli-connect-timeout','5','--cli-read-timeout','90','--output','json'],capture_output=True,timeout=120,env={**os.environ,'AWS_MAX_ATTEMPTS':'1','AWS_RETRY_MODE':'standard','AWS_PAGER':''})
   (BASE/(row['name']+'-provider.json')).write_bytes(response.stdout);row['provider_response_sha256']=sha(response.stdout)
   if response.returncode:
    path=BASE/(row['name']+'-error.bin');path.write_bytes(response.stderr);path.chmod(0o600);raise RuntimeError('Provider failure; no retry; original diagnostic private')
   value=json.loads(response.stdout);row['usage']=value.get('usage');row['estimated_cents']=model.estimate(row['usage']);message=workflow.canonical(value['output']['message']);(BASE/(row['name']+'-message.json')).write_bytes(message);row['output_sha256']=sha(message)
   answer=model.parse(value)
   if answer['action'] not in model.request_actions(context):raise RuntimeError('Answer violated the actual phase action guard')
   (BASE/(row['name']+'-rendered.json')).write_bytes(workflow.canonical(answer));row['output']=answer
   checks=dict(no_readiness=answer['ready'] is None,no_proposal=answer['proposal'] is None,coverage_false=answer['coverage_complete'] is False,no_paper_conclusion=answer['assessment_label'] not in ('reproduced','discrepant'),permitted_action=answer['action'] in ('inspect','assess'))
   if answer['action']=='assess':checks['final_inconclusive']=answer['assessment_label']=='inconclusive';report['final_inconclusive']=checks['final_inconclusive']
   elif answer['action']=='inspect':
    a,b,c=db.mocks()
    with a,b,c:read=autonomy.inspect_evidence(db.task,answer['read_request'])
    tool=workflow.canonical(read);(BASE/(row['name']+'-tool-result.json')).write_bytes(tool);row['tool_result_sha256']=sha(tool);checks['actual_scoped_reader_accepted']=True
    context['evidence_read']=read
    if index==1:checks['final_inconclusive']=False
   row.update(status='complete',deterministic_checks=checks,passed=all(checks.values()));save();print(json.dumps(dict(name=row['name'],checks=checks)),flush=True)
   if not row['passed'] or answer['action']=='assess':break
  except Exception as error:
   row.update(status='failed',reason=str(error));save();break
 report.update(passed=bool(report.get('final_inconclusive')) and all(c['passed'] for c in report['cases']),known_estimated_cents=sum(c.get('estimated_cents') or 0 for c in report['cases']),missing_usage_calls=sum(c.get('estimated_cents') is None for c in report['cases'] if c.get('request_sha256')),ended_at=dt.datetime.now(dt.timezone.utc).isoformat());save();print(json.dumps(dict(directory=str(BASE),calls=report['live_provider_calls'],passed=report['passed'],review_required=True)))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--live',action='store_true');args=parser.parse_args()
 if args.prepare==args.live:parser.error('Choose prepare or live')
 prepare() if args.prepare else live()
