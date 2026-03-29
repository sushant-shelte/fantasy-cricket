import re
import requests
from bs4 import BeautifulSoup

from backend.config import ESPN_IPL_SERIES_ID, ESPN_IPL_SERIES_SLUG, ESPN_MATCH_ID_OFFSET, TEAM_MAP


def _session_get(url):
    session = requests.Session()
    session.trust_env = False
    return session.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )


def fetch_scorecard_html(scorecard_id):
    url = f"https://www.espn.in/cricket/series/8048/scorecard/{scorecard_id}/utils"
    try:
        res = _session_get(url)
        if res.status_code != 200:
            return None
        return res.text
    except Exception as e:
        print("Error fetching scorecard:", e)
        return None


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", value)


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _expand_team_name(team_name: str) -> str:
    reverse_team_map = {short: full for full, short in TEAM_MAP.items() if len(short) <= 4}
    return reverse_team_map.get(team_name, team_name)


def build_ipl_playing_xi_url(match_id: int, team1: str, team2: str) -> str:
    espn_match_id = int(match_id) + ESPN_MATCH_ID_OFFSET
    matchup_slug = f"{_slugify(_expand_team_name(team1))}-vs-{_slugify(_expand_team_name(team2))}"
    return (
        f"https://www.espncricinfo.com/series/{ESPN_IPL_SERIES_SLUG}-{ESPN_IPL_SERIES_ID}/"
        f"{matchup_slug}-{_ordinal(int(match_id))}-match-{espn_match_id}/match-playing-xi"
    )


def _normalize_player_name(name: str) -> str:
    name = re.sub(r"[\u2020\u2021*]", "", str(name))
    name = re.sub(r"\s*\((?:c|wk|sub)\)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    return " ".join(name.split()).strip()


def _build_team_player_lookup(players_rows: list[dict]) -> dict[str, dict[str, int]]:
    lookup: dict[str, dict[str, int]] = {}

    for player in players_rows:
        team = player["team"]
        team_lookup = lookup.setdefault(team, {})
        names = [player["name"]]
        aliases = (player.get("aliases") or "").split(",")
        names.extend(alias.strip() for alias in aliases if alias.strip())

        for raw_name in names:
            normalized = _normalize_player_name(raw_name)
            if normalized:
                team_lookup[normalized] = player["id"]

    return lookup


def _extract_playing_xi_from_text(html: str, team1: str, team2: str, players_rows: list[dict]) -> set[int]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    player_lookup = _build_team_player_lookup(players_rows)
    playing_ids: set[int] = set()

    expanded_team_names = {
        team1: {_normalize_player_name(team1), _normalize_player_name(_expand_team_name(team1))},
        team2: {_normalize_player_name(team2), _normalize_player_name(_expand_team_name(team2))},
    }

    def gather_from_section(team: str, start_idx: int) -> set[int]:
        ids: set[int] = set()
        next_team_markers = expanded_team_names[team1 if team == team2 else team2]

        for line in lines[start_idx + 1:start_idx + 40]:
            normalized_line = _normalize_player_name(line)
            if not normalized_line:
                continue
            if normalized_line in next_team_markers and ids:
                break

            player_id = player_lookup.get(team, {}).get(normalized_line)
            if player_id:
                ids.add(player_id)
                if len(ids) >= 11:
                    break

        return ids

    for team in (team1, team2):
        for idx, line in enumerate(lines):
            normalized_line = _normalize_player_name(line)
            if normalized_line in expanded_team_names[team]:
                section_ids = gather_from_section(team, idx)
                if len(section_ids) >= 9:
                    playing_ids.update(section_ids)
                    break

    return playing_ids


def fetch_playing_xi(match_id: int, team1: str, team2: str, players_rows: list[dict]) -> dict:
    url = build_ipl_playing_xi_url(match_id, team1, team2)

    try:
        res = _session_get(url)
        if res.status_code != 200:
            return {"announced": False, "url": url, "player_ids": []}

        playing_ids = _extract_playing_xi_from_text(res.text, team1, team2, players_rows)
        if len(playing_ids) < 18:
            return {"announced": False, "url": url, "player_ids": []}

        return {
            "announced": True,
            "url": url,
            "player_ids": sorted(playing_ids),
        }
    except Exception as e:
        print("Error fetching playing XI:", e)
        return {"announced": False, "url": url, "player_ids": []}
