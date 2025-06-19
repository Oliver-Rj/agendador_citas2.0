# -*- coding: utf-8 -*-
import os
import json
import threading
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from config import Config
from models import db, Perfil, Usuario
from flask_migrate import Migrate

from automation import run_looped_scheduler

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get('SECRET_KEY', 'cambia_esto_por_una_clave_segura')

db.init_app(app)
migrate = Migrate(app, db)

# --- Variables GLOBALES de control del bot ---
bot_thread = None
stop_event = None
interval = (5, 10)
max_workers = 2
last_attempt = None
refresh_seconds = 60
app.config['REFRESH_INTERVAL'] = refresh_seconds

# Intenta cargar meses/año desde archivo (persistencia real)
try:
    with open("allowed_months.json", "r") as f:
        data_file = json.load(f)
    app.config['ALLOWED_MONTHS'] = data_file.get('allowed_months', [])
    app.config['ALLOWED_YEAR'] = data_file.get('allowed_year', datetime.now().year)
except Exception:
    app.config['ALLOWED_MONTHS'] = []
    app.config['ALLOWED_YEAR'] = datetime.now().year

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    perfiles = Perfil.query.all()
    return render_template('index.html', perfiles=perfiles)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash("Credenciales inválidas", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('register.html')
        user = Usuario(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash("Usuario registrado correctamente. Inicia sesión.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/control_panel')
def control_panel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('control.html')

@app.route('/agregar', methods=['GET', 'POST'])
def agregar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        usuario_portal = request.form.get('usuario_portal')
        contrasena = request.form.get('contrasena')
        schedule_code = request.form.get('schedule_code')

        if not all([nombre, correo, usuario_portal, contrasena, schedule_code]):
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('agregar_usuario.html')

        perfil = Perfil(
            nombre=nombre,
            correo=correo,
            usuario_portal=usuario_portal,
            contrasena_portal=contrasena,
            schedule_code=schedule_code,
            estado='pendiente'
        )
        db.session.add(perfil)
        db.session.commit()
        flash("Perfil agregado exitosamente.", "success")
        return redirect(url_for('control_panel'))
    return render_template('agregar_usuario.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    perfil = Perfil.query.get_or_404(id)
    if request.method == 'POST':
        perfil.correo = request.form.get('correo')
        perfil.contrasena_portal = request.form.get('contrasena')
        perfil.schedule_code = request.form.get('schedule_code')
        db.session.commit()
        flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for('control_panel'))
    return render_template('editar_usuario.html', perfil=perfil)

@app.route('/eliminar/<int:id>', methods=['GET'])
def eliminar(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    perfil = Perfil.query.get_or_404(id)
    db.session.delete(perfil)
    db.session.commit()
    flash("Perfil eliminado correctamente.", "success")
    return redirect(url_for('index'))

# CONTROL BOT
@app.route('/start_bot', methods=['GET', 'POST'])
def start_bot():
    global bot_thread, stop_event
    if bot_thread and bot_thread.is_alive():
        return "El bot ya está corriendo.", 400
    try:
        stop_event = threading.Event()

        def run():
            run_looped_scheduler(app, interval[0], interval[1], stop_event, max_workers)

        bot_thread = threading.Thread(target=run)
        bot_thread.start()
        return "Bot iniciado."
    except Exception as e:
        app.logger.error("Error al iniciar bot", exc_info=True)
        return f"Ocurrió un error al iniciar el bot: {e}", 500

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    global stop_event
    if stop_event:
        stop_event.set()
        return "Bot detenido."
    return "El bot no estaba en ejecución.", 400

@app.route('/control_data')
def control_data():
    return jsonify({
        'current_time': datetime.now().strftime('%H:%M:%S'),
        'next_attempt': (datetime.now() + timedelta(minutes=interval[0], seconds=interval[1])).strftime('%H:%M:%S'),
        'interval_min': interval[0],
        'interval_sec': interval[1],
        'refresh_seconds': refresh_seconds,
        'max_workers': max_workers,
        'allowed_months': app.config.get('ALLOWED_MONTHS', []),
        'allowed_year': app.config.get('ALLOWED_YEAR', datetime.now().year)
    })

@app.route('/perfiles_status')
def perfiles_status():
    perfiles = Perfil.query.all()
    data = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'correo': p.correo,
            'estado': p.estado,
            'cita_confirmada': p.cita_confirmada,
            'usuario_cita': p.id_usuario_cita
        }
        for p in perfiles
    ]
    return jsonify(data)

@app.route('/config_interval', methods=['POST'])
def config_interval():
    global interval
    data = request.get_json() or {}
    m = int(data.get('minutes', interval[0]))
    s = int(data.get('seconds', interval[1]))
    interval = (m, s)
    return f"Intervalo ajustado a {m} min y {s} seg."

@app.route('/config_refresh', methods=['POST'])
def config_refresh():
    global refresh_seconds
    data = request.get_json() or {}
    seconds = int(data.get('refresh_seconds', refresh_seconds))
    refresh_seconds = max(5, seconds)
    app.config['REFRESH_INTERVAL'] = refresh_seconds
    return f"Tiempo de refresco actualizado a {refresh_seconds}s"

@app.route('/config_range', methods=['POST'])
def config_range():
    data = request.get_json() or {}
    start = int(data.get('start_month', 1))
    end = int(data.get('end_month', 12))
    if 1 <= start <= end <= 12:
        meses = list(range(start, end + 1))
        app.config['ALLOWED_MONTHS'] = meses
        try:
            with open("allowed_months.json", "r") as f:
                data_file = json.load(f)
        except Exception:
            data_file = {}
        data_file["allowed_months"] = meses
        data_file["allowed_year"] = app.config.get('ALLOWED_YEAR', datetime.now().year)
        with open("allowed_months.json", "w") as f:
            json.dump(data_file, f)
        return f"Rango de meses ajustado: {start} -> {end}"
    return "Rango inválido", 400

@app.route('/config_year', methods=['POST'])
def config_year():
    data = request.get_json() or {}
    year = int(data.get('year', datetime.now().year))
    app.config['ALLOWED_YEAR'] = year
    try:
        with open("allowed_months.json", "r") as f:
            data_file = json.load(f)
    except Exception:
        data_file = {}
    data_file['allowed_year'] = year
    if 'allowed_months' not in data_file:
        data_file['allowed_months'] = app.config.get('ALLOWED_MONTHS', [])
    with open("allowed_months.json", "w") as f:
        json.dump(data_file, f)
    return f"Año permitido actualizado a {year}"

@app.route('/config_workers', methods=['POST'])
def config_workers():
    global max_workers
    data = request.get_json() or {}
    w = int(data.get('workers', max_workers))
    max_workers = max(1, w)
    return f"Navegadores simultáneos ajustados a {max_workers}."

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
