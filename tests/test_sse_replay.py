"""SSE reconnect should replay completed research without rerunning it."""
import asyncio
import importlib
import os
import pathlib
import sys
from unittest.mock import MagicMock, patch

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-only-placeholder')
main = importlib.import_module('main')


def seed(rid, owner='a@example.invalid'):
    with main.request_event_lock:
        main.request_events[rid] = []
        main.request_event_base[rid] = 0
        main.request_updated_at[rid] = main.time.monotonic()
        main.request_created_at[rid] = main.time.monotonic()
        main.request_owners[rid] = owner


def clean(*rids):
    with main.request_event_lock:
        for rid in rids:
            main.request_events.pop(rid, None)
            main.request_event_base.pop(rid, None)
            main.request_updated_at.pop(rid, None)
            main.request_created_at.pop(rid, None)
            main.request_owners.pop(rid, None)


def test_sse_reconnect_replays_complete_output_and_retains_owner():
    rid = 'test-replay'
    seed(rid)

    async def scenario():
        await main.send_update(rid, 'Retrieved 2 Articles...')
        first = main.event_generator(rid)
        got = await asyncio.wait_for(first.__anext__(), 1)
        assert 'Retrieved 2 Articles' in got['data']
        await first.aclose()
        assert main.request_owners[rid] == 'a@example.invalid'
        await main.send_update(rid, {'end_output': 'finished'})
        second = main.event_generator(rid)
        replay = [event async for event in second]
        assert len(replay) == 2
        assert 'finished' in replay[-1]['data']
    try:
        asyncio.run(scenario())
    finally:
        clean(rid)


def test_concurrent_streams_do_not_cross_and_each_finishes():
    seed('one'); seed('two')
    async def scenario():
        one, two = main.event_generator('one'), main.event_generator('two')
        readers = [asyncio.create_task(one.__anext__()), asyncio.create_task(two.__anext__())]
        await main.send_update('one', {'end_output': 'alpha'})
        await main.send_update('two', {'end_output': 'beta'})
        result = await asyncio.wait_for(asyncio.gather(*readers), 1)
        assert 'alpha' in result[0]['data'] and 'beta' not in result[0]['data']
        assert 'beta' in result[1]['data'] and 'alpha' not in result[1]['data']
        for stream in (one, two):
            try:
                await stream.__anext__()
                assert False, 'stream must end after final event'
            except StopAsyncIteration:
                pass
    try:
        asyncio.run(scenario())
    finally:
        clean('one', 'two')


def test_replay_bounded_and_expired_terminal_pruned():
    rid = 'bounded'
    seed(rid)
    async def scenario():
        for n in range(main.MAX_PROGRESS_EVENTS + 10):
            await main.send_update(rid, str(n))
        await main.send_update(rid, {'end_output': 'last'})
        replay = [event async for event in main.event_generator(rid)]
        assert len(replay) <= main.MAX_PROGRESS_EVENTS + 1
        assert 'last' in replay[-1]['data']
    try:
        asyncio.run(scenario())
        with main.request_event_lock:
            main.request_updated_at[rid] -= main.EVENT_RETENTION_SECONDS + 1
            main._prune_request_events()
            assert rid not in main.request_events
            assert rid not in main.request_owners
    finally:
        clean(rid)


def test_active_stream_keeps_up_after_buffer_trim():
    rid = 'trim-while-reading'
    seed(rid)
    async def scenario():
        stream = main.event_generator(rid)
        await main.send_update(rid, 'initial')
        assert 'initial' in (await stream.__anext__())['data']
        for n in range(main.MAX_PROGRESS_EVENTS + 10):
            await main.send_update(rid, str(n))
        await main.send_update(rid, {'end_output': 'last'})
        continuation = [event async for event in stream]
        assert 'last' in continuation[-1]['data']
    try:
        asyncio.run(scenario())
    finally:
        clean(rid)

def test_article_title_progress_uses_actual_retrieved_titles():
    medline = {'MedlineCitation': {'Article': {'ArticleTitle': 'A real source title'}}}
    captured = []
    async def capture(_rid, event):
        captured.append(event)
    with patch.object(main, 'send_update', new=capture):
        main._send_article_titles('r', [medline, {'title': 'Second title'}, {'title': 'Second title'}], 'retrieved')
    assert captured[0]['article_titles'] == ['A real source title', 'Second title']
    assert 'not verified support' in captured[0]['note']


def test_title_is_thread_scoped_and_stale_generation_cannot_overwrite():
    turns = [{'query_number': 2, 'raw_question': 'Zinc and sleep?', 'answer': 'Small trials.'}]
    cursor = MagicMock()
    db = MagicMock()
    db.cursor.return_value = cursor
    llm = MagicMock()
    llm.choices = [MagicMock(message=MagicMock(content='Zinc Sleep Evidence'))]
    with patch.object(main, 'get_session_memory', return_value=turns), \
         patch.object(main, '_get_db_connection', return_value=db), \
         patch.object(main.client.chat.completions, 'create', return_value=llm):
        main.update_conversation_title('a@example.invalid', 'thread-1')
    sql, args = cursor.execute.call_args.args
    assert 'WHERE email = %s AND conversation_id = %s AND next_query_number = %s' in sql
    assert args == ('Zinc Sleep Evidence', 'a@example.invalid', 'thread-1', 3)
    db.commit.assert_called_once()
