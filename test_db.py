# -*- coding: utf-8 -*-
from sqlalchemy import create_engine

uri = "postgresql://postgres:Jesucristo1992@localhost:5432/agendador_citas"
engine = create_engine(uri, connect_args={"client_encoding": "utf8"})

with engine.connect() as conn:
    print("✔ Conexión exitosa a:", conn.engine.url)



