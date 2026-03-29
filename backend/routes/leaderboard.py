from fastapi import APIRouter, Depends

from backend.middleware.auth import get_current_user
from backend.database import get_db

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard")
async def leaderboard(user: dict = Depends(get_current_user)):
    db = get_db()

    rows = db.execute(
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
    for i, row in enumerate(rows):
        result.append({
            "rank": i + 1,
            "name": row["name"],
            "user_id": row["id"],
            "points": round(float(row["total_points"]), 2),
        })

    return result


@router.get("/points-table")
async def points_table(user: dict = Depends(get_current_user)):
    db = get_db()

    rows = db.execute(
        """
        SELECT cp.user_id, u.name, cp.match_id, cp.points, cp.last_updated
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE u.is_active = 1
        ORDER BY cp.match_id, cp.points DESC
        """
    ).fetchall()

    return [dict(row) for row in rows]
