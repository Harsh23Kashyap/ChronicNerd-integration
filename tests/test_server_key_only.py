import os
import pathlib
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class ServerKeyOnlyTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        self.client = TestClient(main.app)
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_no_key_routes(self):
        self.assertEqual(self.client.get('/openai_key').status_code, 404)
        self.assertEqual(self.client.post('/openai_key', json={'api_key':'not-a-real-key'}).status_code, 404)
        self.assertEqual(self.client.delete('/openai_key').status_code, 404)
    def test_missing_server_key_does_not_create_conversation(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, 'create_conversation') as create:
            response = self.client.post('/process_query', json={'user_query':'question'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], 'Research is temporarily unavailable. Please try again later.')
        create.assert_not_called()
    def test_server_key_allows_generation_without_user_key(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test-only'}), patch.object(main, 'create_conversation', return_value='conv-1'), patch.object(main, '_run_research_with_key') as run:
            response = self.client.post('/process_query', json={'user_query':'question'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['conversation_id'], 'conv-1')
        run.assert_called_once()
        with main.request_event_lock:
            rid = response.json()['request_id']
            for table in (main.request_events, main.request_event_base, main.request_updated_at, main.request_created_at, main.request_owners):
                table.pop(rid, None)
