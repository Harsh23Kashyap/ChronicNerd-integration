"""BYOK lifecycle and route behavior. Deliberately never print test secrets."""
import os
import pathlib
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main
import byok

KEY = 'sk-' + 'a' * 34
KEY2 = 'sk-' + 'b' * 34

class ByokTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'a@example.test'
        self.origins = main.origins[:]
        main.origins[:] = ['http://localhost:18080']
        self.client = TestClient(main.app, base_url='https://localhost:8000')
        self.client.cookies.set(main.auth.SESSION_COOKIE, 'session-a')

    def tearDown(self):
        byok.remove_user('a@example.test')
        main.app.dependency_overrides.clear()
        main.origins[:] = self.origins

    def test_requires_origin_and_session_isolation_and_removal(self):
        self.assertEqual(self.client.post('/openai_key', json={'api_key': KEY}).status_code, 403)
        r = self.client.post('/openai_key', json={'api_key': KEY}, headers={'Origin': 'http://localhost:18080'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(KEY, r.text)
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/openai_key').json(), {'ready': True})
        second = TestClient(main.app, base_url='https://localhost:8000')
        second.cookies.set(main.auth.SESSION_COOKIE, 'session-b')
        self.assertEqual(second.get('/openai_key').json(), {'ready': False})
        self.assertEqual(self.client.delete('/openai_key', headers={'Origin': 'http://localhost:18080'}).status_code, 200)
        self.assertEqual(self.client.get('/openai_key').json(), {'ready': False})

    def test_validation_never_reflects_secret(self):
        r = self.client.post('/openai_key', json={'api_key': 'invalid-sensitive-string'}, headers={'Origin': 'http://localhost:18080'})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('invalid-sensitive-string', r.text)
        huge = self.client.post('/openai_key', json={'api_key': 'sk-' + 'x' * 1100}, headers={'Origin': 'http://localhost:18080'})
        self.assertEqual(huge.status_code, 413)
        wrong_type = self.client.post('/openai_key', json={'api_key': {'value': KEY}}, headers={'Origin': 'http://localhost:18080'})
        self.assertEqual(wrong_type.status_code, 400)
        self.assertNotIn(KEY, wrong_type.text)

    def test_expiry_and_context_reset(self):
        with patch.object(byok.time, 'monotonic', return_value=100):
            byok.put('hash', 'a@example.test', KEY)
        with patch.object(byok.time, 'monotonic', return_value=1901):
            self.assertIsNone(byok.get('hash', 'a@example.test'))
        byok.put("scope-hash", "a@example.test", KEY)
        scope = byok.activate("scope-hash", "a@example.test")
        try:
            with byok.ContextThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(byok._SCOPE.get).result(), ("scope-hash", "a@example.test"))
        finally:
            byok.reset(scope)
        self.assertIsNone(byok._SCOPE.get())

    def test_proxy_uses_correct_secret_and_revocation_fails_closed(self):
        found = []
        class FakeClient:
            def __init__(self, api_key=None): self.chat = api_key
        byok.put('scope-hash', 'a@example.test', KEY)
        with patch.object(byok, 'OpenAI', side_effect=lambda api_key=None: FakeClient(api_key)):
            proxy = byok.ScopedOpenAI()
            scope = byok.activate('scope-hash', 'a@example.test')
            try:
                found.append(proxy.chat)
                byok.remove('scope-hash')
                with self.assertRaisesRegex(RuntimeError, 'no longer available'):
                    proxy.chat
            finally: byok.reset(scope)
        self.assertEqual(found, [KEY])

if __name__ == '__main__': unittest.main()
