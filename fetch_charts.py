#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
S'exécute via GitHub Actions ou cron local.
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import os

# Configuration des sources
SOURCES = {
    "uk": {
        "name": "Royaume-Uni",
        "flag": "🇬🇧",
        "url": "https://www.officialcharts.com/charts/singles-chart/",
        "region": "europe"
    },
    "de": {
        "name": "Allemagne",
        "flag": "🇩🇪",
        "url": "https://www.offiziellecharts.de/charts",
        "region": "europe"
    },
    "ch": {
        "name": "Suisse",
        "flag": "🇨🇭",
        "url": "https://www.hitparade.ch/charts/singles",
        "region": "europe"
    },
    "us": {
        "name": "États-Unis",
        "flag": "🇺🇸",
        "url": "https://www.billboard.com/charts/hot-100/",
        "region": "anglo"
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_week_info():
    """Obtient les informations de la semaine en cours"""
    now = datetime.now()
    week_number = now.isocalendar()[1]
    year = now.year
    return {
        "week": week_number,
        "year": year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {week_number}/{year}"
    }

def fetch_with_retry(url, max_retries=3):
    """Fetch avec retry en cas d'erreur"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"Tentative {attempt + 1} échouée pour {url}: {e}")
            if attempt == max_retries - 1:
                raise

def scrape_uk_official_charts():
    """Scrape Official Charts UK"""
    try:
        response = fetch_with_retry(SOURCES["uk"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        # Structure : Number X, Title, Artist, LW, Peak, Weeks
        chart_items = soup.find_all('div', class_='chart-item') or soup.find_all('article')
        
        # Fallback : chercher par pattern
        if not chart_items:
            # Chercher dans le texte brut
            text = response.text
            pattern = r'Number\s+(\d+).*?<h2[^>]*>(.*?)</h2>.*?<p[^>]*>(.*?)</p>'
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            
            for rank, title, artist in matches[:50]:
                entries.append({
                    "position": int(rank),
                    "track": {
                        "title": title.strip(),
                        "artist": artist.strip()
                    },
                    "previousPosition": None,
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": int(rank)
                })
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur UK: {e}")
        return []

def scrape_germany_offizielle_charts():
    """Scrape Offizielle Charts Allemagne"""
    try:
        response = fetch_with_retry(SOURCES["de"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        # Chercher dans les tableaux
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[:50]:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    rank_text = cells[0].get_text(strip=True)
                    if rank_text.isdigit():
                        rank = int(rank_text)
                        
                        # Extraire artiste et titre
                        info_cell = cells[2] if len(cells) > 2 else None
                        if info_cell:
                            text = info_cell.get_text(separator='|', strip=True)
                            parts = text.split('|')
                            
                            title = parts[0].strip() if len(parts) > 0 else ""
                            artist = parts[1].strip() if len(parts) > 1 else ""
                            
                            # Chercher les métadonnées
                            weeks_text = info_cell.get_text()
                            weeks_match = re.search(r'In Charts:\s*(\d+)', weeks_text)
                            peak_match = re.search(r'Peak:\s*(\d+)', weeks_text)
                            
                            weeks = int(weeks_match.group(1)) if weeks_match else 1
                            peak = int(peak_match.group(1)) if peak_match else rank
                            
                            prev_rank = None
                            if len(cells) > 1:
                                prev_text = cells[1].get_text(strip=True)
                                if prev_text.isdigit():
                                    prev_rank = int(prev_text)
                            
                            movement = "same"
                            if prev_rank:
                                if prev_rank > rank:
                                    movement = "up"
                                elif prev_rank < rank:
                                    movement = "down"
                            
                            entries.append({
                                "position": rank,
                                "track": {
                                    "title": title,
                                    "artist": artist
                                },
                                "previousPosition": prev_rank,
                                "movement": movement,
                                "weeksOnChart": weeks,
                                "peakPosition": peak
                            })
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur Allemagne: {e}")
        return []

def scrape_swiss_hitparade():
    """Scrape Hitparade Suisse"""
    try:
        response = fetch_with_retry(SOURCES["ch"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        # Structure simple : rang, mouvement, artiste, titre, semaines, peak
        
        # Chercher les éléments de classement
        items = soup.find_all('tr') or soup.find_all('div', class_='chart-entry')
        
        current_rank = 0
        for item in items:
            text = item.get_text(separator='|', strip=True)
            
            # Pattern : rang | mouvement | artiste | titre
            parts = [p.strip() for p in text.split('|') if p.strip()]
            
            if len(parts) >= 3 and parts[0].isdigit():
                current_rank += 1
                rank = int(parts[0])
                
                # Détecter si c'est une nouvelle entrée
                is_new = 'neu' in text.lower() or 'new' in text.lower()
                
                title = ""
                artist = ""
                
                if len(parts) >= 4:
                    artist = parts[2]
                    title = parts[3]
                elif len(parts) >= 3:
                    artist = parts[1]
                    title = parts[2]
                
                # Extraire semaines et peak
                weeks_match = re.search(r'W\s*(\d+)', text)
                peak_match = re.search(r'P\s*(\d+)', text)
                
                weeks = int(weeks_match.group(1)) if weeks_match else 1
                peak = int(peak_match.group(1)) if peak_match else rank
                
                movement = "new" if is_new else "same"
                prev_rank = None if is_new else rank
                
                entries.append({
                    "position": rank,
                    "track": {
                        "title": title,
                        "artist": artist
                    },
                    "previousPosition": prev_rank,
                    "movement": movement,
                    "weeksOnChart": weeks,
                    "peakPosition": peak
                })
                
                if len(entries) >= 50:
                    break
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur Suisse: {e}")
        return []

def scrape_billboard_hot100():
    """Scrape Billboard Hot 100"""
    try:
        response = fetch_with_retry(SOURCES["us"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Billboard utilise une structure complexe
        # Chercher les éléments de classement
        chart_items = soup.find_all('div', class_='o-chart-results-list-row-container') or \
                     soup.find_all('li', class_='lrv-u-width-100p')
        
        if not chart_items:
            # Fallback : chercher dans le HTML brut
            text = response.text
            
            # Pattern pour extraire les données
            # Format : rang, titre, artiste, LW, Peak, Weeks
            lines = text.split('\n')
            current_entry = {}
            
            for i, line in enumerate(lines):
                if '###' in line and i < len(lines) - 1:
                    # Nouvelle entrée
                    if current_entry and 'title' in current_entry:
                        entries.append(current_entry)
                    
                    current_entry = {
                        "position": len(entries) + 1,
                        "track": {"title": "", "artist": ""},
                        "previousPosition": None,
                        "movement": "same",
                        "weeksOnChart": 1,
                        "peakPosition": len(entries) + 1
                    }
                    
                    # Extraire le titre
                    title_match = re.search(r'###\s*(.+?)(?:\n|$)', line)
                    if title_match:
                        current_entry["track"]["title"] = title_match.group(1).strip()
                    
                    # Chercher l'artiste dans les lignes suivantes
                    for j in range(i+1, min(i+10, len(lines))):
                        if '###' in lines[j]:
                            break
                        artist_match = re.search(r'([A-Z][^\n]+?)(?:\s*-\s*|\n)', lines[j])
                        if artist_match and len(artist_match.group(1)) < 100:
                            current_entry["track"]["artist"] = artist_match.group(1).strip()
                            break
        
        if current_entry and 'title' in current_entry:
            entries.append(current_entry)
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur Billboard: {e}")
        return []

def main():
    """Fonction principale de collecte"""
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    week_info = get_week_info()
    
    charts_data = {
        "meta": {
            "weekLabel": week_info["label"],
            "week": week_info["week"],
            "year": week_info["year"],
            "updatedAt": week_info["date"],
            "sourceNote": "Données collectées automatiquement depuis les sources officielles. Certaines sources peuvent être indisponibles."
        },
        "countries": {},
        "regions": {
            "europe": {"label": "Europe", "countries": []},
            "anglo": {"label": "Pays anglo-saxons", "countries": []},
            "latam": {"label": "Amérique du Sud", "countries": []}
        }
    }
    
    # Collecter les données pour chaque source
    scrapers = {
        "uk": scrape_uk_official_charts,
        "de": scrape_germany_offizielle_charts,
        "ch": scrape_swiss_hitparade,
        "us": scrape_billboard_hot100
    }
    
    for code, scraper in scrapers.items():
        print(f"📊 Collecte {SOURCES[code]['name']}...")
        entries = scraper()
        
        if entries:
            charts_data["countries"][code] = {
                "name": SOURCES[code]["name"],
                "flag": SOURCES[code]["flag"],
                "region": SOURCES[code]["region"],
                "chart": entries
            }
            
            # Ajouter à la région
            region = SOURCES[code]["region"]
            if region in charts_data["regions"]:
                charts_data["regions"][region]["countries"].append(code)
            
            print(f"  ✅ {len(entries)} entrées collectées")
        else:
            print(f"  ❌ Échec de la collecte")
    
    # Sauvegarder les données
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    # Fichier principal
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    # Fichier horodaté pour l'historique
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Collecte terminée - {len(charts_data['countries'])} pays traités")
    print(f"📁 Données sauvegardées dans {output_dir}/")

if __name__ == "__main__":
    main()