import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

class HTTP2ToolsTest(unittest.TestCase):
    def setUp(self):
        strands=types.ModuleType('strands'); strands.tool=lambda f:f
        database=types.ModuleType('database'); self.db=Mock(); database.Database=Mock(return_value=self.db)
        spec=importlib.util.spec_from_file_location('http2_test_tools',Path(__file__).resolve().parents[1]/'agent/tools/http2_study.py')
        self.tools=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'strands':strands,'database':database}):spec.loader.exec_module(self.tools)
    def test_invalid_query_inputs_never_reach_database(self):
        for identifier in ('x&select=*', '../raw', '', None):
            with self.assertRaises(ValueError):self.tools.get_http2_configuration(identifier)
        for offset in (-1,157,True,'0'):
            with self.assertRaises(ValueError):self.tools.get_http2_configuration('Apache-2.4.63',offset)
        for ref in (-1,49,True,'0'):
            with self.assertRaises(ValueError):self.tools.get_http2_literature(ref)
        self.db.get.assert_not_called()
    def test_results_do_not_duplicate_locked_validation_vectors(self):
        self.db.get.side_effect=[[{'provenance':{'analysis_version':'v3','lock':{'private':'manifest'},'validation':{'counts':42}}}],[],[],[]]
        result=self.tools.get_http2_study_results()
        self.assertEqual(result['campaign']['provenance'],{'analysis_version':'v3'})
        self.assertEqual(result['summaries'],[])
        self.assertTrue(all('artifacts' not in call.args[0] for call in self.db.get.call_args_list))
    def test_configuration_page_retains_unknowns_and_explicit_next_offset(self):
        rows=[{'test_id':i,'outcome':'unknown','error_code':None} for i in range(1,4)]
        self.db.get.side_effect=[[{'id':'Apache-2.4.63'}],[{'id':'archive-001'}],rows]
        result=self.tools.get_http2_configuration('Apache-2.4.63',limit=2)
        self.assertEqual(result['next_offset'],2)
        self.assertEqual(result['measurements'],rows[:2])
        params=self.db.get.call_args.kwargs['params']
        self.assertEqual(params['run_id'],'eq.archive-001');self.assertEqual(params['limit'],3)

if __name__=='__main__':unittest.main()
