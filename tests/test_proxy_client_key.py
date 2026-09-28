"""Unauthenticated clients cannot evade the auth limiter with forged XFF."""
import os
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dietnerd-backend'))

class ProxyClientKeyTest(unittest.TestCase):
    def test_forwarded_header_is_not_a_trusted_client_identity(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}):
            import main
        request = SimpleNamespace(headers={'x-forwarded-for': '1.2.3.4'}, client=SimpleNamespace(host='10.1.2.3'))
        self.assertEqual(main._client_key(request), '10.1.2.3')
