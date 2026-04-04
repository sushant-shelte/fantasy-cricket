import time
import threading
import traceback
from datetime import datetime, timedelta

from backend.config import IST, ESPN_MATCH_ID_OFFSET
from backend.models.match import Match
from backend.models.team import Team, Contestant
from backend.models.registry import PlayerRegistry
from backend.services.scraper import (
    fetch_playing_xi,
    fetch_scorecard_html,
    fetch_cricbuzz_scorecard_html,
    initialize_cricbuzz_match_map,
)
from backend.services import data_service
from bs4 import BeautifulSoup

DEBUG_PLAYER_ID = 0


def build_player_role_map(players_data):
    return {int(p["PlayerID"]): p["Role"] for p in players_data}


class Tournament:
    def __init__(self):
        self.matches = {}
        self.match_rows = {}
        self.contestants = {}
        self.match_participants = {}
        self.locked_match_ids_loaded = set()
        self.registry = None
        self.player_roles = {}
        self.player_points = {}
        self.players_by_team = {}

    def initialize(self, players_data, matches_data, teams_data):
        self.refresh_static_data(players_data, matches_data, refresh_schedule_map=True)

        self.contestants = {}
        self.match_participants = {}
        self.locked_match_ids_loaded = set()
        if teams_data:
            self.load_teams(teams_data)

    def refresh_static_data(self, players_data, matches_data, refresh_schedule_map=False):
        self.registry = PlayerRegistry(players_data)
        self.player_roles = build_player_role_map(players_data)
        if refresh_schedule_map:
            initialize_cricbuzz_match_map(matches_data)
        self.players_by_team = {}
        for player in players_data:
            self.players_by_team.setdefault(player["Team"], []).append({
                "id": int(player["PlayerID"]),
                "name": player.get("Name", ""),
                "team": player.get("Team", ""),
                "role": player.get("Role", ""),
                "aliases": player.get("Aliases", ""),
            })

        self.matches = {}
        self.match_rows = {}
        for m in matches_data:
            match_id = str(m["MatchID"])
            self.matches[match_id] = Match(match_id, m["Team1"], m["Team2"], self.registry)
            self.match_rows[match_id] = m

    def load_teams(self, teams_data):
        self.contestants = {}
        self.match_participants = {}
        self.locked_match_ids_loaded = set()

        for row in teams_data:
            self._apply_team_row(row)

        self.locked_match_ids_loaded.update(self.match_participants.keys())

    def _apply_team_row(self, row):
        contestant_key = str(row.get("UserID") or row.get("Mobile") or row.get("User"))
        match_id = str(row["MatchID"])
        pid = int(row["PlayerID"])

        if contestant_key not in self.contestants:
            self.contestants[contestant_key] = Contestant(
                row["User"],
                str(row.get("Mobile") or ""),
                row.get("UserID"),
                bool(row.get("IsActive", True)),
            )

        contestant = self.contestants[contestant_key]
        contestant.is_active = bool(row.get("IsActive", True))
        if match_id not in contestant.teams:
            contestant.teams[match_id] = Team(match_id)

        team = contestant.teams[match_id]
        team.player_ids.add(pid)
        self.match_participants.setdefault(match_id, set()).add(contestant_key)

        if str(row["Captain"]).lower() == "true":
            team.captain = pid
        if str(row["ViceCaptain"]).lower() == "true":
            team.vice_captain = pid

    def _remove_match_teams(self, match_id):
        participant_keys = list(self.match_participants.get(match_id, set()))
        for contestant_key in participant_keys:
            contestant = self.contestants.get(contestant_key)
            if not contestant:
                continue
            contestant.teams.pop(match_id, None)
            contestant.points.pop(match_id, None)
            if not contestant.teams:
                self.contestants.pop(contestant_key, None)
        self.match_participants.pop(match_id, None)
        self.locked_match_ids_loaded.discard(match_id)

    def ensure_match_teams_loaded(self, match_ids, force=False):
        normalized_ids = [str(match_id) for match_id in match_ids]
        if not normalized_ids:
            return

        if force:
            for match_id in normalized_ids:
                self._remove_match_teams(match_id)
            ids_to_fetch = normalized_ids
        else:
            ids_to_fetch = [match_id for match_id in normalized_ids if match_id not in self.locked_match_ids_loaded]

        if not ids_to_fetch:
            return

        rows = data_service.get_teams_for_matches(ids_to_fetch)
        for row in rows:
            self._apply_team_row(row)

        self.locked_match_ids_loaded.update(ids_to_fetch)

    def _log_active_player_count(self, match_id, match):
        active_players = [player for player in match.players.values() if getattr(player, "played", False)]
        active_count = len(active_players)
        if active_count < 22 or active_count > 24:
            print(f"[ALERT] Match {match_id}: active scoring player count is {active_count} (expected 22 to 24)")

    def update_match_data(self, match_id, use_playing_xi=False, include_scorecards=True):
        match = self.matches.get(match_id)
        if not match:
            return

        match.players = {}

        players_rows = self.players_by_team.get(match.team1, []) + self.players_by_team.get(match.team2, [])

        if use_playing_xi:
            match_row = self.match_rows.get(match_id, {})
            playing_xi = fetch_playing_xi(
                int(match_id),
                match.team1,
                match.team2,
                players_rows,
                match_row.get("Date"),
                match_row.get("Time"),
            )
            playing_ids = playing_xi.get("player_ids", [])
            substitute_ids = playing_xi.get("substitute_ids", [])
            print(f"[Playing XI] Match {match_id}: fetch result url={playing_xi.get('url')} players={len(playing_ids)}")
            if len(playing_ids) == 22 and len(substitute_ids) >= 10:
                swaps_applied = data_service.apply_backups_for_match(match_id, playing_ids, substitute_ids)
                if swaps_applied:
                    print(f"[Backups] Match {match_id}: applied {swaps_applied} backup swaps")
                    self.ensure_match_teams_loaded([match_id], force=True)
            if playing_ids:
                match.apply_playing_xi(playing_ids)

                team1_players = sorted(
                    [match.players[int(pid)].name for pid in playing_ids if self.registry.players.get(int(pid), {}).get("Team") == match.team1]
                )
                team2_players = sorted(
                    [match.players[int(pid)].name for pid in playing_ids if self.registry.players.get(int(pid), {}).get("Team") == match.team2]
                )
                print(f"[Playing XI] Match {match_id} via {playing_xi.get('url')}")
                print(f"  {match.team1}: {', '.join(team1_players) if team1_players else 'none'}")
                print(f"  {match.team2}: {', '.join(team2_players) if team2_players else 'none'}")
            else:
                print(f"[Playing XI] Match {match_id}: no mapped playing XI players found")

        if not include_scorecards:
            return

        cricbuzz_html = fetch_cricbuzz_scorecard_html(int(match_id), match.team1, match.team2)
        if cricbuzz_html:
            match.parse_cricbuzz_scorecard_html(cricbuzz_html, reset_players=False)

        scorecard_id = int(match_id) + ESPN_MATCH_ID_OFFSET
        espn_html_text = fetch_scorecard_html(scorecard_id)
        if espn_html_text:
            soup = BeautifulSoup(espn_html_text, "html.parser")
            match.parse_espn_bowling_dot_balls(soup)
            self._log_active_player_count(match_id, match)

    def get_match_status(self, match_row):
        try:
            match_datetime = datetime.strptime(
                f"{match_row['Date']} {match_row['Time']}", "%Y-%m-%d %H:%M"
            )
            match_datetime = IST.localize(match_datetime)
        except Exception:
            return None

        now = datetime.now(IST)
        today = now.date()
        parsed_date = datetime.strptime(match_row['Date'], "%Y-%m-%d").date()

        if now < match_datetime - timedelta(minutes=30):
            return "future"
        elif now < match_datetime:
            return "lineups"
        elif now < match_datetime + timedelta(hours=5):
            return "live"
        return "over"

    def compute_player_points_for_match(self, match_id):
        match = self.matches.get(match_id)
        if not match:
            return
        player_points = {}
        for pid, player in match.players.items():
            role = self.player_roles.get(pid)
            if role:
                player_points[pid] = player.calculate_player_points(role)
                if DEBUG_PLAYER_ID and int(pid) == DEBUG_PLAYER_ID:
                    print(
                        f"[DEBUG player {DEBUG_PLAYER_ID}]",
                        {
                            "match_id": match_id,
                            "player_id": pid,
                            "name": player.name,
                            "team": player.team,
                            "role": role,
                            "played": player.played,
                            "runs": player.runs,
                            "balls": player.balls,
                            "fours": player.fours,
                            "sixes": player.sixes,
                            "strike_rate": player.strike_rate,
                            "overs": player.overs,
                            "maidens": player.maidens,
                            "runs_conceded": player.runs_conceded,
                            "wickets": player.wickets,
                            "dot_balls": player.dot_balls,
                            "bowled": player.bowled,
                            "lbw": player.lbw,
                            "economy": player.economy,
                            "catches": player.catches,
                            "runout_direct": player.runout_direct,
                            "runout_indirect": player.runout_indirect,
                            "stumpings": player.stumpings,
                            "dismissal": player.dismissal,
                            "is_out": player.is_out,
                            "points": player_points[pid],
                        },
                    )
        self.player_points[match_id] = player_points

    def compute_points_for_match(self, match_id):
        participant_keys = self.match_participants.get(match_id, set())
        match = self.matches.get(match_id)
        if not match:
            return

        for contestant_key in participant_keys:
            contestant = self.contestants.get(contestant_key)
            if not contestant:
                continue
            if not contestant.is_active:
                contestant.points.pop(match_id, None)
                continue
            contestant.calculate_points_for_match(match, self.player_roles)

    def persist_to_local(self):
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        data_service.delete_inactive_contestant_points()
        rows = []
        for contestant in self.contestants.values():
            if not contestant.is_active:
                continue
            for match_id, pts in contestant.points.items():
                rows.append({
                    "UserID": contestant.user_id,
                    "User": contestant.name,
                    "Mobile": contestant.mobile,
                    "MatchID": match_id,
                    "Points": round(pts, 2),
                    "LastUpdated": now_str,
                })
        if rows:
            data_service.save_contestant_points(rows)

    def persist_player_points_to_local(self):
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for match_id, pp in self.player_points.items():
            match = self.matches.get(match_id)
            if not match:
                continue
            for pid, points in pp.items():
                player = match.players.get(pid)
                info = self.registry.players.get(pid)
                if not info:
                    continue
                rows.append({
                    "MatchID": match_id,
                    "PlayerID": pid,
                    "PlayerName": player.name if player else "",
                    "Team": info.get("Team", ""),
                    "Role": info.get("Role", ""),
                    "Points": round(points, 2),
                    "LastUpdated": now_str,
                })
        if rows:
            data_service.save_player_points(rows)

    def recompute_completed_matches(self, reason: str = "manual"):
        from backend.routes.leaderboard import invalidate_leaderboard_cache
        from backend.routes.matches import invalidate_matches_response_cache

        print(f"\n--- Completed matches recompute ({reason}) ---")
        players_data = data_service.get_cached_data("players")
        matches_data = data_service.get_cached_data("matches")
        self.refresh_static_data(players_data, matches_data, refresh_schedule_map=True)

        completed_match_ids = [
            str(match_row["MatchID"])
            for match_row in matches_data
            if self.get_match_status(match_row) == "over"
        ]

        if not completed_match_ids:
            invalidate_leaderboard_cache()
            invalidate_matches_response_cache()
            print("  No completed matches found for recompute")
            return 0

        self.ensure_match_teams_loaded(completed_match_ids, force=True)

        processed = 0
        for match_id in completed_match_ids:
            try:
                print(f"  Match {match_id}: OVER - recomputing completed match")
                self.update_match_data(match_id, use_playing_xi=True, include_scorecards=True)
                self.compute_player_points_for_match(match_id)
                self.compute_points_for_match(match_id)
                processed += 1
            except Exception as exc:
                print(f"  Match {match_id}: ERROR - {exc}")
                traceback.print_exc()

        if processed > 0:
            self.persist_player_points_to_local()
            self.persist_to_local()

        invalidate_leaderboard_cache()
        invalidate_matches_response_cache()
        print(f"  Recomputed {processed} completed matches")
        return processed

    def start_scheduler(self):
        def run():
            while True:
                sleep_seconds = 60
                try:
                    print("\n--- Scheduler tick ---")
                    matches_data = data_service.get_cached_data("matches")
                    computed_matches = data_service.get_computed_match_ids()
                    locked_match_ids_to_load = []
                    has_lineup_window_match = False

                    for m in matches_data:
                        match_id = str(m["MatchID"])
                        status = self.get_match_status(m)
                        if status in ("lineups", "live"):
                            locked_match_ids_to_load.append(match_id)
                        if status == "lineups":
                            has_lineup_window_match = True
                        elif status == "over" and match_id not in computed_matches:
                            locked_match_ids_to_load.append(match_id)

                    self.ensure_match_teams_loaded(locked_match_ids_to_load)

                    processed = 0

                    for m in matches_data:
                        match_id = str(m["MatchID"])
                        status = self.get_match_status(m)

                        if status == "future":
                            continue

                        # Per-match error handling — one failure doesn't stop others
                        try:
                            if status == "lineups":
                                print(f"  Match {match_id}: {status.upper()} — fetching scores")
                                self.update_match_data(match_id, use_playing_xi=True, include_scorecards=False)
                            elif status == "live":
                                print(f"  Match {match_id}: LIVE - fetching scores")
                                self.update_match_data(match_id, use_playing_xi=True, include_scorecards=True)
                                self.compute_player_points_for_match(match_id)
                                self.compute_points_for_match(match_id)
                                processed += 1

                            elif status == "over":
                                if match_id in computed_matches:
                                    # Already computed, skip scraping
                                    continue

                                print(f"  Match {match_id}: OVER — computing for first time")
                                self.update_match_data(match_id, use_playing_xi=True, include_scorecards=True)
                                self.compute_player_points_for_match(match_id)
                                self.compute_points_for_match(match_id)
                                processed += 1

                        except Exception as e:
                            print(f"  Match {match_id}: ERROR — {e}")
                            traceback.print_exc()
                            continue  # Keep processing other matches

                    if has_lineup_window_match:
                        sleep_seconds = 15

                    # Only persist if we processed something
                    if processed > 0:
                        try:
                            self.persist_player_points_to_local()
                            self.persist_to_local()
                            print(f"  Persisted {processed} matches")
                        except Exception as e:
                            print(f"  Persist ERROR: {e}")
                            traceback.print_exc()

                except Exception as e:
                    print(f"Scheduler outer error: {e}")
                    traceback.print_exc()

                time.sleep(sleep_seconds)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
