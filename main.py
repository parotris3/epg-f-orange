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
    print("🚀 Iniciando escaneo en GitHub Actions...")

    # Configuración para entorno Servidor (Headless real)
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage") # Vital para contenedores Docker/GitHub
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

    root = ET.Element("tv")
    target_channels = ["Fútbol 1", "Fútbol 2", "Fútbol 3"]
    
    for c_name in target_channels:
        chan = ET.SubElement(root, "channel", id=c_name)
        ET.SubElement(chan, "display-name").text = c_name

    meses = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

    matches_found = 0
    last_date = None
    last_channel = None
    lines_since_date = 999
    lines_since_channel = 999

    # Usamos hora local del sistema (que configuraremos a Madrid en el YAML)
    now = datetime.now()
    current_year = now.year

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
                    
                    # Ajuste de año lógico
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
                fmt = "%Y%m%d%H%M%S +0100"
                end_dt = last_date + timedelta(hours=2)
                
                prog = ET.SubElement(root, "programme", start=last_date.strftime(fmt), stop=end_dt.strftime(fmt), channel=last_channel)
                ET.SubElement(prog, "title").text = title
                
                print(f"⚽ {title} | {last_channel}")
                matches_found += 1

    # Guardar XML
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open("orange.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✅ Generado con {matches_found} eventos.")

if __name__ == "__main__":
    generar_epg()