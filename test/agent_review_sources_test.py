import copy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path
from agent_ideas_test import FakeDatabase, USER, request, response
import research_ideas as ideas
import idea_review as review

def reply(issues):
    value = response(dict(issues=issues))
    value['output']['message']['content'][0]['toolUse']['name'] = review.CHANNEL
    return value

class SourceReview(unittest.TestCase):
    def setUp(self):
        seed = json.loads((Path(__file__).resolve().parents[1]/'database/seed-research-ideas-prompt-v11.json').read_text())
        self.prompt = SimpleNamespace(**seed, content_sha256='a'*64, text=seed['system_prompt']+'\n\n'+seed['research_context'])
        self.patch = patch.object(ideas, 'load_active_prompt', return_value=self.prompt)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.packet = dict(question='Can this fixture compress?', controls='Treat 100 repeats as independent.',
            protocol=dict(statistics='Bootstrap repeats as independent population samples.', dependence='All repeats are independent.',
                          replication_unit='One deterministic input; repeats are not independent.', resource_limits=dict(max_observations=0)))

    def test_problematic_statistics_is_copied_exactly_and_never_rephrased(self):
        output, source = review.parse(reply([dict(severity='blocking',code='dependence', references=['/protocol/statistics','/protocol/replication_unit','/controls'])]), self.packet, 'critic', 'b'*64)
        self.assertEqual(source['fields'][0]['value'], self.packet['protocol']['statistics'])
        self.assertEqual(source['packet_sha256'], 'b'*64)
        self.assertEqual(output['verdict'], 'needs-clarification')
        self.assertNotIn('statistics correctly', json.dumps(output))
        self.assertNotIn(self.packet['protocol']['statistics'], output['summary'])
        self.assertEqual(source['fields'][0]['value_sha256'], hashlib.sha256(review.canonical(self.packet['protocol']['statistics'])).hexdigest())

    def test_model_cannot_supply_or_invert_source_text(self):
        for issue in (dict(severity='blocking',code='dependence',references=['/protocol/statistics'],explanation='Statistics disclaims independence'),
                      dict(severity='blocking',code='dependence',references=['/not_recorded']),dict(severity='blocking',code='fabricated-evidence',references=['/controls']),
                      dict(severity='blocking',code='dependence',references=['/controls','/controls'])):
            with self.assertRaises(ValueError): review.parse(reply([issue]), self.packet, 'critic', 'b'*64)

    def test_zero_null_empty_missing_are_distinct(self):
        packet=dict(question='',hypothesis=None,metrics=0,protocol=None)
        output, source=review.parse(reply([]),packet,'comprehension','b'*64)
        states={f['path']:f for f in source['fields']}
        self.assertEqual(states['/question']['state'],'empty');self.assertEqual(states['/hypothesis']['state'],'null')
        self.assertEqual(states['/metrics']['state'],'recorded');self.assertEqual(states['/metrics']['value'],0)
        self.assertEqual(states['/conditions']['state'],'missing');self.assertNotIn('value',states['/conditions'])

    def test_missing_protocol_cannot_be_fabricated_for_a_recorded_protocol(self):
        with self.assertRaises(ValueError):review.parse(reply([dict(severity='blocking',code='missing-protocol',references=['/protocol'])]),self.packet,'critic','b'*64)
        output,_=review.parse(reply([dict(severity='blocking',code='missing-protocol',references=['/protocol'])]),dict(protocol=None),'critic','b'*64)
        self.assertEqual(output['verdict'],'needs-clarification')

    def test_complete_review_preserves_recorded_comprehension_fields(self):
        output, source=review.parse(reply([]),self.packet,'comprehension','b'*64)
        self.assertEqual(output['verdict'],'ready');self.assertEqual(output['questions'],[])
        self.assertEqual(next(f for f in source['fields'] if f['path']=='/question')['value'],self.packet['question'])

    def test_actual_handler_records_sources_in_mutable_completion_events_only(self):
        db=FakeDatabase();raw=review.canonical(self.packet).decode();db.packet.update(document=self.packet,raw_document=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())
        seen=[]
        def invoke(system,messages,**options):seen.append((system,messages,options));return reply([dict(severity='blocking',code='dependence',references=['/protocol/statistics'])])
        result=ideas.handle(request(),USER,db,invoke)
        self.assertEqual(result['run']['status'],'complete');self.assertEqual(seen[0][2],dict(source_review=True))
        self.assertIn('submit_idea_issues',seen[0][0]);self.assertNotIn('user_message',json.loads(seen[0][1][0]['content'][0]['text']))
        begin=db.rpc_calls[0][1]['p_provenance'];finish=db.rpc_calls[-1][1]['p_provenance']
        self.assertNotIn('source_evidence',begin);self.assertEqual(set(finish)-set(begin),{'stop_reason','tool_events','data_origin','provider_message','raw_response_scope'})
        source=finish['tool_events'][0]['source_evidence'];self.assertEqual(source['fields'][0]['value'],self.packet['protocol']['statistics'])

    def test_invalid_citation_keeps_original_provider_response(self):
        result=ideas.handle(request(),USER,FakeDatabase(),lambda *_,**__:reply([dict(severity='blocking',code='dependence',references=['/protocol/statistics'])]))
        self.assertEqual(result['run']['status'],'invalid-output')
