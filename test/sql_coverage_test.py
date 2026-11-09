"""The SQL test harness must never fall back to an existing or remote database."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_sql_coverage as runner
import setup_sql_coverage as setup


class SQLCoverageScope(unittest.TestCase):
    def test_queries_accept_only_the_dedicated_user_port_and_fresh_fixture_database(self):
        urls = ['postgresql://unit_coverage@production.example:54479/postgres', 'postgresql://unit_coverage@127.0.0.1:5432/postgres', 'postgresql://other@127.0.0.1:54479/postgres', 'postgresql://unit_coverage:secret@127.0.0.1:54479/postgres', 'postgresql://unit_coverage@127.0.0.1:54479/production', 'postgresql://unit_coverage@127.0.0.1:54479/postgres?host=production.example', 'postgresql://unit_coverage@127.0.0.1:54479/postgres#other']
        with patch.object(runner.subprocess, 'run') as execute:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError): runner.query('/fixture/psql', url, 'select 1')
            execute.assert_not_called()
            execute.return_value.returncode = 0; execute.return_value.stdout = '1\n'
            self.assertEqual(runner.query('/fixture/psql', 'postgresql://unit_coverage@127.0.0.1:54479/jumpserve_platform_test_fixture', 'select 1'), '1')
            self.assertEqual(execute.call_args.kwargs['input'], 'select 1'); self.assertIn('ON_ERROR_STOP=1', execute.call_args.args[0])

    def test_profiler_receipt_rejects_changed_bytes_wrong_revision_and_paths_outside_test_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp) / 'tools'; tools.mkdir(); library = tools / 'profiler.so'; library.write_bytes(b'Synthetic compiled library')
            bindir = tools / 'bin'; bindir.mkdir()
            original = dict(revision=runner.REVISION, library=str(library), sha256=hashlib.sha256(library.read_bytes()).hexdigest(), bindir=str(bindir))
            receipt = tools / 'sql-profiler.json'
            with patch.object(runner, 'TOOLS', tools):
                receipt.write_text(json.dumps(original)); self.assertEqual(runner.verified_tool(), original)
                for change in [dict(revision='unreviewed'), dict(sha256='0' * 64), dict(library=str(Path(tmp) / 'outside')), dict(bindir='/usr/bin')]:
                    receipt.write_text(json.dumps(dict(original, **change)))
                    with self.subTest(change=change), self.assertRaises(RuntimeError): runner.verified_tool()

    def test_setup_rejects_an_existing_source_checkout_at_an_unpinned_revision_before_build(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, 'TOOLS', Path(tmp)), patch.object(setup, 'SOURCE', Path(tmp)), patch.object(setup.subprocess, 'check_output', return_value='unreviewed\n'), patch.object(setup.subprocess, 'run') as execute:
            with self.assertRaisesRegex(RuntimeError, 'pinned revision'): setup.prepare()
            execute.assert_not_called()

    def test_literal_preserves_apostrophes_without_sql_command_substitution(self):
        self.assertEqual(runner.literal("fixture'; select 1; --"), "'fixture''; select 1; --'")


if __name__ == '__main__': unittest.main()
