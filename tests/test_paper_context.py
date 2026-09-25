import os, pathlib, sys, unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

PAPER = {"pmid": "123", "title": "Oat beta-glucan trial", "abstract": "Oats lowered LDL cholesterol.",
         "url": "https://pubmed.ncbi.nlm.nih.gov/123/"}

class PaperContextProcessingTest(unittest.TestCase):
    def test_paper_record_flows_into_attachment_grounding(self):
        captured = {}
        def capture(question, context):
            captured['context'] = context
            return (True, 'The trial found oats lowered LDL.', None)
        with patch.object(main, 'try_answer_from_attachment', side_effect=capture), \
             patch.object(main, 'send_update'):
            result = main.process_user_query('What did it find?', 'req', 'test@example.com', None, [], None, PAPER)
        self.assertIn('oats lowered LDL', result['end_output'])
        self.assertIn('Oat beta-glucan trial', captured['context'])
        self.assertIn('PMID 123', captured['context'])
        self.assertIn('Oats lowered LDL cholesterol.', captured['context'])

    def test_paper_combines_with_saved_documents(self):
        captured = {}
        def capture(question, context):
            captured['context'] = context
            return (True, 'Combined answer.', None)
        with patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'check_attachment_exists', return_value=True), \
             patch.object(main, 'get_user_documents', return_value={'note.txt': 'Personal note text.'}), \
             patch.object(main, 'try_answer_from_attachment', side_effect=capture), \
             patch.object(main, 'append_session_memory'), \
             patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value='summary'), \
             patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            result = main.process_user_query('What did it find?', 'req', 'test@example.com', 'conv-1', None, None, PAPER)
        self.assertIn('Combined answer', result['end_output'])
        self.assertIn('Personal note text.', captured['context'])
        self.assertIn('Oat beta-glucan trial', captured['context'])

class PaperContextEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_rejects_invalid_paper_context(self):
        os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'test')
        for payload in ('not-a-pmid', '١٢٣', '1' * 13):
            result = self.client.post('/process_query', json={
                'user_query': 'q', 'temporary': True, 'paper_pmid': payload})
            self.assertEqual(result.status_code, 400, result.text)
    def test_accepts_valid_paper_context(self):
        os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'test')
        with patch.object(main, '_run_research_with_key') as run, \
             patch.object(main, 'fetch_paper_record', return_value=PAPER) as fetch:
            result = self.client.post('/process_query', json={
                'user_query': 'q', 'temporary': True, 'paper_pmid': '123', 'paper_context': {'pmid': '123', 'title': 'FAKE', 'abstract': 'FAKE'}})
        fetch.assert_called_once_with('123')
        self.assertEqual(result.status_code, 200, result.text)
        run.assert_called_once()
        self.assertEqual(run.call_args[0][6], PAPER)
    def test_paper_context_endpoint_parses_pubmed_record(self):
        fake_record = {'PubmedArticle': [{'MedlineCitation': {'Article': {
            'ArticleTitle': 'Oat beta-glucan trial',
            'Abstract': {'AbstractText': ['Oats lowered LDL cholesterol.']}}}}]}
        fake_entrez = Mock()
        fake_entrez.read.return_value = fake_record
        fake_handle = Mock()
        with patch.object(main, 'Entrez', fake_entrez), \
             patch.object(main, 'exponential_backoff', return_value=fake_handle):
            result = self.client.get('/paper_context/123')
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body['title'], 'Oat beta-glucan trial')
        self.assertEqual(body['abstract'], 'Oats lowered LDL cholesterol.')
        self.assertEqual(body['url'], 'https://pubmed.ncbi.nlm.nih.gov/123/')
        self.assertEqual(self.client.get('/paper_context/not-a-pmid').status_code, 404)

if __name__ == '__main__': unittest.main()
