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
    print("🚀 Iniciando escaneo PRO (Nueva URL + Competiciones)...")

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
        
        # 1. CAMBIO DE URL
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
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]

    target_channels = ["Fútbol 1", "Fútbol 2", "Fútbol 3"]
    channel_events = {ch: [] for ch in target_channels}

    # Mapeos de fechas
    meses = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

    # Palabras clave para detectar competiciones
    keywords_competicion = ["LALIGA", "COPA DEL REY", "CHAMPIONS", "EUROPA LEAGUE", "CONFERENCE", "PREMIER", "SERIE A", "BUNDESLIGA", "LIGUE 1", "SUPERCOPA"]

    last_date = None
    last_channel = None
    current_competition = "Fútbol" # Valor por defecto

    # Contadores de distancia
    lines_since_date = 999
    lines_since_channel = 999
    lines_since_comp = 999

    now = datetime.now()
    current_year = now.year

    print("🔍 Analizando bloques de competición y partidos...")

    for i, line in enumerate(lines):
        lines_since_date += 1
        lines_since_channel += 1
        lines_since_comp += 1
        
        line_upper = line.upper()

        # A. DETECCIÓN DE COMPETICIÓN (Lógica de Bloques)
        # Si la línea contiene alguna palabra clave y NO es una fecha ni un canal
        if any(k in line_upper for k in keywords_competicion) and "DE" not in line_upper and "FÚTBOL" not in line_upper:
            current_competition = line.title() # Convertir a Tipo Título (ej: Laliga Ea Sports)
            lines_since_comp = 0
            # print(f"  🏆 Bloque detectado: {current_competition}")
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
                team1 = lines[i-1] if len(lines[i-1]) > 1 else lines[i-2]
                team2 = lines[i+1] if len(lines[i+1]) > 1 else lines[i+2]
                
                # 2. FORMATO EN EMISIÓN: "Competición: Equipo A - Equipo B"
                # Limpiamos los nombres de equipos y usamos guión
                clean_teams = f"{team1} - {team2}"
                final_title = f"{current_competition}: {clean_teams}"
                
                end_dt = last_date + timedelta(hours=2)
                
                channel_events[last_channel].append({
                    'clean_teams': clean_teams, # Guardamos nombre limpio para el relleno
                    'title': final_title,       # Título completo para la emisión
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
            
            # --- 3. FORMATO "PRÓXIMO PARTIDO" ---
            if start_time > current_cursor:
                # Formato: (Jueves 15/01 - 21:00)
                dia_semana = dias_semana[start_time.weekday()]
                dia_mes = start_time.strftime("%d/%m")
                hora = start_time.strftime("%H:%M")
                
                time_info = f"({dia_semana} {dia_mes} - {hora})"
                
                # Próximo partido: Real Madrid - Albacete (Jueves 15/01 - 21:00)
                filler_title = f"Próximo partido: {event['clean_teams']} {time_info}"
                
                prog_fill = ET.SubElement(root, "programme", 
                                          start=current_cursor.strftime(fmt_xml), 
                                          stop=start_time.strftime(fmt_xml), 
                                          channel=c_name)
                ET.SubElement(prog_fill, "title").text = filler_title
                ET.SubElement(prog_fill, "desc").text = f"Siguiente emisión en {c_name}"
            
            # EMISIÓN REAL
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
    print(f"✅ XML generado con éxito. Eventos: {matches_found}")

if __name__ == "__main__":
    generar_epg()
    
