from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import text

from models.inventory import Inventory
from models.medicine import Medicine
from models.operations import ExpiredDisposal, InventoryAdjustment
from models.purchase import StockMovement
from models.setting import AuditLog
from models.user import db
from flask_login import current_user
from routes.dashboard import admin_required


inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")
ADJUSTMENT_TYPES = ["Stock Found", "Stock Missing", "Damage", "Theft", "Expired Disposal"]


def clean(value):
    return (value or "").strip()


def active_medicine_options():
    return (
        Medicine.query.filter(Medicine.is_deleted == False)  # noqa: E712
        .order_by(Medicine.medicine_name.asc())
        .all()
    )


def parse_decimal(value, label, errors):
    try:
        parsed = Decimal(clean(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a valid number.")
        return Decimal("0")
    if parsed < 0:
        errors.append(f"{label} cannot be negative.")
    return parsed


def parse_quantity(value, errors):
    try:
        quantity = int(clean(value))
    except ValueError:
        quantity = 0
        errors.append("Quantity must be a whole number.")
    if quantity <= 0:
        errors.append("Quantity must be greater than 0.")
    return quantity


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


def validate_inventory_form(form):
    errors = []
    medicine_id_raw = clean(form.get("medicine_id"))
    batch_no = clean(form.get("batch_no"))
    purchase_price = parse_decimal(form.get("purchase_price"), "Purchase price", errors)
    sale_price = parse_decimal(form.get("sale_price"), "Sale price", errors)
    quantity_raw = clean(form.get("quantity"))
    expiry_raw = clean(form.get("expiry_date"))

    medicine = None
    if not medicine_id_raw.isdigit():
        errors.append("Medicine is required.")
    else:
        medicine = (
            Medicine.query.filter(Medicine.is_deleted == False)  # noqa: E712
            .filter_by(medicine_id=int(medicine_id_raw))
            .first()
        )
        if not medicine:
            errors.append("Selected medicine was not found.")

    if not batch_no:
        errors.append("Batch number is required.")

    try:
        quantity = int(quantity_raw)
    except ValueError:
        quantity = 0
        errors.append("Quantity must be a whole number.")

    if quantity <= 0:
        errors.append("Quantity must be greater than 0.")

    if sale_price < purchase_price:
        errors.append("Sale price must be greater than or equal to purchase price.")

    try:
        expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
    except ValueError:
        expiry_date = None
        errors.append("Expiry date is required.")

    if expiry_date and expiry_date <= date.today():
        errors.append("Expiry date must be in the future.")

    return {
        "medicine_id": medicine.medicine_id if medicine else None,
        "batch_no": batch_no,
        "purchase_price": purchase_price,
        "sale_price": sale_price,
        "quantity": quantity,
        "expiry_date": expiry_date,
    }, errors


def inventory_analytics():
    row = db.session.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM medicines WHERE is_deleted = 0) AS total_medicines,
                COALESCE(SUM(i.quantity), 0) AS total_units,
                COALESCE(SUM(i.quantity * i.purchase_price), 0) AS inventory_value,
                SUM(CASE WHEN i.quantity BETWEEN 10 AND 20 THEN 1 ELSE 0 END) AS warning_stock_count,
                SUM(CASE WHEN i.quantity < 10 THEN 1 ELSE 0 END) AS critical_stock_count,
                SUM(CASE WHEN i.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS expiring_count,
                SUM(CASE WHEN i.expiry_date < CURDATE() THEN 1 ELSE 0 END) AS expired_count
            FROM inventory i
            """
        )
    ).mappings().first()

    return [
        {"label": "Total Medicines", "value": int(row["total_medicines"] or 0), "icon": "bi-capsule-pill", "accent": "primary"},
        {"label": "Inventory Units", "value": int(row["total_units"] or 0), "icon": "bi-box-seam", "accent": "info"},
        {"label": "Inventory Value", "value": f"Rs {float(row['inventory_value'] or 0):,.2f}", "icon": "bi-bank", "accent": "teal"},
        {"label": "Warning Stock", "value": int(row["warning_stock_count"] or 0), "icon": "bi-exclamation-triangle", "accent": "warning"},
        {"label": "Critical Stock", "value": int(row["critical_stock_count"] or 0), "icon": "bi-exclamation-octagon", "accent": "danger"},
        {"label": "Expiring Count", "value": int(row["expiring_count"] or 0), "icon": "bi-calendar2-x", "accent": "danger"},
        {"label": "Expired Count", "value": int(row["expired_count"] or 0), "icon": "bi-x-circle", "accent": "danger"},
    ]


@inventory_bp.route("/")
@admin_required
def index():
    rows = db.session.execute(
        text(
            """
            SELECT i.*, m.medicine_name, m.generic_name, m.company
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0
            ORDER BY i.expiry_date ASC, i.inventory_id DESC
            """
        )
    ).mappings().all()
    return render_template("inventory/index.html", inventory_items=rows, analytics=inventory_analytics())


@inventory_bp.route("/add", methods=["GET", "POST"])
@admin_required
def add():
    medicines = active_medicine_options()

    if request.method == "POST":
        data, errors = validate_inventory_form(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("inventory/form.html", medicines=medicines, item=data)

        item = Inventory(**data)
        db.session.add(item)
        db.session.commit()
        flash("Inventory batch added successfully.", "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/form.html", medicines=medicines, item={})


@inventory_bp.route("/low-stock")
@admin_required
def low_stock():
    rows = db.session.execute(
        text(
            """
            SELECT m.medicine_id, m.medicine_name, i.batch_no, i.quantity,
                   GREATEST(20 - i.quantity, 0) AS reorder_qty
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0 AND i.quantity <= 20
            ORDER BY i.quantity ASC, m.medicine_name ASC
            """
        )
    ).mappings().all()
    return render_template("inventory/low_stock.html", rows=rows)


@inventory_bp.route("/expiring")
@admin_required
def expiring():
    days = request.args.get("days", "30")
    if days not in {"30", "60", "90"}:
        days = "30"

    expiring_rows = db.session.execute(
        text(
            """
            SELECT i.*, m.medicine_name, m.generic_name
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0
              AND i.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL :days DAY)
            ORDER BY i.expiry_date ASC
            """
        ),
        {"days": int(days)},
    ).mappings().all()

    expired_rows = db.session.execute(
        text(
            """
            SELECT i.*, m.medicine_name, m.generic_name
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0 AND i.expiry_date < CURDATE()
            ORDER BY i.expiry_date ASC
            """
        )
    ).mappings().all()

    return render_template(
        "inventory/expiring.html",
        expiring_rows=expiring_rows,
        expired_rows=expired_rows,
        days=days,
    )


@inventory_bp.route("/adjustments", methods=["GET", "POST"])
@admin_required
def adjustments():
    if request.method == "POST":
        inventory_id_raw = clean(request.form.get("inventory_id"))
        adjustment_type = clean(request.form.get("adjustment_type"))
        notes = clean(request.form.get("notes"))
        errors = []
        quantity = parse_quantity(request.form.get("quantity"), errors)
        item = db.session.get(Inventory, int(inventory_id_raw)) if inventory_id_raw.isdigit() else None
        if not item:
            errors.append("Inventory batch is required.")
        if adjustment_type not in ADJUSTMENT_TYPES:
            errors.append("Adjustment type is not valid.")

        signed_quantity = quantity if adjustment_type == "Stock Found" else -quantity
        if item and item.quantity + signed_quantity < 0:
            errors.append("Adjustment cannot reduce stock below zero.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("inventory.adjustments"))

        try:
            item.quantity += signed_quantity
            adjustment = InventoryAdjustment(
                inventory_id=item.inventory_id,
                medicine_id=item.medicine_id,
                batch_no=item.batch_no,
                quantity=signed_quantity,
                adjustment_type=adjustment_type,
                notes=notes,
                user_id=current_user.user_id,
                created_at=datetime.now(),
            )
            db.session.add(adjustment)
            db.session.flush()
            db.session.add(
                StockMovement(
                    medicine_id=item.medicine_id,
                    batch_no=item.batch_no,
                    movement_type="Adjustment",
                    quantity=signed_quantity,
                    reference_id=adjustment.adjustment_id,
                    movement_date=datetime.now(),
                    user_id=current_user.user_id,
                    notes=adjustment_type,
                )
            )
            add_audit("Create Inventory Adjustment", "InventoryAdjustment", adjustment.adjustment_id, f"{adjustment_type}: {signed_quantity} units.")
            db.session.commit()
            flash("Inventory adjustment saved.", "success")
            return redirect(url_for("inventory.adjustments"))
        except Exception:
            db.session.rollback()
            flash("Inventory adjustment could not be saved.", "danger")

    batches = db.session.execute(
        text(
            """
            SELECT i.*, m.medicine_name, m.generic_name
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0
            ORDER BY m.medicine_name ASC, i.expiry_date ASC
            """
        )
    ).mappings().all()
    history = db.session.execute(
        text(
            """
            SELECT ia.*, m.medicine_name, COALESCE(u.username, 'Unknown') AS username
            FROM inventory_adjustments ia
            JOIN medicines m ON m.medicine_id = ia.medicine_id
            LEFT JOIN users u ON u.user_id = ia.user_id
            ORDER BY ia.created_at DESC, ia.adjustment_id DESC
            LIMIT 80
            """
        )
    ).mappings().all()
    return render_template("inventory/adjustments.html", batches=batches, history=history, adjustment_types=ADJUSTMENT_TYPES)


@inventory_bp.route("/disposals", methods=["GET", "POST"])
@admin_required
def disposals():
    if request.method == "POST":
        inventory_id_raw = clean(request.form.get("inventory_id"))
        reason = clean(request.form.get("reason"))
        errors = []
        quantity = parse_quantity(request.form.get("quantity"), errors)
        item = db.session.get(Inventory, int(inventory_id_raw)) if inventory_id_raw.isdigit() else None
        if not item:
            errors.append("Expired batch is required.")
        elif item.expiry_date >= date.today():
            errors.append("Only expired batches can be disposed from this screen.")
        elif quantity > item.quantity:
            errors.append("Disposal quantity cannot exceed current stock.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("inventory.disposals"))

        try:
            item.quantity -= quantity
            disposal = ExpiredDisposal(
                inventory_id=item.inventory_id,
                medicine_id=item.medicine_id,
                batch_no=item.batch_no,
                quantity=quantity,
                reason=reason,
                user_id=current_user.user_id,
                created_at=datetime.now(),
            )
            db.session.add(disposal)
            db.session.flush()
            db.session.add(
                StockMovement(
                    medicine_id=item.medicine_id,
                    batch_no=item.batch_no,
                    movement_type="Disposal",
                    quantity=-quantity,
                    reference_id=disposal.disposal_id,
                    movement_date=datetime.now(),
                    user_id=current_user.user_id,
                    notes=reason,
                )
            )
            add_audit("Create Expired Disposal", "ExpiredDisposal", disposal.disposal_id, f"Disposed {quantity} expired units.")
            db.session.commit()
            flash("Expired stock disposal recorded.", "success")
            return redirect(url_for("inventory.disposals"))
        except Exception:
            db.session.rollback()
            flash("Expired stock disposal could not be saved.", "danger")

    expired_batches = db.session.execute(
        text(
            """
            SELECT i.*, m.medicine_name, m.generic_name
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0 AND i.expiry_date < CURDATE() AND i.quantity > 0
            ORDER BY i.expiry_date ASC, m.medicine_name ASC
            """
        )
    ).mappings().all()
    history = db.session.execute(
        text(
            """
            SELECT ed.*, m.medicine_name, COALESCE(u.username, 'Unknown') AS username
            FROM expired_disposals ed
            JOIN medicines m ON m.medicine_id = ed.medicine_id
            LEFT JOIN users u ON u.user_id = ed.user_id
            ORDER BY ed.created_at DESC, ed.disposal_id DESC
            LIMIT 80
            """
        )
    ).mappings().all()
    return render_template("inventory/disposals.html", expired_batches=expired_batches, history=history)
