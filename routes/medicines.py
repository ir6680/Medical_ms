import csv
from io import StringIO

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from sqlalchemy import func, text

from models.medicine import Medicine
from models.user import db
from routes.dashboard import admin_required


medicines_bp = Blueprint("medicines", __name__, url_prefix="/medicines")


def clean(value):
    return (value or "").strip()


def active_medicines_query():
    return Medicine.query.filter(Medicine.is_deleted == False)  # noqa: E712


def validate_medicine_form(form, medicine_id=None):
    data = {
        "medicine_name": clean(form.get("medicine_name")),
        "generic_name": clean(form.get("generic_name")),
        "company": clean(form.get("company")),
        "category": clean(form.get("category")),
        "barcode": clean(form.get("barcode")),
    }
    errors = []

    for field, label in [
        ("medicine_name", "Medicine name"),
        ("generic_name", "Generic name"),
        ("company", "Company"),
        ("category", "Category"),
        ("barcode", "Barcode"),
    ]:
        if not data[field]:
            errors.append(f"{label} is required.")

    name_query = active_medicines_query().filter(
        func.lower(Medicine.medicine_name) == data["medicine_name"].lower()
    )
    barcode_query = active_medicines_query().filter(
        func.lower(Medicine.barcode) == data["barcode"].lower()
    )

    if medicine_id:
        name_query = name_query.filter(Medicine.medicine_id != medicine_id)
        barcode_query = barcode_query.filter(Medicine.medicine_id != medicine_id)

    if data["medicine_name"] and name_query.first():
        errors.append("A medicine with this name already exists.")

    if data["barcode"] and barcode_query.first():
        errors.append("A medicine with this barcode already exists.")

    return data, errors


def medicine_rows():
    return (
        active_medicines_query()
        .order_by(Medicine.medicine_id.desc())
        .all()
    )


@medicines_bp.route("/")
@admin_required
def index():
    search = clean(request.args.get("q"))
    query = active_medicines_query()

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Medicine.medicine_name.ilike(pattern))
            | (Medicine.generic_name.ilike(pattern))
            | (Medicine.company.ilike(pattern))
            | (Medicine.category.ilike(pattern))
            | (Medicine.barcode.ilike(pattern))
        )

    medicines = query.order_by(Medicine.medicine_id.desc()).all()
    return render_template("medicines/index.html", medicines=medicines, search=search)


@medicines_bp.route("/add", methods=["GET", "POST"])
@admin_required
def add():
    if request.method == "POST":
        data, errors = validate_medicine_form(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("medicines/form.html", medicine=data, mode="Add")

        medicine = Medicine(**data)
        db.session.add(medicine)
        db.session.commit()
        flash("Medicine added successfully.", "success")
        return redirect(url_for("medicines.index"))

    return render_template("medicines/form.html", medicine={}, mode="Add")


@medicines_bp.route("/<int:medicine_id>")
@admin_required
def detail(medicine_id):
    medicine = active_medicines_query().filter_by(medicine_id=medicine_id).first_or_404()

    inventory_items = db.session.execute(
        text(
            """
            SELECT *
            FROM inventory
            WHERE medicine_id = :medicine_id
            ORDER BY expiry_date ASC, batch_no ASC
            """
        ),
        {"medicine_id": medicine_id},
    ).mappings().all()

    stock_history = db.session.execute(
        text(
            """
            SELECT movement_type, quantity, reference_id, movement_date
            FROM stock_movements
            WHERE medicine_id = :medicine_id
            ORDER BY movement_date DESC
            LIMIT 10
            """
        ),
        {"medicine_id": medicine_id},
    ).mappings().all()

    recent_purchases = db.session.execute(
        text(
            """
            SELECT p.purchase_id, p.purchase_date, pd.quantity, pd.purchase_price, pd.sale_price
            FROM purchase_details pd
            JOIN purchases p ON p.purchase_id = pd.purchase_id
            WHERE pd.medicine_id = :medicine_id
            ORDER BY p.purchase_date DESC
            LIMIT 10
            """
        ),
        {"medicine_id": medicine_id},
    ).mappings().all()

    recent_sales = db.session.execute(
        text(
            """
            SELECT s.sale_id, s.sale_date, sd.quantity, sd.unit_price, sd.subtotal
            FROM sale_details sd
            JOIN sales s ON s.sale_id = sd.sale_id
            WHERE sd.medicine_id = :medicine_id
            ORDER BY s.sale_date DESC
            LIMIT 10
            """
        ),
        {"medicine_id": medicine_id},
    ).mappings().all()

    return render_template(
        "medicines/detail.html",
        medicine=medicine,
        inventory_items=inventory_items,
        stock_history=stock_history,
        recent_purchases=recent_purchases,
        recent_sales=recent_sales,
    )


@medicines_bp.route("/<int:medicine_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(medicine_id):
    medicine = active_medicines_query().filter_by(medicine_id=medicine_id).first_or_404()

    if request.method == "POST":
        data, errors = validate_medicine_form(request.form, medicine_id=medicine_id)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("medicines/form.html", medicine={**data, "medicine_id": medicine_id}, mode="Edit")

        for key, value in data.items():
            setattr(medicine, key, value)
        db.session.commit()
        flash("Medicine updated successfully.", "success")
        return redirect(url_for("medicines.detail", medicine_id=medicine.medicine_id))

    return render_template("medicines/form.html", medicine=medicine, mode="Edit")


@medicines_bp.route("/<int:medicine_id>/delete", methods=["POST"])
@admin_required
def delete(medicine_id):
    medicine = active_medicines_query().filter_by(medicine_id=medicine_id).first_or_404()
    medicine.is_deleted = True
    db.session.commit()
    flash("Medicine moved out of active catalog.", "info")
    return redirect(url_for("medicines.index"))


@medicines_bp.route("/export/csv")
@admin_required
def export_csv():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Medicine ID", "Medicine Name", "Generic Name", "Company", "Category", "Barcode", "Status"])
    for medicine in medicine_rows():
        writer.writerow(
            [
                medicine.medicine_id,
                medicine.medicine_name,
                medicine.generic_name,
                medicine.company,
                medicine.category,
                medicine.barcode,
                medicine.status,
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=medicines.csv"},
    )


@medicines_bp.route("/export/excel")
@admin_required
def export_excel():
    medicines = medicine_rows()
    return render_template("medicines/export.xls", medicines=medicines), 200, {
        "Content-Type": "application/vnd.ms-excel",
        "Content-Disposition": "attachment; filename=medicines.xls",
    }
