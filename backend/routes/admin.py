from collections import defaultdict
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, List, Optional, List

from backend.middleware.auth import require_admin
from backend.database import get_db
from backend.config import ROLES
from backend.services import data_service
from backend.config import IST
from backend.config import ROLES
from backend.services import data_service
from backend.routes.leaderboard import invalidate_leaderboard_cache

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Tournament reference - will be set from main.py
tournament_ref = None


def _now_str():
    from datetime import datetime
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def set_tournament(t):
    global tournament_ref
    tournament_ref = t


# --- User Management ---

class UpdateUserBody(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [dict(row) for row in rows]


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserBody,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    updates = []
    params = []

    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
        updates.append("role = ?")
        params.append(body.role)

    if body.is_active is not None:
        updates.append("is_active = ?")
        params.append(int(body.is_active))

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    data_service.invalidate_cache("users")

    updated = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(updated)


# --- Player Management ---

class CreatePlayerBody(BaseModel):
    name: str
    team: str
    role: str
    aliases: Optional[str] = ""


class UpdatePlayerBody(BaseModel):
    name: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    aliases: Optional[str] = None


@router.get("/players")
async def list_players(user: dict = Depends(require_admin)):
    db = get_db()
    rows = db.execute("SELECT * FROM players ORDER BY team, role, name").fetchall()
    return [dict(row) for row in rows]


@router.post("/players")
async def create_player(
    body: CreatePlayerBody,
    user: dict = Depends(require_admin),
):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO players (name, team, role, aliases) VALUES (?, ?, ?, ?)",
        (body.name, body.team, body.role, body.aliases or ""),
    )
    db.commit()
    data_service.invalidate_cache("players")

    player = db.execute(
        "SELECT * FROM players WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(player)


@router.put("/players/{player_id}")
async def update_player(
    player_id: int,
    body: UpdatePlayerBody,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Player not found")

    updates = []
    params = []

    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.team is not None:
        updates.append("team = ?")
        params.append(body.team)
    if body.role is not None:
        updates.append("role = ?")
        params.append(body.role)
    if body.aliases is not None:
        updates.append("aliases = ?")
        params.append(body.aliases)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(player_id)
    db.execute(f"UPDATE players SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    data_service.invalidate_cache("players")

    updated = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    return dict(updated)


@router.delete("/players/{player_id}")
async def delete_player(
    player_id: int,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Player not found")

    db.execute("DELETE FROM players WHERE id = ?", (player_id,))
    db.commit()
    data_service.invalidate_cache("players")

    return {"success": True}


# --- Match Management ---

class CreateMatchBody(BaseModel):
    team1: str
    team2: str
    match_date: str
    match_time: str


class UpdateMatchBody(BaseModel):
    team1: Optional[str] = None
    team2: Optional[str] = None
    match_date: Optional[str] = None
    match_time: Optional[str] = None
    status: Optional[str] = None


@router.get("/matches")
async def list_matches(user: dict = Depends(require_admin)):
    db = get_db()
    rows = db.execute("SELECT * FROM matches ORDER BY id").fetchall()
    return [dict(row) for row in rows]


@router.post("/matches")
async def create_match(
    body: CreateMatchBody,
    user: dict = Depends(require_admin),
):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO matches (team1, team2, match_date, match_time) VALUES (?, ?, ?, ?)",
        (body.team1, body.team2, body.match_date, body.match_time),
    )
    db.commit()
    data_service.invalidate_cache("matches")

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(match)


@router.put("/matches/{match_id}")
async def update_match(
    match_id: int,
    body: UpdateMatchBody,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Match not found")

    updates = []
    params = []

    if body.team1 is not None:
        updates.append("team1 = ?")
        params.append(body.team1)
    if body.team2 is not None:
        updates.append("team2 = ?")
        params.append(body.team2)
    if body.match_date is not None:
        updates.append("match_date = ?")
        params.append(body.match_date)
    if body.match_time is not None:
        updates.append("match_time = ?")
        params.append(body.match_time)
    if body.status is not None:
        updates.append("status = ?")
        params.append(body.status)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(match_id)
    db.execute(f"UPDATE matches SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    data_service.invalidate_cache("matches")

    updated = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    return dict(updated)


@router.delete("/matches/{match_id}")
async def delete_match(
    match_id: int,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Match not found")

    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()
    data_service.invalidate_cache("matches")

    return {"success": True}


# --- Score Recalculation ---

@router.post("/recalculate/{match_id}")
async def recalculate_match(
    match_id: int,
    user: dict = Depends(require_admin),
):
    if tournament_ref is None:
        raise HTTPException(status_code=500, detail="Tournament not initialized")

    db = get_db()
    match_row = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not match_row:
        raise HTTPException(status_code=404, detail="Match not found")

    match_id_str = str(match_id)

    tournament_ref.refresh_static_data(
        data_service.get_cached_data("players"),
        data_service.get_cached_data("matches"),
    )
    tournament_ref.ensure_match_teams_loaded([match_id_str], force=True)

    # Fetch and parse scorecard, compute points
    tournament_ref.update_match_data(match_id_str, use_playing_xi=True)
    tournament_ref.compute_player_points_for_match(match_id_str)
    tournament_ref.compute_points_for_match(match_id_str)
    tournament_ref.persist_player_points_to_local()
    tournament_ref.persist_to_local()
    invalidate_leaderboard_cache()

    return {"success": True, "message": f"Recalculated scores for match {match_id}"}


# --- View Submitted Teams ---

class AdminPlayerSelection(BaseModel):
    player_id: int
    is_captain: bool = False
    is_vice_captain: bool = False


class AdminUpdateTeamBody(BaseModel):
    user_id: int
    match_id: int
    players: List[AdminPlayerSelection]


def _validate_team_selection(db, match_id: int, selections: List[AdminPlayerSelection]):
    if len(selections) != 11:
        raise HTTPException(status_code=400, detail="Exactly 11 players required")

    captains = [p for p in selections if p.is_captain]
    vice_captains = [p for p in selections if p.is_vice_captain]

    if len(captains) != 1:
        raise HTTPException(status_code=400, detail="Exactly 1 captain required")
    if len(vice_captains) != 1:
        raise HTTPException(status_code=400, detail="Exactly 1 vice captain required")
    if captains[0].player_id == vice_captains[0].player_id:
        raise HTTPException(status_code=400, detail="Captain and Vice Captain cannot be the same player")

    player_ids = [p.player_id for p in selections]
    placeholders = ",".join("?" * len(player_ids))
    players = db.execute(
        f"""
        SELECT *
        FROM players
        WHERE id IN ({placeholders})
          AND team IN (
            SELECT team1 FROM matches WHERE id = ?
            UNION
            SELECT team2 FROM matches WHERE id = ?
          )
        """,
        [*player_ids, match_id, match_id],
    ).fetchall()

    if len(players) != 11:
        raise HTTPException(status_code=400, detail="Some selected players are invalid for this match")

    role_counts = {role: 0 for role in ROLES}
    for player in players:
        if player["role"] in role_counts:
            role_counts[player["role"]] += 1

    for role in ROLES:
        if role_counts[role] < 1:
            raise HTTPException(status_code=400, detail=f"At least 1 {role} required")


def _fetch_match_team_snapshots(db, match_id: int):
    rows = db.execute(
        """
        SELECT
            ut.user_id,
            u.name AS user_name,
            u.email AS user_email,
            u.mobile AS user_mobile,
            ut.player_id,
            p.name AS player_name,
            p.team,
            p.role,
            ut.is_captain,
            ut.is_vice_captain
        FROM user_teams ut
        JOIN users u ON u.id = ut.user_id
        JOIN players p ON p.id = ut.player_id
        WHERE ut.match_id = ?
        ORDER BY u.name, p.team, p.role, p.name
        """,
        (match_id,),
    ).fetchall()

    teams_by_user = {}
    for row in rows:
        uid = row["user_id"]
        if uid not in teams_by_user:
            teams_by_user[uid] = {
                "user_id": uid,
                "user_name": row["user_name"],
                "user_email": row["user_email"],
                "user_mobile": row["user_mobile"],
                "players": [],
                "team_counts": defaultdict(int),
            }
        teams_by_user[uid]["players"].append({
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "team": row["team"],
            "role": row["role"],
            "is_captain": bool(row["is_captain"]),
            "is_vice_captain": bool(row["is_vice_captain"]),
        })
        teams_by_user[uid]["team_counts"][row["team"]] += 1

    result = []
    for team in teams_by_user.values():
        team["team_counts"] = dict(team["team_counts"])
        team["captain_name"] = next((p["player_name"] for p in team["players"] if p["is_captain"]), None)
        team["vice_captain_name"] = next((p["player_name"] for p in team["players"] if p["is_vice_captain"]), None)
        result.append(team)

    return result


@router.get("/teams/matches")
async def team_matches(user: dict = Depends(require_admin)):
    db = get_db()
    rows = db.execute(
        """
        SELECT
            m.id,
            m.team1,
            m.team2,
            m.match_date,
            m.match_time,
            COUNT(DISTINCT ut.user_id) AS team_count
        FROM matches m
        LEFT JOIN user_teams ut ON ut.match_id = m.id
        GROUP BY m.id, m.team1, m.team2, m.match_date, m.match_time
        ORDER BY m.id
        """
    ).fetchall()
    return [dict(row) for row in rows]

@router.get("/teams")
async def view_teams(
    match_id: int = Query(...),
    user: dict = Depends(require_admin),
):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    return {
        "match": dict(match),
        "teams": _fetch_match_team_snapshots(db, match_id),
    }


@router.put("/teams")
async def update_team(
    body: AdminUpdateTeamBody,
    user: dict = Depends(require_admin),
):
    db = get_db()

    existing_user = db.execute("SELECT id FROM users WHERE id = ?", (body.user_id,)).fetchone()
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_match = db.execute("SELECT id FROM matches WHERE id = ?", (body.match_id,)).fetchone()
    if not existing_match:
        raise HTTPException(status_code=404, detail="Match not found")

    _validate_team_selection(db, body.match_id, body.players)

    db.execute(
        "DELETE FROM user_teams WHERE user_id = ? AND match_id = ?",
        (body.user_id, body.match_id),
    )

    updated_at = _now_str()
    for player in body.players:
        db.execute(
            """
            INSERT INTO user_teams (user_id, match_id, player_id, is_captain, is_vice_captain, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (body.user_id, body.match_id, player.player_id, int(player.is_captain), int(player.is_vice_captain), updated_at),
        )

    db.commit()

    return {
        "success": True,
        "teams": _fetch_match_team_snapshots(db, body.match_id),
    }


# --- Clear Table Data ---

CLEARABLE_TABLES = {
    "players": "DELETE FROM players",
    "matches": "DELETE FROM matches",
    "user_teams": "DELETE FROM user_teams",
    "contestant_points": "DELETE FROM contestant_points",
    "player_points": "DELETE FROM player_points",
}


@router.delete("/clear/{table_name}")
async def clear_table(
    table_name: str,
    user: dict = Depends(require_admin),
):
    if table_name not in CLEARABLE_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot clear '{table_name}'. Allowed: {', '.join(CLEARABLE_TABLES.keys())}",
        )

    db = get_db()

    # If clearing matches, also clear dependent data
    if table_name == "matches":
        db.execute("DELETE FROM user_teams")
        db.execute("DELETE FROM contestant_points")
        db.execute("DELETE FROM player_points")

    # If clearing players, also clear dependent data
    if table_name == "players":
        db.execute("DELETE FROM user_teams")
        db.execute("DELETE FROM contestant_points")
        db.execute("DELETE FROM player_points")

    db.execute(CLEARABLE_TABLES[table_name])
    db.commit()
    if table_name in {"players", "matches"}:
        data_service.invalidate_cache(table_name)

    return {"success": True, "message": f"Cleared all data from {table_name}"}


# --- Admin Submit Team on Behalf of User ---

class AdminTeamPlayer(BaseModel):
    player_id: int
    is_captain: bool = False
    is_vice_captain: bool = False


class AdminSubmitTeamBody(BaseModel):
    user_id: int
    match_id: int
    players: List[AdminTeamPlayer]


@router.post("/teams/submit")
async def admin_submit_team(body: AdminSubmitTeamBody, user: dict = Depends(require_admin)):
    db = get_db()
    # Delete old team
    db.execute("DELETE FROM user_teams WHERE user_id = ? AND match_id = ?", (body.user_id, body.match_id))
    # Insert new
    updated_at = _now_str()
    for p in body.players:
        db.execute(
            "INSERT INTO user_teams (user_id, match_id, player_id, is_captain, is_vice_captain, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (body.user_id, body.match_id, p.player_id, int(p.is_captain), int(p.is_vice_captain), updated_at),
        )
    db.commit()
    return {"success": True}
