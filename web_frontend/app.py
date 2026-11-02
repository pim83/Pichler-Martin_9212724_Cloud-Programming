"""Passwortgeschütztes, ausschließlich lesendes Projekt-Dashboard."""
import hashlib
import hmac
import secrets
import time
from collections import deque
from threading import Lock
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

import requests
from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


class ApiUnavailable(Exception):
    pass


class ResultsApi:
    def get(self, path, device):
        base = os.environ.get("RESULTS_API_URL", "").rstrip("/")
        key = os.environ.get("RESULTS_API_KEY", "")
        url = urlsplit(base)
        if (url.scheme != "https" or not url.hostname
                or not url.hostname.endswith(".azurewebsites.net")
                or url.path != "/api" or url.query or url.fragment
                or url.username or url.password or url.port
                or not key or key.startswith("@Microsoft.KeyVault(")):
            raise ApiUnavailable()
        try:
            with requests.get(base + path, params={"device_id": device, "limit": 100},
                              headers={"x-functions-key": key}, timeout=(5, 20),
                              allow_redirects=False) as response:
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise ApiUnavailable()
                return response.json()
        except (requests.RequestException, ValueError):
            raise ApiUnavailable() from None


def create_app(api=None):
    app = Flask(__name__)
    api = api if api is not None else ResultsApi()
    password_hash = os.environ.get("DASHBOARD_PASSWORD_HASH", "")
    session_key = os.environ.get("DASHBOARD_SESSION_KEY", "")
    configured = (password_hash.startswith("scrypt:") and len(session_key) >= 32
                  and not session_key.startswith("@Microsoft.KeyVault("))
    app.config.update(SECRET_KEY=session_key if configured else None,
                      SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
                      SESSION_REFRESH_EACH_REQUEST=False, MAX_CONTENT_LENGTH=4096)
    credential_version = hashlib.sha256(password_hash.encode()).hexdigest()
    attempts = deque()
    attempts_lock = Lock()

    @app.before_request
    def require_login():
        if request.endpoint == "static":
            return
        if not configured:
            abort(503, description="Der Zugang ist noch nicht eingerichtet.")
        if request.endpoint == "login":
            return
        if session.get("authenticated") != credential_version:
            return redirect(url_for("login"))

    def csrf_valid():
        expected = session.get("csrf", "")
        supplied = request.form.get("csrf", "")
        return bool(expected) and hmac.compare_digest(expected, supplied)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if not csrf_valid():
                abort(400, description="Bitte die Anmeldeseite neu laden.")
            # Global pro Prozess, unabhängig von manipulierbaren IP-Headern.
            # Projektbetrieb: genau ein Worker und eine App-Service-Instanz.
            with attempts_lock:
                now = time.monotonic()
                while attempts and now - attempts[0] >= 60:
                    attempts.popleft()
                if len(attempts) >= 5:
                    response = app.make_response((render_template("login.html",
                        error="Zu viele Anmeldeversuche. Bitte nach einer Minute erneut versuchen."), 429))
                    response.headers["Retry-After"] = "60"
                    return response
                attempts.append(now)
            try:
                valid = check_password_hash(password_hash, request.form.get("password", ""))
            except ValueError:
                abort(503, description="Der Zugang ist noch nicht eingerichtet.")
            if not valid:
                return render_template("login.html", error="Das Passwort ist nicht korrekt."), 401
            session.clear()
            session.permanent = True
            session["authenticated"] = credential_version
            session["csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("index"))
        session.setdefault("csrf", secrets.token_urlsafe(32))
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        if not csrf_valid():
            abort(400, description="Bitte die Seite neu laden.")
        session.clear()
        return redirect(url_for("login"))

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.template_filter("percent")
    def percent(value):
        return "–" if value is None else f"{float(value):.2f}".replace(".", ",") + " %"

    @app.template_filter("localtime")
    def localtime(value):
        if not value:
            return "–"
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                ZoneInfo("Europe/Vienna")).strftime("%d.%m.%Y %H:%M %Z")
        except (ValueError, TypeError):
            return "–"

    def device():
        value = request.args.get("device_id", "pruefstand-01")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            abort(400, description="Ungültige Prüfstand-ID.")
        # Nur bewusst freigegebene Projektdaten, keine beliebigen Partitionen.
        allowed = {v.strip() for v in os.environ.get(
            "PUBLIC_DEVICE_IDS", "pruefstand-01").split(",") if v.strip()}
        if value not in allowed:
            abort(404, description="Dieser Prüfstand ist nicht freigegeben.")
        return value

    @app.get("/")
    def index():
        selected = request.args.get("status", "all")
        if selected not in ("all", "normal", "anomaly"):
            abort(400, description="Ungültiger Filter.")
        current = device()
        try:
            data = api.get("/measurements", current)
            rows = data["items"]
            anomaly = sum(row.get("measurement_anomalous") is True for row in rows)
            normal = sum(row.get("measurement_anomalous") is False for row in rows)
            visible = [r for r in rows if selected == "all" or
                       r.get("measurement_anomalous") is (selected == "anomaly")]
            return render_template("index.html", rows=visible, total=len(rows),
                                   anomaly=anomaly, normal=normal, device=current,
                                   selected=selected, has_more=data.get("has_more", False))
        except (ApiUnavailable, KeyError, TypeError):
            logging.warning("Messungsübersicht derzeit nicht verfügbar.")
            abort(503, description="Die Messdaten sind derzeit nicht erreichbar. Bitte später erneut versuchen.")

    @app.get("/measurements/<mid>")
    def detail(mid):
        try:
            if str(uuid.UUID(mid)) != mid:
                raise ValueError()
        except ValueError:
            abort(400, description="Ungültige Messungs-ID.")
        current = device()
        try:
            data = api.get("/measurements/" + mid, current)
        except ApiUnavailable:
            abort(503, description="Die Messung ist derzeit nicht erreichbar.")
        if data is None:
            abort(404, description="Diese Messung wurde nicht gefunden.")
        return render_template("detail.html", row=data, device=current)

    for status in (400, 403, 404, 503):
        app.register_error_handler(status, lambda error: (
            render_template("error.html", message=error.description, status=error.code), error.code))
    return app


app = create_app()
