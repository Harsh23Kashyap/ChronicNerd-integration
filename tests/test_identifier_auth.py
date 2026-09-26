import pathlib,sys,unittest
from unittest.mock import patch,MagicMock
from fastapi.testclient import TestClient
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'dietnerd-backend'))
import main,auth

class IdentifierAuthTest(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(main.app)
        main.login_limiter.reset()
    def test_identifier_validation(self):
        self.assertIsNone(auth.validate_identifier('someone@example.com'))
        self.assertIsNone(auth.validate_identifier('someone_123'))
        for bad in ('a','1name','bad name','bad@','name.with.dot'):
            self.assertIsNotNone(auth.validate_identifier(bad))
    def test_username_registration_and_email_duplicate(self):
        cursor=MagicMock(); cursor.fetchone.return_value=None
        db=MagicMock();db.cursor.return_value=cursor
        with patch.object(main,'_get_db_connection',return_value=db),patch.object(main,'_create_session',return_value='session'):
            r=self.client.post('/register',json={'email':'My_Name','password':'valid password'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['email'],'my_name')
        self.assertEqual(cursor.execute.call_args_list[1].args[1][0],'my_name')
        cursor.fetchone.return_value=('my_name',)
        with patch.object(main,'_get_db_connection',return_value=db):
            duplicate=self.client.post('/register',json={'email':'MY_NAME','password':'valid password'})
        self.assertEqual(duplicate.status_code,409)
    def test_username_login_and_existing_email_login(self):
        for identifier in ('user_name','old@example.com'):
            cursor=MagicMock();cursor.fetchone.return_value=(auth.hash_password('valid password'),)
            db=MagicMock();db.cursor.return_value=cursor
            with patch.object(main,'_get_db_connection',return_value=db),patch.object(main,'_create_session',return_value='session'):
                r=self.client.post('/login',json={'email':identifier.upper(),'password':'valid password'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['email'],identifier)
            self.assertEqual(cursor.execute.call_args.args[1],(identifier,))
    def test_unknown_and_wrong_username_have_same_error(self):
        db=MagicMock();db.cursor.return_value.fetchone.return_value=None
        with patch.object(main,'_get_db_connection',return_value=db):
            unknown=self.client.post('/login',json={'email':'unknown_name','password':'bad password'})
        db.cursor.return_value.fetchone.return_value=(auth.hash_password('correct password'),)
        with patch.object(main,'_get_db_connection',return_value=db):
            wrong=self.client.post('/login',json={'email':'known_name','password':'bad password'})
        self.assertEqual(unknown.status_code,401)
        self.assertEqual(unknown.json(),wrong.json())
