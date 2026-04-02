import time

from fastapi import Depends, Header, HTTPException, Request
from backend.database import get_db
from backend.firebase_setup import verify_firebase_token


def _log_auth_timing(path: str, verify_ms: float, lookup_ms: float, total_ms: float):
    if total_ms < 150:
        return
    print(
        f"[AUTH timing] {path} verify={verify_ms:.1f}ms "
        f"lookup={lookup_ms:.1f}ms total={total_ms:.1f}ms"
    )


async def get_current_user(request: Request, authorization: str = Header(default=None)):
    started_at = time.perf_counter()
    db = get_db()
    verify_ms = 0.0
    lookup_ms = 0.0

    # If Bearer token provided, try Firebase verification
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        verify_started = time.perf_counter()
        decoded = verify_firebase_token(token)
        verify_ms = (time.perf_counter() - verify_started) * 1000

        if decoded:
            firebase_uid = decoded["uid"]
            lookup_started = time.perf_counter()
            user = db.execute(
                "SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)
            ).fetchone()
            lookup_ms = (time.perf_counter() - lookup_started) * 1000

            if not user:
                raise HTTPException(status_code=401, detail="User not registered. Please register first.")

            if not user["is_active"]:
                raise HTTPException(status_code=403, detail="Account disabled")

            total_ms = (time.perf_counter() - started_at) * 1000
            _log_auth_timing(request.url.path, verify_ms, lookup_ms, total_ms)
            return dict(user)

    # Fallback: dev mode — return first available user
    lookup_started = time.perf_counter()
    user = db.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    lookup_ms = (time.perf_counter() - lookup_started) * 1000
    if user:
        total_ms = (time.perf_counter() - started_at) * 1000
        _log_auth_timing(request.url.path, verify_ms, lookup_ms, total_ms)
        return dict(user)

    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
