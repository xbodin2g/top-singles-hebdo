#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version utilisant billboard.py et Official Charts Company pour des données réelles.
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

# Configuration des sources
SOURCES = {
    "us": {"name": "États-Unis", "flag": "🇺🇸", "region": "anglo", "source": "billboard"},
    "fr": {"name": "France", "flag": "🇫🇷", "region": "europe", "source": "official_charts"},
    "gb": {"name": "Royaume-Uni", "flag": "🇬🇧", "region": "europe", "source": "official_charts"},
    "de": {"name": "Allemagne", "flag": "🇩🇪", "itunes_code": "de", "region": "europe", "source": "itunes"},
    "ch": {"name": "Suisse", "flag": "🇨🇭", "itunes_code": "ch", "region": "europe", "source": "itunes"},
    "br": {"name": "Brésil", "flag": "🇧🇷", "itunes_code": "br", "region": "latam", "source": "itunes"}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_week_info():
    now = datetime.now()
    week_number = now.isocalendar()[1]
    year = now.year
    return {
        "week": week_number,
        "year": year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {week_number}/{year}"
    }

def fetch_billboard_hot100():
    """Récupère le vrai Billboard Hot 100 via billboard.py"""
    try:
        import billboard
        
        # Récupérer le Hot 100 actuel
        chart = billboard.ChartData('hot-100')
        
        entries = []
        for i, entry in enumerate(chart.entries[:50]):
            entries.append({
                "position": i + 1,
                "track": {
                    "title": entry.title,
                    "artist": entry.artist,
                    "artwork": ""
                },
                "previousPosition": entry.lastPos if hasattr(entry, 'lastPos') else None,
                "movement": "same",
                "weeksOnChart": entry.weeks if hasattr(entry, 'weeks') else 1,
                "peakPosition": entry.peakPos if hasattr(entry, 'peakPos') else i + 1,
                "source": "billboard"
            })
            
            # Calculer le mouvement
            if entry.lastPos and entry.lastPos > 0:
                if entry.lastPos > i + 1:
                    entries[-1]["movement"] = "up"
                elif entry.lastPos < i + 1:
                    entries[-1]["movement"] = "down"
            else:
                entries[-1]["movement"] = "new"
        
        return entries
    
    except ImportError:
        print("    ❌ billboard.py n'est pas installé")
        return []
    except Exception as e:
        print(f"    ❌ Erreur Billboard: {e}")
        return []

def fetch_official_charts_france():
    """Récupère le top France via Official Charts Company"""
    url = "https://www.officialcharts.com/charts/french-singles-chart/"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher les éléments "Number X"
        text = response.text
        
        # Pattern : Number X suivi de titre et artiste
        pattern = r'Number\s+(\d+)\s*(.*?)\s*([A-Z][A-Z\s]+)\s*1\.\s*LW:\s*(\d+|none)'
        matches = re.findall(pattern, text, re.DOTALL)
        
        if not matches:
            # Essayer avec un pattern plus flexible
            items = soup.find_all(['article', 'div'])
            
            for item in items:
                item_text = item.get_text()
                
                # Chercher "Number X"
                rank_match = re.search(r'Number\s+(\d+)', item_text, re.I)
                if rank_match:
                    rank = int(rank_match.group(1))
                    
                    # Extraire les lignes
                    lines = [line.strip() for line in item_text.split('\n') if line.strip()]
                    
                    title = ""
                    artist = ""
                    lw = None
                    peak = None
                    weeks = None
                    
                    # Chercher le titre et l'artiste
                    for i, line in enumerate(lines):
                        if 'Number' in line and i + 1 < len(lines):
                            title = lines[i + 1]
                            if i + 2 < len(lines):
                                artist = lines[i + 2]
                            break
                    
                    # Chercher les métadonnées
                    lw_match = re.search(r'LW:\s*(\d+)', item_text, re.I)
                    peak_match = re.search(r'Peak:\s*(\d+)', item_text, re.I)
                    weeks_match = re.search(r'Weeks:\s*(\d+)', item_text, re.I)
                    
                    if lw_match and lw_match.group(1) != 'none':
                        lw = int(lw_match.group(1))
                    if peak_match:
                        peak = int(peak_match.group(1))
                    if weeks_match:
                        weeks = int(weeks_match.group(1))
                    
                    if title and artist and rank <= 50:
                        movement = "same"
                        if lw:
                            if lw > rank:
                                movement = "up"
                            elif lw < rank:
                                movement = "down"
                        else:
                            movement = "new"
                        
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist, "artwork": ""},
                            "previousPosition": lw,
                            "movement": movement,
                            "weeksOnChart": weeks if weeks else 1,
                            "peakPosition": peak if peak else rank,
                            "source": "official_charts"
                        })
        
        return entries[:50]
    
    except Exception as e:
        print(f"    ❌ Erreur Official Charts France: {e}")
        return []

def fetch_official_charts_uk():
    """Récupère le top UK via Official Charts Company"""
    url = "https://www.officialcharts.com/charts/singles-chart/"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher les éléments de chart
        items = soup.find_all(['article', 'div'])
        
        for item in items:
            item_text = item.get_text()
            
            rank_match = re.search(r'Number\s+(\d+)', item_text, re.I)
            if rank_match:
                rank = int(rank_match.group(1))
                
                lines = [line.strip() for line in item_text.split('\n') if line.strip()]
                
                title = ""
                artist = ""
                lw = None
                peak = None
                weeks = None
                
                for i, line in enumerate(lines):
                    if 'Number' in line and i + 1 < len(lines):
                        title = lines[i + 1]
                        if i + 2 < len(lines):
                            artist = lines[i + 2]
                        break
                
                lw_match = re.search(r'LW:\s*(\d+)', item_text, re.I)
                peak_match = re.search(r'Peak:\s*(\d+)', item_text, re.I)
                weeks_match = re.search(r'Weeks:\s*(\d+)', item_text, re.I)
                
                if lw_match and lw_match.group(1) != 'none':
                    lw = int(lw_match.group(1))
                if peak_match:
                    peak = int(peak_match.group(1))
                if weeks_match:
                    weeks = int(weeks_match.group(1))
                
                if title and artist and rank <= 50:
                    movement = "same"
                    if lw:
                        if lw > rank:
                            movement = "up"
                        elif lw < rank:
                            movement = "down"
                    else:
                        movement = "new"
                    
                    entries.append({
                        "position": rank,
                        "track": {"title": title, "artist": artist, "artwork": ""},
                        "previousPosition": lw,
                        "movement": movement,
                        "weeksOnChart": weeks if weeks else 1,
                        "peakPosition": peak if peak else rank,
                        "source": "official_charts"
                    })
        
        return entries[:50]
    
    except Exception as e:
        print(f"    ❌ Erreur Official Charts UK: {e}")
        return []

def fetch_itunes_chart(country_code, limit=50):
    """Récupère le top singles via l'API iTunes RSS"""
    url = f"https://itunes.apple.com/{country_code}/rss/topsongs/limit={limit}/json"
    
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
                        "movement": "same",
                        "weeksOnChart": 1,
                        "peakPosition": index + 1,
                        "source": "itunes"
                    })
            except Exception as e:
                print(f"    ⚠️ Erreur lors du parsing de l'entrée {index}: {e}")
                continue
        
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur iTunes {country_code}: {e}")
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
    
    # Traiter chaque pays
    for code, country_info in SOURCES.items():
        print(f"\n📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        entries = []
        source_used = country_info["source"]
        
        if source_used == "billboard":
            entries = fetch_billboard_hot100()
        elif source_used == "official_charts":
            if code == "fr":
                entries = fetch_official_charts_france()
            elif code == "gb":
                entries = fetch_official_charts_uk()
        elif source_used == "itunes":
            entries = fetch_itunes_chart(country_info["itunes_code"])
        
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
    
    # Générer le message de note
    if successful_sources and failed_sources:
        charts_data["meta"]["sourceNote"] = (
            f"✅ Sources réussies : {', '.join(successful_sources)}. "
            f"❌ Sources échouées : {', '.join(failed_sources)}."
        )
    elif successful_sources:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources ont été collectées : {', '.join(successful_sources)}."
    else:
        charts_data["meta"]["sourceNote"] = "❌ Aucune source n'a pu être collectée."
    
    # Sauvegarder
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