#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version avec Official Independent Singles Chart depuis le site officiel.
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

SOURCES = {
    "us": {
        "name": "États-Unis", 
        "flag": "🇺🇸", 
        "region": "anglo", 
        "source": "billboard"
    },
    "fr": {
        "name": "France", 
        "flag": "🇫🇷", 
        "region": "europe", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/france_singles_top_100"
    },
    "gb": {
        "name": "Royaume-Uni", 
        "flag": "🇬🇧", 
        "region": "europe", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/uk_singles_top_75"
    },
    "gb_indie": {
        "name": "UK Indie", 
        "flag": "🇬🇧", 
        "region": "europe", 
        "source": "official_charts",
        "official_url": "https://www.officialcharts.com/charts/independent-singles-chart/",
        "is_indie": True
    },
    "de": {
        "name": "Allemagne", 
        "flag": "🇩🇪", 
        "region": "europe", 
        "source": "kworb_itunes",
        "kworb_url": "https://kworb.net/charts/itunes/de.html"
    },
    "ch": {
        "name": "Suisse", 
        "flag": "🇨🇭", 
        "region": "europe", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/swiss_singles_top_100"
    },
    "br": {
        "name": "Brésil", 
        "flag": "🇧🇷", 
        "region": "latam", 
        "source": "promusica",
        "primary_url": "https://pro-musicabr.org.br/home/top-50-streaming/"
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_week_info():
    now = datetime.now()
    return {
        "week": now.isocalendar()[1],
        "year": now.year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {now.isocalendar()[1]}/{now.year}"
    }

def calculate_movement(current_pos, previous_pos):
    if previous_pos is None or previous_pos == 0:
        return "new"
    if current_pos < previous_pos:
        return "up"
    elif current_pos > previous_pos:
        return "down"
    else:
        return "same"

def fetch_official_charts_indie(url, country_name):
    """Scrape le site officiel Official Charts Company pour l'Indie Chart"""
    print(f"  🔍 Scraping Official Charts pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 403:
            print(f"    ❌ Bloqué (403 Forbidden)")
            return []
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher tous les éléments "Number X"
        text = response.text
        
        # Pattern pour extraire : Number X, Titre, Artiste, LW, Peak, Weeks
        # Exemple : Number **1**\n\nMOVIN' TO THE SUN\n\nHUGEL/IMAEL ANGEL/ULTRA NATE\n\n1. LW: 2,\n2. Peak: 1,\n3. Weeks: 22
        
        # Diviser le texte en sections par "Number **"
        sections = re.split(r'Number\s+\*\*(\d+)\*\*', text)
        
        # sections[0] est avant le premier "Number", donc on commence à 1
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break
            
            rank = int(sections[i])
            content = sections[i + 1]
            
            # Extraire le titre (première ligne après Number)
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            title = lines[0]
            artist = lines[1]
            
            # Chercher LW, Peak, Weeks
            lw_match = re.search(r'LW:\s*(\d+)', content)
            peak_match = re.search(r'Peak:\s*(\d+)', content)
            weeks_match = re.search(r'Weeks:\s*(\d+)', content)
            
            lw = int(lw_match.group(1)) if lw_match else None
            peak = int(peak_match.group(1)) if peak_match else rank
            weeks = int(weeks_match.group(1)) if weeks_match else 1
            
            # Calculer le mouvement
            movement = calculate_movement(rank, lw)
            
            entries.append({
                "position": rank,
                "track": {"title": title, "artist": artist},
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "official_charts"
            })
        
        # Trier par position et limiter aux 50 premiers
        entries.sort(key=lambda x: x["position"])
        entries = entries[:50]
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        
        if entries:
            print(f"    📊 Exemples de mouvements :")
            for i, entry in enumerate(entries[:3]):
                print(f"       {entry['position']}. {entry['track']['title']} - {entry['movement']} (Préc: {entry['previousPosition']})")
        
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []

def fetch_acharts(url, country_name):
    print(f"  🔍 Scraping acharts.co pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 403:
            print(f"    ❌ Bloqué (403 Forbidden)")
            return []
        
        if response.status_code == 404:
            print(f"    ❌ Page non trouvée (404)")
            return []
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        table = soup.find('table')
        
        if not table:
            return []
        
        rows = table.find_all('tr')[1:]
        
        for row in rows[:50]:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                pos_text = cells[0].get_text(strip=True)
                rank_match = re.search(r'\d+', pos_text)
                
                if rank_match:
                    rank = int(rank_match.group())
                    
                    prev_text = cells[1].get_text(strip=True).lower()
                    previous_pos = None
                    
                    if 'new' in prev_text or 're-entry' in prev_text:
                        previous_pos = None
                    else:
                        prev_match = re.search(r'\d+', prev_text)
                        if prev_match:
                            previous_pos = int(prev_match.group())
                    
                    title_cell = cells[2]
                    title_text = title_cell.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in title_text.split('\n') if line.strip()]
                    
                    if len(lines) >= 2:
                        title = lines[0]
                        artist = lines[1]
                        
                        peak_match = re.search(r'peak position:\s*(\d+)', title_text, re.I)
                        weeks_match = re.search(r'total weeks:\s*(\d+)', title_text, re.I)
                        
                        peak = int(peak_match.group(1)) if peak_match else rank
                        weeks = int(weeks_match.group(1)) if weeks_match else 1
                        
                        movement = calculate_movement(rank, previous_pos)
                        
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist},
                            "previousPosition": previous_pos,
                            "movement": movement,
                            "weeksOnChart": weeks,
                            "peakPosition": peak,
                            "source": "acharts"
                        })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_brazil_promusica():
    print(f"  🔍 Scraping Pro-Música Brasil...")
    
    try:
        response = requests.get(SOURCES["br"]["primary_url"], headers=HEADERS, timeout=30)
        
        if response.status_code == 403:
            return []
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = []
        
        for table in soup.find_all('table'):
            for row in table.find_all('tr', limit=51):
                cells = row.find_all('td')
                
                if len(cells) >= 3:
                    rank_text = cells[0].get_text(strip=True)
                    
                    if rank_text.isdigit():
                        rank = int(rank_text)
                        artist_cell = cells[2] if len(cells) > 2 else None
                        
                        if artist_cell:
                            artist_strong = artist_cell.find('strong')
                            
                            if artist_strong:
                                artist = artist_strong.get_text(strip=True)
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
                                        "track": {"title": title, "artist": artist},
                                        "previousPosition": None,
                                        "movement": "same",
                                        "weeksOnChart": 1,
                                        "peakPosition": rank,
                                        "source": "promusica"
                                    })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_kworb_itunes(url, country_name):
    print(f"  🔍 Scraping kworb iTunes pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code in [403, 404]:
            return []
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = []
        
        table = soup.find('table')
        if not table:
            return []
        
        rows = table.find_all('tr')
        
        for row in rows[1:51]:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                pos_text = cells[0].get_text(strip=True)
                
                if pos_text.isdigit():
                    rank = int(pos_text)
                    
                    movement_text = cells[1].get_text(strip=True).lower()
                    artist_cell = cells[2]
                    artist_text = artist_cell.get_text(strip=True)
                    
                    title = ""
                    artist = ""
                    
                    if ' - ' in artist_text:
                        parts = artist_text.split(' - ', 1)
                        if len(parts) == 2:
                            artist = parts[0].strip()
                            title = parts[1].strip()
                    else:
                        links = artist_cell.find_all('a')
                        if len(links) >= 2:
                            artist = links[0].get_text(strip=True)
                            title = links[1].get_text(strip=True)
                    
                    if title and artist:
                        previous_pos = None
                        movement = "new"
                        
                        if movement_text == 'new' or movement_text == '':
                            movement = "new"
                        elif movement_text.startswith('+'):
                            try:
                                diff = int(movement_text[1:])
                                previous_pos = rank + diff
                                movement = "up"
                            except:
                                movement = "same"
                                previous_pos = rank
                        elif movement_text.startswith('-'):
                            try:
                                diff = int(movement_text[1:])
                                previous_pos = rank - diff
                                movement = "down"
                            except:
                                movement = "same"
                                previous_pos = rank
                        else:
                            movement = "same"
                            previous_pos = rank
                        
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist},
                            "previousPosition": previous_pos,
                            "movement": movement,
                            "weeksOnChart": 1,
                            "peakPosition": rank,
                            "source": "kworb_itunes"
                        })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_billboard_hot100():
    print(f"  🔍 Tentative avec billboard.py...")
    
    try:
        import billboard
        
        chart = billboard.ChartData('hot-100')
        entries = []
        
        for i, entry in enumerate(chart.entries[:50]):
            lw = getattr(entry, 'lastPos', None)
            peak = getattr(entry, 'peakPos', i + 1)
            weeks = getattr(entry, 'weeks', 1)
            
            if lw == 0:
                lw = None
            
            movement = calculate_movement(i + 1, lw)
            
            entries.append({
                "position": i + 1,
                "track": {"title": entry.title, "artist": entry.artist},
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "billboard"
            })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur billboard.py: {e}")
    
    print(f"  🔄 Fallback sur acharts.co pour US...")
    return fetch_acharts("https://acharts.co/us_singles_top_100", "US")

def main():
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    week_info = get_week_info()
    
    charts_data = {
        "meta": {
            "weekLabel": week_info["label"],
            "week": week_info["week"],
            "year": week_info["year"],
            "updatedAt": week_info["date"],
            "sourceNote": ""
        },
        "countries": {},
        "regions": {
            "europe": {"label": "Europe", "countries": []},
            "anglo": {"label": "Pays anglo-saxons", "countries": []},
            "latam": {"label": "Amérique du Sud", "countries": []}
        }
    }
    
    successful_sources = []
    failed_sources = []
    
    for code, country_info in SOURCES.items():
        print(f"\n📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        source_used = country_info["source"]
        
        if source_used == "billboard":
            entries = fetch_billboard_hot100()
        elif source_used == "acharts":
            entries = fetch_acharts(country_info["acharts_url"], country_info["name"])
        elif source_used == "kworb_itunes":
            entries = fetch_kworb_itunes(country_info["kworb_url"], country_info["name"])
        elif source_used == "promusica":
            entries = fetch_brazil_promusica()
        elif source_used == "official_charts":
            entries = fetch_official_charts_indie(country_info["official_url"], country_info["name"])
        else:
            entries = []
        
        if entries and len(entries) >= 10:
            charts_data["countries"][code] = {
                "name": country_info["name"],
                "flag": country_info["flag"],
                "region": country_info["region"],
                "chart": entries,
                "sourceType": source_used,
                "isIndie": country_info.get("is_indie", False)
            }
            
            charts_data["regions"][country_info["region"]]["countries"].append(code)
            successful_sources.append(country_info["name"])
            print(f"  ✅ {len(entries)} titres collectés")
        else:
            failed_sources.append(country_info["name"])
            print(f"  ❌ Échec")
    
    if successful_sources and failed_sources:
        charts_data["meta"]["sourceNote"] = f"✅ {len(successful_sources)} sources OK. ❌ {len(failed_sources)} échouées."
    elif successful_sources:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources : {len(successful_sources)} tops collectés."
    else:
        charts_data["meta"]["sourceNote"] = "❌ Aucune source collectée."
    
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Collecte terminée : {len(successful_sources)} réussies, {len(failed_sources)} échouées")

if __name__ == "__main__":
    main()