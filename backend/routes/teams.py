from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List
from datetime import datetime

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.config import IST, ROLES
from backend.services.scraper import fetch_playing_xi

router = APIRouter(prefix="/api/teams", tags=["teams"])


class PlayerSelection(BaseModel):
    player_id: int
    is_captain: bool = False
    is_vice_captain: bool = False


class SubmitTeamBody(BaseModel):
    match_id: int
    players: List[PlayerSelection]


def get_now():
    return datetime.now(IST)


def get_now_str():
    return get_now().strftime("%Y-%m-%d %H:%M:%S")


def is_match_locked(match_date: str, match_time: str) -> bool:
    try:
        match_datetime = datetime.strptime(
            f"{match_date} {match_time}", "%Y-%m-%d %H:%M"
        )
        match_datetime = IST.localize(match_datetime)
    except Exception:
        return True
    return get_now() >= match_datetime


@router.get("/my")
async def my_team(
    match_id: int = Query(...),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    rows = db.execute(
        """
        SELECT ut.player_id, p.name AS player_name, p.team, p.role,
               ut.is_captain, ut.is_vice_captain
        FROM user_teams ut
        JOIN players p ON p.id = ut.player_id
        WHERE ut.user_id = ? AND ut.match_id = ?
        """,
        (user["id"], match_id),
    ).fetchall()

    return [dict(row) for row in rows]


@router.get("/my-matches")
async def my_team_matches(user: dict = Depends(get_current_user)):
    """Returns list of match IDs where user has picked a team."""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT match_id FROM user_teams WHERE user_id = ?",
        (user["id"],),
    ).fetchall()
    return [row["match_id"] for row in rows]


@router.get("/my-lineup-statuses")
async def my_lineup_statuses(
    match_ids: str = Query(...),
    user: dict = Depends(get_current_user),
):
    requested_ids = [int(match_id.strip()) for match_id in match_ids.split(",") if match_id.strip()]
    if not requested_ids:
        return {}

    db = get_db()
    placeholders = ",".join("?" * len(requested_ids))

    match_rows = db.execute(
        f"SELECT * FROM matches WHERE id IN ({placeholders})",
        requested_ids,
    ).fetchall()
    match_lookup = {row["id"]: dict(row) for row in match_rows}

    team_rows = db.execute(
        f"""
        SELECT match_id, player_id
        FROM user_teams
        WHERE user_id = ?
          AND match_id IN ({placeholders})
        """,
        [user["id"], *requested_ids],
    ).fetchall()

    selected_by_match = {}
    for row in team_rows:
        selected_by_match.setdefault(int(row["match_id"]), set()).add(int(row["player_id"]))

    result = {}
    for match_id in requested_ids:
        match = match_lookup.get(match_id)
        selected_ids = selected_by_match.get(match_id, set())
        if not match or not selected_ids:
            result[str(match_id)] = {
                "announced": False,
                "unannouncedSelected": 0,
                "substituteSelected": 0,
            }
            continue

        player_rows = db.execute(
            """
            SELECT id, name, team, role, aliases
            FROM players
            WHERE team IN (?, ?)
            """,
            (match["team1"], match["team2"]),
        ).fetchall()
        players = [dict(row) for row in player_rows]
        playing_xi = fetch_playing_xi(
            match_id,
            match["team1"],
            match["team2"],
            players,
            match["match_date"],
            match["match_time"],
        )

        playing_ids = set(playing_xi.get("player_ids", []))
        substitute_ids = set(playing_xi.get("substitute_ids", []))
        announced = bool(playing_xi.get("announced"))
        playing_ids_complete = len(playing_ids) == 22 and len(substitute_ids) >= 10

        unavailable_selected = 0
        substitute_selected = 0
        if announced and playing_ids_complete:
            unavailable_selected = len([player_id for player_id in selected_ids if player_id not in playing_ids and player_id not in substitute_ids])
            substitute_selected = len([player_id for player_id in selected_ids if player_id in substitute_ids])

        result[str(match_id)] = {
            "announced": announced,
            "unannouncedSelected": unavailable_selected,
            "substituteSelected": substitute_selected,
        }

    return result


@router.post("")
async def submit_team(
    body: SubmitTeamBody,
    user: dict = Depends(get_current_user),
):
    db = get_db()

    # Get match
    match = db.execute(
        "SELECT * FROM matches WHERE id = ?", (body.match_id,)
    ).fetchone()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Check lock
    if is_match_locked(match["match_date"], match["match_time"]):
        raise HTTPException(status_code=400, detail="Match is locked, team submission closed")

    # Validate 11 players
    if len(body.players) != 11:
        raise HTTPException(status_code=400, detail="Exactly 11 players required")

    # Validate captain and vice captain
    captains = [p for p in body.players if p.is_captain]
    vice_captains = [p for p in body.players if p.is_vice_captain]

    if len(captains) != 1:
        raise HTTPException(status_code=400, detail="Exactly 1 captain required")
    if len(vice_captains) != 1:
        raise HTTPException(status_code=400, detail="Exactly 1 vice captain required")
    if captains[0].player_id == vice_captains[0].player_id:
        raise HTTPException(status_code=400, detail="Captain and Vice Captain cannot be the same player")

    # Validate at least 1 player per role
    player_ids = [p.player_id for p in body.players]
    players_db = db.execute(
        f"SELECT * FROM players WHERE id IN ({','.join('?' * len(player_ids))})",
        player_ids,
    ).fetchall()

    if len(players_db) != 11:
        raise HTTPException(status_code=400, detail="Some player IDs are invalid")

    role_counts = {role: 0 for role in ROLES}
    for p in players_db:
        if p["role"] in role_counts:
            role_counts[p["role"]] += 1

    for role in ROLES:
        if role_counts[role] < 1:
            raise HTTPException(status_code=400, detail=f"At least 1 {role} required")

    # Delete old team for this user + match
    db.execute(
        "DELETE FROM user_teams WHERE user_id = ? AND match_id = ?",
        (user["id"], body.match_id),
    )

    # Insert new team
    updated_at = get_now_str()
    for p in body.players:
        db.execute(
            "INSERT INTO user_teams (user_id, match_id, player_id, is_captain, is_vice_captain, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], body.match_id, p.player_id, int(p.is_captain), int(p.is_vice_captain), updated_at),
        )

    db.commit()

    return {"success": True}


@router.get("/contestants")
async def match_contestants_with_updates(
    match_id: int = Query(...),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    rows = db.execute(
        """
        SELECT
            u.id AS user_id,
            u.name,
            MAX(COALESCE(ut.updated_at, '')) AS last_team_updated
        FROM user_teams ut
        JOIN users u ON u.id = ut.user_id
        WHERE ut.match_id = ?
          AND u.is_active = 1
        GROUP BY u.id, u.name
        ORDER BY last_team_updated DESC, u.name ASC
        """,
        (match_id,),
    ).fetchall()

    return [
        {
            "user_id": row["user_id"],
            "name": row["name"],
            "last_team_updated": row["last_team_updated"] or None,
        }
        for row in rows
    ]
