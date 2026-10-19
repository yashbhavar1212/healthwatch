"""JSON API (all endpoints live under /api)."""
import csv
import io
import secrets
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, Response, jsonify, request, session
from werkzeug.security import check_password_hash

from . import risk
from .db import add_record, get_db

api = Blueprint("api", __name__, url_prefix="/api")

CSRF_EXEMPT = {"api.login", "api.assess"}
_failed_logins = {}  # ip -> (count, last_time); simple brute-force guard


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@api.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify(error=err.message), err.status


@api.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.endpoint not in CSRF_EXEMPT:
        sent = request.headers.get("X-CSRF-Token", "").encode()
        expected = session.get("csrf", "").encode()
        if not expected or not secrets.compare_digest(sent, expected):
            raise ApiError("Security token missing or expired. Refresh the page and try again.", 403)


# ---------------------------------------------------------------- helpers
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            raise ApiError("Please sign in to continue.", 401)
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            raise ApiError("Only the district officer (admin) can do this.", 403)
        return fn(*args, **kwargs)
    return wrapper


def _int(value, label, lo=0, hi=100000):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError(f"{label} must be a whole number.")
    try:
        number = int(value)
    except ValueError:
        raise ApiError(f"{label} must be a whole number.")
    if not lo <= number <= hi:
        raise ApiError(f"{label} must be between {lo} and {hi}.")
    return number


def _choice(value, options, label):
    text = str(value if value is not None else "").strip().capitalize()
    if text not in options:
        raise ApiError(f"{label} must be one of: {', '.join(options)}.")
    return text


def _report_date(value):
    if not value:
        return date.today().isoformat()
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        raise ApiError("Date must look like 2026-01-31.")
    if parsed > date.today():
        raise ApiError("Report date cannot be in the future.")
    if parsed < date.today() - timedelta(days=365):
        raise ApiError("Report date is more than a year old.")
    return parsed.isoformat()


def _rows(rows):
    return [dict(r) for r in rows]


def _village_status(db):
    """Latest report per village plus the one before it (for the trend arrow)."""
    villages = db.execute("SELECT * FROM villages ORDER BY name").fetchall()
    grouped = {}
    for rec in db.execute("SELECT * FROM records ORDER BY report_date, id").fetchall():
        grouped.setdefault(rec["village_id"], []).append(rec)
    out = []
    for v in villages:
        history = grouped.get(v["id"], [])
        latest = history[-1] if history else None
        prev = history[-2] if len(history) > 1 else None
        trend = None
        if latest and prev:
            trend = ("up" if latest["diarrhea"] > prev["diarrhea"]
                     else "down" if latest["diarrhea"] < prev["diarrhea"] else "flat")
        out.append({
            "id": v["id"], "name": v["name"], "district": v["district"],
            "population": v["population"], "lat": v["lat"], "lng": v["lng"],
            "trend": trend,
            "latest": None if not latest else {
                "date": latest["report_date"], "diarrhea": latest["diarrhea"],
                "fever": latest["fever"], "rainfall": latest["rainfall"],
                "water_quality": latest["water_quality"], "score": latest["score"],
                "risk": latest["risk"], "rising": bool(latest["rising"]),
            },
        })
    return out


# ------------------------------------------------------------------- auth
@api.post("/login")
def login():
    ip = request.remote_addr or "?"
    count, last = _failed_logins.get(ip, (0, 0))
    if count >= 5 and time.time() - last < 60:
        raise ApiError("Too many failed attempts. Wait a minute and try again.", 429)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        _failed_logins[ip] = (count + 1 if time.time() - last < 60 else 1, time.time())
        raise ApiError("Wrong username or password.", 401)
    _failed_logins.pop(ip, None)
    session.clear()
    session.permanent = True
    session.update(user_id=user["id"], username=user["username"], role=user["role"],
                   full_name=user["full_name"], csrf=secrets.token_urlsafe(24))
    return jsonify(ok=True, role=user["role"])


@api.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@api.get("/me")
@login_required
def me():
    return jsonify(username=session["username"], role=session["role"], full_name=session["full_name"])


# ----------------------------------------------------------------- public
@api.post("/assess")
def assess():
    """Public calculator used on the home page. Stores nothing."""
    d = request.get_json(silent=True) or {}
    result = risk.assess(
        _int(d.get("diarrhea"), "Diarrhea cases", 0, 5000),
        _int(d.get("fever"), "Fever cases", 0, 5000),
        _choice(d.get("rainfall"), risk.RAINFALL_POINTS, "Rainfall"),
        _choice(d.get("water_quality", "Good"), risk.WATER_POINTS, "Water quality"),
    )
    return jsonify(result)


@api.get("/public/overview")
def public_overview():
    db = get_db()
    status = _village_status(db)
    week_ago = (date.today() - timedelta(days=6)).isoformat()
    row = db.execute("SELECT COUNT(*) AS cnt, MAX(report_date) AS last_date FROM records WHERE report_date>=?",
                     (week_ago,)).fetchone()
    on_alert = sum(1 for s in status if s["latest"] and s["latest"]["risk"] in ("High", "Critical"))
    return jsonify(villages=len(status), on_alert=on_alert,
                   reports_7d=row["cnt"], last_report=row["last_date"])


# --------------------------------------------------------------- villages
@api.get("/villages")
@login_required
def list_villages():
    rows = get_db().execute(
        "SELECT v.id, v.name, v.district, v.population, COUNT(r.id) AS reports, "
        "MAX(r.report_date) AS last_report FROM villages v "
        "LEFT JOIN records r ON r.village_id=v.id GROUP BY v.id ORDER BY lower(v.name)"
    ).fetchall()
    return jsonify(_rows(rows))


@api.post("/villages")
@login_required
def create_village():
    d = request.get_json(silent=True) or {}
    name = " ".join(str(d.get("name", "")).split())
    if not 2 <= len(name) <= 60:
        raise ApiError("Village name must be 2 to 60 characters.")
    population = _int(d.get("population") or 0, "Population", 0, 10_000_000)
    district = " ".join(str(d.get("district", "")).split())[:60]
    db = get_db()
    if db.execute("SELECT 1 FROM villages WHERE lower(name)=lower(?)", (name,)).fetchone():
        raise ApiError(f"{name} is already in the list.", 409)
    cur = db.execute(
        "INSERT INTO villages (name, district, population, lat, lng) VALUES (?,?,?,0,0)",
        (name, district, population))
    db.commit()
    return jsonify(id=cur.lastrowid, name=name), 201


@api.delete("/villages/<int:village_id>")
@admin_required
def delete_village(village_id):
    db = get_db()
    village = db.execute("SELECT name FROM villages WHERE id=?", (village_id,)).fetchone()
    if not village:
        raise ApiError("Village not found.", 404)
    count = db.execute("SELECT COUNT(*) FROM records WHERE village_id=?", (village_id,)).fetchone()[0]
    db.execute("DELETE FROM alerts WHERE village_id=?", (village_id,))
    db.execute("DELETE FROM records WHERE village_id=?", (village_id,))
    db.execute("DELETE FROM villages WHERE id=?", (village_id,))
    db.commit()
    return jsonify(ok=True, name=village["name"], reports_deleted=count)


# ---------------------------------------------------------------- records
def _record_filters():
    where, args = [], []
    q = request.args.get("q", "").strip()
    if q:
        where.append("lower(v.name) LIKE lower(?)")
        args.append(f"%{q}%")
    village_id = request.args.get("village_id", type=int)
    if village_id:
        where.append("r.village_id=?")
        args.append(village_id)
    level = request.args.get("risk", "")
    if level in risk.LEVELS:
        where.append("r.risk=?")
        args.append(level)
    for key, op in (("from", ">="), ("to", "<=")):
        value = request.args.get(key, "")
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ApiError("Dates must look like 2026-01-31.")
            where.append(f"r.report_date {op} ?")
            args.append(value)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return clause, args


_RECORD_SELECT = (
    "SELECT r.*, v.name AS village, v.district, u.username AS reporter "
    "FROM records r JOIN villages v ON v.id=r.village_id "
    "LEFT JOIN users u ON u.id=r.reported_by"
)


@api.get("/records")
@login_required
def list_records():
    db = get_db()
    clause, args = _record_filters()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 15, type=int), 1), 100)
    total = db.execute(
        f"SELECT COUNT(*) FROM records r JOIN villages v ON v.id=r.village_id{clause}", args
    ).fetchone()[0]
    rows = db.execute(
        f"{_RECORD_SELECT}{clause} ORDER BY r.report_date DESC, r.id DESC LIMIT ? OFFSET ?",
        args + [per_page, (page - 1) * per_page],
    ).fetchall()
    return jsonify(records=_rows(rows), total=total, page=page, per_page=per_page,
                   pages=max((total + per_page - 1) // per_page, 1))


@api.post("/records")
@login_required
def create_record():
    d = request.get_json(silent=True) or {}
    db = get_db()
    village_id = _int(d.get("village_id"), "Village", 1, 10**9)
    village = db.execute("SELECT id, name FROM villages WHERE id=?", (village_id,)).fetchone()
    if not village:
        raise ApiError("Choose a village from the list.")
    record_id, result = add_record(
        db,
        village_id=village_id,
        diarrhea=_int(d.get("diarrhea"), "Diarrhea cases", 0, 5000),
        fever=_int(d.get("fever"), "Fever cases", 0, 5000),
        rainfall=_choice(d.get("rainfall"), risk.RAINFALL_POINTS, "Rainfall"),
        water_quality=_choice(d.get("water_quality", "Good"), risk.WATER_POINTS, "Water quality"),
        report_date=_report_date(d.get("report_date")),
        notes=str(d.get("notes") or "").strip()[:300],
        reported_by=session["user_id"],
    )
    return jsonify(id=record_id, village=village["name"], assessment=result), 201


@api.delete("/records/<int:record_id>")
@admin_required
def delete_record(record_id):
    db = get_db()
    cur = db.execute("DELETE FROM records WHERE id=?", (record_id,))
    db.commit()
    if not cur.rowcount:
        raise ApiError("Record not found.", 404)
    return jsonify(ok=True)


def _csv_safe(value):
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@api.get("/export.csv")
@login_required
def export_csv():
    clause, args = _record_filters()
    rows = get_db().execute(f"{_RECORD_SELECT}{clause} ORDER BY r.report_date DESC, r.id DESC", args)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Village", "District", "Diarrhea", "Fever", "Rainfall",
                     "Water quality", "Score", "Risk", "Rising", "Reported by", "Notes"])
    for r in rows:
        writer.writerow([r["report_date"], _csv_safe(r["village"]), _csv_safe(r["district"]),
                         r["diarrhea"], r["fever"], r["rainfall"], r["water_quality"], r["score"],
                         r["risk"], "yes" if r["rising"] else "no", r["reporter"] or "",
                         _csv_safe(r["notes"])])
    filename = f"healthwatch-{date.today().isoformat()}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# -------------------------------------------------------------- dashboard
@api.get("/summary")
@login_required
def summary():
    db = get_db()
    status = _village_status(db)
    today = date.today()
    days = [(today - timedelta(days=n)).isoformat() for n in range(29, -1, -1)]
    series = {d: {"diarrhea": 0, "fever": 0} for d in days}
    for r in db.execute("SELECT report_date, SUM(diarrhea) AS d, SUM(fever) AS f FROM records "
                        "WHERE report_date>=? GROUP BY report_date", (days[0],)):
        if r["report_date"] in series:
            series[r["report_date"]] = {"diarrhea": int(r["d"]), "fever": int(r["f"])}
    this_week = sum(series[d]["diarrhea"] for d in days[-7:])
    last_week = sum(series[d]["diarrhea"] for d in days[-14:-7])
    distribution = {lvl: 0 for lvl in risk.LEVELS}
    for s in status:
        if s["latest"]:
            distribution[s["latest"]["risk"]] += 1
    reporting = sum(1 for s in status if s["latest"])
    open_alerts = db.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0]
    return jsonify(
        villages=status,
        stats={
            "villages": len(status), "reporting": reporting,
            "on_alert": distribution["High"] + distribution["Critical"],
            "open_alerts": open_alerts,
            "cases_this_week": this_week, "cases_last_week": last_week,
        },
        distribution=distribution,
        series={"labels": days, "diarrhea": [series[d]["diarrhea"] for d in days],
                "fever": [series[d]["fever"] for d in days]},
        generated_at=datetime.now().strftime("%H:%M"),
    )


# ----------------------------------------------------------------- alerts
@api.get("/alerts")
@login_required
def list_alerts():
    rows = get_db().execute(
        "SELECT a.id, a.level, a.message, a.created_at, a.emailed, v.name AS village "
        "FROM alerts a JOIN villages v ON v.id=a.village_id WHERE a.acknowledged=0 "
        "ORDER BY a.id DESC LIMIT 8"
    ).fetchall()
    return jsonify(_rows(rows))


@api.post("/alerts/<int:alert_id>/ack")
@login_required
def ack_alert(alert_id):
    db = get_db()
    cur = db.execute("UPDATE alerts SET acknowledged=1, acknowledged_by=? WHERE id=?",
                     (session["user_id"], alert_id))
    db.commit()
    if not cur.rowcount:
        raise ApiError("Alert not found.", 404)
    return jsonify(ok=True)
