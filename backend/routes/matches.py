from fastapi import APIRouter, Depends
from datetime import datetime, timedelta

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import IST

router = APIRouter(prefix="/api", tags=["matches"])


def compute_match_status(match_date: str, match_time: str):
    try:
        match_datetime = datetime.strptime(
            f"{match_date} {match_time}", "%Y-%m-%d %H:%M"
        )
        match_datetime = IST.localize(match_datetime)
    except Exception:
        return "future", False

    now = datetime.now(IST)
    locked = now >= match_datetime

    if now < match_datetime:
        status = "future"
    elif now < match_datetime + timedelta(hours=5):
        status = "live"
    else:
        status = "over"

    return status, locked


@router.get("/matches")
async def list_matches(user: dict = Depends(get_current_user)):
    db = get_db()
    rows = db.execute("SELECT * FROM matches ORDER BY id").fetchall()

    result = []
    for row in rows:
        match = dict(row)
        status, locked = compute_match_status(match["match_date"], match["match_time"])
        match["status"] = status
        match["locked"] = locked
        result.append(match)

    return result
