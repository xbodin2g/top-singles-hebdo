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
    },
    "fr": {
        "name": "France",
        "flag": "🇫🇷",
        "url": "https://snepmusique.com/les-tops/le-top-de-la-semaine/top-singles/",
        "region": "europe"
    },
    "br": {
        "name": "Brésil",
        "flag": "🇧🇷",
        "url": "https://pro-musicabr.org.br/home/top-50-streaming/",
        "region": "latam"
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
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[:50]:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    rank_text = cells[0].get_text(strip=True)
                    if rank_text.isdigit():
                        rank = int(rank_text)
                        
                        info_cell = cells[2] if len(cells) > 2 else None
                        if info_cell:
                            text = info_cell.get_text(separator='|', strip=True)
                            parts = text.split('|')
                            
                            title = parts[0].strip() if len(parts) > 0 else ""
                            artist = parts[1].strip() if len(parts) > 1 else ""
                            
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
        items = soup.find_all('tr') or soup.find_all('div', class_='chart-entry')
        
        current_rank = 0
        for item in items:
            text = item.get_text(separator='|', strip=True)
            parts = [p.strip() for p in text.split('|') if p.strip()]
            
            if len(parts) >= 3 and parts[0].isdigit():
                current_rank += 1
                rank = int(parts[0])
                
                is_new = 'neu' in text.lower() or 'new' in text.lower()
                
                title = ""
                artist = ""
                
                if len(parts) >= 4:
                    artist = parts[2]
                    title = parts[3]
                elif len(parts) >= 3:
                    artist = parts[1]
                    title = parts[2]
                
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
        chart_items = soup.find_all('div', class_='o-chart-results-list-row-container') or \
                     soup.find_all('li', class_='lrv-u-width-100p')
        
        if not chart_items:
            text = response.text
            lines = text.split('\n')
            current_entry = {}
            
            for i, line in enumerate(lines):
                if '###' in line and i < len(lines) - 1:
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
                    
                    title_match = re.search(r'###\s*(.+?)(?:\n|$)', line)
                    if title_match:
                        current_entry["track"]["title"] = title_match.group(1).strip()
                    
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

def scrape_france_snep():
    """Scrape SNEP France - utilise l'API ou scraping alternatif"""
    try:
        # Le site SNEP nécessite JavaScript, on essaie une approche alternative
        # Chercher dans le HTML brut ou utiliser un endpoint API
        response = fetch_with_retry(SOURCES["fr"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Essayer de trouver les données dans le HTML
        # SNEP utilise souvent des data attributes ou du JSON embarqué
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string:
                # Chercher des patterns de données
                json_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
                matches = re.findall(json_pattern, script.string)
                
                for match in matches:
                    try:
                        # Essayer de parser si ça ressemble à du JSON
                        if 'title' in match.lower() and 'artist' in match.lower():
                            # C'est probablement du JSON, essayer de l'extraire
                            pass
                    except:
                        continue
        
        # Fallback : chercher dans le texte brut
        text = response.text
        
        # Pattern pour extraire rang, artiste, titre
        # Format typique : numéro suivi de l'artiste et du titre
        lines = text.split('\n')
        current_rank = 0
        
        for i, line in enumerate(lines):
            # Chercher les patterns de classement
            rank_match = re.search(r'^\s*(\d{1,2})\s*$', line.strip())
            if rank_match and current_rank < 50:
                current_rank = int(rank_match.group(1))
                
                # Chercher l'artiste et le titre dans les lignes suivantes
                artist = ""
                title = ""
                
                for j in range(i+1, min(i+5, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and len(next_line) > 3:
                        if not artist:
                            artist = next_line
                        elif not title:
                            title = next_line
                            break
                
                if artist and title:
                    entries.append({
                        "position": current_rank,
                        "track": {
                            "title": title,
                            "artist": artist
                        },
                        "previousPosition": None,
                        "movement": "same",
                        "weeksOnChart": 1,
                        "peakPosition": current_rank
                    })
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur France SNEP: {e}")
        # Retourner des données vides si le scraping échoue
        return []

def scrape_brazil_promusica():
    """Scrape Pro-Música Brasil Top 50 Streaming"""
    try:
        response = fetch_with_retry(SOURCES["br"]["url"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher le tableau avec les données
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows[:50]:
                cells = row.find_all('td')
                
                if len(cells) >= 3:
                    # Structure : rang, (vide ou évolution), artiste + titre
                    rank_cell = cells[0]
                    artist_cell = cells[2] if len(cells) > 2 else None
                    
                    rank_text = rank_cell.get_text(strip=True)
                    
                    if rank_text.isdigit():
                        rank = int(rank_text)
                        
                        if artist_cell:
                            # L'artiste est en gras (<strong>), le titre suit
                            artist_strong = artist_cell.find('strong')
                            
                            if artist_strong:
                                artist = artist_strong.get_text(strip=True)
                                
                                # Le titre est le texte après le <strong>
                                title_parts = []
                                for elem in artist_cell.descendants:
                                    if isinstance(elem, str) and elem.strip():
                                        text = elem.strip()
                                        if text != artist and text:
                                            title_parts.append(text)
                                
                                title = ' '.join(title_parts) if title_parts else ""
                                
                                if title:
                                    entries.append({
                                        "position": rank,
                                        "track": {
                                            "title": title,
                                            "artist": artist
                                        },
                                        "previousPosition": None,
                                        "movement": "same",
                                        "weeksOnChart": 1,
                                        "peakPosition": rank
                                    })
        
        return entries[:50]
    except Exception as e:
        print(f"Erreur Brésil: {e}")
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
        "us": scrape_billboard_hot100,
        "fr": scrape_france_snep,
        "br": scrape_brazil_promusica
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
            
            region = SOURCES[code]["region"]
            if region in charts_data["regions"]:
                charts_data["regions"][region]["countries"].append(code)
            
            print(f"  ✅ {len(entries)} entrées collectées")
        else:
            print(f"  ❌ Échec de la collecte")
    
    # Sauvegarder les données
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Collecte terminée - {len(charts_data['countries'])} pays traités")
    print(f"📁 Données sauvegardées dans {output_dir}/")

if __name__ == "__main__":
    main()