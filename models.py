# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Perfil(db.Model):
    __tablename__ = 'perfiles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=False)
    usuario_portal = db.Column(db.String(100), nullable=False)
    contrasena_portal = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(50), default='pendiente')
    cita_confirmada = db.Column(db.Boolean, default=False)
    schedule_code = db.Column(db.String(255))
    id_usuario_cita = db.Column(db.String(100), nullable=True)  # Campo necesario
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Perfil {self.id} {self.correo}>"

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Usuario {self.username}>"

# NUEVO MODELO DE CONFIGURACIÓN
class Configuracion(db.Model):
    __tablename__ = 'configuracion'
    id = db.Column(db.Integer, primary_key=True)
    meses = db.Column(db.String(50), default="5,6")  # Guarda lista como "5,6"
    year = db.Column(db.Integer, default=datetime.now().year)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_meses(self):
        """Devuelve la lista de meses como enteros."""
        return [int(m) for m in self.meses.split(",") if m]

    def set_meses(self, lista):
        """Guarda una lista de meses (como [5, 6, 7])."""
        self.meses = ",".join(str(m) for m in lista)
