import re


def is_batting_role(role):
    return role in ("Batter", "Wicketkeeper", "AllRounder")


class Player:
    def __init__(self, player_id, name):
        self.player_id = player_id
        self.name = name
        self.team = None

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

        self.played = False
        self.points = 0
        self.role = None

    # --- Dismissal parser ---

    def apply_dismissal(self, dismissal_text, match, bowling_team=None):
        self.dismissal = dismissal_text.strip()

        if self.dismissal.lower() == "not out":
            self.is_out = False
            return

        self.is_out = True

        def get_player(name):
            if bowling_team:
                return match.get_player_by_team(name, bowling_team)
            return match.get_player_by_name(name)

        # Caught
        if self.dismissal.startswith("c "):
            m = re.search(r"c\s+(.+?)\s+b\s+(.+)", self.dismissal)
            if m:
                fielder = get_player(m.group(1))
                bowler = get_player(m.group(2))
                if fielder:
                    fielder.catches += 1
                if bowler:
                    bowler.wickets += 1
            return

        # Bowled
        if self.dismissal.startswith("b "):
            bowler = get_player(self.dismissal.replace("b ", "").strip())
            if bowler:
                bowler.wickets += 1
                bowler.bowled += 1
            return

        # LBW
        if self.dismissal.startswith("lbw"):
            m = re.search(r"lbw\s+b\s+(.+)", self.dismissal)
            if m:
                bowler = get_player(m.group(1))
                if bowler:
                    bowler.wickets += 1
                    bowler.lbw += 1
            return

        # Stumping
        if self.dismissal.startswith("st"):
            m = re.search(r"st\s+(.+?)\s+b\s+(.+)", self.dismissal)
            if m:
                fielder = get_player(m.group(1))
                bowler = get_player(m.group(2))
                if fielder:
                    fielder.stumpings += 1
                    fielder.runout_direct += 1
                if bowler:
                    bowler.wickets += 1
            return

        # Run out
        if "run out" in self.dismissal.lower():
            m = re.search(r"\((.*?)\)", self.dismissal)
            if m:
                fielders = [f.strip() for f in m.group(1).split("/")]
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

    # --- Points engine ---

    def calculate_player_points(self, role: str):
        points = 0
        self.role = role

        # Playing
        if self.played:
            points += 4

        # Batting: runs
        points += self.runs

        # Boundaries
        points += self.fours * 4
        points += self.sixes * 6

        # Milestones
        if self.runs >= 100:
            points += 16
        elif self.runs >= 50:
            points += 8
        elif self.runs >= 30:
            points += 4

        # Duck
        if self.runs == 0 and self.is_out and is_batting_role(role):
            points -= 2

        # Strike rate (min 10 balls, batting roles only)
        if self.balls >= 10 and is_batting_role(role):
            sr = self.strike_rate
            if sr > 170:
                points += 6
            elif sr > 150:
                points += 4
            elif sr >= 130:
                points += 2
            elif sr <= 50:
                points -= 6
            elif sr < 60:
                points -= 4
            elif sr <= 70:
                points -= 2

        # Bowling: wickets
        points += self.wickets * 30

        # Wicket haul bonus
        if self.wickets >= 5:
            points += 16
        elif self.wickets == 4:
            points += 8
        elif self.wickets == 3:
            points += 4

        # Maidens
        points += self.maidens * 12

        # Economy (min 2 overs)
        if self.overs >= 2:
            eco = self.economy
            if eco < 5:
                points += 6
            elif eco < 6:
                points += 4
            elif eco <= 7:
                points += 2
            elif eco > 12:
                points -= 6
            elif eco > 11:
                points -= 4
            elif eco >= 10:
                points -= 2

        # Fielding
        points += self.catches * 8
        if self.catches >= 3:
            points += 4
        points += self.stumpings * 12
        points += self.runout_direct * 12
        points += self.runout_indirect * 6

        self.points = points
        return points
