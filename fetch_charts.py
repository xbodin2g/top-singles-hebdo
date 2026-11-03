#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version avec UK Indie (Wayback Machine) et Singapour (iTunes RSS).
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
import time

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
        "source": "wayback",
        "wayback_url": "https://web.archive.org/web/2026/https://www.officialcharts.com/charts/independent-singles-chart/",
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
    },
    "sg": {
        "name": "Singapour", 
        "flag": "🇸🇬", 
        "region": "asia", 
        "source": "itunes_rss",
        "itunes_url": "https://itunes.apple.com/sg/rss/topsongs/limit=50/json"
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_week_info():
    """Obtient les informations de la semaine en cours"""
    now = datetime.now()
    return {
        "week": now.isocalendar()[1],
        "year": now.year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {now.isocalendar()[1]}/{now.year}"
    }

def calculate_movement(current_pos, previous_pos):
    """Calcule le mouvement basé sur les positions"""
    if previous_pos is None or previous_pos == 0:
        return "new"
    if current_pos < previous_pos:
        return "up"
    elif current_pos > previous_pos:
        return "down"
    else:
        return "same"

def fetch_uk_indie_wayback(country_name):
    """Récupère UK Indie via Wayback Machine (contourne le 403)"""
    print(f"  🔍 Scraping UK Indie via Wayback Machine pour {country_name}...")
    
    # URL Wayback Machine qui récupère la dernière archive de 2026
    wayback_url = "https://web.archive.org/web/2026/https://www.officialcharts.com/charts/independent-singles-chart/"
    
    try:
        response = requests.get(wayback_url, headers=HEADERS, timeout=45, allow_redirects=True)
        
        if response.status_code == 404:
            print(f"    ❌ Pas d'archive trouvée (404)")
            return []
        
        response.raise_for_status()
        text = response.text
        
        print(f"    📄 Taille HTML : {len(text)} caractères")
        
        # Parser le contenu (même structure que le site officiel)
        entries = []
        
        # Pattern 1 : Number **X**
        sections = re.split(r'Number\s+\*\*(\d+)\*\*', text)
        
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break
            
            rank = int(sections[i])
            content = sections[i + 1]
            
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            title = lines[0]
            artist = lines[1]
            
            lw_match = re.search(r'LW:\s*(\d+)', content)
            peak_match = re.search(r'Peak:\s*(\d+)', content)
            weeks_match = re.search(r'Weeks:\s*(\d+)', content)
            
            lw = int(lw_match.group(1)) if lw_match else None
            peak = int(peak_match.group(1)) if peak_match else rank
            weeks = int(weeks_match.group(1)) if weeks_match else 1
            
            movement = calculate_movement(rank, lw)
            
            entries.append({
                "position": rank,
                "track": {"title": title, "artist": artist},
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "wayback_official_charts"
            })
        
        entries.sort(key=lambda x: x["position"])
        entries = entries[:50]
        
        if entries:
            print(f"    ✅ {len(entries)} entrées trouvées via Wayback Machine")
            print(f"    📊 Top 3 :")
            for i, entry in enumerate(entries[:3]):
                print(f"       {entry['position']}. {entry['track']['title']} - {entry['track']['artist']} ({entry['movement']})")
            return entries
        
        print(f"    ❌ 0 entrées trouvées")
        return []
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_itunes_rss(url, country_name):
    """Récupère le top via l'API iTunes RSS (JSON, très fiable)"""
    print(f"  🔍 Scraping iTunes RSS pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        entries = []
        feed_entries = data.get('feed', {}).get('entry', [])
        
        for index, entry in enumerate(feed_entries):
            try:
                title = entry.get('im:name', {}).get('label', '')
                artist = entry.get('im:artist', {}).get('label', '')
                
                images = entry.get('im:image', [])
                artwork = images[-1].get('label', '') if images else ''
                
                if title and artist:
                    entries.append({
                        "position": index + 1,
                        "track": {
                            "title": title,
                            "artist": artist,
                            "artwork": artwork
                        },
                        "previousPosition": None,
                        "movement": "new" if index == 0 else "same",
                        "weeksOnChart": 1,
                        "peakPosition": index + 1,
                        "source": "itunes_rss"
                    })
            except Exception as e:
                continue
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        
        if entries:
            print(f"    📊 Top 3 :")
            for i, entry in enumerate(entries[:3]):
                print(f"       {entry['position']}. {entry['track']['artist']} - {entry['track']['title']}")
        
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_acharts(url, country_name):
    """Scrape acharts.co pour les tops standards"""
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
    """Scrape Pro-Música Brasil (source officielle)"""
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
    """Scrape kworb.net iTunes (pour Allemagne)"""
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
    """Récupère le Billboard Hot 100"""
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
    """Fonction principale de collecte"""
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
            "latam": {"label": "Amérique du Sud", "countries": []},
            "asia": {"label": "Asie", "countries": []}
        }
    }
    
    successful_sources = []
    failed_sources = []
    
    for code, country_info in SOURCES.items():
        print(f"\n📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        source_used = country_info["source"]
        entries = []
        
        if source_used == "billboard":
            entries = fetch_billboard_hot100()
        
        elif source_used == "acharts":
            entries = fetch_acharts(country_info["acharts_url"], country_info["name"])
        
        elif source_used == "kworb_itunes":
            entries = fetch_kworb_itunes(country_info["kworb_url"], country_info["name"])
        
        elif source_used == "promusica":
            entries = fetch_brazil_promusica()
        
        elif source_used == "wayback":
            entries = fetch_uk_indie_wayback(country_info["name"])
        
        elif source_used == "itunes_rss":
            entries = fetch_itunes_rss(country_info["itunes_url"], country_info["name"])
        
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
            print(f"  ✅ {len(entries)} titres collectés via {source_used}")
        else:
            failed_sources.append(country_info["name"])
            print(f"  ❌ Échec")
    
    # Générer le message de note
    if successful_sources and failed_sources:
        charts_data["meta"]["sourceNote"] = f"✅ {len(successful_sources)} sources OK. ❌ {len(failed_sources)} échouées."
    elif successful_sources:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources : {len(successful_sources)} tops collectés."
    else:
        charts_data["meta"]["sourceNote"] = "❌ Aucune source collectée."
    
    # Sauvegarder les données
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ Collecte terminée")
    print(f"   - {len(successful_sources)} sources réussies")
    print(f"   - {len(failed_sources)} sources échouées")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()