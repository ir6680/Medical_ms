from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text

from models.inventory import Inventory
from models.purchase import PurchaseDetail, StockMovement
from models.returns import PurchaseReturn, PurchaseReturnItem, SaleReturn, SaleReturnItem
from models.sales import Sale, SaleDetail
from models.setting import AuditLog
from models.user import db
from routes.dashboard import admin_required


returns_bp = Blueprint("returns", __name__, url_prefix="/returns")

SALE_REASONS = ["Wrong Medicine", "Customer Changed Mind", "Damaged Pack", "Billing Mistake", "Other"]
PURCHASE_REASONS = ["Damaged Stock", "Expired Stock", "Wrong Supply", "Company Recall"]


def clean(value):
    return (value or "").strip()


def add_audit(action, entity_type, entity_id, description):
    db.session.add(
        AuditLog(
            user_id=current_user.user_id,
            username=current_user.username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
        )
    )


def int_from_form(name):
    raw = clean(request.form.get(name))
    return int(raw) if raw.isdigit() else None


@returns_bp.route("/sales", methods=["GET", "POST"])
@admin_required
def sales():
    if request.method == "POST":
        sale_id = int_from_form("sale_id")
        detail_id = int_from_form("sale_detail_id")
        quantity = int_from_form("quantity") or 0
        reason = clean(request.form.get("reason"))
        notes = clean(request.form.get("notes"))

        sale = db.session.get(Sale, sale_id) if sale_id else None
        detail = db.session.get(SaleDetail, detail_id) if detail_id else None
        errors = []
        if not sale or not detail or detail.sale_id != sale.sale_id:
            errors.append("Selected sale item was not found.")
        if quantity <= 0:
            errors.append("Return quantity must be greater than 0.")
        if reason not in SALE_REASONS:
            errors.append("Return reason is not valid.")

        already_returned = 0
        if detail:
            already_returned = db.session.execute(
                text("SELECT COALESCE(SUM(quantity), 0) FROM sale_return_items WHERE sale_detail_id = :detail_id"),
                {"detail_id": detail.detail_id},
            ).scalar() or 0
            if quantity > detail.quantity - int(already_returned):
                errors.append("Return quantity cannot exceed remaining sold quantity.")

        inventory_item = None
        if detail:
            inventory_item = (
                Inventory.query.filter(
                    Inventory.medicine_id == detail.medicine_id,
                    Inventory.expiry_date >= date.today(),
                )
                .order_by(Inventory.expiry_date.asc(), Inventory.inventory_id.asc())
                .first()
            )
            if not inventory_item:
                errors.append("Returned medicine cannot be accepted because available batches are expired.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("returns.sales", sale_id=sale_id or ""))

        try:
            subtotal = Decimal(detail.unit_price) * quantity
            sale_return = SaleReturn(
                sale_id=sale.sale_id,
                user_id=current_user.user_id,
                return_date=datetime.now(),
                total_amount=subtotal,
                notes=notes,
            )
            db.session.add(sale_return)
            db.session.flush()

            inventory_item.quantity += quantity
            db.session.add(
                SaleReturnItem(
                    return_id=sale_return.return_id,
                    sale_detail_id=detail.detail_id,
                    medicine_id=detail.medicine_id,
                    batch_no=inventory_item.batch_no,
                    quantity=quantity,
                    unit_price=detail.unit_price,
                    subtotal=subtotal,
                    reason=reason,
                )
            )
            sale.total_amount = max(Decimal(sale.total_amount or 0) - subtotal, Decimal("0"))
            db.session.add(
                StockMovement(
                    medicine_id=detail.medicine_id,
                    batch_no=inventory_item.batch_no,
                    movement_type="Sale Return",
                    quantity=quantity,
                    reference_id=sale_return.return_id,
                    movement_date=datetime.now(),
                    user_id=current_user.user_id,
                    notes=reason,
                )
            )
            add_audit("Create Sale Return", "SaleReturn", sale_return.return_id, f"Sale #{sale.sale_id} returned Rs {subtotal}.")
            db.session.commit()
            flash("Sale return recorded and stock restored.", "success")
            return redirect(url_for("returns.sales", sale_id=sale.sale_id))
        except Exception:
            db.session.rollback()
            flash("Sale return could not be saved. Please try again.", "danger")
            return redirect(url_for("returns.sales", sale_id=sale_id or ""))

    sale_id = request.args.get("sale_id", "").strip()
    sale = None
    items = []
    if sale_id.isdigit():
        sale = db.session.execute(
            text(
                """
                SELECT s.*, COALESCE(u.username, 'Unknown') AS employee
                FROM sales s
                LEFT JOIN users u ON u.user_id = s.employee_id
                WHERE s.sale_id = :sale_id
                """
            ),
            {"sale_id": int(sale_id)},
        ).mappings().first()
        if sale:
            items = db.session.execute(
                text(
                    """
                    SELECT sd.*, m.medicine_name, m.generic_name,
                           COALESCE(SUM(sri.quantity), 0) AS returned_qty
                    FROM sale_details sd
                    JOIN medicines m ON m.medicine_id = sd.medicine_id
                    LEFT JOIN sale_return_items sri ON sri.sale_detail_id = sd.detail_id
                    WHERE sd.sale_id = :sale_id
                    GROUP BY sd.detail_id, sd.sale_id, sd.medicine_id, sd.quantity, sd.unit_price, sd.subtotal, m.medicine_name, m.generic_name
                    ORDER BY sd.detail_id ASC
                    """
                ),
                {"sale_id": int(sale_id)},
            ).mappings().all()

    returns = db.session.execute(
        text(
            """
            SELECT sr.*, COALESCE(u.username, 'Unknown') AS username
            FROM sale_returns sr
            LEFT JOIN users u ON u.user_id = sr.user_id
            ORDER BY sr.return_date DESC, sr.return_id DESC
            LIMIT 40
            """
        )
    ).mappings().all()
    return render_template("returns/sales.html", sale=sale, items=items, sale_id=sale_id, returns=returns, reasons=SALE_REASONS)


@returns_bp.route("/purchases", methods=["GET", "POST"])
@admin_required
def purchases():
    if request.method == "POST":
        purchase_id = int_from_form("purchase_id")
        detail_id = int_from_form("purchase_detail_id")
        quantity = int_from_form("quantity") or 0
        reason = clean(request.form.get("reason"))
        notes = clean(request.form.get("notes"))
        detail = db.session.get(PurchaseDetail, detail_id) if detail_id else None
        errors = []

        if not detail or detail.purchase_id != purchase_id:
            errors.append("Selected purchase item was not found.")
        if quantity <= 0:
            errors.append("Return quantity must be greater than 0.")
        if reason not in PURCHASE_REASONS:
            errors.append("Return reason is not valid.")

        already_returned = 0
        inventory_item = None
        if detail:
            already_returned = db.session.execute(
                text("SELECT COALESCE(SUM(quantity), 0) FROM purchase_return_items WHERE purchase_detail_id = :detail_id"),
                {"detail_id": detail.detail_id},
            ).scalar() or 0
            inventory_item = Inventory.query.filter_by(medicine_id=detail.medicine_id, batch_no=detail.batch_no).first()
            current_stock = inventory_item.quantity if inventory_item else 0
            max_returnable = min(detail.quantity - int(already_returned), current_stock)
            if quantity > max_returnable:
                errors.append("Return quantity cannot exceed purchased, unreturned, and available stock.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("returns.purchases", purchase_id=purchase_id or ""))

        try:
            subtotal = Decimal(detail.purchase_price) * quantity
            purchase_return = PurchaseReturn(
                purchase_id=purchase_id,
                user_id=current_user.user_id,
                return_date=datetime.now(),
                total_amount=subtotal,
                notes=notes,
            )
            db.session.add(purchase_return)
            db.session.flush()

            inventory_item.quantity -= quantity
            db.session.add(
                PurchaseReturnItem(
                    return_id=purchase_return.return_id,
                    purchase_detail_id=detail.detail_id,
                    medicine_id=detail.medicine_id,
                    batch_no=detail.batch_no,
                    quantity=quantity,
                    unit_price=detail.purchase_price,
                    subtotal=subtotal,
                    reason=reason,
                )
            )
            db.session.add(
                StockMovement(
                    medicine_id=detail.medicine_id,
                    batch_no=detail.batch_no,
                    movement_type="Purchase Return",
                    quantity=-quantity,
                    reference_id=purchase_return.return_id,
                    movement_date=datetime.now(),
                    user_id=current_user.user_id,
                    notes=reason,
                )
            )
            add_audit("Create Purchase Return", "PurchaseReturn", purchase_return.return_id, f"Purchase #{purchase_id} returned Rs {subtotal}.")
            db.session.commit()
            flash("Purchase return recorded and stock reduced.", "success")
            return redirect(url_for("returns.purchases", purchase_id=purchase_id))
        except Exception:
            db.session.rollback()
            flash("Purchase return could not be saved. Please try again.", "danger")
            return redirect(url_for("returns.purchases", purchase_id=purchase_id or ""))

    purchase_id = request.args.get("purchase_id", "").strip()
    purchases = db.session.execute(
        text("SELECT purchase_id, invoice_no, purchase_date FROM purchases ORDER BY purchase_date DESC, purchase_id DESC LIMIT 80")
    ).mappings().all()
    purchase = None
    items = []
    if purchase_id.isdigit():
        purchase = db.session.execute(
            text(
                """
                SELECT p.*, COALESCE(s.supplier_name, 'Unknown Supplier') AS supplier_name
                FROM purchases p
                LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
                WHERE p.purchase_id = :purchase_id
                """
            ),
            {"purchase_id": int(purchase_id)},
        ).mappings().first()
        if purchase:
            items = db.session.execute(
                text(
                    """
                    SELECT pd.*, m.medicine_name, m.generic_name,
                           COALESCE(SUM(pri.quantity), 0) AS returned_qty,
                           COALESCE(i.quantity, 0) AS stock_qty
                    FROM purchase_details pd
                    JOIN medicines m ON m.medicine_id = pd.medicine_id
                    LEFT JOIN purchase_return_items pri ON pri.purchase_detail_id = pd.detail_id
                    LEFT JOIN inventory i ON i.medicine_id = pd.medicine_id AND i.batch_no = pd.batch_no
                    WHERE pd.purchase_id = :purchase_id
                    GROUP BY pd.detail_id, pd.purchase_id, pd.medicine_id, pd.batch_no, pd.quantity, pd.purchase_price, pd.sale_price, pd.expiry_date, m.medicine_name, m.generic_name, i.quantity
                    ORDER BY pd.detail_id ASC
                    """
                ),
                {"purchase_id": int(purchase_id)},
            ).mappings().all()

    returns = db.session.execute(
        text(
            """
            SELECT pr.*, COALESCE(u.username, 'Unknown') AS username
            FROM purchase_returns pr
            LEFT JOIN users u ON u.user_id = pr.user_id
            ORDER BY pr.return_date DESC, pr.return_id DESC
            LIMIT 40
            """
        )
    ).mappings().all()
    return render_template("returns/purchases.html", purchase=purchase, purchases=purchases, purchase_id=purchase_id, items=items, returns=returns, reasons=PURCHASE_REASONS)
