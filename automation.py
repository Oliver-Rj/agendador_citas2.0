# -*- coding: utf-8 -*-
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import random
import datetime
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import db, Perfil
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from app import allowed_months, app, stop_event

refresh_seconds = app.config.get('REFRESH_INTERVAL', 60)

def human_pause(min_s=0.3, max_s=1.2):
    time.sleep(random.uniform(min_s, max_s))

def human_move(driver):
    x = random.randint(-50, 50)
    y = random.randint(-50, 50)
    try:
        ActionChains(driver).move_by_offset(x, y).perform()
        human_pause(0.1, 0.4)
    except WebDriverException:
        pass

def conditional_sleep(duration):
    for _ in range(duration):
        if stop_event and stop_event.is_set():
            print("🛑 Detención detectada durante la espera. Cancelando...")
            return False
        time.sleep(1)
    return True

def get_pending_profiles():
    with app.app_context():
        return Perfil.query.filter_by(estado='pendiente').all()

def init_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    return webdriver.Chrome(options=opts)

def sanitize_schedule_code(code):
    return str(code).strip().replace(" ", "")

def schedule_for(profile):
    driver = init_driver()
    try:
        print(f"🛫 Procesando {profile.correo}")
        human_pause(0.5, 1.0)

        # ——— Login con reintentos (hasta 3) ———
        login_success = False
        for i in range(3):
            try:
                human_move(driver)
                driver.get('https://ais.usvisa-info.com/es-do/niv/users/sign_in')
                WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.ID, 'user_email'))
                )
                driver.find_element(By.ID, 'user_email').send_keys(profile.correo)
                driver.find_element(By.ID, 'user_password').send_keys(profile.contrasena_portal)
                driver.find_element(By.CSS_SELECTOR, 'div.icheckbox.icheck-item').click()
                driver.find_element(By.NAME, 'commit').click()
                WebDriverWait(driver, 10).until(EC.url_contains('/niv'))
                print('✔ Login OK')
                login_success = True
                break
            except WebDriverException:
                print("❌ Fallo en carga de login, reintentando…")
                human_pause(1, 2)
        if not login_success:
            print(f"❌ No se pudo hacer login para {profile.correo} tras 3 intentos.")
            with app.app_context():
                profile.estado = 'fallo'
                db.session.commit()
            driver.quit()
            print(f"🚪 Cerrado para {profile.correo} (fallo en login)")
            return

        schedule_code = sanitize_schedule_code(profile.schedule_code)
        if not schedule_code:
            print(f"❌ El perfil '{profile.correo}' no tiene código de agenda (schedule_code).")
            with app.app_context():
                profile.estado = 'fallo'
                db.session.commit()
            driver.quit()
            print(f"🚪 Cerrado para {profile.correo} (sin schedule code)")
            return

        terminado = False
        while not terminado:
            try:
                target_url = f"https://ais.usvisa-info.com/es-do/niv/schedule/{schedule_code}/appointment"
                driver.get(target_url)
                WebDriverWait(driver, 10).until(
                    EC.url_contains(f"/schedule/{schedule_code}/appointment")
                )
                print(f"✔ Redirigido a página de agendamiento: {schedule_code}")

                # Buscar fecha y hora
                human_move(driver)
                btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
                )
                driver.execute_script('arguments[0].scrollIntoView(true);', btn)
                btn.click()
                human_pause(0.3, 0.6)
                WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, 'ui-datepicker-calendar'))
                )

                found = False
                for month in allowed_months:
                    target_reached = False
                    while True:
                        hdr_m = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-month').text
                        hdr_y = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-year').text
                        year_val = int(hdr_y)
                        current_month = datetime.datetime.strptime(f"{hdr_m} {hdr_y}", "%B %Y").month
                        if year_val > datetime.datetime.now().year:
                            break
                        if year_val == datetime.datetime.now().year and current_month < month:
                            driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-next').click()
                            human_pause(0.2, 0.4)
                            continue
                        if year_val == datetime.datetime.now().year and current_month == month:
                            target_reached = True
                        break
                    if not target_reached:
                        continue
                    days2 = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
                    for day2 in days2:
                        day2.click()
                        human_pause(0.3, 0.6)
                        try:
                            time_elem2_check = WebDriverWait(driver, 2).until(
                                EC.presence_of_element_located((By.ID, 'appointments_asc_appointment_time'))
                            )
                            sel2_check = Select(time_elem2_check)
                            valid_times2 = [o for o in sel2_check.options if o.get_attribute('value')]
                            if valid_times2:
                                print(f"✔ Fecha CAS y hora disponible: {day2.text}/{month}")
                                found = True
                                break
                            else:
                                btn2 = driver.find_element(By.ID, 'appointments_asc_appointment_date')
                                driver.execute_script("arguments[0].click();", btn2)
                                human_pause(0.3, 0.6)
                                continue
                        except TimeoutException:
                            btn2 = driver.find_element(By.ID, 'appointments_asc_appointment_date')
                            driver.execute_script("arguments[0].click();", btn2)
                            human_pause(0.3, 0.6)
                            continue
                    if found:
                        break

                if found:
                    human_move(driver)
                    cas_sel = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_time'))
                    )
                    sel2 = Select(cas_sel)
                    opts2 = [o for o in sel2.options if o.get_attribute('value')]
                    if opts2:
                        sel2.select_by_value(opts2[0].get_attribute('value'))
                        print('✔ Hora CAS seleccionada')
                        # Hacer clic en “Reprogramar” y confirmar
                        human_move(driver)
                        btn_reprogramar = WebDriverWait(driver, 20).until(
                            lambda d: d.find_element(By.ID, "appointments_submit")
                        )
                        WebDriverWait(driver, 30).until(lambda d: btn_reprogramar.is_enabled())
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn_reprogramar)
                        btn_reprogramar.click()
                        WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-content"))
                        )
                        WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Confirmar']"))
                        ).click()
                        WebDriverWait(driver, 10).until(EC.url_contains('/confirmation'))
                        conf = WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, '.confirmation-number'))
                        ).text
                        print(f"✔ Confirmación final: {conf}")
                        with app.app_context():
                            profile.estado = 'reagendado'
                            profile.cita_confirmada = True
                            profile.id_usuario_cita = conf
                            db.session.commit()
                        print('🎉 Proceso completado')
                        terminado = True  # Solo aquí sale y cierra
                        break

                # Si no encontró, o si hubo error, simplemente repite el ciclo
                if stop_event and stop_event.is_set():
                    print("🛑 Detenido por señal de parada.")
                    terminado = True

            except (TimeoutException, WebDriverException) as e:
                print(f"⚠️ Error temporal en la página: {e}. Intentando de nuevo…")
                human_pause(2, 5)  # Espera y vuelve a intentar

            except Exception as e:
                # Cualquier error crítico SÍ cierra y marca como fallo
                print(f"❌ Error grave {profile.correo}: {e}")
                traceback.print_exc()
                with app.app_context():
                    profile.estado = 'fallo'
                    db.session.commit()
                driver.quit()
                print(f"🚪 Cerrado para {profile.correo} (por excepción grave)")
                return

        driver.quit()
        print(f"🚪 Cerrado para {profile.correo} (proceso terminado/stop)")

    except Exception as e:
        print(f"❌ Error fatal {profile.correo}: {e}")
        traceback.print_exc()
        with app.app_context():
            profile.estado = 'fallo'
            db.session.commit()
        driver.quit()
        print(f"🚪 Cerrado para {profile.correo} (por excepción fatal)")

def main_loop():
    while True:
        perfiles = get_pending_profiles()
        if perfiles:
            with ThreadPoolExecutor(max_workers=max(1, len(perfiles), 2)) as exe:
                for p in perfiles:
                    exe.submit(schedule_for, p)
        else:
            print('ℹ️ Sin pendientes')
        if not conditional_sleep(app.config.get('REFRESH_INTERVAL', 2)):
            break

if __name__ == '__main__':
    try:
        main_loop()
    except Exception as e:
        print(f"Error en el bucle principal: {e}")
        traceback.print_exc()
