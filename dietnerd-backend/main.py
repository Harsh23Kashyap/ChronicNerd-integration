from helper_functions import *
from conversation_store import append_turn
import auth
from heavy_sources import summarize_selected_pdf

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, UploadFile, File, Form, Depends, Request, Response
from fastapi.responses import StreamingResponse
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import asyncio
from sse_starlette.sse import EventSourceResponse
from concurrent.futures import ThreadPoolExecutor

import uuid
import json
from urllib.parse import unquote

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

import heapq
import hashlib
import base64
import binascii
import os
import mysql.connector

import logging
import re

#Sim search
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import threading
import time
from contextvars import copy_context

logging.basicConfig(level=logging.INFO)

# Replayable, bounded per-request event buffers survive a dropped browser SSE link.
request_events = {}
request_event_base = {}  # First retained sequence number per request.
request_updated_at = {}
request_created_at = {}
request_event_lock = threading.Lock()
EVENT_RETENTION_SECONDS = 600
MAX_PROGRESS_EVENTS = 80
MAX_ACTIVE_REQUESTS = 64

app = FastAPI()

def _allowed_origins():
    configured = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]
    return origins or ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5500", "http://127.0.0.1:5500"]

origins = _allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.on_event("startup")
def create_tables():
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email VARCHAR(255) PRIMARY KEY,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                title VARCHAR(255),
                next_query_number INT NOT NULL DEFAULT 1,
                title_locked TINYINT(1) NOT NULL DEFAULT 0,
                use_profile TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_conversations_email (email),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_session_memory (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                conversation_id VARCHAR(36) NOT NULL,
                query_number INT NOT NULL,
                request_id VARCHAR(36),
                raw_question TEXT,
                standalone_question TEXT,
                answer LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (email),
                UNIQUE KEY uq_conversation_query (conversation_id, query_number),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("SHOW COLUMNS FROM conversations LIKE 'use_profile'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE conversations ADD COLUMN use_profile TINYINT(1) NOT NULL DEFAULT 1")
        cursor.execute("SHOW COLUMNS FROM user_session_memory LIKE 'sources_json'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE user_session_memory ADD COLUMN sources_json LONGTEXT")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_conversation_summary (
                email VARCHAR(255) NOT NULL,
                conversation_id VARCHAR(36) NOT NULL,
                summary LONGTEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (email, conversation_id),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                filename VARCHAR(500) NOT NULL,
                content LONGTEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_email_filename (email, filename),
                INDEX idx_email (email),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profile_documents (
                email VARCHAR(255) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                content LONGTEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (email, filename),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                token_hash CHAR(64) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                INDEX idx_sessions_email (email),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                email VARCHAR(255) PRIMARY KEY,
                age_range VARCHAR(40) NOT NULL DEFAULT '',
                goals VARCHAR(300) NOT NULL DEFAULT '',
                conditions VARCHAR(300) NOT NULL DEFAULT '',
                additional_notes TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        cursor.execute("SHOW COLUMNS FROM user_profiles LIKE 'additional_notes'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE user_profiles ADD COLUMN additional_notes TEXT")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash CHAR(64) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used_at DATETIME NULL,
                INDEX idx_resets_email (email),
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            )
        """)
        # Answer cache and article tables used by the research pipeline. They
        # already exist on the shared DietNerd database; creating them here
        # lets a clean database boot.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_answer (
                question TEXT,
                answer LONGTEXT NOT NULL,
                question_id INT NOT NULL AUTO_INCREMENT,
                to_save TINYINT(1) DEFAULT NULL,
                PRIMARY KEY (question_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_analysis (
                article_id VARCHAR(45) NOT NULL PRIMARY KEY,
                article_json LONGTEXT NOT NULL
            )
        """)
        connection.commit()
        logging.info("[STARTUP] Database tables verified/created")
    finally:
        connection.close()

class QueryModel(BaseModel):
    user_query: str
    # Ignored: the user always comes from the session. Kept optional so older
    # clients that still send it are not rejected.
    email: Optional[str] = None
    conversation_id: Optional[str] = None
    temporary: bool = False
    use_profile: bool = True
    temporary_history: Optional[List[Dict[str, str]]] = None
    attachment_filename: Optional[str] = None
    attachment_base64: Optional[str] = None
    paper_pmid: Optional[str] = None
    answer_mode: str = "light"

class AuthModel(BaseModel):
    email: str
    password: str

class ForgotPasswordModel(BaseModel):
    email: str

class ResetPasswordModel(BaseModel):
    token: str
    password: str

class ChangePasswordModel(BaseModel):
    current_password: str
    new_password: str

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".csv"}
login_limiter = auth.RateLimiter(limit=10, window_seconds=300)
reset_limiter = auth.RateLimiter(limit=5, window_seconds=900)
request_owners: Dict[str, str] = {}

def _get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('host'),
        port=os.getenv('port'),
        user=os.getenv('user'),
        password=os.getenv('password'),
        database=os.getenv('database')
    )

def _client_key(request: Request) -> str:
    # A direct caller can forge X-Forwarded-For. Use the socket peer for auth
    # rate limits; add an edge WAF rate limit when deployed behind an ALB.
    return request.client.host if request.client else "unknown"

def _create_session(email: str) -> str:
    token = auth.new_token()
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO user_sessions (token_hash, email, expires_at) "
            "VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND))",
            (auth.token_digest(token), email, auth.SESSION_TTL_SECONDS),
        )
        connection.commit()
    finally:
        connection.close()
    return token

def _set_session_cookie(response: Response, token: str):
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=auth.SESSION_TTL_SECONDS, **auth.cookie_settings())

def _clear_session_cookie(response: Response):
    settings = auth.cookie_settings()
    response.delete_cookie(auth.SESSION_COOKIE, path=settings["path"], samesite=settings["samesite"], secure=settings["secure"], httponly=True)

def _session_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(auth.SESSION_COOKIE)

def _email_for_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT email FROM user_sessions WHERE token_hash = %s "
            "AND expires_at > UTC_TIMESTAMP() "
            "AND DATE_ADD(created_at, INTERVAL 14 DAY) > UTC_TIMESTAMP()",
            (auth.token_digest(token),),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        connection.close()

def current_user(request: Request) -> str:
    email = _email_for_token(_session_token(request))
    if not email:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return email

def _revoke_sessions(email: str, keep_token: Optional[str] = None):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        if keep_token:
            cursor.execute(
                "DELETE FROM user_sessions WHERE email = %s AND token_hash <> %s",
                (email, auth.token_digest(keep_token)),
            )
        else:
            cursor.execute("DELETE FROM user_sessions WHERE email = %s", (email,))
        connection.commit()
    finally:
        connection.close()

def _set_password(email: str, password: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (auth.hash_password(password), email))
        connection.commit()
    finally:
        connection.close()

@app.get("/health")
async def health():
    try:
        connection = _get_db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            connection.close()
    except Exception:
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
    return {"status": "ok", "database": "ok"}

@app.post("/register")
async def register(auth_body: AuthModel, response: Response):
    email = auth.normalize_email(auth_body.email)
    password = auth_body.password
    problem = auth.validate_identifier(email) or auth.validate_password(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="This email or username is already registered. Try signing in.")
        try:
            cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, auth.hash_password(password)))
            connection.commit()
        except mysql.connector.IntegrityError as exc:
            if getattr(exc, "errno", None) == 1062:
                raise HTTPException(status_code=409, detail="This email or username is already registered. Try signing in.")
            raise
    finally:
        connection.close()
    logging.info("[AUTH] Registered new user")
    token = _create_session(email)
    _set_session_cookie(response, token)
    return {"message": "Registration successful.", "email": email}

@app.post("/login")
async def login(auth_body: AuthModel, request: Request, response: Response):
    email = auth.normalize_email(auth_body.email)
    password = auth_body.password or ""
    if not login_limiter.allow(f"{_client_key(request)}|{email}"):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Please wait a few minutes and try again.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT password FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
    finally:
        connection.close()
    if not row:
        auth.burn_time(password)
        raise HTTPException(status_code=401, detail="Incorrect email/username or password.")
    ok, needs_upgrade = auth.verify_password(password, row[0])
    if not ok:
        raise HTTPException(status_code=401, detail="Incorrect email/username or password.")
    if needs_upgrade:
        _set_password(email, password)
        logging.info("[AUTH] Upgraded legacy password hash to bcrypt")
    token = _create_session(email)
    _set_session_cookie(response, token)
    return {"message": "Login successful.", "email": email}

@app.post("/logout")
async def logout(request: Request, response: Response):
    token = _session_token(request)
    if token:
        connection = _get_db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE token_hash = %s", (auth.token_digest(token),))
            connection.commit()
        finally:
            connection.close()
    _clear_session_cookie(response)
    return {"status": "ok"}

@app.get("/me")
async def me(request: Request, email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT GREATEST(0, TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), "
            "LEAST(expires_at, DATE_ADD(created_at, INTERVAL 14 DAY)))) "
            "FROM user_sessions WHERE token_hash = %s AND email = %s",
            (auth.token_digest(_session_token(request)), email),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Please sign in.")
        return {"email": email, "session_expires_in_seconds": row[0]}
    finally:
        connection.close()

@app.post("/change_password")
async def change_password(body: ChangePasswordModel, request: Request, email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT password FROM users WHERE email = %s", (email,))
        row = cursor.fetchone()
    finally:
        connection.close()
    ok, _ = auth.verify_password(body.current_password or "", row[0] if row else "")
    if not ok:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    problem = auth.validate_password(body.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    _set_password(email, body.new_password)
    keep_token = _session_token(request)
    _revoke_sessions(email, keep_token=keep_token)
    return {"message": "Password updated. Other devices have been signed out."}

disclaimer = """
DietNerd is an exploratory tool designed to enrich your conversations with a registered dietitian or registered dietitian nutritionist, who can then review your profile before providing recommendations.
Please be aware that the insights provided by DietNerd may not fully take into consideration all potential medication interactions or pre-existing conditions.
To find a local expert near you, use this website: https://www.eatright.org/find-a-nutrition-expert
"""

executor = ThreadPoolExecutor()

# Create a global event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def run_in_executor(func, *args):
    return loop.run_in_executor(executor, func, *args)

@app.get("/")
async def root():
    logging.info("Root route accessed")
    return "Hello! Go to /docs!'"

@app.get("/db_sim_search/{question:str}")
async def sim_search(question:str, email: str = Depends(current_user)):
   decoded_query = unquote(question)
   result = await sim_score(decoded_query)
   return result

@app.post("/cached_answer")
async def cached_answer(query: QueryModel, email: str = Depends(current_user)):
    query.email = email
    conversation_id = query.conversation_id
    if query.temporary:
        raise HTTPException(status_code=400, detail="Temporary chats cannot use saved answers.")
    if conversation_id and not conversation_belongs_to(query.email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if query.answer_mode == "heavy":
        raise HTTPException(status_code=409, detail="Heavy mode requires full source research.")
    # Generic cached answers do not carry account profile context. A cache hit
    # must never stand in for a personalized response, regardless of client UI.
    use_profile = conversation_uses_profile(email, conversation_id) if conversation_id else query.use_profile
    if use_profile and (get_diet_profile_prompt(email) or get_profile_documents(email)):
        raise HTTPException(status_code=409, detail="A personalized answer needs fresh research.")

    # Cache lookup uses the literal question. Context rewriting belongs only to
    # the generation path, so a cache miss cannot invoke the rewrite model twice.
    standalone_question = query.user_query
    result = await query_db_final(standalone_question)
    if not result:
        raise HTTPException(status_code=404, detail="Cached answer not found.")

    if not conversation_id:
        conversation_id = create_conversation(query.email, query.user_query[:120], query.use_profile)
    request_id = str(uuid.uuid4())
    cached_payload = result[0][1]
    try:
        cached_answer_text = json.loads(cached_payload)["end_output"]
    except (TypeError, ValueError, KeyError, IndexError):
        raise HTTPException(status_code=500, detail="Cached answer has an invalid format.")
    from answer_sources import extract_answer_sources
    cached_obj = json.loads(cached_payload)
    cached_sources = extract_answer_sources(cached_answer_text, cached_obj.get("citations_obj", {}))
    append_session_memory(query.email, conversation_id, {
        "sources": cached_sources,
        "request_id": request_id,
        "raw_question": query.user_query,
        "standalone_question": standalone_question,
        "answer": cached_answer_text,
    })
    summary = update_conversation_summary(
        get_conversation_summary(query.email, conversation_id),
        standalone_question,
        cached_answer_text,
    )
    set_conversation_summary(query.email, conversation_id, summary)
    logging.info("Conversation title job queued (cache hit)")
    threading.Thread(target=update_conversation_title, args=(query.email, conversation_id), daemon=True).start()
    return {
        "cached_payload": cached_payload,
        "sources": cached_sources,
        "conversation_id": conversation_id,
        "request_id": request_id,
    }

@app.get("/check_valid/{question:str}")
async def check_valid(question:str, email: str = Depends(current_user)):
   question_validity = determine_question_validity(question)
   if question_validity == 'False - Meal Plan/Recipe':
    final_output = ("I'm sorry, I cannot help you with this question. For any questions or advice around meal planning or recipes, please speak to a registered dietitian or registered dietitian nutritionist.\n"
                    "To find a local expert near you, use this website: https://www.eatright.org/find-a-nutrition-expert.")
    print(final_output)
   elif question_validity == 'False - Animal':
    final_output = ("I'm sorry, I cannot help you with this question. For any questions regarding an animal, please speak to a veterinarian.\n"
                   "To find a local expert near you, use this website: https://vetlocator.com/.")
   else:
    final_output = "good"
   return {"response" : final_output}

@app.post("/check_valid")
async def check_valid_private(query: QueryModel, email: str = Depends(current_user)):
    return await check_valid(query.user_query, email)

def create_conversation(email: str, title: Optional[str] = None, use_profile: bool = True) -> str:
    conversation_id = str(uuid.uuid4())
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO conversations (conversation_id, email, title, use_profile) VALUES (%s, %s, %s, %s)",
            (conversation_id, email, title, int(use_profile)),
        )
        connection.commit()
    finally:
        connection.close()
    return conversation_id

def conversation_belongs_to(email: str, conversation_id: str) -> bool:
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT 1 FROM conversations WHERE conversation_id = %s AND email = %s",
            (conversation_id, email),
        )
        return cursor.fetchone() is not None
    finally:
        connection.close()

def conversation_uses_profile(email: str, conversation_id: str) -> bool:
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT use_profile FROM conversations WHERE conversation_id = %s AND email = %s", (conversation_id, email))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return bool(row[0])
    finally:
        connection.close()

def get_session_memory(email: str, conversation_id: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT query_number, request_id, raw_question, standalone_question, answer, sources_json "
            "FROM user_session_memory WHERE email = %s AND conversation_id = %s ORDER BY query_number",
            (email, conversation_id),
        )
        rows = cursor.fetchall()
        for row in rows:
            try:
                row["sources"] = json.loads(row.pop("sources_json") or "[]")
            except (ValueError, TypeError):
                row["sources"] = []
        return rows
    finally:
        connection.close()

def get_conversation_summary(email: str, conversation_id: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT summary FROM user_conversation_summary WHERE email = %s AND conversation_id = %s",
            (email, conversation_id),
        )
        row = cursor.fetchone()
        return row[0] if row else ""
    finally:
        connection.close()

def set_conversation_summary(email: str, conversation_id: str, summary: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO user_conversation_summary (email, conversation_id, summary) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE summary = %s",
            (email, conversation_id, summary, summary),
        )
        connection.commit()
    finally:
        connection.close()

def append_session_memory(email: str, conversation_id: str, entry: dict):
    return append_turn(_get_db_connection, email, conversation_id, entry)

@app.get("/articles/{pmid}")
async def read_article_analysis(pmid: str, email: str = Depends(current_user)):
    if not pmid.isdigit() or len(pmid) > 12:
        raise HTTPException(status_code=404, detail="Article analysis not found.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT article_json FROM article_analysis WHERE article_id = %s", (pmid,))
        row = cursor.fetchone()
    finally:
        connection.close()
    if not row:
        raise HTTPException(status_code=404, detail="Article analysis not found.")
    try:
        article = json.loads(row[0])
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Article analysis not found.")
    if not isinstance(article, dict):
        raise HTTPException(status_code=404, detail="Article analysis not found.")
    return {"pmid": pmid, "title": article.get("title") or "Article analysis",
            "citation": article.get("citation") or "", "summary": article.get("summary") or "",
            "url": article.get("url") if str(article.get("url", "")).startswith("https://") else ""}

def fetch_selected_pmid_articles(pmid: str):
    """Adapt DietNerdV2's selected-PMID lane, retaining authenticated request scope."""
    if not isinstance(pmid, str) or not pmid.isascii() or not pmid.isdigit() or len(pmid) > 12:
        raise ValueError("Invalid selected PMID")
    Entrez.email = os.getenv('ENTREZ_EMAIL')
    Entrez.api_key = os.getenv('NCBI_API_KEY') or None
    handle = exponential_backoff(Entrez.efetch, db="pubmed", id=pmid, rettype="xml")
    try:
        return Entrez.read(handle)["PubmedArticle"]
    finally:
        if handle is not None:
            handle.close()

def fetch_paper_record(pmid: str):
    if not isinstance(pmid, str) or not pmid.isascii() or not pmid.isdigit() or len(pmid) > 12:
        raise HTTPException(status_code=404, detail="Paper not found.")
    try:
        Entrez.email = os.getenv('ENTREZ_EMAIL')
        Entrez.api_key = os.getenv('NCBI_API_KEY') or None
        handle = exponential_backoff(Entrez.efetch, db="pubmed", id=pmid, rettype="xml")
        try:
            records = Entrez.read(handle)["PubmedArticle"]
        finally:
            if handle is not None:
                handle.close()
        if not records:
            raise HTTPException(status_code=404, detail="Paper not found.")
        article = records[0]["MedlineCitation"]["Article"]
        title = str(article.get("ArticleTitle") or "").strip()
        abstract_parts = article.get("Abstract", {}).get("AbstractText", [])
        abstract = "\n".join(str(part) for part in abstract_parts).strip()
        if not title or not abstract:
            raise HTTPException(status_code=404, detail="This paper has no available abstract.")
        return {"pmid": pmid, "title": title[:500], "abstract": abstract[:20000],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Could not reach PubMed. Please try again.")

@app.get("/paper_context/{pmid}")
async def read_paper_context(pmid: str, email: str = Depends(current_user)):
    return await run_in_threadpool(fetch_paper_record, pmid)

@app.post("/conversations")
async def new_conversation(email: str = Depends(current_user)):
    return {"conversation_id": create_conversation(email)}

class ConversationProfileModel(BaseModel):
    use_profile: bool

class RenameModel(BaseModel):
    title: str

@app.put("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, body: RenameModel, email: str = Depends(current_user)):
    title = body.title.strip()
    if not title or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise HTTPException(status_code=400, detail="Enter a name up to 120 characters.")
    if not conversation_belongs_to(email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE conversations SET title = %s, title_locked = 1 WHERE email = %s AND conversation_id = %s",
            (title, email, conversation_id),
        )
        connection.commit()
    finally:
        connection.close()
    return {"conversation_id": conversation_id, "title": title}

@app.put("/conversations/{conversation_id}/profile")
async def set_conversation_profile(conversation_id: str, body: ConversationProfileModel, email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("UPDATE conversations SET use_profile = %s WHERE conversation_id = %s AND email = %s",
                       (int(body.use_profile), conversation_id, email))
        if cursor.rowcount == 0:
            cursor.execute("SELECT 1 FROM conversations WHERE conversation_id = %s AND email = %s", (conversation_id, email))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Conversation not found.")
        connection.commit()
    finally:
        connection.close()
    return {"conversation_id": conversation_id, "use_profile": body.use_profile}

@app.get("/conversations")
async def list_conversations(email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT conversation_id, title, use_profile, created_at, updated_at FROM conversations WHERE email = %s ORDER BY updated_at DESC", (email,))
        return {"conversations": cursor.fetchall()}
    finally:
        connection.close()

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM conversations WHERE conversation_id = %s AND email = %s",
            (conversation_id, email),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        connection.commit()
    finally:
        connection.close()
    return {"status": "ok"}

@app.get("/session_memory")
async def read_session_memory(conversation_id: str = Query(...), email: str = Depends(current_user)):
    if not conversation_belongs_to(email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    entries = get_session_memory(email, conversation_id)
    return {"entries": entries, "count": len(entries), "conversation_summary": get_conversation_summary(email, conversation_id)}

@app.delete("/session_memory")
async def reset_session_memory(conversation_id: str = Query(...), email: str = Depends(current_user)):
    if not conversation_belongs_to(email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM user_session_memory WHERE email = %s AND conversation_id = %s", (email, conversation_id))
        cursor.execute("DELETE FROM user_conversation_summary WHERE email = %s AND conversation_id = %s", (email, conversation_id))
        cursor.execute(
            "UPDATE conversations SET next_query_number = 1 WHERE email = %s AND conversation_id = %s",
            (email, conversation_id),
        )
        connection.commit()
    finally:
        connection.close()
    return {"status": "ok"}

@app.post("/upload_attachment")
async def upload_attachment(attachment: UploadFile = File(...), email: str = Depends(current_user)):
    filename = os.path.basename((attachment.filename or "").replace("\\", "/")).strip()
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=400, detail="Please choose a file with a valid name.")
    if os.path.splitext(filename)[1].lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, TXT and CSV files are supported.")
    file_bytes = await attachment.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    attachment_text = extract_text_from_upload(file_bytes, filename)

    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO user_documents (email, filename, content) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE content = %s",
            (email, filename, attachment_text, attachment_text)
        )
        connection.commit()
    finally:
        connection.close()
    return JSONResponse({"status": "ok"})

@app.get("/list_attachments")
async def list_attachments(email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT filename FROM user_documents WHERE email = %s", (email,))
        rows = cursor.fetchall()
    finally:
        connection.close()
    return JSONResponse({"documents": [row[0] for row in rows]})

@app.delete("/remove_attachment")
async def remove_attachment(filename: str = Query(...), email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM user_documents WHERE email = %s AND filename = %s", (email, filename))
        connection.commit()
    finally:
        connection.close()
    return JSONResponse({"status": "ok"})

ALLOWED_AGE_RANGES = {'18-24', '25-34', '35-44', '45-54', '55-64', '65+'}

class ProfileModel(BaseModel):
    age_range: Optional[str] = None
    goals: Optional[str] = None
    conditions: Optional[str] = None
    additional_notes: Optional[str] = None

def read_diet_profile(email):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT age_range, goals, conditions, additional_notes FROM user_profiles WHERE email = %s", (email,))
        row = cursor.fetchone()
    finally:
        connection.close()
    if not row:
        return None
    return {"age_range": row[0] or "", "goals": row[1] or "", "conditions": row[2] or "", "additional_notes": row[3] or ""}

def get_diet_profile_prompt(email):
    try:
        profile = read_diet_profile(email)
    except Exception:
        logging.warning("Diet profile lookup failed: continuing without it")
        return ""
    if not profile:
        return ""
    parts = []
    if profile["age_range"]:
        parts.append(f"age range {profile['age_range']}")
    if profile["goals"]:
        parts.append(f"goals: {profile['goals']}")
    if profile["conditions"]:
        parts.append(f"conditions or other details: {profile['conditions']}")
    if profile.get("additional_notes"):
        parts.append(f"additional notes: {profile['additional_notes']}")
    if not parts:
        return ""
    return ("The person asking self-reported the following: " + "; ".join(parts) +
            ". Use this only to personalize general guidance; it is not a diagnosis or medical record, and do not repeat it back unless it is relevant.")

@app.get("/profile")
async def get_profile(email: str = Depends(current_user)):
    profile = read_diet_profile(email) or {}
    return {"age_range": profile.get("age_range") or "", "goals": profile.get("goals") or "",
            "conditions": profile.get("conditions") or "", "additional_notes": profile.get("additional_notes") or ""}

@app.put("/profile")
async def put_profile(profile: ProfileModel, email: str = Depends(current_user)):
    age_range = (profile.age_range or "").strip()
    goals = (profile.goals or "").strip()
    conditions = (profile.conditions or "").strip()
    additional_notes = (profile.additional_notes or "").strip()
    if age_range and age_range not in ALLOWED_AGE_RANGES:
        raise HTTPException(status_code=400, detail="Choose an age range from the list.")
    if len(goals) > 300 or len(conditions) > 300 or len(age_range) > 40 or len(additional_notes) > 1000:
        raise HTTPException(status_code=400, detail="Profile fields are too long.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        if not age_range and not goals and not conditions and not additional_notes:
            cursor.execute("DELETE FROM user_profiles WHERE email = %s", (email,))
        else:
            cursor.execute(
                "INSERT INTO user_profiles (email, age_range, goals, conditions, additional_notes) VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE age_range = VALUES(age_range), goals = VALUES(goals), conditions = VALUES(conditions), additional_notes = VALUES(additional_notes)",
                (email, age_range, goals, conditions, additional_notes),
            )
        connection.commit()
    finally:
        connection.close()
    return {"age_range": age_range, "goals": goals, "conditions": conditions}


@app.post("/profile/documents")
async def upload_profile_document(attachment: UploadFile = File(...), email: str = Depends(current_user)):
    filename = os.path.basename((attachment.filename or "").replace("\\", "/")).strip()
    if not filename or len(filename) > 255 or os.path.splitext(filename)[1].lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose a PDF, TXT or CSV file with a valid name.")
    file_bytes = await attachment.read(MAX_UPLOAD_BYTES + 1)
    if not file_bytes or len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    if filename.lower().endswith('.pdf') and not file_bytes.startswith(b'%PDF-'):
        raise HTTPException(status_code=400, detail="The PDF file is invalid.")
    text = extract_text_from_upload(file_bytes, filename).strip()
    if not text:
        raise HTTPException(status_code=400, detail="No readable text was found in this file.")
    if len(text) > 80000:
        raise HTTPException(status_code=413, detail="Extracted text is too long for a profile file.")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO user_profile_documents (email, filename, content) VALUES (%s, %s, %s) "
                       "ON DUPLICATE KEY UPDATE content = VALUES(content)", (email, filename, text))
        connection.commit()
    finally:
        connection.close()
    return {"filename": filename}

@app.get("/profile/documents")
async def list_profile_documents(email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT filename FROM user_profile_documents WHERE email = %s ORDER BY filename", (email,))
        names = [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()
    return {"documents": names}

@app.delete("/profile/documents")
async def remove_profile_document(filename: str = Query(...), email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM user_profile_documents WHERE email = %s AND filename = %s", (email, filename))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Profile file not found.")
        connection.commit()
    finally:
        connection.close()
    return {"status": "ok"}

def get_profile_documents(email: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT filename, content FROM user_profile_documents WHERE email = %s ORDER BY filename", (email,))
        return cursor.fetchall()
    finally:
        connection.close()

@app.post("/process_query/temporary_attachment")
async def process_temporary_attachment(background_tasks: BackgroundTasks, request: Request, email: str = Depends(current_user)):
    body = bytearray()
    max_body = (MAX_UPLOAD_BYTES * 4 // 3) + 24000
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_body:
            raise HTTPException(status_code=413, detail="Temporary file is too large.")
    try:
        query = QueryModel.model_validate_json(bytes(body))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid temporary request.")
    if not query.temporary or query.conversation_id or not query.attachment_filename or not query.attachment_base64:
        raise HTTPException(status_code=400, detail="A temporary file and question are required.")
    filename = os.path.basename(query.attachment_filename.replace("\\", "/")).strip()
    if not filename or len(filename) > 255 or os.path.splitext(filename)[1].lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, TXT and CSV files are supported.")
    try:
        file_bytes = base64.b64decode(query.attachment_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid file data.")
    if not file_bytes or len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    if filename.lower().endswith('.pdf') and not file_bytes.startswith(b'%PDF-'):
        raise HTTPException(status_code=400, detail="The PDF file is invalid.")
    text = extract_text_from_upload(file_bytes, filename).strip()
    if not text:
        raise HTTPException(status_code=400, detail="No readable text was found in this file.")
    if len(text) > 80000:
        raise HTTPException(status_code=413, detail="Extracted text is too long for temporary chat.")
    return await _start_query(background_tasks, query, email, f"Document: {filename}\n{text}")

@app.post("/process_query/paper_pdf")
async def process_paper_pdf(background_tasks: BackgroundTasks, request: Request, email: str = Depends(current_user)):
    # Limit the body before decoding; do not store the selected PDF as an account document.
    body = bytearray()
    max_body = (MAX_UPLOAD_BYTES * 4 // 3) + 24000
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_body:
            raise HTTPException(status_code=413, detail="Paper PDF is too large.")
    try:
        query = QueryModel.model_validate_json(bytes(body))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid paper request.")
    filename = os.path.basename((query.attachment_filename or "").replace("\\", "/")).strip()
    if not filename or len(filename) > 255 or not filename.lower().endswith('.pdf') or not query.attachment_base64:
        raise HTTPException(status_code=400, detail="A PDF paper and question are required.")
    if query.paper_pmid:
        raise HTTPException(status_code=400, detail="Choose either a PubMed paper or a PDF paper.")
    try:
        file_bytes = base64.b64decode(query.attachment_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid PDF data.")
    if not file_bytes or len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"PDF must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    if not file_bytes.startswith(b'%PDF-'):
        raise HTTPException(status_code=400, detail="The PDF file is invalid.")
    text = extract_text_from_upload(file_bytes, filename).strip()
    if not text:
        raise HTTPException(status_code=400, detail="No readable text was found in this PDF.")
    if len(text) > 80000:
        raise HTTPException(status_code=413, detail="Extracted PDF text is too long.")
    return await _start_query(background_tasks, query, email,
                              f"Selected paper PDF: {filename}\n{text}")

@app.post("/process_query")
async def process_query(background_tasks: BackgroundTasks, query: QueryModel, request: Request, email: str = Depends(current_user)):
    if query.attachment_filename is not None or query.attachment_base64 is not None:
        raise HTTPException(status_code=400, detail="Use the temporary file endpoint for attachments.")
    return await _start_query(background_tasks, query, email)

async def _start_query(background_tasks, query, email, temporary_attachment_context=None):
    if query.answer_mode not in ("light", "heavy"):
        raise HTTPException(status_code=400, detail="Invalid answer mode.")
    query.email = email
    paper_context = None
    if query.paper_pmid is not None:
        pmid = query.paper_pmid
        if not isinstance(pmid, str) or not pmid.isascii() or not pmid.isdigit() or len(pmid) > 12:
            raise HTTPException(status_code=400, detail="Invalid paper reference.")
        paper_context = await run_in_threadpool(fetch_paper_record, pmid)
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Research is temporarily unavailable. Please try again later.")
    request_id = str(uuid.uuid4())
    conversation_id = query.conversation_id
    if query.temporary and conversation_id:
        raise HTTPException(status_code=400, detail="Temporary research cannot use a saved conversation.")
    if query.temporary_history and not query.temporary:
        raise HTTPException(status_code=400, detail="Temporary history requires temporary mode.")
    temporary_history = []
    if query.temporary:
        if len(query.temporary_history or []) > 8:
            raise HTTPException(status_code=400, detail="Too many temporary turns.")
        for turn in query.temporary_history or []:
            if not isinstance(turn, dict) or not isinstance(turn.get("raw_question"), str) or not isinstance(turn.get("answer"), str):
                raise HTTPException(status_code=400, detail="Invalid temporary turn.")
            question = turn["raw_question"].strip()
            answer = turn["answer"].strip()
            if not question or not answer or len(question) > 2000 or len(answer) > 15000:
                raise HTTPException(status_code=400, detail="Temporary turn is too large.")
            temporary_history.append({"raw_question": question, "standalone_question": question, "answer": answer})
    if conversation_id and not conversation_belongs_to(query.email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    with request_event_lock:
        _prune_request_events()
        active_count = sum(not (events and isinstance(events[-1], dict) and 'end_output' in events[-1])
                           for events in request_events.values())
        if active_count >= MAX_ACTIVE_REQUESTS:
            raise HTTPException(status_code=503, detail="Research is busy. Please try again shortly.")
        if len(request_events) >= MAX_ACTIVE_REQUESTS * 4:
            completed_ids = [rid for rid, events in request_events.items()
                             if events and isinstance(events[-1], dict) and 'end_output' in events[-1]]
            for rid in sorted(completed_ids, key=lambda r: request_updated_at.get(r, 0))[:MAX_ACTIVE_REQUESTS]:
                request_events.pop(rid, None)
                request_event_base.pop(rid, None)
                request_updated_at.pop(rid, None)
                request_created_at.pop(rid, None)
                request_owners.pop(rid, None)
        request_events[request_id] = []
        request_event_base[request_id] = 0
        request_updated_at[request_id] = time.monotonic()
        request_created_at[request_id] = time.monotonic()
        request_owners[request_id] = email
    if not conversation_id and not query.temporary:
        try:
            conversation_id = create_conversation(query.email, query.user_query[:120], query.use_profile)
        except Exception:
            with request_event_lock:
                request_events.pop(request_id, None)
                request_event_base.pop(request_id, None)
                request_updated_at.pop(request_id, None)
                request_created_at.pop(request_id, None)
                request_owners.pop(request_id, None)
            raise
    # New conversation choice is supplied with creation; existing chats use the stored setting.
    use_profile = False if query.temporary else (query.use_profile if query.conversation_id is None else conversation_uses_profile(query.email, conversation_id))
    background_tasks.add_task(_run_research_with_key, query.user_query, request_id, query.email, conversation_id, temporary_history, temporary_attachment_context, paper_context, use_profile, query.answer_mode)
    return JSONResponse({"request_id": request_id, "conversation_id": conversation_id})

def _prune_request_events():
    """Caller holds request_event_lock. Keep finished events ten minutes for reconnects."""
    now = time.monotonic()
    for rid, seen in list(request_updated_at.items()):
        created = request_created_at.get(rid, seen)
        events = request_events.get(rid, [])
        completed = bool(events and isinstance(events[-1], dict) and 'end_output' in events[-1])
        if (completed and now - seen > EVENT_RETENTION_SECONDS) or now - created > 3600:
            request_updated_at.pop(rid, None)
            request_created_at.pop(rid, None)
            request_events.pop(rid, None)
            request_event_base.pop(rid, None)
            request_owners.pop(rid, None)


@app.get("/sse")
async def sse(request_id: str = Query(default=None), email: str = Depends(current_user)):
    if not request_id:
        raise HTTPException(status_code=400, detail="request_id is required")
    with request_event_lock:
        if request_owners.get(request_id) != email or request_id not in request_events:
            raise HTTPException(status_code=404, detail="Request not found.")
    return EventSourceResponse(event_generator(request_id))


def _serialize_progress_event(data):
    """Keep terminal answer deliverable if article metadata is not JSON-safe."""
    try:
        return json.dumps({"update": data}, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        if isinstance(data, dict) and isinstance(data.get("end_output"), str):
            logging.warning("SSE final metadata serialization failed; sending answer text only")
            return json.dumps({"update": {
                "end_output": data["end_output"],
                "relevant_articles": [], "citations_obj": {}, "citations": [],
            }})
        logging.warning("SSE progress serialization failed; dropping unsafe metadata")
        return json.dumps({"update": "Research is continuing..."})


async def event_generator(request_id: str):
    cursor = 0
    while True:
        with request_event_lock:
            events = request_events.get(request_id)
            if events is None:
                break
            base = request_event_base.get(request_id, 0)
            batch = events[max(0, cursor - base):]
            cursor = base + len(events)
        for data in batch:
            yield {"event": "message", "data": _serialize_progress_event(data)}
            if isinstance(data, dict) and "end_output" in data:
                return
        await asyncio.sleep(0.25)

def check_attachment_exists(email: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_documents WHERE email = %s", (email,))
        count = cursor.fetchone()[0]
        return count > 0
    finally:
        connection.close()

def get_user_documents(email: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT filename, content FROM user_documents WHERE email = %s", (email,))
        return {row[0]: row[1] for row in cursor.fetchall()}
    finally:
        connection.close()

def _run_research_with_key(user_query, request_id, email, conversation_id, temporary_history=None, temporary_attachment_context=None, paper_context=None, use_profile=True, answer_mode="light"):
    try:
        result = process_user_query(user_query, request_id, email, conversation_id, temporary_history, temporary_attachment_context, paper_context, use_profile, answer_mode)
        if conversation_id:
            logging.info("Conversation title job queued")
            scope_context = copy_context()
            threading.Thread(
                target=scope_context.run,
                args=(update_conversation_title, email, conversation_id),
                daemon=True,
            ).start()
        return result
    except Exception as exc:
        # Log only the exception class and numeric provider status. Exception
        # messages may echo request headers or other sensitive content.
        status = getattr(exc, "status_code", None)
        cause_types = []
        seen = set()
        cause = exc.__cause__
        while cause is not None and len(cause_types) < 4 and id(cause) not in seen:
            seen.add(id(cause))
            cause_types.append(type(cause).__name__)
            cause = cause.__cause__
        logging.error("Research request failed: %s (status=%s; causes=%s)",
                      type(exc).__name__, status if isinstance(status, int) else "n/a",
                      ">".join(cause_types) if cause_types else "none")
        loop.run_until_complete(send_update(request_id, {"end_output": "Research could not finish. Please try again.", "relevant_articles": [], "citations_obj": {}, "citations": []}))

def update_conversation_title(email: str, conversation_id: str):
    """Generate a short topic title from this owner's saved conversation turns."""
    try:
        logging.info("Conversation title job started")
        turns = get_session_memory(email, conversation_id)
        if not turns:
            logging.warning("Conversation title job skipped: no saved turns")
            return
        latest_turn = turns[-1].get("query_number")
        conversation_text = "\n".join(
            f"Q: {str(t.get('raw_question') or '')[:250]}\nA: {str(t.get('answer') or '')[:300]}"
            for t in turns[-4:]
        )[:2600]
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": (
                    "Give this research conversation a short, distinct title of 2 to 6 words. "
                    "Describe its actual topic, not the user's wording. Return only a title, no quotes. "
                    "Do not include health identifiers, email addresses or names."
                )},
                {"role": "user", "content": conversation_text},
            ],
            temperature=0.2,
        )
        title = (response.choices[0].message.content or '').strip().strip('"')[:80]
        if not title or '\n' in title or len(title.split()) > 8:
            logging.warning("Conversation title rejected: malformed model response")
            return
        connection = _get_db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT title FROM conversations WHERE email = %s AND conversation_id <> %s AND title = %s LIMIT 1",
                (email, conversation_id, title),
            )
            if cursor.fetchone():
                title = f"{title[:70]} {conversation_id[:4]}"
            cursor.execute(
                "UPDATE conversations SET title = %s WHERE email = %s AND conversation_id = %s AND next_query_number = %s AND title_locked = 0",
                (title, email, conversation_id, latest_turn + 1),
            )
            affected = cursor.rowcount
            connection.commit()
            if not affected:
                logging.warning("Conversation title skipped: no matching unchanged thread")
            else:
                logging.info("Conversation title saved")
        finally:
            connection.close()
    except Exception as exc:
        logging.warning("Conversation title update failed: %s", type(exc).__name__)


def _send_article_titles(request_id: str, articles: list, stage: str):
    """Display real retrieved titles, never synthetic or claimed citation support."""
    titles = []
    for article in articles:
        medline = article.get('MedlineCitation', {}).get('Article', {}) if isinstance(article, dict) else {}
        title = (article.get('title') or medline.get('ArticleTitle')) if isinstance(article, dict) else None
        if isinstance(title, str) and title.strip() and title.strip() not in titles:
            titles.append(title.strip()[:180])
        if len(titles) >= 5:
            break
    if titles:
        loop.run_until_complete(send_update(request_id, {
            'stage': stage, 'article_titles': titles, 'count_shown': len(titles),
            'note': 'Retrieved titles, not verified support for the answer.'
        }))


def process_user_query(user_query, request_id, email, conversation_id, temporary_history=None, temporary_attachment_context=None, paper_context=None, use_profile=True, answer_mode="light"):
    session_memory = get_session_memory(email, conversation_id) if conversation_id else (temporary_history or [])
    raw_question = user_query

    if session_memory:
        user_query = generate_standalone_question(user_query, session_memory)
        if conversation_id: logging.info("[SESSION MEMORY] Standalone question generated")

    paper_text = None
    if paper_context:
        paper_text = ("The user is asking about this specific paper. Ground the answer in it, and say plainly when the paper does not address part of the question.\n"
                      f"Paper: {paper_context['title']} (PMID {paper_context['pmid']}, {paper_context['url']})\nAbstract: {paper_context['abstract']}")
    user_attachment_context = temporary_attachment_context
    attachment_exist = bool(user_attachment_context)
    attachment_based_answer = False

    if conversation_id and not temporary_attachment_context and not (answer_mode == "heavy" and paper_context) and check_attachment_exists(email):
        attachment_exist = True
        documents = get_user_documents(email)
        if documents:
            user_attachment_context = "\n\n".join(
                f"Document: {name}\n{content}" for name, content in documents.items()
            )

    if paper_text:
        if answer_mode != "heavy":
            user_attachment_context = f"{user_attachment_context}\n\n{paper_text}" if user_attachment_context else paper_text
            attachment_exist = True
        # Heavy mode retrieves the selected PMID as a full article below.

    # Temporary requests have no saved conversation, and must never read account profile.
    profile_prompt = get_diet_profile_prompt(email) if conversation_id and use_profile else ""
    if conversation_id and use_profile:
        profile_documents = get_profile_documents(email)
        if profile_documents:
            profile_files = "\n\n".join(
                f"Profile file: {name}\n{text[:12000]}" for name, text in profile_documents[:5]
            )
            profile_prompt = (profile_prompt + "\n\n" + profile_files).strip()
    # Keep self-reported profile and its files separate from research evidence.
    # Neither is a retrieved paper or permitted to drive public research queries.

    attachment_partial_answer = None
    partial_question = None
    if not (answer_mode == "heavy" and temporary_attachment_context and temporary_attachment_context.startswith("Selected paper PDF: ")) and attachment_exist and user_attachment_context:
        can_answer, attachment_answer, question_not_answered = try_answer_from_attachment(user_query, user_attachment_context)
        if can_answer and attachment_answer:
            attachment_based_answer = True
            logging.info("[ATTACHMENT] Fully answered from attachment — skipping PubMed pipeline")
            return_obj = {
                "end_output": attachment_answer,
                "relevant_articles": [],
                "citations_obj": [],
                "citations": [],
                "session_memory_entry": {
                    "request_id": request_id,
                    "raw_question": raw_question,
                    "standalone_question": user_query,
                    "answer": attachment_answer
                }
            }
            if conversation_id:
                append_session_memory(email, conversation_id, return_obj["session_memory_entry"])
            if conversation_id:
                conversation_summary = update_conversation_summary(
                    get_conversation_summary(email, conversation_id), user_query, attachment_answer
                )
                set_conversation_summary(email, conversation_id, conversation_summary)
            loop.run_until_complete(send_update(request_id, return_obj))
            return return_obj
        else:
            logging.info("[ATTACHMENT] Attachment insufficient — falling through to PubMed pipeline")
            if attachment_answer:
                attachment_partial_answer = attachment_answer
            if question_not_answered:
                partial_question = question_not_answered
                logging.info("[ATTACHMENT] Sending unanswered portion to PubMed")

    pipeline_query = partial_question if attachment_partial_answer and partial_question else user_query
    # Query Generation
    start_poc = time.time()
    general_query, query_contention, query_list = query_generation(pipeline_query)
    end_poc = time.time()

    print("Generated PubMed queries")
    if conversation_id:
        print(query_list)
    loop.run_until_complete(send_update(request_id, "Generated PubMed queries..."))
    # Article Retrieval
    start_api = time.time()
    deduplicated_articles_collected = collect_articles(query_list)
    end_api = time.time()

    print("Retrieved Articles")
    loop.run_until_complete(send_update(request_id, f"Retrieved {len(deduplicated_articles_collected)} Articles..."))
    _send_article_titles(request_id, deduplicated_articles_collected, "retrieved")
    # Relevance Classifier
    start_relevant = time.time()
    relevant_articles, irrelevant_articles = concurrent_relevance_classification(deduplicated_articles_collected, pipeline_query)
    # DietNerdV2's detailed combined-source route: a selected PMID bypasses
    # relevance filtering. If PubMed already returned it, keep the one copy.
    if answer_mode == "heavy" and paper_context:
        selected = fetch_selected_pmid_articles(paper_context["pmid"])
        selected_ids = {str(a["MedlineCitation"]["PMID"]) for a in selected}
        relevant_articles = [a for a in relevant_articles if str(a["MedlineCitation"]["PMID"]) not in selected_ids]
        relevant_articles.extend(selected)
        loop.run_until_complete(send_update(request_id, "Heavy mode: combined PubMed search with the selected PMID..."))
    end_relevant = time.time()

    print("relevant articles")
    loop.run_until_complete(send_update(request_id, f"Classified {len(relevant_articles)} Relevant Articles..."))
    _send_article_titles(request_id, relevant_articles, "relevant")

    # Article Match
    start_processing = time.time()
    reliability_analysis_df = connect_to_reliability_analysis_db()
    reliability_analysis_df = reliability_analysis_df.where(pd.notnull(reliability_analysis_df), None)
    for col in reliability_analysis_df.select_dtypes(include=np.number).columns:
        reliability_analysis_df[col] = reliability_analysis_df[col].astype(object).where(reliability_analysis_df[col].notnull(), None)
    matched_articles, articles_to_process = article_matching(relevant_articles, reliability_analysis_df)

    print("matched articles")
    # Article Processing
    relevant_article_summaries = concurrent_article_processing(articles_to_process)

    # Write Processed Articles to DB
    if conversation_id:
        write_articles_to_db(relevant_article_summaries, env)

    all_relevant_articles = list(itertools.chain(relevant_article_summaries, matched_articles))
    # V2's selected-PDF lane contributes a separately labeled, unverified
    # source; unlike public papers it is never written to article_analysis.
    if answer_mode == "heavy" and temporary_attachment_context and temporary_attachment_context.startswith("Selected paper PDF: "):
        first_line, _, pdf_text = temporary_attachment_context.partition("\n")
        filename = first_line.removeprefix("Selected paper PDF: ").strip()
        pdf_source = summarize_selected_pdf(pdf_text, filename, client)
        all_relevant_articles.append(pdf_source)
        user_attachment_context = None  # Avoid duplicating full PDF text in synthesis.
        loop.run_until_complete(send_update(request_id, "Heavy mode: included the selected PDF as an unverified source..."))
    end_processing = time.time()

    print(f"Processed {len(all_relevant_articles)} Articles...")
    loop.run_until_complete(send_update(request_id, f"Processed {len(all_relevant_articles)} Articles..."))

    # Final Output
    start_output = time.time()
    if answer_mode == "heavy":
        loop.run_until_complete(send_update(request_id, "Heavy mode: synthesizing the combined sources..."))
    final_output = generate_final_response(all_relevant_articles, pipeline_query, user_attachment_context, original_articles=relevant_articles, recent_history=session_memory[-8:], profile_context=profile_prompt or None, answer_mode=answer_mode)
    # The synthesis model may ignore a supplied weight even when the question
    # explicitly asks for a per-kg calculation. Retry synthesis once, never
    # retrieval: private measurements stay out of PubMed queries.
    weight_match = re.search(r"\b(?:body )?weight\s*(?:is|:|=)?\s*(\d{2,3}(?:\.\d+)?)\s*kg\b", profile_prompt, re.I) if profile_prompt else None
    if weight_match and re.search(r"\bprotein\b", pipeline_query, re.I) and re.search(r"(?:calculat|range|body weight|my weight|daily)", pipeline_query, re.I):
        weight = weight_match.group(1)
        if not re.search(rf"\b{re.escape(weight)}\s*(?:kg|kilograms?)\b", final_output, re.I):
            logging.warning("Personalized answer omitted the supplied weight; retrying synthesis once")
            final_output = generate_final_response(
                all_relevant_articles,
                pipeline_query + f"\nFor this question, the self-reported body weight is {weight} kg. If the supplied human research supports a per-kg range, calculate the corresponding gram range, show multiplication and name study limits. If it does not, say no personal range is established; do not invent one.",
                user_attachment_context, original_articles=relevant_articles,
                recent_history=session_memory[-8:], profile_context=profile_prompt or None,
                answer_mode=answer_mode)
    if attachment_partial_answer:
        final_output = attachment_partial_answer + "\n\n" + final_output
    end_output = time.time()

    poc_duration = end_poc - start_poc
    api_duration = end_api - start_api
    relevance_classifier_duration = end_relevant - start_relevant
    article_processing_duration = end_processing - start_processing
    final_output_duration = end_output - start_output
    total_runtime = poc_duration + api_duration + article_processing_duration + final_output_duration

    if conversation_id:
        write_output_to_db(user_query, final_output, all_relevant_articles, total_runtime, env)
    end_output = time.time()

    print('-'*200)
    if conversation_id:
        print(final_output)
        print('-'*20)
        print('User Question: ', user_query)
        print('-'*20)
        print('General Query: ', general_query)
        print('-'*20)
        print('Points of Contention: ', query_contention)
    print('-'*20)

    print('# Matched: ', len(matched_articles))
    print('# Processed: ', len(articles_to_process))
    print('# Relevant: ', len(all_relevant_articles))
    print('# Irrelevant: ', len(irrelevant_articles))
    if conversation_id:
        print('Relevant Articles: ', all_relevant_articles)
    print('-'*20)
    print('Total Runtime: ', total_runtime)
    print(' -- ')
    print('[Section 1] Points of Contention: ', poc_duration)
    print('[Section 2] PubMed API Call: ', api_duration)
    print('[Section 3] Relevance Classification: ', relevance_classifier_duration)
    print('[Section 4] Reliability Analysis: ', article_processing_duration)
    print('[Section 5] Final Synthesis: ', final_output_duration)


    from evidence_ledger import build_claim_evidence_ledger
    return_obj = {
       "end_output": final_output,
       "relevant_articles": all_relevant_articles,
       "evidence_ledger": build_claim_evidence_ledger(final_output, [a for a in all_relevant_articles if not str(a.get('publication_type', '')).startswith('User-supplied PDF')])
    }

    main_output, citations = split_end_output(return_obj["end_output"])
    relevant_articles = return_obj.get("relevant_articles", [])
    # User PDF summaries are not verified external articles and have no trusted
    # source URL; never upgrade their citation into an Article Analysis link.
    citation_articles = [a for a in all_relevant_articles if not str(a.get('publication_type', '')).startswith('User-supplied PDF')]
    updated_citations = match_citations_with_articles(citations, citation_articles)
    return_obj["end_output"] = final_output
    return_obj["citations_obj"] = updated_citations
    return_obj["citations"] = citations
    
    from answer_sources import extract_answer_sources
    session_memory_entry = {
        "request_id": request_id,
        "raw_question": raw_question,
        "standalone_question": user_query,
        "answer": final_output,
        "sources": extract_answer_sources(final_output, updated_citations, return_obj["evidence_ledger"]),
        "evidence_ledger": return_obj["evidence_ledger"]
    }
    if conversation_id:
        append_session_memory(email, conversation_id, session_memory_entry)
    return_obj["session_memory_entry"] = session_memory_entry
    if conversation_id:
        logging.info("[SESSION MEMORY] Entry created | request_id=%s", request_id)

    if conversation_id:
        conversation_summary = update_conversation_summary(
            get_conversation_summary(email, conversation_id), user_query, final_output
        )
        set_conversation_summary(email, conversation_id, conversation_summary)

    loop.run_until_complete(send_update(request_id, return_obj))

    return return_obj

async def send_update(request_id, data):
    with request_event_lock:
        if request_id not in request_events:
            return
        events = request_events[request_id]
        events.append(data)
        if len(events) > MAX_PROGRESS_EVENTS + 1:
            trimmed = len(events) - MAX_PROGRESS_EVENTS - 1
            del events[:trimmed]
            request_event_base[request_id] = request_event_base.get(request_id, 0) + trimmed
        request_updated_at[request_id] = time.monotonic()

async def query_db_final(query: str):
   mydb = _get_db_connection()
   try:
      mycursor = mydb.cursor()
      sql = "SELECT * FROM question_answer WHERE question = %s"
      mycursor.execute(sql, (query,))
      return mycursor.fetchall()
   finally:
      mydb.close()


async def sim_score(question: str):
   mydb = mysql.connector.connect(
    host=os.getenv("host"),
    port=os.getenv("port"),
    user=os.getenv("user"),
    password=os.getenv("password"),
    database=os.getenv("database")
  )
   mycursor = mydb.cursor()
   sql = f"SELECT question FROM question_answer;"
   mycursor.execute(sql)
   myresult = mycursor.fetchall()
   resultdict = []

   for x in myresult:
      resultdict.append(x[0])

   if not resultdict:
      return []

   scores_dict = calculate_similarity(resultdict, question)
   print(scores_dict)

   min_heap = []

   for item in scores_dict:
      score = item[0]
      sentence = item[1]
      if (score > 0.23):
         heapq.heappush(min_heap, (score, sentence))
      if (len(min_heap) > 3):
         heapq.heappop(min_heap)
   top_k_sentences = [(score, sentence) for score, sentence in sorted(min_heap, reverse=True)]
   print(top_k_sentences)
   return top_k_sentences

def calculate_similarity(sentences, source_sentence):
    # Combine source sentence with the list of sentences
    all_sentences = sentences + [source_sentence]
    
    # Create the TF-IDF vectorizer and transform the sentences
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(all_sentences)
    
    # Calculate the cosine similarity between the source sentence and all other sentences
    cosine_similarities = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1]).flatten()
    
    # Combine the similarity scores with the sentences
    similarity_scores = [(score, sentence) for score, sentence in zip(cosine_similarities, sentences)]
    
    return similarity_scores


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)