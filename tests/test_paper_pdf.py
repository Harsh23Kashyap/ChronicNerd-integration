import base64, os, pathlib, sys, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class PaperPDFTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
        os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'test')
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def payload(self, filename='paper.pdf', content=b'%PDF-1.4\nmock pdf'):
        return {'user_query': 'What did it find?', 'temporary': True,
                'attachment_filename': filename,
                'attachment_base64': base64.b64encode(content).decode()}
    def test_pdf_text_is_passed_to_research_not_documents(self):
        with patch.object(main, 'extract_text_from_upload', return_value='Study result: oats lowered LDL.'), \
             patch.object(main, '_run_research_with_key') as run, \
             patch.object(main, 'append_session_memory') as memory:
            result = self.client.post('/process_query/paper_pdf', json=self.payload())
        self.assertEqual(result.status_code, 200, result.text)
        run.assert_called_once()
        self.assertIn('Selected paper PDF: paper.pdf', run.call_args[0][5])
        self.assertIn('Study result: oats lowered LDL.', run.call_args[0][5])
        memory.assert_not_called()
    def test_rejects_non_pdf_and_invalid_bytes(self):
        for payload in (self.payload('notes.txt'), self.payload(content=b'not pdf'),
                        dict(self.payload(), paper_pmid='123')):
            response = self.client.post('/process_query/paper_pdf', json=payload)
            self.assertEqual(response.status_code, 400, response.text)
    def test_rejects_empty_extracted_text(self):
        with patch.object(main, 'extract_text_from_upload', return_value=''):
            result = self.client.post('/process_query/paper_pdf', json=self.payload())
        self.assertEqual(result.status_code, 400)
    def test_saved_chat_uses_selected_paper_instead_of_account_documents(self):
        with patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'get_profile_documents', return_value=[]), \
             patch.object(main, 'check_attachment_exists') as account_docs, \
             patch.object(main, 'try_answer_from_attachment', return_value=(True,'The PDF says oats lowered LDL.',None)) as answer, \
             patch.object(main, 'append_session_memory'), \
             patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value='summary'), \
             patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            main.process_user_query('What did it find?', 'req', 'test@example.com', 'conv-1', None,
                                    'Selected paper PDF: paper.pdf\nOats lowered LDL.')
        account_docs.assert_not_called()
        self.assertIn('Selected paper PDF:', answer.call_args[0][1])

if __name__ == '__main__': unittest.main()
