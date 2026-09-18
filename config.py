class Config:
    SECRET_KEY = "medical_store_secret"

    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://root:Irfan9090%40%40@localhost/medical_store_db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOW_STOCK_THRESHOLD = 10
