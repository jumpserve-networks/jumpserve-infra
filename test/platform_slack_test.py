"""No paid calls: exercise original-response retention and Slack authority."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slack_gateway', ROOT / 'assets/platform/slack_gateway.py')
gateway = importlib.util.module_from_spec(spec); spec.loader.exec_module(gateway)
operator_spec = importlib.util.spec_from_file_location('platform_slack', ROOT/'bin/platform-slack.py')
operator = importlib.util.module_from_spec(operator_spec); operator_spec.loader.exec_module(operator)


class Store:
    def __init__(self):
        self.objects = {}; self.records = {}; self.tool_calls = []; self.fail_response = False
        self.enabled = True; self.owner_active = True
    def request(self, path, method='GET', body=None, raw=False):
        if path.startswith('/rest/v1/platform_slack_bindings?'):
            return [dict(enabled=self.enabled, delegated_by='94fe1491-0e02-492b-b907-4db9ef12d09d')]
        if path.startswith('/rest/v1/platform_operators?'):
            return [dict(user_id='94fe1491-0e02-492b-b907-4db9ef12d09d')] if self.owner_active else []
        if path.startswith('/rest/v1/platform_slack_records?'):
            record = path.split('id=eq.')[1].split('&')[0]
            return [self.records[record]] if record in self.records else []
        if path.endswith('/platform_slack_record'):
            self.records[body['p_id']] = dict(sha256=body['p_sha'], byte_count=body['p_bytes']); return {'recorded': True}
        if path.startswith('/storage/'):
            if self.fail_response and (body == b'original provider stream' or self.objects.get(path) == b'original provider stream'):
                raise RuntimeError('Synthetic persistence failure')
            if method == 'POST': self.objects[path] = body; return {}
            if path not in self.objects: raise RuntimeError('Synthetic missing object')
            return self.objects[path]
        self.tool_calls.append((path, body)); return {'recorded': True}


class Transport:
    def __init__(self): self.calls = 0; self.http_status = 200
    def credential(self): return 'synthetic-not-a-real-grant'
    def http_request(self, method, url, token, body):
        self.calls += 1
        assert method == 'POST' and url == 'https://api.openai.com/v1/responses'
        assert json.loads(body)['store'] is False
        response = io.BytesIO(b'original provider stream'); response.status = self.http_status; return response


class Wire:
    def __init__(self): self.cut = False
    def read_stream(self, response, sink, deadline, maximum):
        sink.write(response.read())
        if self.cut: raise ValueError('Synthetic cut stream after dispatch')
        return dict(model=gateway.MODEL, output=[], usage={'input_tokens': 4})
    def usage(self, value): return {'inputTokens': 4}


class SlackGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.store = Store(); self.transport = Transport(); self.wire = Wire()
        self.members = [gateway.OWNER, 'USECOND']
        self.bridge = self.open()
    def tearDown(self): self.bridge.db.close(); self.temp.cleanup()
    def open(self):
        return gateway.Bridge(self.store, self.root, self.transport, self.wire,
                              lambda *args, **kwargs: dict(members=self.members))
    def request(self, text='Hello'):
        return gateway.canonical(dict(model=gateway.MODEL, input=text, tools=[dict(type='function', name='jumpserve_status')]))
    def envelope(self, channel=gateway.CHANNEL, sender='USECOND'):
        return dict(actor=dict(team_id=gateway.TEAM, channel_id=channel, sender_id=sender, session_id=str(uuid.uuid4())),
                    request_id=str(uuid.uuid4()), operation='jumpserve_status', payload={})
    def test_repeated_request_returns_original_without_provider_replay(self):
        self.assertEqual(self.bridge.inference(self.request()), b'original provider stream')
        self.assertEqual(self.bridge.inference(self.request()), b'original provider stream')
        self.assertEqual(self.transport.calls, 1)
        self.assertEqual(len(self.store.records), 3)
        self.assertNotIn(b'synthetic-not-a-real-grant', b''.join(self.store.objects.values()))
    def test_uncertain_call_fences_after_restart(self):
        self.wire.cut = True
        with self.assertRaises(ValueError): self.bridge.inference(self.request())
        self.bridge.db.close(); self.bridge = self.open()
        for text in ('Hello', 'New question'):
            with self.assertRaises(ValueError): self.bridge.inference(self.request(text))
        self.assertEqual(self.transport.calls, 1)
    def test_completed_receipt_survives_crash_before_sqlite_settlement(self):
        self.bridge.inference(self.request())
        self.bridge.db.execute("update calls set status='dispatched'"); self.bridge.db.commit()
        self.bridge.db.close(); self.bridge = self.open()
        self.assertEqual(self.bridge.inference(self.request()), b'original provider stream')
        self.assertEqual(self.transport.calls, 1)
    def test_retained_response_repairs_persistence_without_inference(self):
        self.store.fail_response = True
        with self.assertRaises(RuntimeError): self.bridge.inference(self.request())
        with self.assertRaises(RuntimeError): self.bridge.inference(self.request('Different request before settlement'))
        self.assertEqual(self.transport.calls, 1)
        self.store.fail_response = False
        self.bridge.db.close(); self.bridge = self.open()
        self.assertEqual(self.bridge.inference(self.request()), b'original provider stream')
        self.assertEqual(self.transport.calls, 1)
    def test_model_cannot_expand_tools_or_use_provider_state(self):
        for change in (dict(model='other'), dict(tools=[dict(type='function', name='exec')]), dict(previous_response_id='previous'), dict(background=True)):
            request = json.loads(self.request()); request.update(change)
            with self.assertRaises(ValueError): self.bridge.inference(gateway.canonical(request))
        self.assertEqual(self.transport.calls, 0)
    def test_disabled_or_revoked_delegation_stops_even_cached_responses(self):
        self.bridge.inference(self.request())
        self.store.enabled = False
        with self.assertRaises(ValueError): self.bridge.inference(self.request())
        self.store.enabled = True; self.store.owner_active = False
        with self.assertRaises(ValueError): self.bridge.inference(self.request('New question'))
        self.assertEqual(self.transport.calls, 1)
    def test_definite_http_failure_retains_identity(self):
        self.transport.http_status = 429
        with self.assertRaises(ValueError): self.bridge.inference(self.request())
        with self.assertRaises(ValueError): self.bridge.inference(self.request())
        self.assertEqual(self.transport.calls, 1)
        self.assertEqual(self.bridge.db.execute('select status from calls').fetchone()[0], 'failed')
    def test_every_current_member_can_read_but_removed_members_cannot(self):
        self.bridge.tool(self.envelope())
        self.assertEqual(self.store.tool_calls[-1][1]['p_sender'], 'USECOND')
        self.members.remove('USECOND')
        with self.assertRaises(ValueError): self.bridge.tool(self.envelope())
        self.assertEqual(len(self.store.tool_calls), 1)
    def test_dm_owner_channel_and_payload_boundaries(self):
        for value in (self.envelope('COTHER'), self.envelope('DPRIVATE'),
                      dict(self.envelope(), operation='disable-releases'),
                      dict(self.envelope(), payload={'actor': gateway.OWNER})):
            with self.assertRaises(ValueError): self.bridge.tool(value)
        self.assertEqual(self.store.tool_calls, [])
        self.bridge.tool(self.envelope('DPRIVATE', gateway.OWNER))
        self.assertEqual(self.store.tool_calls[-1][1]['p_channel'], 'DPRIVATE')
    def test_configuration_keeps_only_supervisor_tools_and_isolated_state(self):
        policy = json.loads((ROOT / 'assets/platform/slack-channel-policy.json').read_bytes())
        config = gateway.configuration(self.root, 'http://127.0.0.1:18000', 'synthetic-bridge-key', policy)
        self.assertEqual(config['tools']['allow'], list(gateway.TOOLS))
        self.assertEqual(config['models']['providers']['lab']['models'][0]['id'], gateway.MODEL)
        self.assertFalse(config['browser']['enabled'])
        self.assertFalse(config['commands']['config'])
        self.assertEqual(config['session']['dmScope'], 'per-channel-peer')
        self.assertEqual(config['plugins']['slots']['memory'], 'none')
        self.assertNotIn('users', config['channels']['slack']['channels'][gateway.CHANNEL])
    def test_configuration_uses_native_writer_and_checks_metadata(self):
        policy = json.loads((ROOT/'assets/platform/slack-channel-policy.json').read_bytes())
        config=gateway.configuration(self.root,'http://127.0.0.1:18000','synthetic-local-token',policy)
        path=self.root/'config.json'
        def write(command,**kwargs):
            self.assertIn('--stdin',command)
            self.assertEqual(json.loads(kwargs['input']),config)
            self.assertEqual(kwargs['env']['OPENCLAW_SKIP_CHANNELS'],'1')
            path.write_text(json.dumps(dict(config,meta=dict(lastTouchedVersion='2026.10.5'))))
            return types.SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        with patch.object(gateway.subprocess,'run',side_effect=write):
            actual=gateway.write_configuration(config,path,'node','openclaw.mjs',{})
        self.assertEqual(actual['meta']['lastTouchedVersion'],'2026.10.5')
    def test_members_can_use_controls_without_an_additional_owner_approval(self):
        envelope = dict(self.envelope(), operation='jumpserve_control', payload={'action':'pause'})
        self.bridge.tool(envelope)
        path, params = self.store.tool_calls[-1]
        self.assertTrue(path.endswith('/platform_slack_control'))
        self.assertEqual(params['p_sender'], 'USECOND')
        self.assertEqual(params['p_request'], envelope['request_id'])
        self.assertEqual(params['p_session'], envelope['actor']['session_id'])
        self.assertEqual(params['p_action'], 'pause')
        self.assertIsNone(params['p_task'])
        self.assertNotIn('approval', params)
        task = str(uuid.uuid4())
        envelope['payload'] = dict(action='cancel', task_id=task)
        self.bridge.tool(envelope)
        self.assertEqual(self.store.tool_calls[-1][1]['p_task'], task)
        self.members.remove('USECOND')
        with self.assertRaises(ValueError): self.bridge.tool(envelope)
        self.assertEqual(len(self.store.tool_calls), 2)
    def test_controls_reject_ambiguous_targets_and_forged_fields_before_dispatch(self):
        for payload in ({}, {'action':'cancel'}, {'action':'pause','task_id':str(uuid.uuid4())},
                        {'action':'cancel','task_id':'invalid'}, {'action':'resume','actor':gateway.OWNER},
                        {'action':'arbitrary-command'}, {'action':None}, []):
            with self.assertRaises((ValueError,TypeError,AttributeError)):
                self.bridge.tool(dict(self.envelope(),operation='jumpserve_control',payload=payload))
        self.assertEqual(self.store.tool_calls, [])
    def test_native_nullable_task_argument_allows_global_controls_without_inventing_a_target(self):
        envelope=dict(self.envelope(),operation='jumpserve_control',payload={'action':'resume','task_id':None})
        self.bridge.tool(envelope)
        self.assertEqual(self.store.tool_calls[-1][1]['p_action'],'resume')
        self.assertIsNone(self.store.tool_calls[-1][1]['p_task'])
        for payload in ({'action':'cancel','task_id':None},
                        {'action':'resume','task_id':'00000000-0000-0000-0000-000000000000'}):
            with self.assertRaises(ValueError):self.bridge.tool(dict(envelope,payload=payload))
        self.assertEqual(len(self.store.tool_calls),1)
    def test_task_inspection_binds_identity_and_only_accepts_a_task_id(self):
        task = str(uuid.uuid4())
        envelope = dict(self.envelope(),operation='jumpserve_task',payload={'task_id':task})
        self.bridge.tool(envelope)
        self.assertEqual(self.store.tool_calls[-1][1]['p_task'], task)
        self.assertEqual(self.store.tool_calls[-1][1]['p_channel'], gateway.CHANNEL)
        for payload in ({}, {'task_id':'invalid'}, {'task_id':task,'include_private':True}):
            with self.assertRaises(ValueError): self.bridge.tool(dict(envelope,payload=payload))
        self.assertEqual(len(self.store.tool_calls), 1)
    def test_activation_requires_the_installed_operations_contract(self):
        contract = dict(version='platform-slack-operations-v2',tools=list(gateway.TOOLS),
                        controls=list(gateway.CONTROLS),requires_additional_owner_approval=False)
        store=types.SimpleNamespace(request=lambda *args:contract)
        self.assertEqual(gateway.verify_operations(store), contract)
        for change in (dict(version='old'), dict(tools=['jumpserve_status']),
                       dict(controls=[]), dict(requires_additional_owner_approval=True)):
            with self.assertRaises(ValueError):
                gateway.verify_operations(types.SimpleNamespace(request=lambda *args:dict(contract,**change)))


class SlackCredentialTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(version='jumpserve-slack-v1',team_id=operator.TEAM,channel_id=operator.CHANNEL,
                        app_id=operator.APP,bot_token='xoxb-synthetic-fixture',app_token='',pending='fixture')
        self.writes=0; self.uncertain=False; self.commit=True
    def aws(self,service,operation,payload):
        if service=='sts':return {'Account':operator.ACCOUNT}
        if operation=='get-secret-value':return dict(ARN='arn:aws:secretsmanager:us-east-1:395567831870:secret:'+operator.SECRET+'-fixture',SecretString=json.dumps(self.value),VersionId='synthetic-version')
        if operation=='put-secret-value':
            self.writes+=1
            if self.commit:self.value=json.loads(payload['SecretString'])
            if self.uncertain:raise RuntimeError('Synthetic lost acknowledgment')
            return {'VersionId':'synthetic-version'}
        raise AssertionError('Unexpected AWS operation')
    def store(self):
        with patch.object(operator,'aws',side_effect=self.aws),patch.object(operator,'app_connection',return_value=True):
            return operator.store_token('synthetic-app-credential')
    def test_updates_preserve_bot_and_do_not_return_tokens(self):
        result=self.store()
        self.assertEqual(self.value['bot_token'],'xoxb-synthetic-fixture')
        self.assertNotIn('pending',self.value)
        self.assertNotIn('synthetic-app-credential',json.dumps(result))
        self.assertFalse(self.store()['changed']);self.assertEqual(self.writes,1)
    def test_uncertain_secret_write_is_settled_by_readback_without_rewrite(self):
        self.uncertain=True
        self.assertTrue(self.store()['reconciled']);self.assertEqual(self.writes,1)
    def test_wrong_workspace_and_unconfirmed_write_never_overwrite_again(self):
        self.value['team_id']='TOTHER'
        with self.assertRaises(RuntimeError):self.store()
        self.assertEqual(self.writes,0)
        self.value['team_id']=operator.TEAM;self.uncertain=True;self.commit=False
        with self.assertRaises(RuntimeError):self.store()
        self.assertEqual(self.writes,1)


if __name__ == '__main__': unittest.main()
