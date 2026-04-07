import json
import re
import time
from datetime import datetime, timedelta
import requests
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

from backend.config import (
    CRICBUZZ_IPL_SERIES_ID,
    CRICBUZZ_IPL_SERIES_SLUG,
    ESPN_IPL_SERIES_ID,
    ESPN_IPL_SERIES_SLUG,
    ESPN_MATCH_ID_OFFSET,
    IST,
    TEAM_MAP,
)
from backend.models.registry import PlayerRegistry


CRICBUZZ_MATCH_ID_MAP: dict[int, int] = {}
PLAYING_XI_CACHE: dict[int, dict] = {}
PLAYING_XI_TTL_SECONDS = 60
TOSS_INFO_CACHE: dict[int, dict] = {}
TOSS_INFO_TTL_SECONDS = 60


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


def _copy_playing_xi_payload(payload: dict) -> dict:
    return {
        "announced": bool(payload.get("announced")),
        "url": payload.get("url", ""),
        "player_ids": list(payload.get("player_ids", [])),
        "substitute_ids": list(payload.get("substitute_ids", [])),
    }


def _copy_toss_payload(payload: dict) -> dict:
    return {
        "announced": bool(payload.get("announced")),
        "team": payload.get("team"),
        "decision": payload.get("decision"),
        "text": payload.get("text", ""),
        "url": payload.get("url", ""),
    }


def _is_finalized_playing_xi(payload: dict) -> bool:
    return len(payload.get("player_ids", [])) == 22 and len(payload.get("substitute_ids", [])) >= 10


def _is_playing_xi_announced(payload: dict) -> bool:
    return len(payload.get("player_ids", [])) == 22


def _should_attempt_playing_xi_fetch(match_date: str | None, match_time: str | None) -> bool:
    if not match_date or not match_time:
        return True

    try:
        match_start = IST.localize(datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M"))
    except Exception:
        return True

    return datetime.now(IST) >= (match_start - timedelta(minutes=30))


def should_attempt_toss_fetch(match_date: str | None, match_time: str | None) -> bool:
    if not match_date or not match_time:
        return False

    try:
        match_start = IST.localize(datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M"))
    except Exception:
        return False

    now = datetime.now(IST)
    return (match_start - timedelta(minutes=30)) <= now < match_start


def _is_before_match_start(match_date: str | None, match_time: str | None) -> bool:
    if not match_date or not match_time:
        return False

    try:
        match_start = IST.localize(datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M"))
    except Exception:
        return False

    return datetime.now(IST) < match_start


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


def fetch_cricbuzz_scorecard_html(match_id: int, team1: str | None = None, team2: str | None = None):
    if team1 and team2:
        cricbuzz_match_id = resolve_cricbuzz_match_id(int(match_id), team1, team2)
    else:
        cricbuzz_match_id = CRICBUZZ_MATCH_ID_MAP.get(int(match_id))
    if not cricbuzz_match_id:
        print(f"[Cricbuzz Scorecard] Match {match_id}: no cached Cricbuzz match id found")
        return None

    url = f"https://www.cricbuzz.com/live-cricket-scorecard/{cricbuzz_match_id}"
    try:
        res = _session_get(url)
        if res.status_code != 200:
            print(f"[Cricbuzz Scorecard] Match {match_id}: status {res.status_code} for {url}")
            return None
        return res.text
    except Exception as e:
        print(f"[Cricbuzz Scorecard] Match {match_id}: error fetching {url}: {e}")
        return None


def build_cricbuzz_schedule_url() -> str:
    return f"https://www.cricbuzz.com/cricket-series/{CRICBUZZ_IPL_SERIES_ID}/{CRICBUZZ_IPL_SERIES_SLUG}/matches"


def build_cricbuzz_playing_xi_url(cricbuzz_match_id: int) -> str:
    return f"https://www.cricbuzz.com/cricket-match-squads/{cricbuzz_match_id}"


def build_cricbuzz_commentary_url(cricbuzz_match_id: int) -> str:
    return f"https://www.cricbuzz.com/live-cricket-scores/{cricbuzz_match_id}"


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

    schedule_lookup = _fetch_cricbuzz_schedule_lookup()
    if schedule_lookup is None:
        CRICBUZZ_MATCH_ID_MAP = {}
        return CRICBUZZ_MATCH_ID_MAP

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

    CRICBUZZ_MATCH_ID_MAP.update(mapping)
    print(f"[Cricbuzz] Cached {len(CRICBUZZ_MATCH_ID_MAP)} match id mappings")
    return CRICBUZZ_MATCH_ID_MAP


def _fetch_cricbuzz_schedule_lookup() -> dict[tuple[int, frozenset[str]], int] | None:
    schedule_url = build_cricbuzz_schedule_url()
    print(f"[Cricbuzz] Loading schedule mapping from {schedule_url}")

    try:
        res = _session_get(schedule_url)
        if res.status_code != 200:
            print(f"[Cricbuzz] Schedule fetch failed with status {res.status_code}")
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        schedule_lookup: dict[tuple[int, frozenset[str]], int] = {}

        for anchor in soup.find_all("a", href=True, title=True):
            href = anchor.get("href", "")
            title = anchor.get("title", "")
            match_id_match = re.search(r"/live-cricket-scores/(\d+)", href)
            title_match = re.match(r"(.+?) vs (.+?), (\d+)(?:st|nd|rd|th) Match\b", title, flags=re.IGNORECASE)
            if not match_id_match or not title_match:
                continue

            team_a = _to_short_team_name(title_match.group(1).strip())
            team_b = _to_short_team_name(title_match.group(2).strip())
            match_no = int(title_match.group(3))
            cricbuzz_match_id = int(match_id_match.group(1))
            schedule_lookup[(match_no, frozenset({team_a, team_b}))] = cricbuzz_match_id

        # Completed and older matches are consistently present in the embedded
        # matchesData payload even when they are not rendered as title anchors.
        matches_data_payload = _extract_cricbuzz_embedded_json(res.text, "matchesData")
        if matches_data_payload:
            for section in matches_data_payload.get("matchDetails", []):
                match_map = section.get("matchDetailsMap", {})
                for match in match_map.get("match", []):
                    match_info = match.get("matchInfo", {})
                    match_desc = str(match_info.get("matchDesc", ""))
                    desc_match = re.match(r"(\d+)(?:st|nd|rd|th)? Match\b", match_desc, flags=re.IGNORECASE)
                    if not desc_match:
                        continue

                    cricbuzz_match_id = int(match_info.get("matchId"))
                    match_no = int(desc_match.group(1))
                    team_a = _to_short_team_name((match_info.get("team1") or {}).get("teamSName", "").strip())
                    team_b = _to_short_team_name((match_info.get("team2") or {}).get("teamSName", "").strip())
                    if team_a and team_b:
                        schedule_lookup[(match_no, frozenset({team_a, team_b}))] = cricbuzz_match_id

        return schedule_lookup
    except Exception as e:
        print(f"[Cricbuzz] Error loading schedule mapping: {e}")
        return None


def _extract_cricbuzz_embedded_json(html_text: str, key: str) -> dict | None:
    marker = f'{key}\\":{{'
    start = html_text.find(marker)
    if start == -1:
        return None

    index = start + len(marker) - 1
    brace_count = 0
    payload_chars = []
    started = False

    for ch in html_text[index:]:
        if ch == "{":
            brace_count += 1
            started = True
        if started:
            payload_chars.append(ch)
        if ch == "}":
            brace_count -= 1
            if started and brace_count == 0:
                break

    if not payload_chars:
        return None

    try:
        payload_text = "".join(payload_chars).encode("utf-8").decode("unicode_escape")
        return json.loads(payload_text)
    except Exception as exc:
        print(f"[Cricbuzz] Failed to parse embedded {key} payload: {exc}")
        return None


def resolve_cricbuzz_match_id(match_id: int, team1: str, team2: str) -> int | None:
    cached_match_id = CRICBUZZ_MATCH_ID_MAP.get(int(match_id))
    if cached_match_id:
        return cached_match_id

    schedule_lookup = _fetch_cricbuzz_schedule_lookup()
    if not schedule_lookup:
        return None

    key = (
        int(match_id),
        frozenset({_to_short_team_name(team1), _to_short_team_name(team2)}),
    )
    resolved = schedule_lookup.get(key)
    if resolved:
        CRICBUZZ_MATCH_ID_MAP[int(match_id)] = resolved
    return resolved


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


def _resolve_team_player_ids_from_names(
    names: list[str],
    team: str,
    players_rows: list[dict],
) -> tuple[list[int], list[str]]:
    registry = _build_registry_from_players_rows(players_rows)
    ordered_ids: list[int] = []
    seen_ids: set[int] = set()
    unmatched_names: list[str] = []
    seen_unmatched: set[str] = set()

    for raw_name in names:
        cleaned_name = re.sub(r"\((?:w|wk|c|sub)\)", "", raw_name, flags=re.IGNORECASE).strip()
        normalized = _normalize_player_name(cleaned_name)
        if not normalized:
            continue

        player_id = _find_registry_player_id_silent(registry, cleaned_name, team)
        if not player_id:
            player_id = _find_close_team_player_id(cleaned_name, team, players_rows)

        if player_id:
            if player_id not in seen_ids:
                seen_ids.add(player_id)
                ordered_ids.append(player_id)
        elif normalized not in seen_unmatched:
            seen_unmatched.add(normalized)
            unmatched_names.append(cleaned_name)

    return ordered_ids, unmatched_names


def _extract_comma_separated_names(value: str) -> list[str]:
    return [name.strip() for name in value.split(",") if name.strip()]


def _team_name_variants(team_name: str) -> set[str]:
    variants = {_normalize_player_name(team_name), _normalize_player_name(_expand_team_name(team_name))}
    return {variant for variant in variants if variant}


def _resolve_toss_team(raw_team_text: str, team1: str, team2: str) -> str | None:
    normalized_raw = _normalize_player_name(raw_team_text)
    if normalized_raw in _team_name_variants(team1):
        return team1
    if normalized_raw in _team_name_variants(team2):
        return team2
    return None


def _extract_toss_info_from_html(html: str, team1: str, team2: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    if not text:
        return None

    patterns = [
        r"([A-Za-z .-]+?)\s+have won the toss and have opted to\s+(bat|bowl)",
        r"([A-Za-z .-]+?)\s+won the toss and opted to\s+(bat|bowl)",
        r"([A-Za-z .-]+?)\s+opt to\s+(bat|bowl)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        resolved_team = _resolve_toss_team(match.group(1).strip(), team1, team2)
        if not resolved_team:
            continue
        decision = match.group(2).lower()
        return {
            "announced": True,
            "team": resolved_team,
            "decision": decision,
            "text": f"{resolved_team} opt to {decision}",
        }

    return None


def extract_match_completion_status_from_cricbuzz_html(
    html: str,
    team1: str | None = None,
    team2: str | None = None,
) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)
    if not page_text:
        return None

    if re.search(r"\bNo result\b", page_text, flags=re.IGNORECASE) or re.search(
        r"\bMatch abandoned\b",
        page_text,
        flags=re.IGNORECASE,
    ):
        match = re.search(
            r"(No result(?:\s*\([^)]*\))?)|(Match abandoned(?:\s*\([^)]*\))?)",
            page_text,
            flags=re.IGNORECASE,
        )
        text = match.group(0).strip() if match else "No result"
        return {
            "status": "nr",
            "text": text,
        }

    candidate_team_names = [team1, team2]
    for team_name in candidate_team_names:
        if not team_name:
            continue
        for variant in {team_name, _expand_team_name(team_name)}:
            if not variant:
                continue
            match = re.search(
                rf"({re.escape(variant)}\s+won\s+by\s+[^.\n]+)",
                page_text,
                flags=re.IGNORECASE,
            )
            if match:
                return {
                    "status": "completed",
                    "text": " ".join(match.group(1).split()),
                }

    generic_match = re.search(r"([A-Za-z][A-Za-z .-]+?\s+won\s+by\s+[^.\n]+)", page_text, flags=re.IGNORECASE)
    if generic_match:
        return {
            "status": "completed",
            "text": " ".join(generic_match.group(1).split()),
        }

    return None


def _extract_playing_xi_from_commentary(
    html: str,
    team1: str,
    team2: str,
    players_rows: list[dict],
) -> tuple[list[int], list[int], list[str], list[str], bool]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)
    if not page_text:
        return [], [], [], [], False

    expanded_team_names = {
        team1: {team1, _expand_team_name(team1)},
        team2: {team2, _expand_team_name(team2)},
    }

    playing_ids: list[int] = []
    substitute_ids: list[int] = []
    unmatched_playing: list[str] = []
    unmatched_substitutes: list[str] = []
    announced = False

    for team, name_variants in expanded_team_names.items():
        xi_names: list[str] = []
        substitute_names: list[str] = []

        for variant in name_variants:
            escaped_variant = re.escape(variant)
            xi_match = re.search(
                rf"{escaped_variant}\s*\(Playing XI\):\s*(.+)",
                page_text,
                flags=re.IGNORECASE,
            )
            if xi_match and not xi_names:
                xi_names = _extract_comma_separated_names(xi_match.group(1).split("\n", 1)[0])

            subs_match = re.search(
                rf"{escaped_variant}\s+Impact\s+(?:subs|substitutes)\s*:\s*(.+)",
                page_text,
                flags=re.IGNORECASE,
            )
            if subs_match and not substitute_names:
                substitute_names = _extract_comma_separated_names(subs_match.group(1).split("\n", 1)[0])

        if xi_names:
            resolved_ids, unresolved_names = _resolve_team_player_ids_from_names(xi_names, team, players_rows)
            playing_ids.extend(resolved_ids)
            unmatched_playing.extend(unresolved_names)
        if substitute_names:
            resolved_ids, unresolved_names = _resolve_team_player_ids_from_names(substitute_names, team, players_rows)
            substitute_ids.extend(resolved_ids)
            unmatched_substitutes.extend(unresolved_names)

    if len(playing_ids) >= 18:
        announced = True

    return playing_ids, substitute_ids, unmatched_playing, unmatched_substitutes, announced


def parse_playing_xi_from_sources(
    commentary_html: str | None,
    squads_html: str | None,
    team1: str,
    team2: str,
    players_rows: list[dict],
    commentary_url: str = "",
    squads_url: str = "",
) -> dict:
    payload = {
        "announced": False,
        "url": "",
        "player_ids": [],
        "substitute_ids": [],
        "unmatched_names": [],
        "substitute_unmatched_names": [],
        "source": "",
        "substitutes_available": False,
        "finalized": False,
    }

    if commentary_html:
        (
            playing_ids,
            substitute_ids,
            unmatched_names,
            substitute_unmatched_names,
            announced,
        ) = _extract_playing_xi_from_commentary(commentary_html, team1, team2, players_rows)
        if announced:
            payload.update(
                {
                    "announced": len(playing_ids) == 22,
                    "url": commentary_url or "commentary",
                    "player_ids": list(playing_ids),
                    "substitute_ids": list(substitute_ids),
                    "unmatched_names": list(unmatched_names),
                    "substitute_unmatched_names": list(substitute_unmatched_names),
                    "source": "commentary",
                    "substitutes_available": len(substitute_ids) > 0,
                }
            )

    if not payload["announced"] and squads_html:
        playing_ids, unmatched_names, announced = _extract_named_players_from_cricbuzz_section(
            squads_html, "playing xi", team1, team2, players_rows
        )
        substitute_ids, substitute_unmatched_names, substitutes_available = _extract_named_players_from_cricbuzz_section(
            squads_html, "substitutes", team1, team2, players_rows
        )
        if announced:
            payload.update(
                {
                    "announced": len(playing_ids) == 22,
                    "url": squads_url or "squads",
                    "player_ids": list(playing_ids),
                    "substitute_ids": list(substitute_ids),
                    "unmatched_names": list(unmatched_names),
                    "substitute_unmatched_names": list(substitute_unmatched_names),
                    "source": "squads",
                    "substitutes_available": bool(substitutes_available),
                }
            )

    payload["announced"] = _is_playing_xi_announced(payload)
    payload["finalized"] = _is_finalized_playing_xi(payload)
    return payload


def _find_cricbuzz_section_heading(soup: BeautifulSoup, section_name: str):
    target = _normalize_player_name(section_name)
    for tag in soup.find_all(["h1", "h2", "h3"]):
        if _normalize_player_name(tag.get_text(" ", strip=True)) == target:
            return tag
    return None


def _extract_named_players_from_cricbuzz_section(
    html: str,
    section_name: str,
    team1: str,
    team2: str,
    players_rows: list[dict],
) -> tuple[list[int], list[str], bool]:
    soup = BeautifulSoup(html, "html.parser")
    heading = _find_cricbuzz_section_heading(soup, section_name)

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
    ordered_ids: list[int] = []
    seen_ids: set[int] = set()
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
                if player_id not in seen_ids:
                    seen_ids.add(player_id)
                    ordered_ids.append(player_id)
            elif normalized not in seen_unmatched:
                seen_unmatched.add(normalized)
                unmatched_names.append(raw_name)

    return ordered_ids, unmatched_names, True


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


def fetch_playing_xi(
    match_id: int,
    team1: str,
    team2: str,
    players_rows: list[dict],
    match_date: str | None = None,
    match_time: str | None = None,
) -> dict:
    cached = PLAYING_XI_CACHE.get(int(match_id))
    now_ts = time.time()
    allow_cache_read = not _is_before_match_start(match_date, match_time)
    if cached:
        payload = _copy_playing_xi_payload(cached["payload"])
        if cached.get("finalized"):
            return payload
        if allow_cache_read and now_ts - cached.get("fetched_at", 0) < PLAYING_XI_TTL_SECONDS:
            return payload

    if not _should_attempt_playing_xi_fetch(match_date, match_time):
        return {"announced": False, "url": "", "player_ids": [], "substitute_ids": []}

    cricbuzz_match_id = resolve_cricbuzz_match_id(int(match_id), team1, team2)
    if not cricbuzz_match_id:
        print(f"[Playing XI] Match {match_id}: no Cricbuzz match id found after schedule lookup")
        return {"announced": False, "url": "", "player_ids": [], "substitute_ids": []}

    commentary_url = build_cricbuzz_commentary_url(cricbuzz_match_id)
    squads_url = build_cricbuzz_playing_xi_url(cricbuzz_match_id)

    try:
        squads_html = None
        print(f"[Playing XI] Match {match_id}: trying {squads_url}")
        res = _session_get(squads_url)
        if res.status_code == 200:
            squads_html = res.text

        parsed_from_squads = None
        if squads_html:
            parsed_from_squads = parse_playing_xi_from_sources(
                None,
                squads_html,
                team1,
                team2,
                players_rows,
                commentary_url=commentary_url,
                squads_url=squads_url,
            )

        commentary_html = None
        if not parsed_from_squads or not parsed_from_squads["announced"]:
            print(f"[Playing XI] Match {match_id}: trying commentary {commentary_url}")
            commentary_res = _session_get(commentary_url)
            if commentary_res.status_code == 200:
                commentary_html = commentary_res.text

        if not squads_html and not commentary_html:
            print(f"[Playing XI] Match {match_id}: unable to fetch squads/commentary")
            payload = {"announced": False, "url": squads_url, "player_ids": [], "substitute_ids": []}
            PLAYING_XI_CACHE[int(match_id)] = {
                "payload": payload,
                "fetched_at": now_ts,
                "finalized": False,
            }
            return _copy_playing_xi_payload(payload)

        parsed_payload = parse_playing_xi_from_sources(
            commentary_html,
            squads_html,
            team1,
            team2,
            players_rows,
            commentary_url=commentary_url,
            squads_url=squads_url,
        )

        if not parsed_payload["announced"]:
            print(f"[Playing XI] Match {match_id}: Playing XI section not available yet")
            payload = {"announced": False, "url": parsed_payload.get("url", commentary_url), "player_ids": [], "substitute_ids": []}
            PLAYING_XI_CACHE[int(match_id)] = {
                "payload": payload,
                "fetched_at": now_ts,
                "finalized": False,
            }
            return _copy_playing_xi_payload(payload)

        source_url = parsed_payload["url"] or commentary_url
        playing_ids = parsed_payload["player_ids"]
        substitute_ids = parsed_payload["substitute_ids"]
        print(f"[Playing XI] Match {match_id}: using {source_url} (total={len(playing_ids)})")
        for name in parsed_payload["unmatched_names"]:
            print(f"[Playing XI] Match {match_id}: player mapping not found for '{name}'")
        if parsed_payload["substitutes_available"]:
            print(f"[Playing XI] Match {match_id}: substitutes found ({len(substitute_ids)})")
            for name in parsed_payload["substitute_unmatched_names"]:
                print(f"[Playing XI] Match {match_id}: substitute mapping not found for '{name}'")

        payload = {
            "announced": parsed_payload["announced"],
            "url": source_url,
            "player_ids": list(playing_ids),
            "substitute_ids": list(substitute_ids),
        }
        PLAYING_XI_CACHE[int(match_id)] = {
            "payload": payload,
            "fetched_at": now_ts,
            "finalized": parsed_payload["finalized"],
        }
        return _copy_playing_xi_payload(payload)
    except Exception as e:
        print("Error fetching playing XI:", e)
        payload = {"announced": False, "url": commentary_url, "player_ids": [], "substitute_ids": []}
        PLAYING_XI_CACHE[int(match_id)] = {
            "payload": payload,
            "fetched_at": now_ts,
            "finalized": False,
        }
        return _copy_playing_xi_payload(payload)


def fetch_toss_info(
    match_id: int,
    team1: str,
    team2: str,
    match_date: str | None = None,
    match_time: str | None = None,
) -> dict:
    cached = TOSS_INFO_CACHE.get(int(match_id))
    now_ts = time.time()
    if cached:
        if cached.get("announced"):
            return _copy_toss_payload(cached["payload"])
        if now_ts - cached.get("fetched_at", 0) < TOSS_INFO_TTL_SECONDS:
            return _copy_toss_payload(cached["payload"])

    if not should_attempt_toss_fetch(match_date, match_time):
        payload = {"announced": False, "team": None, "decision": None, "text": "", "url": ""}
        TOSS_INFO_CACHE[int(match_id)] = {
            "payload": payload,
            "fetched_at": now_ts,
            "announced": False,
        }
        return _copy_toss_payload(payload)

    cricbuzz_match_id = resolve_cricbuzz_match_id(int(match_id), team1, team2)
    if not cricbuzz_match_id:
        payload = {"announced": False, "team": None, "decision": None, "text": "", "url": ""}
        TOSS_INFO_CACHE[int(match_id)] = {
            "payload": payload,
            "fetched_at": now_ts,
            "announced": False,
        }
        return _copy_toss_payload(payload)

    commentary_url = build_cricbuzz_commentary_url(cricbuzz_match_id)
    scorecard_url = f"https://www.cricbuzz.com/live-cricket-scorecard/{cricbuzz_match_id}"

    for url in (commentary_url, scorecard_url):
        try:
            res = _session_get(url)
            if res.status_code != 200:
                continue
            parsed = _extract_toss_info_from_html(res.text, team1, team2)
            if parsed:
                parsed["url"] = url
                TOSS_INFO_CACHE[int(match_id)] = {
                    "payload": parsed,
                    "fetched_at": now_ts,
                    "announced": True,
                }
                return _copy_toss_payload(parsed)
        except Exception as exc:
            print(f"[Toss] Match {match_id}: error fetching {url}: {exc}")

    payload = {"announced": False, "team": None, "decision": None, "text": "", "url": ""}
    TOSS_INFO_CACHE[int(match_id)] = {
        "payload": payload,
        "fetched_at": now_ts,
        "announced": False,
    }
    return _copy_toss_payload(payload)


def fetch_venues_from_cricbuzz() -> dict[int, str]:
    """Fetch venue info for all matches from Cricbuzz schedule. Returns {match_no: 'Ground, City'}. Fails silently."""
    try:
        schedule_url = build_cricbuzz_schedule_url()
        res = _session_get(schedule_url)
        if res.status_code != 200:
            return {}

        venues: dict[int, str] = {}
        data = _extract_cricbuzz_embedded_json(res.text, "matchesData")
        if not data:
            return {}

        for section in data.get("matchDetails", []):
            match_map = section.get("matchDetailsMap", {})
            for match in match_map.get("match", []):
                match_info = match.get("matchInfo", {})
                match_desc = str(match_info.get("matchDesc", ""))
                desc_match = re.match(r"(\d+)(?:st|nd|rd|th)? Match\b", match_desc, flags=re.IGNORECASE)
                if not desc_match:
                    continue

                match_no = int(desc_match.group(1))
                venue_info = match_info.get("venueInfo", {})
                ground = venue_info.get("ground", "")
                city = venue_info.get("city", "")
                if ground:
                    venues[match_no] = f"{ground}, {city}" if city else ground

        print(f"[Cricbuzz] Fetched venues for {len(venues)} matches")
        return venues
    except Exception as e:
        print(f"[Cricbuzz] Error fetching venues: {e}")
        return {}


def populate_match_venues(db) -> None:
    """Populate venue column in matches table from Cricbuzz. Fails silently."""
    try:
        # Check which matches are missing venue
        rows = db.execute("SELECT id FROM matches WHERE venue IS NULL OR venue = ''").fetchall()
        if not rows:
            return

        missing_ids = {r["id"] for r in rows}
        venues = fetch_venues_from_cricbuzz()
        if not venues:
            return

        updated = 0
        for match_no, venue_str in venues.items():
            if match_no in missing_ids:
                db.execute("UPDATE matches SET venue = ? WHERE id = ?", (venue_str, match_no))
                updated += 1

        if updated:
            db.commit()
            from backend.services import data_service
            from backend.routes.matches import invalidate_matches_response_cache
            from backend.services.venue_stats import invalidate_today_venue_cache

            data_service.invalidate_cache("matches")
            invalidate_matches_response_cache()
            invalidate_today_venue_cache()
            print(f"[Venues] Updated venue for {updated} matches")
    except Exception as e:
        print(f"[Venues] Error populating venues: {e}")
