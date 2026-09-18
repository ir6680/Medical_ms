import csv
from datetime import date, datetime, timedelta
from io import StringIO

from flask import Blueprint, Response, render_template, request
from sqlalchemy import text

from models.user import db
from routes.dashboard import admin_required, money


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def sales_range():
    today = date.today()
    period = request.args.get("period", "month")
    if period == "today":
        return today, today, period
    if period == "week":
        return today - timedelta(days=today.weekday()), today, period
    if period == "custom":
        start = parse_date(request.args.get("start_date"), today.replace(day=1))
        end = parse_date(request.args.get("end_date"), today)
        if start > end:
            start, end = end, start
        return start, end, period
    return today.replace(day=1), today, "month"


def purchase_range():
    today = date.today()
    start = parse_date(request.args.get("purchase_start"), today.replace(day=1))
    end = parse_date(request.args.get("purchase_end"), today)
    if start > end:
        start, end = end, start
    supplier_id = request.args.get("supplier_id", "")
    supplier_id = int(supplier_id) if supplier_id.isdigit() else None
    return start, end, supplier_id


def scalar(sql, params=None):
    value = db.session.execute(text(sql), params or {}).scalar()
    return value or 0


def sales_summary(start, end):
    row = db.session.execute(
        text(
            """
            SELECT COALESCE(SUM(s.total_amount), 0) AS revenue,
                   COUNT(s.sale_id) AS invoice_count,
                   COALESCE(SUM(sd.quantity), 0) AS total_units,
                   COALESCE(SUM(
                       (sd.unit_price - COALESCE((
                           SELECT pd.purchase_price
                           FROM purchase_details pd
                           WHERE pd.medicine_id = sd.medicine_id
                           ORDER BY pd.detail_id DESC
                           LIMIT 1
                       ), 0)) * sd.quantity
                   ), 0) AS profit
            FROM sales s
            LEFT JOIN sale_details sd ON sd.sale_id = s.sale_id
            WHERE DATE(s.sale_date) BETWEEN :start_date AND :end_date
            """
        ),
        {"start_date": start, "end_date": end},
    ).mappings().first()
    return row


def purchase_summary(start, end, supplier_id):
    where_supplier = "AND p.supplier_id = :supplier_id" if supplier_id else ""
    return db.session.execute(
        text(
            f"""
            SELECT COALESCE(SUM(p.total_amount), 0) AS purchase_amount,
                   COUNT(p.purchase_id) AS purchase_count
            FROM purchases p
            WHERE DATE(p.purchase_date) BETWEEN :start_date AND :end_date
            {where_supplier}
            """
        ),
        {"start_date": start, "end_date": end, "supplier_id": supplier_id},
    ).mappings().first()


def inventory_summary():
    return db.session.execute(
        text(
            """
            SELECT COALESCE(SUM(i.quantity), 0) AS current_stock,
                   COALESCE(SUM(i.quantity * i.purchase_price), 0) AS inventory_value,
                   SUM(CASE WHEN i.quantity BETWEEN 10 AND 20 THEN 1 ELSE 0 END) AS low_stock,
                   SUM(CASE WHEN i.quantity < 10 THEN 1 ELSE 0 END) AS critical_stock,
                   SUM(CASE WHEN i.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS expiring,
                   SUM(CASE WHEN i.expiry_date < CURDATE() THEN 1 ELSE 0 END) AS expired
            FROM inventory i
            """
        )
    ).mappings().first()


def report_rows(report_type, start=None, end=None, supplier_id=None):
    if report_type == "sales":
        return db.session.execute(
            text(
                """
                SELECT s.sale_id AS id, s.sale_date AS report_date,
                       COALESCE(u.username, 'Unknown') AS party,
                       COUNT(sd.detail_id) AS count_value,
                       COALESCE(s.total_amount, 0) AS amount
                FROM sales s
                LEFT JOIN users u ON u.user_id = s.employee_id
                LEFT JOIN sale_details sd ON sd.sale_id = s.sale_id
                WHERE DATE(s.sale_date) BETWEEN :start_date AND :end_date
                GROUP BY s.sale_id, s.sale_date, u.username, s.total_amount
                ORDER BY s.sale_date DESC
                """
            ),
            {"start_date": start, "end_date": end},
        ).mappings().all()
    if report_type == "purchases":
        where_supplier = "AND p.supplier_id = :supplier_id" if supplier_id else ""
        return db.session.execute(
            text(
                f"""
                SELECT p.purchase_id AS id, p.purchase_date AS report_date,
                       COALESCE(s.supplier_name, 'Unknown Supplier') AS party,
                       1 AS count_value,
                       COALESCE(p.total_amount, 0) AS amount
                FROM purchases p
                LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id
                WHERE DATE(p.purchase_date) BETWEEN :start_date AND :end_date
                {where_supplier}
                ORDER BY p.purchase_date DESC
                """
            ),
            {"start_date": start, "end_date": end, "supplier_id": supplier_id},
        ).mappings().all()
    return db.session.execute(
        text(
            """
            SELECT i.inventory_id AS id, i.expiry_date AS report_date,
                   m.medicine_name AS party,
                   i.quantity AS count_value,
                   COALESCE(i.quantity * i.purchase_price, 0) AS amount
            FROM inventory i
            JOIN medicines m ON m.medicine_id = i.medicine_id
            WHERE m.is_deleted = 0
            ORDER BY i.expiry_date ASC, m.medicine_name ASC
            """
        )
    ).mappings().all()


def export_response(report_type, export_format, rows):
    title = f"{report_type.title()} Report"
    if export_format == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Date", "Name", "Count/Qty", "Amount"])
        for row in rows:
            writer.writerow([row["id"], row["report_date"], row["party"], row["count_value"], row["amount"]])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"},
        )
    if export_format == "excel":
        return render_template("reports/export.xls", title=title, rows=rows), 200, {
            "Content-Type": "application/vnd.ms-excel",
            "Content-Disposition": f"attachment; filename={report_type}_report.xls",
        }
    return render_template("reports/pdf.html", title=title, rows=rows)


@reports_bp.route("/", strict_slashes=False)
@admin_required
def index():
    sale_start, sale_end, sale_period = sales_range()
    purchase_start, purchase_end, supplier_id = purchase_range()
    export_type = request.args.get("export")
    export_format = request.args.get("format")

    if export_type in {"sales", "purchases", "inventory"} and export_format in {"csv", "excel", "pdf"}:
        rows = report_rows(export_type, sale_start if export_type == "sales" else purchase_start, sale_end if export_type == "sales" else purchase_end, supplier_id)
        return export_response(export_type, export_format, rows)

    sales = sales_summary(sale_start, sale_end)
    purchases = purchase_summary(purchase_start, purchase_end, supplier_id)
    inventory = inventory_summary()
    todays_sales_total = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE DATE(sale_date) = CURDATE()")
    monthly_revenue_total = scalar(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM sales
        WHERE YEAR(sale_date)=YEAR(CURDATE()) AND MONTH(sale_date)=MONTH(CURDATE())
        """
    )
    total_purchase_value = scalar("SELECT COALESCE(SUM(total_amount), 0) FROM purchases")

    kpis = [
        {"label": "Today's Sales", "value": f"Rs {money(todays_sales_total):,.2f}", "icon": "bi-cash-coin", "accent": "teal"},
        {"label": "Monthly Revenue", "value": f"Rs {money(monthly_revenue_total):,.2f}", "icon": "bi-bar-chart", "accent": "primary"},
        {"label": "Total Purchases", "value": f"Rs {money(total_purchase_value):,.2f}", "icon": "bi-bag-check", "accent": "info"},
        {"label": "Total Profit", "value": f"Rs {money(sales['profit']):,.2f}", "icon": "bi-graph-up", "accent": "success"},
        {"label": "Inventory Value", "value": f"Rs {money(inventory['inventory_value']):,.2f}", "icon": "bi-bank", "accent": "teal"},
        {"label": "Total Medicines", "value": scalar('SELECT COUNT(*) FROM medicines WHERE is_deleted = 0'), "icon": "bi-capsule-pill", "accent": "primary"},
        {"label": "Low Stock Medicines", "value": int(inventory["low_stock"] or 0), "icon": "bi-exclamation-triangle", "accent": "warning"},
        {"label": "Expiring Medicines", "value": int(inventory["expiring"] or 0), "icon": "bi-calendar2-x", "accent": "danger"},
    ]

    top_selling = db.session.execute(
        text(
            """
            SELECT m.medicine_name, COALESCE(SUM(sd.quantity), 0) AS quantity_sold,
                   COALESCE(SUM(sd.subtotal), 0) AS revenue
            FROM sale_details sd
            JOIN medicines m ON m.medicine_id = sd.medicine_id
            GROUP BY m.medicine_id, m.medicine_name
            ORDER BY quantity_sold DESC, revenue DESC
            LIMIT 8
            """
        )
    ).mappings().all()

    top_suppliers = db.session.execute(
        text(
            """
            SELECT s.supplier_name, COUNT(p.purchase_id) AS purchase_count,
                   COALESCE(SUM(p.total_amount), 0) AS purchase_amount
            FROM suppliers s
            LEFT JOIN purchases p ON p.supplier_id = s.supplier_id
            WHERE s.is_deleted = 0
            GROUP BY s.supplier_id, s.supplier_name
            ORDER BY purchase_amount DESC, purchase_count DESC
            LIMIT 8
            """
        )
    ).mappings().all()

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

    chart_data = {
        "reportDailySales": {"labels": [row["sale_day"].strftime("%d %b") for row in daily_sales], "values": [money(row["revenue"]) for row in daily_sales]},
        "reportMonthlyRevenue": {"labels": [row["sale_month"] for row in monthly_revenue], "values": [money(row["revenue"]) for row in monthly_revenue]},
        "reportTopSelling": {"labels": [row["medicine_name"] for row in top_selling], "values": [int(row["quantity_sold"] or 0) for row in top_selling]},
        "reportInventoryHealth": {
            "labels": ["Healthy", "Low", "Critical", "Expired"],
            "values": [
                max(int(inventory["current_stock"] or 0) - int(inventory["low_stock"] or 0) - int(inventory["critical_stock"] or 0), 0),
                int(inventory["low_stock"] or 0),
                int(inventory["critical_stock"] or 0),
                int(inventory["expired"] or 0),
            ],
        },
    }

    suppliers = db.session.execute(text("SELECT supplier_id, supplier_name FROM suppliers WHERE is_deleted = 0 ORDER BY supplier_name")).mappings().all()
    return render_template(
        "reports/index.html",
        kpis=kpis,
        sales=sales,
        purchases=purchases,
        inventory=inventory,
        top_selling=top_selling,
        top_suppliers=top_suppliers,
        suppliers=suppliers,
        sale_start=sale_start,
        sale_end=sale_end,
        sale_period=sale_period,
        purchase_start=purchase_start,
        purchase_end=purchase_end,
        selected_supplier_id=supplier_id,
        chart_data=chart_data,
    )
