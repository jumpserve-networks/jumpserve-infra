"""Loopback-only actual API/agent/SQL flow with explicit synthetic auth and model.

No legitimate Google session, live provider call or production writes occur.
"""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
import urllib.parse
import os
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
prompt='e5c9b8f7-2dd2-4bfa-934c-fae73a9c09d8'
# The isolated test publishes a synthetic SQL declaration only. This is not
# passed-off actual model evaluation and cannot affect any remote pointer.
names=['idea-planning','idea-comprehension','idea-critic','idea-missing','idea-novelty','idea-untrusted','idea-clear-plan','idea-scope']
hash_value=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(prompt))
declaration=dict(evaluation_kind='actual-model-development',module_id='research-verification',analysis_version='research-ideas-v1',prompt_version_id=prompt,prompt_version='research-ideas-v2',prompt_content_sha256=hash_value,model_id='synthetic-browser-provider',cases_sha256='a'*64,cases=[dict(name=n,status='complete',passed=True,output_sha256='b'*64) for n in names],reviewer=dict(identity='Synthetic browser fixture, not actual evaluation',type='AI',independent=False,passed=True))
f.rpc('publish_agent_prompt',dict(p_version_id=prompt,p_expected_active_version_id=None,p_expected_content_sha256=hash_value,p_report=declaration,p_actor='Software fixture',p_module_id='research-verification'))
class Database:
    url='https://regphejnlvfpyokpniny.supabase.co'
    def get(self,table,params):
        if table=='rpc/get_active_agent_prompt':
            return json.loads(f.query("select coalesce(json_agg(t),'[]') from public.get_active_agent_prompt('research-verification')t",role='service_role'))
        if table not in ('research_study_owners','research_studies','research_idea_packets','research_idea_sessions','agent_sessions'):raise ValueError('Fixed fixture tables only')
        params=dict(params);columns=params.pop('select').split(',');limit=int(params.pop('limit',100))
        if any(not c.replace('_','').isalnum() for c in columns):raise ValueError('Unsafe projection')
        conditions=[]
        for k,v in params.items():
            if k not in ('id','study_id','owner_id','session_id') or not v.startswith('eq.'):raise ValueError('Fixed equality scope only')
            conditions.append(k+'='+f.sql_text(v[3:]))
        return json.loads(f.query("select coalesce(json_agg(t),'[]') from (select "+','.join(columns)+' from '+table+' where '+(' and '.join(conditions) or 'true')+' limit '+str(limit)+')t',role='service_role'))
    def rpc(self,name,payload):return f.rpc(name,payload)
failed_critic=set()

def invoke(system,messages):
    context=json.loads(messages[-1]['content'][0]['text']);task=context['task'];doc=context['packet']
    if task=='critic' and context['packet_id'] not in failed_critic:
        failed_critic.add(context['packet_id']);raise TimeoutError('Deliberate synthetic provider failure')
    missing=f.ideas.completeness(doc)
    output=dict(summary='Synthetic AI response for software flow verification; no experiment executed.',questions=['Complete the missing plan fields.'] if missing else [],findings=[],verdict='needs-clarification' if missing else 'ready')
    if task=='critic' and (doc.get('protocol') or {}).get('dependence')=='SOFTWARE-FIXTURE-BLOCKING-DEPENDENCE':
        output=dict(summary='Synthetic critical review fixture: dependence needs a correction.',questions=['How will related observations be handled?'],findings=[dict(severity='blocking',field='dependence',message='Explicit software fixture blocker; revise the dependence declaration before readiness.')],verdict='needs-clarification')
    return dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(toolUseId='fixture',name=agent.RESPONSE_CHANNEL,input=output))])),stopReason='tool_use',usage=dict(inputTokens=10,outputTokens=20))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,status,data):
        raw=json.dumps(data,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.end_headers();self.wfile.write(raw)
    def do_OPTIONS(self):self.respond(200,{})
    def do_GET(self):self.process('GET')
    def do_POST(self):self.process('POST')
    def process(self,method):
        parsed=urllib.parse.urlsplit(self.path)
        if parsed.path=='/fixture-metadata':return self.respond(200,dict(actor=f.ACTOR,database=f.DATABASE,packet=packet(),network_package_source=network_fixture.SOURCE.read_text(),network_requests=len(network_requests),design='Synthetic auth/provider/AWS; actual component/API/agent/isolated PostgreSQL and fixed local HTTP package'))
        if parsed.path=='/fixture-network-target' and method=='GET':network_requests.append(self.path);return self.respond(200,dict(fixture='actual loopback HTTP response'))
        if self.headers.get('Authorization')!='Bearer explicit-software-fixture':return self.respond(401,dict(error='Synthetic fixture sign-in required'))
        raw=self.rfile.read(int(self.headers.get('Content-Length','0'))).decode() if method=='POST' else '{}'
        if len(raw.encode())>512000:return self.respond(413,dict(error='Fixture request too large'))
        try:
            if parsed.path=='/fixture-network-poll' and method=='POST':
                with patch.object(network_execution,'invoke',side_effect=fixed_network_provider):result=worker.handler({'source':'fixed local development poll'})
            elif parsed.path=='/idea-model':
                data=json.loads(raw)
                if data.get('action')=='capabilities':return self.respond(200,dict(research_ideas=dict(version=agent.VERSION)))
                result=agent.handle(data,dict(id=f.ACTOR,email='software-fixture@example.invalid'),Database(),invoke)
            else:
                event=dict(rawPath=parsed.path,body=raw,requestContext=dict(http=dict(method=method)),queryStringParameters=dict(urllib.parse.parse_qsl(parsed.query)))
                result=f.api.dispatch(event,f.ACTOR)
            self.respond(200,result)
        except Exception as error:self.respond(getattr(error,'status',400),dict(error=str(error)))

print(json.dumps(dict(port=4103,database=f.DATABASE,actor=f.ACTOR,synthetic_auth=True,synthetic_model=True)),flush=True)
ThreadingHTTPServer(('127.0.0.1',4103),Handler).serve_forever()
