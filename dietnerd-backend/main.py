from helper_functions import *
from conversation_store import append_turn
import auth

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, UploadFile, File, Form, Depends, Request, Response
from fastapi.responses import StreamingResponse
from starlette.responses import JSONResponse

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
import os
import mysql.connector

import logging

#Sim search
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from collections import defaultdict

logging.basicConfig(level=logging.INFO)

update_queues = defaultdict(asyncio.Queue)

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
    allow_methods=["GET", "POST", "DELETE"],
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
            "SELECT email FROM user_sessions WHERE token_hash = %s AND expires_at > UTC_TIMESTAMP()",
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
    problem = auth.validate_email(email) or auth.validate_password(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists. Try signing in or resetting your password.")
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, auth.hash_password(password)))
        connection.commit()
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
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    ok, needs_upgrade = auth.verify_password(password, row[0])
    if not ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
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
async def me(email: str = Depends(current_user)):
    return {"email": email}

@app.post("/forgot_password")
async def forgot_password(body: ForgotPasswordModel, request: Request):
    email = auth.normalize_email(body.email)
    generic = {"message": "If an account exists for that email, we've sent a link to reset the password."}
    if not reset_limiter.allow(f"{_client_key(request)}|{email}"):
        raise HTTPException(status_code=429, detail="Too many reset requests. Please wait a few minutes and try again.")
    if auth.validate_email(email):
        return generic
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        exists = cursor.fetchone() is not None
        if not exists:
            return generic
        token = auth.new_token()
        # One live reset link per account.
        cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))
        cursor.execute(
            "INSERT INTO password_resets (token_hash, email, expires_at) "
            "VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND))",
            (auth.token_digest(token), email, auth.RESET_TTL_SECONDS),
        )
        connection.commit()
    finally:
        connection.close()
    base = os.getenv("PUBLIC_SITE_URL", "").rstrip("/") or (request.headers.get("origin") or "").rstrip("/")
    reset_url = f"{base}/login.html#reset_token={token}"
    auth.send_reset_email(email, reset_url)
    return generic

@app.post("/reset_password")
async def reset_password(body: ResetPasswordModel):
    problem = auth.validate_password(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    digest = auth.token_digest(body.token or "")
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        connection.start_transaction()
        cursor.execute(
            "SELECT email FROM password_resets WHERE token_hash = %s AND used_at IS NULL "
            "AND expires_at > UTC_TIMESTAMP() FOR UPDATE",
            (digest,),
        )
        row = cursor.fetchone()
        if not row:
            connection.rollback()
            raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")
        email = row[0]
        cursor.execute("UPDATE password_resets SET used_at = UTC_TIMESTAMP() WHERE token_hash = %s", (digest,))
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (auth.hash_password(body.password), email))
        cursor.execute("DELETE FROM user_sessions WHERE email = %s", (email,))
        connection.commit()
    finally:
        connection.close()
    logging.info("[AUTH] Password reset completed")
    return {"message": "Your password has been reset. Please sign in with the new password."}

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
    _revoke_sessions(email, keep_token=_session_token(request))
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
    if conversation_id and not conversation_belongs_to(query.email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Cache lookup uses the literal question. Context rewriting belongs only to
    # the generation path, so a cache miss cannot invoke the rewrite model twice.
    standalone_question = query.user_query
    result = await query_db_final(standalone_question)
    if not result:
        raise HTTPException(status_code=404, detail="Cached answer not found.")

    if not conversation_id:
        conversation_id = create_conversation(query.email, query.user_query[:120])
    request_id = str(uuid.uuid4())
    cached_payload = result[0][1]
    try:
        cached_answer_text = json.loads(cached_payload)["end_output"]
    except (TypeError, ValueError, KeyError, IndexError):
        raise HTTPException(status_code=500, detail="Cached answer has an invalid format.")
    append_session_memory(query.email, conversation_id, {
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
    return {
        "cached_payload": cached_payload,
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

def create_conversation(email: str, title: Optional[str] = None) -> str:
    conversation_id = str(uuid.uuid4())
    connection = _get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO conversations (conversation_id, email, title) VALUES (%s, %s, %s)",
            (conversation_id, email, title),
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

def get_session_memory(email: str, conversation_id: str):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT query_number, request_id, raw_question, standalone_question, answer "
            "FROM user_session_memory WHERE email = %s AND conversation_id = %s ORDER BY query_number",
            (email, conversation_id),
        )
        return cursor.fetchall()
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

@app.post("/conversations")
async def new_conversation(email: str = Depends(current_user)):
    return {"conversation_id": create_conversation(email)}

@app.get("/conversations")
async def list_conversations(email: str = Depends(current_user)):
    connection = _get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT conversation_id, title, created_at, updated_at FROM conversations WHERE email = %s ORDER BY updated_at DESC", (email,))
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

@app.post("/process_query")
async def process_query(background_tasks: BackgroundTasks, query: QueryModel, email: str = Depends(current_user)):
    query.email = email
    request_id = str(uuid.uuid4())
    conversation_id = query.conversation_id
    if conversation_id and not conversation_belongs_to(query.email, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if not conversation_id:
        conversation_id = create_conversation(query.email, query.user_query[:120])
    update_queues[request_id]
    request_owners[request_id] = email
    background_tasks.add_task(process_user_query, query.user_query, request_id, query.email, conversation_id)
    return JSONResponse({"request_id": request_id, "conversation_id": conversation_id})

@app.get("/sse")
async def sse(request_id: str = Query(default=None), email: str = Depends(current_user)):
    if not request_id:
        raise HTTPException(status_code=400, detail="request_id is required")
    if request_owners.get(request_id) != email:
        raise HTTPException(status_code=404, detail="Request not found.")
    return EventSourceResponse(event_generator(request_id))

async def event_generator(request_id: str):
    queue = update_queues[request_id]
    try:
        while True:
            data = await queue.get()
            if isinstance(data, dict) and "end_output" in data:
                yield {"event": "message", "data": json.dumps({"update": data})}
                break
            yield {"event": "message", "data": json.dumps({"update": data})}
    finally:
        update_queues.pop(request_id, None)
        request_owners.pop(request_id, None)

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

def process_user_query(user_query, request_id, email, conversation_id):
    session_memory = get_session_memory(email, conversation_id)
    raw_question = user_query

    if session_memory:
        user_query = generate_standalone_question(user_query, session_memory)
        logging.info(f"[SESSION MEMORY] Standalone question generated: '{user_query}'")

    user_attachment_context = None
    attachment_exist = False
    attachment_based_answer = False

    if check_attachment_exists(email):
        attachment_exist = True
        documents = get_user_documents(email)
        if documents:
            user_attachment_context = "\n\n".join(
                f"Document: {name}\n{content}" for name, content in documents.items()
            )

    attachment_partial_answer = None
    partial_question = None
    if attachment_exist and user_attachment_context:
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
            append_session_memory(email, conversation_id, return_obj["session_memory_entry"])
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
                logging.info(f"[ATTACHMENT] Sending unanswered portion to PubMed: '{partial_question}'")

    pipeline_query = partial_question if attachment_partial_answer and partial_question else user_query

    # Query Generation
    start_poc = time.time()
    general_query, query_contention, query_list = query_generation(pipeline_query)
    end_poc = time.time()

    print("Generated PubMed queries")
    print(query_list)
    loop.run_until_complete(send_update(request_id, "Generated PubMed queries..."))
    # Article Retrieval
    start_api = time.time()
    deduplicated_articles_collected = collect_articles(query_list)
    end_api = time.time()

    print("Retrieved Articles")
    loop.run_until_complete(send_update(request_id, f"Retrieved {len(deduplicated_articles_collected)} Articles..."))
    # Relevance Classifier
    start_relevant = time.time()
    relevant_articles, irrelevant_articles = concurrent_relevance_classification(deduplicated_articles_collected, pipeline_query)
    end_relevant = time.time()

    print("relevant articles")
    loop.run_until_complete(send_update(request_id, f"Classified {len(relevant_articles)} Relevant Articles..."))

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
    write_articles_to_db(relevant_article_summaries, env)

    all_relevant_articles = list(itertools.chain(relevant_article_summaries, matched_articles))
    end_processing = time.time()

    print(f"Processed {len(all_relevant_articles)} Articles...")
    loop.run_until_complete(send_update(request_id, f"Processed {len(all_relevant_articles)} Articles..."))

    # Final Output
    start_output = time.time()
    final_output = generate_final_response(all_relevant_articles, pipeline_query, None, original_articles=relevant_articles)
    if attachment_partial_answer:
        final_output = attachment_partial_answer + "\n\n" + final_output
    end_output = time.time()

    poc_duration = end_poc - start_poc
    api_duration = end_api - start_api
    relevance_classifier_duration = end_relevant - start_relevant
    article_processing_duration = end_processing - start_processing
    final_output_duration = end_output - start_output
    total_runtime = poc_duration + api_duration + article_processing_duration + final_output_duration

    write_output_to_db(user_query, final_output, all_relevant_articles, total_runtime, env)
    end_output = time.time()

    print('-'*200)
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
       "evidence_ledger": build_claim_evidence_ledger(final_output, all_relevant_articles)
    }

    main_output, citations = split_end_output(return_obj["end_output"])
    relevant_articles = return_obj.get("relevant_articles", [])
    updated_citations = match_citations_with_articles(citations, all_relevant_articles)
    return_obj["end_output"] = final_output
    return_obj["citations_obj"] = updated_citations
    return_obj["citations"] = citations
    
    session_memory_entry = {
        "request_id": request_id,
        "raw_question": raw_question,
        "standalone_question": user_query,
        "answer": final_output,
        "evidence_ledger": return_obj["evidence_ledger"]
    }
    append_session_memory(email, conversation_id, session_memory_entry)
    return_obj["session_memory_entry"] = session_memory_entry
    logging.info(f"[SESSION MEMORY] Entry created | request_id={request_id} | email={email}")

    conversation_summary = update_conversation_summary(
        get_conversation_summary(email, conversation_id), user_query, final_output
    )
    set_conversation_summary(email, conversation_id, conversation_summary)

    loop.run_until_complete(send_update(request_id, return_obj))

    return return_obj

async def send_update(request_id, data):
    if request_id in update_queues:
        await update_queues[request_id].put(data)

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