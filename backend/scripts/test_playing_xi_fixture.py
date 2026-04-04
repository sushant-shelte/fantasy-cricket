import argparse
from pathlib import Path

from backend.database import get_db
from backend.services.scraper import parse_playing_xi_from_sources


def _load_players_for_match(team1: str, team2: str) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT id, name, team, role, aliases
        FROM players
        WHERE team IN (?, ?)
        ORDER BY team, name
        """,
        (team1, team2),
    ).fetchall()
    return [dict(row) for row in rows]


def _find_fixture_file(base_dir: Path, match_id: str, suffix: str) -> Path | None:
    path = base_dir / f"{match_id}.{suffix}.html"
    return path if path.exists() else None


def _ids_to_names(players_rows: list[dict], player_ids: list[int]) -> list[str]:
    by_id = {int(row["id"]): row["name"] for row in players_rows}
    return [by_id.get(int(player_id), str(player_id)) for player_id in player_ids]


def main():
    parser = argparse.ArgumentParser(description="Run Playing XI parser against saved Cricbuzz HTML fixtures.")
    parser.add_argument("--match-id", required=True, help="Your internal match id / Cricbuzz fixture prefix")
    parser.add_argument("--team1", required=True, help="Short team name in DB, for example RR")
    parser.add_argument("--team2", required=True, help="Short team name in DB, for example GT")
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/playing_xi",
        help="Directory containing saved HTML fixtures",
    )
    parser.add_argument("--commentary-file", help="Optional explicit commentary HTML path")
    parser.add_argument("--squads-file", help="Optional explicit squads HTML path")
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures_dir)
    commentary_path = Path(args.commentary_file) if args.commentary_file else _find_fixture_file(fixtures_dir, args.match_id, "commentary")
    squads_path = Path(args.squads_file) if args.squads_file else _find_fixture_file(fixtures_dir, args.match_id, "squads")

    commentary_html = commentary_path.read_text(encoding="utf-8") if commentary_path and commentary_path.exists() else None
    squads_html = squads_path.read_text(encoding="utf-8") if squads_path and squads_path.exists() else None

    if not commentary_html and not squads_html:
        raise SystemExit("No fixture HTML found. Provide --commentary-file/--squads-file or save files in fixtures-dir.")

    players_rows = _load_players_for_match(args.team1, args.team2)
    parsed = parse_playing_xi_from_sources(
        commentary_html,
        squads_html,
        args.team1,
        args.team2,
        players_rows,
        commentary_url=str(commentary_path) if commentary_path else "",
        squads_url=str(squads_path) if squads_path else "",
    )

    all_team_players = {
        args.team1: [row for row in players_rows if row["team"] == args.team1],
        args.team2: [row for row in players_rows if row["team"] == args.team2],
    }
    playing_set = {int(player_id) for player_id in parsed["player_ids"]}
    substitute_set = {int(player_id) for player_id in parsed["substitute_ids"]}

    print(f"Source: {parsed['source'] or 'none'}")
    print(f"Announced: {parsed['announced']}")
    print(f"Finalized: {parsed['finalized']}")
    print(f"Playing XI count: {len(parsed['player_ids'])}")
    print(f"Substitute count: {len(parsed['substitute_ids'])}")

    for team in (args.team1, args.team2):
        team_player_rows = all_team_players[team]
        available = [row["name"] for row in team_player_rows if int(row["id"]) in playing_set]
        substitutes = [row["name"] for row in team_player_rows if int(row["id"]) in substitute_set]
        unavailable = [
            row["name"]
            for row in team_player_rows
            if int(row["id"]) not in playing_set and int(row["id"]) not in substitute_set
        ]
        print(f"\n{team} Playing XI ({len(available)}): {', '.join(available) if available else 'none'}")
        print(f"{team} Substitutes ({len(substitutes)}): {', '.join(substitutes) if substitutes else 'none'}")
        print(f"{team} Unavailable ({len(unavailable)}): {', '.join(unavailable) if unavailable else 'none'}")

    if parsed["unmatched_names"]:
        print(f"\nUnmatched Playing XI names: {', '.join(parsed['unmatched_names'])}")
    if parsed["substitute_unmatched_names"]:
        print(f"Unmatched substitute names: {', '.join(parsed['substitute_unmatched_names'])}")


if __name__ == "__main__":
    main()
