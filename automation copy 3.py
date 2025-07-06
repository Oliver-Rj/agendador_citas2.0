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
#def human_pause(a=0.4, b=1.2):
def human_pause(a=0.4, b=1.2):
    time.sleep(random.uniform(a, b))

def init_driver(proxy=None):
    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    opts.add_argument("window-size=1200x600")
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
       # return []
        #    print(f"sesion {session} ")
        if response.status_code == 404:
            print(f"❌ API devolvió 404 para {date_str} {url}")
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

            continue_date_search_cycle = True
            while continue_date_search_cycle:

                #print(f"Valor de ciclo 1")
                
                #print(f"Valor de ciclo 2")
                for a in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):    

                    #print(f"🔍 El valor es: {a.text} {date_str.split('-')[2]}") 
                    #print(f"Valor de ciclo 3")
                    if int(a.text) == int(date_str.split('-')[2]):
                        print(f"Clik ejecutado en: {a.text}") 
                        #print(f"Valor de ciclo 4")
                        a.click()
                        continue_date_search_cycle = False
                        break
        
                if not continue_date_search_cycle:
                    break

                for a in driver.find_elements(By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > div > span.ui-datepicker-year'):
                   
                    if int(a.text) > int(date_str.split('-')[0]):
                        continue_date_search_cycle = False
                        break

                if not continue_date_search_cycle:
                    break

                WebDriverWait(driver, 10).until(
                 EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
                ).click()         
                #human_pause(3,5)
            #print(f"Valor de ciclo 5") 
            human_pause()
            #print(f"Valor de ciclo 6")  
            WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_time'))
            )
            #print(f"Valor de ciclo 7")
            select = Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time'))
           # print(f"Valor de ciclo 8") 
            opciones = [o.text.strip() for o in select.options if o.text.strip()]
          #  print(f"Valor de ciclo 9")
            print(f"✅ Horarios Selenium para {date_str}: {opciones}")
         #   print(f"Valor de ciclo 10")
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

       human_pause()

       WebDriverWait(driver, 10).until(
         EC.element_to_be_clickable((By.CSS_SELECTOR, '#main > div:nth-child(2) > div.mainContent > div:nth-child(1) > div > div > div:nth-child(1) > div.medium-6.columns.text-right > ul > li > a'))
       ).click()

       human_pause()

       print(f"🌀 Explorando {allowed_year} meses {allowed_months}")
       driver.get(f"https://ais.usvisa-info.com/es-do/niv/schedule/{profile.schedule_code}/appointment")
       #print(f"🌀 vALOR {driver} ")

       human_pause()
     

       continue_cycle_to_schedule_appointment = True

       date_consular_encontrada = False
       hora_consular_encontrada = False
       date_huella_encontrada = False 
       hora_huella_encontrada = False   

      
       quantity_list_consular_dates_found = 0
       quantity_list_huella_dates_found = 0    
       
       #print(f"Impresion 1")

       while continue_cycle_to_schedule_appointment:

           WebDriverWait(driver, 10).until(
              EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
           ).click()
           #print(f"Impresion 2")
           for i in range(0, quantity_list_consular_dates_found):
              WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
              ).click() 

           #print(f"Impresion 3")
           if driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
              quantity_list_consular_dates_found += 1

           #print(f"Impresion 4")
           cantidad_fecha_consular = 0
           cantidad_fecha_consular_lista = len(driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'))
           #dias_disponibles_lista = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
           #for fecha_consular in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
           for i in range(cantidad_fecha_consular_lista):

             
             cantidad_fecha_consular += 1

             if cantidad_fecha_consular > 1:
                WebDriverWait(driver, 10).until(
                  EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
                ).click()

             fecha_consular_lista = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')   
             #print(f"Fecha consular: {fecha_consular} - Cantidad: {cantidad_fecha_consular}")
             human_pause()
              
             fecha_consular_lista[i].click()  
             #print(f"Impresion 5")
             date_consular_encontrada = True
             hora_consular_encontrada = False
             date_huella_encontrada = False 
             hora_huella_encontrada = False
             human_pause()

             #print(f"Impresion 6")                                   
             WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_time'))
             )

             select_hora_consular = Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time'))

             opciones_hora_consular = [o.text.strip() for o in select_hora_consular.options if o.text.strip()]

             #print(f"Impresion 7")
             for hora_consular in opciones_hora_consular:

               #print(f"Impresion 8")
               Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time')).select_by_visible_text(hora_consular)
               hora_consular_encontrada = True
               date_huella_encontrada = False 
               hora_huella_encontrada = False
               human_pause()

               #print(f"Impresion 9")
               try:
                  WebDriverWait(driver, 10).until(
                     EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_date'))
                  ).click()
               except Exception as e:
                 print(f"❌ Error al obtener fecha ASC: {e}")
                 continue

               continue_cycle_to_schedule_appointment_2 = True
               quantity_list_huella_dates_found = 0     
               #print(f"Impresion 10")     
               while continue_cycle_to_schedule_appointment_2:  
                
                  #print(f"Impresion 11")
                  for i in range(0, quantity_list_huella_dates_found):
                     WebDriverWait(driver, 10).until(
                       EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
                     ).click() 

                  #print(f"Impresion 12")
                  if driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
                    quantity_list_huella_dates_found += 1 

                  #print(f"Impresion 13")
                  cantidad_fecha_huella = 0
                  cantidad_fecha_huella_lista = len(driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'))
                  #for fecha_huella in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
                  for i in range(cantidad_fecha_huella_lista):
                     cantidad_fecha_huella += 1
                     #print(f"Impresion 14")
                     if cantidad_fecha_huella > 1:
                        WebDriverWait(driver, 10).until(
                          EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
                        ).click()
                     #quantity_list_huella_dates_found += 1 
                     fecha_huella_lista = driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a')
                     fecha_huella_lista[i].click()  
                     date_huella_encontrada = True 
                     hora_huella_encontrada = False
                     human_pause()

                     #print(f"Impresion 15")
                     WebDriverWait(driver, 10).until(
                       EC.presence_of_element_located((By.ID, 'appointments_asc_appointment_time'))
                     )

                     #print(f"Impresion 16")
                     select_hora_huella = Select(driver.find_element(By.ID, 'appointments_asc_appointment_time'))
                    # print(f"Valor de ciclo 8") 
                     opciones_hora_huella = [o.text.strip() for o in select_hora_huella.options if o.text.strip()]

                     for hora_huella in opciones_hora_huella:
                       #print(f"Impresion 17") 
                       Select(driver.find_element(By.ID, 'appointments_asc_appointment_time')).select_by_visible_text(hora_huella)
                       hora_huella_encontrada = True
                       continue_cycle_to_schedule_appointment = False
                       continue_cycle_to_schedule_appointment_2 = False
                       human_pause()   
                       break
 
                     if date_consular_encontrada and hora_consular_encontrada and date_huella_encontrada and hora_huella_encontrada:
                       break 
                  if date_consular_encontrada and hora_consular_encontrada and date_huella_encontrada and hora_huella_encontrada:
                       break
                  #print(f"Impresion 18")
                  for a in driver.find_elements(By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-first > div > div > span.ui-datepicker-year'):
                   
                    if int(a.text) > int(allowed_year):
                      continue_cycle_to_schedule_appointment_2 = False
                      break 

                  #print(f"Impresion 19")
                  if not continue_cycle_to_schedule_appointment_2:
                    break

                  #print(f"Impresion 20")
                  if not date_huella_encontrada:
                    WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
                    ).click()  
                    continue  

               if date_consular_encontrada and hora_consular_encontrada and date_huella_encontrada and hora_huella_encontrada:
                 break
             if date_consular_encontrada and hora_consular_encontrada and date_huella_encontrada and hora_huella_encontrada:
                 break    
           if date_consular_encontrada and hora_consular_encontrada and date_huella_encontrada and hora_huella_encontrada:
                 break
           #print(f"Impresion 21")
           for a in driver.find_elements(By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-first > div > div > span.ui-datepicker-year'):
                   
             if int(a.text) > int(allowed_year):
               continue_cycle_to_schedule_appointment = False
               break 
 
           #print(f"Impresion 22")
           if not continue_cycle_to_schedule_appointment:
             break

           #print(f"Impresion 23")
           if not date_consular_encontrada:
             WebDriverWait(driver, 10).until(
             EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
             ).click()
             continue

       print(f"Cmpletado")       

    except Exception as e:
        print("❌ Error schedule_for:", e)
        traceback.print_exc()
        with app.app_context():
            p = Perfil.query.get(profile.id)
            p.estado = 'pendiente'
            db.session.commit()  
    
    
    
    
    
    
    return
    try:

       driver, session = login_and_capture(profile, app)
       allowed_months = app.config.get('ALLOWED_MONTHS', [])
       allowed_year = app.config.get('ALLOWED_YEAR', datetime.datetime.now().year)

       human_pause(3,4)

       WebDriverWait(driver, 10).until(
         EC.element_to_be_clickable((By.CSS_SELECTOR, '#main > div:nth-child(2) > div.mainContent > div:nth-child(1) > div > div > div:nth-child(1) > div.medium-6.columns.text-right > ul > li > a'))
       ).click()

       human_pause(3,4)

       print(f"🌀 Explorando {allowed_year} meses {allowed_months}")
       driver.get(f"https://ais.usvisa-info.com/es-do/niv/schedule/{profile.schedule_code}/appointment")
       print(f"🌀 vALOR {driver} ")

       WebDriverWait(driver, 10).until(
         EC.element_to_be_clickable((By.ID, 'appointments_consulate_appointment_date'))
       ).click()

       date_consular_encontrada = False
       hora_consular_encontrada = False
       date_huella_encontrada = False 
       hora_huella_encontrada = False      

       continue_date_consulate_search_cycle = True
       while continue_date_consulate_search_cycle:

           date_consular_encontrada = False
           hora_consular_encontrada = False
           date_huella_encontrada = False 
           hora_huella_encontrada = False 
           for fecha_consular in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):

             fecha_consular.click()  
             date_consular_encontrada = True
             human_pause()
             #print(f"Valor de ciclo 6")  
             WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.ID, 'appointments_consulate_appointment_time'))
             )
             #print(f"Valor de ciclo 7")
             select_hora_consular = Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time'))
             # print(f"Valor de ciclo 8") 
             opciones_hora_consular = [o.text.strip() for o in select_hora_consular.options if o.text.strip()]

             #print(f"oPCIONES HORA CONSULAR: {opciones_hora_consular}")
             hora_consular_encontrada = False
             date_huella_encontrada = False 
             hora_huella_encontrada = False
             for hora_consular in opciones_hora_consular:
 
              Select(driver.find_element(By.ID, 'appointments_consulate_appointment_time')).select_by_visible_text(hora_consular)
              hora_consular_encontrada = True
              human_pause()
            
              #appointments_asc_appointment_date_list = driver.find_elements(By.CSS_SELECTOR, '#appointments_asc_appointment_date') 
              #if not appointments_asc_appointment_date_list:
              #  continue
            
              try:
                WebDriverWait(driver, 10).until(
                  EC.element_to_be_clickable((By.ID, 'appointments_asc_appointment_date'))
                ).click()
              except Exception as e:
                print(f"❌ Error al obtener fecha ASC: {e}")
                continue

              #print(f"MOSTEANDO 1 {appointments_asc_appointment_date_list}")
              
              print(f"MOSTEANDO 2") 
              continue_date_huella_search_cycle = True
              date_huella_encontrada = False 
              hora_huella_encontrada = False
              while continue_date_huella_search_cycle:  

                 date_huella_encontrada = False 
                 hora_huella_encontrada = False
                 for fecha_huella in driver.find_elements(By.CSS_SELECTOR, 'td[data-handler="selectDay"] a'):
                
                    fecha_huella.click()  
                    date_huella_encontrada = True
                    human_pause()

                    WebDriverWait(driver, 10).until(
                       EC.presence_of_element_located((By.ID, 'appointments_asc_appointment_time'))
                    )

                    select_hora_huella = Select(driver.find_element(By.ID, 'appointments_asc_appointment_time'))
                    # print(f"Valor de ciclo 8") 
                    opciones_hora_huella = [o.text.strip() for o in select_hora_huella.options if o.text.strip()]
                    hora_huella_encontrada = False    
                    for hora_huella in opciones_hora_huella:

                      Select(driver.find_element(By.ID, 'appointments_asc_appointment_time')).select_by_visible_text(hora_huella)
                      hora_huella_encontrada = True
                      human_pause() 
                      continue_date_huella_search_cycle = False
                      continue_date_consulate_search_cycle = False
                      break

                 if not continue_date_huella_search_cycle:          
                    break
              
                 WebDriverWait(driver, 10).until(
                  EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
                 ).click() 

              if not continue_date_consulate_search_cycle:
                  break 

              WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
              ).click() 
             
             if not continue_date_consulate_search_cycle:
               break  
          
             WebDriverWait(driver, 10).until(
               EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
             ).click() 
          
           if not continue_date_consulate_search_cycle:
              break
           
           WebDriverWait(driver, 10).until(
             EC.element_to_be_clickable((By.CSS_SELECTOR, '#ui-datepicker-div > div.ui-datepicker-group.ui-datepicker-group-last > div > a'))
           ).click() 

    except Exception as e:
        print("❌ Error schedule_for:", e)
        traceback.print_exc()
        with app.app_context():
            p = Perfil.query.get(profile.id)
            p.estado = 'pendiente'
            db.session.commit()    
    
    #a parti de aqui estaba todo lo de antes
    return
    try:
        driver, session = login_and_capture(profile, app)
        allowed_months = app.config.get('ALLOWED_MONTHS', [])
        allowed_year = app.config.get('ALLOWED_YEAR', datetime.datetime.now().year)

        


        print(f"🌀 Explorando {allowed_year} meses {allowed_months}")
        slot = None
        empty_cycles = 0
        #print(f"🌀 varl {sorted(allowed_months)}")
        
        while not slot:
            for m in sorted(allowed_months):
                days = list(range(1, month_days(allowed_year, m) + 1))
             #   print(f"🌀 dyas {days}")
            #    return
                #for d in random.sample(days, len(days)):
                for d in days:
                    if stop_event and stop_event.is_set():
                        return
                    #print(f"🌀 day {d}")
                    fecha_c = f"{allowed_year}-{m:02d}-{d:02d}"
                    times_c = fetch_times(session, profile.schedule_code, CONSUL_ID, fecha_c, None)
                    #times_c = None
                    if not times_c:
                        print(f"⚠️ No horarios API {fecha_c}, usando Selenium")
                        times_c = fetch_times(session, profile.schedule_code, CONSUL_ID, fecha_c, driver)
                        #times_c = None 

                    human_pause(0.3, 0.6)
                    #human_pause(4, 7)
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
                #human_pause(4, 7)

    
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
    #print(f"Perfiles: {profiles}")
    for profile in profiles:
        t = threading.Thread(target=schedule_for, args=(profile, app))
        t.start()
        threads.append(t)
    #print(f"Hilos: {threads}")    
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
