from datetime import timedelta
import secrets

from flask import Flask, abort, redirect, request, session, url_for
from flask_login import LoginManager
from sqlalchemy import text

from config import Config
from models.user import User, db
from routes.auth import auth_bp
from routes.cash_register import cash_register_bp
from routes.dashboard import dashboard_bp
from routes.employees import employees_bp
from routes.expenses import expenses_bp
from routes.inventory import inventory_bp
from routes.medicines import medicines_bp
from routes.pos import pos_bp
from routes.purchases import purchases_bp
from routes.reports import reports_bp
from routes.returns import returns_bp
from routes.settings import settings_bp
from routes.stock_movements import stock_movements_bp
from routes.suppliers import suppliers_bp
from routes.sales import sales_bp



login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_DURATION=timedelta(days=14),
    )

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        ensure_database_compatibility()

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(medicines_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(returns_bp)
    app.register_blueprint(stock_movements_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(cash_register_bp)
    

    @app.route("/")
    def index():
        return redirect(url_for("dashboard.dashboard"))

    @app.context_processor
    def inject_csrf_token():
        def csrf_token():
            token = session.get("_csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["_csrf_token"] = token
            return token

        return {"csrf_token": csrf_token}

    @app.before_request
    def protect_post_requests():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None

        token = session.get("_csrf_token")
        submitted_token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
        if not token or not submitted_token or not secrets.compare_digest(token, submitted_token):
            abort(400, description="Invalid CSRF token.")

        return None

    @app.errorhandler(403)
    def forbidden(error):
        return (
            "You do not have permission to access this page.",
            403,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    return app


def ensure_database_compatibility():
    def column_exists(table_name, column_name):
        return db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()

    def add_column_if_missing(table_name, column_name, definition):
        if not column_exists(table_name, column_name):
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
            db.session.commit()

    medicine_column_exists = db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'medicines'
              AND column_name = 'is_deleted'
            """
        )
    ).scalar()

    if not medicine_column_exists:
        db.session.execute(
            text("ALTER TABLE medicines ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0")
        )
        db.session.commit()

    supplier_column_exists = db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'suppliers'
              AND column_name = 'is_deleted'
            """
        )
    ).scalar()

    if not supplier_column_exists:
        db.session.execute(
            text("ALTER TABLE suppliers ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0")
        )
        db.session.commit()

    user_active_column_exists = db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND column_name = 'is_active'
            """
        )
    ).scalar()

    if not user_active_column_exists:
        db.session.execute(
            text("ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1")
        )
        db.session.commit()

    add_column_if_missing("users", "full_name", "VARCHAR(150) NULL")
    add_column_if_missing("users", "phone", "VARCHAR(20) NULL")
    add_column_if_missing("users", "email", "VARCHAR(100) NULL")
    add_column_if_missing("users", "last_login", "DATETIME NULL")
    add_column_if_missing("sales", "customer_name", "VARCHAR(150) NULL")
    add_column_if_missing("sales", "customer_phone", "VARCHAR(30) NULL")
    add_column_if_missing("sales", "discount", "DECIMAL(12,2) NOT NULL DEFAULT 0")
    add_column_if_missing("sales", "cash_received", "DECIMAL(12,2) NOT NULL DEFAULT 0")
    add_column_if_missing("sales", "change_return", "DECIMAL(12,2) NOT NULL DEFAULT 0")
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS stock_movements (
                movement_id INT AUTO_INCREMENT PRIMARY KEY,
                medicine_id INT NOT NULL,
                movement_type VARCHAR(20) NOT NULL,
                quantity INT NOT NULL,
                reference_id INT NULL,
                movement_date DATETIME NULL
            )
            """
        )
    )
    db.session.commit()
    add_column_if_missing("stock_movements", "batch_no", "VARCHAR(100) NULL")
    add_column_if_missing("stock_movements", "user_id", "INT NULL")
    add_column_if_missing("stock_movements", "notes", "TEXT NULL")

    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_returns (
                return_id INT AUTO_INCREMENT PRIMARY KEY,
                sale_id INT NOT NULL,
                user_id INT NULL,
                return_date DATETIME NULL,
                total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                notes TEXT NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sale_return_items (
                item_id INT AUTO_INCREMENT PRIMARY KEY,
                return_id INT NOT NULL,
                sale_detail_id INT NOT NULL,
                medicine_id INT NOT NULL,
                batch_no VARCHAR(100) NULL,
                quantity INT NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                subtotal DECIMAL(12,2) NOT NULL,
                reason VARCHAR(100) NOT NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS purchase_returns (
                return_id INT AUTO_INCREMENT PRIMARY KEY,
                purchase_id INT NOT NULL,
                user_id INT NULL,
                return_date DATETIME NULL,
                total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                notes TEXT NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS purchase_return_items (
                item_id INT AUTO_INCREMENT PRIMARY KEY,
                return_id INT NOT NULL,
                purchase_detail_id INT NOT NULL,
                medicine_id INT NOT NULL,
                batch_no VARCHAR(100) NOT NULL,
                quantity INT NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                subtotal DECIMAL(12,2) NOT NULL,
                reason VARCHAR(100) NOT NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS inventory_adjustments (
                adjustment_id INT AUTO_INCREMENT PRIMARY KEY,
                inventory_id INT NOT NULL,
                medicine_id INT NOT NULL,
                batch_no VARCHAR(100) NOT NULL,
                quantity INT NOT NULL,
                adjustment_type VARCHAR(50) NOT NULL,
                notes TEXT NULL,
                user_id INT NULL,
                created_at DATETIME NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS expired_disposals (
                disposal_id INT AUTO_INCREMENT PRIMARY KEY,
                inventory_id INT NOT NULL,
                medicine_id INT NOT NULL,
                batch_no VARCHAR(100) NOT NULL,
                quantity INT NOT NULL,
                reason TEXT NULL,
                user_id INT NULL,
                created_at DATETIME NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                expense_id INT AUTO_INCREMENT PRIMARY KEY,
                expense_date DATE NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount DECIMAL(12,2) NOT NULL,
                description TEXT NULL,
                user_id INT NULL,
                is_deleted TINYINT(1) NOT NULL DEFAULT 0,
                created_at DATETIME NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cash_registers (
                register_id INT AUTO_INCREMENT PRIMARY KEY,
                register_date DATE NOT NULL,
                opening_cash DECIMAL(12,2) NOT NULL DEFAULT 0,
                closing_cash DECIMAL(12,2) NOT NULL DEFAULT 0,
                notes TEXT NULL,
                user_id INT NULL,
                created_at DATETIME NULL,
                updated_at DATETIME NULL,
                UNIQUE KEY uq_cash_register_date (register_date)
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key VARCHAR(100) PRIMARY KEY,
                setting_value TEXT NULL,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS login_activity (
                activity_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                login_time DATETIME NOT NULL,
                logout_time DATETIME NULL,
                ip_address VARCHAR(45) NULL
            )
            """
        )
    )
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                username VARCHAR(50) NULL,
                action VARCHAR(100) NOT NULL,
                entity_type VARCHAR(50) NULL,
                entity_id INT NULL,
                description TEXT NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    if not str(user_id).isdigit():
        return None
    return db.session.get(User, int(user_id))


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
