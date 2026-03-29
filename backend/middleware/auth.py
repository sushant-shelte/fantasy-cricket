from fastapi import Header, HTTPException, Depends
from backend.database import get_db
from backend.firebase_setup import verify_firebase_token


async def get_current_user(authorization: str = Header(default=None)):
    db = get_db()

    # If Bearer token provided, try Firebase verification
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        decoded = verify_firebase_token(token)

        if decoded:
            firebase_uid = decoded["uid"]
            user = db.execute(
                "SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)
            ).fetchone()

            if not user:
                raise HTTPException(status_code=401, detail="User not registered. Please register first.")

            if not user["is_active"]:
                raise HTTPException(status_code=403, detail="Account disabled")

            return dict(user)

    # Fallback: dev mode — return first available user
    user = db.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    if user:
        return dict(user)

    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
