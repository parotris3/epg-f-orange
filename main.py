import re
import time
import locale
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def generar_epg():
    print("🚀 Iniciando escaneo (Detector de estructura 'Fútbol' + Formato Título)...")

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
        
        url = "https://www.orange.es/orange-tv/futbol/partidos-horarios-orange-tv-libre"
        print(f"🌍 Conectando a {url}...")
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
    # Limpieza: quitamos espacios extra y líneas vacías
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]

    target_channels = ["Fútbol 1", "Fútbol 2", "Fútbol 3"]
    channel_events = {ch: [] for ch in target_channels}

    # Mapeos
    meses = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

    last_date = None
    last_channel = None
    
    # Variables de estado
    current_competition = "Fútbol" # Valor por defecto
    expecting_competition_name = False # Bandera para saber si la siguiente línea es competición

    lines_since_date = 999
    lines_since_channel = 999

    now = datetime.now()
    current_year = now.year

    print("🔍 Analizando líneas...")

    for i, line in enumerate(lines):
        lines_since_date += 1
        lines_since_channel += 1
        
        line_upper = line.upper()

        # A. DETECCIÓN DE COMPETICIÓN (Por estructura)
        # La web pone "FÚTBOL" (en gris) y justo debajo el nombre de la liga.
        if line_upper == "FÚTBOL":
            expecting_competition_name = True
            continue # Saltamos esta línea, nos interesa la siguiente
        
        if expecting_competition_name:
            # Esta línea ES la competición (ej: "Bundesliga")
            current_competition = line.title() # Convertimos a "Bundesliga"
            expecting_competition_name = False
            # print(f"  🏆 Nueva competición detectada: {current_competition}")
            continue

        # B. Detección de Fecha
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

        # C. Detección de Canal
        for ch in target_channels:
            if ch in line:
                last_channel = ch
                lines_since_channel = 0

        # D. Detección de Partido (VS)
        if line_upper == "VS":
            if lines_since_date < 30 and lines_since_channel < 20 and last_date and last_channel:
                # Recuperar nombres y limpiar formato
                raw_team1 = lines[i-1] if len(lines[i-1]) > 1 else lines[i-2]
                raw_team2 = lines[i+1] if len(lines[i+1]) > 1 else lines[i+2]
                
                # Convertir a Título (Primera mayúscula, resto minúscula)
                team1 = raw_team1.title()
                team2 = raw_team2.title()
                
                # Formato limpio para relleno: "Equipo A - Equipo B"
                clean_teams = f"{team1} - {team2}"
                
                # Título completo para emisión: "Bundesliga: Equipo A - Equipo B"
                final_title = f"{current_competition}: {clean_teams}"
                
                end_dt = last_date + timedelta(hours=2)
                
                channel_events[last_channel].append({
                    'clean_teams': clean_teams,
                    'title': final_title,
                    'start': last_date,
                    'end': end_dt
                })
                print(f"  ⚽ {final_title} | {last_channel}")

    # --- GENERACIÓN XML ---
    root = ET.Element("tv")
    matches_found = 0
    fmt_xml = "%Y%m%d%H%M%S +0100"

    for c_name in target_channels:
        chan = ET.SubElement(root, "channel", id=c_name)
        ET.SubElement(chan, "display-name").text = c_name
        
        events = sorted(channel_events[c_name], key=lambda x: x['start'])
        current_cursor = datetime.now()
        
        for event in events:
            matches_found += 1
            start_time = event['start']
            
            # --- RELLENO DE HUECOS ---
            if start_time > current_cursor:
                # Calcular datos de fecha para el texto
                dia_semana = dias_semana[start_time.weekday()]
                dia_mes = start_time.strftime("%d/%m")
                hora = start_time.strftime("%H:%M")
                
                # "Próximo partido: Real Madrid - Barcelona (Sábado 26/10 - 21:00)"
                time_info = f"({dia_semana} {dia_mes} - {hora})"
                filler_title = f"Próximo partido: {event['clean_teams']} {time_info}"
                
                prog_fill = ET.SubElement(root, "programme", 
                                          start=current_cursor.strftime(fmt_xml), 
                                          stop=start_time.strftime(fmt_xml), 
                                          channel=c_name)
                ET.SubElement(prog_fill, "title").text = filler_title
                ET.SubElement(prog_fill, "desc").text = f"Siguiente emisión en {c_name}"
            
            # --- EMISIÓN REAL ---
            prog_match = ET.SubElement(root, "programme", 
                                       start=start_time.strftime(fmt_xml), 
                                       stop=event['end'].strftime(fmt_xml), 
                                       channel=c_name)
            ET.SubElement(prog_match, "title").text = event['title']
            ET.SubElement(prog_match, "desc").text = f"Fútbol en directo - {event['title']}"

            current_cursor = max(current_cursor, event['end'])

    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open("orange.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✅ XML Finalizado. {matches_found} eventos procesados.")

if __name__ == "__main__":
    generar_epg()
    
