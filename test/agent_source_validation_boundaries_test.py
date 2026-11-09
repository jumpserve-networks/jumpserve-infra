"""Typed source-review channels and immutable prompt selection, with no model calls."""
import copy
import json
import types
import unittest
from unittest.mock import Mock

import agent_prompt_test as prompt_fixtures
import agent_review_sources_test as review_fixtures
import idea_interview as interview
import idea_review as review
from prompt import PromptUnavailable, PromptVersion
from prompt_publication import evaluation_snapshot


def interview_reply(value=None, name=interview.CHANNEL):
    return {'stopReason': 'tool_use', 'output': {'message': {'content': [{'toolUse': {'name': name,
        'input': {'summary': 'Original scoped question', 'question': 'Which inputs are available?', 'field': 'inputs'} if value is None else value}}]}}}


class SourceValidationBoundaries(unittest.TestCase):
    def test_interview_prompt_templates_are_server_selected_versioned_and_bounded(self):
        prompt = types.SimpleNamespace(system_prompt='Original legacy system', text='Original legacy text', research_context='Original source context')
        self.assertEqual(interview.system_text(prompt), 'Original legacy text')
        with self.assertRaisesRegex(ValueError, 'evaluated task prompt'): interview.system_text(prompt, interview=True)
        template = dict(schema='idea-task-prompts-v2', review='REVIEW', interview='INTERVIEW', planning='PLANNING')
        prompt.system_prompt = json.dumps(template)
        self.assertEqual(interview.system_text(prompt, task='planning'), 'PLANNING\n\nOriginal source context')
        self.assertEqual(interview.system_text(prompt, interview=True), 'INTERVIEW\n\nOriginal source context')
        self.assertEqual(interview.system_text(prompt, task='critic'), 'REVIEW\n\nOriginal source context')
        for invalid in [dict(template, schema='unknown'), dict(template, extra='untrusted'), dict(template, review=''), dict(template, review=None), dict(template, planning='x' * 12001)]:
            prompt.system_prompt = json.dumps(invalid)
            with self.subTest(invalid=str(invalid)[:100]), self.assertRaises(ValueError): interview.system_text(prompt)
        self.assertEqual(interview.response_channel()['toolChoice'], {'tool': {'name': interview.CHANNEL}})

    def test_interview_response_requires_one_bounded_question_for_the_requested_field(self):
        self.assertEqual(interview.parse(interview_reply(), preferred_field='inputs')['field'], 'inputs')
        for value in [{}, {'summary': 'Original', 'question': 'Question?', 'field': 'execute'},
                      {'summary': 'Original', 'question': 0, 'field': 'inputs'},
                      {'summary': 'x' * 1601, 'question': 'Question?', 'field': 'inputs'},
                      {'summary': 'Original', 'question': ' ', 'field': 'inputs'}]:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError): interview.parse(interview_reply(value))
        for response in [interview_reply(name='execute_experiment'), dict(interview_reply(), stopReason='max_tokens'),
                         {'stopReason': 'tool_use', 'output': {'message': {'content': []}}}]:
            with self.assertRaises(ValueError): interview.parse(response)
        with self.assertRaises(ValueError): interview.parse(interview_reply(), preferred_field='design')

    def test_review_schema_exposes_only_issue_classification_and_recorded_field_references(self):
        channel = review.response_channel()
        self.assertEqual(channel['toolChoice'], {'tool': {'name': review.CHANNEL}})
        schema = channel['tools'][0]['toolSpec']['inputSchema']['json']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['required'], ['issues'])
        self.assertEqual(schema['properties']['issues']['maxItems'], 8)
        references = schema['properties']['issues']['items']['properties']['references']
        self.assertTrue(references['uniqueItems'])
        self.assertIn('/protocol/statistics', references['items']['enum'])

    def test_review_rejects_incomplete_channels_over_budget_issues_and_duplicate_source_judgments(self):
        packet = {'controls': 'Retained control', 'protocol': None}
        original = dict(code='clarification', severity='blocking', references=['/controls'])
        cases = [review_fixtures.reply(None), review_fixtures.reply([original] * 9),
            review_fixtures.reply([original, original]), review_fixtures.reply([dict(original, references=[])]),
            review_fixtures.reply([dict(original, references=None)]), review_fixtures.reply([dict(original, references=['/controls'] * 7)]),
            review_fixtures.reply([dict(original, references=[None])]), review_fixtures.reply([dict(original, code=1)]),
            review_fixtures.reply([dict(original, severity='approved')]),
            review_fixtures.reply([dict(code='limitation', severity='blocking', references=['/controls'])])]
        incomplete = review_fixtures.reply([]); incomplete['output']['message']['content'][0]['toolUse']['input'] = {}
        cases += [incomplete, dict(review_fixtures.reply([]), stopReason='end_turn')]
        for value in cases:
            with self.subTest(value=str(value)[:100]), self.assertRaises(ValueError): review.parse(value, packet, 'critic', 'a' * 64)

    def test_warning_findings_preserve_original_source_and_do_not_invent_blocking_questions(self):
        packet = {'controls': 'Original declared scope', 'protocol': None}; before = copy.deepcopy(packet)
        for code in ['limitation', 'clarification']:
            output, grounding = review.parse(review_fixtures.reply([dict(code=code, severity='warning', references=['/controls'])]), packet, 'critic', 'a' * 64)
            self.assertEqual(output['verdict'], 'ready'); self.assertEqual(output['questions'], [])
            self.assertEqual(output['findings'][0]['severity'], 'warning')
            self.assertEqual(grounding['fields'][0]['value'], 'Original declared scope')
            self.assertEqual(packet, before)

    def test_prompt_module_and_evaluation_candidate_cardinality_are_verified_before_publication(self):
        with self.assertRaises(PromptUnavailable): PromptVersion.from_record(dict(prompt_fixtures.record(), module_id='untrusted-module'))
        for values in [[], [{'active_version_id': None}, {'active_version_id': None}]]:
            database = Mock(); database.get.return_value = values
            with self.subTest(settings=values), self.assertRaisesRegex(RuntimeError, 'not been initialized'): evaluation_snapshot(database)
            database.rpc.assert_not_called()
        for records in [[], [prompt_fixtures.record(), prompt_fixtures.record()]]:
            database = Mock(); database.get.side_effect = [[{'active_version_id': 'original'}], records]
            with self.assertRaisesRegex(RuntimeError, 'Prompt version not found'): evaluation_snapshot(database, prompt_id='candidate')
            database.rpc.assert_not_called()
        database = Mock(); database.get.side_effect = [[{'active_version_id': 'original'}], [dict(prompt_fixtures.record(), module_id='congestion-control-real-world')]]
        with self.assertRaisesRegex(RuntimeError, 'another module'): evaluation_snapshot(database, prompt_id='candidate')
        self.assertEqual(database.get.call_args.kwargs['params']['id'], 'eq.candidate')
        database.rpc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
