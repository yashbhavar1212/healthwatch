"""HTML pages (server-rendered with Jinja)."""
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, redirect, render_template, request, session, url_for

pages = Blueprint("pages", __name__)


def page_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("pages.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@pages.app_context_processor
def inject_user():
    user = None
    if "user_id" in session:
        user = {"username": session["username"], "role": session["role"],
                "full_name": session["full_name"]}
    return {"current_user": user, "csrf_token": session.get("csrf", "")}


@pages.get("/")
def index():
    return render_template("index.html")


@pages.get("/login")
def login():
    if "user_id" in session:
        return redirect(url_for("pages.dashboard"))
    nxt = request.args.get("next", "")
    parsed = urlparse(nxt)
    safe_next = nxt if nxt.startswith("/") and not nxt.startswith("//") and not parsed.netloc else ""
    return render_template("login.html", next=safe_next)


@pages.get("/dashboard")
@page_login_required
def dashboard():
    return render_template("dashboard.html")


@pages.get("/entry")
@page_login_required
def entry():
    return render_template("entry.html")


@pages.get("/records")
@page_login_required
def records():
    return render_template("records.html")
