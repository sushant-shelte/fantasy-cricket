import re
from bs4 import BeautifulSoup
from backend.models.player import Player
from backend.models.registry import PlayerRegistry
from backend.config import TEAM_MAP


def clean_name(name):
    return re.sub(r"[†*]", "", name).strip()


def clean_team_name(name):
    name = re.sub(r"\(.*?\)", "", name).strip()
    name = " ".join(name.split())
    short = TEAM_MAP.get(name)
    if not short:
        print("Team mapping missing for:", name)
        return name
    return short


class Match:
    def __init__(self, match_id, team1, team2, registry: PlayerRegistry):
        self.match_id = match_id
        self.team1 = team1
        self.team2 = team2
        self.registry = registry
        self.players = {}  # pid -> Player

    def get_player_id(self, name, team):
        return self.registry.get_player_id(clean_name(name), team)

    def get_or_create_player(self, pid):
        if not pid:
            return None
        if pid not in self.players:
            player_data = self.registry.players.get(pid, {})
            full_name = player_data.get("Name", "Unknown")
            self.players[pid] = Player(pid, full_name)
        return self.players[pid]

    def get_player_by_name(self, name):
        name = clean_name(name)
        pid = (self.registry.get_player_id(name, self.team1)
               or self.registry.get_player_id(name, self.team2))
        if not pid:
            return None
        return self.get_or_create_player(pid)

    def get_player_by_team(self, name, team):
        name = clean_name(name)
        pid = self.registry.get_player_id(name, team)
        if not pid:
            return None
        return self.get_or_create_player(pid)

    # --- Scorecard parser ---

    def parse_scorecard(self, soup: BeautifulSoup):
        self.players = {}

        def get_table_rows(table):
            return [row for row in table.find_all("tr") if row.find_parent("table") == table]

        def get_row_cells(row, allowed_tags=("td", "th")):
            cells = []
            for tag in allowed_tags:
                for cell in row.find_all(tag):
                    if cell.find_parent("tr") == row:
                        cells.append(cell)
            return cells

        def is_int_text(value):
            return bool(re.fullmatch(r"\d+", str(value).strip()))

        def is_float_text(value):
            return bool(re.fullmatch(r"\d+(?:\.\d+)?", str(value).strip()))

        def extract_team_names():
            valid_names = []
            seen = set()
            for tag in soup.find_all(class_="ScorecardCountry3"):
                text = clean_team_name(tag.get_text(" ", strip=True))
                if text in TEAM_MAP.values() and text not in seen:
                    seen.add(text)
                    valid_names.append(text)
            return valid_names

        team_names = extract_team_names()
        if len(team_names) < 2:
            print("Teams not found in scorecard")
            return

        team1_clean = team_names[0]
        team2_clean = team_names[1]

        # --- BATTING ---
        batting_tables = []
        seen_tables = set()
        for cell in soup.find_all(["td", "th"]):
            if cell.get_text(" ", strip=True).upper() != "BATTING":
                continue
            table = cell.find_parent("table")
            if not table:
                continue
            table_id = id(table)
            if table_id in seen_tables:
                continue
            seen_tables.add(table_id)
            batting_tables.append(table)

        for i, table in enumerate(batting_tables[:2]):
            batting_team = team1_clean if i == 0 else team2_clean
            bowling_team = team2_clean if batting_team == team1_clean else team1_clean
            innings_started = False

            for r in get_table_rows(table):
                tds = get_row_cells(r, ("td",))
                cols = [c.get_text(" ", strip=True) for c in tds]

                if len(cols) < 7:
                    continue

                first = cols[0].upper()
                if first == "BATTING":
                    if innings_started and batting_team == team1_clean:
                        batting_team = team2_clean
                        bowling_team = team1_clean
                    continue

                if first in ("BOWLING", "TOTAL", "EXTRAS", "DNB", "SR", "R"):
                    continue

                first_td = tds[0] if tds else None
                if not first_td or not first_td.find("a"):
                    continue

                if not all(is_int_text(cols[idx]) for idx in (2, 3, 4, 5)):
                    continue

                name = clean_name(first_td.find("a").get_text(" ", strip=True))
                pid = self.get_player_id(name, batting_team)
                if not pid:
                    continue

                player = self.get_or_create_player(pid)
                innings_started = True

                player.team = batting_team
                player.played = True
                player.runs = int(cols[2])
                player.balls = int(cols[3])
                player.fours = int(cols[4])
                player.sixes = int(cols[5])

                if player.balls > 0:
                    player.strike_rate = round((player.runs / player.balls) * 100, 2)

                player.apply_dismissal(cols[1], self, bowling_team)

            # Did Not Bat
            current_batting_team = team1_clean if i == 0 else team2_clean
            for td in table.find_all("td"):
                td_text = td.get_text(" ", strip=True)
                if "Did Not Bat" not in td_text:
                    continue
                next_td = td.find_next_sibling("td")
                if not next_td:
                    continue
                for p in next_td.find_all("a"):
                    name = clean_name(p.get_text(" ", strip=True))
                    pid = self.get_player_id(name, current_batting_team)
                    if not pid:
                        continue
                    player = self.get_or_create_player(pid)
                    player.played = True
                    player.team = current_batting_team

        # --- BOWLING ---
        bowling_tables = soup.find_all(class_="ScorecardBowling")

        for i, table in enumerate(bowling_tables[:2]):
            bowling_team = team2_clean if i == 0 else team1_clean

            for r in get_table_rows(table)[1:]:
                tds = get_row_cells(r, ("td",))
                cols = [c.get_text(" ", strip=True) for c in tds]

                if len(cols) < 5:
                    continue

                first = cols[0].upper()
                if first in ("BOWLING", "TOTAL", "O", "M", "R", "W", "ER", "% WICKETS"):
                    continue

                first_td = tds[0] if tds else None
                if not first_td or not first_td.find("a"):
                    continue

                if not is_float_text(cols[1]) or not all(is_int_text(cols[idx]) for idx in (2, 3, 4)):
                    continue

                name = clean_name(first_td.get_text())
                pid = self.get_player_id(name, bowling_team)
                if not pid:
                    continue

                player = self.get_or_create_player(pid)
                player.team = bowling_team
                player.played = True
                player.overs = float(cols[1])
                player.maidens = int(cols[2])
                player.runs_conceded = int(cols[3])
                player.wickets = int(cols[4])

                if player.overs > 0:
                    player.economy = round(player.runs_conceded / player.overs, 2)

        print(f"Total players parsed: {len(self.players)}")
