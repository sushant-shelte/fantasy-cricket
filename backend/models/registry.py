class PlayerRegistry:
    def __init__(self, players_data):
        self.players = {}   # pid -> full row
        self.lookup = {}    # (team, normalized name) -> pid
        self.build(players_data)

    def normalize(self, name):
        return " ".join(name.lower().replace(".", "").split())

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
                normalized = self.normalize(n)
                self.lookup[(team, normalized)] = pid

                parts = normalized.split()
                if len(parts) > 1:
                    self.lookup.setdefault((team, parts[0]), pid)
                    self.lookup.setdefault((team, parts[-1]), pid)

    def get_player_id(self, name, team):
        normalized_name = self.normalize(name)

        # Try whole name
        if (team, normalized_name) in self.lookup:
            return self.lookup[(team, normalized_name)]

        # Try last name
        parts = normalized_name.split()
        if len(parts) > 1:
            if (team, parts[-1]) in self.lookup:
                return self.lookup[(team, parts[-1])]

        # Try first name
        if parts:
            if (team, parts[0]) in self.lookup:
                return self.lookup[(team, parts[0])]

        print(f"Player mapping not found: '{name}' (team: {team})")
        return None
