import os
import sqlite3
import bcrypt
import logging
import re
import threading
from contextlib import contextmanager

logger = logging.getLogger("db_manager")
DB_PATH = "./db/users.db"

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
MAX_PASSWORD_LENGTH = 72


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


@contextmanager
def _execute():
    """Thread-safe cursor context manager for the shared connection."""
    conn = _get_conn()
    with _db_lock:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            raise


def init_db():
    with _execute() as cur:
        # Schema migration
        try:
            cur.execute("PRAGMA table_info(users)")
            cols = [c[1] for c in cur.fetchall()]
            if cols:
                if "email" not in cols:
                    logger.warning("Old schema detected. Dropping tables to migrate.")
                    cur.execute("DROP TABLE IF EXISTS users")
                    cur.execute("DROP TABLE IF EXISTS known_devices")
                else:
                    for col in ["first_name", "last_name", "company", "phone_number"]:
                        if col not in cols:
                            cur.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception as e:
            logger.error(f"Schema check error: {e}")

        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL, last_name TEXT NOT NULL,
            company TEXT NOT NULL, phone_number TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS known_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, device_hash TEXT NOT NULL,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(user_id, device_hash))""")
    logger.info("Database initialized successfully.")


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def register_user(email: str, password: str, first_name: str, last_name: str, company: str, phone_number: str) -> bool:
    email = email.strip().lower()
    if not email or not password or not validate_email(email) or len(password) > MAX_PASSWORD_LENGTH:
        return False
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with _execute() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, first_name, last_name, company, phone_number) VALUES (?,?,?,?,?,?)",
                (email, pw_hash, first_name.strip(), last_name.strip(), company.strip(), phone_number.strip())
            )
        return True
    except sqlite3.IntegrityError:
        logger.warning("Registration failed: duplicate or constraint violation.")
        return False
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return False


def authenticate_user(email: str, password: str) -> dict | None:
    email = email.strip().lower()
    if not email or not password or len(password) > MAX_PASSWORD_LENGTH:
        return None
    try:
        with _execute() as cur:
            cur.execute("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
        if not row:
            return None
        uid, db_email, pw_hash = row
        if bcrypt.checkpw(password.encode(), pw_hash.encode()):
            return {"id": uid, "email": db_email}
        return None
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None


def is_device_known(user_id: int, device_hash: str) -> bool:
    try:
        with _execute() as cur:
            cur.execute("SELECT 1 FROM known_devices WHERE user_id=? AND device_hash=?", (user_id, device_hash))
            return cur.fetchone() is not None
    except Exception:
        return False


def register_device(user_id: int, device_hash: str):
    try:
        with _execute() as cur:
            cur.execute("""INSERT INTO known_devices (user_id, device_hash) VALUES (?,?)
                ON CONFLICT(user_id, device_hash) DO UPDATE SET last_login=CURRENT_TIMESTAMP""",
                (user_id, device_hash))
    except Exception as e:
        logger.error(f"Device registration error: {e}")


init_db()
