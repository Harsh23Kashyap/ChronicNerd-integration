import pathlib, sys, unittest
from fastapi.testclient import TestClient
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "dietnerd-backend"))
import main

class NoPasswordRecoveryTest(unittest.TestCase):
    def test_reset_routes_do_not_exist(self):
        client = TestClient(main.app)
        self.assertEqual(client.post("/forgot_password", json={"email": "someone@example.com"}).status_code, 404)
        self.assertEqual(client.post("/reset_password", json={"token": "anything", "password": "new password"}).status_code, 404)
    def test_warning_on_login_only(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "dietnerd-website"
        login = (root / "login.html").read_text()
        self.assertIn("There is no password recovery or reset for this account. Save your password.", login)
        self.assertNotIn("Forgot password?", login)
        self.assertNotIn("forgot-form", login)
        self.assertNotIn("reset-form", login)
        self.assertNotIn("password recovery or reset", (root / "index.html").read_text())
        self.assertIn("Save this password in your password manager", login)
        self.assertIn('name="username" autocomplete="username"', login)
