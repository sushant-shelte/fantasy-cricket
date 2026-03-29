import sqlite3
import threading
from backend.config import DATABASE_PATH

_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firebase_uid TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            mobile TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            team TEXT NOT NULL,
            role TEXT NOT NULL,
            aliases TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            match_date TEXT NOT NULL,
            match_time TEXT NOT NULL,
            status TEXT DEFAULT 'future'
        );

        CREATE TABLE IF NOT EXISTS user_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            match_id INTEGER NOT NULL REFERENCES matches(id),
            player_id INTEGER NOT NULL REFERENCES players(id),
            is_captain INTEGER NOT NULL DEFAULT 0,
            is_vice_captain INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, match_id, player_id)
        );

        CREATE TABLE IF NOT EXISTS contestant_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            match_id INTEGER NOT NULL REFERENCES matches(id),
            points REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL,
            UNIQUE(user_id, match_id)
        );

        CREATE TABLE IF NOT EXISTS player_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL REFERENCES matches(id),
            player_id INTEGER NOT NULL REFERENCES players(id),
            player_name TEXT NOT NULL,
            team TEXT NOT NULL,
            role TEXT NOT NULL,
            points REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL,
            UNIQUE(match_id, player_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_teams_user_match ON user_teams(user_id, match_id);
        CREATE INDEX IF NOT EXISTS idx_contestant_points_match ON contestant_points(match_id);
        CREATE INDEX IF NOT EXISTS idx_player_points_match ON player_points(match_id);
        CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
    """)
    conn.commit()
    conn.close()
