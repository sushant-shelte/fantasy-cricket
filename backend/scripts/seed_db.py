"""
Seed the SQLite database from the JSON files in data/.

Usage (from the project root):
    python -m backend.scripts.seed_db

Reads:
    data/players.json  -> players table
    data/matches.json  -> matches table
    data/users.json    -> users table  (firebase_uid = "dev_<mobile>",
                                        email = "<name>@dev.local")

The first user is created with role='admin'; the rest get role='user'.
"""

import json
import os
import sys

# Allow running as ``python backend/scripts/seed_db.py`` from the project root
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from backend.database import init_db, get_db
from backend.config import DATA_DIR


def _read_json(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  [skip] {path} not found")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_players(db):
    players = _read_json("players.json")
    if not players:
        return
    print(f"  Seeding {len(players)} players ...")
    for p in players:
        db.execute(
            """INSERT OR REPLACE INTO players (id, name, team, role, aliases)
               VALUES (?, ?, ?, ?, ?)""",
            (
                int(p["PlayerID"]),
                p["Name"],
                p["Team"],
                p["Role"],
                p.get("Aliases", ""),
            ),
        )
    db.commit()


def seed_matches(db):
    matches = _read_json("matches.json")
    if not matches:
        return
    print(f"  Seeding {len(matches)} matches ...")
    for m in matches:
        db.execute(
            """INSERT OR REPLACE INTO matches (id, team1, team2, match_date, match_time)
               VALUES (?, ?, ?, ?, ?)""",
            (
                int(m["MatchID"]),
                m["Team1"],
                m["Team2"],
                m["Date"],
                m["Time"],
            ),
        )
    db.commit()


def seed_users(db):
    users = _read_json("users.json")
    if not users:
        return
    print(f"  Seeding {len(users)} users ...")
    for idx, u in enumerate(users):
        mobile = str(u["Mobile"]).strip()
        name = u["Name"].strip()
        firebase_uid = f"dev_{mobile}"
        email = f"{name.lower()}@dev.local"
        role = "admin" if idx == 0 else "user"

        db.execute(
            """INSERT OR REPLACE INTO users
                   (firebase_uid, email, name, mobile, role, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (firebase_uid, email, name, mobile, role),
        )
    db.commit()


def main():
    print("Initialising database schema ...")
    init_db()

    db = get_db()

    print("Seeding data from JSON files ...")
    seed_players(db)
    seed_matches(db)
    seed_users(db)

    # Quick verification
    player_count = db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    match_count = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"\nDone.  players={player_count}  matches={match_count}  users={user_count}")


if __name__ == "__main__":
    main()
