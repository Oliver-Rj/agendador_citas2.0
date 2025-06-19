# -*- coding: utf-8 -*-
import random
import datetime
import time
import traceback
import json
import urllib3
import requests
import threading
from http.client import RemoteDisconnected

from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from models import db, Perfil

CONSUL_ID = 138
ASC_ID = 139

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

def human_pause(a=0.4, b=1.2):
    time.sleep(random.uniform(a, b))

def init_driver(proxy=None):
    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    if proxy:
        opts.add_argument(f'--proxy-server={proxy}')
    return webdriver.Chrome(options=opts)

def fetch_times(session, schedule_code, cons_id, date_str, driver=None):
    url = f"https://ais.usvisa-info.com/es-do/niv/schedule/{schedule_code}/appointment_times/{cons_id}.json"
    params = {
        "date": date_str,
        "consulate_id": cons_id,
        "appointments[expedite]": "false"
    }

    try:
        response = session.get(url, params=params, timeout=6)
        if response.status_code == 404:
            print(f"❌ API devolvió 404 para {date_str}")
            raise ValueError("404 Not Found")
        response.raise_for_status()
        times = response.json().get("available_times", [])

        if times:
            print(f"✅ Horarios desde API para {date_str}: {times}")
            return times
        else:
            print(f"⚠️ API no devolvió horarios para {date_str}, usando Selenium...")
    except Exception as e:
        print(f"⚠️ Error en API para {date_str}: {e}")

    if driver:
        try:
            print(f"🔍 Fallback Selenium para {date_str}")
            driver.get(f"https://ais.usvisa-info.com/es-do/niv/schedule/{schedule_code}/appointment")
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
            ).click()

            for a in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
                if a.text == date_str.split('-')[2]:
                    a.click()
                    break

            human_pause()

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_time'))
            )

            select = Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time'))
            opciones = [o.text.strip() for o in select.options if o.text.strip()]
            print(f"✅ Horarios Selenium para {date_str}: {opciones}")
            return opciones
        except Exception as e:
            print(f"❌ Selenium falló en {date_str}: {e}")
    return []

def login_and_capture(profile, app):
    driver = init_driver()
    driver.get("https://ais.usvisa-info.com/es-do/niv/users/sign_in")
    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "user_email")))
    driver.find_element(By.ID, "user_email").send_keys(profile.correo)
    driver.find_element(By.ID, "user_password").send_keys(profile.contrasena_portal)
    try:
        driver.find_element(By.CSS_SELECTOR, "div.icheckbox.icheck-item").click()
    except:
        pass
    driver.find_element(By.NAME, "commit").click()
    WebDriverWait(driver, 12).until(EC.url_contains("/niv"))
    print("✔️ Login OK — URL actual:", driver.current_url)

    csrf_token = driver.execute_script(
        "return document.querySelector('meta[name=\\\"csrf-token\\\"]').content"
    )

    session = requests.Session()
    for c in driver.get_cookies():
        session.cookies.set(c['name'], c['value'])
    ua = driver.execute_script("return navigator.userAgent;")
    session.headers.update({
        "User-Agent": ua,
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://ais.usvisa-info.com/es-do/niv"
    })

    return driver, session

def month_days(year, month):
    import calendar
    return calendar.monthrange(year, month)[1]

def schedule_for(profile, app, stop_event=None):
    try:
        driver, session = login_and_capture(profile, app)
        allowed_months = app.config.get('ALLOWED_MONTHS', [])
        allowed_year = app.config.get('ALLOWED_YEAR', datetime.datetime.now().year)

        print(f"🌀 Explorando {allowed_year} meses {allowed_months}")
        slot = None
        empty_cycles = 0

        while not slot:
            for m in sorted(allowed_months):
                days = list(range(1, month_days(allowed_year, m) + 1))
                for d in random.sample(days, len(days)):
                    if stop_event and stop_event.is_set():
                        return

                    fecha_c = f"{allowed_year}-{m:02d}-{d:02d}"
                    times_c = fetch_times(session, profile.schedule_code, CONSUL_ID, fecha_c, None)
                    if not times_c:
                        print(f"⚠️ No horarios API {fecha_c}, usando Selenium")
                        times_c = fetch_times(session, profile.schedule_code, CONSUL_ID, fecha_c, driver)

                    human_pause(0.3, 0.6)
                    if not times_c:
                        print(f"🔍 {fecha_c} → 0 cons (sin buscar ASC)")
                        continue

                    for offset in range(1, 8):
                        fecha_a = (datetime.datetime.strptime(fecha_c, "%Y-%m-%d") + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
                        times_a = fetch_times(session, profile.schedule_code, ASC_ID, fecha_a, None)
                        if not times_a:
                            print(f"⚠️ No horarios ASC API {fecha_a}, usando Selenium")
                            times_a = fetch_times(session, profile.schedule_code, ASC_ID, fecha_a, driver)

                        if times_a:
                            slot = (fecha_c, times_c[0], fecha_a, times_a[0])
                            print(f"🎯 Slot → CONSUL: {fecha_c} {times_c[0]} | ASC: {fecha_a} {times_a[0]}")
                            break
                    if slot: break
                if slot: break

            if not slot:
                empty_cycles += 1
                if empty_cycles % 5 == 0:
                    print("🔄 Re-login")
                    driver.quit()
                    driver, session = login_and_capture(profile, app)
                human_pause(2, 3)

        fecha_c, h_cons, fecha_a, h_asc = slot
        driver.get(f"https://ais.usvisa-info.com/es-do/niv/schedule/{profile.schedule_code}/appointment")

        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
        ).click()
        for a in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
            if a.text == fecha_c.split('-')[2]:
                a.click()
                break
        human_pause()
        Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time')).select_by_visible_text(h_cons)

        driver.find_element(By.ID, 'appointments_asc_appointment_date').click()
        for a in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
            if a.text == fecha_a.split('-')[2]:
                a.click()
                break
        human_pause()
        Select(driver.find_element(By.ID, 'appointments_asc_appointment_time')).select_by_visible_text(h_asc)

        WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.ID, 'appointments_submit'))
        ).click()

        WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'button') and contains(@class, 'alert') and text()='Confirmar']"))
        ).click()

        WebDriverWait(driver, 8).until(EC.url_contains('/confirmation'))
        conf = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '.confirmation-number'))
        ).text

        print("✅ Confirmación obtenida:", conf)
        with app.app_context():
            p = Perfil.query.get(profile.id)
            p.estado = 'reagendado'
            p.cita_confirmada = True
            p.id_usuario_cita = conf
            db.session.commit()
        driver.quit()

    except Exception as e:
        print("❌ Error schedule_for:", e)
        traceback.print_exc()
        with app.app_context():
            p = Perfil.query.get(profile.id)
            p.estado = 'pendiente'
            db.session.commit()

def get_pending_profiles(app):
    with app.app_context():
        return Perfil.query.filter_by(estado='pendiente').all()

def run_multiple(app, max_profiles=5):
    profiles = get_pending_profiles(app)[:max_profiles]
    threads = []
    for profile in profiles:
        t = threading.Thread(target=schedule_for, args=(profile, app))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

def run_looped_scheduler(app, interval_min=5, interval_sec=10, stop_event=None, max_profiles=5):
    from datetime import datetime
    from time import sleep

    while not (stop_event and stop_event.is_set()):
        print(f"⏱️ Iniciando ciclo de búsqueda {datetime.now().strftime('%H:%M:%S')}")
        run_multiple(app, max_profiles=max_profiles)
        total_sleep = interval_min * 60 + interval_sec
        for _ in range(total_sleep):
            if stop_event and stop_event.is_set():
                print("🛑 Stop event detectado. Terminando loop.")
                return
            sleep(1)

__all__ = ['get_pending_profiles', 'schedule_for', 'run_multiple', 'run_looped_scheduler']
