from fastapi import APIRouter, Depends, Query
from typing import Optional

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import ESPN_MATCH_ID_OFFSET, ROLES
from backend.models.match import Match, clean_team_name
from backend.models.registry import PlayerRegistry
from backend.services.scraper import build_cricbuzz_playing_xi_url, fetch_playing_xi, fetch_toss_info
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


def _load_recent_completed_history(db, teams: list[str], player_ids: list[int]) -> dict[int, list[dict]]:
    if not teams or not player_ids:
        return {}

    matches_rows = db.execute(
        f"""
        SELECT id, team1, team2
        FROM matches
        WHERE status = 'completed'
          AND (team1 IN ({",".join("?" * len(teams))}) OR team2 IN ({",".join("?" * len(teams))}))
        ORDER BY id DESC
        """,
        [*teams, *teams],
    ).fetchall()

    matches_by_team: dict[str, list[dict]] = {team: [] for team in teams}
    match_ids: list[int] = []
    for row in matches_rows:
        match_dict = dict(row)
        match_id = int(match_dict["id"])
        match_ids.append(match_id)
        for team in teams:
            if match_dict["team1"] == team or match_dict["team2"] == team:
                matches_by_team.setdefault(team, []).append(match_dict)

    points_lookup: dict[tuple[int, int], float] = {}
    if match_ids:
        point_rows = db.execute(
            f"""
            SELECT match_id, player_id, points
            FROM player_points
            WHERE player_id IN ({",".join("?" * len(player_ids))})
              AND match_id IN ({",".join("?" * len(match_ids))})
            """,
            [*player_ids, *match_ids],
        ).fetchall()
        for row in point_rows:
            points_lookup[(int(row["player_id"]), int(row["match_id"]))] = round(float(row["points"] or 0), 2)

    history_by_player: dict[int, list[dict]] = {}
    player_team_rows = db.execute(
        f"""
        SELECT id, team
        FROM players
        WHERE id IN ({",".join("?" * len(player_ids))})
        """,
        player_ids,
    ).fetchall()
    for row in player_team_rows:
        player_id = int(row["id"])
        team = row["team"]
        recent_matches = matches_by_team.get(team, [])
        history_by_player[player_id] = [
            {
                "match_id": int(match_row["id"]),
                "points": points_lookup.get((player_id, int(match_row["id"]))),
                "did_not_play": (player_id, int(match_row["id"])) not in points_lookup,
            }
            for match_row in recent_matches
        ]

    return history_by_player

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
                COALESCE(SUM(pp.points), 0) AS total_points,
                COUNT(pp.match_id) AS matches_played,
                CASE WHEN COUNT(pp.match_id) > 0
                     THEN ROUND(CAST(COALESCE(SUM(pp.points), 0) * 1.0 / COUNT(pp.match_id) AS numeric), 2)
                     ELSE 0 END AS avg_points
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

        # Fetch last match points per player in one query
        last_match_rows = db.execute(
            """
            SELECT pp.player_id, pp.points
            FROM player_points pp
            INNER JOIN (
                SELECT player_id, MAX(match_id) AS max_mid
                FROM player_points
                GROUP BY player_id
            ) latest ON pp.player_id = latest.player_id AND pp.match_id = latest.max_mid
            """
        ).fetchall()
        last_match_map = {r["player_id"]: round(float(r["points"]), 2) for r in last_match_rows}
        player_ids = [int(row["id"]) for row in rows]
        history_by_player = _load_recent_completed_history(db, [team1, team2], player_ids)

        players = []
        for row in rows:
            player = dict(row)
            player["total_points"] = round(float(player.get("total_points") or 0), 2)
            player["matches_played"] = int(player.get("matches_played") or 0)
            player["avg_points"] = round(float(player.get("avg_points") or 0), 2)
            player["last_match_points"] = last_match_map.get(player["id"])
            player["recent_history"] = history_by_player.get(player["id"], [])
            players.append(player)

        playing_xi_data = {
            "announced": False,
            "url": "",
            "player_ids": [],
            "substitute_ids": [],
        }
        playing_xi_data = fetch_playing_xi(
            match_id,
            team1,
            team2,
            players,
            match["match_date"],
            match["match_time"],
        )
        toss_info = fetch_toss_info(
            match_id,
            team1,
            team2,
            match["match_date"],
            match["match_time"],
        )

        playing_ids = set(playing_xi_data["player_ids"])
        substitute_ids = set(playing_xi_data.get("substitute_ids", []))
        playing_order = {player_id: index for index, player_id in enumerate(playing_xi_data["player_ids"])}
        substitute_order = {
            player_id: index for index, player_id in enumerate(playing_xi_data.get("substitute_ids", []))
        }
        playing_xi_known = len(playing_ids) == 22
        substitutes_known = len(substitute_ids) >= 10

        # Group by role
        grouped = {role: [] for role in ROLES}
        for player in players:
            if not playing_xi_data["announced"]:
                player["is_playing_xi"] = None
                player["is_substitute"] = None
                player["availability_status"] = None
                player["availability_order"] = None
            elif player["id"] in playing_ids:
                player["is_playing_xi"] = True
                player["is_substitute"] = False
                player["availability_status"] = "available"
                player["availability_order"] = playing_order.get(player["id"])
            elif substitutes_known and player["id"] in substitute_ids:
                player["is_playing_xi"] = False
                player["is_substitute"] = True
                player["availability_status"] = "substitute"
                player["availability_order"] = substitute_order.get(player["id"])
            elif playing_xi_known:
                player["is_playing_xi"] = False
                player["is_substitute"] = False
                player["availability_status"] = "unavailable"
                player["availability_order"] = None
            else:
                player["is_playing_xi"] = None
                player["is_substitute"] = None
                player["availability_status"] = None
                player["availability_order"] = None
            if player["role"] in grouped:
                grouped[player["role"]].append(player)

        return {
            "players": grouped,
            "match_teams": [team1, team2],
            "playing_xi": {
                "announced": playing_xi_data["announced"],
                "url": playing_xi_data["url"],
                "substitute_count": len(substitute_ids),
            },
            "toss": toss_info,
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
