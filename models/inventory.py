from datetime import date

from models.user import db


class Inventory(db.Model):
    __tablename__ = "inventory"

    inventory_id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, nullable=False)
    batch_no = db.Column(db.String(100), nullable=False)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)

    @property
    def stock_status(self):
        if self.quantity > 20:
            return "Healthy"
        if self.quantity >= 10:
            return "Warning"
        return "Critical"

    @property
    def status_class(self):
        if self.quantity > 20:
            return "success"
        if self.quantity >= 10:
            return "warning"
        return "danger"

    @property
    def is_expired(self):
        return self.expiry_date < date.today()
