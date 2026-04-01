"""
SQLite-backed data service.

Replaces the old JSON-based data_service with queries against the SQLite
database defined in backend/database.py.  Every public function keeps the
same signature (or a compatible superset) so that tournament.py and all
route modules continue to work without changes.
"""

from __future__ import annotations

import threading
from datetime import datetime

from backend.database import get_db

# ---------------------------------------------------------------------------
# Lightweight in-process cache (mirrors the old JSON cache behaviour)
# ---------------------------------------------------------------------------

_lock = threading.Lock()

CACHE: dict = {
    "players": None,
    "users": None,
    "matches": None,
}


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else {}


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def invalidate_cache(*sheet_names: str):
    keys = sheet_names or tuple(CACHE.keys())
    with _lock:
        for key in keys:
            if key in CACHE:
                CACHE[key] = None


def prime_static_cache():
    """Warm static caches at startup so hot paths avoid repeated reloads."""
    get_cached_data("players")
    get_cached_data("users")
    get_cached_data("matches")


# ---------------------------------------------------------------------------
# Cached reads  – keys returned match what tournament.py / routes expect
# ---------------------------------------------------------------------------

def get_cached_data(sheet_name: str) -> list[dict]:
    """Return cached list-of-dicts for *players*, *users*, or *matches*.

    The dict keys deliberately match the old JSON field names so that every
    consumer (tournament.py, routes, templates) keeps working.
    """
    if sheet_name not in CACHE:
        return []

    with _lock:
        if CACHE[sheet_name] is None:
            if sheet_name == "players":
                CACHE[sheet_name] = _cached_players()
            elif sheet_name == "users":
                CACHE[sheet_name] = _cached_users()
            elif sheet_name == "matches":
                CACHE[sheet_name] = _cached_matches()
    return CACHE.get(sheet_name, [])


def _cached_players() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT id, name, team, role, aliases FROM players").fetchall()
    return [
        {
            "PlayerID": r["id"],
            "Name": r["name"],
            "Team": r["team"],
            "Role": r["role"],
            "Aliases": r["aliases"] or "",
        }
        for r in rows
    ]


def _cached_users() -> list[dict]:
    """Legacy-compatible user dicts (Mobile, Name, Password, Allowed)."""
    db = get_db()
    rows = db.execute(
        "SELECT id, firebase_uid, email, name, mobile, role, is_active FROM users"
    ).fetchall()
    return [
        {
            "Mobile": r["mobile"] or "",
            "Name": r["name"],
            "Password": "",          # Firebase handles auth – dummy value
            "Allowed": "true" if r["is_active"] else "false",
        }
        for r in rows
    ]


def _cached_matches() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT id, team1, team2, match_date, match_time, status FROM matches"
    ).fetchall()
    return [
        {
            "MatchID": r["id"],
            "Team1": r["team1"],
            "Team2": r["team2"],
            "Date": r["match_date"],
            "Time": r["match_time"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_users() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM users").fetchall()
    return _rows_to_dicts(rows)


def get_user_by_firebase_uid(uid: str) -> dict | None:
    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE firebase_uid = ?", (uid,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_user(
    firebase_uid: str,
    email: str,
    name: str,
    mobile: str | None = None,
    role: str = "user",
) -> dict:
    db = get_db()
    cur = db.execute(
        """INSERT INTO users (firebase_uid, email, name, mobile, role)
           VALUES (?, ?, ?, ?, ?)""",
        (firebase_uid, email, name, mobile, role),
    )
    db.commit()
    invalidate_cache("users")
    return get_user_by_id(cur.lastrowid)


def update_user(user_id: int, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    db = get_db()
    db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    db.commit()
    invalidate_cache("users")


def update_user_password(mobile: str, new_password: str) -> None:
    """Legacy compatibility stub.

    With Firebase auth the password is not stored locally.  This is kept so
    the old change-password route does not crash; it is effectively a no-op
    against the DB but invalidates the cache for consistency.
    """
    invalidate_cache("users")


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def get_players() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM players").fetchall()
    return _rows_to_dicts(rows)


def get_players_for_match(match_id) -> list[dict]:
    """Return players whose team participates in the given match."""
    db = get_db()
    match = db.execute(
        "SELECT team1, team2 FROM matches WHERE id = ?", (int(match_id),)
    ).fetchone()
    if not match:
        return []
    rows = db.execute(
        "SELECT * FROM players WHERE team IN (?, ?)",
        (match["team1"], match["team2"]),
    ).fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def get_matches() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM matches").fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Teams (user_teams)
# ---------------------------------------------------------------------------

def get_teams() -> list[dict]:
    """Return all user-team selections in the legacy format expected by
    ``tournament.initialize()`` and the routes.

    Keys: User, Mobile, MatchID, PlayerID, Name, Captain, ViceCaptain
    """
    return get_teams_for_matches()


def get_teams_for_matches(match_ids: list[int | str] | None = None) -> list[dict]:
    db = get_db()
    query = """
        SELECT
            u.id     AS user_id,
            u.name   AS user_name,
            u.mobile AS mobile,
            u.is_active AS user_is_active,
            ut.match_id,
            ut.player_id,
            p.name   AS player_name,
            ut.is_captain,
            ut.is_vice_captain
        FROM user_teams ut
        JOIN users   u ON u.id  = ut.user_id
        JOIN players p ON p.id  = ut.player_id
    """
    params: list[int] = []
    if match_ids:
        normalized_ids = [int(match_id) for match_id in match_ids]
        placeholders = ",".join("?" * len(normalized_ids))
        query += f" WHERE ut.match_id IN ({placeholders})"
        params.extend(normalized_ids)

    rows = db.execute(query, params).fetchall()

    return [
        {
            "UserID": r["user_id"],
            "User": r["user_name"],
            "Mobile": r["mobile"] or "",
            "IsActive": bool(r["user_is_active"]),
            "MatchID": str(r["match_id"]),
            "PlayerID": r["player_id"],
            "Name": r["player_name"],
            "Captain": "TRUE" if r["is_captain"] else "FALSE",
            "ViceCaptain": "TRUE" if r["is_vice_captain"] else "FALSE",
        }
        for r in rows
    ]


def get_user_team(user_id, match_id) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT ut.*, p.name AS player_name, p.team, p.role
        FROM user_teams ut
        JOIN players p ON p.id = ut.player_id
        WHERE ut.user_id = ? AND ut.match_id = ?
        """,
        (int(user_id), int(match_id)),
    ).fetchall()
    return _rows_to_dicts(rows)


def save_team(mobile, name, match_id, selected_players, captain, vice_captain, players_data=None):
    """Persist a user's team selection for a match.

    Signature kept compatible with the old JSON version called from
    ``routes/team.py``:
        save_team(mobile, name, match_id, selected_ids, captain, vice_captain, players_data)
    """
    db = get_db()

    # Resolve user_id from mobile
    user = db.execute(
        "SELECT id FROM users WHERE mobile = ?", (str(mobile),)
    ).fetchone()
    if not user:
        raise ValueError(f"No user found with mobile {mobile}")
    user_id = user["id"]

    mid = int(match_id)

    # Remove previous selections for this user + match
    db.execute(
        "DELETE FROM user_teams WHERE user_id = ? AND match_id = ?",
        (user_id, mid),
    )

    # Insert new selections
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for pid in selected_players:
        is_cap = 1 if str(pid) == str(captain) else 0
        is_vc = 1 if str(pid) == str(vice_captain) else 0
        db.execute(
            """INSERT INTO user_teams (user_id, match_id, player_id, is_captain, is_vice_captain, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, mid, int(pid), is_cap, is_vc, updated_at),
        )

    db.commit()


# ---------------------------------------------------------------------------
# Contestant Points
# ---------------------------------------------------------------------------

def get_contestant_points() -> list[dict]:
    """Return contestant points in the legacy format used by routes and
    tournament.py: User, Mobile, MatchID, Points, LastUpdated.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT
            u.id     AS user_id,
            u.name   AS user_name,
            u.mobile AS mobile,
            cp.match_id,
            cp.points,
            cp.last_updated
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        """
    ).fetchall()
    return [
        {
            "UserID": r["user_id"],
            "User": r["user_name"],
            "Mobile": r["mobile"] or "",
            "MatchID": str(r["match_id"]),
            "Points": r["points"],
            "LastUpdated": r["last_updated"],
        }
        for r in rows
    ]


def save_contestant_points(rows: list[dict]) -> None:
    """Persist contestant points.

    Each dict in *rows* is expected to have:
        User, Mobile, MatchID, Points, LastUpdated
    (produced by ``Tournament.persist_to_local``).
    """
    db = get_db()

    for row in rows:
        user_id = row.get("UserID")
        mobile = str(row.get("Mobile", ""))
        match_id = int(row["MatchID"])
        points = float(row["Points"])
        last_updated = row.get("LastUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        user = None
        if user_id is not None:
            user = db.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not user and mobile:
            user = db.execute(
                "SELECT id FROM users WHERE mobile = ?", (mobile,)
            ).fetchone()
        if not user:
            continue

        update_result = db.execute(
            """
            UPDATE contestant_points
            SET points = ?, last_updated = ?
            WHERE user_id = ? AND match_id = ?
            """,
            (points, last_updated, user["id"], match_id),
        )
        if getattr(update_result, "rowcount", None) == 0:
            db.execute(
                """
                INSERT INTO contestant_points (user_id, match_id, points, last_updated)
                VALUES (?, ?, ?, ?)
                """,
                (user["id"], match_id, points, last_updated),
            )

    db.commit()


def get_computed_match_ids() -> set[str]:
    db = get_db()
    rows = db.execute("SELECT DISTINCT match_id FROM player_points").fetchall()
    return {str(row["match_id"]) for row in rows}


def get_latest_player_points_update(match_id: int | None = None) -> str:
    db = get_db()
    if match_id is None:
        row = db.execute("SELECT COALESCE(MAX(last_updated), '') AS latest FROM player_points").fetchone()
    else:
        row = db.execute(
            "SELECT COALESCE(MAX(last_updated), '') AS latest FROM player_points WHERE match_id = ?",
            (int(match_id),),
        ).fetchone()
    return (row["latest"] if row else "") or ""


def delete_inactive_contestant_points() -> None:
    db = get_db()
    db.execute(
        """
        DELETE FROM contestant_points
        WHERE user_id IN (
            SELECT id FROM users WHERE is_active = 0
        )
        """
    )
    db.commit()


# ---------------------------------------------------------------------------
# Player Points
# ---------------------------------------------------------------------------

def get_player_points() -> list[dict]:
    """Return player points in the legacy format: MatchID, PlayerID,
    PlayerName, Team, Role, Points, LastUpdated.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM player_points").fetchall()
    return [
        {
            "MatchID": str(r["match_id"]),
            "PlayerID": r["player_id"],
            "PlayerName": r["player_name"],
            "Team": r["team"],
            "Role": r["role"],
            "Points": r["points"],
            "LastUpdated": r["last_updated"],
        }
        for r in rows
    ]


def save_player_points(rows: list[dict]) -> None:
    """Persist player points.

    Each dict in *rows* is expected to have:
        MatchID, PlayerID, PlayerName, Team, Role, Points, LastUpdated
    (produced by ``Tournament.persist_player_points_to_local``).
    """
    db = get_db()

    for row in rows:
        match_id = int(row["MatchID"])
        player_id = int(row["PlayerID"])
        player_name = row.get("PlayerName", "")
        team = row.get("Team", "")
        role = row.get("Role", "")
        points = float(row["Points"])
        last_updated = row.get("LastUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        update_result = db.execute(
            """
            UPDATE player_points
            SET player_name = ?, team = ?, role = ?, points = ?, last_updated = ?
            WHERE match_id = ? AND player_id = ?
            """,
            (player_name, team, role, points, last_updated, match_id, player_id),
        )
        if getattr(update_result, "rowcount", None) == 0:
            db.execute(
                """
                INSERT INTO player_points
                    (match_id, player_id, player_name, team, role, points, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (match_id, player_id, player_name, team, role, points, last_updated),
            )

    db.commit()
