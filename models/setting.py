from models.user import db


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    setting_key = db.Column(db.String(100), primary_key=True)
    setting_value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(50))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime)
