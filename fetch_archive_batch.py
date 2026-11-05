#!/usr/bin/env python3
"""
Script pour télécharger les archives du Top singles français depuis TROIS sources :
1. top-archives.fr (1984-1993) - archives complètes
2. chartsinfrance.net (1994-2026 avril) - format YYNN
3. snepmusique.com (2014 S16 - aujourd'hui) - SOURCE OFFICIELLE SNEP

Stratégie :
- 1984-1993 : top-archives.fr
- 1994-2026 : chartsinfrance.net (avec fallback SNEP)
- 2014 S16+ : SNEP en priorité (officiel, données complètes avec labels)
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

# ===== SOURCE 2 : chartsinfrance.net (1994-2026 avril) =====

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
    """
    Parse le HTML de chartsinfrance.net (VERSION FINALE CORRIGÉE)
    CORRIGÉ : Ne casse pas après artiste pour capturer le mouvement qui vient APRÈS
    """
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')
    
    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
     # DEBUG : Afficher les lignes 50-80 pour voir les données
    if not hasattr(parse_chartsinfrance_html, '_debug_done'):
        print("    🔍 DEBUG chartsinfrance - Lignes 50-80 (données de classement) :")
        for i, line in enumerate(lines[50:80], start=50):
            print(f"       [{i}] {line}")
        parse_chartsinfrance_html._debug_done = True
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Pattern : Position (avec ou sans _star_)
        pos_match = re.match(r'^(?:_star_\s*)?(\d{1,3})$', line)
        
        if not pos_match:
            pos_match = re.match(r'^(\d{1,3})\s*(?:##)?', line)
        
        if pos_match:
            position = int(pos_match.group(1))
            
            if position <= 100:
                title = ""
                artist = ""
                movement = "same"
                previous_pos = None
                
                # Scanner les 10 lignes suivantes (TOUTES, sans casser)
                for j in range(i + 1, min(i + 10, len(lines))):
                    next_line = lines[j].strip()
                    
                    if not next_line or len(next_line) < 2:
                        continue
                    
                    # Ignorer UI/navigation
                    ui_keywords = ['Top Singles', 'Classement', 'Semaine du', 'chevron',
                                  'calendar', 'Voir les stats', 'timeline', 'N°Singles']
                    if any(kw.lower() in next_line.lower() for kw in ui_keywords):
                        continue
                    
                    # Ignorer _star_ seul
                    if next_line == '_star_':
                        continue
                    
                    # Détection du MOUVEMENT (peut être AVANT ou APRÈS l'artiste)
                    if 'arrow_top' in next_line:
                        movement = "up"
                        num_match = re.search(r'(\d+)', next_line)
                        if num_match:
                            previous_pos = position + int(num_match.group(1))
                        continue
                    
                    if 'arrow_bot' in next_line:
                        movement = "down"
                        num_match = re.search(r'(\d+)', next_line)
                        if num_match:
                            previous_pos = position - int(num_match.group(1))
                        continue
                    
                    if 'arrow_right' in next_line:
                        movement = "same"
                        previous_pos = position
                        continue
                    
                    if next_line.lower() == 'new':
                        movement = "new"
                        previous_pos = None
                        continue
                    
                    # Ignorer flèches seules
                    if next_line in ['↑', '↓', '→', '▲', '▼']:
                        continue
                    
                    # Titre (commençant par ## ou première ligne significative)
                    if not title:
                        if next_line.startswith('##'):
                            title = next_line[2:].strip()
                        elif len(next_line) > 2 and not next_line.startswith('_'):
                            title = next_line
                        continue
                    
                    # Artiste (deuxième ligne significative après titre)
                    if title and not artist:
                        if len(next_line) > 2 and not next_line.startswith('_'):
                            artist = next_line
                        # NE PAS CASSER ! Continuer pour chercher le mouvement
                
                if title and artist and len(title) > 2 and len(artist) > 2:
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
    
    return entries

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
        url = "https://snepmusique.com/classement-radio/"
    else:
        url = f"https://snepmusique.com/classement-radio/?annee={year}&semaine={week}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Semaine non trouvée (404)")
            return False
        
        response.raise_for_status()
        
        if "Aucun classement" in response.text or len(response.text) < 1000:
            print(f"    ❌ Aucune donnée disponible")
            return False
        
        entries = parse_snep_html(response.text)
        
        if not entries:
            print(f"    ❌ Aucune entrée parsée")
            return False
        
        entries.sort(key=lambda x: x["position"])
        
        seen = set()
        unique_entries = []
        for entry in entries:
            if entry["position"] not in seen:
                seen.add(entry["position"])
                unique_entries.append(entry)
        
        entries = unique_entries[:200]
        
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
    Parse le HTML de snepmusique.com (VERSION FINALE CORRIGÉE)
    CORRIGÉ : Parse les balises <strong> directement depuis le HTML source
    """
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')
    
     # DEBUG : Afficher les lignes 50-100 pour voir les données
    if not hasattr(parse_snep_html, '_debug_done'):
        text_debug = soup.get_text(separator='\n', strip=True)
        lines_debug = [l.strip() for l in text_debug.split('\n') if l.strip()]
        print("    🔍 DEBUG SNEP - Lignes 50-100 (données de classement) :")
        for i, line in enumerate(lines_debug[50:100], start=50):
            print(f"       [{i}] {line}")
        parse_snep_html._debug_done = True

    
    # Labels connus
    known_labels = [
        'SONY MUSIC', 'UNIVERSAL', 'WARNER MUSIC', 'BELIEVE', 
        'WAGRAM', 'WAGRAM MUSIC', 'IDOL', 'SCORPIO', 'HAPPY MUSIC', 
        'THIRTY KNOTS', 'NOJOKE RECORDS', 'AWAL', 'EMPIRE', 
        'BECAUSE MUSIC', 'LEVEL UP MUSIC', 'YPDP', 'ARGENTIC MUSIC', 
        'STMPD RCRDS', 'FIDEL', 'TRINITY', 'LORE', 'THE ORCHARD',
        'UNIVERSAL MUSIC', 'POLYDOR', 'VIRGIN', 'PARLOPHONE',
        'TÔT OU TARD', 'NAÏVE', 'PIAS', 'DOMINO', 'BEGGARS',
        'EPIC', 'COLUMBIA', 'RCA', 'ATLANTIC', 'ELEKTRA', 'DEF JAM',
        '3EME OEIL', 'PLAY TWO', 'M6', 'TF1', 'EARLY BIRD'
    ]
    known_labels_upper = [lbl.upper() for lbl in known_labels]
    
    nav_keywords = [
        'Semaine précédente', 'Semaine suivante', 'Télécharger en PDF', 
        'Voir les filtres', 'Top Radio', 'Top Outre-mer', 'Abonnement',
        'newsletter', 'Twitter', 'LinkedIn', 'Email', 'Copy link',
        'Merci de partager', 'AddToAny', 'FERMER', 'Marketing Permissions'
    ]
    
    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Position : nombre seul
        pos_match = re.match(r'^(\d{1,3})$', line)
        
        if pos_match:
            position = int(pos_match.group(1))
            
            if position <= 200:
                title = ""
                artist = ""
                label = ""
                previous_pos = None
                movement = "same"
                weeks_on_chart = 1
                
                # Scanner les 12 lignes suivantes
                for j in range(i + 1, min(i + 12, len(lines))):
                    next_line = lines[j].strip()
                    
                    if not next_line or len(next_line) < 2:
                        continue
                    
                    # Ignorer navigation
                    if any(kw.lower() in next_line.lower() for kw in nav_keywords):
                        continue
                    
                    # DÉTECTION MOUVEMENT : "Xer La Semaine Dernière"
                    if 'La Semaine Dernière' in next_line or 'semaine dernière' in next_line.lower():
                        prev_match = re.search(r'(\d+)(?:er|e|ème|ere|ere)?', next_line, re.IGNORECASE)
                        if prev_match:
                            previous_pos = int(prev_match.group(1))
                            if previous_pos > position:
                                movement = "up"
                            elif previous_pos < position:
                                movement = "down"
                            else:
                                movement = "same"
                        continue
                    
                    # DÉTECTION SEMAINES : "Xer Semaine dans le Top"
                    if 'Semaine dans le Top' in next_line or 'semaine dans le top' in next_line.lower():
                        weeks_match = re.search(r'(\d+)(?:er|e|ème|ere)?', next_line, re.IGNORECASE)
                        if weeks_match:
                            weeks_on_chart = int(weeks_match.group(1))
                            if weeks_on_chart == 1:
                                movement = "new"
                                previous_pos = None
                        continue
                    
                    # Ignorer labels
                    if next_line.upper() in known_labels_upper or next_line.upper().strip() in known_labels_upper:
                        label = next_line
                        continue
                    
                    # Ignorer lignes très courtes ou avec seulement des chiffres/ponctuation
                    if len(next_line) < 3:
                        continue
                    
                    # Titre (première ligne significative après position)
                    if not title:
                        title = next_line
                        continue
                    
                    # Artiste (deuxième ligne significative après titre)
                    if title and not artist:
                        artist = next_line
                        # NE PAS CASSER - continuer pour chercher label et mouvement
                
                # Valider
                if title and artist and len(title) > 2 and len(artist) > 2:
                    entries.append({
                        "position": position,
                        "track": {
                            "title": title,
                            "artist": artist
                        },
                        "label": label if label else None,
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
    
    if year <= 1993:
        print(f"   Source : top-archives.fr (1984-1993)")
    elif year < SNEP_START_YEAR:
        print(f"   Source : chartsinfrance.net (1994-2013)")
    elif year == SNEP_START_YEAR:
        print(f"   Source : chartsinfrance.net (S01-S15) + SNEP (S16+)")
    else:
        print(f"   Source : SNEP (officiel) + chartsinfrance (fallback)")
    
    print(f"{'='*60}\n")
    
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
            # 1984-1993 : top-archives.fr uniquement
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
            # 2015+ : SNEP en priorité, chartsinfrance en fallback
            result = fetch_snep_week(year, week, cache)
            
            # Fallback si SNEP échoue (pour les semaines récentes non encore sur SNEP)
            if not result:
                print(f"  🔄 Fallback sur chartsinfrance.net...")
                result = fetch_chartsinfrance_week(year, week, cache)
        
        if result:
            success += 1
        else:
            fail += 1
        
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