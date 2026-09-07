import jwt
from fastapi.testclient import TestClient

from config import settings
from main import app


def _token(email: str = "csrf@test.local") -> str:
    return jwt.encode({"sub": email}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def test_cookie_is_not_accepted_as_credentials():
    client = TestClient(app)
    r = client.get("/api/me", cookies={"access_token": _token()})
    assert r.status_code == 401, f"cookie auth is back: {r.status_code}"


def test_login_sets_no_cookie():
    client = TestClient(app)
    r = client.post("/api/login", json={"email": "nobody@test.local", "password": "wrong"})
    assert "set-cookie" not in r.headers, r.headers.get("set-cookie")


if __name__ == "__main__":
    test_cookie_is_not_accepted_as_credentials()
    test_login_sets_no_cookie()
    print("ok")
