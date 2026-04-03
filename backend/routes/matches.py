import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from backend.config import IST
from backend.database import get_db
from backend.middleware.auth import get_current_user
from backend.services import data_service
from backend.services.venue_stats import (
    get_today_cached_venue_stats,
    prime_today_venue_cache,
)

router = APIRouter(prefix="/api", tags=["matches"])
MATCHES_CACHE_TTL_SECONDS = 20
MATCHES_RESPONSE_CACHE = {
    "matches": None,
    "dashboard": None,
    "generated_at": 0.0,
    "today_key": "",
}


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
    return _get_matches_payload(cache_key="matches")


@router.get("/dashboard/matches")
async def dashboard_matches(user: dict = Depends(get_current_user)):
    payload = _get_matches_payload(cache_key="dashboard")
    if not user:
        return payload
    return _attach_user_match_ranks(payload, user["id"])


def invalidate_matches_response_cache():
    MATCHES_RESPONSE_CACHE["matches"] = None
    MATCHES_RESPONSE_CACHE["dashboard"] = None
    MATCHES_RESPONSE_CACHE["generated_at"] = 0.0
    MATCHES_RESPONSE_CACHE["today_key"] = ""


def _is_matches_cache_valid(cache_key: str, today_key: str) -> bool:
    if MATCHES_RESPONSE_CACHE.get(cache_key) is None:
        return False
    if MATCHES_RESPONSE_CACHE.get("today_key") != today_key:
        return False
    return (time.time() - MATCHES_RESPONSE_CACHE.get("generated_at", 0.0)) < MATCHES_CACHE_TTL_SECONDS


def _build_matches_payload() -> list[dict]:
    route_started = time.perf_counter()
    rows = data_service.get_matches_api_rows()
    today_key = datetime.now(IST).strftime("%Y-%m-%d")
    prepared_matches = []
    for row in rows:
        match = dict(row)
        status, locked = compute_match_status(match["match_date"], match["match_time"])
        match["status"] = status
        match["locked"] = locked
        prepared_matches.append(match)

    prime_today_venue_cache(prepared_matches)

    result = []
    for match in prepared_matches:
        match["venue"] = get_today_cached_venue_stats(match["id"], match["match_date"], match["status"])
        result.append(match)

    today_matches = [m for m in result if m["match_date"] == today_key]
    future_matches = [m for m in result if m["status"] == "future" and m["match_date"] != today_key]
    over_matches = [m for m in result if m["status"] == "over" and m["match_date"] != today_key]

    today_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    future_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    over_matches.sort(key=lambda m: (m["match_date"], m["match_time"]), reverse=True)

    payload = today_matches + future_matches + over_matches
    route_ms = (time.perf_counter() - route_started) * 1000
    if route_ms >= 80:
        print(f"[MATCHES timing] build={route_ms:.1f}ms rows={len(payload)}")
    return payload


def _get_matches_payload(cache_key: str) -> list[dict]:
    today_key = datetime.now(IST).strftime("%Y-%m-%d")
    if _is_matches_cache_valid(cache_key, today_key):
        return MATCHES_RESPONSE_CACHE[cache_key] or []

    payload = _build_matches_payload()
    MATCHES_RESPONSE_CACHE["matches"] = payload
    MATCHES_RESPONSE_CACHE["dashboard"] = payload
    MATCHES_RESPONSE_CACHE["generated_at"] = time.time()
    MATCHES_RESPONSE_CACHE["today_key"] = today_key
    return payload


def _attach_user_match_ranks(payload: list[dict], user_id: int) -> list[dict]:
    db = get_db()
    rank_rows = db.execute(
        """
        SELECT ranked.match_id, ranked.match_rank
        FROM (
            SELECT
                cp.match_id,
                cp.user_id,
                RANK() OVER (PARTITION BY cp.match_id ORDER BY cp.points DESC) AS match_rank
            FROM contestant_points cp
        ) ranked
        WHERE ranked.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    rank_map = {row["match_id"]: row["match_rank"] for row in rank_rows}

    result = []
    for match in payload:
        match_copy = dict(match)
        if match_copy.get("status") in {"live", "over"}:
            match_copy["current_rank"] = rank_map.get(match_copy["id"])
        else:
            match_copy["current_rank"] = None
        result.append(match_copy)
    return result
