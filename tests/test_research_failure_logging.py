"""Research failures log only exception types, never secret or request text."""
import importlib
import os
import pathlib
import sys
from unittest.mock import MagicMock, patch

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-only-placeholder')
main = importlib.import_module('main')


def test_failure_logs_cause_types_without_exception_text():
    secret = 'sk-never-log-this-value'
    root = OSError(f'connection failed with {secret}')
    nested = ConnectionError('secret in nested text')
    nested.__cause__ = root
    error = RuntimeError('private user query')
    error.__cause__ = nested
    fake_loop = MagicMock()
    with patch.object(main, 'process_user_query', side_effect=error), patch.object(main, 'send_update', new=lambda *args, **kwargs: None), patch.object(main, 'loop', fake_loop), patch.object(main.logging, 'error') as log:
        main._run_research_with_key('private query', 'req', 'test@example.invalid', 'conv')
    fmt, *params = log.call_args.args
    rendered = fmt % tuple(params)
    assert 'RuntimeError' in rendered and 'ConnectionError>OSError' in rendered
    assert secret not in rendered and 'private user query' not in rendered and 'secret in nested text' not in rendered
