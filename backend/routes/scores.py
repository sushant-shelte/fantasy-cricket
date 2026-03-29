from fastapi import APIRouter, Depends, HTTPException

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.models.match import Match, clean_team_name
from backend.models.registry import PlayerRegistry
from backend.services.scraper import fetch_playing_xi, fetch_scorecard_html
from backend.config import ESPN_MATCH_ID_OFFSET
from bs4 import BeautifulSoup

router = APIRouter(prefix="/api/scores", tags=["scores"])


def _build_registry(db):
    """Build a PlayerRegistry from the players table."""
    rows = db.execute("SELECT * FROM players").fetchall()
    players_data = []
    for row in rows:
        players_data.append({
            "PlayerID": row["id"],
            "Name": row["name"],
            "Team": row["team"],
            "Role": row["role"],
            "Aliases": row["aliases"] or "",
        })
    return PlayerRegistry(players_data), players_data


@router.get("/{match_id}")
async def match_scores(
    match_id: int,
    user: dict = Depends(get_current_user),
):
    db = get_db()

    # Get match info
    match_row = db.execute(
        "SELECT * FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not match_row:
        raise HTTPException(status_code=404, detail="Match not found")

    registry, players_data = _build_registry(db)

    match_obj = Match(
        str(match_id),
        clean_team_name(match_row["team1"]),
        clean_team_name(match_row["team2"]),
        registry,
    )

    scorecard_id = match_id + ESPN_MATCH_ID_OFFSET
    html_content = fetch_scorecard_html(scorecard_id)

    if not html_content:
        raise HTTPException(status_code=404, detail="No scorecard data available")

    soup = BeautifulSoup(html_content, "html.parser")
    match_obj.parse_scorecard(soup)

    players_rows = []
    for row in players_data:
        players_rows.append({
            "id": row["PlayerID"],
            "name": row["Name"],
            "team": row["Team"],
            "role": row["Role"],
            "aliases": row["Aliases"],
        })

    playing_xi = fetch_playing_xi(match_id, clean_team_name(match_row["team1"]), clean_team_name(match_row["team2"]), players_rows)
    for pid in playing_xi.get("player_ids", []):
        player = match_obj.get_or_create_player(int(pid))
        if player:
            player.team = registry.players.get(int(pid), {}).get("Team")
            player.played = True

    # Get stored player points for this match
    pp_rows = db.execute(
        "SELECT * FROM player_points WHERE match_id = ?", (match_id,)
    ).fetchall()
    pp_lookup = {}
    role_lookup = {}
    for row in pp_rows:
        pp_lookup[str(row["player_id"])] = float(row["points"])
        role_lookup[str(row["player_id"])] = row["role"]

    result = []
    for p in match_obj.players.values():
        pid_str = str(p.player_id)
        role = role_lookup.get(pid_str) or registry.players.get(p.player_id, {}).get("Role")
        calculated_points = p.calculate_player_points(role) if role else 0
        result.append({
            "name": p.name,
            "team": p.team,
            "role": role,
            "played": p.played,
            "is_out": p.is_out,
            "runs": p.runs,
            "balls": p.balls,
            "fours": p.fours,
            "sixes": p.sixes,
            "strike_rate": p.strike_rate,
            "overs": p.overs,
            "maidens": p.maidens,
            "runs_conceded": p.runs_conceded,
            "wickets": p.wickets,
            "bowled": p.bowled,
            "lbw": p.lbw,
            "economy": p.economy,
            "dot_balls": p.dot_balls,
            "catches": p.catches,
            "runout_direct": p.runout_direct,
            "stumpings": p.stumpings,
            "runout_indirect": p.runout_indirect,
            "points": calculated_points if calculated_points or p.played else pp_lookup.get(pid_str, 0),
            "breakdown": p.get_points_breakdown() if role else [],
        })

    result.sort(key=lambda x: x["points"], reverse=True)

    # Contestants for this match
    contestant_rows = db.execute(
        """
        SELECT u.name, cp.points
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE cp.match_id = ?
          AND u.is_active = 1
        ORDER BY cp.points DESC
        """,
        (match_id,),
    ).fetchall()

    contestants = [{"name": row["name"], "points": float(row["points"])} for row in contestant_rows]

    return {"players": result, "contestants": contestants}


@router.get("/{match_id}/my-team")
async def my_team_for_match(
    match_id: int,
    user: dict = Depends(get_current_user),
):
    db = get_db()

    rows = db.execute(
        """
        SELECT p.name
        FROM user_teams ut
        JOIN players p ON p.id = ut.player_id
        WHERE ut.user_id = ? AND ut.match_id = ?
        """,
        (user["id"], match_id),
    ).fetchall()

    return [row["name"] for row in rows]


@router.get("/{match_id}/team-breakdown")
async def team_breakdown(
    match_id: int,
    user_id: int = None,
    user: dict = Depends(get_current_user),
):
    """Get detailed breakdown of a user's team points for a match."""
    db = get_db()
    target_user_id = user_id or user["id"]

    # Get user's team
    team_rows = db.execute(
        """
        SELECT ut.player_id, ut.is_captain, ut.is_vice_captain,
               p.name, p.team, p.role
        FROM user_teams ut
        JOIN players p ON p.id = ut.player_id
        WHERE ut.user_id = ? AND ut.match_id = ?
        """,
        (target_user_id, match_id),
    ).fetchall()

    if not team_rows:
        return {"error": "No team found for this match"}

    # Get player points
    pp_rows = db.execute(
        "SELECT player_id, points FROM player_points WHERE match_id = ?",
        (match_id,),
    ).fetchall()
    pp_lookup = {row["player_id"]: float(row["points"]) for row in pp_rows}

    # Get user name
    target_user = db.execute("SELECT name FROM users WHERE id = ?", (target_user_id,)).fetchone()

    breakdown = []
    total = 0.0

    for row in team_rows:
        pid = row["player_id"]
        base_pts = pp_lookup.get(pid, 0)
        is_captain = bool(row["is_captain"])
        is_vc = bool(row["is_vice_captain"])

        if is_captain:
            multiplier = 2.0
            tag = "C"
        elif is_vc:
            multiplier = 1.5
            tag = "VC"
        else:
            multiplier = 1.0
            tag = ""

        adjusted = round(base_pts * multiplier, 2)
        total += adjusted

        breakdown.append({
            "name": row["name"],
            "team": row["team"],
            "role": row["role"],
            "base_points": base_pts,
            "multiplier": multiplier,
            "tag": tag,
            "adjusted_points": adjusted,
        })

    breakdown.sort(key=lambda x: x["adjusted_points"], reverse=True)

    return {
        "user_name": target_user["name"] if target_user else "Unknown",
        "total": round(total, 2),
        "players": breakdown,
    }


def _load_match_and_points(db, match_id):
    """Shared helper: fetch scorecard, parse, get player points."""
    match_row = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not match_row:
        return None, None, {}, {}

    registry, _ = _build_registry(db)
    match_obj = Match(
        str(match_id),
        clean_team_name(match_row["team1"]),
        clean_team_name(match_row["team2"]),
        registry,
    )

    scorecard_id = match_id + ESPN_MATCH_ID_OFFSET
    html_content = fetch_scorecard_html(scorecard_id)
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        match_obj.parse_scorecard(soup)

    pp_rows = db.execute("SELECT * FROM player_points WHERE match_id = ?", (match_id,)).fetchall()
    pp_lookup = {str(row["player_id"]): float(row["points"]) for row in pp_rows}
    role_lookup = {str(row["player_id"]): row["role"] for row in pp_rows}

    return match_row, match_obj, pp_lookup, role_lookup


def _build_team_snapshot(db, user_id, match_id, match_obj, pp_lookup, role_lookup):
    """Build a snapshot of a user's team with points and multipliers."""
    rows = db.execute(
        """
        SELECT ut.player_id, ut.is_captain, ut.is_vice_captain, p.name, p.team, p.role
        FROM user_teams ut
        JOIN players p ON p.id = ut.player_id
        WHERE ut.user_id = ? AND ut.match_id = ?
        """,
        (user_id, match_id),
    ).fetchall()

    entries = {}
    total = 0.0

    for row in rows:
        pid = row["player_id"]
        pid_str = str(pid)
        base_points = pp_lookup.get(pid_str, 0)

        is_captain = bool(row["is_captain"])
        is_vice_captain = bool(row["is_vice_captain"])

        if is_captain:
            multiplier = 2.0
            tag = "C"
        elif is_vice_captain:
            multiplier = 1.5
            tag = "VC"
        else:
            multiplier = 1.0
            tag = ""

        adjusted = round(base_points * multiplier, 2)
        total += adjusted

        entries[pid] = {
            "player_id": pid,
            "name": row["name"],
            "team": row["team"],
            "role": role_lookup.get(pid_str, row["role"]),
            "base_points": base_points,
            "multiplier": multiplier,
            "tag": tag,
            "adjusted_points": adjusted,
        }

    return entries, round(total, 2)


@router.get("/{match_id}/team-diff")
async def team_diff(
    match_id: int,
    other_user_id: int,
    user: dict = Depends(get_current_user),
):
    db = get_db()

    if user["id"] == other_user_id:
        return {"error": "Select another contestant to compare"}

    match_row, match_obj, pp_lookup, role_lookup = _load_match_and_points(db, match_id)
    if not match_row:
        return {"error": "Match not found"}

    # Get other user's name
    other_user = db.execute("SELECT * FROM users WHERE id = ?", (other_user_id,)).fetchone()
    if not other_user:
        return {"error": "Contestant not found"}
    if not other_user["is_active"]:
        return {"error": "Contestant is inactive"}

    my_entries, my_total = _build_team_snapshot(db, user["id"], match_id, match_obj, pp_lookup, role_lookup)
    other_entries, other_total = _build_team_snapshot(db, other_user_id, match_id, match_obj, pp_lookup, role_lookup)

    if not my_entries:
        return {"error": "You haven't picked a team for this match"}
    if not other_entries:
        return {"error": f"{other_user['name']} hasn't picked a team for this match"}

    my_ids = set(my_entries.keys())
    other_ids = set(other_entries.keys())

    # Players only in my team vs only in their team
    my_only = sorted(
        [my_entries[pid] for pid in my_ids - other_ids],
        key=lambda x: x["adjusted_points"], reverse=True,
    )
    other_only = sorted(
        [other_entries[pid] for pid in other_ids - my_ids],
        key=lambda x: x["adjusted_points"], reverse=True,
    )

    different_players_diff = round(
        sum(e["adjusted_points"] for e in other_only) - sum(e["adjusted_points"] for e in my_only), 2
    )

    # Common players with different roles (C/VC difference)
    common_role_diff = []
    common_same = []
    role_diff_total = 0.0

    for pid in sorted(my_ids & other_ids, key=lambda p: my_entries[p]["adjusted_points"], reverse=True):
        left = my_entries[pid]
        right = other_entries[pid]
        row = {"left": left, "right": right}

        if left["tag"] != right["tag"] or left["multiplier"] != right["multiplier"]:
            diff_points = round(right["adjusted_points"] - left["adjusted_points"], 2)
            row["diff_points"] = diff_points
            role_diff_total += diff_points
            common_role_diff.append(row)
        else:
            common_same.append(row)

    # Pair different players side by side
    max_len = max(len(my_only), len(other_only), 1)
    different_players = [
        {
            "left": my_only[i] if i < len(my_only) else None,
            "right": other_only[i] if i < len(other_only) else None,
        }
        for i in range(max_len)
    ]

    return {
        "current_user": user["name"],
        "other_user": other_user["name"],
        "my_total": my_total,
        "other_total": other_total,
        "total_diff": round(other_total - my_total, 2),
        "different_players_diff": different_players_diff,
        "different_players": different_players,
        "common_role_diff_total": round(role_diff_total, 2),
        "common_role_diff": common_role_diff,
        "common_players": common_same,
    }


@router.get("/{match_id}/contestants")
async def match_contestants(
    match_id: int,
    user: dict = Depends(get_current_user),
):
    """List contestants who picked teams for this match (for the diff dropdown)."""
    db = get_db()
    rows = db.execute(
        """
        SELECT DISTINCT u.id, u.name
        FROM user_teams ut
        JOIN users u ON u.id = ut.user_id
        WHERE ut.match_id = ?
          AND u.is_active = 1
        ORDER BY u.name
        """,
        (match_id,),
    ).fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]
