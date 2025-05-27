# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config
from models import db, Perfil, Usuario
import threading, time

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get('SECRET_KEY', 'cambia_esto_por_una_clave_segura')

db.init_app(app)

# --- Variables GLOBALES de control del bot ---
bot_thread     = None
stop_event     = None
interval       = (5, 10)           # (minutos, segundos)
allowed_months = [5, 6]            # rango de meses por defecto (Mayo–Junio)
max_workers    = 2                 # instancias de Chrome en paralelo
# --------------------------------------------

def run_loop(stop_event):
    """Bucle que reprograma perfiles cada intervalo."""
    from automation import get_pending_profiles, schedule_for
    while not stop_event.is_set():
        perfiles = get_pending_profiles()
        if perfiles:
            print(f"🔀 Lanzando hasta {max_workers} navegadores en paralelo...")
            from concurrent.futures import ThreadPoolExecutor, as_completed
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

# --- RUTAS DE AUTENTICACION & CRUD ---
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
            contrasena_portal=request.form['contrasena']
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
# --------------------------------------------

# --- PANEL DE CONTROL DEL BOT ---
@app.route('/control')
def control_panel():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('control.html',
                           interval_min=interval[0],
                           interval_sec=interval[1],
                           allowed_months=allowed_months,
                           max_workers=max_workers)

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
# --------------------------------------------

def create_tables():
    """Crea las tablas si no existen."""
    with app.app_context():
        db.create_all()

if __name__=='__main__':
    create_tables()
    app.run(debug=True)
