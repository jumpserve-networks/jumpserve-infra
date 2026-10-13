import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import research_ideas as ideas
from auth import AuthError

ACTOR,STUDY,PACKET,SESSION,PROMPT=(str(uuid4()) for _ in range(5))
USER={'id':ACTOR,'email':'idea-fixture@example.invalid'}
OUTPUT=dict(summary='Explicit development fixture; no scientific finding',questions=[],findings=[],verdict='ready')
class FakeDatabase:
    url='https://regphejnlvfpyokpniny.supabase.co'
    def __init__(self):
        self.calls=[];self.rpc_calls=[];self.owned=True;self.foreign=False;self.replayed=False;self.history=[]
        raw='{"question":"Fixture only","protocol":null}'
        self.packet=dict(id=PACKET,version=1,document=json.loads(raw),raw_document=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())
    def get(self,path,params):
        self.calls.append((path,params))
        if path=='research_study_owners':return [{'study_id':STUDY}] if self.owned else []
        if path=='research_studies':return [{'id':STUDY,'study_kind':'idea'}]
        if path=='research_idea_packets':return [self.packet]
        if path=='research_idea_sessions':return [dict(study_id=STUDY,actor_id=ACTOR,user_id=USER['email'])] if self.history or self.foreign else []
        if path=='agent_sessions':
            if params['select']=='messages':return [{'messages':self.history}]
            return [dict(id=SESSION,user_id='different-user' if self.foreign else USER['email'],module_id='research-verification')] if self.history or self.foreign else []
        raise AssertionError(path)
    def rpc(self,name,payload):
        self.rpc_calls.append((name,copy.deepcopy(payload)))
        if name=='research_begin_idea_run':return dict(id=payload['p_id'],status='complete' if self.replayed else 'running',replayed=self.replayed)
        if name=='research_finish_idea_run':return dict(id=payload['p_id'],status=payload['p_status'],reason=payload['p_reason'],output=payload['p_output'])
        raise AssertionError(name)

def request(task='critic'):
    return dict(action='idea',request_id=str(uuid4()),study_id=STUDY,packet_id=PACKET,task=task,**({'session_id':SESSION,'message':'Challenge my assumptions'} if task=='planning' else {}))
def response(value=OUTPUT):return dict(output={'message':{'role':'assistant','content':[{'toolUse':{'toolUseId':'fixture','name':ideas.RESPONSE_CHANNEL,'input':value}}]}},stopReason='tool_use',usage={'inputTokens':10,'outputTokens':20})
PROMPT_OBJECT=SimpleNamespace(id=PROMPT,version='fixture-v1',content_sha256='a'*64,text='Fixture-only trusted instructions')

class IdeaAgent(unittest.TestCase):
    def setUp(self):self.patch=patch.object(ideas,'load_active_prompt',return_value=PROMPT_OBJECT);self.patch.start();self.addCleanup(self.patch.stop)
    def test_reviews_have_one_packet_message_and_never_load_planning_history(self):
        for task in ('comprehension','critic'):
            db=FakeDatabase();db.history=[{'role':'user','content':[{'text':'PRIVATE_PLANNING_CANARY'}]}]
            seen=[]
            result=ideas.handle(request(task),USER,db,lambda system,messages:(seen.append((system,messages)) or response()))
            self.assertEqual(result['run']['status'],'complete');self.assertEqual(len(seen[0][1]),1)
            self.assertNotIn('PRIVATE_PLANNING_CANARY',json.dumps(seen));self.assertFalse(any(path=='agent_sessions' for path,_ in db.calls))
            begin=db.rpc_calls[0][1];self.assertEqual(begin['p_provenance']['history_messages'],0);self.assertIsNone(begin['p_session'])
    def test_planning_history_is_owner_and_study_scoped_and_retained(self):
        db=FakeDatabase();db.history=[{'role':'user','content':[{'text':'Earlier question'}]},{'role':'assistant','content':[{'text':'Earlier response'}]}]
        ideas.handle(request('planning'),USER,db,lambda system,messages:response())
        self.assertEqual(db.rpc_calls[0][1]['p_provenance']['history_messages'],2)
        self.assertEqual(len(db.rpc_calls[-1][1]['p_messages']),4)
        self.assertEqual(db.rpc_calls[-1][1]['p_messages'][-2]['content'][0]['text'],'Challenge my assumptions')
    def test_cross_owner_cross_module_and_caller_context_overrides_are_refused(self):
        db=FakeDatabase();db.owned=False
        with self.assertRaises(AuthError):ideas.handle(request(),USER,db,lambda *_:self.fail('Model invoked'))
        self.assertFalse(any(path=='research_idea_packets' for path,_ in db.calls))
        db=FakeDatabase();db.foreign=True
        with self.assertRaises(AuthError):ideas.handle(request('planning'),USER,db,lambda *_:self.fail('Model invoked'))
        self.assertFalse(any(params.get('select')=='messages' for _,params in db.calls))
        for field in ('history','prompt_version_id','tools','actor_id'):
            with self.assertRaises(ValueError):ideas.handle(dict(request(),**{field:'override'}),USER,FakeDatabase(),lambda *_:self.fail('Model invoked'))
        with self.assertRaises(ValueError):ideas.handle(dict(request(),session_id=SESSION),USER,FakeDatabase(),lambda *_:self.fail('Model invoked'))
    def test_packet_hash_and_context_budget_block_model_calls(self):
        db=FakeDatabase();db.packet['sha256']='b'*64
        with self.assertRaises(ValueError):ideas.handle(request(),USER,db,lambda *_:self.fail('Model invoked'))
        db=FakeDatabase();db.packet['raw_document']=json.dumps({'question':'x'*24001});db.packet['document']=json.loads(db.packet['raw_document']);db.packet['sha256']=hashlib.sha256(db.packet['raw_document'].encode()).hexdigest()
        with self.assertRaises(ValueError):ideas.handle(request(),USER,db,lambda *_:self.fail('Model invoked'))
    def test_replayed_request_does_not_invoke_again(self):
        db=FakeDatabase();db.replayed=True
        result=ideas.handle(request(),USER,db,lambda *_:self.fail('Model invoked twice'))
        self.assertTrue(result['replayed']);self.assertEqual(len(db.rpc_calls),1)
    def test_failed_and_invalid_calls_keep_originals_and_missing_usage(self):
        db=FakeDatabase()
        def fail(*_):raise TimeoutError('Never expose this private diagnostic')
        result=ideas.handle(request(),USER,db,fail)
        self.assertEqual(result['run']['status'],'failed');self.assertNotIn('private diagnostic',result['run']['reason'])
        self.assertIsNone(db.rpc_calls[-1][1]['p_usage']['tokens']);self.assertIsNone(db.rpc_calls[-1][1]['p_usage']['measured_charges_usd'])
        db=FakeDatabase();bad=response();bad['output']['message']['content']=[{'toolUse':{'name':'publish_every_claim','input':{}}}]
        result=ideas.handle(request(),USER,db,lambda *_:bad)
        self.assertEqual(result['run']['status'],'invalid-output');self.assertIn('publish_every_claim',db.rpc_calls[-1][1]['p_raw'])
        self.assertEqual(db.rpc_calls[-1][1]['p_provenance']['provider_message'],bad['output']['message'])
    def test_readiness_schema_refuses_results_and_outstanding_questions(self):
        for value in (dict(OUTPUT,verdict='reproduced'),dict(OUTPUT,questions=['Missing units?']),dict(OUTPUT,findings=[{'severity':'blocking','field':'units','message':'Ambiguous'}]),dict(OUTPUT,measurements=[0])):
            with self.assertRaises(ValueError):ideas.validate_output(json.dumps(value),'critic')
    def test_response_channel_cannot_smuggle_an_action_or_partial_answer(self):
        valid=response();self.assertEqual(ideas.parse_response(valid,'critic'),OUTPUT)
        for bad in (dict(valid,stopReason='max_tokens'),dict(valid,stopReason='end_turn'),
            dict(valid,output={'message':{'content':valid['output']['message']['content']+[{'toolUse':{'name':'execute_experiment','input':{}}}]}})):
            with self.assertRaises(ValueError):ideas.parse_response(bad,'critic')
        self.assertEqual(ideas.response_channel()['toolChoice'],{'tool':{'name':ideas.RESPONSE_CHANNEL}})

if __name__=='__main__':unittest.main()
