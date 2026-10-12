import pathlib, sys, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'dietnerd-backend'))
import main

class ArticleEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(main.app)
    def test_numeric_article_is_scoped_to_server_row(self):
        class Cursor:
            def execute(self, sql, params):
                assert sql.startswith('SELECT article_json FROM article_analysis WHERE article_id = %s')
                assert params == ('12345',)
            def fetchone(self):
                return ('{"title":"Test trial","citation":"Author. Test trial.","summary":"1. Purpose & Design: Test","url":"https://pubmed.ncbi.nlm.nih.gov/12345/","full_text":"PRIVATE FULL TEXT"}',)
        class Connection:
            def cursor(self): return Cursor()
            def close(self): pass
        main.app.dependency_overrides[main.current_user]=lambda:'test@example.com'
        try:
            with patch.object(main,'_get_db_connection',return_value=Connection()):
                result=self.client.get('/articles/12345')
            self.assertEqual(result.status_code,200,result.text)
            self.assertNotIn('full_text',result.json())
            self.assertEqual(result.json()['pmid'],'12345')
            self.assertEqual(self.client.get('/articles/not-a-pmid').status_code,404)
        finally:
            main.app.dependency_overrides.clear()

if __name__ == '__main__': unittest.main()
