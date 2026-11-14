#!/usr/bin/env python3
"""
Archives Top singles français — 3 sources :
  1. top-archives.fr    (1984 → 1993 S35)
  2. chartsinfrance.net (1993 S36 → 2014 S15)
  3. snepmusique.com    (2014 S16 → aujourd'hui, officiel)

Paliers de taille publiés par chartsinfrance (mesurés) :
  < 1998-10 : 50   |  1998-10 → 2012-05 : 100  |  >= 2012-06 : 25

Corrections :
  - data/track_overrides.json appliqué à chaque sauvegarde (rename / delete)
  - garde-fou anti-fantômes à deux niveaux (dur / souple)
  - artistes et titres courts acceptés (U2, M, 19, 7…)
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
import unicodedata

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}

CACHE_DIR = "data/cache"
CACHE_RETRO_FILE = os.path.join(CACHE_DIR, "retro_archives.json")
TRACK_OVERRIDES_FILE = "data/track_overrides.json"

SNEP_START_YEAR = 2014
SNEP_START_WEEK = 16
TOP_ARCHIVES_END_YEAR = 1993
TOP_ARCHIVES_END_WEEK = 35

# Tokens qui ne sont JAMAIS un titre ni un artiste réel.
# Rejet si l'UN des deux champs correspond.
UI_HARD_JUNK = {
    'timeline', 'voir les stats', 'n°',
    'arrow_right', 'arrow_top', 'arrow_bot', 'arrow',
    'chevron_right', 'chevron_bot', 'chevron_left', 'chevron',
}

# Tokens ambigus : ce sont aussi de vrais titres ("Singles" de Nirvana,
# "Star" de La Clinique / Teri Moïse). Rejet seulement si les DEUX
# champs sont des tokens d'interface.
UI_SOFT_JUNK = {'singles', 'star'}


def _junk_kind(value):
    v = str(value or "").strip().lower()
    if v in UI_HARD_JUNK:
        return "hard"
    if v in UI_SOFT_JUNK:
        return "soft"
    return None


def is_phantom(title, artist):
    """True si l'entrée est un artefact d'interface, pas un vrai titre."""
    kt = _junk_kind(title)
    ka = _junk_kind(artist)
    if kt == "hard" or ka == "hard":
        return True
    if kt == "soft" and ka == "soft":
        return True
    return False


# ===== OVERRIDES DE TITRES =====

_overrides_cache = None


def _norm_override(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_numeric_title(t):
    t = str(t or "").strip()
    if not t:
        return True
    return re.fullmatch(r"[\d\s\.\-–—#/°]+", t) is not None


def _load_overrides():
    global _overrides_cache
    if _overrides_cache is not None:
        return _overrides_cache

    _overrides_cache = []
    if os.path.exists(TRACK_OVERRIDES_FILE):
        try:
            with open(TRACK_OVERRIDES_FILE, "r", encoding="utf-8") as f:
                rules = json.load(f)
            for r in rules:
                am = (r.get("artist_match") or "").strip()
                nt = (r.get("new_title") or "").strip()
                action = (r.get("action") or "rename").lower()
                if not am:
                    continue
                if action == "rename" and not nt:
                    continue
                _overrides_cache.append({
                    "action": action,
                    "needle": am.lower(),
                    "needle_norm": _norm_override(am),
                    "title_needle": (r.get("title_match") or "").strip().lower(),
                    "new_title": nt,
                    "new_artist": (r.get("new_artist") or am).strip(),
                    "years": set(r.get("years") or []),
                    "numeric_only": bool(r.get("only_if_numeric_title", True)),
                })
            if _overrides_cache:
                n_del = sum(1 for r in _overrides_cache if r["action"] == "delete")
                print(f"🔧 {len(_overrides_cache)} règle(s) : "
                      f"{len(_overrides_cache)-n_del} renommage(s), {n_del} suppression(s)")
        except Exception as e:
            print(f"⚠️ Overrides illisibles ({TRACK_OVERRIDES_FILE}) : {e}")
    return _overrides_cache


def apply_track_overrides(cache):
    rules = _load_overrides()
    if not rules:
        return 0

    fixed = 0
    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue

        m = re.match(r"^(\d{4})-(\d{1,2})$", str(key))
        try:
            year = int(m.group(1)) if m else int(arch.get("year"))
        except (TypeError, ValueError):
            year = None

        entries = arch.get("entries") or []
        kept = []

        for entry in entries:
            tr = entry.get("track")
            if not isinstance(tr, dict):
                kept.append(entry)
                continue

            title = tr.get("title", "")
            artist = tr.get("artist", "")
            a_low = str(artist).lower()
            t_low = str(title).lower()
            drop = False

            for r in rules:
                if r["years"] and year not in r["years"]:
                    continue
                if r["needle"] not in a_low and r["needle"] not in t_low:
                    continue
                tn = r.get("title_needle")
                if tn and tn not in t_low and tn not in a_low:
                    continue

                if r.get("action") == "delete":
                    fixed += 1
                    drop = True
                    break

                if r["numeric_only"] and not _is_numeric_title(title):
                    continue

                if tr.get("title") != r["new_title"] or tr.get("artist") != r["new_artist"]:
                    tr["title"] = r["new_title"]
                    tr["artist"] = r["new_artist"]
                    fixed += 1
                break

            if not drop:
                kept.append(entry)

        if len(kept) != len(entries):
            arch["entries"] = kept

    return fixed


# ===== CACHE =====

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
        n = apply_track_overrides(cache)
        if n:
            print(f"🔧 {n} entrée(s) corrigée(s)/supprimée(s) via track_overrides.json")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_RETRO_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} archives")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde: {e}")


def year_to_yy(year):
    return str(year)[2:]


def get_date_from_year_week(year, week):
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    return start_of_week1 + timedelta(weeks=week - 1)


# ===== SOURCE 1 : top-archives.fr =====

def fetch_toparchives_week(year, week, cache):
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
            match = re.search(r'/top/week/(\d+)', link.get('href', ''))
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
            cache[cache_key] = {
                "week": week,
                "year": year,
                "date": date.strftime('%d/%m/%Y'),
                "entries": entries,
                "source": "top-archives.fr",
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            print(f"  ✅ top-archives.fr : {len(entries)} entrées")
            time.sleep(2)
            return True

    except Exception as e:
        print(f"  ❌ top-archives.fr erreur: {e}")

    return False


def parse_toparchives_html(soup):
    entries = []
    table = soup.find('table')

    if table:
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            rank_text = cells[0].get_text(strip=True)
            rank_match = re.search(r'\d+', rank_text)
            if not rank_match:
                continue

            rank = int(rank_match.group())
            if not 1 <= rank <= 50:
                continue

            links = cells[1].find_all('a')
            if len(links) >= 2:
                artist = links[0].get_text(strip=True)
                title = links[1].get_text(strip=True)
            else:
                text = cells[1].get_text(separator='|', strip=True)
                parts = [p.strip() for p in text.split('|') if p.strip()]
                artist = parts[0] if parts else ""
                title = parts[1] if len(parts) > 1 else ""

            if artist and title and not is_phantom(title, artist):
                entries.append({
                    "position": rank,
                    "track": {"title": title, "artist": artist},
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": rank
                })

    return entries


# ===== SOURCE 2 : chartsinfrance.net =====

def fetch_chartsinfrance_week(year, week, cache):
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
                break

            if "Aucun classement disponible" in response.text:
                if page == 1:
                    print(f"    ❌ Aucune donnée disponible")
                    return False
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
        cache[cache_key] = {
            "week": week,
            "year": year,
            "date": date.strftime('%d/%m/%Y'),
            "entries": entries,
            "source": "chartsinfrance.net",
            "pages": page,
            "cached_at": datetime.now().strftime('%Y-%m-%d')
        }
        print(f"  ✅ chartsinfrance.net : {len(entries)} entrées (sur {page} page(s))")
        time.sleep(1)
        return True

    return False


def parse_chartsinfrance_html(html_text):
    """
    Structure : Position → Titre → Artiste → arrow_XXX → Valeur → timeline → Voir les stats

    Corrections V2 :
      - longueurs minimales ramenées à 1 : "U2" (2 car.) était rejeté,
        ainsi que les titres courts comme "19" ou "7"
      - garde-fou à deux niveaux : "Singles" (Nirvana) et "Star"
        (La Clinique, Teri Moïse) sont de vrais titres, pas des fantômes
    """
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')

    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        pos_match = re.match(r'^(?:_star_\s*|star\s*)?(\d{1,3})$', line)

        if pos_match:
            position = int(pos_match.group(1))

            if 1 <= position <= 100:
                block = []
                for j in range(i + 1, min(i + 9, len(lines))):
                    block.append(lines[j])

                if len(block) >= 3:
                    title = block[0]
                    artist = block[1]
                    movement = "same"
                    previous_pos = None

                    for k, bline in enumerate(block[2:], start=2):
                        if 'arrow_top' in bline:
                            movement = "up"
                            if k + 1 < len(block):
                                num_match = re.search(r'^(\d+)$', block[k + 1])
                                if num_match:
                                    previous_pos = position + int(num_match.group(1))
                            break

                        if 'arrow_bot' in bline:
                            movement = "down"
                            if k + 1 < len(block):
                                num_match = re.search(r'^(\d+)$', block[k + 1])
                                if num_match:
                                    previous_pos = position - int(num_match.group(1))
                            break

                        if 'arrow_right' in bline:
                            movement = "same"
                            previous_pos = position
                            break

                        if bline.lower() == 'new':
                            movement = "new"
                            previous_pos = None
                            break

                    if (title and artist
                            and len(title) >= 1 and len(artist) >= 1
                            and not is_phantom(title, artist)):
                        if not any(kw in title.lower() for kw in
                                   ['semaine', 'top singles', 'charts', 'classement']):
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
    if '?page=' in html_text:
        if 'Suivant' in html_text or 'Next' in html_text or 'arrow_right' in html_text:
            return True
    return False


# ===== SOURCE 3 : snepmusique.com =====

def fetch_snep_week(year, week, cache):
    cache_key = f"{year}-{week:02d}"
    if cache_key in cache:
        return True

    print(f"  📥 snepmusique.com (SNEP) : {year} S{week:02d}...")

    now = datetime.now()
    if year == now.year and week == now.isocalendar()[1]:
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
            cache[cache_key] = {
                "week": week,
                "year": year,
                "date": date.strftime('%d/%m/%Y'),
                "entries": entries,
                "source": "snepmusique.com",
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
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
    Structure : Position → Titre → Artiste → LABEL
                → [nombre] → [e] → La Semaine Dernière
                → [nombre] → [e] → Semaine dans le Top

    Même correction de longueur que chartsinfrance : "U2" était rejeté.
    """
    entries = []
    soup = BeautifulSoup(html_text, 'html.parser')

    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    known_labels = [
        'SONY MUSIC', 'UNIVERSAL', 'WARNER MUSIC', 'BELIEVE',
        'WAGRAM', 'WAGRAM MUSIC', 'IDOL', 'SCORPIO', 'HAPPY MUSIC',
        'THIRTY KNOTS', 'NOJOKE RECORDS', 'AWAL', 'EMPIRE',
        'BECAUSE MUSIC', 'LEVEL UP MUSIC', 'YPDP', 'ARGENTIC MUSIC',
        'STMPD RCRDS', 'FIDEL', 'TRINITY', 'LORE', 'THE ORCHARD',
        'UNIVERSAL MUSIC', 'POLYDOR', 'VIRGIN', 'PARLOPHONE',
        'EPIC', 'COLUMBIA', 'RCA', 'ATLANTIC', 'ELEKTRA', 'DEF JAM',
        'PLAY TWO', 'EARLY BIRD', 'TÔT OU TARD', 'NAÏVE', 'PIAS',
        'WARNER', 'SONY', 'BECAUSE', '3EME OEIL'
    ]
    known_labels_upper = [lbl.upper().strip() for lbl in known_labels]

    i = 0
    while i < len(lines):
        pos_match = re.match(r'^(\d{1,3})$', lines[i])

        if pos_match:
            position = int(pos_match.group(1))

            if 1 <= position <= 200:
                block = []
                for j in range(i + 1, min(i + 13, len(lines))):
                    block.append(lines[j])

                if len(block) >= 5:
                    title = block[0]
                    artist = block[1]
                    label = ""
                    previous_pos = None
                    movement = "same"
                    weeks_on_chart = 1

                    if len(block) > 2 and block[2].upper() in known_labels_upper:
                        label = block[2]
                        data_start = 3
                    else:
                        data_start = 2

                    for k, bline in enumerate(block[data_start:], start=data_start):
                        if 'La Semaine Dernière' in bline:
                            if k >= 2 and block[k - 2].isdigit():
                                previous_pos = int(block[k - 2])
                                if previous_pos > position:
                                    movement = "up"
                                elif previous_pos < position:
                                    movement = "down"
                                else:
                                    movement = "same"

                        elif 'Semaine dans le Top' in bline:
                            if k >= 2 and block[k - 2].isdigit():
                                weeks_on_chart = int(block[k - 2])
                                if weeks_on_chart == 1:
                                    movement = "new"
                                    previous_pos = None

                    if (title and artist
                            and len(title) >= 1 and len(artist) >= 1
                            and not is_phantom(title, artist)):
                        if not any(kw in title.lower() for kw in
                                   ['semaine', 'top radio', 'actualités', 'les tops', 'news', 'newsletter']):
                            entries.append({
                                "position": position,
                                "track": {"title": title, "artist": artist},
                                "label": label if label else None,
                                "previousPosition": previous_pos,
                                "movement": movement,
                                "weeksOnChart": weeks_on_chart,
                                "peakPosition": position,
                                "source": "snep"
                            })

        i += 1

    return entries


# ===== MAIN =====

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

    print(f"📅 Archives Top singles France — Année {year}")

    if year < TOP_ARCHIVES_END_YEAR:
        print("   Source : top-archives.fr")
    elif year == TOP_ARCHIVES_END_YEAR:
        print(f"   Source : top-archives.fr (S01-S{TOP_ARCHIVES_END_WEEK}) + "
              f"chartsinfrance.net (S{TOP_ARCHIVES_END_WEEK+1}+)")
    elif year < SNEP_START_YEAR:
        print("   Source : chartsinfrance.net")
    elif year == SNEP_START_YEAR:
        print(f"   Source : chartsinfrance.net (S01-S{SNEP_START_WEEK-1}) + SNEP (S{SNEP_START_WEEK}+)")
    else:
        print("   Source : SNEP (officiel) + chartsinfrance (fallback)")

    print(f"{'='*60}\n")

    if '-' in args.weeks:
        start, end = map(int, args.weeks.split('-'))
        weeks = list(range(start, end + 1))
    else:
        weeks = [int(args.weeks)]

    cache = load_retro_cache()
    _load_overrides()

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

        if year < TOP_ARCHIVES_END_YEAR:
            result = fetch_toparchives_week(year, week, cache)

        elif year == TOP_ARCHIVES_END_YEAR:
            if week <= TOP_ARCHIVES_END_WEEK:
                result = fetch_toparchives_week(year, week, cache)
            else:
                result = fetch_chartsinfrance_week(year, week, cache)

        elif year < SNEP_START_YEAR:
            result = fetch_chartsinfrance_week(year, week, cache)

        elif year == SNEP_START_YEAR:
            if week < SNEP_START_WEEK:
                result = fetch_chartsinfrance_week(year, week, cache)
            else:
                result = fetch_snep_week(year, week, cache)

        else:
            result = fetch_snep_week(year, week, cache)
            if not result:
                print("  🔄 Fallback sur chartsinfrance.net...")
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