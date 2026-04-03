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

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PgConnectionWrapper:
    """Wraps psycopg2 connection to behave like sqlite3.Connection."""
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = _connect_postgres(dsn)

    def _is_closed(self) -> bool:
        return self._conn is None or bool(getattr(self._conn, "closed", 0))

    def _ensure_connection(self):
        if self._is_closed():
            self._conn = _connect_postgres(self._dsn)

    def execute(self, sql, params=None):
        self._ensure_connection()
        sql = sql.replace("?", "%s")
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
        except Exception as exc:
            if not _should_reconnect_postgres(exc):
                raise
            self._conn = _connect_postgres(self._dsn)
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
        return PgCursorWrapper(cursor, self._conn)

    def executescript(self, sql):
        self._ensure_connection()
        cursor = self._conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)
        self._conn.commit()

    def commit(self):
        self._ensure_connection()
        self._conn.commit()

    def close(self):
        if self._conn is not None and not self._is_closed():
            self._conn.close()

    def cursor(self):
        self._ensure_connection()
        return PgCursorWrapper(self._conn.cursor(), self._conn)


def _is_postgres():
    return DATABASE_URL.startswith("postgres")


def _postgres_dsn() -> str:
    return DATABASE_URL.replace("postgres://", "postgresql://", 1)


def _connect_postgres(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn)


def _should_reconnect_postgres(exc: Exception) -> bool:
    message = str(exc).lower()
    return "connection already closed" in message or "closed the connection unexpectedly" in message


def _sqlite_column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _ensure_user_teams_updated_at_sqlite(conn):
    if not _sqlite_column_exists(conn, "user_teams", "updated_at"):
        conn.execute("ALTER TABLE user_teams ADD COLUMN updated_at TEXT")
        conn.execute(
            "UPDATE user_teams SET updated_at = datetime('now') WHERE updated_at IS NULL OR updated_at = ''"
        )


def _ensure_user_teams_updated_at_postgres(cursor):
    cursor.execute("ALTER TABLE user_teams ADD COLUMN IF NOT EXISTS updated_at TEXT")
    cursor.execute(
        "UPDATE user_teams SET updated_at = TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS') WHERE updated_at IS NULL OR updated_at = ''"
    )


def _ensure_team_backups_postgres(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_backups (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            match_id INTEGER NOT NULL REFERENCES matches(id),
            backup_order INTEGER NOT NULL,
            backup_player_id INTEGER NOT NULL REFERENCES players(id),
            replaced_player_id INTEGER REFERENCES players(id),
            UNIQUE(user_id, match_id, backup_order)
        )
    """)


def _ensure_team_backups_sqlite(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            match_id INTEGER NOT NULL REFERENCES matches(id),
            backup_order INTEGER NOT NULL,
            backup_player_id INTEGER NOT NULL REFERENCES players(id),
            replaced_player_id INTEGER REFERENCES players(id),
            UNIQUE(user_id, match_id, backup_order)
        )
    """)


def get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        if _is_postgres():
            _local.conn = PgConnectionWrapper(_postgres_dsn())
        else:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _local.conn = conn
    elif _is_postgres() and getattr(_local.conn, "_is_closed", lambda: False)():
        _local.conn = PgConnectionWrapper(_postgres_dsn())
    return _local.conn


def init_db():
    if _is_postgres():
        conn = _connect_postgres(_postgres_dsn())
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
                status TEXT DEFAULT 'future',
                venue TEXT DEFAULT NULL
            )
        """)
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'matches' AND column_name = 'venue'
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE matches ADD COLUMN venue TEXT DEFAULT NULL")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_teams (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                is_captain INTEGER NOT NULL DEFAULT 0,
                is_vice_captain INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                UNIQUE(user_id, match_id, player_id)
            )
        """)
        _ensure_user_teams_updated_at_postgres(cursor)
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
        _ensure_team_backups_postgres(cursor)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_user_match ON user_teams(user_id, match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_match ON user_teams(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_match_user ON user_teams(match_id, user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_teams_match_updated_at ON user_teams(match_id, updated_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contestant_points_match ON contestant_points(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_points_match ON player_points(match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_points_last_updated ON player_points(last_updated)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_backups_user_match ON team_backups(user_id, match_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_backups_match ON team_backups(match_id)")

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
                status TEXT DEFAULT 'future',
                venue TEXT DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS user_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                is_captain INTEGER NOT NULL DEFAULT 0,
                is_vice_captain INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
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
            CREATE TABLE IF NOT EXISTS team_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                match_id INTEGER NOT NULL REFERENCES matches(id),
                backup_order INTEGER NOT NULL,
                backup_player_id INTEGER NOT NULL REFERENCES players(id),
                replaced_player_id INTEGER REFERENCES players(id),
                UNIQUE(user_id, match_id, backup_order)
            );
            CREATE INDEX IF NOT EXISTS idx_user_teams_user_match ON user_teams(user_id, match_id);
            CREATE INDEX IF NOT EXISTS idx_user_teams_match ON user_teams(match_id);
            CREATE INDEX IF NOT EXISTS idx_user_teams_match_user ON user_teams(match_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_user_teams_match_updated_at ON user_teams(match_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_contestant_points_match ON contestant_points(match_id);
            CREATE INDEX IF NOT EXISTS idx_player_points_match ON player_points(match_id);
            CREATE INDEX IF NOT EXISTS idx_player_points_last_updated ON player_points(last_updated);
            CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
            CREATE INDEX IF NOT EXISTS idx_team_backups_user_match ON team_backups(user_id, match_id);
            CREATE INDEX IF NOT EXISTS idx_team_backups_match ON team_backups(match_id);
        """)
        _ensure_user_teams_updated_at_sqlite(conn)
        _ensure_team_backups_sqlite(conn)
        try:
            conn.execute("ALTER TABLE matches ADD COLUMN venue TEXT DEFAULT NULL")
        except Exception:
            pass
        conn.commit()
        conn.close()
