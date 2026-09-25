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
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}),patch.object(main,'create_conversation') as create,patch.object(main,'_run_research_with_key') as run:
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
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}),patch.object(main,'_run_research_with_key') as run:
            response=self.client.post('/process_query',json={'user_query':'And sleep?', 'temporary':True,'temporary_history':turns})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(run.call_args.args[4], [{'raw_question':'What about fiber?', 'standalone_question':'What about fiber?', 'answer':'First answer'}])
        with main.request_event_lock:
            rid=response.json()['request_id']
            for table in (main.request_events,main.request_event_base,main.request_updated_at,main.request_created_at,main.request_owners): table.pop(rid,None)
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}):
            too_many=self.client.post('/process_query',json={'user_query':'q','temporary':True,'temporary_history':turns*9})
        self.assertEqual(too_many.status_code,400)

    def test_private_validation_has_no_question_in_url(self):
        with patch.object(main,'determine_question_validity',return_value='True'):
            r=self.client.post('/check_valid',json={'user_query':'Sensitive question'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['response'],'good')

    def test_temporary_cannot_attach_saved_conversation(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}):
            response=self.client.post('/process_query',json={'user_query':'q','temporary':True,'conversation_id':'saved'})
        self.assertEqual(response.status_code,400)

class TemporaryAttachmentTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        self.client = TestClient(main.app)
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def payload(self, data=b'Fiber appears in oats.', name='notes.txt'):
        import base64
        return {'user_query': 'What does this say?', 'temporary': True,
                'attachment_filename': name, 'attachment_base64': base64.b64encode(data).decode()}
    def test_attachment_processed_without_account_write(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}), \
             patch.object(main, '_get_db_connection') as db, \
             patch.object(main, '_run_research_with_key') as run:
            r = self.client.post('/process_query/temporary_attachment', json=self.payload())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()['conversation_id'])
        self.assertIn('Fiber appears in oats.', run.call_args.args[5])
        db.assert_not_called()
        rid = r.json()['request_id']
        with main.request_event_lock:
            for table in (main.request_events, main.request_event_base, main.request_updated_at,
                          main.request_created_at, main.request_owners):
                table.pop(rid, None)
    def test_invalid_file_and_saved_conversation_rejected(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}):
            for payload in [self.payload(b'x', 'bad.exe'), self.payload(b'not a pdf', 'notes.pdf'),
                            self.payload(b'x' * (main.MAX_UPLOAD_BYTES + 1))]:
                r = self.client.post('/process_query/temporary_attachment', json=payload)
                self.assertIn(r.status_code, (400, 413), r.text)
            payload = self.payload()
            payload['conversation_id'] = 'saved'
            self.assertEqual(self.client.post('/process_query/temporary_attachment', json=payload).status_code, 400)
            self.assertEqual(self.client.post('/process_query', json=payload).status_code, 400)
