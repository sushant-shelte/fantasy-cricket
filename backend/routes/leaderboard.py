from fastapi import APIRouter, Depends
from collections import defaultdict

from backend.middleware.auth import get_current_user
from backend.database import get_db

ENTRY_FEE = 50
PRIZE_SPLIT = [0.50, 0.30, 0.20]  # 1st, 2nd, 3rd

router = APIRouter(prefix="/api", tags=["leaderboard"])


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


@router.get("/leaderboard")
async def leaderboard(user: dict = Depends(get_current_user)):
    db = get_db()

    balances, _ = _calculate_balances(db)

    # Get all active users
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

        # Tied rank
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


@router.get("/points-table")
async def points_table(user: dict = Depends(get_current_user)):
    db = get_db()

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
