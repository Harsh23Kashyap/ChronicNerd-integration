"""The browser retries only one saved-answer lookup after SSE disconnect.

This is a static contract paired with test_sse_replay's synthetic server stream
and the isolated browser tests. It does not assert restart persistence.
"""
from pathlib import Path

FRONT = (Path(__file__).resolve().parents[1] / 'dietnerd-website' / 'index.js').read_text()


def test_saved_answer_recovered_only_by_matching_request_id():
    assert 'entry.request_id === data.request_id' in FRONT
    assert 'if (saved?.answer) finish({end_output:saved.answer, session_memory_entry:saved})' in FRONT
    assert 'lostAt = 0; // Only one history lookup per interrupted request.' in FRONT


def test_unsaved_request_is_explicit_one_retry_and_stream_closes():
    assert 'Research was interrupted before an answer was saved. Retry once to start a new request.' in FRONT
    assert 'Temporary answers cannot be restored after a disconnect. Retry once' in FRONT
    assert 'eventSource.close();' in FRONT
    assert 'if (settled) return;' in FRONT
