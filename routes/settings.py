from datetime import datetime
from io import StringIO

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from models.setting import AppSetting, AuditLog
from models.user import User, db
from routes.dashboard import admin_required


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


DEFAULT_SETTINGS = {
    "store_name": "MedStore",
    "owner_name": "",
    "phone": "",
    "email": "",
    "address": "",
    "low_stock_threshold": "20",
    "critical_stock_threshold": "10",
    "expiry_warning_days": "30",
    "currency_symbol": "Rs",
    "date_format": "%d %b %Y",
    "time_format": "%I:%M %p",
}


def clean(value):
    return (value or "").strip()


def all_settings():
    values = DEFAULT_SETTINGS.copy()
    for row in AppSetting.query.all():
        values[row.setting_key] = row.setting_value or ""
    return values


def save_setting(key, value):
    setting = db.session.get(AppSetting, key)
    if not setting:
        setting = AppSetting(setting_key=key)
        db.session.add(setting)
    setting.setting_value = value
    setting.updated_at = datetime.now()


def add_audit(action, entity_type=None, entity_id=None, description=None):
    db.session.add(
        AuditLog(
            user_id=current_user.user_id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
        )
    )


def parse_positive_int(value, label, errors):
    try:
        parsed = int(clean(value))
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return 0
    if parsed <= 0:
        errors.append(f"{label} must be greater than 0.")
    return parsed


@settings_bp.route("/", methods=["GET", "POST"], strict_slashes=False)
@admin_required
def index():
    if request.method == "POST":
        section = request.form.get("section")
        if section == "store":
            for key in ["store_name", "owner_name", "phone", "email", "address"]:
                save_setting(key, clean(request.form.get(key)))
            add_audit("Update Store Settings", "Settings", None, "Store information updated.")
            db.session.commit()
            flash("Store information saved.", "success")
        elif section == "rules":
            errors = []
            rules = {
                "low_stock_threshold": parse_positive_int(request.form.get("low_stock_threshold"), "Low stock threshold", errors),
                "critical_stock_threshold": parse_positive_int(request.form.get("critical_stock_threshold"), "Critical stock threshold", errors),
                "expiry_warning_days": parse_positive_int(request.form.get("expiry_warning_days"), "Expiry warning days", errors),
            }
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                for key, value in rules.items():
                    save_setting(key, str(value))
                add_audit("Update Inventory Rules", "Settings", None, "Inventory rule settings updated.")
                db.session.commit()
                flash("Inventory rules saved.", "success")
        elif section == "preferences":
            for key in ["currency_symbol", "date_format", "time_format"]:
                save_setting(key, clean(request.form.get(key)))
            add_audit("Update Preferences", "Settings", None, "System preferences updated.")
            db.session.commit()
            flash("System preferences saved.", "success")
        return redirect(url_for("settings.index"))

    users = User.query.order_by(User.user_id.asc()).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc(), AuditLog.log_id.desc()).limit(80).all()
    return render_template("settings/index.html", settings=all_settings(), users=users, audit_logs=audit_logs)


@settings_bp.route("/users/add", methods=["POST"])
@admin_required
def add_user():
    username = clean(request.form.get("username"))
    password = request.form.get("password", "")
    role = clean(request.form.get("role")) or "Employee"
    errors = []

    if not username:
        errors.append("Username is required.")
    if not password:
        errors.append("Password is required.")
    if role not in {"Admin", "Employee"}:
        errors.append("Role is not valid.")
    if username and User.query.filter(User.username == username).first():
        errors.append("A user with this username already exists.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("settings.index"))

    user = User(username=username, role=role, password_hash=generate_password_hash(password), is_active_account=True)
    db.session.add(user)
    db.session.flush()
    add_audit("Add User", "User", user.user_id, f"User {username} created.")
    db.session.commit()
    flash("User added successfully.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User was not found.", "danger")
        return redirect(url_for("settings.index"))

    username = clean(request.form.get("username"))
    role = clean(request.form.get("role")) or "Employee"
    password = request.form.get("password", "")
    duplicate = User.query.filter(User.username == username, User.user_id != user_id).first()

    if not username or duplicate or role not in {"Admin", "Employee"}:
        flash("User details are not valid or username already exists.", "danger")
        return redirect(url_for("settings.index"))

    user.username = username
    user.role = role
    if password:
        user.password_hash = generate_password_hash(password)
    add_audit("Edit User", "User", user.user_id, f"User {username} updated.")
    db.session.commit()
    flash("User updated successfully.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User was not found.", "danger")
        return redirect(url_for("settings.index"))
    if user.user_id == current_user.user_id:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("settings.index"))

    user.is_active_account = not user.is_active_account
    action = "Activate User" if user.is_active_account else "Deactivate User"
    add_audit(action, "User", user.user_id, f"{user.username} marked {'active' if user.is_active_account else 'inactive'}.")
    db.session.commit()
    flash("User status updated.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.verify_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("settings.index"))
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "danger")
        return redirect(url_for("settings.index"))
    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("settings.index"))

    current_user.set_password(new_password)
    add_audit("Change Password", "User", current_user.user_id, "Password changed.")
    db.session.commit()
    flash("Password changed successfully.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/backup")
@admin_required
def backup():
    tables = ["users", "medicines", "suppliers", "inventory", "purchases", "purchase_details", "sales", "sale_details", "stock_movements", "app_settings", "audit_logs"]
    output = StringIO()
    output.write("-- Medical Store backup\n")
    output.write(f"-- Generated {datetime.now().isoformat(sep=' ', timespec='seconds')}\n\n")
    for table in tables:
        rows = db.session.execute(text(f"SELECT * FROM {table}")).mappings().all()
        output.write(f"-- Table: {table}\n")
        for row in rows:
            columns = ", ".join(f"`{key}`" for key in row.keys())
            values = []
            for value in row.values():
                if value is None:
                    values.append("NULL")
                else:
                    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
                    values.append(f"'{escaped}'")
            output.write(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join(values)});\n")
        output.write("\n")
    add_audit("Download Backup", "System", None, "Database backup downloaded.")
    db.session.commit()
    return Response(
        output.getvalue(),
        mimetype="application/sql",
        headers={"Content-Disposition": "attachment; filename=medical_store_backup.sql"},
    )


@settings_bp.route("/restore", methods=["POST"])
@admin_required
def restore():
    upload = request.files.get("backup_file")
    if not upload or not upload.filename.lower().endswith(".sql"):
        flash("Please upload a valid .sql backup file.", "danger")
        return redirect(url_for("settings.index"))

    content = upload.read().decode("utf-8", errors="ignore")
    sql_lines = [line for line in content.splitlines() if not line.strip().startswith("--")]
    statements = [statement.strip() for statement in "\n".join(sql_lines).split(";") if statement.strip()]
    try:
        for statement in statements:
            if statement.startswith("--"):
                continue
            db.session.execute(text(statement))
        add_audit("Restore Backup", "System", None, upload.filename)
        db.session.commit()
        flash("Backup restored successfully.", "success")
    except Exception:
        db.session.rollback()
        flash("Backup restore failed. Please verify the SQL file.", "danger")
    return redirect(url_for("settings.index"))
