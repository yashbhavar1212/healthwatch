"""Default users, villages and optional demo data (30 days of reports)."""
import os
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from .db import add_record, connect

# Coordinates are approximate (Pune district, Maharashtra). Admins can add more villages.
VILLAGES = [
    ("Tathawade", "Pune", 24000, 18.6150, 73.7550),
    ("Moshi", "Pune", 31000, 18.6770, 73.8530),
    ("Alandi", "Pune", 27000, 18.6770, 73.8970),
    ("Talegaon", "Pune", 42000, 18.7350, 73.6760),
    ("Lonavala", "Pune", 57000, 18.7481, 73.4072),
    ("Junnar", "Pune", 25000, 19.2090, 73.8760),
    ("Manchar", "Pune", 19000, 19.0020, 73.9420),
    ("Awasari", "Pune", 8000, 19.0260, 73.9110),
    ("Gawadewadi", "Pune", 4200, 19.0480, 73.8870),
    ("Bhimashankar", "Pune", 3100, 19.0720, 73.5350),
]

# base diarrhea, base fever, growth per report, water quality
PROFILES = {
    "Tathawade": (3, 8, 0.0, "Good"),
    "Moshi": (5, 12, 0.15, "Good"),
    "Alandi": (3, 8, 0.08, "Good"),
    "Talegaon": (2, 6, -0.05, "Good"),
    "Lonavala": (4, 10, -0.12, "Good"),
    "Junnar": (6, 16, 0.22, "Doubtful"),
    "Manchar": (6, 22, 0.90, "Doubtful"),
    "Awasari": (8, 18, 0.45, "Doubtful"),
    "Gawadewadi": (9, 30, 1.10, "Contaminated"),
    "Bhimashankar": (10, 35, 1.60, "Contaminated"),
}
RAIN = ["Low", "Low", "Medium", "Medium", "High", "High", "Medium", "Low",
        "Medium", "High", "High", "High", "Medium", "High", "High"]


def seed_users(conn):
    users = [
        ("admin", os.environ.get("ADMIN_PASSWORD", "Admin@123"), "admin", "District Health Officer"),
        ("worker", os.environ.get("WORKER_PASSWORD", "Worker@123"), "worker", "Village Health Worker"),
    ]
    for username, password, role, full_name in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), role, full_name),
        )
    conn.commit()


def seed_villages(conn):
    """The fixed list of monitored villages (loaded once into an empty table)."""
    if conn.execute("SELECT COUNT(*) FROM villages").fetchone()[0]:
        return
    conn.executemany(
        "INSERT INTO villages (name, district, population, lat, lng) VALUES (?,?,?,?,?)", VILLAGES
    )
    conn.commit()


def seed_demo(conn):
    """Insert 30 days of sample reports, only into a database with no records."""
    if conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]:
        return
    worker = conn.execute("SELECT id FROM users WHERE username='worker'").fetchone()["id"]
    rng = random.Random(42)
    today = date.today()
    for row in conn.execute("SELECT id, name FROM villages").fetchall():
        base_d, base_f, growth, water = PROFILES[row["name"]]
        for i in range(15):  # one report every two days, oldest first
            day = today - timedelta(days=28 - 2 * i)
            diarrhea = max(0, round(base_d + growth * i + rng.randint(-1, 2)))
            fever = max(0, round(base_f + growth * 1.5 * i + rng.randint(-2, 3)))
            add_record(
                conn, village_id=row["id"], diarrhea=diarrhea, fever=fever, rainfall=RAIN[i],
                water_quality=water, report_date=day.isoformat(), reported_by=worker,
                with_alert=i >= 13, notify=False,
            )


def seed_all(path: str, demo: bool = True):
    conn = connect(path)
    try:
        seed_users(conn)
        if demo:
            seed_villages(conn)
            seed_demo(conn)
    finally:
        conn.close()
