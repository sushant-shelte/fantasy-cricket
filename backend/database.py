"""
Database abstraction layer.
- Uses PostgreSQL if DATABASE_URL env var is set (production)
- Falls back to SQLite (local development)

All other files use `?` parameter style. This module wraps PostgreSQL
connections to translate `?` to `%s` automatically.
"""

import os
import re
import sqlite3
import threading
from backend.config import DATABASE_PATH

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_local = threading.local()


class PgRowDict(dict):
    """Dict that also supports attribute-style access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PgCursorWrapper:
    """Wraps psycopg2 cursor to translate ? params to %s."""
    def __init__(self, cursor, conn):
        self._cursor = cursor
        self._conn = conn

    def execute(self, sql, params=None):
        sql = sql.replace("?", "%s")
        self._cursor.execute(sql, params)
        return self

    def executescript(self, sql):
        # Split by semicolons and execute each
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._cursor.execute(stmt)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in self._cursor.description]
        return PgRowDict(zip(cols, row))

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows or not self._cursor.description:
            return []
        cols = [desc[0] for desc in self._cursor.description]
        return [PgRowDict(zip(cols, row)) for row in rows]

    @property
    def lastrowid(self):
        return self._cursor.fetchone()[0] if self._cursor.description else None


class PgConnectionWrapper:
    """Wraps psycopg2 connection to behave like sqlite3.Connection."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cursor = self._conn.cursor()
        sql = sql.replace("?", "%s")
        # For INSERT ... RETURNING id to get lastrowid
        cursor.execute(sql, params)
        return PgCursorWrapper(cursor, self._conn)

    def executescript(self, sql):
        cursor = self._conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor(), self._conn)


def _is_postgres():
    return DATABASE_URL.startswith("postgres")


def get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        if _is_postgres():
            import psycopg2
            url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            _local.conn = PgConnectionWrapper(psycopg2.connect(url))
        else:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _local.conn = conn
    return _local.conn


def init_db():
    if _is_postgres():
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                firebase_uid TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                mobile TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                team TEXT NOT NULL,
                role TEXT NOT NULL,
                aliases TEXT DEFAULT ''
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY,
                team1 TEXT NOT NULL,
                team2 TEXT NOT NULL,
                match_date TEXT NOT NULL,
                match_time TEXT NOT NULL,
                status TEXT DEFAULT 'future'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_teams (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                is_captain INTEGER NOT NULL DEFAULT 0,
                is_vice_captain INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, match_id, player_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contestant_points (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                points REAL NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL,
                UNIQUE(user_id, match_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_points (
                id SERIAL PRIMARY KEY,
                match_id INTEGER NOT NULL REFERENCES matches(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                player_name TEXT NOT NULL,
                team TEXT NOT NULL,
                role TEXT NOT NULL,
                points REAL NOT NULL DEFAULT 0,
                last_updated TEXT NOT NULL,
                UNIQUE(match_id, player_id)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_user_match ON user_teams(user_id, match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_match ON user_teams(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_match_user ON user_teams(match_id, user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contestant_points_match ON contestant_points(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_points_match ON player_points(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_points_last_updated ON player_points(last_updated)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid)")

        conn.commit()
        conn.close()
    else:
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
            CREATE INDEX IF NOT EXISTS idx_user_teams_match ON user_teams(match_id);
            CREATE INDEX IF NOT EXISTS idx_user_teams_match_user ON user_teams(match_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_contestant_points_match ON contestant_points(match_id);
            CREATE INDEX IF NOT EXISTS idx_player_points_match ON player_points(match_id);
            CREATE INDEX IF NOT EXISTS idx_player_points_last_updated ON player_points(last_updated);
            CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
        """)
        conn.commit()
        conn.close()
