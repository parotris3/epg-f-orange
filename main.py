import re
import time
import os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def generar_epg():
    print("🚀 Iniciando escaneo avanzado con relleno de huecos...")

    # --- CONFIGURACIÓN SELENIUM ---
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        url = "https://www.orange.es/orange-tv/futbol/partidos-horarios"
        driver.get(url)
        time.sleep(5) 
        html_content = driver.page_source
        driver.quit()
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        return

    # --- PROCESAMIENTO ---
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text(separator="\n")
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]

    # Estructura para guardar eventos en memoria antes de escribir el XML
    target_channels = ["Fútbol 1", "Fútbol 2", "Fútbol 3"]
    channel_events = {ch: [] for ch in target_channels}

    meses = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

    last_date = None
    last_channel = None
    lines_since_date = 999
    lines_since_channel = 999

    now = datetime.now()
    current_year = now.year

    print("🔍 Analizando datos...")

    # 1. RECOLECCIÓN DE DATOS
    for i, line in enumerate(lines):
        lines_since_date += 1
        lines_since_channel += 1

        # Detección de fecha
        date_match = re.search(r'(\d{1,2})\s+de\s+([a-z]+),?\s+(\d{1,2}:\d{2})', line, re.IGNORECASE)
        if date_match:
            try:
                day = int(date_match.group(1))
                month_str = date_match.group(2).lower()
                time_str = date_match.group(3)
                
                if month_str in meses:
                    month = meses[month_str]
                    hour, minute = map(int, time_str.split(':'))
                    dt = datetime(current_year, month, day, hour, minute)
                    
                    if now.month == 12 and month == 1:
                        dt = dt.replace(year=current_year + 1)
                    elif now.month == 1 and month == 12:
                        dt = dt.replace(year=current_year - 1)

                    last_date = dt
                    lines_since_date = 0
            except: pass

        # Detección de Canal
        for ch in target_channels:
            if ch in line:
                last_channel = ch
                lines_since_channel = 0

        # Detección de Partido
        if line.strip().upper() == "VS":
            if lines_since_date < 25 and lines_since_channel < 15 and last_date and last_channel:
                team1 = lines[i-1] if len(lines[i-1]) > 1 else lines[i-2]
                team2 = lines[i+1] if len(lines[i+1]) > 1 else lines[i+2]
                
                title = f"{team1} VS {team2}"
                end_dt = last_date + timedelta(hours=2) # Duración 2h
                
                # Guardamos en memoria en lugar de escribir XML directamente
                channel_events[last_channel].append({
                    'title': title,
                    'start': last_date,
                    'end': end_dt
                })
                print(f"  ⚽ Detectado: {title} | {last_channel}")

    # 2. GENERACIÓN XML CON RELLENO DE HUECOS
    root = ET.Element("tv")
    matches_found = 0
    fmt = "%Y%m%d%H%M%S +0100"

    for c_name in target_channels:
        # Cabecera del canal
        chan = ET.SubElement(root, "channel", id=c_name)
        ET.SubElement(chan, "display-name").text = c_name
        
        # Ordenamos los eventos por fecha
        events = sorted(channel_events[c_name], key=lambda x: x['start'])
        
        # Puntero de tiempo: Empezamos a rellenar desde AHORA
        # (Restamos unos minutos por seguridad para no dejar huecos si el script tarda)
        current_cursor = datetime.now()
        
        for event in events:
            matches_found += 1
            start_time = event['start']
            
            # Si el partido empieza después de 'ahora', hay un hueco
            if start_time > current_cursor:
                # CREAR EVENTO DE RELLENO
                filler_title = f"Próximo partido: {event['title']}"
                
                prog_fill = ET.SubElement(root, "programme", 
                                          start=current_cursor.strftime(fmt), 
                                          stop=start_time.strftime(fmt), 
                                          channel=c_name)
                ET.SubElement(prog_fill, "title").text = filler_title
                ET.SubElement(prog_fill, "desc").text = "No hay emisión en directo en este momento."
            
            # CREAR EVENTO DEL PARTIDO REAL
            prog_match = ET.SubElement(root, "programme", 
                                       start=start_time.strftime(fmt), 
                                       stop=event['end'].strftime(fmt), 
                                       channel=c_name)
            ET.SubElement(prog_match, "title").text = event['title']
            ET.SubElement(prog_match, "desc").text = "Fútbol en directo"

            # Actualizamos el cursor al final de este partido
            # Para que el siguiente relleno empiece cuando acabe este
            current_cursor = max(current_cursor, event['end'])

    # Guardar XML
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open("orange.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✅ XML generado. Total eventos reales procesados: {matches_found}")

if __name__ == "__main__":
    generar_epg()
