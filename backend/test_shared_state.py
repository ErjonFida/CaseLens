import uuid

from sqlalchemy import text

from database import SyncSessionLocal
from legal_api.api import RateLimiter, RateLimitExceeded, _get_status, _set_status


def _sql(stmt, **params):
    session = SyncSessionLocal()
    try:
        row = session.execute(text(stmt), params)
        result = row.scalar() if row.returns_rows else None
        session.commit()
        return result
    finally:
        session.close()


def test_limit_is_shared_across_workers():
    key = f"test-{uuid.uuid4()}"
    worker_a, worker_b = RateLimiter(3, 60), RateLimiter(3, 60)

    worker_a.check(key)
    worker_b.check(key)
    worker_a.check(key) 

    for worker in (worker_b, worker_a):
        try:
            worker.check(key)
        except RateLimitExceeded:
            return
    raise AssertionError("4th request past a limit of 3 was allowed: budget is per-worker")


def test_status_survives_a_different_worker():
    email = f"status-{uuid.uuid4()}@test.local"
    uid = _sql(
        "INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id", e=email
    )
    try:
        assert _get_status(uid, "contract.pdf") == "unknown"
        _set_status(uid, "contract.pdf", "indexing")
        # No in-process cache to hit: this read goes to Postgres, as another worker's read would.
        assert _get_status(uid, "contract.pdf") == "indexing"
    finally:
        _sql("DELETE FROM users WHERE id = :i", i=uid)


if __name__ == "__main__":
    test_limit_is_shared_across_workers()
    test_status_survives_a_different_worker()
    print("ok")
