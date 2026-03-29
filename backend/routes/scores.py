from fastapi import APIRouter, Depends, HTTPException

from backend.middleware.auth import get_current_user
from backend.database import get_db
from backend.models.match import Match, clean_team_name
from backend.models.registry import PlayerRegistry
from backend.services.scraper import fetch_scorecard_html
from backend.config import MATCH_CODE_OFFSET
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

    match_code = match_id + MATCH_CODE_OFFSET
    html_content = fetch_scorecard_html(match_code)

    if not html_content:
        raise HTTPException(status_code=404, detail="No scorecard data available")

    soup = BeautifulSoup(html_content, "html.parser")
    match_obj.parse_scorecard(soup)

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
        result.append({
            "name": p.name,
            "team": p.team,
            "role": role_lookup.get(pid_str),
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
            "catches": p.catches,
            "runout_direct": p.runout_direct,
            "stumpings": p.stumpings,
            "runout_indirect": p.runout_indirect,
            "points": pp_lookup.get(pid_str, 0),
        })

    result.sort(key=lambda x: x["points"], reverse=True)

    # Contestants for this match
    contestant_rows = db.execute(
        """
        SELECT u.name, cp.points
        FROM contestant_points cp
        JOIN users u ON u.id = cp.user_id
        WHERE cp.match_id = ?
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
