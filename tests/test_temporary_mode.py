import pathlib, sys, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class TemporaryModeTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user]=lambda:'test@example.com'
        self.client=TestClient(main.app)
        self.client.cookies.set(main.auth.SESSION_COOKIE,'test-token')
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_temporary_process_skips_conversation_row_and_persists_only_sse(self):
        with patch.object(main.byok,'get',return_value='sk-test-token-long-value'),patch.object(main,'create_conversation') as create,patch.object(main,'_run_research_with_key') as run:
            response=self.client.post('/process_query',json={'user_query':'Temporary test question','temporary':True})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()['conversation_id'])
        create.assert_not_called()
        run.assert_called_once()
        self.assertIsNone(run.call_args.args[3])
        with main.request_event_lock:
            rid=response.json()['request_id']
            for table in (main.request_events,main.request_event_base,main.request_updated_at,main.request_created_at,main.request_owners): table.pop(rid,None)
    def test_temporary_history_is_bounded_and_passed_to_worker(self):
        turns=[{'raw_question':'What about fiber?', 'answer':'First answer'}]
        with patch.object(main.byok,'get',return_value='sk-test-token-long-value'),patch.object(main,'_run_research_with_key') as run:
            response=self.client.post('/process_query',json={'user_query':'And sleep?', 'temporary':True,'temporary_history':turns})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(run.call_args.args[-1], [{'raw_question':'What about fiber?', 'standalone_question':'What about fiber?', 'answer':'First answer'}])
        with main.request_event_lock:
            rid=response.json()['request_id']
            for table in (main.request_events,main.request_event_base,main.request_updated_at,main.request_created_at,main.request_owners): table.pop(rid,None)
        with patch.object(main.byok,'get',return_value='sk-test-token-long-value'):
            too_many=self.client.post('/process_query',json={'user_query':'q','temporary':True,'temporary_history':turns*9})
        self.assertEqual(too_many.status_code,400)

    def test_private_validation_has_no_question_in_url(self):
        with patch.object(main,'determine_question_validity',return_value='True'):
            r=self.client.post('/check_valid',json={'user_query':'Sensitive question'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['response'],'good')

    def test_temporary_cannot_attach_saved_conversation(self):
        with patch.object(main.byok,'get',return_value='sk-test-token-long-value'):
            response=self.client.post('/process_query',json={'user_query':'q','temporary':True,'conversation_id':'saved'})
        self.assertEqual(response.status_code,400)
