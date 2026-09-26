import os, pathlib, sys, unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.rowcount = 1 if row else 0
        self.executed = []
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
    def fetchone(self):
        return self.row
class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
    def cursor(self):
        return self._cursor
    def commit(self):
        self.committed = True
    def close(self):
        pass

class DietProfileEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_put_preflight_allows_cross_origin_browser(self):
        response = self.client.options('/profile', headers={
            'Origin': 'http://localhost:8080',
            'Access-Control-Request-Method': 'PUT',
            'Access-Control-Request-Headers': 'content-type'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('PUT', response.headers['access-control-allow-methods'])
    def test_put_upserts_profile(self):
        cursor = FakeCursor()
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            result = self.client.put('/profile', json={'age_range': '25-34', 'goals': 'build muscle', 'conditions': '', 'additional_notes': ''})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn('INSERT INTO user_profiles', cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], ('test@example.com', '25-34', 'build muscle', '', ''))
    def test_put_rejects_bad_age_range_and_long_fields(self):
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(FakeCursor())):
            bad_age = self.client.put('/profile', json={'age_range': 'twenty', 'goals': '', 'conditions': ''})
            long_goals = self.client.put('/profile', json={'age_range': '', 'goals': 'x' * 301, 'conditions': ''})
        self.assertEqual(bad_age.status_code, 400)
        self.assertEqual(long_goals.status_code, 400)
    def test_put_empty_clears_profile(self):
        cursor = FakeCursor()
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            result = self.client.put('/profile', json={'age_range': '', 'goals': '', 'conditions': ''})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn('DELETE FROM user_profiles', cursor.executed[0][0])
    def test_get_returns_saved_profile(self):
        cursor = FakeCursor(row=('25-34', 'build muscle', 'PCOS', 'height 175 cm'))
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            result = self.client.get('/profile')
        self.assertEqual(result.json(), {'age_range': '25-34', 'goals': 'build muscle', 'conditions': 'PCOS', 'additional_notes': 'height 175 cm'})

class DietProfilePromptTest(unittest.TestCase):
    def test_prompt_text_built_from_profile(self):
        with patch.object(main, 'read_diet_profile', return_value={'age_range': '25-34', 'goals': 'build muscle', 'conditions': 'PCOS'}):
            prompt = main.get_diet_profile_prompt('test@example.com')
        self.assertIn('age range 25-34', prompt)
        self.assertIn('goals: build muscle', prompt)
        self.assertIn('conditions or other details: PCOS', prompt)
        self.assertIn('not a diagnosis', prompt)
    def test_additional_notes_reach_profile_prompt(self):
        with patch.object(main, 'read_diet_profile', return_value={'age_range': '', 'goals': 'build muscle', 'conditions': '', 'additional_notes': 'weight 72 kg; height 175 cm'}):
            prompt = main.get_diet_profile_prompt('test@example.com')
        self.assertIn('additional notes: weight 72 kg; height 175 cm', prompt)
    def test_empty_profile_gives_no_prompt(self):
        with patch.object(main, 'read_diet_profile', return_value=None):
            self.assertEqual(main.get_diet_profile_prompt('test@example.com'), '')
    def test_profile_stays_out_of_retrieval_query(self):
        captured = {}
        def capture(question):
            captured['question'] = question
            return ('general', 'contention', ['q'])
        with patch.object(main, 'get_diet_profile_prompt', return_value='PROFILE PROMPT'), \
             patch.object(main, 'get_profile_documents', return_value=[]), \
             patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'check_attachment_exists', return_value=False), \
             patch.object(main, 'query_generation', side_effect=capture), \
             patch.object(main, 'collect_articles', return_value=[]), \
             patch.object(main, 'concurrent_relevance_classification', return_value=([], [])), \
             patch.object(main, 'connect_to_reliability_analysis_db') as db, \
             patch.object(main, 'article_matching', return_value=([], [])), \
             patch.object(main, 'concurrent_article_processing', return_value=[]), \
             patch.object(main, 'generate_final_response', return_value='Answer') as final, \
             patch.object(main, 'write_articles_to_db'), patch.object(main, 'write_output_to_db'), \
             patch.object(main, 'append_session_memory'), patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value=''), patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            db.return_value = __import__('pandas').DataFrame([{'x': 1}])
            main.process_user_query('question', 'req', 'test@example.com', 'conv-1')
        self.assertEqual(captured['question'], 'question')
        self.assertEqual(final.call_args.kwargs['profile_context'], 'PROFILE PROMPT')
    def test_profile_is_not_mislabeled_as_document_evidence(self):
        captured = {}
        def answer(question, context):
            captured['context'] = context
            return (True, 'Grounded response', None)
        with patch.object(main, 'get_diet_profile_prompt', return_value='PROFILE PROMPT'), \
             patch.object(main, 'get_profile_documents', return_value=[]), \
             patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'try_answer_from_attachment', side_effect=answer), \
             patch.object(main, 'append_session_memory'), patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value=''), patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            main.process_user_query('question', 'req', 'test@example.com', 'conv-1', [], 'Document: note.txt\nexample')
        self.assertNotIn('PROFILE PROMPT', captured['context'])

if __name__ == '__main__': unittest.main()

class ConversationProfileBoundaryTest(unittest.TestCase):
    def test_temporary_document_never_reads_profile_even_if_requested(self):
        with patch.object(main, 'get_diet_profile_prompt') as profile, \
             patch.object(main, 'try_answer_from_attachment', return_value=(True, 'Document answer', None)) as answer, \
             patch.object(main, 'send_update'):
            main.process_user_query('q', 'req', 'test@example.com', None, [], 'Document: note', None, True)
        profile.assert_not_called()
        self.assertNotIn('Personalization context', answer.call_args.args[1])

    def test_saved_conversation_opt_out_never_reads_profile(self):
        with patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'get_diet_profile_prompt') as profile, \
             patch.object(main, 'try_answer_from_attachment', return_value=(True, 'Document answer', None)), \
             patch.object(main, 'append_session_memory'), patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value=''), patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            main.process_user_query('q', 'req', 'test@example.com', 'conv-1', [], 'Document: note', None, False)
        profile.assert_not_called()

    def test_temporary_endpoint_overrides_client_profile_true(self):
        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        try:
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), \
                 patch.object(main, '_run_research_with_key') as run:
                response = client.post('/process_query', json={'user_query':'q', 'temporary':True, 'use_profile':True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(run.call_args.args[-2])
            self.assertEqual(run.call_args.args[-1], 'light')
            rid = response.json()['request_id']
            with main.request_event_lock:
                for table in (main.request_events, main.request_event_base, main.request_updated_at,
                              main.request_created_at, main.request_owners): table.pop(rid, None)
        finally:
            main.app.dependency_overrides.clear()

class ConversationProfileEndpointTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        self.client = TestClient(main.app)
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_toggle_is_scoped_to_owner_and_conversation(self):
        cursor = FakeCursor(row=(1,))
        connection = FakeConnection(cursor)
        with patch.object(main, '_get_db_connection', return_value=connection):
            response = self.client.put('/conversations/conv-1/profile', json={'use_profile':False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(cursor.executed[0][1], (0, 'conv-1', 'test@example.com'))
        self.assertTrue(connection.committed)
    def test_unknown_conversation_returns_404(self):
        cursor = FakeCursor(row=None)
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            response = self.client.put('/conversations/not-mine/profile', json={'use_profile':False})
        self.assertEqual(response.status_code, 404)

class ProfileCacheBoundaryTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        self.client = TestClient(main.app)
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_cached_answer_skips_generic_hit_when_profile_exists(self):
        with patch.object(main, 'get_diet_profile_prompt', return_value='goals: muscle') as profile, \
             patch.object(main, 'query_db_final') as cache:
            response = self.client.post('/cached_answer', json={'user_query':'protein'})
        self.assertEqual(response.status_code, 409)
        profile.assert_called_once_with('test@example.com')
        cache.assert_not_called()
    def test_cache_allowed_when_profile_is_off(self):
        with patch.object(main, 'get_diet_profile_prompt') as profile, \
             patch.object(main, 'query_db_final', return_value=[]) as cache:
            response = self.client.post('/cached_answer', json={'user_query':'protein', 'use_profile':False})
        self.assertEqual(response.status_code, 404)
        profile.assert_not_called()
        cache.assert_called_once()

class FinalPromptProfileTest(unittest.TestCase):
    def test_profile_is_distinct_context_and_missing_claim_is_blocked(self):
        from unittest.mock import MagicMock
        import helper_functions as h
        old = h.client
        try:
            h.client = MagicMock()
            h.client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="What we know\nStudy.\n\nWhat we don't know\nUnknown.\n\nWhat to ask a dietitian\nAsk."))]
            h.generate_final_response([], 'How much protein for me?', profile_context='goals: build muscle; conditions or other details: weight 72 kg')
            messages = h.client.chat.completions.create.call_args.kwargs['messages']
            self.assertIn('weight 72 kg', messages[1]['content'])
            self.assertIn('Self-reported diet profile', messages[1]['content'])
            self.assertNotIn('uploaded document', messages[1]['content'])
            self.assertIn('Never say a measurement or goal is missing', messages[0]['content'])
        finally:
            h.client = old
