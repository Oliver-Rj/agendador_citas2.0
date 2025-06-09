# init_db.py
from flask import Flask
from config import Config
from models import db, Perfil, Usuario

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    print("✅ Tablas creadas correctamente en PostgreSQL.")
