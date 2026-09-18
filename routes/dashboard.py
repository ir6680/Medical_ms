from datetime import date
from decimal import Decimal
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, text

from models.inventory import Inventory
from models.medicine import Medicine, Supplier
from models.user import db


dashboard_bp = Blueprint("dashboard", __name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def money(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def scalar(query, default=0):
    value = db.session.execute(query).scalar()
    return default if value is None else value


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    if not current_user.is_admin:
        return redirect(url_for("pos.index"))

    threshold = current_app.config.get("LOW_STOCK_THRESHOLD", 10)

    total_medicines = Medicine.query.filter_by(is_deleted=False).count()
    total_suppliers = Supplier.query.filter_by(is_deleted=False).count()
    inventory_quantity = db.session.query(func.coalesce(func.sum(Inventory.quantity), 0)).scalar()
    total_sales_today = scalar(
        text("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE DATE(sale_date) = CURDATE()")
    )
    monthly_revenue_total = scalar(
        text(
            """
            SELECT COALESCE(SUM(total_amount), 0)
            FROM sales
            WHERE YEAR(sale_date) = YEAR(CURDATE()) AND MONTH(sale_date) = MONTH(CURDATE())
            """
        )
    )
    total_profit = scalar(
        text(
            """
            SELECT COALESCE(SUM(
                (sd.unit_price - COALESCE((
                    SELECT inv.purchase_price
                    FROM inventory inv
                    WHERE inv.medicine_id = sd.medicine_id
                    ORDER BY inv.expiry_date ASC
                    LIMIT 1
                ), 0)) * sd.quantity
            ), 0)
            FROM sale_details sd
            JOIN sales s ON s.sale_id = sd.sale_id
            """
        )
    )
    todays_purchases = scalar(
        text("SELECT COALESCE(SUM(total_amount), 0) FROM purchases WHERE DATE(purchase_date) = CURDATE()")
    )
    total_purchase_value = scalar(
        text("SELECT COALESCE(SUM(total_amount), 0) FROM purchases")
    )
    inventory_value = scalar(
        text("SELECT COALESCE(SUM(quantity * purchase_price), 0) FROM inventory")
    )
    low_stock_medicines = scalar(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT medicine_id, COALESCE(SUM(quantity), 0) AS stock_qty
                FROM inventory
                GROUP BY medicine_id
                HAVING stock_qty BETWEEN 10 AND 20
            ) low_stock
            """
        )
    )
    critical_stock_medicines = scalar(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT medicine_id, COALESCE(SUM(quantity), 0) AS stock_qty
                FROM inventory
                GROUP BY medicine_id
                HAVING stock_qty < 10
            ) critical_stock
            """
        )
    )
    expiring_medicines = scalar(
        text(
            """
            SELECT COUNT(*)
            FROM inventory
            WHERE expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
              AND quantity > 0
            """
        )
    )
    out_of_stock = scalar(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT medicine_id, COALESCE(SUM(quantity), 0) AS stock_qty
                FROM inventory
                GROUP BY medicine_id
                HAVING stock_qty <= 0
            ) out_stock
            """
        )
    )

    inventory_health_rows = db.session.execute(
        text(
            """
            SELECT
                SUM(CASE WHEN stock_qty > 20 THEN 1 ELSE 0 END) AS healthy,
                SUM(CASE WHEN stock_qty BETWEEN 10 AND 20 THEN 1 ELSE 0 END) AS low,
                SUM(CASE WHEN stock_qty < 10 THEN 1 ELSE 0 END) AS critical,
                COUNT(*) AS total
            FROM (
                SELECT m.medicine_id, COALESCE(SUM(i.quantity), 0) AS stock_qty
                FROM medicines m
                LEFT JOIN inventory i ON i.medicine_id = m.medicine_id
                WHERE m.is_deleted = 0
                GROUP BY m.medicine_id
            ) stock_summary
            """
        )
    ).mappings().first()

    health_total = int(inventory_health_rows["total"] or 0) if inventory_health_rows else 0

    def pct(value):
        if not health_total:
            return 0
        return round((int(value or 0) / health_total) * 100)

    inventory_health = {
        "healthy": pct(inventory_health_rows["healthy"] if inventory_health_rows else 0),
        "low": pct(inventory_health_rows["low"] if inventory_health_rows else 0),
        "critical": pct(inventory_health_rows["critical"] if inventory_health_rows else 0),
    }

    alerts = [
        {
            "message": f"{expiring_medicines} medicines expiring within 30 days",
            "icon": "bi-calendar2-x",
            "url": "/inventory/expiring?days=30",
            "level": "warning",
        },
        {
            "message": f"{low_stock_medicines} medicines in warning stock range",
            "icon": "bi-exclamation-triangle",
            "url": "/inventory/low-stock",
            "level": "warning",
        },
        {
            "message": f"{critical_stock_medicines} medicines in critical stock",
            "icon": "bi-x-circle",
            "url": "/inventory/low-stock",
            "level": "danger",
        },
    ]

    daily_sales = db.session.execute(
        text(
            """
            SELECT DATE(sale_date) AS sale_day, COALESCE(SUM(total_amount), 0) AS revenue
            FROM sales
            WHERE sale_date >= DATE_SUB(CURDATE(), INTERVAL 29 DAY)
            GROUP BY DATE(sale_date)
            ORDER BY sale_day
            """
        )
    ).mappings().all()

    monthly_revenue = db.session.execute(
        text(
            """
            SELECT DATE_FORMAT(sale_date, '%b %Y') AS sale_month,
                   DATE_FORMAT(sale_date, '%Y-%m') AS month_key,
                   COALESCE(SUM(total_amount), 0) AS revenue
            FROM sales
            WHERE sale_date >= DATE_SUB(CURDATE(), INTERVAL 11 MONTH)
            GROUP BY month_key, sale_month
            ORDER BY month_key
            """
        )
    ).mappings().all()

    categories = db.session.execute(
        text(
            """
            SELECT COALESCE(NULLIF(category, ''), 'Uncategorized') AS category,
                   COUNT(*) AS medicine_count
            FROM medicines
            GROUP BY COALESCE(NULLIF(category, ''), 'Uncategorized')
            ORDER BY medicine_count DESC
            LIMIT 8
            """
        )
    ).mappings().all()

    recent_sales = db.session.execute(
        text(
            """
            SELECT s.sale_id, s.sale_date, s.total_amount, COALESCE(u.username, 'Unknown') AS employee
            FROM sales s
            LEFT JOIN users u ON u.user_id = s.employee_id
            ORDER BY s.sale_date DESC
            LIMIT 6
            """
        )
    ).mappings().all()

    recent_purchases = db.session.execute(
        text(
            """
            SELECT p.purchase_id, p.purchase_date, p.total_amount,
                   COALESCE(s.supplier_name, 'Unknown Supplier') AS supplier
            FROM purchases p
            LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
            ORDER BY p.purchase_date DESC
            LIMIT 6
            """
        )
    ).mappings().all()

    stats = [
        {
            "label": "Total Medicines",
            "value": total_medicines,
            "icon": "bi-capsule-pill",
            "accent": "primary",
            "note": "Active catalog records",
            "url": "/medicines",
        },
        {
            "label": "Total Suppliers",
            "value": total_suppliers,
            "icon": "bi-truck",
            "accent": "success",
            "note": "Approved vendor network",
            "url": "/suppliers",
        },
        {
            "label": "Inventory Quantity",
            "value": int(inventory_quantity or 0),
            "icon": "bi-box-seam",
            "accent": "info",
            "note": "Units currently in stock",
            "url": "/inventory",
        },
        {
            "label": "Today's Sales Revenue",
            "value": f"Rs {money(total_sales_today):,.2f}",
            "icon": "bi-cash-coin",
            "accent": "teal",
            "note": date.today().strftime("%d %b %Y"),
            "url": "/sales",
        },
        {
            "label": "Monthly Revenue",
            "value": f"Rs {money(monthly_revenue_total):,.2f}",
            "icon": "bi-bar-chart",
            "accent": "primary",
            "note": "Current month",
            "url": "/reports",
        },
        {
            "label": "Total Profit",
            "value": f"Rs {money(total_profit):,.2f}",
            "icon": "bi-graph-up",
            "accent": "success",
            "note": "Estimated from sales",
            "url": "/reports",
        },
        {
            "label": "Today's Purchases",
            "value": f"Rs {money(todays_purchases):,.2f}",
            "icon": "bi-bag-check",
            "accent": "info",
            "note": "Purchase spend today",
            "url": "/purchases",
        },
        {
            "label": "Total Purchase Value",
            "value": f"Rs {money(total_purchase_value):,.2f}",
            "icon": "bi-cart-check",
            "accent": "warning",
            "note": "All-time purchase spend",
            "url": "/purchases",
        },
        {
            "label": "Total Inventory Value",
            "value": f"Rs {money(inventory_value):,.2f}",
            "icon": "bi-bank",
            "accent": "teal",
            "note": "At purchase cost",
            "url": "/inventory",
        },
        {
            "label": "Low Stock",
            "value": low_stock_medicines,
            "icon": "bi-exclamation-triangle",
            "accent": "warning",
            "note": "10 to 20 units",
            "url": "/inventory/low-stock",
        },
        {
            "label": "Critical Stock",
            "value": critical_stock_medicines,
            "icon": "bi-exclamation-octagon",
            "accent": "danger",
            "note": "Below 10 units",
            "url": "/inventory/low-stock",
        },
        {
            "label": "Expiring Soon",
            "value": expiring_medicines,
            "icon": "bi-calendar2-x",
            "accent": "danger",
            "note": "Within next 30 days",
            "url": "/inventory/expiring?days=30",
        },
    ]

    chart_data = {
        "dailySales": {
            "labels": [row["sale_day"].strftime("%d %b") for row in daily_sales],
            "values": [money(row["revenue"]) for row in daily_sales],
        },
        "monthlyRevenue": {
            "labels": [row["sale_month"] for row in monthly_revenue],
            "values": [money(row["revenue"]) for row in monthly_revenue],
        },
        "categories": {
            "labels": [row["category"] for row in categories],
            "values": [int(row["medicine_count"]) for row in categories],
        },
    }

    return render_template(
        "dashboard/dashboard.html",
        stats=stats,
        alerts=alerts,
        inventory_health=inventory_health,
        chart_data=chart_data,
        recent_sales=recent_sales,
        recent_purchases=recent_purchases,
        top_suppliers=db.session.execute(
            text(
                """
                SELECT s.supplier_id, s.supplier_name, COUNT(p.purchase_id) AS purchase_count,
                       COALESCE(SUM(p.total_amount), 0) AS purchase_total
                FROM suppliers s
                LEFT JOIN purchases p ON p.supplier_id = s.supplier_id
                WHERE s.is_deleted = 0
                GROUP BY s.supplier_id, s.supplier_name
                ORDER BY purchase_total DESC, purchase_count DESC
                LIMIT 5
                """
            )
        ).mappings().all(),
    )


@dashboard_bp.route("/medicine-search")
@login_required
def medicine_search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])

    pattern = f"%{query}%"
    medicines = (
        Medicine.query.filter(Medicine.is_deleted == False)  # noqa: E712
        .filter(
            (Medicine.medicine_name.ilike(pattern))
            | (Medicine.generic_name.ilike(pattern))
            | (Medicine.barcode.ilike(pattern))
        )
        .order_by(Medicine.medicine_name.asc())
        .limit(8)
        .all()
    )

    return jsonify(
        [
            {
                "id": medicine.medicine_id,
                "name": medicine.medicine_name,
                "generic": medicine.generic_name,
                "barcode": medicine.barcode,
                "url": f"/medicines/{medicine.medicine_id}",
            }
            for medicine in medicines
        ]
    )
