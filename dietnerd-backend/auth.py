"""Accounts, sessions and password resets for DietNerd.

Passwords are stored as bcrypt hashes. Accounts created before bcrypt was
introduced hold an unsalted SHA-256 hex digest; those are accepted once and
upgraded to bcrypt on the next successful login.

Sessions and reset tokens are random values handed to the browser. Only their
SHA-256 digest is stored, so a database leak does not hand out live sessions.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from typing import Optional

import bcrypt

SESSION_COOKIE = "dietnerd_session"
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_HOURS", "168")) * 3600
RESET_TTL_SECONDS = int(os.getenv("RESET_TTL_MINUTES", "30")) * 60
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt only uses the first 72 bytes

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LEGACY_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> Optional[str]:
    if not email or len(email) > 255 or not EMAIL_RE.match(email):
        return "Please enter a valid email address."
    return None


def validate_password(password: str) -> Optional[str]:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored: str) -> tuple:
    """Return (matches, needs_upgrade)."""
    if not stored:
        return False, False
    if stored.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode(), stored.encode()), False
        except ValueError:
            return False, False
    if _LEGACY_SHA256_RE.match(stored):
        legacy = hashlib.sha256(password.encode()).hexdigest()
        ok = hmac.compare_digest(legacy, stored)
        return ok, ok
    return False, False


# A bcrypt hash of a random value, used so unknown-email logins spend the same
# time as real ones and do not reveal which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_time(password: str) -> None:
    verify_password(password or "x", _DUMMY_HASH)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_settings() -> dict:
    samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    secure = os.getenv("COOKIE_SECURE", "1" if samesite == "none" else "0") == "1"
    return {"httponly": True, "samesite": samesite, "secure": secure, "path": "/"}


class RateLimiter:
    """Small in-process sliding window limiter (single replica deployment)."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self.hits = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

    def reset(self):
        self.hits.clear()


def send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send the reset link over SMTP when configured; otherwise log it.

    Required env for real delivery: SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, MAIL_FROM. Without them (local development) the link is
    written to the server log so the flow can still be exercised.
    """
    host = os.getenv("SMTP_HOST")
    body = (
        "Someone asked to reset the password for your DietNerd account.\n\n"
        f"Use this link within {RESET_TTL_SECONDS // 60} minutes to choose a new password:\n"
        f"{reset_url}\n\n"
        "If you did not ask for this, you can ignore this email. Your password has not changed.\n"
    )
    if not host:
        logging.warning("[AUTH] SMTP not configured; password reset link for %s: %s", to_email, reset_url)
        return False
    msg = EmailMessage()
    msg["Subject"] = "Reset your DietNerd password"
    msg["From"] = os.getenv("MAIL_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = to_email
    msg.set_content(body)
    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except Exception:  # never reveal delivery problems to the caller
        logging.exception("[AUTH] Failed to send password reset email")
        return False
