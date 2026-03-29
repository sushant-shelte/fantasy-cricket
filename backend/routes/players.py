from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from typing import Optional

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import IST, ROLES
from backend.services.scraper import build_ipl_playing_xi_url, fetch_playing_xi

router = APIRouter(prefix="/api", tags=["players"])


def _should_fetch_playing_xi(match_date: str, match_time: str) -> bool:
    try:
        match_datetime = IST.localize(datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M"))
    except Exception:
        return False

    now = datetime.now(IST)
    return now >= match_datetime - timedelta(minutes=30)


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

        players = []
        for row in rows:
            player = dict(row)
            player["total_points"] = round(float(player.get("total_points") or 0), 2)
            players.append(player)

        playing_xi_data = {
            "announced": False,
            "url": build_ipl_playing_xi_url(match_id, team1, team2),
            "player_ids": [],
        }
        if _should_fetch_playing_xi(match["match_date"], match["match_time"]):
            playing_xi_data = fetch_playing_xi(match_id, team1, team2, players)

        playing_ids = set(playing_xi_data["player_ids"])

        # Group by role
        grouped = {role: [] for role in ROLES}
        for player in players:
            player["is_playing_xi"] = player["id"] in playing_ids if playing_xi_data["announced"] else None
            if player["role"] in grouped:
                grouped[player["role"]].append(player)

        return {
            "players": grouped,
            "playing_xi": {
                "announced": playing_xi_data["announced"],
                "url": playing_xi_data["url"],
            },
        }

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
