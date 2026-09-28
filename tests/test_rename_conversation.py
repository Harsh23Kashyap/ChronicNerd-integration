import os, pathlib, sys, unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class FakeCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 1
    def execute(self, sql, params=None):
        self.executed.append((sql, params))
class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
    def cursor(self):
        return self._cursor
    def commit(self):
        pass
    def close(self):
        pass

class RenameConversationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: 'test@example.com'
    def tearDown(self):
        main.app.dependency_overrides.clear()
    def test_rename_updates_title_and_locks(self):
        cursor = FakeCursor()
        with patch.object(main, 'conversation_belongs_to', return_value=True), \
             patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)):
            result = self.client.put('/conversations/conv-1', json={'title': '  PCOS evidence  '})
        self.assertEqual(result.status_code, 200, result.text)
        sql, params = cursor.executed[0]
        self.assertIn('title_locked = 1', sql)
        self.assertEqual(params, ('PCOS evidence', 'test@example.com', 'conv-1'))
        self.assertEqual(result.json()['title'], 'PCOS evidence')
    def test_rejects_bad_titles(self):
        with patch.object(main, 'conversation_belongs_to', return_value=True):
            for title in ('', '   ', 'x' * 121, 'bad\nname'):
                result = self.client.put('/conversations/conv-1', json={'title': title})
                self.assertEqual(result.status_code, 400, repr(title))
    def test_unknown_conversation_is_404(self):
        with patch.object(main, 'conversation_belongs_to', return_value=False):
            result = self.client.put('/conversations/nope', json={'title': 'Fine'})
        self.assertEqual(result.status_code, 404)

class AutoTitleLockTest(unittest.TestCase):
    def test_auto_title_skips_user_locked_rows(self):
        cursor = FakeCursor()
        cursor.fetchone = lambda: None
        response = type('R', (), {'choices': [type('C', (), {'message': type('M', (), {'content': 'Kidney Diet Evidence'})()})()]})()
        with patch.object(main, 'get_session_memory', return_value=[{'query_number': 1, 'raw_question': 'q', 'answer': 'a'}]), \
             patch.object(main, '_get_db_connection', return_value=FakeConnection(cursor)), \
             patch.object(main, 'client', Mock()) as fake_client:
            fake_client.chat.completions.create.return_value = response
            main.update_conversation_title('test@example.com', 'conv-1')
        update_sql = [sql for sql, _ in cursor.executed if sql.startswith('UPDATE')]
        self.assertEqual(len(update_sql), 1)
        self.assertIn('title_locked = 0', update_sql[0])
        self.assertEqual(cursor.executed[-1][1][-1], 2)

if __name__ == '__main__': unittest.main()
