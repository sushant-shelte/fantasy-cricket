from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from collections import defaultdict

from backend.config import IST
from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.services import data_service

ENTRY_FEE = 50
PRIZE_SPLIT = [0.50, 0.30, 0.20]  # 1st, 2nd, 3rd
NON_PARTICIPANT_ADJUSTMENT = {
    "type": "percentage",  # "percentage" or "direct"
    "value": 15.0,
}

router = APIRouter(prefix="/api", tags=["leaderboard"])
LEADERBOARD_CACHE = {
    "leaderboard": None,
    "points_table": None,
    "player_points_version": "",
}


def invalidate_leaderboard_cache():
    LEADERBOARD_CACHE["leaderboard"] = None
    LEADERBOARD_CACHE["points_table"] = None
    LEADERBOARD_CACHE["player_points_version"] = ""


def _compute_non_participant_points(lowest_points: float) -> float:
    adjustment_type = NON_PARTICIPANT_ADJUSTMENT["type"]
    adjustment_value = float(NON_PARTICIPANT_ADJUSTMENT["value"])
    if adjustment_type == "direct":
        adjusted = lowest_points - adjustment_value
    else:
        adjusted = lowest_points - (lowest_points * adjustment_value / 100.0)
    return round(adjusted * 2) / 2


def _compute_match_contestant_points(db, match_id: int) -> list[dict]:
    team_rows = db.execute(
        """
        SELECT
            u.id AS user_id,
            u.name AS user_name,
            ut.player_id,
            ut.is_captain,
            ut.is_vice_captain,
            COALESCE(pp.points, 0) AS player_points
        FROM user_teams ut
        JOIN users u ON u.id = ut.user_id
        LEFT JOIN player_points pp ON pp.match_id = ut.match_id AND pp.player_id = ut.player_id
        WHERE ut.match_id = ?
          AND u.is_active = 1
        ORDER BY u.id
        """,
        (match_id,),
    ).fetchall()

    totals = {}
    for row in team_rows:
        user_id = row["user_id"]
        entry = totals.setdefault(
            user_id,
            {"user_id": user_id, "name": row["user_name"], "points": 0.0},
        )

        base_points = float(row["player_points"] or 0)
        if row["is_captain"]:
            base_points *= 2.0
        elif row["is_vice_captain"]:
            base_points *= 1.5

        entry["points"] += base_points

    result = list(totals.values())
    for row in result:
        row["points"] = round(row["points"], 2)
    result.sort(key=lambda item: (-item["points"], item["name"]))
    return result


def _get_completed_match_ids(db) -> list[int]:
    rows = db.execute("SELECT id, match_date, match_time FROM matches").fetchall()
    now = datetime.now(IST)
    completed_ids: list[int] = []

    for row in rows:
        try:
            match_datetime = datetime.strptime(
                f"{row['match_date']} {row['match_time']}", "%Y-%m-%d %H:%M"
            )
            match_datetime = IST.localize(match_datetime)
        except Exception:
            continue

        if now >= match_datetime + timedelta(hours=5):
            completed_ids.append(int(row["id"]))

    return completed_ids


def _load_effective_match_points(db) -> dict[int, list[dict]]:
    stored_rows = db.execute(
        """
        SELECT cp.user_id, u.name, cp.match_id, cp.points, cp.last_updated
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE u.is_active = 1
        ORDER BY cp.match_id, cp.points DESC
        """
    ).fetchall()

    matches = defaultdict(list)
    for row in stored_rows:
        matches[row["match_id"]].append({
            "user_id": row["user_id"],
            "name": row["name"],
            "points": round(float(row["points"]), 2),
            "last_updated": row["last_updated"],
        })

    match_ids = _get_completed_match_ids(db)
    active_users = db.execute(
        """
        SELECT id, name
        FROM users
        WHERE is_active = 1
        ORDER BY name
        """
    ).fetchall()
    active_user_map = {row["id"]: row["name"] for row in active_users}
    effective = {}

    for match_id in match_ids:
        contestants = matches.get(match_id, [])
        if contestants:
            has_nonzero = any(entry["points"] != 0 for entry in contestants)
            player_points_exist = db.execute(
                "SELECT 1 FROM player_points WHERE match_id = ? AND points <> 0 LIMIT 1",
                (match_id,),
            ).fetchone()
            if has_nonzero or not player_points_exist:
                effective[match_id] = contestants
                continue

        recomputed = _compute_match_contestant_points(db, match_id)
        effective[match_id] = recomputed

    for match_id, contestants in list(effective.items()):
        if not contestants:
            continue

        normalized = []
        for contestant in contestants:
            normalized.append({
                "user_id": contestant["user_id"],
                "name": contestant["name"],
                "points": round(float(contestant["points"]), 2),
                "last_updated": contestant.get("last_updated", ""),
                "adjusted": bool(contestant.get("adjusted", False)),
                "participated": bool(contestant.get("participated", True)),
            })

        participant_ids = {entry["user_id"] for entry in normalized if entry["participated"]}
        lowest_points = min(entry["points"] for entry in normalized if entry["participated"])
        adjusted_points = _compute_non_participant_points(lowest_points)

        for user_id, name in active_user_map.items():
            if user_id in participant_ids:
                continue
            normalized.append({
                "user_id": user_id,
                "name": name,
                "points": adjusted_points,
                "last_updated": "",
                "adjusted": True,
                "participated": False,
            })

        normalized.sort(key=lambda item: (-item["points"], item["name"]))
        effective[match_id] = normalized

    return effective


def _calculate_balances(db):
    """Calculate running balance for each user across all completed matches."""
    matches = defaultdict(list)
    for match_id, contestants in _load_effective_match_points(db).items():
        for contestant in contestants:
            if not contestant.get("participated", True):
                continue
            matches[match_id].append({
                "user_id": contestant["user_id"],
                "points": float(contestant["points"]),
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

def _build_leaderboard(db):
    balances, _ = _calculate_balances(db)
    effective_match_points = _load_effective_match_points(db)
    totals_by_user = defaultdict(float)
    for contestants in effective_match_points.values():
        for contestant in contestants:
            totals_by_user[contestant["user_id"]] += float(contestant["points"])

    users = db.execute(
        """
        SELECT u.id, u.name
        FROM users u
        WHERE u.is_active = 1
        ORDER BY u.name
        """
    ).fetchall()

    sorted_users = sorted(
        users,
        key=lambda row: (-round(float(totals_by_user.get(row["id"], 0)), 2), row["name"]),
    )

    result = []
    rank = 1
    for i, row in enumerate(sorted_users):
        uid = row["id"]
        pts = round(float(totals_by_user.get(uid, 0)), 2)

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
    result = []
    for match_id, contestants in _load_effective_match_points(db).items():
        sorted_contestants = sorted(contestants, key=lambda item: (-item["points"], item["name"]))
        for contestant in sorted_contestants:
            uid = contestant["user_id"]
            result.append({
                "user_id": uid,
                "name": contestant["name"],
                "match_id": match_id,
                "points": contestant["points"],
                "last_updated": contestant.get("last_updated", ""),
                "net": match_results.get(uid, {}).get(match_id, 0),
                "adjusted": contestant.get("adjusted", False),
                "participated": contestant.get("participated", True),
            })
    return result


def _ensure_leaderboard_cache(db):
    player_points_version = data_service.get_latest_player_points_update()
    cache_ready = LEADERBOARD_CACHE["leaderboard"] is not None and LEADERBOARD_CACHE["points_table"] is not None

    if (
        not cache_ready
        or LEADERBOARD_CACHE["player_points_version"] != player_points_version
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
