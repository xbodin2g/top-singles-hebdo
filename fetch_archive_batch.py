#!/usr/bin/env python3
"""
Script pour télécharger les archives du Top 50 français depuis DEUX sources :
1. top-archives.fr (1984-1993) - archives complètes
2. chartsinfrance.net (1985-2026) - données officielles SNEP

Stratégie :
- 1984-1993 : Priorité à top-archives.fr (plus complet)
- 1994-2026 : Utiliser chartsinfrance.net uniquement
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
CACHE_RETRO_FILE = os.path.join(CACHE_DIR, "retro_archives.json")

# Configuration chartsinfrance
CIF_REF_WEEK = 8645
CIF_REF_DATE = datetime(1986, 11, 6)

def load_retro_cache():
    if os.path.exists(CACHE_RETRO_FILE):
        try:
            with open(CACHE_RETRO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur chargement cache: {e}")
    return {}

def save_retro_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_RETRO_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} archives")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde: {e}")

def week_to_date(year, week):
    """Convertit numéro de semaine ISO en date"""
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    return start_of_week1 + timedelta(weeks=week-1)

def date_to_cif_week(target_date):
    """Convertit une date en numéro de semaine chartsinfrance"""
    delta_days = (target_date - CIF_REF_DATE).days
    delta_weeks = delta_days // 7
    return CIF_REF_WEEK + delta_weeks

# ===== SOURCE 1 : top-archives.fr (1984-1993) =====

def fetch_toparchives_week(year, week, cache):
    """Récupère depuis top-archives.fr"""
    cache_key = f"{year}-{week:02d}"
    
    if cache_key in cache:
        print(f"  ⏭️  top-archives.fr : déjà en cache")
        return True
    
    # Récupérer la liste des semaines pour l'année
    url = f"https://top-archives.fr/top/year/{year}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            return False
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Trouver le lien pour cette semaine
        week_id = None
        
        for link in soup.find_all('a', href=re.compile(r'/top/week/\d+')):
            href = link.get('href', '')
            link_text = link.get_text(strip=True)
            
            # Chercher le numéro de semaine dans le texte
            if f"Semaine {week}" in link_text or f"S{week}" in link_text:
                match = re.search(r'/top/week/(\d+)', href)
                if match:
                    week_id = int(match.group(1))
                    break
        
        if not week_id:
            print(f"  ❌ top-archives.fr : Semaine {week} non trouvée")
            return False
        
        # Récupérer les données
        url = f"https://top-archives.fr/top/week/{week_id}"
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = parse_toparchives_html(soup)
        
        if entries:
            date = week_to_date(year, week)
            
            archive_data = {
                "week": week,
                "year": year,
                "date": date.strftime('%Y-%m-%d'),
                "entries": entries,
                "source": "top-archives.fr",
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = archive_data
            print(f"  ✅ top-archives.fr : {len(entries)} entrées")
            time.sleep(2)
            return True
        
    except Exception as e:
        print(f"  ❌ top-archives.fr erreur: {e}")
    
    return False

def parse_toparchives_html(soup):
    """Parse le HTML de top-archives.fr"""
    entries = []
    
    table = soup.find('table')
    
    if table:
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) >= 2:
                rank_text = cells[0].get_text(strip=True)
                rank_match = re.search(r'\d+', rank_text)
                
                if rank_match:
                    rank = int(rank_match.group())
                    
                    if 1 <= rank <= 50:
                        # Extraire artiste et titre
                        links = cells[1].find_all('a')
                        
                        if len(links) >= 2:
                            artist = links[0].get_text(strip=True)
                            title = links[1].get_text(strip=True)
                        else:
                            text = cells[1].get_text(separator='|', strip=True)
                            parts = [p.strip() for p in text.split('|') if p.strip()]
                            artist = parts[0] if parts else ""
                            title = parts[1] if len(parts) > 1 else ""
                        
                        if artist and title:
                            entries.append({
                                "position": rank,
                                "track": {"title": title, "artist": artist},
                                "movement": "same",
                                "weeksOnChart": 1,
                                "peakPosition": rank
                            })
    
    return entries

# ===== SOURCE 2 : chartsinfrance.net (1985-2026) =====

def fetch_chartsinfrance_week(year, week, cache):
    """Récupère depuis chartsinfrance.net"""
    cache_key = f"{year}-{week:02d}"
    
    if cache_key in cache:
        print(f"  ⏭️  chartsinfrance.net : déjà en cache")
        return True
    
    # Calculer le numéro de semaine chartsinfrance
    date = week_to_date(year, week)
    cif_week = date_to_cif_week(date)
    
    url = f"https://www.chartsinfrance.net/charts/{cif_week}/singles.php"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"  ❌ chartsinfrance.net : Page non trouvée")
            return False
        
        response.raise_for_status()
        
        if "Aucun classement disponible" in response.text:
            print(f"  ❌ chartsinfrance.net : Aucune donnée")
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = parse_chartsinfrance_html(soup, response.text)
        
        if entries:
            archive_data = {
                "week": week,
                "year": year,
                "date": date.strftime('%Y-%m-%d'),
                "entries": entries,
                "source": "chartsinfrance.net",
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = archive_data
            print(f"  ✅ chartsinfrance.net : {len(entries)} entrées")
            time.sleep(1)
            return True
        
    except Exception as e:
        print(f"  ❌ chartsinfrance.net erreur: {e}")
    
    return False

def parse_chartsinfrance_html(soup, html_text):
    """Parse le HTML de chartsinfrance.net"""
    entries = []
    
    # Parser ligne par ligne
    lines = html_text.split('\n')
    
    for i, line in enumerate(lines):
        # Chercher les positions
        if re.search(r'^\s*\d{1,2}\s*$', line.strip()):
            position = int(line.strip())
            
            if position <= 50:
                title = ""
                artist = ""
                
                # Chercher titre et artiste dans les lignes suivantes
                for j in range(i+1, min(i+5, len(lines))):
                    next_line = lines[j].strip()
                    
                    if next_line and not next_line.startswith('_') and len(next_line) > 3:
                        if not title:
                            title = next_line
                        elif not artist:
                            artist = next_line
                            break
                
                if title and artist:
                    # Déterminer le mouvement
                    movement = "same"
                    
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
                        "track": {"title": title, "artist": artist},
                        "movement": movement,
                        "weeksOnChart": 1,
                        "peakPosition": position
                    })
    
    # Dédupliquer et trier
    seen = set()
    unique_entries = []
    for entry in entries:
        if entry["position"] not in seen:
            seen.add(entry["position"])
            unique_entries.append(entry)
    
    return sorted(unique_entries, key=lambda x: x["position"])[:50]

# ===== FONCTION PRINCIPALE =====

def main():
    parser = argparse.ArgumentParser(description='Télécharge les archives Top 50 depuis 2 sources')
    parser.add_argument('--year', type=int, required=True, help='Année (1984-2026)')
    parser.add_argument('--weeks', type=str, default='1-53', help='Semaines (ex: 1-52)')
    
    args = parser.parse_args()
    
    year = args.year
    
    if year < 1984 or year > datetime.now().year:
        print(f"❌ Année invalide (1984-{datetime.now().year})")
        sys.exit(1)
    
    print(f"📅 Archives Top 50 France - Année {year}")
    print(f"   Sources : top-archives.fr (1984-1993) + chartsinfrance.net (1985-2026)")
    print(f"{'='*60}\n")
    
    # Parser les semaines
    weeks = []
    if '-' in args.weeks:
        start, end = map(int, args.weeks.split('-'))
        weeks = list(range(start, end + 1))
    else:
        weeks = [int(args.weeks)]
    
    cache = load_retro_cache()
    
    success = 0
    fail = 0
    
    for week in weeks:
        cache_key = f"{year}-{week:02d}"
        
        if cache_key in cache:
            print(f"  ⏭️  Semaine {week}/{year} : déjà en cache")
            success += 1
            continue
        
        print(f"\n📥 Semaine {week}/{year}...")
        
        # Stratégie selon l'année
        if year <= 1993:
            # 1984-1993 : Essayer top-archives.fr d'abord
            result = fetch_toparchives_week(year, week, cache)
            
            if not result:
                # Fallback sur chartsinfrance.net
                print(f"  🔄 Essai chartsinfrance.net...")
                result = fetch_chartsinfrance_week(year, week, cache)
        else:
            # 1994+ : Utiliser chartsinfrance.net uniquement
            result = fetch_chartsinfrance_week(year, week, cache)
        
        if result:
            success += 1
        else:
            fail += 1
        
        # Sauvegarder toutes les 5 semaines
        if (success + fail) % 5 == 0 and success > 0:
            save_retro_cache(cache)
            print(f"\n  💾 Cache sauvegardé ({len(cache)} archives)\n")
    
    save_retro_cache(cache)
    
    print(f"\n{'='*60}")
    print(f"✅ Année {year} terminée")
    print(f"   - {success} semaines récupérées")
    print(f"   - {fail} échecs")
    print(f"   - Total en cache : {len(cache)} archives")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()