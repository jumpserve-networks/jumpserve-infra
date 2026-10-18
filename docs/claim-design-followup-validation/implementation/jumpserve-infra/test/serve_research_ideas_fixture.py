"""Loopback-only actual API/agent/SQL flow with explicit synthetic auth and model.

No legitimate Google session, live provider call or production writes occur.
"""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
import urllib.parse
import os
import argparse
arguments=argparse.ArgumentParser(description=__doc__);arguments.add_argument("--claim-design",action="store_true");mode=arguments.parse_args().claim_design
from unittest.mock import patch
import check_research_ideas_database as f
f.bootstrap()
sys.path.insert(0,str(f.ROOT/'agent'))
import research_ideas as agent
from research_idea_fixtures import packet
import network_execution,worker
import check_network_execution_database as network_fixture
original_advance=network_execution.advance
def diagnostic_advance(*args):
    try:return original_advance(*args)
    except Exception:
        import traceback
        traceback.print_exc()
        raise
network_execution.advance=diagnostic_advance
# Only the fixed known development package can run locally through this fixture.
# No arbitrary uploaded program, container, production endpoint or AWS call.
os.environ['NETWORK_PACKAGE_FUNCTION']='arn:aws:lambda:us-east-1:395567831870:function:local-browser-fixture'
os.environ['NETWORK_EMULATED_FUNCTION']='arn:aws:lambda:us-east-1:395567831870:function:local-browser-fixture-emulated'
os.environ['NETWORK_REAL_WORLD_FUNCTION']='arn:aws:lambda:us-east-1:395567831870:function:local-browser-fixture-real-world'
os.environ['RESEARCH_QUEUE_WORKERS_ENABLED']='true'
network_requests=[]
def fixed_network_provider(spec,job,action):
    if spec['runner']!='custom-package-v1' or spec['config']['package'].get('sha256')!=f.workflow.digest(network_fixture.SOURCE.read_bytes()) or spec['config']['parameters']!={'url':'http://127.0.0.1:4103/fixture-network-target','requests':3} or spec['config']['arguments']!=[]:
        raise ValueError('This local fixture executes only the fixed reviewed development HTTP package and endpoint.')
    return network_fixture.provider(spec,job,action)
prompt='ba16759e-ff38-4491-ae21-5766261e710b'
# The isolated test publishes a synthetic SQL declaration only. This is not
# passed-off actual model evaluation and cannot affect any remote pointer.
names=['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']
names += ['interview-'+name for name in ('cdn','congestion','known','vague','unknown','untrusted','pilot','complete')]
names += ['review-complete-critic','review-controls-only','review-statistics-only','review-consistent-percent','review-untrusted-metadata']
hash_value=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(prompt))
declaration=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version='research-ideas-v1',prompt_version_id=prompt,prompt_version='research-ideas-v11',prompt_content_sha256=hash_value,model_id='synthetic-browser-provider',cases_sha256='a'*64,cases=[dict(name=n,status='complete',passed=True,output_sha256='b'*64,rendered_sha256='c'*64) for n in names],reviewer=dict(identity='Synthetic browser fixture, not actual evaluation',type='AI',independent=False,passed=True))
f.rpc('publish_agent_prompt',dict(p_version_id=prompt,p_expected_active_version_id=None,p_expected_content_sha256=hash_value,p_report=declaration,p_actor='Software fixture',p_module_id='research-verification'))
claim_fixture={}
if mode:
    import claim_design
    seed=json.loads((f.ROOT/'database/seed-claim-experiment-design-v6.json').read_text())
    claim_prompt=seed['id'];h=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(claim_prompt))
    names=['design-networking','design-missing-data','design-equipment','design-causal','design-units','design-injection','design-missing-source','design-complete','review-comprehension','review-complete','review-units','review-injection']
    report=dict(declaration,module_id='research-claim-design',analysis_version=claim_design.VERSION,prompt_version_id=claim_prompt,prompt_version=seed['version'],prompt_content_sha256=h,cases=[dict(name=n,status='complete',passed=True,output_sha256='b'*64) for n in names])
    report.update(protocol='claim-experiment-design-protocol-v3',decision_policy=claim_design.POLICY_IDENTITY,cases_sha256=json.loads((f.ROOT/'test/claim-design-evaluation-cases-v4.lock.json').read_text())['sha256'],evaluator=dict(identity='Synthetic local fixture',type='AI',independent=False),cases=[dict(name=c['name'],status='complete',passed=True,raw_answer_reviewed=True,rendered_answer_reviewed=True,output_sha256='b'*64) for c in json.loads((f.ROOT/'test/claim-design-evaluation-cases-v4.json').read_text())['cases']])
    sys.path.insert(0,str(f.ROOT/'agent'));import claim_experiment_design as model_design
    report.update(response_version=model_design.RESPONSE_VERSION,runner_context_sha256=f.workflow.digest(model_design.canonical(model_design.RUNNER_CONTEXT)),response_channel_sha256=f.workflow.digest(model_design.canonical(model_design.response_channel())),input_sha256={n:f.workflow.digest((f.ROOT/n).read_bytes()) for n in ('agent/claim_experiment_design.py','agent/research_ideas.py')})
    for row in report['cases']:row['rendered_output_sha256']='c'*64
    report=json.loads((f.ROOT/'docs/claim-design-followup-validation/v6-replay-exact-final/evaluation-reviewed.json').read_text())
    f.rpc('publish_agent_prompt',dict(p_version_id=claim_prompt,p_expected_active_version_id=None,p_expected_content_sha256=h,p_report=report,p_actor='Synthetic browser fixture only',p_module_id='research-claim-design'))
    study=f.uid();src=f.uid();claim=f.uid()
    f.store.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=f.workflow.paper_details(dict(title='Claim design browser software fixture',domain='Networking software verification',scope='Synthetic paper-shaped claim; no scientific findings',study_kind='paper',paper_url='https://example.org/claim-design-software-fixture'))))
    source=dict(id=src,citation='Synthetic networking claim fixture',source_url='https://example.org/claim-design-software-fixture',retrieved_url=None,kind='software-fixture',role='Software contract test',retrieved_version='fixture-v1',sha256='a'*64,byte_count=1,access_status='retrieved',review_status='retrieved-unreviewed',review_definition='No actual paper reviewed',examined='Metadata fixture',unexamined='No real full text',retrieval_attempts=[],reviewer=dict(identity='Software fixture',type='AI',independence='Not independent'),findings='None; synthetic source',limitations='No scientific evidence')
    c=dict(id=claim,source_id=src,location='Fixture claim 1',description='Under fixed emulated conditions, the cubic flow completes in a finite number of milliseconds.',claim_type='operational',scope={},metrics=[dict(name='flow_completion_time_ms',units='ms')],priority=3)
    f.store.append_bundle(study,f.ACTOR,[dict(kind='sources',record=source),dict(kind='claims',record=c)])
    proto=network_fixture.document();proto.update(stage='pilot',experiment_type='new-measurement',hypotheses=c['description']);proto['input_versions'].append(dict(identity='Original source',sha256='a'*64))
    claim_plan=dict({field:'Explicit bounded software fixture plan; no scientific findings or population inference.' for field in f.ideas.FIELDS},hypothesis=c['description'],protocol=proto)
    claim_plan['protocol'].update(decision_policy=claim_design.POLICY_IDENTITY,statistics=claim_design.POLICY['statistics'])
    claim_plan['falsification']=claim_design.POLICY['decision_rule']
    claim_fixture=dict(study_id=study,claim_id=claim,plan=claim_plan)

class Database:
    url='https://regphejnlvfpyokpniny.supabase.co'
    def get(self,table,params):
        if table=='rpc/get_active_agent_prompt':
            return json.loads(f.query("select coalesce(json_agg(t),'[]') from public.get_active_agent_prompt("+f.sql_text(params['p_module_id'])+")t",role='service_role'))
        if table not in ('research_study_owners','research_studies','research_idea_packets','research_idea_sessions','agent_sessions','research_claim_designs'):raise ValueError('Fixed fixture tables only')
        params=dict(params);columns=params.pop('select').split(',');limit=int(params.pop('limit',100))
        if any(not c.replace('_','').isalnum() for c in columns):raise ValueError('Unsafe projection')
        conditions=[]
        for k,v in params.items():
            if k not in ('id','study_id','owner_id','session_id') or not v.startswith('eq.'):raise ValueError('Fixed equality scope only')
            conditions.append(k+'='+f.sql_text(v[3:]))
        return json.loads(f.query("select coalesce(json_agg(t),'[]') from (select "+','.join(columns)+' from '+table+' where '+(' and '.join(conditions) or 'true')+' limit '+str(limit)+')t',role='service_role'))
    def rpc(self,name,payload):return f.rpc(name,payload)
failed_critic=set()

def invoke(system,messages,**options):
    context=json.loads(messages[-1]['content'][0]['text']);task=context['task'];doc=context['packet']
    if task=='critic' and context['packet_id'] not in failed_critic:
        failed_critic.add(context['packet_id']);raise TimeoutError('Deliberate synthetic provider failure')
    missing=f.ideas.completeness(doc)
    output=dict(summary='Synthetic AI response for software flow verification; no experiment executed.',questions=['Complete the missing plan fields.'] if missing else [],findings=[],verdict='needs-clarification' if missing else 'ready')
    if task=='critic' and (doc.get('protocol') or {}).get('dependence')=='SOFTWARE-FIXTURE-BLOCKING-DEPENDENCE':
        output=dict(summary='Synthetic critical review fixture: dependence needs a correction.',questions=['How will related observations be handled?'],findings=[dict(severity='blocking',field='dependence',message='Explicit software fixture blocker; revise the dependence declaration before readiness.')],verdict='needs-clarification')
    channel=agent.RESPONSE_CHANNEL
    if options.get('source_review'):
        issues=[]
        if missing:issues=[dict(code='clarification',severity='blocking',references=['/protocol'])]
        if task=='critic' and (doc.get('protocol') or {}).get('dependence')=='SOFTWARE-FIXTURE-BLOCKING-DEPENDENCE':
            issues=[dict(code='dependence',severity='blocking',references=['/protocol/dependence'])]
        if task=='critic' and (doc.get('protocol') or {}).get('statistics')=='Bootstrap 100 repeats of the same deterministic input as independent samples to claim a population confidence interval.':
            issues=[dict(code='dependence',severity='blocking',references=['/protocol/statistics','/protocol/replication_unit'])]
        output=dict(issues=issues);channel=agent.idea_review.CHANNEL
    if options.get('interview'):
        focus=context['interview'].get('preferred_field') or ('design' if doc.get('conditions') else 'conditions')
        question='For your CDN header-and-timing study, which providers, probe region and recent-request window will you test?' if focus=='conditions' else 'For those CDN objects and that window, how will you assign zero versus one prior request while keeping the probe identical?'
        if 'Question for the guide:' in context['user_message']:question='For your CDN comparison, could you use owner-controlled test objects and randomized zero-versus-one request assignments?'
        if 'SOFTWARE-FIXTURE-INVALID-INTERVIEW' in context['user_message']:focus='execute'
        output=dict(summary='Synthetic tailored response for software verification; not an actual model assessment.',question=question,field=focus)
        channel=agent.idea_interview.CHANNEL
    if options.get('design'):
        complete='confirm' in context['user_message'].lower()
        proposed={k:v for k,v in claim_plan.items() if k!='falsification'} if complete else None
        if complete:
            proposed['protocol']={k:v for k,v in claim_plan['protocol'].items() if k not in ('statistics','decision_policy')}
            proposed['protocol']['metrics']=[{k:v for k,v in metric.items() if k not in ('criterion','tolerance_absolute','tolerance_relative')} for metric in claim_plan['protocol']['metrics']]
        output=dict(mode='propose' if complete else 'clarify',guidance=[],unit_values=[],clarification_questions=[] if complete else ['Can you confirm the 1 MB cubic flow, 10 ms delay and 100 Mbit/s bottleneck for this pilot?'],proposal=proposed)
        if '200 microseconds' in context['user_message']:
            output.update(mode='clarify',guidance=['units'],unit_values=[dict(value=.2,unit='ms',source_quote='200 microseconds'),dict(value=.2,unit='ms',source_quote='0.2 milliseconds')],clarification_questions=['Which workload and bottleneck will this comparison use?'],proposal=None)
        channel=agent.claim_design.CHANNEL
    return dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(toolUseId='fixture',name=channel,input=output))])),stopReason='tool_use',usage=dict(inputTokens=10,outputTokens=20))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,status,data):
        raw=json.dumps(data,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.end_headers();self.wfile.write(raw)
    def do_OPTIONS(self):self.respond(200,{})
    def do_GET(self):self.process('GET')
    def do_POST(self):self.process('POST')
    def process(self,method):
        parsed=urllib.parse.urlsplit(self.path)
        if parsed.path=='/fixture-metadata':return self.respond(200,dict(actor=f.ACTOR,database=f.DATABASE,packet=packet(),network_package_source=network_fixture.SOURCE.read_text(),network_requests=len(network_requests),claim_design=claim_fixture,design='Synthetic auth/provider/AWS; actual component/API/agent/isolated PostgreSQL and fixed local HTTP package'))
        if parsed.path=='/fixture-network-target' and method=='GET':network_requests.append(self.path);return self.respond(200,dict(fixture='actual loopback HTTP response'))
        if self.headers.get('Authorization')!='Bearer explicit-software-fixture':return self.respond(401,dict(error='Synthetic fixture sign-in required'))
        raw=self.rfile.read(int(self.headers.get('Content-Length','0'))).decode() if method=='POST' else '{}'
        if len(raw.encode())>512000:return self.respond(413,dict(error='Fixture request too large'))
        try:
            if parsed.path=='/fixture-network-poll' and method=='POST':
                with patch.object(network_execution,'invoke',side_effect=fixed_network_provider):result=worker.handler({'source':'fixed local development poll'})
            elif parsed.path=='/idea-model':
                data=json.loads(raw)
                if data.get('action')=='capabilities':return self.respond(200,dict(research_ideas=dict(version=agent.VERSION,interview_version=agent.idea_interview.VERSION,claim_design_version=agent.claim_design.VERSION)))
                result=agent.handle(data,dict(id=f.ACTOR,email='software-fixture@example.invalid'),Database(),invoke)
            else:
                event=dict(rawPath=parsed.path,body=raw,requestContext=dict(http=dict(method=method)),queryStringParameters=dict(urllib.parse.parse_qsl(parsed.query)))
                result=f.api.dispatch(event,f.ACTOR)
            self.respond(200,result)
        except Exception as error:self.respond(getattr(error,'status',400),dict(error=str(error)))

print(json.dumps(dict(port=4103,database=f.DATABASE,actor=f.ACTOR,synthetic_auth=True,synthetic_model=True)),flush=True)
ThreadingHTTPServer(('127.0.0.1',4103),Handler).serve_forever()
