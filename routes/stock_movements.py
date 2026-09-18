from flask import Blueprint, render_template, request
from sqlalchemy import text

from models.user import db
from routes.dashboard import admin_required


stock_movements_bp = Blueprint("stock_movements", __name__, url_prefix="/stock-movements")


@stock_movements_bp.route("/")
@admin_required
def index():
    movement_type = request.args.get("type", "")
    where_type = "WHERE sm.movement_type = :movement_type" if movement_type else ""
    rows = db.session.execute(
        text(
            f"""
            SELECT sm.*, m.medicine_name, COALESCE(u.username, 'System') AS username
            FROM stock_movements sm
            JOIN medicines m ON m.medicine_id = sm.medicine_id
            LEFT JOIN users u ON u.user_id = sm.user_id
            {where_type}
            ORDER BY sm.movement_date DESC, sm.movement_id DESC
            LIMIT 500
            """
        ),
        {"movement_type": movement_type},
    ).mappings().all()
    movement_types = ["Purchase", "Sale", "Sale Return", "Purchase Return", "Adjustment", "Disposal"]
    return render_template("stock_movements/index.html", rows=rows, movement_types=movement_types, selected_type=movement_type)
