"""Small admin helper (replaces the old check_database.py).

    python manage.py stats                      show record counts and risk mix
    python manage.py create-user NAME ROLE      add a user (ROLE = admin or worker)
    python manage.py reset                      delete the database and start empty
    python manage.py reset --demo               delete the database and load sample data
"""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from backend.db import connect, init_db, is_postgres
from backend.seed import seed_all

BASE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PATH", os.path.join(BASE, "instance", "shms.db"))


def stats():
    conn = connect(PATH)
    print("Villages :", conn.execute("SELECT COUNT(*) FROM villages").fetchone()[0])
    print("Records  :", conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
    print("Alerts   :", conn.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0], "open")
    for row in conn.execute("SELECT risk, COUNT(*) c FROM records GROUP BY risk ORDER BY c DESC"):
        print(f"  {row['risk']:<9}{row['c']}")


def create_user(name, role):
    if role not in ("admin", "worker"):
        sys.exit("ROLE must be admin or worker")
    password = getpass.getpass("Password: ")
    init_db(PATH)
    conn = connect(PATH)
    conn.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
                 (name, generate_password_hash(password), role, name))
    conn.commit()
    print("User created.")


def reset(demo=False):
    if is_postgres(PATH):
        conn = connect(PATH)
        conn.execute("DROP TABLE IF EXISTS alerts, records, villages, users CASCADE")
        conn.commit()
        conn.close()
    else:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(PATH + suffix):
                os.remove(PATH + suffix)
    init_db(PATH)
    seed_all(PATH, demo=demo)
    print("Database reset" + (" with demo data." if demo else ". It is empty now."))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "stats":
        stats()
    elif cmd == "create-user" and len(sys.argv) == 4:
        create_user(sys.argv[2], sys.argv[3])
    elif cmd == "reset":
        reset(demo="--demo" in sys.argv)
    else:
        print(__doc__)
