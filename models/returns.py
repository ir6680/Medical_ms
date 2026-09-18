from models.user import db


class SaleReturn(db.Model):
    __tablename__ = "sale_returns"

    return_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer)
    return_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)


class SaleReturnItem(db.Model):
    __tablename__ = "sale_return_items"

    item_id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, nullable=False)
    sale_detail_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(100))
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.String(100), nullable=False)


class PurchaseReturn(db.Model):
    __tablename__ = "purchase_returns"

    return_id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer)
    return_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)


class PurchaseReturnItem(db.Model):
    __tablename__ = "purchase_return_items"

    item_id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, nullable=False)
    purchase_detail_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
