from fastapi import APIRouter, Depends, Query
from typing import Optional

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import ROLES

router = APIRouter(prefix="/api", tags=["players"])


@router.get("/players")
async def list_players(
    match_id: Optional[int] = Query(None),
    user: dict = Depends(get_current_user),
):
    db = get_db()

    if match_id:
        # Get the match to find teams
        match = db.execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()

        if not match:
            return {"error": "Match not found"}

        team1 = match["team1"]
        team2 = match["team2"]

        rows = db.execute(
            """
            SELECT
                p.id,
                p.name,
                p.team,
                p.role,
                p.aliases,
                COALESCE(SUM(pp.points), 0) AS total_points
            FROM players p
            LEFT JOIN player_points pp ON pp.player_id = p.id
            WHERE p.team IN (?, ?)
            GROUP BY p.id, p.name, p.team, p.role, p.aliases
            ORDER BY
                CASE p.role
                    WHEN 'Wicketkeeper' THEN 1
                    WHEN 'Batter' THEN 2
                    WHEN 'AllRounder' THEN 3
                    WHEN 'Bowler' THEN 4
                    ELSE 5
                END,
                total_points DESC,
                p.name ASC
            """,
            (team1, team2),
        ).fetchall()

        # Group by role
        grouped = {role: [] for role in ROLES}
        for row in rows:
            player = dict(row)
            player["total_points"] = round(float(player.get("total_points") or 0), 2)
            if player["role"] in grouped:
                grouped[player["role"]].append(player)

        return grouped

    # Return all players
    rows = db.execute(
        """
        SELECT
            p.id,
            p.name,
            p.team,
            p.role,
            p.aliases,
            COALESCE(SUM(pp.points), 0) AS total_points
        FROM players p
        LEFT JOIN player_points pp ON pp.player_id = p.id
        GROUP BY p.id, p.name, p.team, p.role, p.aliases
        ORDER BY p.team, p.role, total_points DESC, p.name
        """
    ).fetchall()
    result = []
    for row in rows:
        player = dict(row)
        player["total_points"] = round(float(player.get("total_points") or 0), 2)
        result.append(player)
    return result
