# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from config import Config
from models import db, Perfil, Usuario
from flask_migrate import Migrate
import threading, time
from datetime import datetime, timedelta

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get('SECRET_KEY', 'cambia_esto_por_una_clave_segura')

db.init_app(app)
migrate = Migrate(app, db)

# --- Variables GLOBALES de control del bot ---
bot_thread     = None
stop_event     = None
interval       = (5, 10)
allowed_months = [5, 6]
max_workers    = 2
last_attempt   = None
refresh_seconds = 60
app.config['REFRESH_INTERVAL'] = refresh_seconds
# --------------------------------------------

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

def run_loop(stop_event):
    global last_attempt
    from automation import get_pending_profiles, schedule_for
    while not stop_event.is_set():
        last_attempt = datetime.now()
        perfiles = get_pending_profiles()
        if perfiles:
            print(f"\U0001f500 Lanzando hasta {max_workers} navegadores en paralelo...")
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=max_workers) as execr:
                futures = {execr.submit(schedule_for, p): p for p in perfiles}
                for fut in as_completed(futures):
                    perfil = futures[fut]
                    try:
                        fut.result()
                    except Exception:
                        print(f"\u274c Error inesperado en {perfil.correo}")
        else:
            print("ℹ️ No hay perfiles pendientes.")
        total_secs = interval[0] * 60 + interval[1]
        for _ in range(total_secs):
            if stop_event.is_set():
                break
            time.sleep(1)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = request.form['username']; p = request.form['password']
        user = Usuario.query.filter_by(username=u, password=p).first()
        if user:
            session['user'] = u
            return redirect(url_for('index'))
        flash('Credenciales invalidas', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u = request.form['username']; p = request.form['password']
        if Usuario.query.filter_by(username=u).first():
            flash('El usuario ya existe','warning')
        else:
            nuevo = Usuario(username=u, password=p)
            db.session.add(nuevo); db.session.commit()
            flash('Usuario registrado exitosamente','success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    perfiles = Perfil.query.all()
    return render_template('index.html', perfiles=perfiles)

@app.route('/agregar', methods=['GET','POST'])
def agregar():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method=='POST':
        nuevo = Perfil(
            nombre=request.form['nombre'],
            correo=request.form['correo'],
            usuario_portal=request.form['usuario_portal'],
            contrasena_portal=request.form['contrasena'],
            schedule_code=request.form.get('schedule_code')
        )
        db.session.add(nuevo); db.session.commit()
        return redirect(url_for('index'))
    return render_template('agregar_usuario.html')

@app.route('/editar/<int:id>', methods=['GET','POST'])
def editar(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    perfil = Perfil.query.get_or_404(id)
    if request.method=='POST':
        perfil.nombre            = request.form['nombre']
        perfil.correo            = request.form['correo']
        perfil.usuario_portal    = request.form['usuario_portal']
        perfil.contrasena_portal = request.form['contrasena']
        perfil.schedule_code     = request.form.get('schedule_code')
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('editar_usuario.html', perfil=perfil)

@app.route('/eliminar/<int:id>')
def eliminar(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    perfil = Perfil.query.get_or_404(id)
    db.session.delete(perfil); db.session.commit()
    return redirect(url_for('index'))

@app.route('/control')
def control_panel():
    if 'user' not in session:
        return redirect(url_for('login'))
    now = datetime.now()
    total_secs = interval[0] * 60 + interval[1]
    next_try = (last_attempt + timedelta(seconds=total_secs)) if last_attempt else (now + timedelta(seconds=total_secs))
    return render_template('control.html',
                           interval_min=interval[0],
                           interval_sec=interval[1],
                           allowed_months=allowed_months,
                           max_workers=max_workers,
                           bot_status=bot_thread.is_alive() if bot_thread else False,
                           current_time=now.strftime('%H:%M:%S'),
                           next_attempt=next_try.strftime('%H:%M:%S'),
                           refresh_seconds=refresh_seconds)

@app.route('/control_data')
def control_data():
    now = datetime.now()
    total_secs = interval[0] * 60 + interval[1]
    next_try = (last_attempt + timedelta(seconds=total_secs)) if last_attempt else (now + timedelta(seconds=total_secs))
    return jsonify({
        'current_time': now.strftime('%H:%M:%S'),
        'next_attempt': next_try.strftime('%H:%M:%S')
    })

@app.route('/config_interval', methods=['POST'])
def config_interval():
    global interval
    data = request.get_json() or {}
    m = int(data.get('minutes', interval[0]))
    s = int(data.get('seconds', interval[1]))
    interval = (m, s)
    return f"Intervalo ajustado a {m} min y {s} seg."

@app.route('/config_range', methods=['POST'])
def config_range():
    global allowed_months
    data = request.get_json() or {}
    start = int(data.get('start_month', allowed_months[0]))
    end   = int(data.get('end_month', allowed_months[-1]))
    if 1 <= start <= end <= 12:
        allowed_months = list(range(start, end+1))
        return f"Rango de meses ajustado: {start} -> {end}"
    return "Rango invalido", 400

@app.route('/config_workers', methods=['POST'])
def config_workers():
    global max_workers
    data = request.get_json() or {}
    w = int(data.get('workers', max_workers))
    max_workers = max(1, w)
    return f"Navegadores simultaneos ajustados a {max_workers}."

@app.route('/start_bot', methods=['POST'])
def start_bot():
    global bot_thread, stop_event
    if bot_thread and bot_thread.is_alive():
        return "El bot ya esta corriendo.", 400
    stop_event = threading.Event()
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

def create_tables():
    with app.app_context():
        db.create_all()

if __name__=='__main__':
    create_tables()
    app.run(debug=True)
