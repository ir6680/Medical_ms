from models.user import db


class Medicine(db.Model):
    __tablename__ = "medicines"

    medicine_id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(150), nullable=False)
    generic_name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    barcode = db.Column(db.String(100), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    inventory_items = db.relationship(
        "Inventory",
        primaryjoin="Medicine.medicine_id == foreign(Inventory.medicine_id)",
        lazy="dynamic",
        viewonly=True,
    )

    @property
    def status(self):
        return "Inactive" if self.is_deleted else "Active"


class Supplier(db.Model):
    __tablename__ = "suppliers"

    supplier_id = db.Column(db.Integer, primary_key=True)
    supplier_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def status(self):
        return "Inactive" if self.is_deleted else "Active"
