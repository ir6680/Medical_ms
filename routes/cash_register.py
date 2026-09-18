from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text

from models.operations import CashRegister
from models.setting import AuditLog
from models.user import db
from routes.dashboard import admin_required, money


cash_register_bp = Blueprint("cash_register", __name__, url_prefix="/cash-register")


def clean(value):
    return (value or "").strip()


def parse_amount(value, label, errors):
    try:
        amount = Decimal(clean(value) or "0")
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a valid number.")
        return Decimal("0")
    if amount < 0:
        errors.append(f"{label} cannot be negative.")
    return amount


def scalar(sql, params):
    return db.session.execute(text(sql), params).scalar() or 0


def register_summary(register_date):
    params = {"day": register_date}
    total_sales = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE DATE(sale_date) = :day", params)
    total_purchases = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM purchases WHERE DATE(purchase_date) = :day", params)
    sale_returns = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sale_returns WHERE DATE(return_date) = :day", params)
    purchase_returns = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM purchase_returns WHERE DATE(return_date) = :day", params)
    expenses = scalar("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE expense_date = :day AND is_deleted = 0", params)
    gross_profit = scalar(
        """
        SELECT COALESCE(SUM(
            (sd.unit_price - COALESCE((
                SELECT pd.purchase_price
                FROM purchase_details pd
                WHERE pd.medicine_id = sd.medicine_id
                ORDER BY pd.detail_id DESC
                LIMIT 1
            ), 0)) * sd.quantity
        ), 0)
        FROM sale_details sd
        JOIN sales s ON s.sale_id = sd.sale_id
        WHERE DATE(s.sale_date) = :day
        """,
        params,
    )
    net_profit = Decimal(str(gross_profit)) - Decimal(str(expenses)) - Decimal(str(sale_returns)) + Decimal(str(purchase_returns))
    return {
        "total_sales": total_sales,
        "total_purchases": total_purchases,
        "sale_returns": sale_returns,
        "purchase_returns": purchase_returns,
        "total_returns": Decimal(str(sale_returns)) + Decimal(str(purchase_returns)),
        "expenses": expenses,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
    }


def add_audit(action, register, description):
    db.session.add(
        AuditLog(
            user_id=current_user.user_id,
            username=current_user.username,
            action=action,
            entity_type="CashRegister",
            entity_id=register.register_id,
            description=description,
        )
    )


@cash_register_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        register_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        register_date = date.today()

    if request.method == "POST":
        errors = []
        try:
            register_date = datetime.strptime(clean(request.form.get("register_date")), "%Y-%m-%d").date()
        except ValueError:
            register_date = date.today()
            errors.append("Register date is required.")
        opening_cash = parse_amount(request.form.get("opening_cash"), "Opening cash", errors)
        closing_cash = parse_amount(request.form.get("closing_cash"), "Closing cash", errors)
        notes = clean(request.form.get("notes"))

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("cash_register.index", date=register_date))

        register = CashRegister.query.filter_by(register_date=register_date).first()
        is_new = not register
        if not register:
            register = CashRegister(register_date=register_date, created_at=datetime.now())
            db.session.add(register)
        register.opening_cash = opening_cash
        register.closing_cash = closing_cash
        register.notes = notes
        register.user_id = current_user.user_id
        register.updated_at = datetime.now()
        db.session.flush()
        add_audit("Create Cash Register" if is_new else "Update Cash Register", register, f"Cash register saved for {register_date}.")
        db.session.commit()
        flash("Cash register saved.", "success")
        return redirect(url_for("cash_register.index", date=register_date))

    register = CashRegister.query.filter_by(register_date=register_date).first()
    summary = register_summary(register_date)
    opening = Decimal(register.opening_cash or 0) if register else Decimal("0")
    closing = Decimal(register.closing_cash or 0) if register else Decimal("0")
    expected_cash = opening + Decimal(str(summary["total_sales"])) - Decimal(str(summary["sale_returns"])) - Decimal(str(summary["expenses"]))
    cash_difference = closing - expected_cash
    registers = CashRegister.query.order_by(CashRegister.register_date.desc()).limit(30).all()
    return render_template(
        "cash_register/index.html",
        register=register,
        registers=registers,
        register_date=register_date,
        summary=summary,
        expected_cash=expected_cash,
        cash_difference=cash_difference,
        money=money,
    )


@cash_register_bp.route("/closing-report")
@admin_required
def closing_report():
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        register_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        register_date = date.today()
    register = CashRegister.query.filter_by(register_date=register_date).first()
    summary = register_summary(register_date)
    return render_template("cash_register/closing_report.html", register=register, register_date=register_date, summary=summary, money=money)
