#!/usr/bin/env python3
"""
Scraper pour chartsinfrance.net
Source officielle SNEP/SCPP pour les tops français.

Utilisation :
    python fetch_chartsinfrance.py --week 8645
    python fetch_chartsinfrance.py --year 1989 --weeks 1-52
    python fetch_chartsinfrance.py --latest
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import os
import argparse
import sys
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}

CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "chartsinfrance.json")

# Point de référence : 8645 = Semaine du 6 novembre 1986
REF_WEEK = 8645
REF_DATE = datetime(1986, 11, 6)

def load_cache():
    """Charge le cache chartsinfrance"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur chargement cache: {e}")
    return {}

def save_cache(cache):
    """Sauvegarde le cache"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} semaines")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde: {e}")

def week_number_to_date(week_num):
    """Convertit un numéro de semaine en date"""
    delta_weeks = week_num - REF_WEEK
    target_date = REF_DATE + timedelta(weeks=delta_weeks)
    return target_date

def date_to_week_number(target_date):
    """Convertit une date en numéro de semaine"""
    delta_days = (target_date - REF_DATE).days
    delta_weeks = delta_days // 7
    return REF_WEEK + delta_weeks

def fetch_chartsinfrance_week(week_num, cache=None):
    """Récupère le top singles pour un numéro de semaine donné"""
    if cache is None:
        cache = {}
    
    cache_key = str(week_num)
    
    # Vérifier le cache
    if cache_key in cache:
        print(f"  ✅ Semaine {week_num} : déjà en cache")
        return cache[cache_key]
    
    url = f"https://www.chartsinfrance.net/charts/{week_num}/singles.php"
    
    print(f"  📥 Semaine {week_num} ({week_number_to_date(week_num).strftime('%Y-%m-%d')})...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Page non trouvée (404)")
            return None
        
        response.raise_for_status()
        
        # Vérifier si des données sont disponibles
        if "Aucun classement disponible" in response.text:
            print(f"    ❌ Aucune donnée disponible")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Parser le classement
        # Le site utilise une structure spécifique avec des divs
        chart_container = soup.find('div', class_=re.compile(r'chart|top', re.I))
        
        if not chart_container:
            # Fallback : chercher toutes les lignes
            chart_container = soup
        
        # Chercher les éléments de classement
        rows = chart_container.find_all(['div', 'article'], recursive=True)
        
        current_position = 0
        
        for row in rows:
            text = row.get_text(separator='|', strip=True)
            
            # Chercher un pattern de position (1, 2, 3, etc.)
            pos_match = re.search(r'\b(\d{1,2})\b.*?##\s*(.*?)\|', text)
            
            if pos_match and int(pos_match.group(1)) <= 50:
                position = int(pos_match.group(1))
                title = pos_match.group(2).strip()
                
                # Chercher l'artiste (après le titre)
                artist_match = re.search(r'##.*?\|.*?\|.*?\|\s*(.*?)\s*(?:arrow|New)', text)
                if artist_match:
                    artist = artist_match.group(1).strip()
                    
                    if title and artist and position <= 50:
                        # Déterminer le mouvement
                        movement = "same"
                        if 'arrow_top' in text or '▲' in text:
                            movement = "up"
                        elif 'arrow_bot' in text or '▼' in text:
                            movement = "down"
                        elif 'New' in text or 'new' in text.lower():
                            movement = "new"
                        
                        entries.append({
                            "position": position,
                            "track": {
                                "title": title,
                                "artist": artist
                            },
                            "movement": movement,
                            "weeksOnChart": 1,
                            "peakPosition": position,
                            "source": "chartsinfrance"
                        })
        
        # Stratégie alternative : parser ligne par ligne
        if len(entries) < 10:
            entries = []
            lines = response.text.split('\n')
            
            for i, line in enumerate(lines):
                # Chercher les positions
                if re.search(r'^\d{1,2}$', line.strip()):
                    position = int(line.strip())
                    
                    if position <= 50:
                        # Les 2-3 lignes suivantes contiennent titre et artiste
                        title = ""
                        artist = ""
                        
                        for j in range(i+1, min(i+5, len(lines))):
                            next_line = lines[j].strip()
                            
                            if next_line and not next_line.startswith('_') and len(next_line) > 3:
                                if not title:
                                    title = next_line
                                elif not artist:
                                    artist = next_line
                                    break
                        
                        if title and artist:
                            movement = "same"
                            
                            # Chercher le mouvement dans les lignes suivantes
                            for j in range(i+1, min(i+10, len(lines))):
                                if 'arrow_top' in lines[j] or '▲' in lines[j]:
                                    movement = "up"
                                    break
                                elif 'arrow_bot' in lines[j] or '▼' in lines[j]:
                                    movement = "down"
                                    break
                                elif 'New' in lines[j]:
                                    movement = "new"
                                    break
                            
                            entries.append({
                                "position": position,
                                "track": {
                                    "title": title,
                                    "artist": artist
                                },
                                "movement": movement,
                                "weeksOnChart": 1,
                                "peakPosition": position,
                                "source": "chartsinfrance"
                            })
        
        if entries:
            entries.sort(key=lambda x: x["position"])
            
            # Dédupliquer
            seen = set()
            unique_entries = []
            for entry in entries:
                if entry["position"] not in seen:
                    seen.add(entry["position"])
                    unique_entries.append(entry)
            
            entries = unique_entries[:50]
            
            date = week_number_to_date(week_num)
            
            week_data = {
                "week": week_num,
                "date": date.strftime('%Y-%m-%d'),
                "entries": entries,
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = week_data
            
            print(f"    ✅ {len(entries)} entrées trouvées")
            
            # Afficher le top 3
            if entries:
                print(f"    📊 Top 3 :")
                for entry in entries[:3]:
                    print(f"       {entry['position']}. {entry['track']['artist']} - {entry['track']['title']}")
            
            time.sleep(1)
            
            return week_data
        else:
            print(f"    ❌ Aucune entrée parsée")
            return None
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return None

def fetch_latest_week(cache=None):
    """Récupère la dernière semaine disponible (celle en cours)"""
    if cache is None:
        cache = {}
    
    # Calculer le numéro de semaine pour aujourd'hui
    today = datetime.now()
    week_num = date_to_week_number(today)
    
    # Essayer cette semaine et les précédentes
    for offset in range(0, 5):
        test_week = week_num - offset
        result = fetch_chartsinfrance_week(test_week, cache)
        
        if result:
            return result
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Scraper chartsinfrance.net')
    parser.add_argument('--week', type=int, help='Numéro de semaine spécifique')
    parser.add_argument('--year', type=int, help='Année (pour télécharger toute une année)')
    parser.add_argument('--weeks', type=str, help='Plage de semaines (ex: 1-52)')
    parser.add_argument('--latest', action='store_true', help='Récupérer la dernière semaine')
    
    args = parser.parse_args()
    
    cache = load_cache()
    
    if args.latest:
        print(f"📅 Récupération de la dernière semaine...")
        result = fetch_latest_week(cache)
        
        if result:
            save_cache(cache)
            print(f"\n✅ Dernière semaine récupérée : {result['date']}")
        else:
            print(f"\n❌ Échec")
        
    elif args.week:
        print(f"📅 Semaine {args.week} ({week_number_to_date(args.week).strftime('%Y-%m-%d')})...")
        result = fetch_chartsinfrance_week(args.week, cache)
        
        if result:
            save_cache(cache)
            print(f"\n✅ Semaine récupérée")
        else:
            print(f"\n❌ Échec")
    
    elif args.year:
        print(f"📅 Année {args.year}...")
        
        # Calculer les numéros de semaine pour l'année
        start_date = datetime(args.year, 1, 1)
        end_date = datetime(args.year, 12, 31)
        
        start_week = date_to_week_number(start_date)
        end_week = date_to_week_number(end_date)
        
        if args.weeks:
            # Parse la plage
            if '-' in args.weeks:
                start, end = map(int, args.weeks.split('-'))
                start_week = start
                end_week = end
        
        print(f"   Semaines {start_week} à {end_week}")
        
        success = 0
        fail = 0
        
        for week_num in range(start_week, end_week + 1):
            result = fetch_chartsinfrance_week(week_num, cache)
            
            if result:
                success += 1
            else:
                fail += 1
            
            # Sauvegarder toutes les 10 semaines
            if (success + fail) % 10 == 0 and success > 0:
                save_cache(cache)
                print(f"\n  💾 Cache sauvegardé ({len(cache)} semaines)\n")
        
        save_cache(cache)
        
        print(f"\n{'='*60}")
        print(f"✅ Année {args.year} terminée")
        print(f"   - {success} semaines récupérées")
        print(f"   - {fail} échecs")
        print(f"   - Total en cache : {len(cache)} semaines")
        print(f"{'='*60}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()