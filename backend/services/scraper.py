import json
import re
import requests
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

from backend.config import (
    CRICBUZZ_IPL_SERIES_ID,
    CRICBUZZ_IPL_SERIES_SLUG,
    ESPN_IPL_SERIES_ID,
    ESPN_IPL_SERIES_SLUG,
    ESPN_MATCH_ID_OFFSET,
    TEAM_MAP,
)
from backend.models.registry import PlayerRegistry


CRICBUZZ_MATCH_ID_MAP: dict[int, int] = {}


def _session_get(url):
    session = requests.Session()
    session.trust_env = False
    return session.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Referer": "https://www.espncricinfo.com/",
            "Connection": "keep-alive",
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


def build_cricbuzz_schedule_url() -> str:
    return f"https://www.cricbuzz.com/cricket-series/{CRICBUZZ_IPL_SERIES_ID}/{CRICBUZZ_IPL_SERIES_SLUG}/matches"


def build_cricbuzz_playing_xi_url(cricbuzz_match_id: int) -> str:
    return f"https://www.cricbuzz.com/cricket-match-squads/{cricbuzz_match_id}"


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
    reverse_team_map = {
        short: full
        for full, short in TEAM_MAP.items()
        if len(short) <= 4 and full != short
    }
    return reverse_team_map.get(team_name, team_name)


def _to_short_team_name(team_name: str) -> str:
    return TEAM_MAP.get(team_name, team_name)


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


def initialize_cricbuzz_match_map(matches_data: list[dict]) -> dict[int, int]:
    global CRICBUZZ_MATCH_ID_MAP

    schedule_url = build_cricbuzz_schedule_url()
    print(f"[Cricbuzz] Loading schedule mapping from {schedule_url}")

    try:
        res = _session_get(schedule_url)
        if res.status_code != 200:
            print(f"[Cricbuzz] Schedule fetch failed with status {res.status_code}")
            CRICBUZZ_MATCH_ID_MAP = {}
            return CRICBUZZ_MATCH_ID_MAP

        soup = BeautifulSoup(res.text, "html.parser")
        schedule_lookup: dict[tuple[int, frozenset[str]], int] = {}

        for anchor in soup.find_all("a", href=True, title=True):
            href = anchor.get("href", "")
            title = anchor.get("title", "")
            match_id_match = re.search(r"/live-cricket-scores/(\d+)", href)
            title_match = re.match(r"(.+?) vs (.+?), (\d+)(?:st|nd|rd|th) Match\b", title)
            if not match_id_match or not title_match:
                continue

            team_a = _to_short_team_name(title_match.group(1).strip())
            team_b = _to_short_team_name(title_match.group(2).strip())
            match_no = int(title_match.group(3))
            cricbuzz_match_id = int(match_id_match.group(1))
            schedule_lookup[(match_no, frozenset({team_a, team_b}))] = cricbuzz_match_id

        mapping: dict[int, int] = {}
        for match in matches_data:
            our_match_id = int(match["MatchID"])
            key = (
                our_match_id,
                frozenset({
                    _to_short_team_name(match["Team1"]),
                    _to_short_team_name(match["Team2"]),
                }),
            )
            cricbuzz_match_id = schedule_lookup.get(key)
            if cricbuzz_match_id:
                mapping[our_match_id] = cricbuzz_match_id

        CRICBUZZ_MATCH_ID_MAP = mapping
        print(f"[Cricbuzz] Cached {len(CRICBUZZ_MATCH_ID_MAP)} match id mappings")
        return CRICBUZZ_MATCH_ID_MAP
    except Exception as e:
        print(f"[Cricbuzz] Error loading schedule mapping: {e}")
        CRICBUZZ_MATCH_ID_MAP = {}
        return CRICBUZZ_MATCH_ID_MAP


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


def _extract_team_names_from_column(column) -> list[str]:
    names: list[str] = []
    for row in column.find_all("a", href=True, recursive=False):
        spans = row.find_all("span")
        for span in spans:
            text = span.get_text(" ", strip=True)
            if not text or text.startswith("("):
                continue
            names.append(text)
            break
    return names


def _build_registry_from_players_rows(players_rows: list[dict]) -> PlayerRegistry:
    players_data = []
    for row in players_rows:
        players_data.append({
            "PlayerID": row["id"],
            "Name": row["name"],
            "Team": row["team"],
            "Role": row.get("role", ""),
            "Aliases": row.get("aliases") or "",
        })
    return PlayerRegistry(players_data)


def _find_registry_player_id_silent(registry: PlayerRegistry, raw_name: str, team: str) -> int | None:
    normalized_name = registry.normalize(raw_name)

    if (team, normalized_name) in registry.lookup:
        return registry.lookup[(team, normalized_name)]

    parts = normalized_name.split()
    if len(parts) > 1:
        first_name_matches = registry.first_name_lookup.get((team, parts[0]), set())
        last_name_matches = registry.last_name_lookup.get((team, parts[-1]), set())
        combined_matches = first_name_matches & last_name_matches
        if len(combined_matches) == 1:
            return next(iter(combined_matches))
    elif len(parts) == 1:
        first_name_matches = registry.first_name_lookup.get((team, parts[0]), set())
        if len(first_name_matches) == 1:
            return next(iter(first_name_matches))

        last_name_matches = registry.last_name_lookup.get((team, parts[0]), set())
        if len(last_name_matches) == 1:
            return next(iter(last_name_matches))

    initials, surname = registry._extract_initials_and_surname(normalized_name)
    if surname:
        surname_matches = registry.last_name_lookup.get((team, surname), set())
        if len(surname_matches) == 1:
            return next(iter(surname_matches))

        if initials:
            first_initial = initials[0]
            matching_candidates = []
            for pid in surname_matches:
                player_name = registry.normalize(registry.players.get(pid, {}).get("Name", ""))
                if not player_name:
                    continue
                player_parts = player_name.split()
                if player_parts and player_parts[0].startswith(first_initial):
                    matching_candidates.append(pid)

            if len(matching_candidates) == 1:
                return matching_candidates[0]

    return None


def _find_close_team_player_id(raw_name: str, team: str, players_rows: list[dict]) -> int | None:
    normalized_target = _normalize_player_name(raw_name)
    if not normalized_target:
        return None

    best_player_id = None
    best_score = 0.0
    tie = False

    for row in players_rows:
        if row["team"] != team:
            continue

        candidate_names = [row["name"]]
        aliases = (row.get("aliases") or "").split(",")
        candidate_names.extend(alias.strip() for alias in aliases if alias.strip())

        candidate_score = 0.0
        for candidate in candidate_names:
            normalized_candidate = _normalize_player_name(candidate)
            if not normalized_candidate:
                continue
            score = SequenceMatcher(None, normalized_target, normalized_candidate).ratio()
            candidate_score = max(candidate_score, score)

        if candidate_score > best_score:
            best_score = candidate_score
            best_player_id = row["id"]
            tie = False
        elif candidate_score == best_score and candidate_score > 0:
            tie = True

    if best_player_id and best_score >= 0.88 and not tie:
        return int(best_player_id)
    return None


def _extract_playing_xi_from_cricbuzz_page(
    html: str,
    team1: str,
    team2: str,
    players_rows: list[dict],
) -> tuple[set[int], list[str], bool]:
    soup = BeautifulSoup(html, "html.parser")
    heading = None
    for tag in soup.find_all(["h1", "h2", "h3"]):
        if _normalize_player_name(tag.get_text(" ", strip=True)) == "playing xi":
            heading = tag
            break

    if not heading:
        return set(), [], False

    container = heading.find_next(
        lambda tag: (
            tag.name == "div"
            and len([
                child for child in tag.find_all("div", recursive=False)
                if "w-1/2" in " ".join(child.get("class", []))
            ]) >= 2
        )
    )
    if not container:
        return set(), [], True

    columns = [
        child for child in container.find_all("div", recursive=False)
        if "w-1/2" in " ".join(child.get("class", []))
    ][:2]
    if len(columns) < 2:
        return set(), [], True

    registry = _build_registry_from_players_rows(players_rows)
    playing_ids: set[int] = set()
    unmatched_names: list[str] = []
    seen_unmatched: set[str] = set()

    for team, column in zip((team1, team2), columns):
        for raw_name in _extract_team_names_from_column(column):
            normalized = _normalize_player_name(raw_name)
            if not normalized:
                continue
            player_id = _find_registry_player_id_silent(registry, raw_name, team)
            if not player_id:
                player_id = _find_close_team_player_id(raw_name, team, players_rows)
            if player_id:
                playing_ids.add(player_id)
            elif normalized not in seen_unmatched:
                seen_unmatched.add(normalized)
                unmatched_names.append(raw_name)

    return playing_ids, unmatched_names, True


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
    cricbuzz_match_id = CRICBUZZ_MATCH_ID_MAP.get(int(match_id))
    if not cricbuzz_match_id:
        print(f"[Playing XI] Match {match_id}: no cached Cricbuzz match id found")
        return {"announced": False, "url": "", "player_ids": []}

    url = build_cricbuzz_playing_xi_url(cricbuzz_match_id)

    try:
        print(f"[Playing XI] Match {match_id}: trying {url}")
        res = _session_get(url)
        if res.status_code != 200:
            print(f"[Playing XI] Match {match_id}: status {res.status_code} for {url}")
            return {"announced": False, "url": url, "player_ids": []}

        playing_ids, unmatched_names, announced = _extract_playing_xi_from_cricbuzz_page(
            res.text, team1, team2, players_rows
        )
        if not announced:
            print(f"[Playing XI] Match {match_id}: Playing XI section not available yet at {url}")
            return {"announced": False, "url": url, "player_ids": []}

        print(f"[Playing XI] Match {match_id}: using {url} (total={len(playing_ids)})")
        for name in unmatched_names:
            print(f"[Playing XI] Match {match_id}: player mapping not found for '{name}'")

        return {
            "announced": len(playing_ids) >= 18,
            "url": url,
            "player_ids": sorted(playing_ids),
        }
    except Exception as e:
        print("Error fetching playing XI:", e)
        return {"announced": False, "url": url, "player_ids": []}
