from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, text

from models.inventory import Inventory
from models.medicine import Medicine
from models.purchase import StockMovement
from models.sales import Sale, SaleDetail
from models.setting import AuditLog
from models.user import User, db
from routes.dashboard import admin_required


sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


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


def active_medicines_with_stock():
    return db.session.execute(
        text(
            """
            SELECT m.medicine_id, m.medicine_name, m.generic_name,
                   COALESCE(SUM(CASE
                       WHEN i.quantity > 0 AND i.expiry_date >= CURDATE() THEN i.quantity
                       ELSE 0
                   END), 0) AS available_stock,
                   COALESCE((
                       SELECT i2.sale_price
                       FROM inventory i2
                       WHERE i2.medicine_id = m.medicine_id
                         AND i2.quantity > 0
                         AND i2.expiry_date >= CURDATE()
                       ORDER BY i2.expiry_date ASC, i2.inventory_id ASC
                       LIMIT 1
                   ), 0) AS sale_price
            FROM medicines m
            LEFT JOIN inventory i ON i.medicine_id = m.medicine_id
            WHERE m.is_deleted = 0
            GROUP BY m.medicine_id, m.medicine_name, m.generic_name
            ORDER BY m.medicine_name ASC
            """
        )
    ).mappings().all()


def employees():
    return User.query.order_by(User.username.asc()).all()


def available_stock(medicine_id, sale_date):
    return (
        db.session.query(func.coalesce(func.sum(Inventory.quantity), 0))
        .filter(
            Inventory.medicine_id == medicine_id,
            Inventory.quantity > 0,
            Inventory.expiry_date >= sale_date.date(),
        )
        .scalar()
        or 0
    )


def parse_line_items(form, sale_date):
    errors = []
    items = []
    medicine_ids = form.getlist("medicine_id[]")
    quantities = form.getlist("quantity[]")
    unit_prices = form.getlist("unit_price[]")

    seen_medicines = {}

    for index, medicine_id_raw in enumerate(medicine_ids):
        row_number = index + 1
        medicine_id = clean(medicine_id_raw)
        quantity_raw = clean(quantities[index] if index < len(quantities) else "")
        unit_price = parse_decimal(
            unit_prices[index] if index < len(unit_prices) else "",
            f"Row {row_number} sale price",
            errors,
        )

        if not medicine_id.isdigit():
            errors.append(f"Row {row_number}: medicine is required.")
            medicine_id_value = None
        else:
            medicine_id_value = int(medicine_id)
            medicine = Medicine.query.filter_by(medicine_id=medicine_id_value, is_deleted=False).first()
            if not medicine:
                errors.append(f"Row {row_number}: selected medicine was not found.")

        try:
            quantity = int(quantity_raw)
        except ValueError:
            quantity = 0
            errors.append(f"Row {row_number}: quantity must be a whole number.")

        if quantity <= 0:
            errors.append(f"Row {row_number}: quantity must be greater than 0.")

        if unit_price <= 0:
            errors.append(f"Row {row_number}: sale price must be greater than 0.")

        if medicine_id_value:
            seen_medicines[medicine_id_value] = seen_medicines.get(medicine_id_value, 0) + quantity

        items.append(
            {
                "medicine_id": medicine_id_value,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": unit_price * quantity,
                "available_stock": 0,
            }
        )

    if not items:
        errors.append("At least one sale line item is required.")

    for item in items:
        if not item["medicine_id"]:
            continue
        stock = int(available_stock(item["medicine_id"], sale_date))
        item["available_stock"] = stock
        requested = seen_medicines.get(item["medicine_id"], item["quantity"])
        if requested > stock:
            errors.append(
                f"Medicine #{item['medicine_id']} has only {stock} available non-expired units."
            )

    return items, errors


def deduct_fifo_stock(sale, items):
    for item in items:
        remaining = item["quantity"]
        batches = (
            Inventory.query.filter(
                Inventory.medicine_id == item["medicine_id"],
                Inventory.quantity > 0,
                Inventory.expiry_date >= sale.sale_date.date(),
            )
            .order_by(Inventory.expiry_date.asc(), Inventory.inventory_id.asc())
            .all()
        )

        for batch in batches:
            if remaining <= 0:
                break
            deducted = min(batch.quantity, remaining)
            batch.quantity -= deducted
            remaining -= deducted
            db.session.add(
                StockMovement(
                    medicine_id=item["medicine_id"],
                    batch_no=batch.batch_no,
                    movement_type="Sale",
                    quantity=-deducted,
                    reference_id=sale.sale_id,
                    movement_date=datetime.now(),
                    user_id=sale.employee_id,
                )
            )

        if remaining > 0:
            raise ValueError("Insufficient stock while deducting inventory.")


@sales_bp.route("/")
@admin_required
def index():
    sales = db.session.execute(
        text(
            """
            SELECT s.sale_id, s.sale_date, s.total_amount,
                   COALESCE(u.username, 'Unknown') AS employee,
                   COUNT(sd.detail_id) AS item_count
            FROM sales s
            LEFT JOIN users u ON u.user_id = s.employee_id
            LEFT JOIN sale_details sd ON sd.sale_id = s.sale_id
            GROUP BY s.sale_id, s.sale_date, s.total_amount, u.username
            ORDER BY s.sale_date DESC, s.sale_id DESC
            """
        )
    ).mappings().all()
    return render_template("sales/index.html", sales=sales)


@sales_bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    medicine_options = active_medicines_with_stock()
    user_options = employees()

    if request.method == "POST":
        employee_id_raw = clean(request.form.get("employee_id"))
        sale_date_raw = clean(request.form.get("sale_date"))

        try:
            sale_date = datetime.strptime(sale_date_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            sale_date = datetime.now()
            flash("Sale date is required.", "danger")
            return render_template(
                "sales/form.html",
                medicines=medicine_options,
                employees=user_options,
                form_data=request.form,
                line_items=[],
                default_sale_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
            )

        items, errors = parse_line_items(request.form, sale_date)

        if not employee_id_raw.isdigit() or not User.query.filter_by(user_id=int(employee_id_raw)).first():
            errors.append("Employee is required.")

        total_amount = sum(item["subtotal"] for item in items)

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sales/form.html",
                medicines=medicine_options,
                employees=user_options,
                form_data=request.form,
                line_items=items,
                default_sale_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
            )

        try:
            sale = Sale(
                employee_id=int(employee_id_raw),
                sale_date=sale_date,
                total_amount=total_amount,
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
                    user_id=int(employee_id_raw),
                    username=User.query.get(int(employee_id_raw)).username,
                    action="Create Sale",
                    entity_type="Sale",
                    entity_id=sale.sale_id,
                    description=f"Sale #{sale.sale_id} saved for Rs {total_amount}.",
                )
            )
            db.session.commit()
            flash("Sale invoice saved and inventory deducted successfully.", "success")
            return redirect(url_for("sales.detail", sale_id=sale.sale_id))
        except Exception:
            db.session.rollback()
            flash("Sale could not be saved. Please review stock and try again.", "danger")

    return render_template(
        "sales/form.html",
        medicines=medicine_options,
        employees=user_options,
        form_data={},
        line_items=[],
        default_sale_date=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    )


@sales_bp.route("/<int:sale_id>")
@admin_required
def detail(sale_id):
    sale = db.session.execute(
        text(
            """
            SELECT s.*, COALESCE(u.username, 'Unknown') AS employee,
                   COALESCE(u.role, 'Employee') AS employee_role
            FROM sales s
            LEFT JOIN users u ON u.user_id = s.employee_id
            WHERE s.sale_id = :sale_id
            """
        ),
        {"sale_id": sale_id},
    ).mappings().first()

    if not sale:
        return render_template("dashboard/placeholder.html", title="Sale Not Found", icon="bi-exclamation-circle"), 404

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

    return render_template("sales/detail.html", sale=sale, items=items)
