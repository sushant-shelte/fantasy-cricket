from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from collections import defaultdict

from backend.config import IST
from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.services import data_service

ENTRY_FEE = 50
PRIZE_SPLIT = [0.50, 0.30, 0.20]  # 1st, 2nd, 3rd

router = APIRouter(prefix="/api", tags=["leaderboard"])
LEADERBOARD_CACHE = {
    "leaderboard": None,
    "points_table": None,
    "player_points_version": "",
}


def _calculate_balances(db):
    """Calculate running balance for each user across all completed matches."""
    # Get all contestant points grouped by match
    rows = db.execute(
        """
        SELECT cp.user_id, cp.match_id, cp.points
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE u.is_active = 1
        ORDER BY cp.match_id, cp.points DESC
        """
    ).fetchall()

    # Group by match
    matches = defaultdict(list)
    for row in rows:
        matches[row["match_id"]].append({
            "user_id": row["user_id"],
            "points": float(row["points"]),
        })

    # Calculate balance per user
    balances = defaultdict(float)  # user_id -> running balance
    match_results = defaultdict(dict)  # user_id -> {match_id -> net}

    for match_id, participants in matches.items():
        # Sort by points descending
        participants.sort(key=lambda x: x["points"], reverse=True)
        num = len(participants)
        pool = num * ENTRY_FEE

        for i, p in enumerate(participants):
            uid = p["user_id"]

            # Prize for top 3
            if i < len(PRIZE_SPLIT):
                prize = pool * PRIZE_SPLIT[i]
            else:
                prize = 0

            net = prize - ENTRY_FEE
            balances[uid] += net
            match_results[uid][match_id] = round(net, 2)

    return balances, match_results


def _has_live_matches(db) -> bool:
    rows = db.execute("SELECT match_date, match_time FROM matches").fetchall()
    now = datetime.now(IST)
    for row in rows:
        try:
            match_datetime = datetime.strptime(
                f"{row['match_date']} {row['match_time']}", "%Y-%m-%d %H:%M"
            )
            match_datetime = IST.localize(match_datetime)
        except Exception:
            continue
        if match_datetime <= now < match_datetime + timedelta(hours=5):
            return True
    return False


def _build_leaderboard(db):
    balances, _ = _calculate_balances(db)

    users = db.execute(
        """
        SELECT u.id, u.name, COALESCE(SUM(cp.points), 0) AS total_points
        FROM users u
        LEFT JOIN contestant_points cp ON cp.user_id = u.id
        WHERE u.is_active = 1
        GROUP BY u.id, u.name
        ORDER BY total_points DESC
        """
    ).fetchall()

    result = []
    rank = 1
    for i, row in enumerate(users):
        uid = row["id"]
        pts = round(float(row["total_points"]), 2)

        if i > 0 and pts == result[i - 1]["points"]:
            rank = result[i - 1]["rank"]
        else:
            rank = i + 1

        result.append({
            "rank": rank,
            "name": row["name"],
            "user_id": uid,
            "points": pts,
            "balance": round(balances.get(uid, 0), 2),
        })

    return result


def _build_points_table(db):
    _, match_results = _calculate_balances(db)
    rows = db.execute(
        """
        SELECT cp.user_id, u.name, cp.match_id, cp.points, cp.last_updated
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE u.is_active = 1
        ORDER BY cp.match_id, cp.points DESC
        """
    ).fetchall()

    result = []
    for row in rows:
        entry = dict(row)
        uid = row["user_id"]
        mid = row["match_id"]
        entry["net"] = match_results.get(uid, {}).get(mid, 0)
        result.append(entry)
    return result


def _ensure_leaderboard_cache(db):
    has_live_matches = _has_live_matches(db)
    player_points_version = data_service.get_latest_player_points_update()
    cache_ready = LEADERBOARD_CACHE["leaderboard"] is not None and LEADERBOARD_CACHE["points_table"] is not None

    if has_live_matches and cache_ready:
        return

    if (
        not cache_ready
        or (not has_live_matches and LEADERBOARD_CACHE["player_points_version"] != player_points_version)
    ):
        LEADERBOARD_CACHE["leaderboard"] = _build_leaderboard(db)
        LEADERBOARD_CACHE["points_table"] = _build_points_table(db)
        LEADERBOARD_CACHE["player_points_version"] = player_points_version


@router.get("/leaderboard")
async def leaderboard(user: dict = Depends(get_current_user)):
    db = get_db()
    _ensure_leaderboard_cache(db)
    return LEADERBOARD_CACHE["leaderboard"] or []


@router.get("/points-table")
async def points_table(user: dict = Depends(get_current_user)):
    db = get_db()
    _ensure_leaderboard_cache(db)
    return LEADERBOARD_CACHE["points_table"] or []
