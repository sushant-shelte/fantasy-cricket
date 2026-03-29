from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional

from backend.middleware.auth import get_current_user
from backend.firebase_setup import verify_firebase_token
from backend.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    name: str
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.post("/register")
async def register(body: RegisterBody, authorization: str = Header(default=None)):
    db = get_db()

    # Try Firebase token first
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        decoded = verify_firebase_token(token)

        if decoded:
            firebase_uid = decoded["uid"]
            email = decoded.get("email", "")

            # Check by firebase_uid first
            existing = db.execute(
                "SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)
            ).fetchone()
            if existing:
                return dict(existing)

            # Check by email — maybe user exists from seed data
            existing_email = db.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing_email:
                # Update existing record with real firebase_uid
                db.execute(
                    "UPDATE users SET firebase_uid = ? WHERE id = ?",
                    (firebase_uid, existing_email["id"]),
                )
                db.commit()
                user = db.execute("SELECT * FROM users WHERE id = ?", (existing_email["id"],)).fetchone()
                return dict(user)

            # Create new user
            db.execute(
                "INSERT INTO users (firebase_uid, email, name, mobile) VALUES (?, ?, ?, ?)",
                (firebase_uid, email, body.name, body.mobile or ""),
            )
            db.commit()

            user = db.execute("SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)).fetchone()
            return dict(user)

    # Dev mode fallback
    if not body.email:
        raise HTTPException(status_code=400, detail="Email is required")

    firebase_uid = f"dev_{body.email}"
    email = body.email

    existing = db.execute(
        "SELECT * FROM users WHERE firebase_uid = ? OR email = ?",
        (firebase_uid, email),
    ).fetchone()
    if existing:
        return dict(existing)

    db.execute(
        "INSERT INTO users (firebase_uid, email, name, mobile) VALUES (?, ?, ?, ?)",
        (firebase_uid, email, body.name, body.mobile or ""),
    )
    db.commit()

    user = db.execute("SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)).fetchone()
    return dict(user)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
