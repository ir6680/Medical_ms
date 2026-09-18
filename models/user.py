from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    is_active_account = db.Column("is_active", db.Boolean, nullable=False, default=True)

    def get_id(self):
        return str(self.user_id)

    @property
    def is_admin(self):
        return (self.role or "").lower() == "admin"

    @property
    def is_active(self):
        return bool(self.is_active_account)

    @property
    def display_role(self):
        return (self.role or "Employee").title()

    @property
    def display_name(self):
        return self.full_name or self.username

    def verify_password(self, password):
        try:
            return check_password_hash(self.password_hash, password)
        except ValueError:
            return False

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def __repr__(self):
        return f"<User {self.username}>"


class LoginActivity(db.Model):
    __tablename__ = "login_activity"

    activity_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    login_time = db.Column(db.DateTime, nullable=False)
    logout_time = db.Column(db.DateTime)
    ip_address = db.Column(db.String(45))
