"""Existing host maintenance safeguards; no AWS or database calls."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('maintenance_unit', ROOT / 'bin/openclaw-maintenance.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class AuthorizationMaintenance(unittest.TestCase):
 def test_native_login_requires_held_admission_polling_and_drained_work(self):
  def configuration(enabled='false',rule='DISABLED'):
   def aws(service,operation,*args):
    if operation=='get-function-configuration':return dict(Environment=dict(Variables=dict(RESEARCH_AUTONOMY_ENABLED=enabled)))
    if operation=='list-stack-resources':return dict(StackResourceSummaries=[dict(ResourceType='AWS::Events::Rule',LogicalResourceId='ResearchWorkflowAutonomyPoll',PhysicalResourceId='fixed-rule')])
    if operation=='describe-rule':return dict(State=rule)
    raise AssertionError(operation)
   return aws
  with patch.object(release,'functions',return_value=dict(api='fixed-api')):
   for enabled,rule in [('true','DISABLED'),('false','ENABLED')]:
    with self.subTest(enabled=enabled,rule=rule),patch.object(release,'aws',side_effect=configuration(enabled,rule)),self.assertRaisesRegex(RuntimeError,'Hold new admission'):release.auth_maintenance_guard()
   with patch.object(release,'aws',side_effect=configuration()),patch.object(release.admin,'query',return_value=[dict(count=1)]),self.assertRaisesRegex(RuntimeError,'Drain active'):release.auth_maintenance_guard()
   with patch.object(release,'aws',side_effect=configuration()),patch.object(release.admin,'query',return_value=[dict(count=0)]):release.auth_maintenance_guard()
 def test_maintenance_restores_prior_service_state_on_success_or_failure(self):
  # Execute the real shell lifecycle with a synthetic systemctl executable;
  # no sudo, AWS, actual service action, native sign-in or credentials.
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);tool=root/'systemctl';tool.write_text('#!/bin/sh\nif test "$1" = is-active; then test "$TASK_SERVICE_ACTIVE" = 1; else printf "%s\\n" "$1" >> "$TASK_SERVICE_LOG"; fi\n');tool.chmod(0o755)
   for active in ('0','1'):
    for code in (0,7):
     log=root/('calls-'+active+'-'+str(code));env=dict(os.environ,PATH=str(root)+':/usr/bin:/bin',TASK_SERVICE_ACTIVE=active,TASK_SERVICE_LOG=str(log))
     result=subprocess.run(['/bin/bash','-c',release.auth_maintenance_script('/bin/sh -c '+shlex.quote('exit '+str(code)))],env=env,capture_output=True,timeout=5)
     self.assertEqual(result.returncode,code,result.stderr);self.assertEqual(log.read_text().splitlines() if log.exists() else [],['stop','start'] if active=='1' else [])
 def test_native_login_and_forced_refresh_use_the_same_private_owner_lock(self):
  self.assertIn('flock -x /var/lib/jumpserve-openclaw/auth/refresh.lock',release.native_auth_command())
  command=release.host_refresh_command();self.assertIn('r.credential(force_refresh=True)',command);self.assertNotIn('refreshTokenSharingCredential',command);self.assertNotIn('UPDATE config_machine_state',command)


class HostMaintenance(unittest.TestCase):
    def test_aws_wrapper_keeps_fixed_profile_region_and_timeout(self):
        with patch.object(release.subprocess, 'check_output', return_value=b'{"Account":"fixed"}') as run:
            self.assertEqual(release.aws('sts', 'get-caller-identity'), {'Account': 'fixed'})
        self.assertEqual(run.call_args.args[0], ['aws', 'sts', 'get-caller-identity', '--profile', 'jumpserve', '--region', 'us-east-1', '--output', 'json'])
        self.assertEqual(run.call_args.kwargs, {'timeout': 60})
        with patch.object(release.subprocess, 'check_output', return_value=b''):
            self.assertEqual(release.aws('ssm', 'synthetic-operation'), {})

    def test_target_checks_aws_and_supabase_before_using_shared_security_guard(self):
        with patch.object(release.security, 'target', return_value={'database': 'synthetic'}) as guard:
            for account, project in [('other-account', 'regphejnlvfpyokpniny'), ('395567831870', 'other-project')]:
                with self.subTest(account=account, project=project), patch.object(release, 'aws', return_value={'Account': account}), patch.object(release.admin, 'PROJECT_REF', project):
                    with self.assertRaisesRegex(RuntimeError, 'Release target mismatch'):
                        release.target()
            guard.assert_not_called()
            with patch.object(release, 'aws', return_value={'Account': '395567831870'}), patch.object(release.admin, 'PROJECT_REF', 'regphejnlvfpyokpniny'):
                self.assertEqual(release.target(), {'database': 'synthetic', 'aws_account': '395567831870', 'supabase_project': 'regphejnlvfpyokpniny'})
            guard.assert_called_once_with()

    def test_ssm_uses_the_guarded_existing_worker_identity(self):
        stack = {'Stacks': [{'Outputs': [{'OutputKey': 'OpenClawWorkerInstanceId', 'OutputValue': 'i-abc123'}]}]}
        with patch.object(release, 'aws', return_value=stack):
            self.assertEqual(release.instance(), 'i-abc123')
            stack['Stacks'][0]['Outputs'][0]['OutputValue'] = 'arbitrary-target'
            with self.assertRaisesRegex(RuntimeError, 'Invalid worker identity'):
                release.instance()
        with patch.object(release, 'instance', return_value='i-abc123'), patch.object(release, 'aws', return_value={'Command': {'CommandId': 'synthetic-command'}}) as aws:
            self.assertEqual(release.ssm(['fixed command']), {'command_id': 'synthetic-command', 'instance_id': 'i-abc123'})
        self.assertEqual(aws.call_args.args, ('ssm', 'send-command', '--instance-ids', 'i-abc123', '--document-name', 'AWS-RunShellScript', '--parameters', json.dumps({'commands': ['fixed command']})))

    def test_removed_release_modes_fail_before_target_or_cloud_access(self):
        for mode in ['deploy', 'activate', 'migrate', 'record-result', 'host-repair']:
            with self.subTest(mode=mode), patch.object(sys, 'argv', ['maintenance', mode]), patch.object(release, 'target') as target, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    release.main()
                self.assertEqual(stopped.exception.code, 2)
                target.assert_not_called()

    def run_mode(self, root, mode, *, session_status=0, submission_error=None):
        with patch.object(release, 'ROOT', root), patch.object(sys, 'argv', ['maintenance', mode]), patch.object(release, 'target', return_value={'synthetic_target': True}), patch.object(release, 'instance', return_value='i-abc123'), patch.object(release, 'auth_maintenance_guard') as guard, patch.object(release, 'ssm', return_value={'command_id': 'synthetic-command'}, side_effect=submission_error) as ssm, patch.object(release.subprocess, 'run', return_value=types.SimpleNamespace(returncode=session_status)) as session, contextlib.redirect_stdout(io.StringIO()):
            failure = None
            try:
                release.main()
            except RuntimeError as error:
                failure = str(error)
            receipts = list(root.glob('.test-artifacts/openclaw-maintenance/*/receipt.json'))
            receipt = json.loads(receipts[0].read_text()) if receipts else None
            return receipt, failure, guard, ssm, session

    def test_target_is_read_only_and_writes_no_maintenance_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt, failure, guard, ssm, session = self.run_mode(Path(temporary), 'target')
        self.assertIsNone(receipt)
        self.assertIsNone(failure)
        guard.assert_not_called(); ssm.assert_not_called(); session.assert_not_called()

    def test_native_sign_in_retains_admission_lock_and_private_failure_receipts(self):
        for status in [0, 7]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                receipt, failure, guard, ssm, session = self.run_mode(root, 'native-auth', session_status=status)
                guard.assert_called_once_with(); ssm.assert_not_called()
                args = session.call_args.args[0]
                self.assertEqual(args[args.index('--document-name') + 1], 'AWS-StartInteractiveCommand')
                self.assertIn('flock -x /var/lib/jumpserve-openclaw/auth/refresh.lock', args[-1])
                self.assertEqual(session.call_args.kwargs['timeout'], 900)
                self.assertTrue(session.call_args.kwargs['env']['PATH'].startswith(str(root / '.test-artifacts/openclaw-release/tools/sessionmanager-bundle/bin')))
                self.assertEqual(receipt['status'], 'complete' if status == 0 else 'failed')
                if status == 0:
                    self.assertFalse(receipt['authorization_verified'])
                    self.assertIsNone(failure)
                else:
                    self.assertIn('never inference', failure)
                path = next(root.glob('.test-artifacts/openclaw-maintenance/*/receipt.json'))
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_refresh_and_host_check_submit_only_the_fixed_commands(self):
        for mode in ['host-refresh', 'host-check']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / 'research-workflow-runtime.json').write_text(json.dumps({'files': {'runtime.py': 'a' * 64}}))
                receipt, failure, guard, ssm, session = self.run_mode(root, mode)
                self.assertIsNone(failure); session.assert_not_called()
                self.assertEqual(receipt['ssm']['command_id'], 'synthetic-command')
                command = ssm.call_args.args[0][0]
                program = shlex.split(command)[-1]
                compile(program, '<fixed-host-check>', 'exec')
                if mode == 'host-refresh':
                    self.assertIn('r.credential(force_refresh=True)', program)
                else:
                    self.assertIn("'runtime.py': '" + 'a' * 64 + "'", program)
                    self.assertIn("assert actual==expected", program)
                    self.assertIn('catalog=r.catalog(r.credential())', program)

    def test_uncertain_submission_is_retained_as_failed_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt, failure, guard, ssm, session = self.run_mode(Path(temporary), 'host-refresh', submission_error=RuntimeError('uncertain submission'))
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(failure, 'uncertain submission')
        ssm.assert_called_once(); session.assert_not_called()
