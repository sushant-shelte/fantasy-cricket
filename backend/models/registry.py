class PlayerRegistry:
    def __init__(self, players_data):
        self.players = {}   # pid -> full row
        self.lookup = {}    # (team, normalized full name/alias) -> pid
        self.first_name_lookup = {}  # (team, first_name) -> set[pids]
        self.last_name_lookup = {}   # (team, last_name) -> set[pids]
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
                    self.first_name_lookup.setdefault((team, parts[0]), set()).add(pid)
                    self.last_name_lookup.setdefault((team, parts[-1]), set()).add(pid)

    def get_player_id(self, name, team):
        normalized_name = self.normalize(name)

        # Try whole name
        if (team, normalized_name) in self.lookup:
            return self.lookup[(team, normalized_name)]

        parts = normalized_name.split()
        if len(parts) > 1:
            first_name_matches = self.first_name_lookup.get((team, parts[0]), set())
            last_name_matches = self.last_name_lookup.get((team, parts[-1]), set())
            combined_matches = first_name_matches & last_name_matches
            if len(combined_matches) == 1:
                return next(iter(combined_matches))
        elif len(parts) == 1:
            first_name_matches = self.first_name_lookup.get((team, parts[0]), set())
            if len(first_name_matches) == 1:
                return next(iter(first_name_matches))

            last_name_matches = self.last_name_lookup.get((team, parts[0]), set())
            if len(last_name_matches) == 1:
                return next(iter(last_name_matches))

        print(f"Player mapping not found: '{name}' (team: {team})")
        return None
