import os
from dotenv import load_dotenv
load_dotenv()
import logging, hashlib, re, time, secrets, threading, asyncio
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main_server")

from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import google.generativeai as genai
import jwt

from ocr import extract_document_pages
from vector_store import LegalVectorStore
from db_manager import register_user, authenticate_user, is_device_known, register_device, validate_email, MAX_PASSWORD_LENGTH
from email_service import send_registration_email, send_unknown_device_login_email

app = FastAPI(title="Legal Assistant RAG Application")
templates = Jinja2Templates(directory="templates")

# --- Configuration ---
IS_PRODUCTION = os.environ.get("ENVIRONMENT", "development") == "production"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
if not os.environ.get("JWT_SECRET"):
    logger.warning("JWT_SECRET not set. Generated a random secret for this session. Tokens will not persist across restarts.")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
CSRF_COOKIE = "csrf_token"
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
db = LegalVectorStore()


# --- CSRF Middleware (validate only — home_page issues tokens) ---
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not request.headers.get("authorization", "").startswith("Bearer "):
            cookie_tok = request.cookies.get(CSRF_COOKIE)
            header_tok = request.headers.get("x-csrf-token")
            if cookie_tok is not None and (not header_tok or cookie_tok != header_tok):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
    return await call_next(request)


# --- Rate Limiter ---
class RateLimiter:
    def __init__(self, max_req: int = 10, window: int = 60):
        self.max_req, self.window = max_req, window
        self._reqs: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str):
        now = time.time()
        with self._lock:
            ts = [t for t in self._reqs.get(key, []) if now - t < self.window]
            if len(ts) >= self.max_req:
                raise HTTPException(429, "Too many requests. Please try again later.")
            ts.append(now)
            self._reqs[key] = ts if ts else self._reqs.pop(key, None) or []

auth_limiter = RateLimiter(10, 60)
query_limiter = RateLimiter(30, 60)


# --- Auth helpers ---
def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "127.0.0.1"

def create_access_token(data: dict) -> str:
    to_encode = {**data, "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))) -> str:
    token = creds.credentials if creds else request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Session expired. Please log in again.")
    try:
        email = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]).get("sub")
        if not email:
            raise HTTPException(401, "Invalid token")
        return email
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired authentication token")


# --- Request parsing + error helpers ---
async def _parse_payload(request: Request, *fields: str) -> tuple[dict, bool]:
    """Parses form or JSON body and returns (dict-of-values, is_html_request)."""
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        data = await request.json()
        return {f: data.get(f) for f in fields}, False
    form = await request.form()
    return {f: form.get(f) for f in fields}, True

class _AuthError(Exception):
    """Raised by validation helpers; caught by register/login to return the right format."""
    def __init__(self, msg: str, status: int = 400):
        self.msg, self.status = msg, status

def _auth_response(err: _AuthError, is_html: bool):
    if is_html:
        return HTMLResponse(
            f'<div id="auth-error-container" hx-swap-oob="true" class="error-msg">{err.msg}</div>',
            status_code=err.status
        )
    raise HTTPException(err.status, err.msg)

def _require(condition: bool, msg: str, status: int = 400):
    if not condition:
        raise _AuthError(msg, status)

_PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


# --- Processing Status (thread-safe with TTL) ---
_status_store: dict[str, dict] = {}
_status_lock = threading.Lock()
_STATUS_TTL = 3600

def _set_status(key: str, status: str):
    now = time.time()
    with _status_lock:
        for k in [k for k, v in _status_store.items() if now - v["t"] > _STATUS_TTL]:
            del _status_store[k]
        _status_store[key] = {"s": status, "t": now}

def _get_status(key: str) -> str:
    with _status_lock:
        e = _status_store.get(key)
        if not e:
            return "unknown"
        if time.time() - e["t"] > _STATUS_TTL:
            del _status_store[key]
            return "unknown"
        return e["s"]

def _remove_status(key: str):
    with _status_lock:
        _status_store.pop(key, None)


def process_document_task(file_path: str, filename: str, owner: str):
    status_key = f"{owner}:{filename}"
    try:
        _set_status(status_key, "extracting_text")
        logger.info(f"Processing started: {filename} (owner: {owner})")
        pages = extract_document_pages(file_path)
        if not any(p["text"].strip() for p in pages):
            raise ValueError("No text could be extracted from the document.")
        _set_status(status_key, "indexing")
        db.add_document_pages(filename, pages, owner)
        _set_status(status_key, "completed")
        logger.info(f"Processing completed: {filename} (owner: {owner})")
    except Exception as e:
        _set_status(status_key, f"error: {e}")
        logger.error(f"Error processing {filename} for {owner}: {e}")


# --- Pydantic model ---
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)


# ======================== ROUTES ========================

@app.post("/register")
async def register(request: Request, background_tasks: BackgroundTasks):
    auth_limiter.check(_client_ip(request))
    fields, is_html = await _parse_payload(
        request, "email", "password", "confirm_password",
        "first_name", "last_name", "company", "phone_number"
    )
    try:
        email = (fields["email"] or "").strip().lower()
        pw = fields["password"] or ""
        _require(email and pw, "Email and password are required")
        _require(validate_email(email), "Please provide a valid email address")
        _require(len(pw) >= 6, "Password must be at least 6 characters long")
        _require(len(pw) <= MAX_PASSWORD_LENGTH, f"Password must not exceed {MAX_PASSWORD_LENGTH} characters")
        if fields["confirm_password"] is not None:
            _require(pw == fields["confirm_password"], "Passwords do not match")

        fn = (fields["first_name"] or "").strip()
        ln = (fields["last_name"] or "").strip()
        co = (fields["company"] or "").strip()
        ph = (fields["phone_number"] or "").strip()
        _require(all([fn, ln, co, ph]), "First name, last name, company, and phone number are all required")
        _require(len(fn) >= 2, "First name must be at least 2 characters long")
        _require(len(ln) >= 2, "Last name must be at least 2 characters long")
        _require(len(co) >= 2, "Company name must be at least 2 characters long")
        _require(_PHONE_RE.match(ph), "Please provide a valid phone number (7-20 characters, e.g., +1 (555) 019-2834)")

        _require(register_user(email, pw, fn, ln, co, ph), "Registration could not be completed. Please try again.")
    except _AuthError as e:
        return _auth_response(e, is_html)

    background_tasks.add_task(send_registration_email, email)
    if is_html:
        return HTMLResponse(
            '<div id="auth-success-container" hx-swap-oob="true" class="success-msg">Registration complete. Please sign in.</div>'
            '<div id="auth-error-container" hx-swap-oob="true" class="error-msg" style="display: none;"></div>'
            '<script>showAuthMode("login");</script>'
        )
    return {"message": "User registered successfully"}


@app.post("/login")
async def login(request: Request, background_tasks: BackgroundTasks):
    auth_limiter.check(_client_ip(request))
    fields, is_html = await _parse_payload(request, "email", "password")
    try:
        _require(fields["email"] and fields["password"], "Email and password are required")
        user = authenticate_user(fields["email"], fields["password"])
        _require(user is not None, "Incorrect email or password", 401)
    except _AuthError as e:
        return _auth_response(e, is_html)

    # Device fingerprint
    client_ip = _client_ip(request)
    ua = request.headers.get("user-agent", "Unknown Device")
    dev_hash = hashlib.sha256(f"{client_ip}:{ua}".encode()).hexdigest()
    if not is_device_known(user["id"], dev_hash):
        logger.warning(f"New device login for user ID {user['id']}")
        background_tasks.add_task(send_unknown_device_login_email, user["email"], client_ip, ua)
    register_device(user["id"], dev_hash)

    token = create_access_token({"sub": user["email"]})
    if is_html:
        resp = HTMLResponse(content="")
        resp.headers["HX-Redirect"] = "/"
        resp.set_cookie(key="access_token", value=token, httponly=True, secure=IS_PRODUCTION, max_age=36000, samesite="lax")
        return resp
    return {"access_token": token, "token_type": "bearer", "email": user["email"]}


@app.post("/logout")
async def logout():
    resp = HTMLResponse(content="")
    resp.headers["HX-Redirect"] = "/"
    resp.delete_cookie("access_token")
    return resp


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    is_light = request.cookies.get("theme") == "light"
    token = request.cookies.get("access_token")
    is_auth, email, docs = False, "", []
    if token:
        try:
            email = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM]).get("sub", "")
            if email:
                is_auth = True
                docs = db.list_documents(email)
        except jwt.PyJWTError:
            pass
    csrf = request.cookies.get(CSRF_COOKIE, "")
    if not csrf:
        csrf = secrets.token_hex(32)
    resp = templates.TemplateResponse("index.html", {
        "request": request, "is_authenticated": is_auth, "email": email,
        "documents": docs, "is_light_theme": is_light, "csrf_token": csrf,
    })
    if not request.cookies.get(CSRF_COOKIE):
        resp.set_cookie(key=CSRF_COOKIE, value=csrf, httponly=False, secure=IS_PRODUCTION, samesite="lax", max_age=36000)
    if not is_auth and token:
        resp.delete_cookie("access_token")
    return resp


# --- Core RAG Routes ---

@app.post("/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    filename = os.path.basename(file.filename or "")
    if not filename:
        raise HTTPException(400, "Invalid filename")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    contents = bytearray()
    while chunk := await file.read(1024 * 1024):
        contents.extend(chunk)
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(400, f"File too large. Maximum: {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")

    safe_email = re.sub(r'[^a-zA-Z0-9_.-]', '_', current_user)
    user_dir = os.path.join(UPLOAD_DIR, safe_email)
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(500, f"Could not save file: {e}")

    existing = db.delete_document(filename, current_user)
    if existing > 0:
        logger.info(f"Removed {existing} old chunks for '{filename}' before re-indexing.")
    _set_status(f"{current_user}:{filename}", "queued")
    background_tasks.add_task(process_document_task, file_path, filename, current_user)
    return {"filename": filename, "status": "queued"}


_STATUS_MAP = {
    "completed": ("completed", "Success"),
    "queued":    ("queued", "Queued"),
    "unknown":   ("unknown", "Completed"),
}

@app.get("/status/{filename}")
async def get_processing_status(filename: str, request: Request, current_user: str = Depends(get_current_user)):
    status = _get_status(f"{current_user}:{filename}")
    if request.headers.get("HX-Request"):
        if status.startswith("error"):
            badge, label = "error", "Failed"
        else:
            badge, label = _STATUS_MAP.get(status, ("indexing", "Indexing"))
        return templates.TemplateResponse("status_badge.html", {"request": request, "badge": badge, "label": label, "name": filename})
    return {"filename": filename, "status": status}


@app.get("/documents")
async def list_documents(request: Request, current_user: str = Depends(get_current_user)):
    docs = db.list_documents(current_user)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("doc_list.html", {"request": request, "documents": docs})
    return {"documents": docs}


@app.delete("/documents/{filename}")
async def delete_document(filename: str, request: Request, current_user: str = Depends(get_current_user)):
    filename = os.path.basename(filename)
    deleted = db.delete_document(filename, current_user)
    if not deleted:
        raise HTTPException(404, "Document not found")
    path = os.path.join(UPLOAD_DIR, re.sub(r'[^a-zA-Z0-9_.-]', '_', current_user), filename)
    if os.path.exists(path):
        os.remove(path)
    _remove_status(f"{current_user}:{filename}")
    if request.headers.get("HX-Request"):
        return HTMLResponse("")
    return {"message": f"Document '{filename}' deleted", "deleted_chunks": deleted}


@app.post("/query")
async def query_assistant(payload: QueryRequest, request: Request, current_user: str = Depends(get_current_user)):
    query_limiter.check(_client_ip(request))
    contexts = db.query_similar_context(payload.query, current_user, top_k=5)
    ctx_str = "\n".join(
        f"--- Chunk {i} (Source: {c['metadata'].get('filename','?')}, Page: {c['metadata'].get('page',1)}) ---\n{c['text']}"
        for i, c in enumerate(contexts, 1)
    )
    prompt = (
        "You are a helpful and professional Legal Assistant. Answer based strictly on the provided document contexts. "
        "If the answer cannot be found, state so. Always reference sources (filenames and page numbers).\n\n"
        f"CONTEXT:\n{ctx_str}\n\nQUESTION:\n{payload.query}\n\nANSWER:"
    )

    async def stream():
        try:
            loop = asyncio.get_event_loop()
            model = genai.GenerativeModel(GEMINI_MODEL)
            response = await loop.run_in_executor(None, lambda: model.generate_content(prompt, stream=True))
            for chunk in await loop.run_in_executor(None, lambda: [c.text for c in response if c.text]):
                yield chunk
        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            yield f"\n[Error: {e}]"

    return StreamingResponse(stream(), media_type="text/plain")


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
