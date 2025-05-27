# -*- coding: utf-8 -*-
class Config:
    SQLALCHEMY_DATABASE_URI = (
        "postgresql://postgres:12345@localhost:5432/agendador_citas"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'pon_aqui_una_clave_secreta_larga_y_segura'

    

