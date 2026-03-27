# =============================
# IMPORTS
# =============================
import sys
print("🔥 STARTING APP", flush=True)
sys.stdout.flush()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
from typing import Optional
from bs4 import BeautifulSoup
import requests
import time
import re
import threading
import os
import json
import traceback

try:
    print("🔥 inside try block")

    # =============================
    # CONFIG
    # =============================
    TEST_MODE = True
    TEST_MODE_MONTH = 3
    TEST_MODE_DATE = 22
    TEST_MODE_TIME_HR = 20
    TEST_MODE_TIME_MIN = 0
    
    MATCH_CODE_OFFSET = 1107 if TEST_MODE else 1107 #1181
    
    ROLES = ["Wicketkeeper", "Batter", "AllRounder", "Bowler"]
    
    app = FastAPI()
    
    # Add session middleware
    app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")  # Change to a secure key
    
    # =============================
    # CACHE
    # =============================
    CACHE = {
        "players": None,
        "users": None,
        "matches": None,
        "last_updated": 0
    }
    CACHE_TTL = 60
    
    # =============================
    # GOOGLE SHEETS
    # =============================
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        print("✅ creds loading")
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        #creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
        #creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        print("✅ creds loaded")
    except Exception as e:
        print("❌ creds failed")
        traceback.print_exc()
    
    
    
    client = gspread.authorize(creds)
    sheet = client.open("FantasyCricket")
    
    users_sheet = sheet.worksheet("Users")
    players_sheet = sheet.worksheet("Players")
    matches_sheet = sheet.worksheet("Matches")
    teams_sheet = sheet.worksheet("Teams")
    
    # =============================
    # TIMEZONE
    # =============================
    ist = pytz.timezone("Asia/Kolkata")
    
    # =============================
    # TEAM MAP (UNCHANGED)
    # =============================
    TEAM_MAP = {
        "Royal Challengers Bengaluru": "RCB",
        "Mumbai Indians": "MI",
        "Chennai Super Kings": "CSK",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Gujarat Titans": "GT",
        "Delhi Capitals": "DC",
        "Lucknow Super Giants": "LSG",
        "Punjab Kings": "PBKS",
        "Sunrisers Hyderabad": "SRH",
        "RCB": "RCB",
        "MI": "MI",
        "CSK": "CSK",
        "KKR": "KKR",
        "RR": "RR",
        "GT": "GT",
        "DC": "DC",
        "LSG": "LSG",
        "PBKS": "PBKS",
        "SRH": "SRH"
    }
    
    # =============================
    # HELPERS (UNCHANGED LOGIC)
    # =============================
    def normalize_name(name):
        return name.lower().replace(".", "").strip()
    
    def clean_name(name):
        return re.sub(r"[†*]", "", name).strip()
    
    def clean_team_name(name):
        # Remove anything in parentheses
        name = re.sub(r"\(.*?\)", "", name).strip()
    
        # Normalize spacing
        name = " ".join(name.split())
    
        # Convert to short name using TEAM_MAP
        short = TEAM_MAP.get(name)
    
        if not short:
            print("❌ Team mapping missing for:", name)
            return name  # fallback (important for debugging)
    
        return short
    
    def is_batting_role(role):
        return role in ["Batter", "Wicketkeeper", "AllRounder"]
    
    def build_player_role_map(players_data):
        role_map = {}
        for p in players_data:
            role_map[int(p["PlayerID"])] = p["Role"]
        return role_map
    
    def build_player_lookup(players):
        lookup = {}
    
        for p in players:
            team = p["Team"]
            pid = p["PlayerID"]
    
            names = [p["Name"]]
    
            if p.get("Aliases"):
                names.extend(p["Aliases"].split(","))
    
            for name in names:
                key = (normalize_name(name), team)
                lookup[key] = pid
    
        return lookup
    
    def get_player_id_from_lookup(name, team, lookup):
        return lookup.get((normalize_name(name), team))
    
    # =============================
    # CACHE FETCH
    # =============================
    def get_cached_data(sheet_name):
        now = time.time()
    
        if now - CACHE["last_updated"] > CACHE_TTL:
            CACHE["players"] = players_sheet.get_all_records()
            CACHE["users"] = users_sheet.get_all_records()
            CACHE["matches"] = matches_sheet.get_all_records()
            CACHE["last_updated"] = now
    
        return CACHE[sheet_name]
    
    # =============================
    # MATCH LOCK LOGIC (UNCHANGED)
    # =============================
    def is_match_locked_by_row(match):
        try:
            match_datetime = datetime.strptime(
                f"{match['Date']} {match['Time']}",
                "%Y-%m-%d %H:%M"
            )
            match_datetime = ist.localize(match_datetime)
        except:
            return False
    
        if TEST_MODE:
            now = ist.localize(datetime(
                2025,
                TEST_MODE_MONTH,
                TEST_MODE_DATE,
                TEST_MODE_TIME_HR,
                TEST_MODE_TIME_MIN
            ))
        else:
            now = datetime.now(ist)
    
        return now >= match_datetime
    
    # Backward compatibility for older call-sites
    def is_match_locked(match_datetime_str):
        # expected format: "YYYY-MM-DD HH:MM"
        try:
            match_datetime = datetime.strptime(match_datetime_str, "%Y-%m-%d %H:%M")
            match_datetime = ist.localize(match_datetime)
        except Exception:
            return False
    
        if TEST_MODE:
            now = ist.localize(datetime(
                2025,
                TEST_MODE_MONTH,
                TEST_MODE_DATE,
                TEST_MODE_TIME_HR,
                TEST_MODE_TIME_MIN
            ))
        else:
            now = datetime.now(ist)
    
        return now >= match_datetime
    
    # =============================
    # FETCH SCORECARD
    # =============================
    def fetch_scorecard_html(match_code):
        url = f"https://www.howstat.com/Cricket/Statistics/IPL/MatchScorecard.asp?MatchCode={match_code}"
    
        try:
            res = requests.get(url)
            if res.status_code != 200:
                return None
            return res.text
        except Exception as e:
            print("Error fetching scorecard:", e)
            return None
            
    # =============================
    # PLAYER POINTS ENGINE
    # =============================
    class Player: pass 
    def calculate_player_points(player: Player, role: str):
    
        points = 0
    
        # -----------------------
        # 🟢 PLAYING
        # -----------------------
        if player.played:
            points += 4
    
        # -----------------------
        # 🏏 BATTING
        # -----------------------
        runs = player.runs
    
        points += runs
    
        # Boundaries
        points += player.fours * 1
        points += player.sixes * 2
    
        # Milestones
        if runs >= 100:
            points += 16
        elif runs >= 50:
            points += 8
        elif runs >= 30:
            points += 4
    
        # Duck (only batting roles)
        if runs == 0 and player.is_out and is_batting_role(role):
            points -= 2
    
        # Strike Rate (min 10 balls)
        if player.balls >= 10:
            sr = player.strike_rate
    
            if sr > 170:
                points += 6
            elif sr >= 150:
                points += 4
            elif sr >= 130:
                points += 2
            elif sr < 50:
                points -= 6
            elif sr < 60:
                points -= 4
            elif sr < 70:
                points -= 2
    
        # -----------------------
        # 🎯 BOWLING
        # -----------------------
        wkts = player.wickets
    
        points += wkts * 25
    
        # Wicket haul bonus
        if wkts >= 5:
            points += 16
        elif wkts == 4:
            points += 8
        elif wkts == 3:
            points += 4
    
        # Maidens
        points += player.maidens * 12
    
        # Economy (min 2 overs)
        if player.overs >= 2:
            eco = player.economy
    
            if eco < 5:
                points += 6
            elif eco < 6:
                points += 4
            elif eco < 7:
                points += 2
            elif eco > 11:
                points -= 6
            elif eco > 10:
                points -= 4
            elif eco > 9:
                points -= 2
    
        # -----------------------
        # 🧤 FIELDING
        # -----------------------
        points += player.catches * 8
    
        # 3 catch bonus
        if player.catches >= 3:
            points += 4
    
        points += player.stumpings * 12
        points += player.runout_direct * 12
        points += player.runout_indirect * 6
    
        return points
    
    # =============================
    # PLAYER REGISTRY
    # =============================
    class PlayerRegistry:
        def __init__(self, players_data):
            self.players = {}   # pid → full row
            self.lookup = {}    # (team, normalized name) → pid
    
            self.build(players_data)
    
        def normalize(self, name):
            return name.lower().replace(".", "").strip()
    
        def build(self, players_data):
            for row in players_data:
                pid = int(row["PlayerID"])
                name = row["Name"]
                team = row["Team"]
    
                self.players[pid] = row
    
                names = [name]
                if row.get("Aliases"):
                    names.extend(row["Aliases"].split(","))
    
                for n in names:
                    self.lookup[(team, self.normalize(n))] = pid
    
        def get_player_id(self, name, team):
            normalized_name = self.normalize(name)
            
            # 1. Try whole name first
            if (team, normalized_name) in self.lookup:
                return self.lookup[(team, normalized_name)]
            
            # 2. Try last name (split by space and take last part)
            name_parts = normalized_name.split()
            if len(name_parts) > 1:
                last_name = name_parts[-1]
                if (team, last_name) in self.lookup:
                    return self.lookup[(team, last_name)]
            
            # 3. Try first name (split by space and take first part)
            if len(name_parts) > 0:
                first_name = name_parts[0]
                if (team, first_name) in self.lookup:
                    return self.lookup[(team, first_name)]
            
            # 4. Not found - print error
            print(f"❌ Player mapping not found: '{name}' (team: {team})")
            return None
    
    # =============================
    # PLAYER MODEL
    # =============================
    class Player:
        def __init__(self, player_id, name):
            self.player_id = player_id
            self.name = name
    
            # Batting
            self.runs = 0
            self.balls = 0
            self.fours = 0
            self.sixes = 0
            self.strike_rate = 0.0
            self.dismissal = None
            self.is_out = False
    
            # Bowling
            self.overs = 0.0
            self.maidens = 0
            self.runs_conceded = 0
            self.wickets = 0
            self.bowled = 0
            self.lbw = 0
            self.economy = 0.0
    
            # Fielding
            self.catches = 0
            self.runout_direct = 0
            self.runout_indirect = 0
            self.stumpings = 0
    
            # Played
            self.played = False
    
        # =============================
        # DISMISSAL PARSER (PID SAFE)
        # =============================
        def apply_dismissal(self, dismissal_text, match, bowling_team=None):
            self.dismissal = dismissal_text.strip()
    
            if self.dismissal.lower() == "not out":
                self.is_out = False
                return
    
            self.is_out = True
    
            # 🔥 Always resolve via MATCH and bowling team (dismissal is from bowling side)
            def get_player(name):
                if bowling_team:
                    return match.get_player_by_team(name, bowling_team)
                return match.get_player_by_name(name)
    
            # -----------------------
            # CAUGHT
            # -----------------------
            if self.dismissal.startswith("c "):
                match_obj = re.search(r"c\s+(.+?)\s+b\s+(.+)", self.dismissal)
                if match_obj:
                    fielder = get_player(match_obj.group(1))
                    bowler = get_player(match_obj.group(2))
    
                    if fielder:
                        fielder.catches += 1
                    if bowler:
                        bowler.wickets += 1
                return
    
            # -----------------------
            # BOWLED
            # -----------------------
            if self.dismissal.startswith("b "):
                bowler = get_player(self.dismissal.replace("b ", "").strip())
                if bowler:
                    bowler.wickets += 1
                    bowler.bowled += 1
                return
    
            # -----------------------
            # LBW
            # -----------------------
            if self.dismissal.startswith("lbw"):
                match_obj = re.search(r"lbw\s+b\s+(.+)", self.dismissal)
                if match_obj:
                    bowler = get_player(match_obj.group(1))
                    if bowler:
                        bowler.wickets += 1
                        bowler.lbw += 1
                return
    
            # -----------------------
            # STUMPING
            # -----------------------
            if self.dismissal.startswith("st"):
                match_obj = re.search(r"st\s+(.+?)\s+b\s+(.+)", self.dismissal)
                if match_obj:
                    fielder = get_player(match_obj.group(1))
                    bowler = get_player(match_obj.group(2))
    
                    if fielder:
                        fielder.stumpings += 1
                        fielder.runout_direct += 1
                    if bowler:
                        bowler.wickets += 1
                return
    
            # -----------------------
            # RUN OUT
            # -----------------------
            if "run out" in self.dismissal.lower():
                match_obj = re.search(r"\((.*?)\)", self.dismissal)
                if match_obj:
                    fielders = [f.strip() for f in match_obj.group(1).split("/")]
    
                    if len(fielders) == 1:
                        f = get_player(fielders[0])
                        if f:
                            f.runout_direct += 1
                    else:
                        for name in fielders:
                            f = get_player(name)
                            if f:
                                f.runout_indirect += 1
                return
    
    
    # =============================
    # MATCH
    # =============================
    class Match:
        def __init__(self, match_id, team1, team2, registry: PlayerRegistry):
            self.match_id = match_id
            self.team1 = team1
            self.team2 = team2
            self.registry = registry
            self.players = {}  # pid → Player
    
        # -------------------------
        # GET PLAYER ID
        # -------------------------
        def get_player_id(self, name, team):
            return self.registry.get_player_id(clean_name(name), team)
    
        # -------------------------
        # CORE: CREATE BY PID
        # -------------------------
        def get_or_create_player(self, pid, name=None):
    
            if not pid:
                return None
    
            if pid not in self.players:
                if not name:
                    name = self.registry.players.get(pid, {}).get("Name", "Unknown")
    
                self.players[pid] = Player(pid, name)
    
            return self.players[pid]
    
        # -------------------------
        # 🔥 USED BY PLAYER CLASS
        # -------------------------
        def get_player_by_name(self, name):
            name = clean_name(name)
    
            pid = self.registry.get_player_id(name, self.team1) \
                  or self.registry.get_player_id(name, self.team2)
    
            if not pid:
                print("❌ Player ID NOT FOUND (dismissal):", name)
                return None
    
            return self.get_or_create_player(pid, name)
    
        def get_player_by_team(self, name, team):
            name = clean_name(name)
    
            pid = self.registry.get_player_id(name, team)
    
            if not pid:
                print(f"❌ Player ID NOT FOUND in team {team} (dismissal):", name)
                return None
    
            return self.get_or_create_player(pid, name)
    
        # =============================
        # PARSE SCORECARD
        # =============================
        def parse_scorecard(self, soup: BeautifulSoup):
    
            # ✅ CLEAR OLD PLAYER DATA BEFORE PARSING NEW SCORECARD
            self.players = {}
    
            team_tags = soup.find_all(class_="ScorecardCountry3")
    
            if len(team_tags) < 2:
                print("❌ Teams not found")
                return
    
            team1_clean = clean_team_name(team_tags[0].get_text(strip=True))
            team2_clean = clean_team_name(team_tags[1].get_text(strip=True))
    
            # ---------------------------
            # 🟢 BATTING
            # ---------------------------
            batting_tables = [t for t in soup.find_all("table") if "BATTING" in t.text]
    
            for i, table in enumerate(batting_tables):
    
                batting_team = team1_clean if i == 0 else team2_clean
                bowling_team = team2_clean if batting_team == team1_clean else team1_clean
    
                for r in table.find_all("tr"):
                    cols = [c.text.strip() for c in r.find_all("td")]
    
                    if len(cols) < 7 or cols[0] == "BATTING":
                        continue
    
                    name = clean_name(cols[0])
                    pid = self.get_player_id(name, batting_team)
    
                    if not pid:
                        print(f"❌ Missing ID (bat): {name} | {batting_team}")
                        continue
    
                    player = self.get_or_create_player(pid, name)
    
                    player.played = True
                    player.runs = int(cols[2])
                    player.balls = int(cols[3])
                    player.fours = int(cols[4])
                    player.sixes = int(cols[5])
    
                    if player.balls > 0:
                        # ✅ Round to 2 decimals to avoid floating point precision issues
                        player.strike_rate = round((player.runs / player.balls) * 100, 2)
    
                    # ✅ Pass bowling team into dismissal parser (dismissal is from bowling side)
                    player.apply_dismissal(cols[1], self, bowling_team)
    
            # ---------------------------
            # 🔵 BOWLING
            # ---------------------------
            bowling_tables = soup.find_all(class_="ScorecardBowling")
    
            for i, table in enumerate(bowling_tables):
    
                bowling_team = team2_clean if i == 0 else team1_clean
    
                for r in table.find_all("tr")[1:]:
                    cols = [c.text.strip() for c in r.find_all("td")]
    
                    if len(cols) < 5:
                        continue
    
                    name = clean_name(cols[0])
                    pid = self.get_player_id(name, bowling_team)
    
                    if not pid:
                        print(f"❌ Missing ID (bowl): {name} | {bowling_team}")
                        continue
    
                    player = self.get_or_create_player(pid, name)
    
                    player.played = True
                    player.overs = float(cols[1])
                    player.maidens = int(cols[2])
                    player.runs_conceded = int(cols[3])
                    player.wickets = int(cols[4])
    
                    if player.overs > 0:
                        # ✅ Round to 2 decimals to avoid floating point precision issues
                        player.economy = round(player.runs_conceded / player.overs, 2)
    
            # ---------------------------
            # 🟡 DID NOT BAT
            # ---------------------------
            tds = soup.find_all("td")
            dnb_index = 0
    
            for i, td in enumerate(tds):
                if "Did Not Bat" in td.get_text():
    
                    batting_team = team1_clean if dnb_index == 0 else team2_clean
                    next_td = tds[i + 1]
    
                    for p in next_td.find_all("a"):
                        name = clean_name(p.get_text())
                        pid = self.get_player_id(name, batting_team)
    
                        if not pid:
                            print(f"❌ Missing ID (DNB): {name} | {batting_team}")
                            continue
    
                        player = self.get_or_create_player(pid, name)
                        player.played = True
    
                    dnb_index += 1
    
            print(f"✅ Total players parsed: {len(self.players)}")
            
    # =============================
    # TEAM
    # =============================
    class Team:
        def __init__(self, match_id, player_ids=None, captain=None, vice_captain=None):
            self.match_id = match_id
            self.player_ids = set(player_ids or [])
            self.captain = captain
            self.vice_captain = vice_captain
    
        # 🔥 RENAMED (no collision)
        def calculate_team_points(self, match: Match, player_roles):
            total = 0
    
            for pid in self.player_ids:
                player = match.players.get(pid)
    
                if not player:
                    continue
    
                role = player_roles.get(pid)
    
                if not role:
                    print("❌ Missing role:", player.name)
                    continue
    
                pts = calculate_player_points(player, role)
    
                # Captain / VC multiplier
                if pid == self.captain:
                    pts *= 2
                elif pid == self.vice_captain:
                    pts *= 1.5
    
                total += pts
    
            return total
    
    
    # =============================
    # CONTESTANT
    # =============================
    class Contestant:
        def __init__(self, name, mobile):
            self.name = name
            self.mobile = mobile
            self.teams = {}   # match_id → Team
            self.points = {}  # match_id → points
    
        def add_team(self, team: Team):
            self.teams[team.match_id] = team
    
        # 🔥 RENAMED
        def calculate_points_for_match(self, match: Match, player_roles):
            team = self.teams.get(match.match_id)
    
            if not team:
                return 0
    
            pts = team.calculate_team_points(match, player_roles)
            self.points[match.match_id] = pts
    
            return pts
    
    
    # =============================
    # TOURNAMENT
    # =============================
    class Tournament:
        def __init__(self):
            self.matches = {}       # match_id → Match
            self.contestants = {}  # mobile → Contestant
    
            self.registry = None
            self.player_roles = {}
            self.player_points = {}  # match_id → {pid: points}
    
        # -------------------------
        # INITIALIZE
        # -------------------------
        def initialize(self, players_data, matches_data, teams_data):
    
            # ✅ SINGLE SOURCE
            self.registry = PlayerRegistry(players_data)
    
            # ✅ Role map
            self.player_roles = build_player_role_map(players_data)
    
            # -------------------------
            # CREATE MATCHES
            # -------------------------
            for m in matches_data:
                match_id = str(m["MatchID"])
    
                self.matches[match_id] = Match(
                    match_id,
                    m["Team1"],
                    m["Team2"],
                    self.registry
                )
    
            # -------------------------
            # CREATE CONTESTANTS + TEAMS
            # -------------------------
            for row in teams_data:
                mobile = str(row["Mobile"])
                match_id = str(row["MatchID"])
                pid = int(row["PlayerID"])
    
                if mobile not in self.contestants:
                    self.contestants[mobile] = Contestant(
                        row["User"],
                        mobile
                    )
    
                contestant = self.contestants[mobile]
    
                if match_id not in contestant.teams:
                    contestant.teams[match_id] = Team(match_id)
    
                team = contestant.teams[match_id]
                team.player_ids.add(pid)
    
                if str(row["Captain"]).lower() == "true":
                    team.captain = pid
    
                if str(row["ViceCaptain"]).lower() == "true":
                    team.vice_captain = pid
    
        # -------------------------
        # UPDATE MATCH DATA
        # -------------------------
        def update_match_data(self, match_id):
    
            match = self.matches.get(match_id)
    
            if not match:
                return
    
            print(f"\n📊 Updating Match {match_id}")
    
            match_code = int(match_id) + MATCH_CODE_OFFSET
            html_text = fetch_scorecard_html(match_code)
    
            if not html_text:
                print("❌ No scorecard")
                return
    
            soup = BeautifulSoup(html_text, "html.parser")
    
            match.parse_scorecard(soup)
    
            # Debug
            for p in match.players.values():
                print(p.name, p.runs, p.wickets, p.catches)
    
        # -------------------------
        # DETERMINE MATCH STATUS
        # -------------------------
        def get_match_status(self, match):
            """
            Returns: 'future', 'live', 'over'
            """
            try:
                match_datetime = datetime.strptime(
                    f"{match['Date']} {match['Time']}",
                    "%Y-%m-%d %H:%M"
                )
                match_datetime = ist.localize(match_datetime)
            except:
                return None
    
            if TEST_MODE:
                now = ist.localize(datetime(
                    2025,
                    TEST_MODE_MONTH,
                    TEST_MODE_DATE,
                    TEST_MODE_TIME_HR,
                    TEST_MODE_TIME_MIN
                ))
            else:
                now = datetime.now(ist)
    
            if now < match_datetime:
                return 'future'
            elif now >= match_datetime and now < match_datetime + timedelta(hours=5):
                return 'live'
            else:
                return 'over'
    
        # -------------------------
        # GET ALREADY COMPUTED POINTS
        # -------------------------
        def get_computed_points(self):
            """
            Returns dict: {(mobile, match_id): points}
            """
            computed = {}
            try:
                sheet = client.open("FantasyCricket").worksheet("ContestantPoints")
                records = sheet.get_all_records()
                for row in records:
                    mobile = str(row["Mobile"])
                    match_id = str(row["MatchID"])
                    points = float(row["Points"])
                    computed[(mobile, match_id)] = points
            except:
                pass
            return computed
    
        # -------------------------
        # GET ALREADY COMPUTED PLAYER POINTS
        # -------------------------
        def get_computed_player_points(self):
            """
            Returns dict: {(match_id, pid): points}
            """
            computed = {}
            try:
                sheet = client.open("FantasyCricket").worksheet("PlayerPoints")
                records = sheet.get_all_records()
                for row in records:
                    match_id = str(row["MatchID"])
                    pid = int(row["PlayerID"])
                    points = float(row["Points"])
                    computed[(match_id, pid)] = points
            except:
                pass
            return computed
    
        # -------------------------
        # COMPUTE PLAYER POINTS FOR MATCH
        # -------------------------
        def compute_player_points_for_match(self, match_id):
            """
            Calculate points for each player in a match
            """
            match = self.matches.get(match_id)
            if not match:
                return
    
            player_points = {}
    
            for pid, player in match.players.items():
                role = self.player_roles.get(pid)
                if not role:
                    continue
    
                points = calculate_player_points(player, role)
                player_points[pid] = points
    
            self.player_points[match_id] = player_points
    
        # -------------------------
        # COMPUTE POINTS FOR MATCH
        # -------------------------
        def compute_points_for_match(self, match_id):
            """
            Compute points for a specific match for all contestants
            """
            for contestant in self.contestants.values():
                match = self.matches.get(match_id)
                if match:
                    contestant.calculate_points_for_match(
                        match,
                        self.player_roles
                    )
    
        # -------------------------
        # SCHEDULER
        # -------------------------
        def start_scheduler(self):
    
            def run():
                while True:
                    try:
                        print("\n🔄 Scheduler running...")
    
                        matches_data = get_cached_data("matches")
                        computed_points = self.get_computed_points()
    
                        for m in matches_data:
                            match_id = str(m["MatchID"])
                            status = self.get_match_status(m)
    
                            # =============================
                            # FUTURE MATCHES
                            # =============================
                            if status == 'future':
                                continue
    
                            # =============================
                            # LIVE MATCHES
                            # =============================
                            if status == 'live':
                                print(f"Match {match_id} 🔴 LIVE - Fetching latest data")
                                self.update_match_data(match_id)
                                self.compute_player_points_for_match(match_id)
                                self.compute_points_for_match(match_id)
                                continue
    
                            # =============================
                            # COMPLETED MATCHES
                            # =============================
                            if status == 'over':
                                # Check if already computed
                                already_computed = False
                                for contestant in self.contestants.values():
                                    key = (contestant.mobile, match_id)
                                    if key in computed_points:
                                        already_computed = True
                                        break
    
                                if already_computed:
                                    print(f"    ✅ Already computed (skipping)")
                                    # Load existing points
                                    for contestant in self.contestants.values():
                                        key = (contestant.mobile, match_id)
                                        if key in computed_points:
                                            contestant.points[match_id] = computed_points[key]
                                else:
                                    print(f"    🔵 FINISHED - Computing points for first time")
                                    self.update_match_data(match_id)
                                    self.compute_player_points_for_match(match_id)
                                    self.compute_points_for_match(match_id)
    
                        # =============================
                        # PERSIST TO SHEETS (EVERY LOOP)
                        # =============================
                        print("\n💾 Persisting to sheets...")
                        self.persist_to_sheets()
                        self.persist_player_points_to_sheets()
    
                    except Exception as e:
                        print(f"❌ Scheduler error: {e}")
                        import traceback
                        traceback.print_exc()
    
                    time.sleep(60)
    
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
    
        # -------------------------
        # SAVE TO GOOGLE SHEETS
        # -------------------------
        def persist_to_sheets(self):
    
            print("💾 Persisting all contestant points...")
    
            rows = []
    
            now_str = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    
            for contestant in self.contestants.values():
                for match_id, pts in contestant.points.items():
    
                    rows.append([
                        contestant.name,
                        contestant.mobile,
                        match_id,
                        round(pts, 2),
                        now_str
                    ])
    
            if not rows:
                print("⚠️  No data to persist")
                return
    
            try:
                sheet = client.open("FantasyCricket").worksheet("ContestantPoints")
            except:
                sheet = client.open("FantasyCricket").add_worksheet(
                    title="ContestantPoints",
                    rows="1000",
                    cols="10"
                )
    
            # Header
            all_values = sheet.get_all_values()
            if not all_values:
                sheet.append_row([
                    "User",
                    "Mobile",
                    "MatchID",
                    "Points",
                    "LastUpdated"
                ])
    
            # Clear old data - delete all rows except header (row 1)
            if len(all_values) > 1:
                sheet.delete_rows(2, len(all_values))
    
            # Write new data - append all new rows
            if rows:
                sheet.append_rows(rows)
    
            print(f"✅ Persisted {len(rows)} rows")
    
        # -------------------------
        # SAVE PLAYER POINTS TO GOOGLE SHEETS
        # -------------------------
        def persist_player_points_to_sheets(self):
    
            print("💾 Persisting player points...")
    
            rows = []
    
            now_str = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    
            # Iterate through each match and its player points
            for match_id, player_points in self.player_points.items():
                match = self.matches.get(match_id)
                if not match:
                    continue
    
                for pid, points in player_points.items():
                    player = match.players.get(pid)
                    player_info = self.registry.players.get(pid)
    
                    if not player_info:
                        continue
    
                    rows.append([
                        match_id,
                        pid,
                        player.name,
                        player_info.get("Team", ""),
                        player_info.get("Role", ""),
                        round(points, 2),
                        now_str
                    ])
    
            if not rows:
                print("⚠️  No player points to persist")
                return
    
            try:
                sheet = client.open("FantasyCricket").worksheet("PlayerPoints")
            except:
                sheet = client.open("FantasyCricket").add_worksheet(
                    title="PlayerPoints",
                    rows="5000",
                    cols="10"
                )
    
            # Header
            all_values = sheet.get_all_values()
            if not all_values:
                sheet.append_row([
                    "MatchID",
                    "PlayerID",
                    "PlayerName",
                    "Team",
                    "Role",
                    "Points",
                    "LastUpdated"
                ])
    
            # Clear old data - delete all rows except header (row 1)
            if len(all_values) > 1:
                sheet.delete_rows(2, len(all_values))
    
            # Write new data - append all new rows
            if rows:
                sheet.append_rows(rows)
    
            print(f"✅ Persisted {len(rows)} player points")
    
    # 🔐 Check if match locked
    #def is_match_locked(match_datetime_str):
    #    match_time = datetime.strptime(match_datetime_str, "%Y-%m-%d %H:%M")
    #    match_time = ist.localize(match_time)
    #    if TEST_MODE:
    #        now = ist.localize(datetime(2025, TEST_MODE_MONTH, TEST_MODE_DATE, TEST_MODE_TIME_HR, TEST_MODE_TIME_MIN))
    #    else:
    #        now = datetime.now(ist)
    #    return now >= match_time
    
    # 🏠 LOGIN PAGE
    @app.get("/", response_class=HTMLResponse)
    def login_page():
        return """
        <h1>🏏 Hippies Mahasangram Login</h1>
        <form action="/login" method="post">
            Mobile Number: <input type="text" name="mobile" required><br><br>
            Password: <input type="password" name="password" required><br><br>
            <button type="submit">Login</button>
        </form>
        """
    
    # 🔐 LOGIN API
    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, mobile: str = Form(...), password: str = Form(...)):
        users = get_cached_data("users")
    
        mobile = str(mobile).strip()
        password = str(password).strip()
    
        for u in users:
            sheet_mobile = str(u["Mobile"]).strip()
            sheet_password = str(u.get("Password", "")).strip()
            allowed = str(u["Allowed"]).strip().lower()
    
            if sheet_mobile == mobile and sheet_password == password and allowed == "true":
                name = u["Name"]
                
                # Set session
                request.session['mobile'] = mobile
                request.session['name'] = name
                
                # Show match list
                matches = get_cached_data("matches")
                html = f"""
                       <h2>Welcome {name}</h2>
                       <a href="/change-password"
                          style="padding:8px 14px; background:#dc3545; color:white; text-decoration:none; border-radius:6px;">
                          🔑 Change Password
                       </a>
                       <br><br>
                       <a href="/leaderboard"
                          style="padding:8px 14px; background:#ff9800; color:white; text-decoration:none; border-radius:6px;">
                          🏆 Leaderboard
                       </a>
                       <br><br>
                       """
                       
                html += """
                <a href="/points-table"
                   style="padding:8px 14px; background:#6f42c1; color:white; text-decoration:none; border-radius:6px;">
                   📊 Points Table
                </a>
                
                <br><br>
                <a href="/logout"
                   style="padding:8px 14px; background:#6c757d; color:white; text-decoration:none; border-radius:6px;">
                   🚪 Logout
                </a>
                
                <br><br>
                """
                
                
    
                for m in matches:
                    locked = is_match_locked_by_row(m)
    
                    if locked:
                        action_button = f"""
                                        <a href="/view-scores?match_id={m['MatchID']}"
                                           style="padding:6px 12px; background:#28a745; color:white; text-decoration:none; border-radius:5px;">
                                           View Scores
                                        </a>
                                        """
                    else:
                        action_button = f"""
                                        <a href="/select-team?match_id={m['MatchID']}"
                                           style="padding:6px 12px; background:#007bff; color:white; text-decoration:none; border-radius:5px;">
                                           Select Team
                                        </a>
                                        """
    
                    html += f"""
                            <div style="display:flex; align-items:center; gap:20px; margin-bottom:12px;">
                            
                                <div style="font-size:18px;">
                                    <b>Match {m['MatchID']}</b>
                                </div>
                            
                                <div style="font-size:18px;">
                                    {m['Team1']} vs {m['Team2']}
                                </div>
                            
                                <div>
                                    {action_button}
                                </div>
                            
                            </div>
                            """
    
                return html
    
        return "<h3>❌ Invalid credentials or not allowed</h3>"
    
    # 🚪 LOGOUT
    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/", status_code=302)
    
    # 🔑 CHANGE PASSWORD PAGE
    @app.get("/change-password", response_class=HTMLResponse)
    def change_password_page(request: Request):
        mobile = request.session.get('mobile')
        if not mobile:
            return RedirectResponse(url="/", status_code=302)
        
        return f"""
        <h1>🔑 Change Password</h1>
        <form action="/change-password" method="post">
            Current Password: <input type="password" name="current_password" required><br><br>
            New Password: <input type="password" name="new_password" required><br><br>
            Confirm New Password: <input type="password" name="confirm_password" required><br><br>
            <button type="submit">Change Password</button>
        </form>
        <br><a href='javascript:window.history.back()'>⬅ Back</a>
        """
    
    # 🔑 CHANGE PASSWORD API
    @app.post("/change-password", response_class=HTMLResponse)
    def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
        mobile = request.session.get('mobile')
        if not mobile:
            return RedirectResponse(url="/", status_code=302)
        
        if new_password != confirm_password:
            return "<h3>❌ New passwords do not match</h3>"
    
        users = get_cached_data("users")
        current_password = str(current_password).strip()
        new_password = str(new_password).strip()
    
        # Find the user
        user_row = None
        row_index = 0
        for idx, u in enumerate(users, start=2):  # Assuming header is row 1
            if str(u["Mobile"]).strip() == mobile:
                user_row = u
                row_index = idx
                break
    
        if not user_row or str(user_row.get("Password", "")).strip() != current_password:
            return "<h3>❌ Current password is incorrect</h3>"
    
        # Update the password in the sheet
        try:
            sheet = client.open("FantasyCricket").worksheet("Users")
            sheet.update_cell(row_index, 4, new_password)  # Assuming Password is column D (4th column)
            return "<h3>✅ Password changed successfully</h3><br><a href='/'>⬅ Back to Dashboard</a>"
        except Exception as e:
            return f"<h3>❌ Error updating password: {str(e)}</h3>"
        
    
    # 🧾 TEAM SELECTION PAGE
    @app.get("/select-team", response_class=HTMLResponse)
    def select_team(request: Request, match_id: str):
        mobile = request.session.get('mobile')
        if not mobile:
            return RedirectResponse(url="/", status_code=302)
        
        from datetime import datetime
        import pytz
    
        matches = get_cached_data("matches")
        match = next((m for m in matches if int(m["MatchID"]) == int(match_id)), None)
    
        if not match:
            return "<h3>❌ Match not found</h3>"
    
        team1 = match["Team1"]
        team2 = match["Team2"]
    
        try:
            match_datetime = datetime.strptime(
                f"{match['Date']} {match['Time']}",
                "%Y-%m-%d %H:%M"
            )
            match_datetime = ist.localize(match_datetime)
        except Exception as e:
            return f"<h3>❌ Invalid match time format: {e}</h3>"
    
        if TEST_MODE:
            now = ist.localize(datetime(2025, TEST_MODE_MONTH, TEST_MODE_DATE, TEST_MODE_TIME_HR, TEST_MODE_TIME_MIN))
        else:
            now = datetime.now(ist)
    
        if now >= match_datetime:
            return "<h3>⛔ Match locked</h3>"
    
        # 🏏 Filter players
        players = [
            p for p in get_cached_data("players")
            if p["Team"] in [team1, team2]
        ]
        
        seen = set()
        unique_players = []
        
        for p in players:
            key = (p["Name"], p["Team"])
            if key not in seen:
                seen.add(key)
                unique_players.append(p)
    
        players = unique_players
    
        grouped = {role: [] for role in ROLES}
    
        for p in players:
            if p["Role"] in grouped:
                grouped[p["Role"]].append(p)
    
        html = f"""
        <h2>{team1} vs {team2}</h2>
        <h3>Select 11 Players</h3>
    
        <form method="post" action="/submit-team" onsubmit="return validateForm()">
        <input type="hidden" name="match_id" value="{match_id}">
        """
    
        def render_section(title, plist):
            section = f"<h3>{title}</h3>"
            section += """
            <table cellpadding="5">
                <tr>
                    <th>Select</th>
                    <th>C</th>
                    <th>VC</th>
                    <th>Player</th>
                </tr>
            """
    
            for p in plist:
                section += f"""
                <tr>
                    <td>
                        <input type="checkbox"
                         class="player-checkbox"
                         data-role="{p['Role']}"
                         name="players"
                         value="{p['PlayerID']}"
                         onchange="toggleRadio(this); limitSelection()">
                    </td>
                    <td>
                        <input type="radio" name="captain" value="{p['PlayerID']}" id="c{p['PlayerID']}" disabled>
                    </td>
                    <td>
                        <input type="radio" name="vice_captain" value="{p['PlayerID']}" id="vc{p['PlayerID']}" disabled>
                    </td>
                    <td>{p['Name']} ({p['Team']})</td>
                </tr>
                """
            section += "</table><br>"
            return section
    
        html += render_section("Wicketkeepers", grouped["Wicketkeeper"])
        html += render_section("Batter", grouped["Batter"])
        html += render_section("AllRounder", grouped["AllRounder"])
        html += render_section("Bowlers", grouped["Bowler"])
    
        # 🧠 JAVASCRIPT LOGIC
        html += f"""
    <script>
    const ROLES = {ROLES};
    """
    
        html +="""
    function validateForm() {
        let selected = document.querySelectorAll(".player-checkbox:checked");
    
        if (selected.length !== 11) {
            alert("Select exactly 11 players");
            return false;
        }
    
        let captain = document.querySelector("input[name='captain']:checked");
        let vc = document.querySelector("input[name='vice_captain']:checked");
    
        if (!captain) {
            alert("Please select a Captain");
            return false;
        }
    
        if (!vc) {
            alert("Please select a Vice Captain");
            return false;
        }
    
        if (captain.value === vc.value) {
            alert("Captain and Vice Captain cannot be same");
            return false;
        }
    
        return true;
    }
    function toggleRadio(checkbox) {
        let row = checkbox.closest("tr");
    
        let cap = row.querySelector("input[name='captain']");
        let vc = row.querySelector("input[name='vice_captain']");
    
        if (checkbox.checked) {
            cap.disabled = false;
            vc.disabled = false;
        } else {
            cap.checked = false;
            vc.checked = false;
            cap.disabled = true;
            vc.disabled = true;
        }
    }
    function limitSelection() {
        let checkboxes = document.querySelectorAll(".player-checkbox");
        let checked = document.querySelectorAll(".player-checkbox:checked");
    
        let total = checked.length;
    
        // 🔴 STEP 1: HARD LIMIT (FIRST)
        if (total > 11) {
            alert("You can select only 11 players");
    
            let last = checked[checked.length - 1];
            last.checked = false;
    
            return limitSelection();
        }
    
        let roleCount = {};
        ROLES.forEach(role => roleCount[role] = 0);
    
        // Count roles safely
        checked.forEach(cb => {
            let role = cb.getAttribute("data-role");
            if (roleCount.hasOwnProperty(role)) {
                roleCount[role]++;
            }
        });
    
        let remaining = 11 - total;
        let missingRoles = [];
    
        ROLES.forEach(role => {
            if (!roleCount[role]) {
                missingRoles.push(role);
            }
        });
    
        // 🔒 STEP 2: Prevent invalid final combination
        if (total === 11 && missingRoles.length > 0) {
            alert("You must select at least 1 player from each category");
    
            let last = checked[checked.length - 1];
            last.checked = false;
    
            return limitSelection();
        }
    
        // 🔒 STEP 3: Smart restriction
        if (remaining === missingRoles.length) {
            checkboxes.forEach(cb => {
                let role = cb.getAttribute("data-role");
    
                if (!cb.checked && !missingRoles.includes(role)) {
                    cb.disabled = true;
                } else {
                    cb.disabled = false;
                }
            });
            return;
        }
    
        // 🔒 STEP 4: Lock at 11
        if (total === 11) {
            checkboxes.forEach(cb => {
                if (!cb.checked) cb.disabled = true;
            });
            return;
        }
    
        // 🔓 STEP 5: Default
        checkboxes.forEach(cb => {
            cb.disabled = false;
        });
    }
    
    // Prevent same Captain & VC
    document.addEventListener("change", function(e) {
        if (e.target.name === "captain" || e.target.name === "vice_captain") {
            let captain = document.querySelector("input[name='captain']:checked");
            let vc = document.querySelector("input[name='vice_captain']:checked");
    
            if (captain && vc && captain.value === vc.value) {
                alert("Captain and Vice Captain cannot be same");
                e.target.checked = false;
            }
        }
    });
    </script>
        """
    
        html += """
        <br>
        <button type="submit">Submit Team</button>
        </form>
        """
    
        return html
    
    
    
    @app.post("/submit-team")
    def submit_team(
        request: Request,
        match_id: str = Form(...),
        players: list[str] = Form(...),
        captain: Optional[str] = Form(None),
        vice_captain: Optional[str] = Form(None)
    ):
        mobile = request.session.get('mobile')
        if not mobile:
            return RedirectResponse(url="/", status_code=302)
    
        users = get_cached_data("users")
        user = next((u for u in users if str(u["Mobile"]) == str(mobile)), None)
    
        if not user:
            return "<h3>❌ User not found</h3>"
    
        name = user["Name"]
        
        # 🟢 STEP 1: CHECK MATCH LOCK
        matches = get_cached_data("matches")
        match = next((m for m in matches if int(m["MatchID"]) == int(match_id)), None)
    
        if not match:
            return "<h3>❌ Match not found</h3>"
    
        match_time = datetime.strptime(
            f"{match['Date']} {match['Time']}",
            "%Y-%m-%d %H:%M"
        )
        if TEST_MODE:
            now = ist.localize(datetime(2025, TEST_MODE_MONTH, TEST_MODE_DATE, TEST_MODE_TIME_HR, TEST_MODE_TIME_MIN))
        else:
            now = datetime.now(ist)
    
        if now > ist.localize(match_time):
            return "<h3>⛔ Team submission closed (match started)</h3>"
    
        # 🟢 STEP 2: VALIDATION RULES
        players_data = get_cached_data("players")
        selected_ids = [int(p) for p in players]
    
        # ❌ Rule 1: Exactly 11 players
        if len(selected_ids) != 11:
            return "<h3>❌ Select exactly 11 players</h3>"
            
        if captain == vice_captain:
            return "<h3>❌ Captain and Vice Captain cannot be same</h3>"
    
        selected_players = [p for p in players_data if int(p["PlayerID"]) in selected_ids]
    
        # Role count
        roles = {role: 0 for role in ROLES}
    
        for p in selected_players:
            role = p["Role"]
            if role in roles:
                roles[role] += 1
    
        # ❌ Role validations
        if roles["Batter"] < 1:
            return "<h3>❌ At least 1 Batter required</h3>"
    
        if roles["Bowler"] < 1:
            return "<h3>❌ At least 1 Bowler required</h3>"
    
        if roles["AllRounder"] < 1:
            return "<h3>❌ At least 1 AllRounder required</h3>"
    
        if roles["Wicketkeeper"] < 1:
            return "<h3>❌ At least 1 Wicketkeeper required</h3>"
            
        if not captain:
            return "<h3>❌ Captain not selected</h3>"
    
        if not vice_captain:
            return "<h3>❌ Vice Captain not selected</h3>"
    
        # ❌ Captain validation
        if int(captain) not in selected_ids:
            return "<h3>❌ Captain must be selected</h3>"
    
        if int(vice_captain) not in selected_ids:
            return "<h3>❌ Vice Captain must be selected</h3>"
    
        if captain == vice_captain:
            return "<h3>❌ Captain and Vice Captain cannot be same</h3>"
            
        # 🟢 REMOVE OLD TEAM (IF EXISTS)
        all_rows = teams_sheet.get_all_records()
    
        rows_to_delete = []
    
        for idx, row in enumerate(all_rows, start=2):  # row 1 = header
            if str(row["Mobile"]) == str(mobile) and int(row["MatchID"]) == int(match_id):
                rows_to_delete.append(idx)
    
        # ⚠️ Delete from bottom to top
        for r in reversed(rows_to_delete):
            teams_sheet.delete_rows(r)
    
        # 🟢 STEP 4: SAVE NEW TEAM
        for pid in selected_ids:
            teams_sheet.append_row([
                name,
                mobile,
                match_id,
                pid,
                "TRUE" if str(pid) == captain else "FALSE",
                "TRUE" if str(pid) == vice_captain else "FALSE"
            ])
    
        return "<h3>✅ Team submitted successfully</h3>"
    
    # 👁️ VIEW TEAMS (AFTER LOCK)
    @app.get("/view-teams", response_class=HTMLResponse)
    def view_teams(match_id: str):
    
        matches = matches_sheet.get_all_records()
        match = next((m for m in matches if int(m["MatchID"]) == int(match_id)), None)
        
        if not match:
            return "<h3>❌ Match not found</h3>"
    
        if not is_match_locked(match["DateTime"]):
            return "<h3>🔒 Teams will be visible after match starts</h3>"
    
        teams = teams_sheet.get_all_records()
    
        html = "<h2>All Teams</h2>"
    
        for t in teams:
            if int(t["MatchID"]) == int(match_id):
                html += f"{t['User']} - Player {t['PlayerID']}<br>"
    
        return html
        
    @app.get("/view-scores", response_class=HTMLResponse)
    def view_scores(match_id: str):
    
        html = f"""
        <h2>Match {match_id} - Live Score</h2>
    
        <div id="loader">Loading scores...</div>
        <div id="score-container" style="display:none"></div>
    
        <br><a href='javascript:window.history.back()'>⬅ Back</a>
    
        <script>
        async function loadScores() {{
            const loader = document.getElementById('loader');
            const container = document.getElementById('score-container');
            loader.style.display = 'block';
            container.style.display = 'none';
    
            try {{
                let res = await fetch('/match-score-data?match_id={match_id}');
                let data = await res.json();
    
                let html = "";
    
                data.forEach(p => {{
                    html += `
                    <div style="margin-bottom:6px;">
                        <b>${{p.name}}</b> -
                        ${{p.runs}}(${{p.balls}})
                        | Wkts: ${{p.wickets}}
                        | Catches: ${{p.catches}}
                    </div>
                    `;
                }});
    
                document.getElementById("score-container").innerHTML = html;
                loader.style.display = 'none';
                container.style.display = 'block';
    
            }} catch (e) {{
                console.log("Error loading scores", e);
                loader.textContent = 'Error loading scores. Please try again.';
            }}
        }}
    
        // Initial load
        loadScores();
    
        // Auto refresh every 10 sec
        setInterval(loadScores, 10000);
        </script>
        """
    
        return html
        
    tournament = Tournament()
    
    @app.on_event("startup")
    def startup():
    
        try:
            players_data = players_sheet.get_all_records()
            matches_data = matches_sheet.get_all_records()
            teams_data = teams_sheet.get_all_records()
    
            tournament.initialize(players_data, matches_data, teams_data)
    
            tournament.start_scheduler()
        except Exception as e:
            print("ERROR DURING STARTUP:")
            traceback.print_exc()
        
    @app.get("/leaderboard", response_class=HTMLResponse)
    def leaderboard():
    
        html = """
        <h2>🏆 Leaderboard</h2>
    
        <div id="loader">Loading leaderboard...</div>
        <div id="leaderboard" style="display:none"></div>
    
        <br><a href='javascript:window.history.back()'>⬅ Back</a>
    
        <script>
            let previousRanks = {};
    
            async function loadLeaderboard() {
                const loader = document.getElementById('loader');
                const board = document.getElementById('leaderboard');
                loader.style.display = 'block';
                board.style.display = 'none';
    
                try {
                    let res = await fetch('/leaderboard-data');
                    let data = await res.json();
    
                    let html = "";
                    let rank = 1;
    
                    data.forEach(user => {
                        let prevRank = previousRanks[user.name];
                        let movement = "";
                        let color = "black";
    
                        if (prevRank) {
                            if (rank < prevRank) {
                                movement = "⬆";
                                color = "green";
                            } else if (rank > prevRank) {
                                movement = "⬇";
                                color = "red";
                            }
                        }
    
                        let className = "";
                        if (prevRank !== undefined) {
                            if (rank < prevRank) className = "flash-up";
                            if (rank > prevRank) className = "flash-down";
                        }
    
                        html += `<div class="${className}" style="margin-bottom:8px; color:${color}; transition:0.3s;">
                            <b>#${rank}</b> ${movement} &nbsp;
                            ${user.name} &nbsp;&nbsp;
                            <span>${user.points.toFixed(2)} pts</span>
                        </div>`;
    
                        previousRanks[user.name] = rank;
                        rank++;
                    });
    
                    board.innerHTML = html;
                    loader.style.display = 'none';
                    board.style.display = 'block';
    
                } catch (e) {
                    console.log('Error loading leaderboard', e);
                    loader.textContent = 'Error loading leaderboard. Please try again.';
                }
            }
    
            // Initial load
            loadLeaderboard();
    
            // Refresh every 15 sec
            setInterval(loadLeaderboard, 15000);
        </script>
        <style>
            .flash-up {
                animation: flashGreen 0.5s;
            }
            .flash-down {
                animation: flashRed 0.5s;
            }
            
            @keyframes flashGreen {
                from { background-color: #d4edda; }
                to { background-color: transparent; }
            }
            
            @keyframes flashRed {
                from { background-color: #f8d7da; }
                to { background-color: transparent; }
            }
        </style>
        """
    
        return html
        
        
    @app.get("/points-table", response_class=HTMLResponse)
    def points_table():
        html = """
        <h2>📊 Match-wise Points</h2>
    
        <div id="loader">Loading points table...</div>
        <div id="points-container" style="display:none"></div>
    
        <br><a href='javascript:window.history.back()'>⬅ Back</a>
    
        <script>
        async function loadPointsTable() {
            const loader = document.getElementById('loader');
            const container = document.getElementById('points-container');
    
            loader.style.display = 'block';
            container.style.display = 'none';
    
            try {
                let res = await fetch('/points-table-data');
                let data = await res.json();
    
                if (!data.length) {
                    loader.textContent = 'No data available';
                    return;
                }
    
                let html = '';
                data.forEach(row => {
                    html += `
                    <div style="margin-bottom:6px;">
                        <b>${row.User}</b> &nbsp; | Match ${row.MatchID} &nbsp; | <span style="color:blue;">${row.Points} pts</span>
                    </div>
                    `;
                });
    
                container.innerHTML = html;
                loader.style.display = 'none';
                container.style.display = 'block';
    
            } catch (e) {
                console.log('Error loading points table', e);
                loader.textContent = 'Error loading points table. Please try again.';
            }
        }
    
        loadPointsTable();
        </script>
        """
    
        return html
    
    @app.get('/points-table-data')
    def points_table_data():
        try:
            sheet = client.open('FantasyCricket').worksheet('ContestantPoints')
            data = sheet.get_all_records()
            return JSONResponse(data)
        except Exception:
            return JSONResponse([])
    
    @app.get("/leaderboard-data")
    def leaderboard_data():
    
        try:
            sheet = client.open("FantasyCricket").worksheet("ContestantPoints")
            data = sheet.get_all_records()
        except:
            return JSONResponse([])
    
        totals = {}
    
        for row in data:
            mobile = str(row["Mobile"])
            name = row["User"]
            pts = float(row["Points"])
    
            if mobile not in totals:
                totals[mobile] = {"name": name, "points": 0}
    
            totals[mobile]["points"] += pts
    
        sorted_users = sorted(
            totals.values(),
            key=lambda x: x["points"],
            reverse=True
        )
    
        return JSONResponse(sorted_users)
    
    @app.get("/match-score-data")
    def match_score_data(match_id: str):
    
        matches = get_cached_data("matches")
        match_row = next((m for m in matches if str(m["MatchID"]) == str(match_id)), None)
    
        if not match_row:
            return JSONResponse({"error": "Match not found"})
    
        players_data = get_cached_data("players")
        registry = PlayerRegistry(players_data)
    
        match_obj = Match(
            match_id,
            clean_team_name(match_row["Team1"]),
            clean_team_name(match_row["Team2"]),
            registry
        )
        print("Parsed players:", len(match_obj.players))
    
    
        match_code = int(match_id) + MATCH_CODE_OFFSET
        html_content = fetch_scorecard_html(match_code)
    
        if not html_content:
            return JSONResponse({"error": "No data"})
    
        # ✅ FIX HERE
        soup = BeautifulSoup(html_content, "html.parser")
        match_obj.parse_scorecard(soup)
    
        players = match_obj.players
        
        
        result = []
    
        for p in players.values():
            result.append({
                "name": p.name,
                "runs": p.runs,
                "balls": p.balls,
                "wickets": p.wickets,
                "catches": p.catches
            })
    
        return JSONResponse(result)
        
    @app.get("/debug")
    def debug():
    
        for match_id in tournament.matches:
            tournament.update_match_data(match_id)
    
        tournament.compute_all_points()
    
        return [
            {
                "name": c.name,
                "points": c.points
            }
            for c in tournament.contestants.values()
        ]

except Exception as e:
    print("❌ STARTUP ERROR:")
    traceback.print_exc()
    raise e