import time
import threading
import traceback
from datetime import datetime, timedelta

from backend.config import IST, ESPN_MATCH_ID_OFFSET
from backend.models.match import Match
from backend.models.team import Team, Contestant
from backend.models.registry import PlayerRegistry
from backend.services.scraper import fetch_scorecard_html
from backend.services import data_service
from bs4 import BeautifulSoup


def build_player_role_map(players_data):
    return {int(p["PlayerID"]): p["Role"] for p in players_data}


class Tournament:
    def __init__(self):
        self.matches = {}
        self.contestants = {}
        self.registry = None
        self.player_roles = {}
        self.player_points = {}

    def initialize(self, players_data, matches_data, teams_data):
        self.registry = PlayerRegistry(players_data)
        self.player_roles = build_player_role_map(players_data)

        for m in matches_data:
            match_id = str(m["MatchID"])
            self.matches[match_id] = Match(match_id, m["Team1"], m["Team2"], self.registry)

        for row in teams_data:
            mobile = str(row["Mobile"])
            match_id = str(row["MatchID"])
            pid = int(row["PlayerID"])

            if mobile not in self.contestants:
                self.contestants[mobile] = Contestant(row["User"], mobile)

            contestant = self.contestants[mobile]
            if match_id not in contestant.teams:
                contestant.teams[match_id] = Team(match_id)

            team = contestant.teams[match_id]
            team.player_ids.add(pid)

            if str(row["Captain"]).lower() == "true":
                team.captain = pid
            if str(row["ViceCaptain"]).lower() == "true":
                team.vice_captain = pid

    def update_match_data(self, match_id):
        match = self.matches.get(match_id)
        if not match:
            return

        scorecard_id = int(match_id) + ESPN_MATCH_ID_OFFSET
        html_text = fetch_scorecard_html(scorecard_id)
        if not html_text:
            return

        soup = BeautifulSoup(html_text, "html.parser")
        match.parse_scorecard(soup)

    def get_match_status(self, match_row):
        try:
            match_datetime = datetime.strptime(
                f"{match_row['Date']} {match_row['Time']}", "%Y-%m-%d %H:%M"
            )
            match_datetime = IST.localize(match_datetime)
        except Exception:
            return None

        now = datetime.now(IST)

        if now < match_datetime:
            return "future"
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
        self.player_points[match_id] = player_points

    def compute_points_for_match(self, match_id):
        for contestant in self.contestants.values():
            match = self.matches.get(match_id)
            if match:
                contestant.calculate_points_for_match(match, self.player_roles)

    def persist_to_local(self):
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for contestant in self.contestants.values():
            for match_id, pts in contestant.points.items():
                rows.append({
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

    def start_scheduler(self):
        def run():
            while True:
                try:
                    print("\n--- Scheduler tick ---")
                    matches_data = data_service.get_cached_data("matches")

                    # Get already computed match IDs from player_points
                    computed_matches = set()
                    try:
                        pp = data_service.get_player_points()
                        computed_matches = {str(r["MatchID"]) for r in pp}
                    except Exception:
                        pass

                    processed = 0

                    for m in matches_data:
                        match_id = str(m["MatchID"])
                        status = self.get_match_status(m)

                        if status == "future":
                            continue

                        # Per-match error handling — one failure doesn't stop others
                        try:
                            if status == "live":
                                print(f"  Match {match_id}: LIVE — fetching scores")
                                self.update_match_data(match_id)
                                self.compute_player_points_for_match(match_id)
                                self.compute_points_for_match(match_id)
                                processed += 1

                            elif status == "over":
                                if match_id in computed_matches:
                                    # Already computed, skip scraping
                                    continue

                                print(f"  Match {match_id}: OVER — computing for first time")
                                self.update_match_data(match_id)
                                self.compute_player_points_for_match(match_id)
                                self.compute_points_for_match(match_id)
                                processed += 1

                        except Exception as e:
                            print(f"  Match {match_id}: ERROR — {e}")
                            traceback.print_exc()
                            continue  # Keep processing other matches

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

                time.sleep(60)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
