#!/usr/bin/env python3
"""
Script pour récupérer les archives du Top 50 français depuis lescharts.com.
Utilise un cache séparé avec nettoyage manuel par année.

Exécution : python fetch_archive.py --year 1995 --week 23
Nettoyage : python fetch_archive.py --clean-year 1995
Liste     : python fetch_archive.py --list
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
import argparse
import sys

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Cache séparé pour les archives rétro (pas de nettoyage automatique)
CACHE_DIR = "data/cache"
CACHE_RETRO_FILE = os.path.join(CACHE_DIR, "retro_archives.json")

def load_retro_cache():
    """Charge le cache des archives rétro"""
    if os.path.exists(CACHE_RETRO_FILE):
        try:
            with open(CACHE_RETRO_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"📦 Cache rétro chargé : {len(cache)} archives en mémoire")
            return cache
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement du cache rétro: {e}")
            return {}
    return {}

def save_retro_cache(cache):
    """Sauvegarde le cache des archives rétro"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_RETRO_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache rétro sauvegardé : {len(cache)} archives au total")
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde du cache rétro: {e}")

def get_retro_cache_key(year, week):
    """Génère la clé de cache pour une archive"""
    return f"{year}-{week:02d}"

def clean_retro_cache_by_year(year):
    """
    Nettoie manuellement le cache rétro pour une année spécifique.
    Retourne le nombre d'entrées supprimées.
    """
    cache = load_retro_cache()
    
    if not cache:
        print("❌ Le cache rétro est vide")
        return 0
    
    keys_to_remove = [key for key in cache.keys() if key.startswith(f"{year}-")]
    
    for key in keys_to_remove:
        del cache[key]
    
    if keys_to_remove:
        save_retro_cache(cache)
        print(f"🧹 Nettoyage manuel : {len(keys_to_remove)} archives de {year} supprimées")
        print(f"   Cache restant : {len(cache)} archives")
    else:
        print(f"ℹ️ Aucune archive trouvée pour l'année {year}")
    
    return len(keys_to_remove)

def fetch_top50_archive(year, week):
    """Récupère le Top 50 français pour une année et semaine données"""
    cache_key = get_retro_cache_key(year, week)
    cache = load_retro_cache()
    
    # Vérifier d'abord le cache
    if cache_key in cache:
        print(f"✅ Archive trouvée dans le cache (pas de nouvelle requête)")
        return cache[cache_key]
    
    print(f"📅 Récupération du Top 50 - Semaine {week}/{year}...")
    
    url = f"https://lescharts.com/weekchart.asp?cat=s&week={week}&year={year}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"  ❌ Page non trouvée (404)")
            return None
        
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
            
            # Sauvegarder dans le cache rétro
            cache[cache_key] = archive_data
            save_retro_cache(cache)
            
            print(f"  ✅ {len(entries)} entrées trouvées et mises en cache")
            print(f"  📊 Top 3 :")
            for entry in entries[:3]:
                print(f"     {entry['position']}. {entry['track']['artist']} - {entry['track']['title']}")
            
            return archive_data
        else:
            print(f"  ❌ Aucune entrée trouvée")
            return None
    
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return None

def list_archives():
    """Liste toutes les archives disponibles dans le cache"""
    cache = load_retro_cache()
    
    if not cache:
        print("📭 Le cache rétro est vide")
        print("   Utilisez : python fetch_archive.py --year YYYY --week WW")
        return
    
    # Grouper par année
    archives_by_year = {}
    for key in cache.keys():
        year, week = key.split('-')
        if year not in archives_by_year:
            archives_by_year[year] = []
        archives_by_year[year].append(int(week))
    
    print(f"\n📚 Archives disponibles ({len(cache)} au total) :")
    print(f"{'='*50}")
    
    for year in sorted(archives_by_year.keys(), reverse=True):
        weeks = sorted(archives_by_year[year])
        weeks_str = ', '.join([f"S{w}" for w in weeks])
        print(f"   {year} : {len(weeks)} archives ({weeks_str})")
    
    print(f"{'='*50}")
    print(f"\n💡 Pour nettoyer une année : python fetch_archive.py --clean-year YYYY")

def main():
    parser = argparse.ArgumentParser(description='Gère les archives du Top 50 français')
    parser.add_argument('--year', type=int, help='Année (ex: 1995)')
    parser.add_argument('--week', type=int, help='Semaine (ex: 23)')
    parser.add_argument('--list', action='store_true', help='Lister les archives disponibles')
    parser.add_argument('--clean-year', type=int, help='Nettoyer le cache pour une année spécifique')
    
    args = parser.parse_args()
    
    if args.clean_year:
        clean_retro_cache_by_year(args.clean_year)
        return
    
    if args.list:
        list_archives()
        return
    
    if not args.year or not args.week:
        print("❌ Veuillez spécifier --year et --week")
        print("   Exemple : python fetch_archive.py --year 1995 --week 23")
        print("   Aide : python fetch_archive.py --help")
        sys.exit(1)
    
    if args.week < 1 or args.week > 53:
        print("❌ La semaine doit être entre 1 et 53")
        sys.exit(1)
    
    if args.year < 1984 or args.year > datetime.now().year:
        print(f"❌ L'année doit être entre 1984 et {datetime.now().year}")
        sys.exit(1)
    
    archive_data = fetch_top50_archive(args.year, args.week)
    
    if archive_data:
        print(f"\n✅ Archive prête : Semaine {args.week}/{args.year}")
    else:
        print(f"\n❌ Impossible de récupérer l'archive")
        sys.exit(1)

if __name__ == "__main__":
    main()