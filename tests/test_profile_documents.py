import pathlib, sys, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class Cursor:
    def __init__(self, rows=()):
        self.rows = rows; self.executed = []; self.rowcount = 1
    def execute(self, sql, params=None): self.executed.append((sql, params))
    def fetchall(self): return self.rows
class Connection:
    def __init__(self, cursor): self.c = cursor; self.committed = False
    def cursor(self): return self.c
    def commit(self): self.committed = True
    def close(self): pass

class ProfileDocumentsTest(unittest.TestCase):
    def setUp(self):
        main.app.dependency_overrides[main.current_user] = lambda: 'owner@example.com'
        self.client = TestClient(main.app)
    def tearDown(self): main.app.dependency_overrides.clear()
    def test_list_is_owner_scoped_and_exposes_names_only(self):
        c = Cursor([('blood.csv',), ('notes.txt',)])
        with patch.object(main, '_get_db_connection', return_value=Connection(c)):
            r = self.client.get('/profile/documents')
        self.assertEqual(r.json(), {'documents': ['blood.csv', 'notes.txt']})
        self.assertEqual(c.executed[0][1], ('owner@example.com',))
    def test_upload_is_separate_from_generic_documents(self):
        c = Cursor(); db = Connection(c)
        with patch.object(main, '_get_db_connection', return_value=db):
            r = self.client.post('/profile/documents', files={'attachment': ('note.txt', b'Weight 72 kg', 'text/plain')})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('user_profile_documents', c.executed[0][0])
        self.assertEqual(c.executed[0][1], ('owner@example.com', 'note.txt', 'Weight 72 kg'))
        self.assertTrue(db.committed)
    def test_rejects_invalid_and_oversize(self):
        for name, contents, status in [('bad.md', b'hello', 400), ('bad.pdf', b'not pdf', 400), ('big.txt', b'a'*(main.MAX_UPLOAD_BYTES+1), 413), ('empty.txt', b'', 413)]:
            with self.subTest(name=name):
                self.assertEqual(self.client.post('/profile/documents', files={'attachment': (name, contents)}).status_code, status)
    def test_remove_is_owner_scoped(self):
        c = Cursor(); db = Connection(c)
        with patch.object(main, '_get_db_connection', return_value=db):
            r = self.client.delete('/profile/documents', params={'filename': 'note.txt'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.executed[0][1], ('owner@example.com', 'note.txt'))
        self.assertTrue(db.committed)
    def test_temporary_never_reads_profile_documents(self):
        with patch.object(main, 'get_profile_documents') as files, patch.object(main, 'get_diet_profile_prompt') as profile, \
             patch.object(main, 'try_answer_from_attachment', return_value=(True, 'file answer', None)), \
             patch.object(main, 'send_update'):
            main.process_user_query('q', 'req', 'owner@example.com', None, [], 'Temporary document', None, True)
        files.assert_not_called(); profile.assert_not_called()
    def test_saved_opt_out_never_reads_profile_documents(self):
        with patch.object(main, 'get_profile_documents') as files, patch.object(main, 'get_diet_profile_prompt') as profile, \
             patch.object(main, 'get_session_memory', return_value=[]), \
             patch.object(main, 'try_answer_from_attachment', return_value=(True, 'file answer', None)), \
             patch.object(main, 'append_session_memory'), patch.object(main, 'get_conversation_summary', return_value=''), \
             patch.object(main, 'update_conversation_summary', return_value=''), patch.object(main, 'set_conversation_summary'), \
             patch.object(main, 'send_update'):
            main.process_user_query('q', 'req', 'owner@example.com', 'conv', [], 'Generic document', None, False)
        files.assert_not_called(); profile.assert_not_called()
    def test_saved_opt_in_sends_files_only_to_profile_context(self):
        import pandas as pd
        with patch.object(main, 'get_profile_documents', return_value=[('blood.csv', 'Weight,72 kg')]), \
             patch.object(main, 'get_diet_profile_prompt', return_value='Goal: build muscle'), \
             patch.object(main, 'get_session_memory', return_value=[]), patch.object(main, 'check_attachment_exists', return_value=False), \
             patch.object(main, 'query_generation', return_value=('general', 'contention', ['q'])), \
             patch.object(main, 'collect_articles', return_value=[]), patch.object(main, 'concurrent_relevance_classification', return_value=([], [])), \
             patch.object(main, 'connect_to_reliability_analysis_db', return_value=pd.DataFrame([{'x': 1}])), \
             patch.object(main, 'article_matching', return_value=([], [])), patch.object(main, 'concurrent_article_processing', return_value=[]), \
             patch.object(main, 'generate_final_response', return_value='Answer') as final, \
             patch.object(main, 'write_articles_to_db'), patch.object(main, 'write_output_to_db'), patch.object(main, 'append_session_memory'), \
             patch.object(main, 'get_conversation_summary', return_value=''), patch.object(main, 'update_conversation_summary', return_value=''), \
             patch.object(main, 'set_conversation_summary'), patch.object(main, 'send_update'):
            main.process_user_query('q', 'req', 'owner@example.com', 'conv')
        self.assertIn('Weight,72 kg', final.call_args.kwargs['profile_context'])
        self.assertIsNone(final.call_args.args[2])
