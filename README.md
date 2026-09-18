# Medical Store Management System

Flask-based Medical Store / Pharmacy Management System for handling medicines, inventory, suppliers, purchases, sales, POS billing, returns, expenses, cash register, reports, employees, settings, and audit logs.

## Project Overview

This project is a web application built with Python Flask, Flask-Login, Flask-SQLAlchemy, SQLAlchemy, PyMySQL, Jinja templates, Bootstrap, and Chart.js. It uses a MySQL database named `medical_store_db` by default.

The app has two main user flows:

- **Admin:** dashboard, medicines, inventory, suppliers, purchases, sales, returns, stock ledger, expenses, cash register, employees, reports, settings, backup/restore, and audit history.
- **Employee:** login and POS-focused workflow for sales/receipts.

## Main Features

- Secure login/logout with Flask-Login
- Admin-only access control for management modules
- CSRF protection for POST/PUT/PATCH/DELETE requests
- Dashboard with sales, purchase, stock, revenue, profit, and expiry analytics
- Global medicine search by name, generic name, or barcode
- Medicine catalog CRUD with CSV/Excel export
- Supplier management with CSV/Excel export
- Inventory batches, low-stock alerts, expiry tracking, adjustments, and expired stock disposals
- Purchase entry with purchase details and stock movement records
- Sales entry with FIFO-style stock deduction
- POS checkout, receipt page, and POS history
- Sale returns and purchase returns
- Stock movement ledger
- Expenses tracking
- Daily cash register and closing report
- Employee/user management with password reset and active/inactive status
- Reports with CSV, Excel, and printable/PDF-style views
- App settings, backup download, restore upload, login activity, and audit logs

## Tech Stack

- **Backend:** Python 3.12, Flask 3.1, Flask-SQLAlchemy, Flask-Login
- **Database:** MySQL with PyMySQL driver
- **Frontend:** Jinja2 templates, Bootstrap Icons, custom CSS/JS
- **ORM:** SQLAlchemy

## Folder Structure

```text
Medical_ms/
+-- app.py                  # Flask app factory, blueprint registration, CSRF, DB compatibility setup
+-- config.py               # App config, MySQL URI, low-stock threshold
+-- models/                 # SQLAlchemy models
+-- routes/                 # Flask blueprints / controllers
+-- templates/              # Jinja templates
+-- static/
|   +-- css/                # Dashboard/app styles
|   +-- js/                 # Dashboard/search scripts
+-- structure.txt           # Older generated folder listing
+-- venv/                   # Local virtual environment, should usually not be committed
```

## Important Files

- `app.py` initializes the Flask app, registers all blueprints, configures login/session behavior, adds CSRF validation, and creates/updates some compatibility tables/columns.
- `config.py` stores the `SECRET_KEY`, MySQL connection string, and `LOW_STOCK_THRESHOLD`.
- `models/user.py` defines `User`, `LoginActivity`, and the shared `db` object.
- `models/medicine.py` defines medicines and suppliers.
- `models/inventory.py` defines inventory batches and stock status helpers.
- `models/purchase.py` defines purchases, purchase details, and stock movements.
- `models/sales.py` defines sales and sale details.
- `models/returns.py` defines sale and purchase returns.
- `models/operations.py` defines adjustments, disposals, expenses, and cash registers.
- `models/setting.py` defines app settings and audit logs.

## Routes / Modules

| Module | URL Prefix | Purpose |
| --- | --- | --- |
| Auth | `/login`, `/logout` | User authentication |
| Dashboard | `/dashboard` | Admin analytics and global search |
| POS | `/pos` | Point-of-sale checkout and receipts |
| Medicines | `/medicines` | Medicine CRUD and exports |
| Inventory | `/inventory` | Batch stock, low stock, expiry, adjustments, disposals |
| Suppliers | `/suppliers` | Supplier CRUD and exports |
| Purchases | `/purchases` | Purchase entry, details, printable view |
| Sales | `/sales` | Manual sales entry and sale detail |
| Returns | `/returns` | Sale returns and purchase returns |
| Stock Ledger | `/stock-movements` | Stock movement history |
| Expenses | `/expenses` | Expense entry and soft delete |
| Cash Register | `/cash-register` | Daily cash open/close summary |
| Employees | `/employees` | Employee/user management |
| Reports | `/reports` | Sales, purchases, inventory reports and exports |
| Settings | `/settings` | Store settings, users, backup/restore, audit logs |

## Database

Default database config in `config.py`:

```python
SQLALCHEMY_DATABASE_URI = "mysql+pymysql://root:Irfan9090%40%40@localhost/medical_store_db"
```

Before running the app, make sure MySQL is running and the database exists:

```sql
CREATE DATABASE medical_store_db;
```

The app contains compatibility logic in `ensure_database_compatibility()` that creates or updates several operational tables, but this project currently does not include a dedicated migration folder or full SQL schema dump. For a fresh setup, initialize the base tables from the models first:

```powershell
.\venv\Scripts\Activate.ps1
python
```

```python
from flask import Flask
from config import Config
from models.user import db
from models.user import User, LoginActivity
from models.medicine import Medicine, Supplier
from models.inventory import Inventory
from models.purchase import Purchase, PurchaseDetail, StockMovement
from models.sales import Sale, SaleDetail
from models.returns import SaleReturn, SaleReturnItem, PurchaseReturn, PurchaseReturnItem
from models.operations import InventoryAdjustment, ExpiredDisposal, Expense, CashRegister
from models.setting import AppSetting, AuditLog

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
```

After this, running `python app.py` will apply the extra compatibility tables/columns defined in `ensure_database_compatibility()`.

## Setup

1. Clone or open the project folder.

```powershell
cd D:\Medical_ms
```

2. Create and activate a virtual environment if needed.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

3. Install dependencies.

```powershell
pip install Flask Flask-SQLAlchemy Flask-Login PyMySQL
```

4. Update database credentials in `config.py` according to your local MySQL setup.

5. Create the MySQL database.

```sql
CREATE DATABASE medical_store_db;
```

6. Initialize tables using the database command shown above.

7. Create an admin user from Python shell.

```python
from app import app
from models.user import db, User
from datetime import datetime

with app.app_context():
    admin = User(
        username="admin",
        role="admin",
        full_name="Administrator",
        created_at=datetime.now(),
        is_active_account=True,
    )
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()
```

8. Run the app.

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Default Login

If you created the sample admin above:

```text
Username: admin
Password: admin123
```

Change this password after first login.

## Configuration Notes

- `SECRET_KEY` is hardcoded in `config.py`; for production, move it to an environment variable.
- MySQL username/password is also hardcoded; for production, use environment variables or a private config file.
- `LOW_STOCK_THRESHOLD` defaults to `10`, while dashboard stock health also displays warning stock around `10-20`.
- Sessions are configured for 8 hours, with HTTP-only cookies and `SameSite=Lax`.

## Development Notes

- `venv/` and `__pycache__/` are local/generated files and should usually be ignored by Git.
- There is no `requirements.txt` yet. You can generate one with:

```powershell
pip freeze > requirements.txt
```

- There is no formal test suite in the current project.
- The project uses direct SQL queries in multiple route files for reporting and summaries.
- Backup/restore is available in Settings for admin users.

## Recommended `.gitignore`

```gitignore
venv/
__pycache__/
*.pyc
.env
instance/
*.log
```

## Common Issues

### Database connection error

Check that MySQL is running, `medical_store_db` exists, and `config.py` has the correct username/password.

### Login works but dashboard redirects to POS

The logged-in user is not an admin. Set `role` to `admin` for dashboard access.

### Missing table error

Run `db.create_all()` with all models imported, or restore a valid SQL backup from Settings.

### CSRF token error

Forms must include:

```html
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
```


