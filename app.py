# -*- coding: utf-8 -*-
import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from config import Config
from models import db, Perfil, Usuario
from flask_migrate import Migrate
import threading, time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get('SECRET_KEY', 'cambia_esto_por_una_clave_segura')

db.init_app(app)
migrate = Migrate(app, db)

# --- Variables GLOBALES de control del bot ---
bot_thread     = None
stop_event     = None
interval       = (5, 10)
max_workers    = 2
last_attempt   = None
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

# --------- RUTAS DEL PANEL Y AUTENTICACIÓN ------------

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
        if not username or not password:
            flash("Por favor ingresa usuario y contraseña.", "danger")
            return render_template('login.html')
        user = Usuario.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            flash("Bienvenido", "success")
            return redirect(url_for('index'))
        else:
            flash("Credenciales incorrectas", "danger")
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
        user = Usuario(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash("Usuario registrado. Ahora inicia sesión.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

# -------------- CRUD DE USUARIOS/PERFILES --------------

@app.route('/agregar', methods=['GET', 'POST'])
def agregar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form.get('username')
        contrasena_portal = request.form.get('contrasena_portal')
        schedule_code = request.form.get('schedule_code')
        perfil = Perfil(correo=username, contrasena_portal=contrasena_portal, schedule_code=schedule_code, estado='pendiente')
        db.session.add(perfil)
        db.session.commit()
        flash("Perfil agregado exitosamente.", "success")
        return redirect(url_for('index'))
    return render_template('agregar_usuario.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    perfil = Perfil.query.get_or_404(id)
    if request.method == 'POST':
        perfil.correo = request.form.get('username')
        perfil.contrasena_portal = request.form.get('contrasena_portal')
        perfil.schedule_code = request.form.get('schedule_code')
        db.session.commit()
        flash("Perfil actualizado.", "success")
        return redirect(url_for('index'))
    return render_template('editar_usuario.html', perfil=perfil)

@app.route('/eliminar/<int:id>')
def eliminar(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    perfil = Perfil.query.get_or_404(id)
    db.session.delete(perfil)
    db.session.commit()
    flash("Perfil eliminado.", "success")
    return redirect(url_for('index'))

# ------------- PANEL DE CONTROL DEL BOT -------------

@app.route('/control_panel')
def control_panel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Lee de archivo, si existe
    try:
        with open("allowed_months.json", "r") as f:
            data_file = json.load(f)
        allowed_months = data_file.get('allowed_months', [])
        allowed_year = data_file.get('allowed_year', datetime.now().year)
    except Exception:
        allowed_months = []
        allowed_year = datetime.now().year
    return render_template(
        'control.html',
        bot_status=(bot_thread is not None and bot_thread.is_alive()),
        interval_min=interval[0],
        interval_sec=interval[1],
        refresh_seconds=refresh_seconds,
        max_workers=max_workers,
        allowed_months=allowed_months,
        allowed_year=allowed_year,
        current_time=datetime.now().strftime('%H:%M:%S'),
        next_attempt=(datetime.now() + timedelta(minutes=interval[0], seconds=interval[1])).strftime('%H:%M:%S')
    )

# --------- NUEVA RUTA: /control (redirige al panel) ---------
@app.route('/control')
def control():
    return redirect(url_for('control_panel'))

# ------------- API CONFIG (AJUSTE DE MESES, AÑO, ETC) -------------

@app.route('/config_range', methods=['POST'])
def config_range():
    data = request.get_json() or {}
    start = int(data.get('start_month', 1))
    end   = int(data.get('end_month', 12))
    if 1 <= start <= end <= 12:
        meses = list(range(start, end + 1))
        app.config['ALLOWED_MONTHS'] = meses
        # Guardar en archivo
        try:
            with open("allowed_months.json", "r") as f:
                data_file = json.load(f)
        except Exception:
            data_file = {}
        data_file["allowed_months"] = meses
        data_file["allowed_year"] = app.config.get('ALLOWED_YEAR', datetime.now().year)
        with open("allowed_months.json", "w") as f:
            json.dump(data_file, f)
        print("[CONFIG] ALLOWED_MONTHS ahora es:", meses)
        return f"Rango de meses ajustado: {start} -> {end}"
    return "Rango invalido", 400

@app.route('/config_range', methods=['GET'])
def get_config_range():
    try:
        with open("allowed_months.json", "r") as f:
            data_file = json.load(f)
        allowed_months = data_file.get('allowed_months', [])
        allowed_year = data_file.get('allowed_year', datetime.now().year)
    except Exception:
        allowed_months = []
        allowed_year = datetime.now().year
    return jsonify({
        'allowed_months': allowed_months,
        'allowed_year': allowed_year
    })

@app.route('/config_year', methods=['POST'])
def config_year():
    data = request.get_json()
    year = int(data.get('year', datetime.now().year))
    app.config['ALLOWED_YEAR'] = year
    # Actualiza archivo de meses si existe
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
    print("[CONFIG] ALLOWED_YEAR ahora es:", year)
    return f"Año permitido actualizado a {year}"

@app.route('/config_interval', methods=['POST'])
def config_interval():
    global interval
    data = request.get_json() or {}
    m = int(data.get('minutes', interval[0]))
    s = int(data.get('seconds', interval[1]))
    interval = (m, s)
    return f"Intervalo ajustado a {m} min y {s} seg."

@app.route('/config_workers', methods=['POST'])
def config_workers():
    global max_workers
    data = request.get_json() or {}
    w = int(data.get('workers', max_workers))
    max_workers = max(1, w)
    return f"Navegadores simultaneos ajustados a {max_workers}."

@app.route('/config_refresh', methods=['POST'])
def config_refresh():
    global refresh_seconds
    data = request.get_json() or {}
    try:
        seconds = int(data.get('refresh_seconds', 60))
        refresh_seconds = max(5, seconds)
        app.config['REFRESH_INTERVAL'] = refresh_seconds
        return f"Tiempo de refresco actualizado a {refresh_seconds}s"
    except Exception as e:
        return f"Error al actualizar: {e}", 400

# ------------- CONTROL DATA PARA UI EN TIEMPO REAL -------------

@app.route('/control_data')
def control_data():
    try:
        with open("allowed_months.json", "r") as f:
            data_file = json.load(f)
        allowed_months = data_file.get('allowed_months', [])
        allowed_year = data_file.get('allowed_year', datetime.now().year)
    except Exception:
        allowed_months = []
        allowed_year = datetime.now().year
    return jsonify({
        'current_time': datetime.now().strftime('%H:%M:%S'),
        'next_attempt': (datetime.now() + timedelta(minutes=interval[0], seconds=interval[1])).strftime('%H:%M:%S'),
        'interval_min': interval[0],
        'interval_sec': interval[1],
        'refresh_seconds': refresh_seconds,
        'max_workers': max_workers,
        'allowed_months': allowed_months,
        'allowed_year': allowed_year
    })

# ------------- BOT START/STOP -------------

@app.route('/start_bot', methods=['POST'])
def start_bot():
    global bot_thread, stop_event
    if bot_thread and bot_thread.is_alive():
        return "El bot ya esta corriendo.", 400
    stop_event = threading.Event()
    from automation import schedule_for, get_pending_profiles
    def run_loop(stop_event):
        global last_attempt
        while not stop_event.is_set():
            last_attempt = datetime.now()
            perfiles = get_pending_profiles()
            if perfiles:
                print(f"🔁 Lanzando hasta {max_workers} navegadores en paralelo...")
                with ThreadPoolExecutor(max_workers=max_workers) as execr:
                    futures = {execr.submit(schedule_for, p): p for p in perfiles}
                    for fut in as_completed(futures):
                        perfil = futures[fut]
                        try:
                            fut.result()
                        except Exception:
                            print(f"❌ Error inesperado en {perfil.correo}")
            else:
                print("ℹ️ No hay perfiles pendientes.")
            total_secs = interval[0] * 60 + interval[1]
            for _ in range(total_secs):
                if stop_event.is_set():
                    break
                time.sleep(1)
    bot_thread = threading.Thread(target=run_loop, args=(stop_event,))
    bot_thread.start()
    return "Bot iniciado."

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    global stop_event
    if stop_event:
        stop_event.set()
        return "Bot detenido."
    return "El bot no estaba en ejecucion.", 400

# --------- ENDPOINT DE DIAGNÓSTICO para estados de meses y año -----
@app.route('/ver_estado')
def ver_estado():
    try:
        with open("allowed_months.json", "r") as f:
            data_file = json.load(f)
        allowed_months = data_file.get('allowed_months', [])
        allowed_year = data_file.get('allowed_year', 'NO YEAR')
    except Exception:
        allowed_months = []
        allowed_year = 'NO YEAR'
    return jsonify({
        'allowed_months': allowed_months,
        'allowed_year': allowed_year
    })

# ---------------------------

if __name__ == '__main__':
    def create_tables():
        with app.app_context():
            db.create_all()
    create_tables()
    app.run(debug=False, host="0.0.0.0", port=5000)
