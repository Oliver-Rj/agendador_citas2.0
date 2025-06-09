# -*- coding: utf-8 -*-
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import random
import datetime
import time
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import db, Perfil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from app import app, stop_event

def human_pause(min_s=0.15, max_s=0.3):
    # Pausa corta y aleatoria para simular humano, pero rápido
    time.sleep(random.uniform(min_s, max_s))

def init_driver():
    print("🚗 Iniciando navegador...")
    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    opts.page_load_strategy = 'eager'
    # Puedes agregar más opciones si quieres hacerlo más "humano"
    return webdriver.Chrome(options=opts)

def get_pending_profiles():
    with app.app_context():
        return Perfil.query.filter_by(estado='pendiente').all()

def days_in_month(year, month):
    import calendar
    return calendar.monthrange(year, month)[1]

def fetch_horas_disponibles(session, profile, year, month, day):
    try:
        url_base = "https://ais.usvisa-info.com/es-do/niv/schedule"
        schedule_code = str(profile.schedule_code).strip()
        url_cita = f"{url_base}/{schedule_code}/appointment_times/139.json"
        fecha_str = f"{year}-{month:02d}-{day:02d}"
        params = {
            "date": fecha_str,
            "consulate_id": 139
        }
        r = session.get(url_cita, params=params, timeout=6)
        if r.status_code == 200:
            data = r.json()
            return data.get("available_times", [])
        return []
    except Exception as e:
        print(f"❌ Error consultando {fecha_str}: {e}")
        return []

def wait_for_valid_date_and_time(driver, profile):
    print("🔎 Buscando fecha y hora disponibles (modo turbo)...")
    allowed_months = app.config.get('ALLOWED_MONTHS', [])
    allowed_year = app.config.get('ALLOWED_YEAR', datetime.datetime.now().year)
    session = requests.Session()
    # Copia cookies actuales del navegador
    for c in driver.get_cookies():
        session.cookies.set(c['name'], c['value'])
    session.headers.update({'User-Agent': driver.execute_script("return navigator.userAgent;")})

    while True:
        for mes in allowed_months:
            total_dias = days_in_month(allowed_year, mes)
            dias_disponibles = list(range(1, total_dias + 1))
            random.shuffle(dias_disponibles)  # Orden aleatorio
            for dia in dias_disponibles:
                if stop_event and stop_event.is_set():
                    print("🛑 Proceso detenido por stop_event")
                    return False
                horas = fetch_horas_disponibles(session, profile, allowed_year, mes, dia)
                print(f"🗓️ {allowed_year}-{mes:02d}-{dia:02d} -> {len(horas)} horas disponibles")
                if horas:
                    # Selecciona ese día y la hora disponible en la UI
                    try:
                        # Click en fecha
                        driver.find_element(By.ID, 'appointments_consulate_appointment_date').click()
                        human_pause()
                        dias_ui = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
                        found_day = False
                        for d_elem in dias_ui:
                            if d_elem.text == str(dia):
                                d_elem.click()
                                found_day = True
                                break
                        if not found_day:
                            print(f"❌ No se encontró el día {dia} en el calendario UI, refrescando calendario...")
                            driver.refresh()
                            human_pause()
                            continue
                        human_pause()

                        # Esperar a que aparezca el combo de hora y seleccionar
                        time_elem = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_time'))
                        )
                        sel = Select(time_elem)
                        for o in sel.options:
                            if o.get_attribute('value'):
                                sel.select_by_value(o.get_attribute('value'))
                                print(f"✅ Seleccionando {allowed_year}-{mes:02d}-{dia:02d} y hora {o.text}")
                                return True
                    except Exception as e:
                        print(f"⚠️ Error interactuando con UI Selenium: {e}")
                        continue
        print("🔄 No hay fechas. Reintentando ciclo completo en 4 seg...")
        time.sleep(4)

def schedule_for(profile, stop_signal=None):
    driver = init_driver()
    try:
        print(f"🛫 Procesando perfil: {profile.correo}")
        driver.get('https://ais.usvisa-info.com/es-do/niv/users/sign_in')
        WebDriverWait(driver, 4).until(EC.visibility_of_element_located((By.ID, 'user_email')))
        driver.find_element(By.ID, 'user_email').send_keys(profile.correo)
        driver.find_element(By.ID, 'user_password').send_keys(profile.contrasena_portal)
        driver.find_element(By.CSS_SELECTOR, 'div.icheckbox.icheck-item').click()
        driver.find_element(By.NAME, 'commit').click()

        # Depuración: Verifica a dónde navega después de login
        WebDriverWait(driver, 8).until(EC.url_contains('/niv'))
        print('✔ Login OK')
        print("URL después de login:", driver.current_url)

        schedule_code = str(profile.schedule_code).strip()
        if not schedule_code:
            print("⚠️ Schedule code no válido o vacío.")
            with app.app_context():
                profile.estado = 'fallo'
                db.session.commit()
            driver.quit()
            return

        target_url = f"https://ais.usvisa-info.com/es-do/niv/schedule/{schedule_code}/appointment"
        print(f"🔗 Navegando a: {target_url}")
        driver.get(target_url)
        time.sleep(2)
        print("URL tras ir a target_url:", driver.current_url)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_date'))
        )

        if wait_for_valid_date_and_time(driver, profile):
            # Selecciona ASC y hora de ASC después de la fecha/hora consulado
            try:
                asc = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_facility_id'))
                )
                Select(asc).select_by_index(0)
                asc_time_elem = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_time'))
                )
                asc_sel = Select(asc_time_elem)
                for o in asc_sel.options:
                    if o.get_attribute('value'):
                        asc_sel.select_by_value(o.get_attribute('value'))
                        break

                btn_reprogramar = WebDriverWait(driver, 15).until(
                    lambda d: d.find_element(By.ID, "appointments_submit")
                )
                WebDriverWait(driver, 15).until(lambda d: btn_reprogramar.is_enabled())
                driver.execute_script("arguments[0].scrollIntoView(true);", btn_reprogramar)
                btn_reprogramar.click()

                WebDriverWait(driver, 8).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-content"))
                )
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Confirmar']"))
                ).click()

                WebDriverWait(driver, 8).until(EC.url_contains('/confirmation'))
                conf = WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, '.confirmation-number'))
                ).text
                print(f"🎉 Reagendamiento confirmado. Código: {conf}")
                with app.app_context():
                    profile.estado = 'reagendado'
                    profile.cita_confirmada = True
                    profile.id_usuario_cita = conf
                    db.session.commit()
            except Exception as e:
                print(f"❌ Error seleccionando ASC/hora: {e}")
                traceback.print_exc()
        driver.quit()
    except Exception as e:
        print(f"❌ Error fatal en perfil {profile.correo}: {e}")
        with app.app_context():
            profile.estado = 'fallo'
            db.session.commit()
        traceback.print_exc()
        driver.quit()

__all__ = ['get_pending_profiles', 'wait_for_valid_date_and_time', 'schedule_for']
