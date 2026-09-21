import importlib.util
import os
from pathlib import Path
import types
import sys
import unittest
from unittest.mock import Mock, patch


class AgentAuthTest(unittest.TestCase):
    def setUp(self):
        self.httpx = types.ModuleType('httpx')
        self.httpx.get = Mock()
        spec = importlib.util.spec_from_file_location('agent_auth_test_target', Path(__file__).parents[1] / 'agent/auth.py')
        self.auth = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'httpx': self.httpx}):
            spec.loader.exec_module(self.auth)
        env = patch.dict(os.environ, SUPABASE_URL='https://supabase.example', SUPABASE_ANON_KEY='public-key')
        env.start()
        self.addCleanup(env.stop)

    def test_missing_token_does_not_call_auth(self):
        with self.assertRaises(self.auth.AuthError) as error:
            self.auth.authenticate({})
        self.assertEqual(error.exception.status, 401)
        self.httpx.get.assert_not_called()

    def test_expired_or_forged_token_is_denied(self):
        self.httpx.get.return_value.status_code = 401
        with self.assertRaises(self.auth.AuthError) as error:
            self.auth.authenticate({'headers': {'Authorization': 'Bearer forged'}})
        self.assertEqual(error.exception.status, 401)

    def test_only_verified_google_identity_is_accepted(self):
        for anonymous, provider, expected in [(True, 'google', 403), (False, 'email', 403), (False, 'google', 200)]:
            user = {'id': 'verified', 'email': 'verified@example.test', 'is_anonymous': anonymous, 'identities': [{'provider': provider}]}
            self.httpx.get.return_value = Mock(status_code=200, json=lambda: user)
            event = {'headers': {'authorization': 'Bearer session'}}
            if expected == 200:
                self.assertEqual(self.auth.authenticate(event), (user, 'Bearer session'))
            else:
                with self.assertRaises(self.auth.AuthError) as error:
                    self.auth.authenticate(event)
                self.assertEqual(error.exception.status, expected)

    def test_auth_service_errors_fail_closed(self):
        self.httpx.get.side_effect = RuntimeError('private details')
        with self.assertRaises(self.auth.AuthError) as error:
            self.auth.authenticate({'headers': {'authorization': 'Bearer session'}})
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn('private', str(error.exception))
