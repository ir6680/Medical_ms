from models.user import db


class InventoryAdjustment(db.Model):
    __tablename__ = "inventory_adjustments"

    adjustment_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    adjustment_type = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)


class ExpiredDisposal(db.Model):
    __tablename__ = "expired_disposals"

    disposal_id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)


class Expense(db.Model):
    __tablename__ = "expenses"

    expense_id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime)


class CashRegister(db.Model):
    __tablename__ = "cash_registers"

    register_id = db.Column(db.Integer, primary_key=True)
    register_date = db.Column(db.Date, nullable=False)
    opening_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    closing_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
