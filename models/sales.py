from models.user import db


class Sale(db.Model):
    __tablename__ = "sales"

    sale_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer)
    sale_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    customer_name = db.Column(db.String(150))
    customer_phone = db.Column(db.String(30))
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cash_received = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    change_return = db.Column(db.Numeric(12, 2), nullable=False, default=0)


class SaleDetail(db.Model):
    __tablename__ = "sale_details"

    detail_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, nullable=False)
    medicine_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
