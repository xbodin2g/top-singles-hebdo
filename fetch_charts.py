#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version avec fallback pour garantir que l'application fonctionne.
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

# Configuration des sources
SOURCES = {
    "uk": {"name": "Royaume-Uni", "flag": "🇬🇧", "url": "https://www.officialcharts.com/charts/singles-chart/", "region": "europe"},
    "de": {"name": "Allemagne", "flag": "🇩🇪", "url": "https://www.offiziellecharts.de/charts", "region": "europe"},
    "ch": {"name": "Suisse", "flag": "🇨🇭", "url": "https://www.hitparade.ch/charts/singles", "region": "europe"},
    "us": {"name": "États-Unis", "flag": "🇺🇸", "url": "https://www.billboard.com/charts/hot-100/", "region": "anglo"},
    "fr": {"name": "France", "flag": "🇫🇷", "url": "https://snepmusique.com/les-tops/le-top-de-la-semaine/top-singles/", "region": "europe"},
    "br": {"name": "Brésil", "flag": "🇧🇷", "url": "https://pro-musicabr.org.br/home/top-50-streaming/", "region": "latam"}
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

def fetch_with_retry(url, max_retries=2):
    """Fetch avec retry en cas d'erreur"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"  Tentative {attempt + 1} échouée: {str(e)[:100]}")
            if attempt == max_retries - 1:
                return None

def scrape_brazil_promusica():
    """Scrape Pro-Música Brasil - FONCTIONNE PARFAITEMENT"""
    try:
        response = fetch_with_retry(SOURCES["br"]["url"])
        if not response:
            return []
        
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
                                        "peakPosition": rank
                                    })
        
        return entries[:50]
    except Exception as e:
        print(f"  ❌ Erreur Brésil: {e}")
        return []

def generate_demo_data(country_code, count=20):
    """Génère des données de démonstration réalistes"""
    demo_titles = {
        "uk": ["Babydoll", "Housewife", "Stop The Wedding", "Expectations", "Great Expectation", 
               "Night Drive", "Golden Hour", "Silver Lining", "Wildfire", "Dancing Alone"],
        "de": ["Housewife", "Dai Dai", "Ain't In LA", "Self Aware", "Movin' To The Sun",
               "Mr. Brightside", "Patient Zero", "Mi chico", "Mama (Remix)", "Stop The Wedding"],
        "ch": ["Housewife", "Bby Wow", "Dai Dai", "Mi chico", "Nicole Kidman",
               "Lumière", "Midnight Gold", "Baila Conmigo", "Évidence", "Golden Hour"],
        "us": ["Choosin' Texas", "Housewife", "Expectations", "Die With A Smile", "Birds Of A Feather",
               "APT.", "Luther", "Timeless", "Sailor Song", "Taste"],
        "fr": ["Maladie", "Sexy Nana", "Dai Dai", "Pilé", "Sicario",
               "Pocahontas", "Melodrama", "Bande organisée", "Je te promets", "Dernière danse"]
    }
    
    demo_artists = {
        "uk": ["Jamie Miller", "Tate McRae", "Ashe", "Olivia Rodrigo", "Sienna Spiro",
               "Kai Rivers", "Aurora West", "Noor", "J.B. Monroe", "Mavie"],
        "de": ["Tate McRae", "Shakira", "Adéla", "Temper City", "Hugel",
               "The Killers", "Taylor Swift", "DJ Goja", "Symba", "Ashe"],
        "ch": ["Tate McRae", "Karol G", "Shakira", "DJ Goja", "Adéla",
               "Alya Nova", "The Amber Lines", "Luz Marina", "Léa Volney", "Aurora West"],
        "us": ["Ella Langley", "Tate McRae", "Olivia Rodrigo", "Lady Gaga", "Billie Eilish",
               "Rosé", "SZA", "The Weeknd", "Gigi Perez", "Sabrina Carpenter"],
        "fr": ["Mauvais Djo", "Aya Nakamura", "Shakira", "Mauvais Djo", "Timal",
               "PLK", "Theodora", "SCH", "Johnny Hallyday", "Indila"]
    }
    
    entries = []
    titles = demo_titles.get(country_code, demo_titles["uk"])
    artists = demo_artists.get(country_code, demo_artists["uk"])
    
    for i in range(min(count, len(titles))):
        entries.append({
            "position": i + 1,
            "track": {
                "title": titles[i],
                "artist": artists[i]
            },
            "previousPosition": None if i == 0 else i + 2,
            "movement": "same" if i == 0 else "up" if i % 3 == 0 else "down",
            "weeksOnChart": 1 if i == 0 else (i % 10) + 1,
            "peakPosition": max(1, i + 1 - (i % 5))
        })
    
    return entries

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
            "sourceNote": "",
            "successfulSources": [],
            "failedSources": []
        },
        "countries": {},
        "regions": {
            "europe": {"label": "Europe", "countries": []},
            "anglo": {"label": "Pays anglo-saxons", "countries": []},
            "latam": {"label": "Amérique du Sud", "countries": []}
        }
    }
    
    # Configurer les scrapers
    scrapers = {
        "br": scrape_brazil_promusica  # Le seul qui fonctionne bien pour l'instant
    }
    
    # Traiter chaque source
    for code, country_info in SOURCES.items():
        print(f"📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        # Essayer de scraper si un scraper existe
        if code in scrapers:
            entries = scrapers[code]()
            is_demo = False
        else:
            entries = []
            is_demo = True
        
        # Si pas de données ou données insuffisantes, utiliser le fallback
        if not entries or len(entries) < 5:
            print(f"  ⚠️ Données insuffisantes ou scraping échoué, utilisation du fallback")
            entries = generate_demo_data(code, count=20)
            is_demo = True
            charts_data["meta"]["failedSources"].append(country_info["name"])
        else:
            print(f"  ✅ {len(entries)} entrées collectées")
            charts_data["meta"]["successfulSources"].append(country_info["name"])
        
        # Ajouter aux données
        charts_data["countries"][code] = {
            "name": country_info["name"],
            "flag": country_info["flag"],
            "region": country_info["region"],
            "chart": entries,
            "isDemo": is_demo
        }
        
        # Ajouter à la région
        charts_data["regions"][country_info["region"]]["countries"].append(code)
        print()
    
    # Générer le message de note
    successful = charts_data["meta"]["successfulSources"]
    failed = charts_data["meta"]["failedSources"]
    
    if successful and failed:
        charts_data["meta"]["sourceNote"] = (
            f"✅ Sources officielles : {', '.join(successful)}. "
            f"⚠️ Données de démonstration : {', '.join(failed)}."
        )
    elif successful:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources officielles ont été collectées : {', '.join(successful)}."
    else:
        charts_data["meta"]["sourceNote"] = "⚠️ Toutes les sources utilisent des données de démonstration."
    
    # Sauvegarder
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Collecte terminée")
    print(f"   - {len(successful)} sources officielles réussies")
    print(f"   - {len(failed)} sources avec données de démonstration")

if __name__ == "__main__":
    main()