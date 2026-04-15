import copy

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import ESPN_MATCH_ID_OFFSET, ROLES, IST
from backend.models.match import Match, clean_team_name
from backend.models.registry import PlayerRegistry
from backend.services import data_service
from backend.services.scraper import get_cached_toss_info
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
                "opponent": match_row["team2"] if match_row["team1"] == team else match_row["team1"],
                "points": points_lookup.get((player_id, int(match_row["id"]))),
                "did_not_play": (player_id, int(match_row["id"])) not in points_lookup,
            }
            for match_row in recent_matches
        ]

    return history_by_player


def _is_lineup_window_open(match_date: str, match_time: str, toss_time: str | None = None) -> bool:
    try:
        match_datetime = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M")
        match_datetime = IST.localize(match_datetime)
    except Exception:
        return False

    if toss_time:
        try:
            window_start = IST.localize(datetime.strptime(f"{match_date} {toss_time}", "%Y-%m-%d %H:%M"))
        except Exception:
            window_start = match_datetime - timedelta(minutes=30)
    else:
        window_start = match_datetime - timedelta(minutes=30)

    now = datetime.now(IST)
    return window_start <= now < match_datetime

@router.get("/players")
async def list_players(
    match_id: Optional[int] = Query(None),
    user: dict = Depends(get_current_user),
):
    db = get_db()

    if match_id:
        cached_payload = data_service.get_cached_match_player_payload(match_id)
        if cached_payload is not None:
            players = [copy.deepcopy(player) for player in cached_payload["players"]]
            team1, team2 = cached_payload["match_teams"]
            match_date = cached_payload["match_date"]
            match_time = cached_payload["match_time"]
        else:
            # Get the match to find teams
            match = db.execute(
                "SELECT * FROM matches WHERE id = ?", (match_id,)
            ).fetchone()

            if not match:
                return {"error": "Match not found"}

            team1 = match["team1"]
            team2 = match["team2"]
            match_date = match["match_date"]
            match_time = match["match_time"]

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

            data_service.set_cached_match_player_payload(match_id, {
                "players": players,
                "match_teams": [team1, team2],
                "match_date": match_date,
                "match_time": match_time,
            })

            players = [copy.deepcopy(player) for player in players]

        playing_xi_data = {
            "announced": False,
            "url": "",
            "player_ids": [],
            "substitute_ids": [],
        }
        cached_playing_xi = data_service.get_cached_match_playing_xi(
            match_id,
            team1,
            team2,
            match_date,
            match_time,
        )
        if cached_playing_xi and cached_playing_xi.get("announced"):
            playing_xi_data = cached_playing_xi

        toss_info = get_cached_toss_info(match_id) or {"announced": False, "team": None, "decision": None, "text": "", "url": ""}
        lineup_window_open = _is_lineup_window_open(match_date, match_time)

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
                "playing_count": len(playing_ids),
                "substitute_count": len(substitute_ids),
            },
            "lineup_window_open": lineup_window_open,
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
