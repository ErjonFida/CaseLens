import os
import tempfile
import uuid

_static = tempfile.mkdtemp()
os.makedirs(os.path.join(_static, "assets"))
with open(os.path.join(_static, "index.html"), "w") as f:
    f.write("<!doctype html><title>CaseLens</title>")
with open(os.path.join(_static, "assets", "app.js"), "w") as f:
    f.write("console.log('app')")
os.environ["STATIC_DIR"] = _static

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.requests import Request

from config import _normalize_db_url, settings
from database import SyncSessionLocal
from legal_api import api
from main import app


def _request(peer: str, forwarded: str) -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-for", forwarded.encode())], "client": (peer, 1234)})


def test_trusted_proxy_can_be_a_range():
    settings.TRUSTED_PROXIES = "10.0.0.0/8"
    try:
        assert api._client_ip(_request("10.42.7.3", "1.2.3.4, 203.0.113.9")) == "203.0.113.9"
        assert api._client_ip(_request("198.51.100.7", "203.0.113.9")) == "198.51.100.7"
    finally:
        settings.TRUSTED_PROXIES = ""


def test_neon_url_works_for_both_drivers():
    url = "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert _normalize_db_url(url, async_driver=True) == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb?ssl=require"
    assert _normalize_db_url(url, async_driver=False).startswith("postgresql+psycopg2://u:p@ep-x.aws.neon.tech/neondb?sslmode=require")


def _sql(statement: str, **params):
    session = SyncSessionLocal()
    try:
        session.execute(text(statement), params)
        session.commit()
    finally:
        session.close()


def test_demo_account_is_read_only_and_capped():
    email = f"demo-{uuid.uuid4()}@example.com"
    _sql("INSERT INTO users (email, password_hash, is_demo) VALUES (:e, 'x', true)", e=email)
    token = jwt.encode({"sub": email}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    auth = {"Authorization": f"Bearer {token}"}
    try:
        with TestClient(app) as client:
            assert client.get("/api/health").json()["demo"] is True
            assert client.post("/api/demo").status_code == 200
            assert client.get("/api/me", headers=auth).json()["is_demo"] is True

            upload = client.post("/api/upload", headers=auth, files={"file": ("x.txt", b"hello", "text/plain")})
            assert upload.status_code == 403, upload.text
            assert client.delete("/api/documents/x.txt", headers=auth).status_code == 403

            api.demo_limiter.max_req = 0  # the day's allowance, already spent
            try:
                chat = client.post("/api/chat", headers=auth, json={"messages": [{"role": "user", "content": "hi"}]})
            finally:
                api.demo_limiter.max_req = settings.DEMO_DAILY_QUESTIONS
            assert chat.status_code == 429 and "allowance" in chat.json()["detail"], chat.text
    finally:
        _sql("DELETE FROM users WHERE email = :e", e=email)


def test_registration_can_be_closed():
    password = "correct horse"
    payload = {"email": f"closed-{uuid.uuid4()}@example.com", "password": password, "confirm_password": password,
               "first_name": "Alice", "last_name": "Smith", "company": "ACME Legal", "phone_number": "+1 (555) 019-2834"}
    settings.REGISTRATION_OPEN = False
    try:
        with TestClient(app) as client:
            assert client.get("/api/health").json()["registration"] is False
            register = client.post("/api/register", json=payload)
            assert register.status_code == 403, register.text
    finally:
        settings.REGISTRATION_OPEN = True


def test_one_container_serves_the_app_and_the_api():
    with TestClient(app) as client:
        assert "CaseLens" in client.get("/").text
        assert "CaseLens" in client.get("/login").text           # a client-side route
        assert "console.log" in client.get("/assets/app.js").text
        assert client.get("/api/health").json()["status"] == "online"
        assert client.get("/api/no-such-endpoint").status_code == 404  # not index.html


if __name__ == "__main__":
    test_trusted_proxy_can_be_a_range()
    test_neon_url_works_for_both_drivers()
    test_demo_account_is_read_only_and_capped()
    test_registration_can_be_closed()
    test_one_container_serves_the_app_and_the_api()
    print("ok")
