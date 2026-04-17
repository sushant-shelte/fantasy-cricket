from __future__ import annotations


def append_missing_live_team_players(
    players: list[dict],
    registry,
    selected_rows: list[dict],
    owners_by_player: dict[int, list[dict]],
) -> int:
    existing_ids = {int(player["player_id"]) for player in players if player.get("player_id") is not None}
    appended = 0

    for row in selected_rows:
        pid = int(row["id"])
        if pid in existing_ids:
            continue

        registry_player = registry.players.get(pid, {}) if registry else {}
        role = row.get("role") or registry_player.get("Role")
        team = row.get("team") or registry_player.get("Team", "")
        name = row.get("name") or registry_player.get("Name", f"Player {pid}")
        players.append({
            "player_id": pid,
            "name": name,
            "team": team,
            "role": role,
            "played": False,
            "is_out": False,
            "runs": 0,
            "balls": 0,
            "fours": 0,
            "sixes": 0,
            "strike_rate": 0,
            "overs": 0,
            "maidens": 0,
            "runs_conceded": 0,
            "wickets": 0,
            "bowled": 0,
            "lbw": 0,
            "economy": 0,
            "dot_balls": 0,
            "catches": 0,
            "runout_direct": 0,
            "stumpings": 0,
            "runout_indirect": 0,
            "points": 0,
            "breakdown": [],
            "owners": owners_by_player.get(pid, []),
        })
        appended += 1

    return appended
