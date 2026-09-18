from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text

from models.inventory import Inventory
from models.medicine import Medicine, Supplier
from models.purchase import Purchase, PurchaseDetail, StockMovement
from models.setting import AuditLog
from models.user import db
from routes.dashboard import admin_required


purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


def clean(value):
    return (value or "").strip()


def parse_decimal(value, label, errors):
    try:
        parsed = Decimal(clean(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a valid number.")
        return Decimal("0")
    if parsed < 0:
        errors.append(f"{label} cannot be negative.")
    return parsed


def parse_line_items(form):
    errors = []
    items = []
    medicine_ids = form.getlist("medicine_id[]")
    batch_numbers = form.getlist("batch_no[]")
    quantities = form.getlist("quantity[]")
    purchase_prices = form.getlist("purchase_price[]")
    sale_prices = form.getlist("sale_price[]")
    expiry_dates = form.getlist("expiry_date[]")

    for index, medicine_id_raw in enumerate(medicine_ids):
        row_number = index + 1
        medicine_id = clean(medicine_id_raw)
        batch_no = clean(batch_numbers[index] if index < len(batch_numbers) else "")
        quantity_raw = clean(quantities[index] if index < len(quantities) else "")
        expiry_raw = clean(expiry_dates[index] if index < len(expiry_dates) else "")
        purchase_price = parse_decimal(purchase_prices[index] if index < len(purchase_prices) else "", f"Row {row_number} purchase price", errors)
        sale_price = parse_decimal(sale_prices[index] if index < len(sale_prices) else "", f"Row {row_number} sale price", errors)

        if not medicine_id.isdigit():
            errors.append(f"Row {row_number}: medicine is required.")
            medicine_id_value = None
        else:
            medicine_id_value = int(medicine_id)
            if not Medicine.query.filter_by(medicine_id=medicine_id_value, is_deleted=False).first():
                errors.append(f"Row {row_number}: selected medicine was not found.")

        if not batch_no:
            errors.append(f"Row {row_number}: batch number is required.")

        try:
            quantity = int(quantity_raw)
        except ValueError:
            quantity = 0
            errors.append(f"Row {row_number}: quantity must be a whole number.")

        if quantity <= 0:
            errors.append(f"Row {row_number}: quantity must be greater than 0.")

        if sale_price < purchase_price:
            errors.append(f"Row {row_number}: sale price must be greater than or equal to purchase price.")

        try:
            expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            expiry_date = None
            errors.append(f"Row {row_number}: expiry date is required.")

        if expiry_date and expiry_date <= datetime.today().date():
            errors.append(f"Row {row_number}: expiry date must be in the future.")

        items.append(
            {
                "medicine_id": medicine_id_value,
                "batch_no": batch_no,
                "quantity": quantity,
                "purchase_price": purchase_price,
                "sale_price": sale_price,
                "expiry_date": expiry_date,
                "subtotal": purchase_price * quantity,
            }
        )

    if not items:
        errors.append("At least one purchase line item is required.")

    return items, errors


def form_options():
    suppliers = Supplier.query.filter_by(is_deleted=False).order_by(Supplier.supplier_name.asc()).all()
    medicines = Medicine.query.filter_by(is_deleted=False).order_by(Medicine.medicine_name.asc()).all()
    return suppliers, medicines


@purchases_bp.route("/")
@admin_required
def index():
    purchases = db.session.execute(
        text(
            """
            SELECT p.purchase_id, p.invoice_no, p.purchase_date, p.total_amount,
                   COALESCE(s.supplier_name, 'Unknown Supplier') AS supplier_name
            FROM purchases p
            LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
            ORDER BY p.purchase_date DESC, p.purchase_id DESC
            """
        )
    ).mappings().all()
    return render_template("purchases/index.html", purchases=purchases)


@purchases_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    suppliers, medicines = form_options()

    if request.method == "POST":
        supplier_id_raw = clean(request.form.get("supplier_id"))
        purchase_date_raw = clean(request.form.get("purchase_date"))
        items, errors = parse_line_items(request.form)

        if not supplier_id_raw.isdigit() or not Supplier.query.filter_by(supplier_id=int(supplier_id_raw), is_deleted=False).first():
            errors.append("Supplier is required.")

        try:
            purchase_date = datetime.strptime(purchase_date_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            purchase_date = datetime.now()
            errors.append("Purchase date is required.")

        total_amount = sum(item["subtotal"] for item in items)

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "purchases/form.html",
                suppliers=suppliers,
                medicines=medicines,
                form_data=request.form,
                line_items=items,
                default_purchase_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
            )

        try:
            purchase = Purchase(
                supplier_id=int(supplier_id_raw),
                purchase_date=purchase_date,
                total_amount=total_amount,
            )
            db.session.add(purchase)
            db.session.flush()

            purchase.invoice_no = f"PUR-{purchase.purchase_id:06d}"

            for item in items:
                detail = PurchaseDetail(
                    purchase_id=purchase.purchase_id,
                    medicine_id=item["medicine_id"],
                    batch_no=item["batch_no"],
                    quantity=item["quantity"],
                    purchase_price=item["purchase_price"],
                    sale_price=item["sale_price"],
                    expiry_date=item["expiry_date"],
                )
                db.session.add(detail)

                inventory_item = Inventory.query.filter_by(
                    medicine_id=item["medicine_id"],
                    batch_no=item["batch_no"],
                ).first()

                if inventory_item:
                    inventory_item.quantity += item["quantity"]
                    inventory_item.purchase_price = item["purchase_price"]
                    inventory_item.sale_price = item["sale_price"]
                    inventory_item.expiry_date = item["expiry_date"]
                else:
                    inventory_item = Inventory(
                        medicine_id=item["medicine_id"],
                        batch_no=item["batch_no"],
                        purchase_price=item["purchase_price"],
                        sale_price=item["sale_price"],
                        quantity=item["quantity"],
                        expiry_date=item["expiry_date"],
                    )
                    db.session.add(inventory_item)

                db.session.add(
                    StockMovement(
                        medicine_id=item["medicine_id"],
                        batch_no=item["batch_no"],
                        movement_type="Purchase",
                        quantity=item["quantity"],
                        reference_id=purchase.purchase_id,
                        movement_date=datetime.now(),
                        user_id=current_user.user_id,
                    )
                )

            db.session.add(
                AuditLog(
                    action="Create Purchase",
                    user_id=current_user.user_id,
                    username=current_user.username,
                    entity_type="Purchase",
                    entity_id=purchase.purchase_id,
                    description=f"Purchase {purchase.invoice_no} saved for Rs {total_amount}.",
                )
            )
            db.session.commit()
            flash("Purchase invoice saved and inventory updated successfully.", "success")
            return redirect(url_for("purchases.detail", purchase_id=purchase.purchase_id))
        except Exception:
            db.session.rollback()
            flash("Purchase could not be saved. Please review the invoice and try again.", "danger")

    return render_template(
        "purchases/form.html",
        suppliers=suppliers,
        medicines=medicines,
        form_data={},
        line_items=[],
        default_purchase_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    )


@purchases_bp.route("/<int:purchase_id>")
@admin_required
def detail(purchase_id):
    purchase = db.session.execute(
        text(
            """
            SELECT p.*, COALESCE(s.supplier_name, 'Unknown Supplier') AS supplier_name,
                   s.phone, s.email, s.address
            FROM purchases p
            LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
            WHERE p.purchase_id = :purchase_id
            """
        ),
        {"purchase_id": purchase_id},
    ).mappings().first()

    if not purchase:
        return render_template("dashboard/placeholder.html", title="Purchase Not Found", icon="bi-exclamation-circle"), 404

    items = db.session.execute(
        text(
            """
            SELECT pd.*, m.medicine_name, m.generic_name
            FROM purchase_details pd
            JOIN medicines m ON m.medicine_id = pd.medicine_id
            WHERE pd.purchase_id = :purchase_id
            ORDER BY pd.detail_id ASC
            """
        ),
        {"purchase_id": purchase_id},
    ).mappings().all()

    return render_template("purchases/detail.html", purchase=purchase, items=items)


@purchases_bp.route("/<int:purchase_id>/pdf")
@admin_required
def pdf(purchase_id):
    purchase = db.session.execute(
        text(
            """
            SELECT p.*, COALESCE(s.supplier_name, 'Unknown Supplier') AS supplier_name,
                   s.phone, s.email, s.address
            FROM purchases p
            LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
            WHERE p.purchase_id = :purchase_id
            """
        ),
        {"purchase_id": purchase_id},
    ).mappings().first()

    if not purchase:
        return render_template("dashboard/placeholder.html", title="Purchase Not Found", icon="bi-exclamation-circle"), 404

    items = db.session.execute(
        text(
            """
            SELECT pd.*, m.medicine_name, m.generic_name
            FROM purchase_details pd
            JOIN medicines m ON m.medicine_id = pd.medicine_id
            WHERE pd.purchase_id = :purchase_id
            ORDER BY pd.detail_id ASC
            """
        ),
        {"purchase_id": purchase_id},
    ).mappings().all()

    return render_template("purchases/pdf.html", purchase=purchase, items=items)
