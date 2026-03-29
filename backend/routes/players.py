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
            "SELECT * FROM players WHERE team IN (?, ?) ORDER BY role, name",
            (team1, team2),
        ).fetchall()

        # Group by role
        grouped = {role: [] for role in ROLES}
        for row in rows:
            player = dict(row)
            if player["role"] in grouped:
                grouped[player["role"]].append(player)

        return grouped

    # Return all players
    rows = db.execute("SELECT * FROM players ORDER BY team, role, name").fetchall()
    return [dict(row) for row in rows]
