"""Database helpers: schema, connections and the shared add_record() function.

Two back ends share one code base:
  * SQLite file (default, used for local runs and tests)
  * PostgreSQL, used automatically when DATABASE_URL is set (e.g. a free Neon
    database), so data survives restarts of free hosting.
"""
import re
import sqlite3
from datetime import date

from flask import current_app, g

from . import alerts, risk

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','worker')),
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS villages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    district TEXT NOT NULL DEFAULT '',
    population INTEGER NOT NULL DEFAULT 0,
    lat REAL NOT NULL,
    lng REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id INTEGER NOT NULL REFERENCES villages(id),
    diarrhea INTEGER NOT NULL CHECK (diarrhea >= 0),
    fever INTEGER NOT NULL CHECK (fever >= 0),
    rainfall TEXT NOT NULL CHECK (rainfall IN ('Low','Medium','High')),
    water_quality TEXT NOT NULL DEFAULT 'Good' CHECK (water_quality IN ('Good','Doubtful','Contaminated')),
    score INTEGER NOT NULL,
    risk TEXT NOT NULL,
    rising INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    reported_by INTEGER REFERENCES users(id),
    report_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    village_id INTEGER NOT NULL REFERENCES villages(id),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    emailed INTEGER NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_records_village_date ON records(village_id, report_date);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(report_date);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(acknowledged, created_at);
"""


SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','worker')),
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS villages (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    district TEXT NOT NULL DEFAULT '',
    population INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION NOT NULL DEFAULT 0,
    lng DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_villages_name ON villages (lower(name));
CREATE TABLE IF NOT EXISTS records (
    id SERIAL PRIMARY KEY,
    village_id INTEGER NOT NULL REFERENCES villages(id),
    diarrhea INTEGER NOT NULL CHECK (diarrhea >= 0),
    fever INTEGER NOT NULL CHECK (fever >= 0),
    rainfall TEXT NOT NULL CHECK (rainfall IN ('Low','Medium','High')),
    water_quality TEXT NOT NULL DEFAULT 'Good' CHECK (water_quality IN ('Good','Doubtful','Contaminated')),
    score INTEGER NOT NULL,
    risk TEXT NOT NULL,
    rising INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    reported_by INTEGER REFERENCES users(id),
    report_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    village_id INTEGER NOT NULL REFERENCES villages(id),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    emailed INTEGER NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_records_village_date ON records(village_id, report_date);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(report_date);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(acknowledged, created_at);
"""


def is_postgres(target: str) -> bool:
    return str(target).startswith(("postgres://", "postgresql://"))


class PgRow(dict):
    """Row that works like sqlite3.Row: row["name"] and row[0] both work."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _pg_row_factory(cursor):
    if cursor.description is None:  # statements that return no rows (UPDATE, DDL ...)
        return lambda values: values
    names = [c.name for c in cursor.description]
    return lambda values: PgRow(zip(names, values))


class PgCursor:
    def __init__(self, cur, returning=False):
        self._cur = cur
        self.rowcount = cur.rowcount
        self.lastrowid = None
        if returning:
            row = cur.fetchone()
            self.lastrowid = row["id"] if row else None

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)


class PgConnection:
    """Small adapter so the rest of the code can use the same calls for both databases."""

    def __init__(self, url):
        import psycopg  # imported here so SQLite-only runs do not need it
        self._conn = psycopg.connect(url, row_factory=_pg_row_factory, connect_timeout=15)

    @staticmethod
    def _translate(sql):
        ignore = bool(re.match(r"\s*INSERT\s+OR\s+IGNORE", sql, re.I))
        sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", sql, flags=re.I).replace("?", "%s")
        return sql + (" ON CONFLICT DO NOTHING" if ignore else "")

    def execute(self, sql, params=()):
        sql = self._translate(sql)
        returning = sql.lstrip().upper().startswith("INSERT")
        if returning:
            sql += " RETURNING id"
        return PgCursor(self._conn.execute(sql, params), returning)

    def executemany(self, sql, seq):
        with self._conn.cursor() as cur:
            cur.executemany(self._translate(sql), seq)

    def executescript(self, script):
        self._conn.execute(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect(target: str):
    """target is a PostgreSQL URL or the path of a SQLite file."""
    if is_postgres(target):
        return PgConnection(target)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(target: str) -> None:
    conn = connect(target)
    try:
        conn.executescript(SCHEMA_PG if is_postgres(target) else SCHEMA)
        conn.commit()
    finally:
        conn.close()


def add_record(db, *, village_id, diarrhea, fever, rainfall, water_quality="Good",
               report_date=None, notes="", reported_by=None, with_alert=True, notify=True):
    """Score a report, save it and raise an alert when needed.

    Used by both the API and the demo-data seeder so the logic lives in one place.
    """
    report_date = report_date or date.today().isoformat()
    prev = db.execute(
        "SELECT diarrhea FROM records WHERE village_id=? AND report_date<=? "
        "ORDER BY report_date DESC, id DESC LIMIT 1",
        (village_id, report_date),
    ).fetchone()
    result = risk.assess(diarrhea, fever, rainfall, water_quality,
                         prev["diarrhea"] if prev else None)
    cur = db.execute(
        "INSERT INTO records (village_id, diarrhea, fever, rainfall, water_quality, score, risk, "
        "rising, notes, reported_by, report_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (village_id, diarrhea, fever, rainfall, water_quality, result["score"], result["level"],
         int(result["rising"]), notes, reported_by, report_date),
    )
    record_id = cur.lastrowid
    if with_alert and result["level"] in ("High", "Critical"):
        name = db.execute("SELECT name FROM villages WHERE id=?", (village_id,)).fetchone()["name"]
        alerts.create_alert(db, record_id, village_id, result, name, report_date,
                            diarrhea, fever, notify=notify)
    db.commit()
    return record_id, result
