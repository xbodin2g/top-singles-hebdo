#!/usr/bin/env python3
"""
Script pour télécharger des archives du Top 50 français en lot.
Utilisé par GitHub Actions pour alimenter la base rétro.

Exécution : python fetch_archive_batch.py --year 1995 --weeks 1-52
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
import argparse
import sys
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

CACHE_DIR = "data/cache"
CACHE_RETRO_FILE = os.path.join(CACHE_DIR, "retro_archives.json")

def load_retro_cache():
    """Charge le cache des archives rétro"""
    if os.path.exists(CACHE_RETRO_FILE):
        try:
            with open(CACHE_RETRO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement du cache: {e}")
            return {}
    return {}

def save_retro_cache(cache):
    """Sauvegarde le cache des archives rétro"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_RETRO_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} archives au total")
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde: {e}")

def fetch_top50_archive(year, week, cache):
    """Récupère le Top 50 français pour une année et semaine données"""
    cache_key = f"{year}-{week:02d}"
    
    # Vérifier d'abord le cache
    if cache_key in cache:
        print(f"  ✅ Semaine {week}/{year} : déjà en cache")
        return True
    
    print(f"  📥 Semaine {week}/{year} : téléchargement...")
    
    url = f"https://lescharts.com/weekchart.asp?cat=s&week={week}&year={year}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Page non trouvée (404)")
            return False
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Stratégie 1 : Tableau
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            
            for row in rows[1:51]:
                cells = row.find_all('td')
                
                if len(cells) >= 3:
                    rank_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', rank_text)
                    
                    if rank_match:
                        rank = int(rank_match.group())
                        
                        text = row.get_text(separator='|', strip=True)
                        parts = [p.strip() for p in text.split('|') if p.strip()]
                        
                        if len(parts) >= 3:
                            artist = parts[1]
                            title = parts[2]
                            
                            title = re.sub(r'\s+', ' ', title).strip()
                            artist = re.sub(r'\s+', ' ', artist).strip()
                            
                            entries.append({
                                "position": rank,
                                "track": {
                                    "title": title,
                                    "artist": artist
                                },
                                "previousPosition": None,
                                "movement": "same",
                                "weeksOnChart": 1,
                                "peakPosition": rank,
                                "source": "lescharts_archive"
                            })
        
        # Stratégie 2 : Divs si tableau non trouvé
        if len(entries) < 10:
            items = soup.find_all(['div', 'li'], class_=re.compile(r'chart|track|song|position', re.I))
            
            for item in items[:50]:
                text = item.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text.split('|') if p.strip()]
                
                if len(parts) >= 2:
                    rank = None
                    for part in parts:
                        if part.isdigit() and int(part) <= 100:
                            rank = int(part)
                            break
                    
                    if rank:
                        artist = ""
                        title = ""
                        
                        for j in range(len(parts) - 1):
                            if len(parts[j]) > 3 and len(parts[j+1]) > 3:
                                artist = parts[j]
                                title = parts[j+1]
                                break
                        
                        if artist and title:
                            entries.append({
                                "position": rank,
                                "track": {"title": title, "artist": artist},
                                "previousPosition": None,
                                "movement": "same",
                                "weeksOnChart": 1,
                                "peakPosition": rank,
                                "source": "lescharts_archive"
                            })
        
        if entries:
            entries.sort(key=lambda x: x["position"])
            
            archive_data = {
                "week": week,
                "year": year,
                "date": f"Semaine {week}/{year}",
                "entries": entries,
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = archive_data
            
            print(f"    ✅ {len(entries)} entrées trouvées")
            
            # Délai pour ne pas surcharger le serveur
            time.sleep(1)
            
            return True
        else:
            print(f"    ❌ Aucune entrée trouvée")
            return False
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return False

def parse_weeks(weeks_str):
    """
    Parse la chaîne de semaines.
    Formats acceptés : "1-52", "23", "1,5,10", "1-10,20,30-40"
    """
    weeks = set()
    
    for part in weeks_str.split(','):
        part = part.strip()
        
        if '-' in part:
            start, end = part.split('-', 1)
            try:
                start_week = int(start.strip())
                end_week = int(end.strip())
                weeks.update(range(start_week, end_week + 1))
            except ValueError:
                print(f"⚠️ Format invalide : {part}")
        else:
            try:
                weeks.add(int(part))
            except ValueError:
                print(f"⚠️ Format invalide : {part}")
    
    return sorted([w for w in weeks if 1 <= w <= 53])

def main():
    parser = argparse.ArgumentParser(description='Télécharge des archives du Top 50 français en lot')
    parser.add_argument('--year', type=int, required=True, help='Année (ex: 1995)')
    parser.add_argument('--weeks', type=str, required=True, help='Semaines (ex: 1-52 ou 23 ou 1,5,10)')
    
    args = parser.parse_args()
    
    year = args.year
    weeks = parse_weeks(args.weeks)
    
    if not weeks:
        print("❌ Aucune semaine valide spécifiée")
        sys.exit(1)
    
    if year < 1984 or year > datetime.now().year:
        print(f"❌ L'année doit être entre 1984 et {datetime.now().year}")
        sys.exit(1)
    
    print(f"📅 Téléchargement des archives Top 50 - Année {year}")
    print(f"   Semaines demandées : {len(weeks)}")
    print(f"{'='*60}\n")
    
    cache = load_retro_cache()
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for week in weeks:
        cache_key = f"{year}-{week:02d}"
        
        if cache_key in cache:
            skip_count += 1
            print(f"  ⏭️  Semaine {week}/{year} : déjà en cache")
            continue
        
        result = fetch_top50_archive(year, week, cache)
        
        if result:
            success_count += 1
        else:
            fail_count += 1
        
        # Sauvegarder le cache toutes les 10 semaines
        if (success_count + fail_count) % 10 == 0:
            save_retro_cache(cache)
            print(f"\n  💾 Cache sauvegardé ({len(cache)} archives)\n")
    
    # Sauvegarde finale
    save_retro_cache(cache)
    
    print(f"\n{'='*60}")
    print(f"✅ Téléchargement terminé")
    print(f"   - {success_count} nouvelles archives téléchargées")
    print(f"   - {skip_count} archives déjà en cache")
    print(f"   - {fail_count} échecs")
    print(f"   - Total en cache : {len(cache)} archives")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()