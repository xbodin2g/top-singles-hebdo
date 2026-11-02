#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version utilisant acharts.co pour tous les pays (mouvements corrects).
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

SOURCES = {
    "us": {"name": "États-Unis", "flag": "🇺🇸", "region": "anglo", "source": "billboard"},
    "fr": {"name": "France", "flag": "🇫🇷", "region": "europe", "source": "acharts", "acharts_url": "https://acharts.co/france_singles_top_100"},
    "gb": {"name": "Royaume-Uni", "flag": "🇬🇧", "region": "europe", "source": "acharts", "acharts_url": "https://acharts.co/uk_singles_top_75"},
    "de": {"name": "Allemagne", "flag": "🇩🇪", "region": "europe", "source": "acharts", "acharts_url": "https://acharts.co/germany_singles_top_100"},
    "ch": {"name": "Suisse", "flag": "🇨🇭", "region": "europe", "source": "acharts", "acharts_url": "https://acharts.co/switzerland_singles_top_100"},
    "br": {"name": "Brésil", "flag": "🇧🇷", "region": "latam", "source": "acharts", "acharts_url": "https://acharts.co/brazil_singles_top_100"}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
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
    """Calcule le mouvement basé sur les positions"""
    if previous_pos is None or previous_pos == 0:
        return "new"
    
    if current_pos < previous_pos:
        return "up"
    elif current_pos > previous_pos:
        return "down"
    else:
        return "same"

def fetch_acharts(url, country_name):
    """Scrape acharts.co avec extraction correcte des positions précédentes"""
    print(f"  🔍 Tentative de scraping de {url}...")
    
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
        
        # Chercher le tableau principal
        table = soup.find('table')
        
        if not table:
            print(f"    ❌ Pas de tableau trouvé")
            return []
        
        rows = table.find_all('tr')[1:]  # Sauter l'en-tête
        
        for row in rows[:50]:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                # Colonne 0 : position actuelle
                pos_text = cells[0].get_text(strip=True)
                rank_match = re.search(r'\d+', pos_text)
                
                if rank_match:
                    rank = int(rank_match.group())
                    
                    # Colonne 1 : position précédente (IMPORTANT !)
                    prev_text = cells[1].get_text(strip=True).lower()
                    previous_pos = None
                    
                    # Vérifier si c'est une nouvelle entrée ou re-entry
                    if 'new' in prev_text or 're-entry' in prev_text:
                        previous_pos = None
                    else:
                        # Extraire le numéro
                        prev_match = re.search(r'\d+', prev_text)
                        if prev_match:
                            previous_pos = int(prev_match.group())
                    
                    # Colonne 2 : titre et artiste
                    title_cell = cells[2]
                    title_text = title_cell.get_text(separator='\n', strip=True)
                    
                    # Pattern : Titre\nArtiste
                    lines = [line.strip() for line in title_text.split('\n') if line.strip()]
                    
                    if len(lines) >= 2:
                        title = lines[0]
                        artist = lines[1]
                        
                        # Chercher les métadonnées
                        peak_match = re.search(r'peak position:\s*(\d+)', title_text, re.I)
                        weeks_match = re.search(r'total weeks:\s*(\d+)', title_text, re.I)
                        
                        peak = int(peak_match.group(1)) if peak_match else rank
                        weeks = int(weeks_match.group(1)) if weeks_match else 1
                        
                        # Calculer le mouvement
                        movement = calculate_movement(rank, previous_pos)
                        
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist, "artwork": ""},
                            "previousPosition": previous_pos,
                            "movement": movement,
                            "weeksOnChart": weeks,
                            "peakPosition": peak,
                            "source": "acharts"
                        })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        
        # Debug : afficher quelques exemples
        if entries:
            print(f"    📊 Exemples de mouvements :")
            for i, entry in enumerate(entries[:5]):
                print(f"       {entry['position']}. {entry['track']['title']} - Mouvement: {entry['movement']} (Préc: {entry['previousPosition']})")
        
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []

def fetch_billboard_hot100():
    """Récupère le Billboard Hot 100 avec positions précédentes"""
    print(f"  🔍 Tentative avec billboard.py...")
    
    try:
        import billboard
        
        chart = billboard.ChartData('hot-100')
        
        entries = []
        for i, entry in enumerate(chart.entries[:50]):
            # Récupérer les attributs (peuvent être None ou 0)
            lw = getattr(entry, 'lastPos', None)
            peak = getattr(entry, 'peakPos', i + 1)
            weeks = getattr(entry, 'weeks', 1)
            
            # Normaliser lastPos (0 signifie nouvelle entrée)
            if lw == 0:
                lw = None
            
            # Calculer le mouvement
            movement = calculate_movement(i + 1, lw)
            
            entries.append({
                "position": i + 1,
                "track": {
                    "title": entry.title,
                    "artist": entry.artist,
                    "artwork": ""
                },
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "billboard"
            })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        
        # Debug
        if entries:
            print(f"    📊 Exemples de mouvements :")
            for i, entry in enumerate(entries[:5]):
                print(f"       {entry['position']}. {entry['track']['title']} - Mouvement: {entry['movement']} (Préc: {entry['previousPosition']})")
        
        return entries
    
    except ImportError:
        print(f"    ❌ billboard.py non installé")
        return []
    except Exception as e:
        print(f"    ❌ Erreur billboard.py: {e}")
        import traceback
        traceback.print_exc()
        
        print(f"  🔄 Fallback sur acharts.co...")
        return fetch_acharts("https://acharts.co/us_singles_top_100", "US")

def fetch_itunes_chart(country_code, limit=50):
    """Fallback : Récupère le top singles via l'API iTunes RSS"""
    url = f"https://itunes.apple.com/{country_code}/rss/topsongs/limit={limit}/json"
    
    print(f"  🔄 Fallback iTunes RSS...")
    
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
                    # iTunes ne fournit pas les positions précédentes
                    entries.append({
                        "position": index + 1,
                        "track": {
                            "title": title,
                            "artist": artist,
                            "artwork": artwork
                        },
                        "previousPosition": None,
                        "movement": "new",
                        "weeksOnChart": 1,
                        "peakPosition": index + 1,
                        "source": "itunes"
                    })
            except Exception as e:
                continue
        
        print(f"    ✅ {len(entries)} entrées trouvées (iTunes fallback)")
        print(f"    ⚠️ iTunes ne fournit pas les positions précédentes")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur iTunes: {e}")
        return []

def main():
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    week_info = get_week_info()
    
    charts_data = {
        "meta": {
            "weekLabel": week_info["label"],
            "week": week_info["week"],
            "year": week_info["year"],
            "updatedAt": week_info["date"],
            "sourceNote": "",
            "sources": {}
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
        
        entries = []
        source_used = country_info["source"]
        
        if source_used == "billboard":
            entries = fetch_billboard_hot100()
            if entries:
                source_used = "billboard"
            else:
                # Fallback sur acharts
                entries = fetch_acharts("https://acharts.co/us_singles_top_100", "US")
                if entries:
                    source_used = "acharts"
        
        elif source_used == "acharts":
            entries = fetch_acharts(country_info["acharts_url"], country_info["name"])
            
            # Si acharts échoue, fallback sur iTunes
            if not entries or len(entries) < 10:
                itunes_codes = {
                    "de": "de",
                    "ch": "ch",
                    "br": "br",
                    "fr": "fr",
                    "gb": "gb"
                }
                
                if code in itunes_codes:
                    print(f"  🔄 Fallback sur iTunes RSS pour {country_info['name']}...")
                    entries = fetch_itunes_chart(itunes_codes[code])
                    if entries:
                        source_used = "itunes"
        
        if entries and len(entries) >= 10:
            charts_data["countries"][code] = {
                "name": country_info["name"],
                "flag": country_info["flag"],
                "region": country_info["region"],
                "chart": entries,
                "isDemo": False,
                "sourceType": source_used
            }
            
            charts_data["regions"][country_info["region"]]["countries"].append(code)
            charts_data["meta"]["sources"][code] = source_used
            successful_sources.append(f"{country_info['name']} ({source_used})")
            
            print(f"  ✅ {len(entries)} titres collectés via {source_used}")
        else:
            print(f"  ❌ Échec pour {country_info['name']}")
            failed_sources.append(country_info["name"])
    
    if successful_sources and failed_sources:
        charts_data["meta"]["sourceNote"] = (
            f"✅ Sources réussies : {', '.join(successful_sources)}. "
            f"❌ Sources échouées : {', '.join(failed_sources)}."
        )
    elif successful_sources:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources : {', '.join(successful_sources)}."
    else:
        charts_data["meta"]["sourceNote"] = "❌ Aucune source n'a pu être collectée."
    
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