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
DASHBOARD_RANK_CACHE = {
    "signature": None,
    "match_rank_map": {},
    "generated_at": 0.0,
}
DASHBOARD_RANK_CACHE_TTL_SECONDS = 20


def compute_match_status(match_date: str, match_time: str):
    return compute_runtime_match_status(match_date, match_time, "future")


def compute_runtime_match_status(match_date: str, match_time: str, stored_status: str | None):
    try:
        match_datetime = datetime.strptime(
            f"{match_date} {match_time}", "%Y-%m-%d %H:%M"
        )
        match_datetime = IST.localize(match_datetime)
    except Exception:
        return "future", False

    now = datetime.now(IST)
    normalized_status = (stored_status or "").strip().lower()

    if normalized_status in {"completed", "nr"}:
        return normalized_status, True

    # Within 30 minutes before match start: "lineups" state
    if now < match_datetime:
        if now >= match_datetime - timedelta(minutes=30):
            return "lineups", False
        return "future", False

    if normalized_status == "live":
        return "live", True

    if now >= match_datetime + timedelta(hours=5):
        return "completed", True

    return "live", True


def _should_fetch_toss_for_dashboard(match_date: str, match_time: str, status: str) -> bool:
    # Only fetch toss for matches in "lineup" state (within 30min of start)
    return status == "lineups"


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
    DASHBOARD_RANK_CACHE["signature"] = None
    DASHBOARD_RANK_CACHE["match_rank_map"] = {}
    DASHBOARD_RANK_CACHE["generated_at"] = 0.0


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
        status, locked = compute_runtime_match_status(
            match["match_date"],
            match["match_time"],
            match.get("status"),
        )
        match["status"] = status
        match["locked"] = locked
        prepared_matches.append(match)

    prime_today_venue_cache(prepared_matches)

    result = []
    for match in prepared_matches:
        match["venue"] = get_today_cached_venue_stats(match["id"], match["match_date"], match["status"])
        
        # Queue toss fetch for lineup matches, then get cached result (may be None if still fetching)
        should_fetch = _should_fetch_toss_for_dashboard(match["match_date"], match["match_time"], match["status"])
        if should_fetch:
            data_service.queue_toss_fetch(
                int(match["id"]),
                match["team1"],
                match["team2"],
                match["match_date"],
                match["match_time"],
                should_fetch=True,
            )
            # Try to get cached toss (background fetcher may have processed it already)
            cached_toss = data_service.get_cached_toss_info(
                int(match["id"]),
                match["match_date"],
                match["match_time"],
            )
            match["toss"] = cached_toss
        else:
            match["toss"] = None
        
        result.append(match)

    today_matches = [m for m in result if (m["match_date"] == today_key or m["status"] == "live") and m["status"] not in {"completed", "nr"}]
    future_matches = [m for m in result if m["status"] == "future" and m["match_date"] != today_key]
    completed_matches = [m for m in result if m["status"] in {"completed", "nr"}]

    today_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    future_matches.sort(key=lambda m: (m["match_date"], m["match_time"]))
    completed_matches.sort(key=lambda m: (m["match_date"], m["match_time"]), reverse=True)

    payload = today_matches + future_matches + completed_matches
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
        if match.get("status") in {"live", "completed"}
    ]
    if not relevant_match_ids:
        return payload

    match_rank_map = _get_cached_match_rank_map(db, relevant_match_ids)

    result = []
    for match in payload:
        match_copy = dict(match)
        if match_copy.get("status") in {"live", "completed"}:
            match_copy["current_rank"] = match_rank_map.get(int(match_copy["id"]), {}).get(int(user_id))
        else:
            match_copy["current_rank"] = None
        result.append(match_copy)
    return result


def _get_cached_match_rank_map(db, relevant_match_ids: list[int]) -> dict[int, dict[int, int]]:
    signature = _build_rank_signature(db, relevant_match_ids)
    now_ts = time.time()
    if (
        DASHBOARD_RANK_CACHE.get("signature") == signature
        and (now_ts - float(DASHBOARD_RANK_CACHE.get("generated_at", 0.0))) < DASHBOARD_RANK_CACHE_TTL_SECONDS
    ):
        return DASHBOARD_RANK_CACHE.get("match_rank_map", {})

    match_rank_map = _build_match_rank_map(db, relevant_match_ids)
    DASHBOARD_RANK_CACHE["signature"] = signature
    DASHBOARD_RANK_CACHE["match_rank_map"] = match_rank_map
    DASHBOARD_RANK_CACHE["generated_at"] = now_ts
    return match_rank_map


def _build_rank_signature(db, relevant_match_ids: list[int]) -> tuple:
    sorted_ids = sorted({int(match_id) for match_id in relevant_match_ids})
    placeholders = ",".join("?" * len(sorted_ids))
    latest_player_points = db.execute(
        f"""
        SELECT COALESCE(MAX(last_updated), '') AS latest
        FROM player_points
        WHERE match_id IN ({placeholders})
        """,
        sorted_ids,
    ).fetchone()
    latest_team_update = db.execute(
        f"""
        SELECT COALESCE(MAX(updated_at), '') AS latest
        FROM user_teams
        WHERE match_id IN ({placeholders})
        """,
        sorted_ids,
    ).fetchone()
    return (
        tuple(sorted_ids),
        (latest_player_points["latest"] if latest_player_points else "") or "",
        (latest_team_update["latest"] if latest_team_update else "") or "",
    )


def _build_match_rank_map(db, relevant_match_ids: list[int]) -> dict[int, dict[int, int]]:
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
    return match_rank_map
