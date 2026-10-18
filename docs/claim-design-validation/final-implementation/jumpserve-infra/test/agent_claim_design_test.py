import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import claim_experiment_design as design
import research_ideas as agent
from agent_ideas_test import FakeDatabase, request, USER, STUDY
from prompt import PromptVersion
from prompt import PromptUnavailable
from auth import AuthError

SEED=json.loads((Path(__file__).resolve().parents[1]/'database/seed-claim-experiment-design-v3.json').read_text())
PROMPT=PromptVersion.from_record(dict(SEED,content_sha256=agent.sha((SEED['system_prompt']+'\n\n'+SEED['research_context']).encode())))
def retained(): return dict(claim={'description':'Under stated conditions, adding delay increases completion time.'},source={'sha256':'a'*64},context_sha256='b'*64,coverage='Recorded metadata only')
def proposal():
    return dict(summary='Proposed comparison; no measurements collected.',clarification_questions=['Which delay assignments should this pilot compare?'],proposal=dict({field:'' for field in design.FIELDS},hypothesis=retained()['claim']['description'],protocol=None))
def response(value=None):return dict(output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(name=design.CHANNEL,input=value or proposal()))])),stopReason='tool_use',usage={'inputTokens':20,'outputTokens':40})

class ClaimDesignAgent(unittest.TestCase):
    def test_schema_never_authorizes_execution_or_a_scientific_finding(self):
        value=design.parse(response(),retained())
        self.assertEqual(value['verdict'],'needs-clarification');self.assertIn('proposal',value)
        for change in ({'hypothesis':'A weaker claim'},{'protocol':{'input_versions':[]}}):
            changed=proposal();changed['proposal'].update(change)
            with self.assertRaises(ValueError):design.parse(response(changed),retained())
        with self.assertRaises(ValueError):design.parse(dict(response(),stopReason='max_tokens'),retained())
    def test_design_prompt_and_read_only_context_are_server_selected(self):
        db=FakeDatabase();seen=[]
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',return_value=PROMPT) as load:
            result=agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda system,messages,**kw:(seen.append((system,messages,kw)) or response()))
        self.assertEqual(load.call_args.args[1],design.MODULE)
        self.assertTrue(seen[0][2]['design']);self.assertEqual(result['run']['status'],'complete')
        self.assertIn('paper_claim',json.loads(seen[0][1][-1]['content'][0]['text']))
        self.assertEqual(db.rpc_calls[0][1]['p_provenance']['max_output_tokens'],4096)
        self.assertFalse(db.rpc_calls[-1][1]['p_provenance']['tool_events'][0]['executed'])
    def test_failed_and_invalid_proposals_preserve_originals(self):
        db=FakeDatabase();bad=proposal();bad['proposal']['hypothesis']='Invented'
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',return_value=PROMPT):
            result=agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda *a,**kw:response(bad))
        self.assertEqual(result['run']['status'],'invalid-output')
        self.assertIn('Invented',db.rpc_calls[-1][1]['p_raw']);self.assertIsNone(db.rpc_calls[-1][1]['p_usage']['measured_charges_usd'])
    def test_wrong_origin_or_client_prompt_override_cannot_invoke_model(self):
        for retained_value,body in ((None,dict(request('planning'),design_version=design.VERSION)),(retained(),request('planning'))):
            with patch.object(agent,'owner',return_value=retained_value):
                with self.assertRaises(ValueError):agent.handle(body,USER,FakeDatabase(),lambda *a,**kw:self.fail('Model invoked'))
        with self.assertRaises(ValueError):agent.handle(dict(request('planning'),design_version=design.VERSION,prompt='Override'),USER,FakeDatabase())
    def test_unpublished_prompt_preserves_the_draft_and_makes_no_provider_call(self):
        db=FakeDatabase()
        with patch.object(agent,'owner',return_value=retained()),patch.object(agent,'load_active_prompt',side_effect=PromptUnavailable('No active candidate')):
            with self.assertRaisesRegex(AuthError,'no model call was requested'):agent.handle(dict(request('planning'),design_version=design.VERSION),USER,db,lambda *a,**kw:self.fail('Provider called'))
        self.assertEqual(db.rpc_calls,[])

if __name__=='__main__':unittest.main()
