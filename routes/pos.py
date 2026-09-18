from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from models.medicine import Medicine
from models.sales import Sale, SaleDetail
from models.setting import AuditLog
from models.user import db
from routes.sales import deduct_fifo_stock, parse_line_items


pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


def clean(value):
    return (value or "").strip()


def parse_money(value, label, errors):
    try:
        parsed = Decimal(clean(value) or "0")
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a valid number.")
        return Decimal("0")
    if parsed < 0:
        errors.append(f"{label} cannot be negative.")
    return parsed


def today_summary():
    return db.session.execute(
        text(
            """
            SELECT COUNT(sale_id) AS invoice_count, COALESCE(SUM(total_amount), 0) AS sales_amount
            FROM sales
            WHERE employee_id = :employee_id AND DATE(sale_date) = CURDATE()
            """
        ),
        {"employee_id": current_user.user_id},
    ).mappings().first()


@pos_bp.route("/")
@login_required
def index():
    summary = today_summary()
    return render_template("pos/index.html", summary=summary)


@pos_bp.route("/search")
@login_required
def search():
    query = clean(request.args.get("q"))
    if len(query) < 2:
        return jsonify([])

    rows = db.session.execute(
        text(
            """
            SELECT i.inventory_id, i.medicine_id, i.batch_no, i.quantity, i.sale_price, i.expiry_date,
                   m.medicine_name, m.generic_name, m.barcode
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0
              AND i.quantity > 0
              AND i.expiry_date >= CURDATE()
              AND (
                  m.medicine_name LIKE :pattern
                  OR m.generic_name LIKE :pattern
                  OR m.barcode LIKE :pattern
              )
            ORDER BY m.medicine_name ASC, i.expiry_date ASC, i.inventory_id ASC
            LIMIT 12
            """
        ),
        {"pattern": f"%{query}%"},
    ).mappings().all()

    return jsonify(
        [
            {
                "medicine_id": row["medicine_id"],
                "medicine_name": row["medicine_name"],
                "generic_name": row["generic_name"],
                "barcode": row["barcode"],
                "batch_no": row["batch_no"],
                "available_stock": int(row["quantity"] or 0),
                "sale_price": float(row["sale_price"] or 0),
                "expiry_date": row["expiry_date"].strftime("%Y-%m-%d") if row["expiry_date"] else "",
            }
            for row in rows
        ]
    )


@pos_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    sale_date = datetime.now()
    items, errors = parse_line_items(request.form, sale_date)
    discount = parse_money(request.form.get("discount"), "Discount", errors)
    cash_received = parse_money(request.form.get("cash_received"), "Cash received", errors)
    customer_name = clean(request.form.get("customer_name"))
    customer_phone = clean(request.form.get("customer_phone"))

    total_before_discount = sum(item["subtotal"] for item in items)
    if discount > total_before_discount:
        errors.append("Discount cannot be greater than total amount.")

    grand_total = total_before_discount - discount
    if cash_received < grand_total:
        errors.append("Cash received cannot be less than grand total.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("pos.index"))

    try:
        sale = Sale(
            employee_id=current_user.user_id,
            sale_date=sale_date,
            total_amount=grand_total,
            customer_name=customer_name,
            customer_phone=customer_phone,
            discount=discount,
            cash_received=cash_received,
            change_return=cash_received - grand_total,
        )
        db.session.add(sale)
        db.session.flush()

        for item in items:
            db.session.add(
                SaleDetail(
                    sale_id=sale.sale_id,
                    medicine_id=item["medicine_id"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    subtotal=item["subtotal"],
                )
            )

        deduct_fifo_stock(sale, items)
        db.session.add(
            AuditLog(
                user_id=current_user.user_id,
                username=current_user.username,
                action="POS Sale",
                entity_type="Sale",
                entity_id=sale.sale_id,
                description=f"POS sale #{sale.sale_id} completed for Rs {grand_total}.",
            )
        )
        db.session.commit()
        flash("Sale completed successfully.", "success")
        return redirect(url_for("pos.receipt", sale_id=sale.sale_id))
    except Exception:
        db.session.rollback()
        flash("Sale could not be completed. Please review stock and try again.", "danger")
        return redirect(url_for("pos.index"))


@pos_bp.route("/history")
@login_required
def history():
    rows = db.session.execute(
        text(
            """
            SELECT s.sale_id, s.sale_date, s.total_amount, COUNT(sd.detail_id) AS item_count
            FROM sales s
            LEFT JOIN sale_details sd ON sd.sale_id = s.sale_id
            WHERE s.employee_id = :employee_id
            GROUP BY s.sale_id, s.sale_date, s.total_amount
            ORDER BY s.sale_date DESC, s.sale_id DESC
            """
        ),
        {"employee_id": current_user.user_id},
    ).mappings().all()
    return render_template("pos/history.html", sales=rows)


def sale_for_current_user(sale_id):
    sale = db.session.execute(
        text(
            """
            SELECT s.*, COALESCE(u.username, 'Unknown') AS employee
            FROM sales s
            LEFT JOIN users u ON u.user_id = s.employee_id
            WHERE s.sale_id = :sale_id
            """
        ),
        {"sale_id": sale_id},
    ).mappings().first()
    if not sale:
        return None
    if not current_user.is_admin and sale["employee_id"] != current_user.user_id:
        abort(403)
    return sale


@pos_bp.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale = sale_for_current_user(sale_id)
    if not sale:
        return render_template("dashboard/placeholder.html", title="Receipt Not Found", icon="bi-receipt"), 404

    items = db.session.execute(
        text(
            """
            SELECT sd.*, m.medicine_name, m.generic_name
            FROM sale_details sd
            JOIN medicines m ON m.medicine_id = sd.medicine_id
            WHERE sd.sale_id = :sale_id
            ORDER BY sd.detail_id ASC
            """
        ),
        {"sale_id": sale_id},
    ).mappings().all()
    receipt_type = request.args.get("type", "thermal")
    if receipt_type not in {"thermal", "a4", "print"}:
        receipt_type = "thermal"
    return render_template("pos/receipt.html", sale=sale, items=items, receipt_type=receipt_type)
