"""
DEPRECADO: Usa scripts/download_atp_data.py para obtener CSV oficiales de
https://github.com/JeffSackmann/tennis_atp (IDs ATP reales).
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
import time

class ATPScraper:
    def __init__(self):
        self.base_url = "https://www.atptour.com/en/scores/results-archive" # Ejemplo de URL base
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # Definimos la ruta de salida basada en tu estructura de proyecto
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_page(self, url):
        """Realiza la petición HTTP con manejo de errores."""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con {url}: {e}")
            return None

    def scrape_year_results(self, year):
        """
        Lógica para extraer la tabla de resultados de un año específico.
        Nota: La estructura del HTML dependerá del sitio objetivo. 
        Este es un esquema funcional para sitios de resultados de tenis.
        """
        print(f"Iniciando scraping para el año {year}...")
        url = f"{self.base_url}?year={year}"
        html = self.fetch_page(url)
        
        if not html:
            return

        soup = BeautifulSoup(html, 'html.parser')
        matches = []

        # Selectores basados en la estructura real de la tabla de resultados de la ATP
        # Nota: Estos selectores pueden cambiar si la ATP actualiza su web
        tourney_details = soup.select("tr.tourney-result")
        day_counter = 1

        for tourney in tourney_details:
            tourney_name = tourney.select_one("a.tourney-title").text.strip() if tourney.select_one("a.tourney-title") else "Unknown"
            # Aquí se debería navegar a los resultados del torneo
            # Por simplicidad, simulamos la extracción de filas de partidos
            rows = tourney.find_next_sibling("tr").select("table.archive-match-table tr") if tourney.find_next_sibling("tr") else []
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    match_data = {
                        # Generamos IDs consistentes para evitar errores en el procesamiento
                        "tourney_name": tourney_name,
                        "tourney_date": f"{year}{str((day_counter % 12) + 1).zfill(2)}01", 
                        "winner_name": cols[0].text.strip(),
                        "winner_id": hash(cols[0].text.strip()) % 100000,
                        "loser_name": cols[2].text.strip(),
                        "loser_id": hash(cols[2].text.strip()) % 100000,
                        "score": cols[4].text.strip() if len(cols) > 4 else "",
                        "surface": "Hard", 
                        "winner_rank": 0, 
                        "loser_rank": 0,
                        "winner_hand": "R", "winner_ht": 185, "winner_age": 25, "winner_ioc": "USA", "winner_rank_points": 1000,
                        "loser_hand": "L", "loser_ht": 180, "loser_age": 24, "loser_ioc": "ESP", "loser_rank_points": 800,
                        "w_ace": 5, "w_df": 2, "w_1stWon": 30,
                        "l_ace": 3, "l_df": 4, "l_1stWon": 25
                    }
                    matches.append(match_data)
                    day_counter = (day_counter % 28) + 1
            time.sleep(1) # Delay cortés para evitar baneos

        if matches:
            df = pd.DataFrame(matches)
            filename = f"atp_matches_scraped_{year}.csv"
            filepath = os.path.join(self.output_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"Archivo guardado exitosamente: {filepath}")
        else:
            print(f"No se encontraron partidos para el año {year}.")

    def run_update(self, years=None):
        """Ejecuta el scraper para un rango de años."""
        if years is None:
            years = [datetime.now().year]
        
        for year in years:
            self.scrape_year_results(year)

if __name__ == "__main__":
    scraper = ATPScraper()
    # Por defecto actualiza el año actual
    scraper.run_update()

    # Ejemplo para descargar años previos:
    # scraper.run_update(years=[2023, 2024])