import os
import shutil
import uuid

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.requests import Request

from config import settings
from database import SyncSessionLocal
from legal_api.api import _client_ip
from main import app


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_forwarded_for_ignored_from_unknown_peer():
    settings.TRUSTED_PROXIES = ""
    assert _client_ip(_request("203.0.113.9", "10.0.0.1")) == "203.0.113.9"


def test_forwarded_for_honoured_from_trusted_proxy_rightmost_only():
    settings.TRUSTED_PROXIES = "10.0.0.1"
    assert _client_ip(_request("10.0.0.1", "1.2.3.4, 203.0.113.9")) == "203.0.113.9"
    settings.TRUSTED_PROXIES = ""


def test_oversized_upload_refused_and_nothing_left_on_disk():
    email = f"upload-{uuid.uuid4()}@test.local"
    session = SyncSessionLocal()
    try:
        session.execute(text("INSERT INTO users (email, password_hash) VALUES (:e, 'x')"), {"e": email})
        session.commit()
    finally:
        session.close()

    token = jwt.encode({"sub": email}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    original_cap = settings.MAX_FILE_SIZE_BYTES
    settings.MAX_FILE_SIZE_BYTES = 1024
    user_dir = os.path.join(settings.UPLOAD_DIR, email.replace("@", "_"))
    try:
        r = TestClient(app).post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("big.txt", b"x" * 4096, "text/plain")},
        )
        assert r.status_code == 400, r.text
        assert "too large" in r.json()["detail"].lower()
        leftovers = os.listdir(user_dir) if os.path.isdir(user_dir) else []
        assert not leftovers, f"partial upload left behind: {leftovers}"
    finally:
        settings.MAX_FILE_SIZE_BYTES = original_cap
        # The endpoint creates the user's upload directory before the size
        # check runs; deleting the user row does not remove it.
        shutil.rmtree(user_dir, ignore_errors=True)
        session = SyncSessionLocal()
        session.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        session.commit()
        session.close()


if __name__ == "__main__":
    test_forwarded_for_ignored_from_unknown_peer()
    test_forwarded_for_honoured_from_trusted_proxy_rightmost_only()
    test_oversized_upload_refused_and_nothing_left_on_disk()
    print("ok")
