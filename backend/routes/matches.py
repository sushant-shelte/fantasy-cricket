import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from backend.config import IST
from backend.database import get_db
from backend.middleware.auth import get_current_user
from backend.services import data_service
from backend.services.scraper import fetch_toss_info, should_attempt_toss_fetch
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


def _should_fetch_toss_for_dashboard(match_date: str, match_time: str, status: str) -> bool:
    return status == "future" and should_attempt_toss_fetch(match_date, match_time)


@router.get("/matches")
async def list_matches(user: dict = Depends(get_current_user)):
    return _get_matches_payload(cache_key="matches")


@router.get("/dashboard/matches")
async def dashboard_matches(user: dict = Depends(get_current_user)):
    route_started = time.perf_counter()
    payload = _get_matches_payload(cache_key="dashboard")
    if not user:
        return payload
    result = _attach_user_match_ranks(payload, user["id"])
    route_ms = (time.perf_counter() - route_started) * 1000
    if route_ms >= 80:
        print(f"[API timing] GET /api/dashboard/matches total={route_ms:.1f}ms user_id={user['id']}")
    return result


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
        match["toss"] = (
            fetch_toss_info(
                int(match["id"]),
                match["team1"],
                match["team2"],
                match["match_date"],
                match["match_time"],
            )
            if _should_fetch_toss_for_dashboard(match["match_date"], match["match_time"], match["status"])
            else None
        )
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
    relevant_match_ids = [
        int(match["id"])
        for match in payload
        if match.get("status") in {"live", "over"}
    ]
    if not relevant_match_ids:
        return payload

    placeholders = ",".join("?" * len(relevant_match_ids))
    score_rows = db.execute(
        """
        SELECT
            ut.match_id,
            ut.user_id,
            u.name,
            SUM(
                COALESCE(pp.points, 0) *
                CASE
                    WHEN ut.is_captain = 1 THEN 2.0
                    WHEN ut.is_vice_captain = 1 THEN 1.5
                    ELSE 1.0
                END
            ) AS points
        FROM user_teams ut
        JOIN users u ON u.id = ut.user_id
        LEFT JOIN player_points pp
            ON pp.match_id = ut.match_id AND pp.player_id = ut.player_id
        WHERE u.is_active = 1
          AND ut.match_id IN (""" + placeholders + """)
        GROUP BY ut.match_id, ut.user_id, u.name
        """,
        relevant_match_ids,
    ).fetchall()

    match_rank_map: dict[int, dict[int, int]] = {}
    match_points: dict[int, list[dict]] = {}
    for row in score_rows:
        match_points.setdefault(int(row["match_id"]), []).append({
            "user_id": int(row["user_id"]),
            "name": row["name"],
            "points": round(float(row["points"] or 0), 2),
        })

    for match_id, contestants in match_points.items():
        sorted_contestants = sorted(
            contestants,
            key=lambda item: (-item["points"], item["name"]),
        )
        rank_lookup: dict[int, int] = {}
        current_rank = 0
        previous_points = None
        for index, contestant in enumerate(sorted_contestants, start=1):
            if previous_points is None or contestant["points"] != previous_points:
                current_rank = index
                previous_points = contestant["points"]
            rank_lookup[contestant["user_id"]] = current_rank
        match_rank_map[match_id] = rank_lookup

    result = []
    for match in payload:
        match_copy = dict(match)
        if match_copy.get("status") in {"live", "over"}:
            match_copy["current_rank"] = match_rank_map.get(int(match_copy["id"]), {}).get(int(user_id))
        else:
            match_copy["current_rank"] = None
        result.append(match_copy)
    return result
