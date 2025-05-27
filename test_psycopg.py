# -*- coding: utf-8 -*-
import psycopg2

conn = psycopg2.connect(
    dbname="agendador_citas",
    user="postgres",
    password="12345",
    host="localhost",
    port=5432,
    client_encoding="utf8"
)
print("✔ psycopg2 conectado:", conn.dsn)
conn.close()
