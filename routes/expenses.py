from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text

from models.operations import Expense
from models.setting import AuditLog
from models.user import db
from routes.dashboard import admin_required


expenses_bp = Blueprint("expenses", __name__, url_prefix="/expenses")
EXPENSE_CATEGORIES = ["Electricity", "Rent", "Salaries", "Internet", "Transport", "Miscellaneous"]


def clean(value):
    return (value or "").strip()


def parse_amount(value, errors):
    try:
        amount = Decimal(clean(value))
    except (InvalidOperation, ValueError):
        errors.append("Amount must be a valid number.")
        return Decimal("0")
    if amount <= 0:
        errors.append("Amount must be greater than 0.")
    return amount


def add_audit(action, expense, description):
    db.session.add(
        AuditLog(
            user_id=current_user.user_id,
            username=current_user.username,
            action=action,
            entity_type="Expense",
            entity_id=expense.expense_id,
            description=description,
        )
    )


@expenses_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    if request.method == "POST":
        errors = []
        category = clean(request.form.get("category"))
        description = clean(request.form.get("description"))
        amount = parse_amount(request.form.get("amount"), errors)
        try:
            expense_date = datetime.strptime(clean(request.form.get("expense_date")), "%Y-%m-%d").date()
        except ValueError:
            expense_date = date.today()
            errors.append("Expense date is required.")
        if category not in EXPENSE_CATEGORIES:
            errors.append("Expense category is not valid.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("expenses.index"))

        expense = Expense(
            expense_date=expense_date,
            category=category,
            amount=amount,
            description=description,
            user_id=current_user.user_id,
            created_at=datetime.now(),
        )
        db.session.add(expense)
        db.session.flush()
        add_audit("Create Expense", expense, f"{category} expense recorded for Rs {amount}.")
        db.session.commit()
        flash("Expense recorded successfully.", "success")
        return redirect(url_for("expenses.index"))

    rows = db.session.execute(
        text(
            """
            SELECT e.*, COALESCE(u.username, 'Unknown') AS username
            FROM expenses e
            LEFT JOIN users u ON u.user_id = e.user_id
            WHERE e.is_deleted = 0
            ORDER BY e.expense_date DESC, e.expense_id DESC
            """
        )
    ).mappings().all()
    total = db.session.execute(text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE is_deleted = 0")).scalar() or 0
    return render_template("expenses/index.html", rows=rows, categories=EXPENSE_CATEGORIES, today=date.today(), total=total)


@expenses_bp.route("/<int:expense_id>/delete", methods=["POST"])
@admin_required
def delete(expense_id):
    expense = db.session.get(Expense, expense_id)
    if not expense or expense.is_deleted:
        flash("Expense was not found.", "danger")
        return redirect(url_for("expenses.index"))
    expense.is_deleted = True
    add_audit("Delete Expense", expense, f"Expense #{expense_id} soft deleted.")
    db.session.commit()
    flash("Expense removed from active records.", "info")
    return redirect(url_for("expenses.index"))
