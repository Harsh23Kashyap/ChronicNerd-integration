import os, pathlib, sys, unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class FakeCursor:
    def __init__(self, row=None):
        self.row = row
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
            result = self.client.put('/profile', json={'age_range': '25-34', 'goals': 'build muscle', 'conditions': ''})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn('INSERT INTO user_profiles', cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], ('test@example.com', '25-34', 'build muscle', ''))
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
        cursor = FakeCursor(row=('25-34', 'build muscle', 'PCOS'))
        with patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            result = self.client.get('/profile')
        self.assertEqual(result.json(), {'age_range': '25-34', 'goals': 'build muscle', 'conditions': 'PCOS'})

class DietProfilePromptTest(unittest.TestCase):
    def test_prompt_text_built_from_profile(self):
        with patch.object(main, 'read_diet_profile', return_value={'age_range': '25-34', 'goals': 'build muscle', 'conditions': 'PCOS'}):
            prompt = main.get_diet_profile_prompt('test@example.com')
        self.assertIn('age range 25-34', prompt)
        self.assertIn('goals: build muscle', prompt)
        self.assertIn('conditions: PCOS', prompt)
        self.assertIn('not a diagnosis', prompt)
    def test_empty_profile_gives_no_prompt(self):
        with patch.object(main, 'read_diet_profile', return_value=None):
            self.assertEqual(main.get_diet_profile_prompt('test@example.com'), '')
    def test_profile_stays_out_of_retrieval_query(self):
        captured = {}
        def capture(question):
            captured['question'] = question
            return ('general', 'contention', ['q'])
        with patch.object(main, 'get_diet_profile_prompt', return_value='PROFILE PROMPT'), \
             patch.object(main, 'check_attachment_exists', return_value=False), \
             patch.object(main, 'query_generation', side_effect=capture), \
             patch.object(main, 'collect_articles', return_value=[]), \
             patch.object(main, 'concurrent_relevance_classification', return_value=([], [])), \
             patch.object(main, 'connect_to_reliability_analysis_db') as db, \
             patch.object(main, 'article_matching', return_value=([], [])), \
             patch.object(main, 'concurrent_article_processing', return_value=[]), \
             patch.object(main, 'generate_final_response', return_value='Answer') as final, \
             patch.object(main, 'send_update'):
            db.return_value = __import__('pandas').DataFrame([{'x': 1}])
            main.process_user_query('question', 'req', 'test@example.com', None)
        self.assertEqual(captured['question'], 'question')
        self.assertEqual(final.call_args[0][2], 'PROFILE PROMPT')
    def test_profile_reaches_document_answer_context(self):
        captured = {}
        def answer(question, context):
            captured['context'] = context
            return (True, 'Grounded response', None)
        with patch.object(main, 'get_diet_profile_prompt', return_value='PROFILE PROMPT'), \
             patch.object(main, 'try_answer_from_attachment', side_effect=answer), \
             patch.object(main, 'send_update'):
            main.process_user_query('question', 'req', 'test@example.com', None, [], 'Document: note.txt\nexample')
        self.assertIn('PROFILE PROMPT', captured['context'])

if __name__ == '__main__': unittest.main()
