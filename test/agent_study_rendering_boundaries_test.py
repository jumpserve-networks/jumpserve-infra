"""Recorded study rendering preserves missing data, source scope and call limits."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
import ipv6_answers as ipv6
import reliable_answers as reliable


def claim(identifier):
    return dict(id=identifier, description='Recorded ' + identifier, assessment='inconclusive',
        location='Synthetic source cell', evidence='Retained finite evidence', limitation='Controlled fixture only')


def evidence():
    identifiers = ['readiness-weighting', 'rq3-fragments', 'analysis-defects', 'rfc3901', 'rq4-causality', 'rq5-dnssec',
                   'memory', 'sensing', 'weighted-code', 'lock-order', 'theory', 'confidence-product']
    return dict(status='recorded', meta={'analysis_version': 'synthetic-assessment',
        'validation': {'reproduced_cells': 0, 'published_cells': 2, 'findings': {'total_cpu_runs': 0}}},
        claims=[claim(identifier) for identifier in identifiers], configuration_ids=['original-config'])


def literature():
    return dict(total_source_records=3, direct_references=1, review_counts={'partial': 1, 'unavailable': 1, 'complete': 1},
        sources=[dict(reference_number=index, citation='Synthetic source ' + str(index), access_status='retrieved', review_status='partial',
            retrieved_version='retained-v1' if index == 0 else None, sha256='a' * 64 if index == 0 else None,
            findings='Retained source note' if index == 0 else None, limitations='Not independent review') for index in range(2)])


def ipv6_configuration():
    metric = dict(mean=0, min=0, max=1, n=1, planned=3, missing=1, invalid=1, pooled=None,
        paired_v6_minus_v4_mean_pp=None, paired_days=0)
    return dict(status='recorded', configuration=dict(id='original-config', cohort='no-dnssec', mtu=1500,
        upstream='no-lgi', family='v6-only', edns_bytes=4096),
        summaries=[dict(epoch='original-day', statistics={'TIMEOUT': dict(metric), 'udp_fragments': dict(metric)})])


def reliable_configuration():
    return dict(status='recorded', configuration=dict(id='original-config', algorithm='RS', skewness='0.3',
        budget_bytes=8192, budget_regime='counter-capped', input_sha256='b' * 64),
        summary=dict(recorded=0, planned=10, failed=1, excluded=1, observed_keys=0,
            statistics={'outliers': dict(median=0, min=0, max=None, units='count', n=1)}))


class StudyRenderingBoundaries(unittest.TestCase):
    def families(self):
        return [
            ('ipv6', ipv6.IPv6AnswerPlan, ipv6.render_ipv6_answer, ipv6.prepare_ipv6_context,
             ipv6_configuration, ['assessment', 'units', 'coverage', 'uncertainty', 'discrepancy', 'standards', 'causality', 'uncovered']),
            ('reliable', reliable.ReliableAnswerPlan, reliable.render_reliable_answer, reliable.prepare_reliable_context,
             reliable_configuration, ['assessment', 'units', 'memory', 'weighted', 'theory', 'coverage', 'uncertainty', 'uncovered']),
        ]

    def test_each_scientific_topic_preserves_evidence_scope_and_recorded_claim_limitations(self):
        for family, plan, render, _prepare, _config, topics in self.families():
            for topic in topics:
                original = evidence(); before = copy.deepcopy(original)
                reader = Mock(return_value=literature())
                text, events = render(plan(topics=[topic, topic]), original, reader, Mock())
                with self.subTest(family=family, topic=topic):
                    self.assertIn('Analysis:', text)
                    self.assertIn('/methods', text)
                    self.assertEqual(original, before)
                    if topic == 'coverage':
                        self.assertEqual(events, [{'name': 'get_' + family + '_literature', 'input': {}}])
                        reader.assert_called_once_with()
                        self.assertIn('not establish review', text)
                    else:
                        self.assertEqual(events, [])
                        reader.assert_not_called()
                    if topic == 'uncertainty': self.assertIn('not confidence intervals', text)
                    if topic == 'assessment':
                        self.assertIn('not new measurements, simulation or full paper validation' if family == 'ipv6' else 'not full paper validation', text)
                    if topic in ['discrepancy', 'standards', 'causality', 'memory', 'weighted', 'theory']:
                        self.assertIn('Controlled fixture only', text)

    def test_missing_and_duplicated_claims_remain_unavailable_without_inventing_values(self):
        for family, plan, render, _prepare, _config, _topics in self.families():
            original = evidence(); original['claims'] = []
            topic = 'standards' if family == 'ipv6' else 'memory'
            text, _ = render(plan(topics=[topic]), original, Mock(), Mock())
            self.assertIn('Claim evidence unavailable; missing is not zero.', text)
            identifier = 'rfc3901' if family == 'ipv6' else 'memory'
            original['claims'] = [claim(identifier), claim(identifier)]
            text, _ = render(plan(topics=[topic]), original, Mock(), Mock())
            self.assertIn('Claim evidence unavailable; missing is not zero.', text)
            text, events = render(plan(topics=['assessment']), {'status': 'unavailable'}, Mock(), Mock())
            self.assertIn('unavailable', text); self.assertEqual(events, [])

    def test_configuration_output_keeps_zero_missing_counts_original_hashes_and_descriptive_ranges(self):
        for family, plan, render, _prepare, configuration, _topics in self.families():
            read = Mock(return_value=configuration())
            text, events = render(plan(topics=['configuration'], configuration_id='original-config'), evidence(), Mock(), read)
            with self.subTest(family=family):
                read.assert_called_once_with('original-config')
                self.assertEqual(events, [{'name': 'get_' + family + '_configuration', 'input': {'configuration_id': 'original-config'}}])
                self.assertIn('original-config', text); self.assertIn('missing', text)
                self.assertIn('not confidence intervals' if family == 'ipv6' else 'not zero violations', text)
                if family == 'ipv6':
                    self.assertIn('0%', text); self.assertIn('missing pp on 0 days', text)
                else:
                    self.assertIn('0/10runs', text); self.assertIn('median 0', text); self.assertIn('b' * 64, text)
            read.reset_mock()
            text, events = render(plan(topics=['configuration']), evidence(), Mock(), read)
            self.assertIn('Choose an exact recorded configuration ID', text); read.assert_not_called(); self.assertEqual(events, [])
            read.return_value = {'status': 'unavailable'}
            text, _ = render(plan(topics=['configuration'], configuration_id='missing-config'), evidence(), Mock(), read)
            self.assertIn('missing-config', text); self.assertIn('unavailable', text)

    def test_literature_sources_preserve_review_and_access_status_and_original_version_or_missing_values(self):
        for family, plan, render, _prepare, _configuration, _topics in self.families():
            for reference in [None, 0]:
                reader = Mock(return_value=literature())
                text, events = render(plan(topics=['source'], reference_number=reference), evidence(), reader, Mock())
                with self.subTest(family=family, reference=reference):
                    reader.assert_called_once_with(reference_number=reference)
                    self.assertEqual(events[0]['input'], {'reference_number': reference})
                    for retained in ['Synthetic source 0', 'retrieved', 'partial', 'retained-v1', 'a' * 64, 'unavailable']:
                        self.assertIn(retained, text)
                    self.assertIn('No substantive', text)
            empty = Mock(return_value={**literature(), 'sources': []})
            text, events = render(plan(topics=['source'], reference_number=1), evidence(), empty, Mock())
            self.assertEqual(len(events), 1); self.assertNotIn('Synthetic source 0', text)

    def test_numerical_rendering_rejects_nonfinite_or_coerced_evidence_and_distinguishes_missing_from_zero(self):
        self.assertEqual(reliable.num(None), 'missing'); self.assertEqual(reliable.num(0), '0')
        for value in [True, False, '0', {}, float('inf'), float('-inf'), float('nan')]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Invalid numerical evidence'):
                reliable.num(value)

    def test_bounded_context_keeps_recent_text_and_ignores_nontext_blocks_without_mutating_history(self):
        for family, _plan, _render, prepare, _configuration, _topics in self.families():
            history = [{'role': 'user', 'content': ['unsupported', None, {'text': 12}, {'toolUse': {'name': 'untrusted'}}, {'text': 'x' * 3000}]},
                       {'role': 'assistant', 'content': [{'toolUse': {'name': 'untrusted'}}]}, {'role': 'user'}]
            original = copy.deepcopy(history); agent = types.SimpleNamespace(messages=history)
            prepare(agent, 'Current question', evidence())
            self.assertEqual(history, original)
            self.assertEqual(len(agent.messages), 4)
            self.assertEqual(agent.messages[0], {'role': 'user', 'content': [{'text': 'x' * 2000}]})
            self.assertNotIn('untrusted', str(agent.messages))
            too_large = evidence(); too_large['source_notes'] = 'x' * 16001
            with self.subTest(family=family), self.assertRaisesRegex(ValueError, 'snapshot exceeds'):
                prepare(agent, 'Current question', too_large)

    def test_explicit_ipv6_references_and_reliable_identifiers_survive_model_topic_selection(self):
        plan = ipv6.IPv6AnswerPlan(topics=['assessment', 'source', 'units', 'coverage'], reference_number=1)
        for number in [0, 73]:
            result = ipv6.constrain_ipv6_plan(plan, 'Please read ref [' + str(number) + ']')
            self.assertEqual(result.reference_number, number); self.assertEqual(result.topics[0], 'source')
            self.assertEqual(len(result.topics), 4)
        self.assertEqual(ipv6.constrain_ipv6_plan(plan, 'ref 74').reference_number, 1)
        original = reliable.ReliableAnswerPlan(topics=['configuration', 'assessment', 'units', 'memory'], reference_number=0)
        self.assertIs(reliable.constrain_reliable_plan(original, 'No explicit configuration'), original)
        result = reliable.constrain_reliable_plan(original, 'Inspect main-zipf1.0-8192-RS_raw')
        self.assertEqual(result.configuration_id, 'main-zipf1.0-8192-RS_raw'); self.assertEqual(result.reference_number, 0)
        self.assertEqual(result.topics, ['configuration', 'assessment', 'units', 'memory'])

    def test_selector_hooks_allow_two_model_calls_then_cancel_and_register_their_exact_event(self):
        events = types.ModuleType('strands.hooks.events')
        events.BeforeModelCallEvent = type('BeforeModelCallEvent', (), {})
        for family in ['ipv6', 'reliable']:
            spec = importlib.util.spec_from_file_location('unit_' + family + '_limits', ROOT / 'agent' / (family + '_limits.py'))
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'strands.hooks.events': events}): spec.loader.exec_module(module)
            limiter = getattr(module, 'IPv6Limits' if family == 'ipv6' else 'ReliableLimits')()
            registry = Mock(); limiter.register_hooks(registry)
            registry.add_callback.assert_called_once_with(events.BeforeModelCallEvent, limiter.before)
            event = types.SimpleNamespace(cancel=None)
            limiter.before(event); limiter.before(event); self.assertIsNone(event.cancel)
            limiter.before(event); self.assertIn('model-call limit reached', event.cancel)


if __name__ == '__main__':
    unittest.main()
