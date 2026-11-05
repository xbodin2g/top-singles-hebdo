#!/usr/bin/env python3
"""
Script pour télécharger les archives du Top singles français depuis DEUX sources :
1. top-archives.fr (1984-1993) - archives complètes
2. chartsinfrance.net (1994-2026) - source officielle SNEP

Format d'URL chartsinfrance : https://www.chartsinfrance.net/charts/YYNN/singles.php
- YY = année sur 2 chiffres (ex: 95 = 1995, 07 = 2007, 25 = 2025)
- NN = numéro de semaine sur 2 chiffres (01-53)
- ?page=2, ?page=3, etc. pour la pagination
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

def year_to_yy(year):
    """Convertit une année complète en format 2 chiffres"""
    if year >= 2000:
        return str(year)[2:]  # 2025 -> 25, 2007 -> 07
    else:
        return str(year)[2:]  # 1995 -> 95, 1989 -> 89

def get_date_from_year_week(year, week):
    """Calcule la date approximative d'une semaine ISO"""
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    return start_of_week1 + timedelta(weeks=week-1)

# ===== SOURCE 1 : top-archives.fr (1984-1993) =====

def fetch_toparchives_week(year, week, cache):
    """Récupère depuis top-archives.fr"""
    cache_key = f"{year}-{week:02d}"
    
    if cache_key in cache:
        return True
    
    url = f"https://top-archives.fr/top/year/{year}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            return False
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        week_id = None
        for link in soup.find_all('a', href=re.compile(r'/top/week/\d+')):
            href = link.get('href', '')
            match = re.search(r'/top/week/(\d+)', href)
            
            if match:
                week_id = int(match.group(1))
                break
        
        if not week_id:
            return False
        
        url = f"https://top-archives.fr/top/week/{week_id}"
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = parse_toparchives_html(soup)
        
        if entries:
            date = get_date_from_year_week(year, week)
            
            archive_data = {
                "week": week,
                "year": year,
                "date": date.strftime('%d/%m/%Y'),
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

# ===== SOURCE 2 : chartsinfrance.net (1994-2026) =====

def fetch_chartsinfrance_week(year, week, cache):
    """
    Récupère depuis chartsinfrance.net avec gestion de la pagination
    Format URL : /charts/YYNN/singles.php?page=X
    """
    cache_key = f"{year}-{week:02d}"
    
    if cache_key in cache:
        return True
    
    yy = year_to_yy(year)
    nn = f"{week:02d}"
    
    print(f"  📥 chartsinfrance.net : {year} S{week:02d}...")
    
    all_entries = []
    page = 1
    max_pages = 5  # Limite de sécurité
    
    while page <= max_pages:
        url = f"https://www.chartsinfrance.net/charts/{yy}{nn}/singles.php"
        if page > 1:
            url += f"?page={page}"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            
            if response.status_code == 404:
                if page == 1:
                    print(f"    ❌ Semaine non trouvée (404)")
                    return False
                else:
                    break  # Plus de pages
            
            if "Aucun classement disponible" in response.text:
                if page == 1:
                    print(f"    ❌ Aucune donnée disponible")
                    return False
                else:
                    break
            
            response.raise_for_status()
            
            entries = parse_chartsinfrance_html(response.text)
            
            if not entries:
                break  # Plus d'entrées sur cette page
            
            all_entries.extend(entries)
            
            # Vérifier s'il y a une page suivante
            if not has_next_page(response.text):
                break
            
            page += 1
            time.sleep(0.5)
            
        except Exception as e:
            print(f"    ⚠️ Erreur page {page}: {e}")
            if page == 1:
                return False
            break
    
    if not all_entries:
        print(f"    ❌ Aucune entrée parsée")
        return False
    
    # Trier par position et dédoublonner
    all_entries.sort(key=lambda x: x["position"])
    
    seen = set()
    unique_entries = []
    for entry in all_entries:
        if entry["position"] not in seen:
            seen.add(entry["position"])
            unique_entries.append(entry)
    
    # Garder le top 100 max (ou plus si demandé)
    entries = unique_entries[:100]
    
    if entries:
        date = get_date_from_year_week(year, week)
        
        archive_data = {
            "week": week,
            "year": year,
            "date": date.strftime('%d/%m/%Y'),
            "entries": entries,
            "source": "chartsinfrance.net",
            "pages": page,
            "cached_at": datetime.now().strftime('%Y-%m-%d')
        }
        
        cache[cache_key] = archive_data
        print(f"  ✅ chartsinfrance.net : {len(entries)} entrées (sur {page} page(s))")
        time.sleep(1)
        return True
    
    return False

def parse_chartsinfrance_html(html_text):
    """Parse le HTML de chartsinfrance.net"""
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Méthode 1 : Chercher les éléments de classement avec une structure plus robuste
    # Le site utilise des divs avec des classes spécifiques
    
    # Chercher tous les éléments qui contiennent un numéro de position
    # Pattern : position, puis titre (h2 ou div), puis artiste
    
    # Stratégie : parser le texte brut ligne par ligne avec un pattern amélioré
    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Chercher une position (nombre seul ou avec étoile)
        pos_match = re.match(r'^[\*_]?\s*(\d{1,3})\s*$', line)
        
        if pos_match:
            position = int(pos_match.group(1))
            
            if position <= 100:
                title = ""
                artist = ""
                movement = "same"
                previous_pos = None
                
                # Chercher titre et artiste dans les lignes suivantes
                for j in range(i+1, min(i+8, len(lines))):
                    next_line = lines[j]
                    
                    # Ignorer les lignes de navigation/UI
                    if next_line.startswith('_') or next_line.startswith('arrow') or next_line.startswith('timeline'):
                        continue
                    
                    # Ignorer les lignes très courtes ou avec des symboles spéciaux
                    if len(next_line) < 2:
                        continue
                    
                    # Détecter le mouvement
                    if 'arrow_top' in next_line or next_line.startswith('↑'):
                        movement = "up"
                        num_match = re.search(r'(\d+)', next_line)
                        if num_match:
                            previous_pos = position + int(num_match.group(1))
                        continue
                    elif 'arrow_bot' in next_line or next_line.startswith('↓'):
                        movement = "down"
                        num_match = re.search(r'(\d+)', next_line)
                        if num_match:
                            previous_pos = position - int(num_match.group(1))
                        continue
                    elif 'New' in next_line or 'new' in next_line.lower():
                        movement = "new"
                        continue
                    elif 'arrow_right' in next_line or next_line.startswith('→'):
                        movement = "same"
                        previous_pos = position
                        continue
                    
                    # Si on a déjà titre et artiste, on arrête
                    if title and artist:
                        break
                    
                    # Première ligne significative = titre
                    if not title and len(next_line) > 2:
                        title = next_line
                    # Deuxième ligne significative = artiste
                    elif not artist and len(next_line) > 2:
                        artist = next_line
                
                if title and artist:
                    if previous_pos is None and movement != "new":
                        previous_pos = position
                    
                    entries.append({
                        "position": position,
                        "track": {"title": title, "artist": artist},
                        "previousPosition": previous_pos,
                        "movement": movement,
                        "weeksOnChart": 1,
                        "peakPosition": position,
                        "source": "chartsinfrance"
                    })
        
        i += 1
    
    # Méthode alternative : chercher directement dans le HTML structuré
    if len(entries) < 10:
        entries = []
        
        # Chercher les blocs de classement
        # Pattern typique : <div class="..."> avec position, titre h2, artiste
        
        for elem in soup.find_all(['div', 'article', 'li']):
            elem_text = elem.get_text(separator='|', strip=True)
            
            # Chercher un pattern : position | titre | artiste
            match = re.search(r'(\d{1,2})\s*\|\s*(.+?)\s*\|\s*([^\|]+?)(?:\s*\||$)', elem_text)
            
            if match:
                position = int(match.group(1))
                title = match.group(2).strip()
                artist = match.group(3).strip()
                
                if position <= 100 and len(title) > 2 and len(artist) > 2:
                    entries.append({
                        "position": position,
                        "track": {"title": title, "artist": artist},
                        "previousPosition": None,
                        "movement": "same",
                        "weeksOnChart": 1,
                        "peakPosition": position,
                        "source": "chartsinfrance"
                    })
    
    return entries

def has_next_page(html_text):
    """Vérifie s'il y a une page suivante"""
    # Chercher des indicateurs de pagination
    if '?page=' in html_text:
        # Chercher "page suivante" ou numéro de page + 1
        if 'Suivant' in html_text or 'Next' in html_text or 'arrow_right' in html_text:
            return True
    return False

# ===== FONCTION PRINCIPALE =====

def main():
    parser = argparse.ArgumentParser(description='Télécharge les archives Top singles depuis 2 sources')
    parser.add_argument('--year', type=int, required=True, help='Année (1984-2026)')
    parser.add_argument('--weeks', type=str, default='1-53', help='Semaines (ex: 1-52)')
    
    args = parser.parse_args()
    
    year = args.year
    current_year = datetime.now().year
    
    if year < 1984 or year > current_year:
        print(f"❌ Année invalide (1984-{current_year})")
        sys.exit(1)
    
    print(f"📅 Archives Top singles France - Année {year}")
    
    if year <= 1993:
        print(f"   Source principale : top-archives.fr (1984-1993)")
    else:
        print(f"   Source principale : chartsinfrance.net (format YYNN)")
    
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
    skip = 0
    
    for week in weeks:
        cache_key = f"{year}-{week:02d}"
        
        if cache_key in cache:
            print(f"  ⏭️  Semaine {week:02d}/{year} : déjà en cache")
            skip += 1
            continue
        
        print(f"\n📥 Semaine {week:02d}/{year}...")
        
        # Stratégie selon l'année
        if year <= 1993:
            # 1984-1993 : top-archives.fr en priorité
            result = fetch_toparchives_week(year, week, cache)
        else:
            # 1994+ : chartsinfrance.net
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
    print(f"   - {skip} déjà en cache")
    print(f"   - {fail} échecs")
    print(f"   - Total en cache : {len(cache)} archives")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()