"""Curl reachability probe never needs the API key and has bounded latency."""
import importlib
import os
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-only-placeholder')
main = importlib.import_module('main')


def test_unauthenticated_401_means_network_reachable():
    with patch.object(main.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='401')) as run:
        assert main._openai_network_probe() == {'status': 'reachable', 'http_status': 401}
    args, kwargs = run.call_args
    assert '--max-time' in args[0]
    assert 'Authorization' not in str(args[0])
    assert kwargs['timeout'] == 9


def test_connection_error_is_unreachable():
    with patch.object(main.subprocess, 'run', return_value=SimpleNamespace(returncode=60, stdout='000')):
        assert main._openai_network_probe() == {'status': 'unreachable', 'http_status': None}


def test_timeout_is_unreachable():
    with patch.object(main.subprocess, 'run', side_effect=main.subprocess.TimeoutExpired('curl', 9)):
        assert main._openai_network_probe() == {'status': 'unreachable', 'http_status': None}
