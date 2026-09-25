"""Short-lived, process-local OpenAI key scoped to one authenticated session.

Never persist values or include them in repr/errors. A multi-worker deployment needs a
separately reviewed secure secret broker; this in-memory store is single-worker only.
"""
from contextvars import ContextVar, copy_context
from concurrent.futures import ThreadPoolExecutor
from threading import RLock, Thread
import time

from openai import OpenAI
import os

_SCOPE = ContextVar('research_key_scope', default=None)
_TTL_SECONDS = 1800
_lock = RLock()
_sessions = {}  # (hashed session token, user email) -> (opaque key, monotonic expiry)


def purge_expired():
    """Drop expired secrets without waiting for another request to that session."""
    with _lock:
        now = time.monotonic()
        for pair, (_, expiry) in list(_sessions.items()):
            if expiry <= now:
                _sessions.pop(pair, None)


def _sweep_loop():
    while True:
        time.sleep(60)
        purge_expired()


Thread(target=_sweep_loop, name='byok-expiry', daemon=True).start()


def put(token_hash, email, secret):
    if not token_hash or not email or not isinstance(secret, str) or not secret.startswith('sk-') or not 20 <= len(secret) <= 512 or any(ch.isspace() for ch in secret):
        raise ValueError('Invalid API key format.')
    purge_expired()
    with _lock:
        _sessions[(token_hash, email)] = (secret, time.monotonic() + _TTL_SECONDS)
    return _TTL_SECONDS


def get(token_hash, email):
    with _lock:
        item = _sessions.get((token_hash, email))
        if not item:
            return None
        if item[1] <= time.monotonic():
            _sessions.pop((token_hash, email), None)
            return None
        return item[0]


def remove(token_hash, email=None):
    with _lock:
        for pair in list(_sessions):
            if pair[0] == token_hash and (email is None or pair[1] == email):
                _sessions.pop(pair, None)


def remove_user(email, keep_hash=None):
    with _lock:
        for pair in list(_sessions):
            if pair[1] == email and pair[0] != keep_hash:
                _sessions.pop(pair, None)


def activate(token_hash, email):
    """Bind a request to an existing session key, not to the secret itself."""
    return _SCOPE.set((token_hash, email))


def reset(token):
    _SCOPE.reset(token)


_default_client = OpenAI() if os.getenv("OPENAI_API_KEY") else None


class ScopedOpenAI:
    """Deliberately tiny proxy; never retain an OpenAI client with a BYOK secret."""
    @property
    def chat(self):
        scope = _SCOPE.get()
        if scope is not None:
            secret = get(*scope)
            if not secret:
                raise RuntimeError("Research key is no longer available. Add it again and retry.")
            client = OpenAI(api_key=secret)
        else:
            client = _default_client or OpenAI()
        return client.chat


class ContextThreadPoolExecutor(ThreadPoolExecutor):
    """Propagate the request's key into the pipeline's own worker threads."""
    def submit(self, fn, /, *args, **kwargs):
        ctx = copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)
