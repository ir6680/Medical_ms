from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text

from models.setting import AuditLog
from models.user import LoginActivity, User, db
from routes.dashboard import admin_required


employees_bp = Blueprint("employees", __name__, url_prefix="/employees")


def clean(value):
    return (value or "").strip()


def employee_payload(form):
    return {
        "full_name": clean(form.get("full_name")),
        "username": clean(form.get("username")),
        "phone": clean(form.get("phone")),
        "email": clean(form.get("email")),
        "role": clean(form.get("role")) or "Employee",
        "is_active_account": form.get("status", "active") == "active",
    }


def validate_employee(data, user_id=None, require_password=False):
    errors = []
    if not data["full_name"]:
        errors.append("Full name is required.")
    if not data["username"]:
        errors.append("Username is required.")
    if data["role"] not in {"Admin", "Employee"}:
        errors.append("Role is not valid.")
    if data["email"] and "@" not in data["email"]:
        errors.append("Email address is not valid.")

    duplicate = User.query.filter(User.username == data["username"])
    if user_id:
        duplicate = duplicate.filter(User.user_id != user_id)
    if data["username"] and duplicate.first():
        errors.append("A user with this username already exists.")

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    if require_password or password or confirm_password:
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Password and confirmation do not match.")

    return errors


def add_audit(action, employee, description):
    db.session.add(
        AuditLog(
            user_id=current_user.user_id,
            username=current_user.username,
            action=action,
            entity_type="User",
            entity_id=employee.user_id,
            description=description,
        )
    )


@employees_bp.route("/")
@admin_required
def index():
    employees = User.query.order_by(User.user_id.desc()).all()
    return render_template("employees/index.html", employees=employees)


@employees_bp.route("/add", methods=["GET", "POST"])
@admin_required
def add():
    if request.method == "POST":
        data = employee_payload(request.form)
        errors = validate_employee(data, require_password=True)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("employees/form.html", employee=data, mode="Add")

        employee = User(**data, created_at=datetime.now())
        employee.set_password(request.form.get("password", ""))
        db.session.add(employee)
        db.session.flush()
        add_audit("Add Employee", employee, f"Employee {employee.username} created.")
        db.session.commit()
        flash("Employee added successfully.", "success")
        return redirect(url_for("employees.detail", employee_id=employee.user_id))

    return render_template("employees/form.html", employee={}, mode="Add")


@employees_bp.route("/<int:employee_id>")
@admin_required
def detail(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        return render_template("dashboard/placeholder.html", title="Employee Not Found", icon="bi-person-x"), 404

    totals = db.session.execute(
        text(
            """
            SELECT COUNT(sale_id) AS total_sales, COALESCE(SUM(total_amount), 0) AS sales_amount
            FROM sales
            WHERE employee_id = :employee_id
            """
        ),
        {"employee_id": employee_id},
    ).mappings().first()
    activities = (
        LoginActivity.query.filter_by(user_id=employee_id)
        .order_by(LoginActivity.login_time.desc(), LoginActivity.activity_id.desc())
        .limit(25)
        .all()
    )
    recent_sales = db.session.execute(
        text(
            """
            SELECT sale_id, sale_date, total_amount
            FROM sales
            WHERE employee_id = :employee_id
            ORDER BY sale_date DESC, sale_id DESC
            LIMIT 10
            """
        ),
        {"employee_id": employee_id},
    ).mappings().all()
    return render_template(
        "employees/detail.html",
        employee=employee,
        totals=totals,
        activities=activities,
        recent_sales=recent_sales,
    )


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        flash("Employee was not found.", "danger")
        return redirect(url_for("employees.index"))

    if request.method == "POST":
        data = employee_payload(request.form)
        errors = validate_employee(data, employee_id)
        if not data["is_active_account"] and employee.user_id == current_user.user_id:
            errors.append("You cannot deactivate your own account.")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("employees/form.html", employee={**data, "user_id": employee_id}, mode="Edit")

        for key, value in data.items():
            setattr(employee, key, value)
        add_audit("Edit Employee", employee, f"Employee {employee.username} updated.")
        db.session.commit()
        flash("Employee updated successfully.", "success")
        return redirect(url_for("employees.detail", employee_id=employee.user_id))

    return render_template("employees/form.html", employee=employee, mode="Edit")


@employees_bp.route("/<int:employee_id>/toggle", methods=["POST"])
@admin_required
def toggle(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        flash("Employee was not found.", "danger")
        return redirect(url_for("employees.index"))
    if employee.user_id == current_user.user_id:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("employees.index"))

    employee.is_active_account = not employee.is_active_account
    add_audit(
        "Activate Employee" if employee.is_active_account else "Deactivate Employee",
        employee,
        f"{employee.username} marked {'active' if employee.is_active_account else 'inactive'}.",
    )
    db.session.commit()
    flash("Employee status updated.", "success")
    return redirect(url_for("employees.index"))


@employees_bp.route("/<int:employee_id>/reset-password", methods=["GET", "POST"])
@admin_required
def reset_password(employee_id):
    employee = db.session.get(User, employee_id)
    if not employee:
        flash("Employee was not found.", "danger")
        return redirect(url_for("employees.index"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 6 or password != confirm_password:
            flash("Password must be at least 6 characters and match confirmation.", "danger")
            return render_template("employees/reset_password.html", employee=employee)

        employee.set_password(password)
        add_audit("Reset Employee Password", employee, f"Password reset for {employee.username}.")
        db.session.commit()
        flash("Employee password reset successfully.", "success")
        return redirect(url_for("employees.detail", employee_id=employee.user_id))

    return render_template("employees/reset_password.html", employee=employee)
