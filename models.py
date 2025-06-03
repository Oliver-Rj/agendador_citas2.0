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
    schedule_code = db.Column(db.String(255))  # 👈 Este es el nuevo campo
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

