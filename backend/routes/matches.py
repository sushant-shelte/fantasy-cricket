from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, date

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import IST
from backend.services.venue_stats import get_venue_stats

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
    today = now.date()
    locked = now >= match_datetime

    parsed_date = datetime.strptime(match_date, "%Y-%m-%d").date()
    if parsed_date < today:
        status = "over"
    elif now < match_datetime:
        status = "future"
    elif now < match_datetime + timedelta(hours=4):
        status = "live"
    else:
        status = "over"

    return status, locked


@router.get("/matches")
async def list_matches(user: dict = Depends(get_current_user)):
    db = get_db()
    rows = db.execute("SELECT * FROM matches ORDER BY id").fetchall()

    now = datetime.now(IST)
    today = now.date()

    result = []
    for row in rows:
        match = dict(row)
        status, locked = compute_match_status(match["match_date"], match["match_time"])
        match["status"] = status
        match["locked"] = locked
        match["venue"] = get_venue_stats(match["team1"], match["team2"], match.get("venue"))
        result.append(match)

    today_matches = [m for m in result if datetime.strptime(m["match_date"], "%Y-%m-%d").date() == today]
    future_matches = [m for m in result if m["status"] == "future" and datetime.strptime(m["match_date"], "%Y-%m-%d").date() != today]
    over_matches = [m for m in result if m["status"] == "over" and datetime.strptime(m["match_date"], "%Y-%m-%d").date() != today]

    today_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    future_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    over_matches.sort(key=lambda m: (m["match_date"], m["match_time"]), reverse=True)

    return today_matches + future_matches + over_matches
