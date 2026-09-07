import os
import re
import time
import asyncio
import hashlib
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import bcrypt

from config import settings
from database import get_db, SyncSessionLocal
from legal_api.models import User, KnownDevice
from legal_api.schemas import RegisterRequest, LoginRequest, SearchRequest, ChatRequest
from legal_api.auth import get_current_user, create_access_token
from ocr import extract_document_pages

logger = logging.getLogger("main_server")

# Lazy-initialize vector store (defers genai import until first use)
_db_store = None
_store_lock = threading.Lock()


def _get_store():
    global _db_store
    if _db_store is None:
        with _store_lock:
            if _db_store is None:  # Double-check after acquiring lock
                from vector_store import LegalVectorStore
                _db_store = LegalVectorStore()
    return _db_store

router = APIRouter()


@router.get("/")
def read_root():
    return {
        "status": "online",
        "message": "CaseLens backend API is running.",
        "frontend_url": "http://localhost:3000",
        "docs_url": "/docs"
    }


_RATE_SQL = text("""
INSERT INTO rate_limits (key, window_start, count)
VALUES (:key, now(), 1)
ON CONFLICT (key) DO UPDATE SET
    count = CASE
        WHEN rate_limits.window_start < now() - make_interval(secs => :window)
        THEN 1 ELSE rate_limits.count + 1 END,
    window_start = CASE
        WHEN rate_limits.window_start < now() - make_interval(secs => :window)
        THEN now() ELSE rate_limits.window_start END
RETURNING count
""")


class RateLimiter:
    def __init__(self, max_req: int = 10, window: int = 60):
        self.max_req, self.window = max_req, window

    def check(self, key: str):

        session = SyncSessionLocal()
        try:
            count = session.execute(
                _RATE_SQL, {"key": f"{self.max_req}:{self.window}:{key}", "window": self.window}
            ).scalar_one()
            session.commit()
        finally:
            session.close()
        if count > self.max_req:
            raise RateLimitExceeded()


class RateLimitExceeded(Exception):
    pass


auth_limiter = RateLimiter(10, 60)
query_limiter = RateLimiter(30, 60)


def _client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


_STATUS_TTL = 3600

_STATUS_SET_SQL = text("""
INSERT INTO upload_status (user_id, filename, status, updated_at)
VALUES (:uid, :fn, :st, now())
ON CONFLICT (user_id, filename) DO UPDATE SET status = :st, updated_at = now()
""")

_STATUS_GET_SQL = text("""
SELECT status FROM upload_status
WHERE user_id = :uid AND filename = :fn
  AND updated_at > now() - make_interval(secs => :ttl)
""")


def _set_status(user_id: int, filename: str, status: str, session=None):
    """Record indexing progress. Pass `session` from the background thread,
    which already holds one; otherwise a short-lived session is used."""
    own = session is None
    session = session or SyncSessionLocal()
    try:
        session.execute(_STATUS_SET_SQL, {"uid": user_id, "fn": filename, "st": status[:255]})
        session.commit()
    finally:
        if own:
            session.close()


def _get_status(user_id: int, filename: str) -> str:
    session = SyncSessionLocal()
    try:
        row = session.execute(
            _STATUS_GET_SQL, {"uid": user_id, "fn": filename, "ttl": _STATUS_TTL}
        ).scalar_one_or_none()
        return row or "unknown"
    finally:
        session.close()


def process_document_task(file_path: str, filename: str, user_email: str, user_id: int):
    session = SyncSessionLocal()
    try:
        _set_status(user_id, filename, "extracting_text", session)
        logger.info(f"Processing started: {filename} (owner: {user_email})")
        pages = extract_document_pages(file_path)
        if not any(p["text"].strip() for p in pages):
            raise ValueError("No text could be extracted from the document.")
        _set_status(user_id, filename, "indexing", session)

        user = session.execute(select(User).where(User.id == user_id))
        user = user.scalar_one_or_none()
        if user:
            _get_store().add_document_pages(filename, pages, user, session)
        else:
            logger.error("User not found in background task.")

        _set_status(user_id, filename, "completed", session)
        logger.info(f"Processing completed: {filename} (owner: {user_email})")
    except ValueError as e:
        _set_status(user_id, filename, f"error: {e}", session)
        logger.warning(f"Could not process {filename} for {user_email}: {e}")
    except Exception:
        _set_status(user_id, filename, "error: processing failed", session)
        logger.exception(f"Error processing {filename} for {user_email}")
    finally:
        session.close()


_SAFE_FILENAME_RE = re.compile(r'^[\w\-. ]+$')

@router.post("/api/register")
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    auth_limiter.check(_client_ip(request))

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    email = payload.email.strip().lower()

    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Registration could not be completed. Email may already exist.",
        )

    pw_hash = await asyncio.to_thread(
        lambda: bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    )
    new_user = User(
        email=email,
        password_hash=pw_hash,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        company=payload.company.strip(),
        phone_number=payload.phone_number.strip(),
    )
    db.add(new_user)
    await db.commit()

    # Send welcome email in background
    from email_service import send_registration_email
    threading.Thread(target=send_registration_email, args=(email,), daemon=True).start()

    return {"message": "User registered successfully"}


@router.post("/api/login")
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    auth_limiter.check(_client_ip(request))

    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    password_valid = await asyncio.to_thread(
        bcrypt.checkpw, payload.password.encode(), user.password_hash.encode()
    )
    if not password_valid:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # Device fingerprinting
    client_ip = _client_ip(request)
    ua = request.headers.get("user-agent", "Unknown Device")
    dev_hash = hashlib.sha256(f"{client_ip}:{ua}".encode()).hexdigest()

    result = await db.execute(
        select(KnownDevice).where(KnownDevice.user_id == user.id, KnownDevice.device_hash == dev_hash)
    )
    device = result.scalar_one_or_none()

    if not device:
        logger.warning(f"New device login for user ID {user.id}")
        from email_service import send_unknown_device_login_email
        threading.Thread(
            target=send_unknown_device_login_email,
            args=(user.email, client_ip, ua),
            daemon=True,
        ).start()

    # Register or update device
    if not device:
        new_device = KnownDevice(user_id=user.id, device_hash=dev_hash)
        db.add(new_device)
    else:
        from datetime import datetime, timezone
        device.last_login = datetime.now(timezone.utc)

    await db.commit()

    token = create_access_token({"sub": user.email})

    return JSONResponse(
        content={"access_token": token, "token_type": "bearer", "email": user.email}
    )


@router.post("/api/logout")
async def logout():
    # Stateless JWT: the client drops the token. Nothing server-side to clear.
    return JSONResponse(content={"message": "Logged out successfully"})


@router.get("/api/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email}


@router.post("/api/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    filename = os.path.basename(file.filename or "")
    if not filename or not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename. Use only letters, numbers, hyphens, underscores, spaces, and dots.",
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(settings.ALLOWED_FILE_EXTENSIONS))}",
        )

    contents = await file.read()
    if len(contents) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum: {settings.MAX_FILE_SIZE_BYTES // (1024*1024)}MB",
        )

    safe_email = re.sub(r'[^a-zA-Z0-9_.-]', '_', current_user.email)
    user_dir = os.path.join(settings.UPLOAD_DIR, safe_email)
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, filename)

    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")

    # Delete existing chunks if re-uploading (sync session for vector store)
    sync_session = SyncSessionLocal()
    try:
        existing = _get_store().delete_document(filename, current_user, sync_session)
        if existing > 0:
            logger.info(f"Removed {existing} old chunks for '{filename}' before re-indexing.")
    finally:
        sync_session.close()

    _set_status(current_user.id, filename, "queued")

    # Process in background thread
    threading.Thread(
        target=process_document_task,
        args=(file_path, filename, current_user.email, current_user.id),
        daemon=True,
    ).start()

    return {"filename": filename, "status": "queued"}


@router.get("/api/status/{filename}")
async def get_processing_status(filename: str, current_user: User = Depends(get_current_user)):
    status = _get_status(current_user.id, filename)
    return {"filename": filename, "status": status}


@router.get("/api/documents")
async def list_documents(current_user: User = Depends(get_current_user)):
    sync_session = SyncSessionLocal()
    try:
        docs = _get_store().list_documents(current_user, sync_session)
        return {"documents": docs}
    finally:
        sync_session.close()


@router.delete("/api/documents/{filename}")
async def delete_document(filename: str, current_user: User = Depends(get_current_user)):
    filename = os.path.basename(filename)
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    sync_session = SyncSessionLocal()
    try:
        deleted = _get_store().delete_document(filename, current_user, sync_session)
    finally:
        sync_session.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    path = os.path.join(
        settings.UPLOAD_DIR,
        re.sub(r'[^a-zA-Z0-9_.-]', '_', current_user.email),
        filename,
    )
    if os.path.exists(path):
        os.remove(path)

    sync_session = SyncSessionLocal()
    try:
        sync_session.execute(
            text("DELETE FROM upload_status WHERE user_id = :uid AND filename = :fn"),
            {"uid": current_user.id, "fn": filename},
        )
        sync_session.commit()
    finally:
        sync_session.close()

    return {"message": f"Document '{filename}' deleted", "deleted_chunks": deleted}



@router.post("/api/search")
async def search_documents(
    request: Request,
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    query_limiter.check(_client_ip(request))
    sync_session = SyncSessionLocal()
    try:
        contexts = _get_store().query_similar_context(payload.query, current_user, sync_session, top_k=5)
        return {"contexts": contexts}
    finally:
        sync_session.close()



@router.post("/api/chat")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    query_limiter.check(_client_ip(request))
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    latest_msg = payload.messages[-1].content.strip()
    if not latest_msg:
        raise HTTPException(status_code=400, detail="Empty query message")

    sync_session = SyncSessionLocal()
    try:
        contexts = _get_store().query_similar_context(latest_msg, current_user, sync_session, top_k=5)
    finally:
        sync_session.close()

    context_text = "\n\n".join([
        f"--- Chunk {i + 1} (Source: {c['metadata'].get('filename', '?')}, Page: {c['metadata'].get('page', 1)}) ---\n{c['text']}"
        for i, c in enumerate(contexts)
    ])

    system_prompt = (
        "You are a helpful and professional Legal Assistant. Answer based strictly on the provided document contexts.\n"
        "If the answer cannot be found in the context, state so. Always reference sources (filenames and page numbers).\n\n"
        f"CONTEXT:\n{context_text}"
    )

    provider = settings.LLM_PROVIDER.lower()
    model_name = settings.llm_model_name

    if provider == "ollama":
        import ollama

        def generate():
            messages = [{"role": "system", "content": system_prompt}]
            for msg in payload.messages[:-1]:
                messages.append({
                    "role": "user" if msg.role == "user" else "assistant",
                    "content": msg.content,
                })
            messages.append({"role": "user", "content": latest_msg})

            try:
                for chunk in ollama.chat(model=model_name, messages=messages, stream=True):
                    text = chunk["message"]["content"]
                    if text:
                        yield text
            except Exception as e:
                logger.error(f"Error during Ollama generation with '{model_name}': {e}")
                yield f"\n[Error generating response: {e}]"

        return StreamingResponse(generate(), media_type="text/plain")

    if provider != "gemini":
        raise HTTPException(
            status_code=500,
            detail=f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Expected 'ollama' or 'gemini'.",
        )

    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")

    genai.configure(api_key=api_key)

    def generate():
        try:
            model = genai.GenerativeModel(model_name=model_name, system_instruction=system_prompt)
            history = []
            for msg in payload.messages[:-1]:
                role = "user" if msg.role == "user" else "model"
                history.append({"role": role, "parts": [msg.content]})

            chat = model.start_chat(history=history)
            response = chat.send_message(latest_msg, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Error during Gemini response generation: {e}")
            yield f"\n[Error generating response: {e}]"

    return StreamingResponse(generate(), media_type="text/plain")

