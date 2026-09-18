import csv
from io import StringIO

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from sqlalchemy import func, text

from models.medicine import Supplier
from models.user import db
from routes.dashboard import admin_required


suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


def clean(value):
    return (value or "").strip()


def active_suppliers_query():
    return Supplier.query.filter(Supplier.is_deleted == False)  # noqa: E712


def validate_supplier_form(form, supplier_id=None):
    data = {
        "supplier_name": clean(form.get("supplier_name")),
        "phone": clean(form.get("phone")),
        "email": clean(form.get("email")),
        "address": clean(form.get("address")),
    }
    errors = []

    if not data["supplier_name"]:
        errors.append("Supplier name is required.")

    duplicate_query = active_suppliers_query().filter(
        func.lower(Supplier.supplier_name) == data["supplier_name"].lower()
    )
    if supplier_id:
        duplicate_query = duplicate_query.filter(Supplier.supplier_id != supplier_id)

    if data["supplier_name"] and duplicate_query.first():
        errors.append("A supplier with this name already exists.")

    if data["email"] and "@" not in data["email"]:
        errors.append("Email address is not valid.")

    return data, errors


@suppliers_bp.route("/")
@admin_required
def index():
    rows = db.session.execute(
        text(
            """
            SELECT s.supplier_id, s.supplier_name, s.phone, s.email, s.address,
                   COUNT(p.purchase_id) AS total_purchases,
                   MAX(p.purchase_date) AS last_purchase_date
            FROM suppliers s
            LEFT JOIN purchases p ON p.supplier_id = s.supplier_id
            WHERE s.is_deleted = 0
            GROUP BY s.supplier_id, s.supplier_name, s.phone, s.email, s.address
            ORDER BY s.supplier_id DESC
            """
        )
    ).mappings().all()
    return render_template("suppliers/index.html", suppliers=rows)


@suppliers_bp.route("/add", methods=["GET", "POST"])
@admin_required
def add():
    if request.method == "POST":
        data, errors = validate_supplier_form(request.form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("suppliers/form.html", supplier=data, mode="Add")

        supplier = Supplier(**data)
        db.session.add(supplier)
        db.session.commit()
        flash("Supplier added successfully.", "success")
        return redirect(url_for("suppliers.index"))

    return render_template("suppliers/form.html", supplier={}, mode="Add")


@suppliers_bp.route("/<int:supplier_id>")
@admin_required
def detail(supplier_id):
    supplier = active_suppliers_query().filter_by(supplier_id=supplier_id).first_or_404()
    purchases = db.session.execute(
        text(
            """
            SELECT purchase_id, invoice_no, purchase_date, total_amount
            FROM purchases
            WHERE supplier_id = :supplier_id
            ORDER BY purchase_date DESC
            """
        ),
        {"supplier_id": supplier_id},
    ).mappings().all()

    totals = db.session.execute(
        text(
            """
            SELECT COUNT(*) AS total_purchases, COALESCE(SUM(total_amount), 0) AS total_amount
            FROM purchases
            WHERE supplier_id = :supplier_id
            """
        ),
        {"supplier_id": supplier_id},
    ).mappings().first()

    return render_template("suppliers/detail.html", supplier=supplier, purchases=purchases, totals=totals)


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(supplier_id):
    supplier = active_suppliers_query().filter_by(supplier_id=supplier_id).first_or_404()

    if request.method == "POST":
        data, errors = validate_supplier_form(request.form, supplier_id=supplier_id)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("suppliers/form.html", supplier={**data, "supplier_id": supplier_id}, mode="Edit")

        for key, value in data.items():
            setattr(supplier, key, value)
        db.session.commit()
        flash("Supplier updated successfully.", "success")
        return redirect(url_for("suppliers.detail", supplier_id=supplier.supplier_id))

    return render_template("suppliers/form.html", supplier=supplier, mode="Edit")


@suppliers_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@admin_required
def delete(supplier_id):
    supplier = active_suppliers_query().filter_by(supplier_id=supplier_id).first_or_404()
    supplier.is_deleted = True
    db.session.commit()
    flash("Supplier moved out of the active list.", "info")
    return redirect(url_for("suppliers.index"))


@suppliers_bp.route("/export/csv")
@admin_required
def export_csv():
    rows = db.session.execute(
        text(
            """
            SELECT s.supplier_id, s.supplier_name, s.phone, s.email, s.address,
                   COUNT(p.purchase_id) AS total_purchases,
                   MAX(p.purchase_date) AS last_purchase_date
            FROM suppliers s
            LEFT JOIN purchases p ON p.supplier_id = s.supplier_id
            WHERE s.is_deleted = 0
            GROUP BY s.supplier_id, s.supplier_name, s.phone, s.email, s.address
            ORDER BY s.supplier_id DESC
            """
        )
    ).mappings().all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Supplier ID", "Supplier Name", "Phone", "Email", "Address", "Total Purchases", "Last Purchase Date"])
    for row in rows:
        writer.writerow(
            [
                row["supplier_id"],
                row["supplier_name"],
                row["phone"],
                row["email"],
                row["address"],
                row["total_purchases"],
                row["last_purchase_date"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=suppliers.csv"},
    )


@suppliers_bp.route("/export/excel")
@admin_required
def export_excel():
    suppliers = db.session.execute(
        text(
            """
            SELECT s.supplier_id, s.supplier_name, s.phone, s.email, s.address,
                   COUNT(p.purchase_id) AS total_purchases,
                   MAX(p.purchase_date) AS last_purchase_date
            FROM suppliers s
            LEFT JOIN purchases p ON p.supplier_id = s.supplier_id
            WHERE s.is_deleted = 0
            GROUP BY s.supplier_id, s.supplier_name, s.phone, s.email, s.address
            ORDER BY s.supplier_id DESC
            """
        )
    ).mappings().all()
    return render_template("suppliers/export.xls", suppliers=suppliers), 200, {
        "Content-Type": "application/vnd.ms-excel",
        "Content-Disposition": "attachment; filename=suppliers.xls",
    }
