import json
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


def build_ipl_playing_xi_urls(match_id: int, team1: str, team2: str) -> list[str]:
    espn_match_id = int(match_id) + ESPN_MATCH_ID_OFFSET
    team1_slug = _slugify(_expand_team_name(team1))
    team2_slug = _slugify(_expand_team_name(team2))
    matchup_slug = f"{team1_slug}-vs-{team2_slug}"

    candidates = [
        build_ipl_playing_xi_url(match_id, team1, team2),
        f"https://www.espncricinfo.com/series/{ESPN_IPL_SERIES_SLUG}-{ESPN_IPL_SERIES_ID}/{matchup_slug}-match-{espn_match_id}/match-playing-xi",
        f"https://www.espncricinfo.com/series/{ESPN_IPL_SERIES_SLUG}-{ESPN_IPL_SERIES_ID}/{matchup_slug}-{espn_match_id}/match-playing-xi",
        f"https://www.espncricinfo.com/series/{ESPN_IPL_SERIES_SLUG}-{ESPN_IPL_SERIES_ID}/{matchup_slug}-{_ordinal(int(match_id))}-match-{espn_match_id}/live-cricket-score",
        f"https://www.espncricinfo.com/series/{ESPN_IPL_SERIES_SLUG}-{ESPN_IPL_SERIES_ID}/{matchup_slug}-match-{espn_match_id}/live-cricket-score",
    ]

    unique_candidates: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    return unique_candidates


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


def _extract_candidate_names_from_json(value, names: list[str]):
    if isinstance(value, dict):
        for key, item in value.items():
            key_normalized = str(key).lower()
            if key_normalized in {"name", "longname", "full_name", "fullname", "cardlongname"} and isinstance(item, str):
                names.append(item)
            else:
                _extract_candidate_names_from_json(item, names)
        return

    if isinstance(value, list):
        for item in value:
            _extract_candidate_names_from_json(item, names)


def _is_likely_player_name(name: str) -> bool:
    normalized = _normalize_player_name(name)
    if not normalized:
        return False
    parts = normalized.split()
    if len(parts) < 2 or len(parts) > 5:
        return False
    banned = {
        "playing xi", "squad", "impact subs", "impact players", "match details",
        "batting", "bowling", "fall of wickets", "toss", "live score", "scorecard",
    }
    return normalized not in banned


def _match_candidate_names(
    candidate_names: list[str],
    player_lookup: dict[str, dict[str, int]],
) -> tuple[set[int], list[str]]:
    playing_ids: set[int] = set()
    unmatched_names: list[str] = []
    seen_unmatched: set[str] = set()

    for raw_name in candidate_names:
        normalized = _normalize_player_name(raw_name)
        if not normalized:
            continue

        matched = False
        for team_lookup in player_lookup.values():
            player_id = team_lookup.get(normalized)
            if player_id:
                playing_ids.add(player_id)
                matched = True
                break

        if not matched and _is_likely_player_name(raw_name) and normalized not in seen_unmatched:
            seen_unmatched.add(normalized)
            unmatched_names.append(str(raw_name).strip())

    return playing_ids, unmatched_names


def _extract_playing_xi_from_json(html: str, players_rows: list[dict]) -> tuple[set[int], list[str]]:
    player_lookup = _build_team_player_lookup(players_rows)
    all_names: list[str] = []

    script_matches = re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>|<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    for match in script_matches:
        script_content = next((part for part in match if part), "")
        if not script_content:
            continue

        try:
            data = json.loads(script_content)
        except Exception:
            continue

        _extract_candidate_names_from_json(data, all_names)

    return _match_candidate_names(all_names, player_lookup)


def _extract_playing_xi_from_text(html: str, team1: str, team2: str, players_rows: list[dict]) -> tuple[set[int], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    player_lookup = _build_team_player_lookup(players_rows)
    playing_ids: set[int] = set()
    unmatched_names: list[str] = []
    unmatched_seen: set[str] = set()

    expanded_team_names = {
        team1: {_normalize_player_name(team1), _normalize_player_name(_expand_team_name(team1))},
        team2: {_normalize_player_name(team2), _normalize_player_name(_expand_team_name(team2))},
    }

    def gather_from_section(team: str, start_idx: int) -> tuple[set[int], list[str]]:
        ids: set[int] = set()
        unmatched: list[str] = []
        next_team_markers = expanded_team_names[team1 if team == team2 else team2]

        for line in lines[start_idx + 1:start_idx + 40]:
            normalized_line = _normalize_player_name(line)
            if not normalized_line:
                continue
            if normalized_line in next_team_markers and ids:
                break

            segments = re.split(r",|;|\u2022|\||\s{2,}", line)
            if len(segments) == 1:
                segments = [line]

            for segment in segments:
                segment = segment.strip()
                normalized_segment = _normalize_player_name(segment)
                if not normalized_segment:
                    continue

                player_id = player_lookup.get(team, {}).get(normalized_segment)
                if player_id:
                    ids.add(player_id)
                    if len(ids) >= 11:
                        break
                elif _is_likely_player_name(segment):
                    unmatched.append(segment)

            if len(ids) >= 11:
                break

        return ids, unmatched

    for team in (team1, team2):
        for idx, line in enumerate(lines):
            normalized_line = _normalize_player_name(line)
            if normalized_line in expanded_team_names[team]:
                section_ids, section_unmatched = gather_from_section(team, idx)
                if len(section_ids) >= 9:
                    playing_ids.update(section_ids)
                    for name in section_unmatched:
                        normalized_name = _normalize_player_name(name)
                        if normalized_name and normalized_name not in unmatched_seen:
                            unmatched_seen.add(normalized_name)
                            unmatched_names.append(name)
                    break

    return playing_ids, unmatched_names


def fetch_playing_xi(match_id: int, team1: str, team2: str, players_rows: list[dict]) -> dict:
    urls = build_ipl_playing_xi_urls(match_id, team1, team2)

    try:
        for url in urls:
            print(f"[Playing XI] Match {match_id}: trying {url}")
            res = _session_get(url)
            if res.status_code != 200:
                print(f"[Playing XI] Match {match_id}: status {res.status_code} for {url}")
                continue

            json_ids, json_unmatched = _extract_playing_xi_from_json(res.text, players_rows)
            text_ids, text_unmatched = _extract_playing_xi_from_text(res.text, team1, team2, players_rows)
            playing_ids = json_ids | text_ids
            unmatched_names = []
            seen_unmatched = set()
            for name in text_unmatched + json_unmatched:
                normalized = _normalize_player_name(name)
                if normalized and normalized not in seen_unmatched:
                    seen_unmatched.add(normalized)
                    unmatched_names.append(name)

            announced = (
                len(text_ids) >= 18
                or len(json_ids) >= 18
                or len(playing_ids) >= 18
                or "playing xi" in res.text.lower()
                or "match-playing-xi" in url.lower()
            )

            if not announced:
                continue

            print(
                f"[Playing XI] Match {match_id}: using {url} "
                f"(json={len(json_ids)}, text={len(text_ids)}, total={len(playing_ids)})"
            )
            for name in unmatched_names:
                print(f"[Playing XI] Match {match_id}: player mapping not found for '{name}'")

            return {
                "announced": True,
                "url": url,
                "player_ids": sorted(playing_ids),
            }

        print(f"[Playing XI] Match {match_id}: no announced XI found, first candidate was {urls[0]}")
        return {"announced": False, "url": urls[0], "player_ids": []}
    except Exception as e:
        print("Error fetching playing XI:", e)
        return {"announced": False, "url": urls[0], "player_ids": []}
