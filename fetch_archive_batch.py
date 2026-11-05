#!/usr/bin/env python3
"""
Script pour télécharger les archives du Top singles français depuis TROIS sources :
1. top-archives.fr (1984-1993) - archives complètes
2. chartsinfrance.net (1994-2014 S15) - format YYNN
3. snepmusique.com (2014 S16 - aujourd'hui) - SOURCE OFFICIELLE SNEP

Stratégie :
- 1984-1993 : top-archives.fr
- 1994-2014 S15 : chartsinfrance.net
- 2014 S16+ : snepmusique.com (officiel, données complètes avec labels)
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

# Point de transition : SNEP commence à la semaine 16 de 2014
SNEP_START_YEAR = 2014
SNEP_START_WEEK = 16

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
    return str(year)[2:]

def get_date_from_year_week(year, week):
    """Calcule la date approximative d'une semaine ISO"""
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    return start_of_week1 + timedelta(weeks=week-1)

def use_snep(year, week):
    """Détermine si on doit utiliser SNEP pour cette semaine"""
    if year > SNEP_START_YEAR:
        return True
    elif year == SNEP_START_YEAR and week >= SNEP_START_WEEK:
        return True
    return False

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

# ===== SOURCE 2 : chartsinfrance.net (1994-2014 S15) =====

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
    max_pages = 5
    
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
                    break
            
            if "Aucun classement disponible" in response.text:
                if page == 1:
                    print(f"    ❌ Aucune donnée disponible")
                    return False
                else:
                    break
            
            response.raise_for_status()
            
            entries = parse_chartsinfrance_html(response.text)
            
            if not entries:
                break
            
            all_entries.extend(entries)
            
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
    
    all_entries.sort(key=lambda x: x["position"])
    
    seen = set()
    unique_entries = []
    for entry in all_entries:
        if entry["position"] not in seen:
            seen.add(entry["position"])
            unique_entries.append(entry)
    
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
    """Parse le HTML de chartsinfrance.net avec extraction robuste des mouvements"""
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')
    
    titles = soup.find_all('h2')
    
    for title_elem in titles:
        try:
            parent = title_elem.parent
            while parent and parent.name not in ['div', 'article', 'li', 'tr']:
                parent = parent.parent
            
            if not parent:
                continue
            
            full_text = parent.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in full_text.split('\n') if l.strip()]
            
            if len(lines) < 3:
                continue
            
            pos_match = re.match(r'^[\*_]?\s*(\d{1,3})\s*$', lines[0])
            if not pos_match:
                continue
            
            position = int(pos_match.group(1))
            if position > 100:
                continue
            
            title = title_elem.get_text(strip=True)
            if not title or len(title) < 2:
                continue
            
            artist = ""
            movement_keywords = ['arrow_top', 'arrow_bot', 'arrow_right', 'timeline', 'New', 'star', 'Voir']
            
            for line in lines[2:]:
                if not line or len(line) < 2:
                    continue
                if any(kw in line for kw in movement_keywords):
                    continue
                if line.startswith('_') or line.startswith('↑') or line.startswith('↓') or line.startswith('→'):
                    continue
                artist = line
                break
            
            if not artist:
                continue
            
            movement = "same"
            previous_pos = None
            
            full_parent_text = ' '.join(lines)
            
            up_match = re.search(r'arrow_top[_\s]*(\d+)|↑\s*(\d+)', full_parent_text)
            if up_match:
                movement = "up"
                diff = int(up_match.group(1) or up_match.group(2))
                previous_pos = position + diff
                entries.append({
                    "position": position,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": previous_pos,
                    "movement": movement,
                    "weeksOnChart": 1,
                    "peakPosition": position,
                    "source": "chartsinfrance"
                })
                continue
            
            down_match = re.search(r'arrow_bot[_\s]*(\d+)|↓\s*(\d+)', full_parent_text)
            if down_match:
                movement = "down"
                diff = int(down_match.group(1) or down_match.group(2))
                previous_pos = position - diff
                entries.append({
                    "position": position,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": previous_pos,
                    "movement": movement,
                    "weeksOnChart": 1,
                    "peakPosition": position,
                    "source": "chartsinfrance"
                })
                continue
            
            if 'New' in full_parent_text or 'new' in full_parent_text.lower():
                movement = "new"
                previous_pos = None
                entries.append({
                    "position": position,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": None,
                    "movement": "new",
                    "weeksOnChart": 1,
                    "peakPosition": position,
                    "source": "chartsinfrance"
                })
                continue
            
            if 'arrow_right' in full_parent_text or '→' in full_parent_text:
                movement = "same"
                previous_pos = position
                entries.append({
                    "position": position,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": previous_pos,
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": position,
                    "source": "chartsinfrance"
                })
                continue
            
            previous_pos = position
            entries.append({
                "position": position,
                "track": {"title": title, "artist": artist},
                "previousPosition": previous_pos,
                "movement": "same",
                "weeksOnChart": 1,
                "peakPosition": position,
                "source": "chartsinfrance"
            })
        
        except Exception as e:
            continue
    
    seen = set()
    unique_entries = []
    for entry in entries:
        if entry["position"] not in seen:
            seen.add(entry["position"])
            unique_entries.append(entry)
    
    return sorted(unique_entries, key=lambda x: x["position"])

def has_next_page(html_text):
    """Vérifie s'il y a une page suivante"""
    if '?page=' in html_text:
        if 'Suivant' in html_text or 'Next' in html_text or 'arrow_right' in html_text:
            return True
    return False

# ===== SOURCE 3 : snepmusique.com (2014 S16 - aujourd'hui) =====

def fetch_snep_week(year, week, cache):
    """
    Récupère depuis snepmusique.com (SOURCE OFFICIELLE SNEP)
    Format URL : /classement-radio/?annee=YYYY&semaine=WW
    """
    cache_key = f"{year}-{week:02d}"
    
    if cache_key in cache:
        return True
    
    print(f"  📥 snepmusique.com (SNEP) : {year} S{week:02d}...")
    
    # Construire l'URL
    if year == datetime.now().year and week == datetime.now().isocalendar()[1]:
        # Semaine en cours
        url = "https://snepmusique.com/classement-radio/"
    else:
        url = f"https://snepmusique.com/classement-radio/?annee={year}&semaine={week}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Semaine non trouvée (404)")
            return False
        
        response.raise_for_status()
        
        # Vérifier si la page contient des données
        if "Aucun classement" in response.text or len(response.text) < 1000:
            print(f"    ❌ Aucune donnée disponible")
            return False
        
        entries = parse_snep_html(response.text)
        
        if not entries:
            print(f"    ❌ Aucune entrée parsée")
            return False
        
        # Trier par position
        entries.sort(key=lambda x: x["position"])
        
        # Dédupliquer
        seen = set()
        unique_entries = []
        for entry in entries:
            if entry["position"] not in seen:
                seen.add(entry["position"])
                unique_entries.append(entry)
        
        entries = unique_entries[:200]  # SNEP peut avoir plus de 100 entrées
        
        if entries:
            date = get_date_from_year_week(year, week)
            
            archive_data = {
                "week": week,
                "year": year,
                "date": date.strftime('%d/%m/%Y'),
                "entries": entries,
                "source": "snepmusique.com",
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = archive_data
            print(f"  ✅ SNEP : {len(entries)} entrées (source officielle)")
            
            # Afficher quelques stats
            new_count = sum(1 for e in entries if e.get('movement') == 'new')
            up_count = sum(1 for e in entries if e.get('movement') == 'up')
            down_count = sum(1 for e in entries if e.get('movement') == 'down')
            print(f"     📊 {new_count} nouvelles, {up_count} ▲, {down_count} ▼")
            
            time.sleep(1)
            return True
    
    except Exception as e:
        print(f"    ❌ Erreur SNEP: {e}")
    
    return False

def parse_snep_html(html_text):
    """
    Parse le HTML de snepmusique.com
    Structure détectée :
    - Position (chiffre)
    - Titre
    - Artiste
    - Label
    - Position précédente (**Xer** La Semaine Dernière)
    - Semaines dans le Top (**Xer** Semaine dans le Top)
    """
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Chercher tous les éléments de classement
    # Le site utilise une structure simple avec des divs ou des sections
    
    # Méthode 1 : Parser le texte brut avec regex
    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Chercher une position (nombre seul)
        pos_match = re.match(r'^(\d{1,3})$', line)
        
        if pos_match:
            position = int(pos_match.group(1))
            
            if position <= 200:  # SNEP peut avoir jusqu'à 200 entrées
                title = ""
                artist = ""
                label = ""
                previous_pos = None
                movement = "same"
                weeks_on_chart = 1
                
                # Chercher titre, artiste, label dans les lignes suivantes
                j = i + 1
                line_count = 0
                
                while j < len(lines) and line_count < 10:
                    next_line = lines[j].strip()
                    
                    # Ignorer les lignes vides ou de navigation
                    if not next_line or len(next_line) < 2:
                        j += 1
                        continue
                    
                    # Détecter les mots-clés de mouvement/position
                    if 'La Semaine Dernière' in next_line:
                        # Extraire la position précédente
                        prev_match = re.search(r'\*\*(\d+)(?:er|e|ème)?\*\*.*La Semaine Dernière', next_line)
                        if prev_match:
                            previous_pos = int(prev_match.group(1))
                            if previous_pos > position:
                                movement = "up"
                            elif previous_pos < position:
                                movement = "down"
                            else:
                                movement = "same"
                        j += 1
                        continue
                    
                    if 'Semaine dans le Top' in next_line:
                        # Extraire le nombre de semaines
                        weeks_match = re.search(r'\*\*(\d+)(?:er|e|ème)?\*\*.*Semaine dans le Top', next_line)
                        if weeks_match:
                            weeks_on_chart = int(weeks_match.group(1))
                        
                        # Détecter nouvelle entrée
                        if '1er' in next_line and 'Semaine dans le Top' in next_line:
                            movement = "new"
                            previous_pos = None
                        
                        j += 1
                        continue
                    
                    # Ignorer les labels connus (à adapter selon besoin)
                    known_labels = ['SONY MUSIC', 'UNIVERSAL', 'WARNER MUSIC', 'BELIEVE', 
                                   'WAGRAM', 'IDOL', 'SCORPIO', 'HAPPY MUSIC', 'THIRTY KNOTS',
                                   'NOJOKE RECORDS', 'AWAL', 'EMPIRE', 'BECAUSE MUSIC',
                                   'LEVEL UP MUSIC', 'YPDP', 'ARGENTIC MUSIC', 'STMPD RCRDS',
                                   'FIDEL', 'TRINITY', 'LORE', 'THE ORCHARD']
                    
                    if next_line in known_labels or any(lbl in next_line for lbl in known_labels):
                        label = next_line
                        j += 1
                        continue
                    
                    # Première ligne significative = titre
                    if not title and len(next_line) > 2:
                        title = next_line
                    # Deuxième ligne significative = artiste
                    elif not artist and len(next_line) > 2:
                        artist = next_line
                        break  # On a titre et artiste, on arrête
                    
                    j += 1
                    line_count += 1
                
                # Vérifier qu'on a bien titre et artiste
                if title and artist and len(title) > 2 and len(artist) > 2:
                    entries.append({
                        "position": position,
                        "track": {
                            "title": title,
                            "artist": artist
                        },
                        "label": label,
                        "previousPosition": previous_pos,
                        "movement": movement,
                        "weeksOnChart": weeks_on_chart,
                        "peakPosition": position,
                        "source": "snep"
                    })
        
        i += 1
    
    return entries

# ===== FONCTION PRINCIPALE =====

def main():
    parser = argparse.ArgumentParser(description='Télécharge les archives Top singles depuis 3 sources')
    parser.add_argument('--year', type=int, required=True, help='Année (1984-2026)')
    parser.add_argument('--weeks', type=str, default='1-53', help='Semaines (ex: 1-52)')
    
    args = parser.parse_args()
    
    year = args.year
    current_year = datetime.now().year
    
    if year < 1984 or year > current_year:
        print(f"❌ Année invalide (1984-{current_year})")
        sys.exit(1)
    
    print(f"📅 Archives Top singles France - Année {year}")
    
    # Déterminer la source selon l'année
    if year <= 1993:
        print(f"   Source : top-archives.fr (1984-1993)")
    elif year < SNEP_START_YEAR or (year == SNEP_START_YEAR):
        if year < SNEP_START_YEAR:
            print(f"   Source : chartsinfrance.net (1994-2013)")
        else:
            print(f"   Source : chartsinfrance.net (S01-S15) + SNEP (S16+)")
    else:
        print(f"   Source : snepmusique.com (SOURCE OFFICIELLE SNEP)")
    
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
        
        # Stratégie selon l'année et la semaine
        if year <= 1993:
            # 1984-1993 : top-archives.fr
            result = fetch_toparchives_week(year, week, cache)
        
        elif year < SNEP_START_YEAR:
            # 1994-2013 : chartsinfrance.net
            result = fetch_chartsinfrance_week(year, week, cache)
        
        elif year == SNEP_START_YEAR:
            # 2014 : chartsinfrance pour S01-S15, SNEP pour S16+
            if week < SNEP_START_WEEK:
                result = fetch_chartsinfrance_week(year, week, cache)
            else:
                result = fetch_snep_week(year, week, cache)
        
        else:
            # 2015+ : SNEP uniquement
            result = fetch_snep_week(year, week, cache)
        
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