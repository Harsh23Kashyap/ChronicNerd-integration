"""Accounts, sessions, route protection and password reset against real MySQL."""
import hashlib
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "dietnerd-backend"
sys.path.insert(0, str(BACKEND))
import main  # noqa: E402

pytestmark = pytest.mark.skipif(os.getenv("RUN_MYSQL_INTEGRATION") != "1", reason="needs MySQL")

A = "auth-a@example.com"
B = "auth-b@example.com"
LEGACY = "auth-legacy@example.com"
PASSWORD = "correct horse 1"


def _db(sql, params=()):
    connection = main._get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall() if cursor.with_rows else None
        connection.commit()
        return rows
    finally:
        connection.close()


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.create_tables()

    def setUp(self):
        for email in (A, B, LEGACY):
            _db("DELETE FROM users WHERE email = %s", (email,))
        main.login_limiter.reset()
        main.reset_limiter.reset()

    def client(self):
        return TestClient(main.app)

    def register(self, email, password=PASSWORD):
        c = self.client()
        r = c.post("/register", json={"email": email, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    # --- registration and login -------------------------------------------------
    def test_register_stores_bcrypt_and_signs_in(self):
        c = self.register(A.upper())
        stored = _db("SELECT password FROM users WHERE email = %s", (A,))[0][0]
        self.assertTrue(stored.startswith("$2"))
        self.assertNotIn(PASSWORD, stored)
        self.assertEqual(c.get("/me").json(), {"email": A})
        cookie = c.cookies.get(main.auth.SESSION_COOKIE)
        self.assertTrue(cookie)
        # Only the digest of the session token is stored.
        rows = _db("SELECT token_hash FROM user_sessions WHERE email = %s", (A,))
        self.assertEqual(rows[0][0], hashlib.sha256(cookie.encode()).hexdigest())

    def test_register_validation(self):
        c = self.client()
        self.assertEqual(c.post("/register", json={"email": "not-an-email", "password": PASSWORD}).status_code, 400)
        self.assertEqual(c.post("/register", json={"email": A, "password": "short"}).status_code, 400)
        self.register(A)
        dup = c.post("/register", json={"email": A, "password": PASSWORD})
        self.assertEqual(dup.status_code, 409)

    def test_login_errors_do_not_reveal_which_emails_exist(self):
        self.register(A)
        c = self.client()
        wrong = c.post("/login", json={"email": A, "password": "wrong password"})
        unknown = c.post("/login", json={"email": "nobody@example.com", "password": "wrong password"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_legacy_sha256_password_is_upgraded_on_login(self):
        legacy = hashlib.sha256(PASSWORD.encode()).hexdigest()
        _db("INSERT INTO users (email, password) VALUES (%s, %s)", (LEGACY, legacy))
        c = self.client()
        self.assertEqual(c.post("/login", json={"email": LEGACY, "password": PASSWORD}).status_code, 200)
        stored = _db("SELECT password FROM users WHERE email = %s", (LEGACY,))[0][0]
        self.assertTrue(stored.startswith("$2"))
        again = self.client().post("/login", json={"email": LEGACY, "password": PASSWORD})
        self.assertEqual(again.status_code, 200)

    def test_login_is_rate_limited(self):
        self.register(A)
        c = self.client()
        codes = [c.post("/login", json={"email": A, "password": "wrong password"}).status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)

    def test_logout_ends_the_session(self):
        c = self.register(A)
        self.assertEqual(c.post("/logout").status_code, 200)
        self.assertEqual(c.get("/me").status_code, 401)
        self.assertEqual(_db("SELECT COUNT(*) FROM user_sessions WHERE email = %s", (A,))[0][0], 0)

    def test_expired_session_is_rejected(self):
        c = self.register(A)
        _db("UPDATE user_sessions SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) WHERE email = %s", (A,))
        self.assertEqual(c.get("/me").status_code, 401)

    def test_bearer_token_works_for_api_clients(self):
        c = self.register(A)
        token = c.cookies.get(main.auth.SESSION_COOKIE)
        r = self.client().get("/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json(), {"email": A})

    # --- route protection ---------------------------------------------------------
    def test_every_user_route_requires_a_session(self):
        c = self.client()
        calls = [
            ("get", "/conversations", {}),
            ("post", "/conversations", {}),
            ("delete", "/conversations/x", {}),
            ("get", "/session_memory", {"params": {"conversation_id": "x"}}),
            ("delete", "/session_memory", {"params": {"conversation_id": "x"}}),
            ("get", "/list_attachments", {}),
            ("delete", "/remove_attachment", {"params": {"filename": "a.txt"}}),
            ("post", "/process_query", {"json": {"user_query": "q"}}),
            ("post", "/cached_answer", {"json": {"user_query": "q"}}),
            ("get", "/check_valid/q", {}),
            ("get", "/db_sim_search/q", {}),
            ("get", "/sse", {"params": {"request_id": "x"}}),
            ("get", "/me", {}),
            ("post", "/change_password", {"json": {"current_password": "a", "new_password": "b"}}),
        ]
        for method, path, kwargs in calls:
            with self.subTest(path=path, method=method):
                self.assertEqual(getattr(c, method)(path, **kwargs).status_code, 401)
        upload = c.post("/upload_attachment", files={"attachment": ("a.txt", b"hi", "text/plain")})
        self.assertEqual(upload.status_code, 401)

    def test_caller_supplied_email_is_ignored(self):
        a = self.register(A)
        self.register(B)
        # A tries to act as B by passing B's email; the session wins.
        created = a.post("/conversations", params={"email": B}).json()["conversation_id"]
        owner = _db("SELECT email FROM conversations WHERE conversation_id = %s", (created,))[0][0]
        self.assertEqual(owner, A)
        listed_as_b = a.get("/conversations", params={"email": B}).json()["conversations"]
        self.assertEqual([c["conversation_id"] for c in listed_as_b], [created])

    def test_users_cannot_see_or_change_each_others_data(self):
        a = self.register(A)
        b = self.register(B)
        conv = a.post("/conversations").json()["conversation_id"]
        a.post("/upload_attachment", files={"attachment": ("notes.txt", b"A's private notes", "text/plain")})

        self.assertEqual(b.get("/conversations").json()["conversations"], [])
        self.assertEqual(b.get("/session_memory", params={"conversation_id": conv}).status_code, 404)
        self.assertEqual(b.delete("/session_memory", params={"conversation_id": conv}).status_code, 404)
        self.assertEqual(b.delete(f"/conversations/{conv}").status_code, 404)
        self.assertEqual(b.post("/process_query", json={"user_query": "q", "conversation_id": conv}).status_code, 404)
        self.assertEqual(b.get("/list_attachments").json()["documents"], [])
        b.delete("/remove_attachment", params={"filename": "notes.txt"})
        self.assertEqual(a.get("/list_attachments").json()["documents"], ["notes.txt"])
        self.assertEqual(len(a.get("/conversations").json()["conversations"]), 1)

    def test_answer_stream_belongs_to_the_user_who_asked(self):
        a = self.register(A)
        b = self.register(B)
        with patch.object(main, "process_user_query", lambda *args: None):
            started = a.post("/process_query", json={"user_query": "is coffee healthy"}).json()
        request_id = started["request_id"]
        self.assertEqual(b.get("/sse", params={"request_id": request_id}).status_code, 404)
        self.assertEqual(a.get("/sse", params={"request_id": "made-up"}).status_code, 404)
        main.update_queues.pop(request_id, None)
        main.request_owners.pop(request_id, None)

    def test_upload_limits(self):
        a = self.register(A)
        bad_type = a.post("/upload_attachment", files={"attachment": ("x.exe", b"MZ", "application/octet-stream")})
        self.assertEqual(bad_type.status_code, 400)
        with patch.object(main, "MAX_UPLOAD_BYTES", 10):
            too_big = a.post("/upload_attachment", files={"attachment": ("big.txt", b"x" * 11, "text/plain")})
        self.assertEqual(too_big.status_code, 413)
        path_name = a.post("/upload_attachment", files={"attachment": ("../../etc/notes.txt", b"hello", "text/plain")})
        self.assertEqual(path_name.status_code, 200)
        self.assertEqual(a.get("/list_attachments").json()["documents"], ["notes.txt"])

    # --- password reset and change -------------------------------------------------
    def _request_reset(self, email):
        sent = {}
        with patch.object(main.auth, "send_reset_email", lambda to, url: sent.update(to=to, url=url)):
            r = self.client().post("/forgot_password", json={"email": email}, headers={"Origin": "http://localhost:8080"})
        self.assertEqual(r.status_code, 200)
        return r, sent

    def test_forgot_password_reply_is_the_same_for_unknown_emails(self):
        self.register(A)
        known, sent = self._request_reset(A)
        unknown, sent_unknown = self._request_reset("nobody@example.com")
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(sent["to"], A)
        self.assertEqual(sent_unknown, {})
        self.assertTrue(sent["url"].startswith("http://localhost:8080/login.html#reset_token="))

    def test_reset_password_flow(self):
        old_session = self.register(A)
        _, sent = self._request_reset(A)
        token = sent["url"].split("reset_token=")[1]
        self.assertEqual(self.client().post("/reset_password", json={"token": token, "password": "short"}).status_code, 400)
        done = self.client().post("/reset_password", json={"token": token, "password": "brand new pass"})
        self.assertEqual(done.status_code, 200, done.text)
        # Old sessions are signed out, the old password stops working, the new one works.
        self.assertEqual(old_session.get("/me").status_code, 401)
        self.assertEqual(self.client().post("/login", json={"email": A, "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.client().post("/login", json={"email": A, "password": "brand new pass"}).status_code, 200)
        # The link only works once.
        reuse = self.client().post("/reset_password", json={"token": token, "password": "another new pass"})
        self.assertEqual(reuse.status_code, 400)

    def test_reset_link_expires_and_newer_link_replaces_older(self):
        self.register(A)
        _, first = self._request_reset(A)
        _, second = self._request_reset(A)
        first_token = first["url"].split("reset_token=")[1]
        second_token = second["url"].split("reset_token=")[1]
        self.assertEqual(self.client().post("/reset_password", json={"token": first_token, "password": "brand new pass"}).status_code, 400)
        _db("UPDATE password_resets SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) WHERE email = %s", (A,))
        self.assertEqual(self.client().post("/reset_password", json={"token": second_token, "password": "brand new pass"}).status_code, 400)

    def test_change_password_keeps_this_session_and_signs_out_others(self):
        here = self.register(A)
        elsewhere = self.client()
        elsewhere.post("/login", json={"email": A, "password": PASSWORD})
        wrong = here.post("/change_password", json={"current_password": "nope nope", "new_password": "brand new pass"})
        self.assertEqual(wrong.status_code, 400)
        ok = here.post("/change_password", json={"current_password": PASSWORD, "new_password": "brand new pass"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(here.get("/me").status_code, 200)
        self.assertEqual(elsewhere.get("/me").status_code, 401)

    # --- deployment surface ------------------------------------------------------------
    def test_health_and_cors(self):
        c = self.client()
        self.assertEqual(c.get("/health").json(), {"status": "ok", "database": "ok"})
        allowed = c.options("/me", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"})
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://localhost:8080")
        blocked = c.options("/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in blocked.headers})


if __name__ == "__main__":
    unittest.main()
