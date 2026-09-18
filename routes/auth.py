from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from models.setting import AuditLog
from datetime import datetime

from models.user import LoginActivity, User, db


auth_bp = Blueprint("auth", __name__, url_prefix="")


def is_safe_next_url(target):
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(target)
    return not test_url.netloc or test_url.netloc == ref_url.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("auth/login.html", username=username)

        user = User.query.filter(User.username == username).first()
        password_ok = False

        if user:
            try:
                password_ok = check_password_hash(user.password_hash, password)
            except ValueError:
                password_ok = False

            if not password_ok and user.password_hash == password:
                user.password_hash = generate_password_hash(password)
                db.session.commit()
                password_ok = True

        if not user or not password_ok:
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html", username=username)

        if not user.is_active:
            flash("This user account is inactive. Please contact an administrator.", "warning")
            return render_template("auth/login.html", username=username)

        session.permanent = True
        login_user(user, remember=remember, fresh=True)
        user.last_login = datetime.now()
        activity = LoginActivity(
            user_id=user.user_id,
            login_time=user.last_login,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "")[:45],
        )
        db.session.add(activity)
        db.session.flush()
        session["login_activity_id"] = activity.activity_id
        db.session.add(
            AuditLog(
                user_id=user.user_id,
                username=user.username,
                action="Login",
                entity_type="User",
                entity_id=user.user_id,
                description=f"{user.username} signed in.",
            )
        )
        db.session.commit()
        flash(f"Welcome back, {user.username}.", "success")

        next_url = request.args.get("next")
        if is_safe_next_url(next_url):
            return redirect(next_url)
        if not user.is_admin:
            return redirect(url_for("pos.index"))
        return redirect(url_for("dashboard.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    activity_id = session.get("login_activity_id")
    if activity_id:
        activity = db.session.get(LoginActivity, activity_id)
        if activity and not activity.logout_time:
            activity.logout_time = datetime.now()
            db.session.commit()
    logout_user()
    session.pop("_csrf_token", None)
    session.pop("login_activity_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
