"""HealthWatch - Smart Community Health Monitoring System (Flask application)."""
import logging
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

from backend.db import close_db, init_db, is_postgres  # noqa: E402
from backend.pages import pages  # noqa: E402
from backend.routes import api  # noqa: E402
from backend.seed import seed_all  # noqa: E402

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _secret_key(instance_dir: str) -> str:
    """Use FLASK_SECRET_KEY, else create one once and keep it so logins survive restarts."""
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    path = os.path.join(instance_dir, ".secret_key")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as fh:
        fh.write(key)
    return key


def create_app(test_config=None) -> Flask:
    app = Flask(__name__, instance_path=os.path.join(BASE_DIR, "instance"))
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        DATABASE_PATH=os.environ.get("DATABASE_PATH", os.path.join(app.instance_path, "shms.db")),
        SECRET_KEY=_secret_key(app.instance_path),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("PRODUCTION") == "1",
        DEMO_DATA=os.environ.get("DEMO_DATA", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)

    # DATABASE_URL (PostgreSQL, e.g. Neon) wins when set; otherwise use the SQLite file.
    if "DATABASE" not in app.config:
        explicit_path = bool(test_config and "DATABASE_PATH" in test_config)
        app.config["DATABASE"] = (None if explicit_path else os.environ.get("DATABASE_URL")) or app.config["DATABASE_PATH"]
    if not is_postgres(app.config["DATABASE"]):
        db_dir = os.path.dirname(app.config["DATABASE"])
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    init_db(app.config["DATABASE"])
    seed_all(app.config["DATABASE"], demo=app.config["DEMO_DATA"])

    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    app.register_blueprint(pages)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template("404.html"), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
