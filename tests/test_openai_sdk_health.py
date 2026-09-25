"""The diagnostic uses a dummy key and returns no provider exception text."""
import importlib
import os
import pathlib
import sys
from unittest.mock import patch

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-only-placeholder')
main = importlib.import_module('main')


def test_dummy_key_authentication_failure_means_reachable():
    class AuthenticationError(Exception):
        status_code = 401

    client = type('Client', (), {'with_options': lambda self, **kwargs: self, 'models': type('Models', (), {'list': lambda self: (_ for _ in ()).throw(AuthenticationError('private secret'))})()})()
    with patch('openai.OpenAI', return_value=client) as ctor:
        outcome = main._openai_sdk_probe()
    assert outcome == {'status': 'reachable', 'http_status': 401}
    assert ctor.call_args.kwargs['api_key'] == 'sk-diagnostic-invalid'


def test_connection_chain_reports_types_and_errno_only():
    err = OSError(101, 'secret message')
    outer = RuntimeError('secret user query')
    outer.__cause__ = err
    client = type('Client', (), {'with_options': lambda self, **kwargs: self, 'models': type('Models', (), {'list': lambda self: (_ for _ in ()).throw(outer)})()})()
    with patch('openai.OpenAI', return_value=client):
        outcome = main._openai_sdk_probe()
    assert outcome == {'status': 'failed', 'error_type': 'RuntimeError', 'http_status': None,
                       'causes': [{'type': 'OSError', 'errno': 101}]}
    assert 'secret' not in str(outcome)
