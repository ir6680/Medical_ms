from models.user import db


class Purchase(db.Model):
    __tablename__ = "purchases"

    purchase_id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer)
    invoice_no = db.Column(db.String(100))
    purchase_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)


class PurchaseDetail(db.Model):
    __tablename__ = "purchase_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    movement_id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference_id = db.Column(db.Integer)
    movement_date = db.Column(db.DateTime)
    batch_no = db.Column(db.String(100))
    user_id = db.Column(db.Integer)
    notes = db.Column(db.Text)
