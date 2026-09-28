import pathlib,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'dietnerd-backend'))
import main

class ProcessingTest(unittest.TestCase):
    def test_temporary_answer_does_not_write_any_query_or_article_or_memory_row(self):
        article={'title':'Trial','citation':'Trial cite','summary':'1. Purpose: test','PMID':'123','url':'https://pubmed.ncbi.nlm.nih.gov/123/'}
        with patch.object(main,'check_attachment_exists',return_value=False),patch.object(main,'query_generation',return_value=('general','contention',['q'])),patch.object(main,'collect_articles',return_value=[article]),patch.object(main,'concurrent_relevance_classification',return_value=([article],[])),patch.object(main,'connect_to_reliability_analysis_db') as db,patch.object(main,'article_matching',return_value=([],[article])),patch.object(main,'concurrent_article_processing',return_value=[article]),patch.object(main,'write_articles_to_db') as articlewrite,patch.object(main,'write_output_to_db') as answerwrite,patch.object(main,'append_session_memory') as memorywrite,patch.object(main,'set_conversation_summary') as summarywrite,patch.object(main,'generate_final_response',return_value='What we know\nTest.\n\nWhat we don\'t know\nUnknown.\n\nWhat to ask a dietitian\nAsk.'),patch.object(main,'send_update') as send:
            db.return_value=__import__('pandas').DataFrame([{'x':1}])
            result=main.process_user_query('question','req','test@example.com',None)
        self.assertIn('Test.',result['end_output'])
        for write in (articlewrite,answerwrite,memorywrite,summarywrite):write.assert_not_called()

    def test_temporary_ignores_existing_account_attachments(self):
        with patch.object(main,'check_attachment_exists') as exists,patch.object(main,'query_generation',return_value=('general','contention',['q'])),patch.object(main,'collect_articles',return_value=[]),patch.object(main,'concurrent_relevance_classification',return_value=([],[])),patch.object(main,'connect_to_reliability_analysis_db') as db,patch.object(main,'article_matching',return_value=([],[])),patch.object(main,'concurrent_article_processing',return_value=[]),patch.object(main,'generate_final_response',return_value='Answer'),patch.object(main,'send_update'):
            db.return_value=__import__('pandas').DataFrame([{'x':1}])
            main.process_user_query('question','req','test@example.com',None)
        exists.assert_not_called()

class TemporaryAttachmentProcessingTest(unittest.TestCase):
    def test_document_answer_does_not_touch_saved_documents_or_history(self):
        with patch.object(main, 'check_attachment_exists') as check_saved, \
             patch.object(main, 'get_user_documents') as read_saved, \
             patch.object(main, 'try_answer_from_attachment', return_value=(True, 'The note says oats contain fiber.', None)) as answer, \
             patch.object(main, 'append_session_memory') as memory, \
             patch.object(main, 'write_output_to_db') as db, \
             patch.object(main, 'send_update'):
            result = main.process_user_query('What does it say?', 'req', 'test@example.com', None, [],
                                             'Document: note.txt\nOats contain fiber.')
        self.assertIn('oats contain fiber', result['end_output'])
        answer.assert_called_once()
        check_saved.assert_not_called()
        read_saved.assert_not_called()
        memory.assert_not_called()
        db.assert_not_called()
