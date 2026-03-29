class Team:
    def __init__(self, match_id, player_ids=None, captain=None, vice_captain=None):
        self.match_id = match_id
        self.player_ids = set(player_ids or [])
        self.captain = captain
        self.vice_captain = vice_captain

    def calculate_team_points(self, match, player_roles):
        total = 0
        for pid in self.player_ids:
            player = match.players.get(pid)
            if not player:
                continue

            role = player_roles.get(pid)
            if not role:
                continue

            pts = player.calculate_player_points(role)

            if pid == self.captain:
                pts *= 2
            elif pid == self.vice_captain:
                pts *= 1.5

            total += pts
        return total


class Contestant:
    def __init__(self, name, mobile="", user_id=None, is_active=True):
        self.name = name
        self.mobile = mobile
        self.user_id = user_id
        self.is_active = is_active
        self.teams = {}   # match_id -> Team
        self.points = {}  # match_id -> points

    def add_team(self, team: Team):
        self.teams[team.match_id] = team

    def calculate_points_for_match(self, match, player_roles):
        team = self.teams.get(match.match_id)
        if not team:
            return 0
        pts = team.calculate_team_points(match, player_roles)
        self.points[match.match_id] = pts
        return pts
