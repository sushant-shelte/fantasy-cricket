from fastapi import APIRouter, Depends, Query
from typing import Optional

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import ESPN_MATCH_ID_OFFSET, ROLES
from backend.models.match import Match, clean_team_name
from backend.models.registry import PlayerRegistry
from backend.services.scraper import build_ipl_playing_xi_url, fetch_playing_xi, fetch_scorecard_html
from bs4 import BeautifulSoup

router = APIRouter(prefix="/api", tags=["players"])


def _build_registry(players_rows: list[dict]) -> PlayerRegistry:
    players_data = []
    for row in players_rows:
        players_data.append({
            "PlayerID": row["id"],
            "Name": row["name"],
            "Team": row["team"],
            "Role": row["role"],
            "Aliases": row.get("aliases") or "",
        })
    return PlayerRegistry(players_data)


def _fetch_playing_xi_from_scorecard(match_id: int, team1: str, team2: str, players_rows: list[dict]) -> set[int]:
    scorecard_id = match_id + ESPN_MATCH_ID_OFFSET
    html_content = fetch_scorecard_html(scorecard_id)
    if not html_content:
        return set()

    registry = _build_registry(players_rows)
    match_obj = Match(
        str(match_id),
        clean_team_name(team1),
        clean_team_name(team2),
        registry,
    )

    soup = BeautifulSoup(html_content, "html.parser")
    match_obj.parse_scorecard(soup)

    return {int(pid) for pid, player in match_obj.players.items() if getattr(player, "played", False)}

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
        playing_xi_data = fetch_playing_xi(match_id, team1, team2, players)

        if not playing_xi_data["announced"] or len(playing_xi_data["player_ids"]) < 18:
            scorecard_ids = _fetch_playing_xi_from_scorecard(match_id, team1, team2, players)
            if len(scorecard_ids) >= 18:
                playing_xi_data = {
                    "announced": True,
                    "url": playing_xi_data.get("url") or build_ipl_playing_xi_url(match_id, team1, team2),
                    "player_ids": sorted(scorecard_ids),
                }

        playing_ids = set(playing_xi_data["player_ids"])
        playing_ids_complete = len(playing_ids) >= 18

        # Group by role
        grouped = {role: [] for role in ROLES}
        for player in players:
            if not playing_xi_data["announced"]:
                player["is_playing_xi"] = None
            elif player["id"] in playing_ids:
                player["is_playing_xi"] = True
            elif playing_ids_complete:
                player["is_playing_xi"] = False
            else:
                player["is_playing_xi"] = None
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
