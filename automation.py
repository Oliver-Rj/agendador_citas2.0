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
from selenium.common.exceptions import WebDriverException
from app import allowed_months, app

# --- Funciones para simular comportamiento humano ---
def human_pause(min_s=0.3, max_s=1.2):
    """Pausa aleatoria entre `min_s` y `max_s` segundos."""
    time.sleep(random.uniform(min_s, max_s))

def human_move(driver):
    """Mueve el ratón una pequeña distancia para simular navegación humana."""
    x = random.randint(-50, 50)
    y = random.randint(-50, 50)
    try:
        ActionChains(driver).move_by_offset(x, y).perform()
        human_pause(0.1, 0.4)
    except WebDriverException:
        pass
# ------------------------------------------------------

def get_pending_profiles():
    with app.app_context():
        return Perfil.query.filter_by(estado='pendiente').all()


def init_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    # opts.add_argument('--headless')
    return webdriver.Chrome(options=opts)


def schedule_for(profile):
    driver = init_driver()
    try:
        print(f"🛫 Procesando {profile.correo}")
        human_pause(0.5, 1.0)
        # 1) login con reintentos
        for i in range(3):
            try:
                human_move(driver)
                driver.get('https://ais.usvisa-info.com/es-do/niv/users/sign_in')
                WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.ID, 'user_email'))
                )
                break
            except Exception:
                if i == 2:
                    raise
                human_pause(1, 2)
        # credenciales
        driver.find_element(By.ID, 'user_email').send_keys(profile.correo)
        driver.find_element(By.ID, 'user_password').send_keys(profile.contrasena_portal)
        driver.find_element(By.CSS_SELECTOR, 'div.icheckbox.icheck-item').click()
        driver.find_element(By.NAME, 'commit').click()
        WebDriverWait(driver, 10).until(EC.url_contains('/niv'))
        print('✔ Login OK')
        human_pause(0.3, 0.6)
        # continuar si aparece
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Continuar']"))
            ).click()
            human_pause(0.3, 0.6)
        except:
            pass
        # ir a reprogramar
        link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(normalize-space(.),'Reprogramar cita')]") )
        )
        driver.execute_script('arguments[0].scrollIntoView();', link)
        link.click()
        WebDriverWait(driver, 10).until(EC.url_contains('/schedule'))
        human_pause(0.3, 0.6)
        # abrir selector de fecha consular
        driver.find_element(By.XPATH, "//*[normalize-space(text())='Reprogramar cita']").click()
        date_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
        )
        driver.execute_script('arguments[0].scrollIntoView();', date_input)
        date_input.click()
        human_pause(0.3, 0.6)
        # seleccionar consulado
        Select(WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_facility_id'))
        )).select_by_visible_text('Santo Domingo')
        human_pause(0.3, 0.6)
        # Paso 5: elegir fecha dentro del rango allowed_months (consular)
        found = False
        for month in allowed_months:
            human_move(driver)
            date_in = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
            )
            driver.execute_script('arguments[0].scrollIntoView();', date_in)
            date_in.click()
            human_pause(0.3, 0.6)
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CLASS_NAME, 'ui-datepicker-calendar'))
            )
            while True:
                hdr_m = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-month').text
                hdr_y = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-year').text
                curr = datetime.datetime.strptime(f"{hdr_m} {hdr_y}", "%B %Y").month
                if curr == month:
                    break
                driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-next').click()
                human_pause(0.2, 0.4)
            days = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
            if days:
                days[0].click()
                print(f"✔ Fecha consular seleccionada: {days[0].text}/{month}")
                human_pause(0.2, 0.6)
                found = True
                break
        if not found:
            print(f"⚠️ No hay fechas en meses {allowed_months} (consular)"); return
        # Paso 6: selección horaria consulado (reintentar hasta encontrar)
        human_move(driver)
        while True:
            try:
                # refrescar opciones de hora clickeando fecha
                date_input_c = driver.find_element(By.ID, 'appointments_consulate_appointment_date')
                date_input_c.click(); human_pause(0.3, 0.6)
                time_elem = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_time'))
                )
                sel = Select(time_elem)
                opts = [o for o in sel.options if o.get_attribute('value')]
                if opts:
                    sel.select_by_value(opts[0].get_attribute('value'))
                    print('✔ Hora consulado seleccionada')
                    break
                else:
                    print('⚠️ Sin horarios consulado disponibles, reintentando...')
                    human_pause(5, 10)
            except Exception as e:
                print(f"⚠️ Error al obtener hora consulado: {e}, reintentando...")
                human_pause(5, 10)
        # Paso 7: seleccionar ASC
        human_move(driver)
        asc = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_facility_id'))
        )
        Select(asc).select_by_visible_text('Santo Domingo ASC')
        print('✔ ASC location seleccionado')
        human_pause(0.3, 0.6)
        # Paso 8: elegir fecha CAS
        human_move(driver)
        found_cas = False
        for month in allowed_months:
            date2 = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_date'))
            )
            driver.execute_script('arguments[0].scrollIntoView();', date2)
            date2.click(); human_pause(0.3, 0.6)
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CLASS_NAME, 'ui-datepicker-calendar'))
            )
            while True:
                hdr_m = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-month').text
                hdr_y = driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-year').text
                curr = datetime.datetime.strptime(f"{hdr_m} {hdr_y}", "%B %Y").month
                if curr == month:
                    break
                driver.find_element(By.CSS_SELECTOR, '.ui-datepicker-next').click(); human_pause(0.2, 0.4)
            days2 = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
            if days2:
                days2[0].click(); print(f"✔ Fecha CAS seleccionada: {days2[0].text}/{month}"); human_pause(0.2,0.6)
                found_cas = True
                break
        if not found_cas:
            print(f"⚠️ No hay fechas en meses {allowed_months} (CAS)"); return
        # Paso 9: hora CAS
        human_move(driver)
        cas_sel = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_time'))
        )
        sel2 = Select(cas_sel)
        opts2 = [o for o in sel2.options if o.get_attribute('value')]
        if opts2:
            sel2.select_by_value(opts2[0].get_attribute('value'))
            print('✔ Hora CAS seleccionada')
        else:
            print('⚠️ Sin horarios CAS disponibles'); return
        # Paso 10: reprogramar y confirmar
        human_move(driver)
        # 1) Localiza el botón “Reprogramar” y espera a que se habilite
        btn_reprogramar = WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.ID, "appointments_submit")
        )
        # 2) Espera a que se habilite
        WebDriverWait(driver, 30).until(lambda d: btn_reprogramar.is_enabled())
        # 3) Llévalo al viewport
        driver.execute_script("arguments[0].scrollIntoView(true);", btn_reprogramar)
        # 4) Haz clic
        btn_reprogramar.click()

        # 5) Espera a que aparezca el modal
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-content"))
        )

        # 6) Localiza y clickea “Confirmar” usando su atributo data-disable-with-content
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Confirmar']"))
            ).click()
            human_pause(0.3, 0.6)
        except:
            pass

        # 7) Ahora sí, espera la página de confirmación y extrae el número
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
    except Exception as e:
        print(f"❌ Error {profile.correo}: {e}")
        traceback.print_exc()
        with app.app_context():
            profile.estado = 'fallo'
            db.session.commit()
    finally:
        driver.quit()
        print(f"🚪 Cerrado para {profile.correo}")


def main_loop():
    while True:
        perfiles = get_pending_profiles()
        if perfiles:
            with ThreadPoolExecutor(max_workers=max(1, len(perfiles), 2)) as exe:
                for p in perfiles:
                    exe.submit(schedule_for, p)
        else:
            print('ℹ️ Sin pendientes')
        time.sleep(5*60 + 10)

if __name__ == '__main__':
    main_loop()




