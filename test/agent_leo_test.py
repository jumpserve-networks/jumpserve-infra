import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
class LeoToolsTest(unittest.TestCase):
    def setUp(self):
        modules={name:types.ModuleType(name) for name in ('strands','database')}
        modules['strands'].tool=lambda fn:fn
        self.db=Mock(); modules['database'].Database=Mock(return_value=self.db)
        spec=importlib.util.spec_from_file_location('leo_tools_test',ROOT/'agent/tools/leo_study.py')
        self.tools=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,modules): spec.loader.exec_module(self.tools)
    def test_public_bounded_evidence_preserves_units_and_does_not_impute_missing(self):
        self.db.get.side_effect=[[{'id':self.tools.CAMPAIGN}],[],[],[]]
        result=self.tools.get_leo_study_results('haiti')
        self.assertEqual(result['summaries'],[])
        self.assertIn('1000 Mbit/s',result['units'])
        self.assertEqual([c.args[0] for c in self.db.get.call_args_list],['leo_study_campaigns','leo_study_claims','leo_study_summaries','leo_study_campaigns'])
        for call in self.db.get.call_args_list: self.assertNotIn('*',call.kwargs['params']['select'])
    def test_unknown_country_and_filter_injection_never_query(self):
        for value in ['../agent_sessions','haiti&select=*','not-a-country']:
            with self.assertRaises(ValueError): self.tools.get_leo_scenarios(value)
        self.db.get.assert_not_called()
    def test_configuration_pagination_and_full_matching_fields(self):
        self.db.get.return_value=[{'id':'a'},{'id':'b'}]
        page=self.tools.get_leo_scenarios('tonga',limit=1)
        self.assertEqual(page['next_offset'],1)
        self.assertEqual(len(page['configurations']),1)
        select=self.db.get.call_args.kwargs['params']['select']
        for field in ('deployed_terminals','variant','constellation','ku_gbps','beam_policy','second'): self.assertIn(field,select)
        for args in ({'limit':0},{'limit':51},{'offset':-1},{'offset':True}):
            with self.assertRaises(ValueError): self.tools.get_leo_scenarios('tonga',**args)
    def test_literature_review_is_explicit_and_reference_is_bounded(self):
        self.db.get.return_value=[{'reading_status':'unread','download_status':'downloaded'}]
        self.assertEqual(self.tools.get_leo_literature(91)['papers'][0]['reading_status'],'unread')
        for n in [-1,97,True,'1&select=*']:
            with self.assertRaises(ValueError): self.tools.get_leo_literature(n)
    def test_server_mapping_has_only_read_tools_for_leo(self):
        text=(ROOT/'agent/tools/__init__.py').read_text()
        self.assertIn('LEO_MODULE: [get_leo_study_results, get_leo_scenarios, get_leo_literature]',text)
if __name__=='__main__': unittest.main()
