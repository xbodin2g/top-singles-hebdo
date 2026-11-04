#!/usr/bin/env python3
"""
Script pour télécharger les archives du Top 50 français via top-archives.fr.
Source officielle des archives 1984-1993.

Exécution : python fetch_archive_batch.py --year 1989
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9',
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

def get_week_links_for_year(year):
    """
    Récupère la liste des semaines (avec leurs IDs et dates) pour une année donnée.
    Retourne une liste de dicts : [{week_id, date_str, week_num}, ...]
    """
    url = f"https://top-archives.fr/top/year/{year}"
    
    print(f"📅 Récupération de la liste des semaines pour {year}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"  ❌ Année {year} non trouvée (le site couvre 1984-1993)")
            return []
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Trouver tous les liens vers les semaines
        week_links = []
        
        # Chercher les liens /top/week/{id}
        for link in soup.find_all('a', href=re.compile(r'/top/week/\d+')):
            href = link.get('href', '')
            match = re.search(r'/top/week/(\d+)', href)
            
            if match:
                week_id = int(match.group(1))
                
                # Extraire le texte du lien pour trouver la date
                link_text = link.get_text(strip=True)
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', link_text)
                
                date_str = date_match.group(1) if date_match else None
                
                week_links.append({
                    'week_id': week_id,
                    'date_str': date_str,
                    'href': href
                })
        
        # Dédoublonner et trier par ID
        seen_ids = set()
        unique_links = []
        
        for link in week_links:
            if link['week_id'] not in seen_ids:
                seen_ids.add(link['week_id'])
                unique_links.append(link)
        
        unique_links.sort(key=lambda x: x['week_id'])
        
        # Calculer les numéros de semaine
        for i, link in enumerate(unique_links):
            link['week_num'] = i + 1
        
        print(f"  ✅ {len(unique_links)} semaines trouvées")
        
        if unique_links:
            print(f"  📊 Première : {unique_links[0]['date_str']} (ID {unique_links[0]['week_id']})")
            print(f"  📊 Dernière : {unique_links[-1]['date_str']} (ID {unique_links[-1]['week_id']})")
        
        return unique_links
    
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return []

def fetch_week_top50(week_id, date_str, year, week_num, cache):
    """Récupère le top 50 complet pour une semaine donnée"""
    cache_key = f"{year}-{week_num:02d}"
    
    if cache_key in cache:
        print(f"  ⏭️  Semaine {week_num}/{year} ({date_str}) : déjà en cache")
        return True
    
    url = f"https://top-archives.fr/top/week/{week_id}"
    
    print(f"  📥 Semaine {week_num}/{year} ({date_str})...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Semaine non trouvée (404)")
            return False
        
        if response.status_code == 403:
            print(f"    ❌ Bloqué (403)")
            return False
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Stratégie 1 : Chercher un tableau
        table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                
                if len(cells) >= 2:
                    # Extraire le rang
                    rank_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', rank_text)
                    
                    if rank_match:
                        rank = int(rank_match.group())
                        
                        if 1 <= rank <= 50:
                            # Extraire artiste et titre
                            # Format variable : peut être dans cells[1], cells[2], etc.
                            artist = ""
                            title = ""
                            
                            # Chercher dans les cellules
                            for cell in cells[1:]:
                                text = cell.get_text(strip=True)
                                
                                if not text:
                                    continue
                                
                                # Vérifier si c'est un lien avec artiste/titre
                                links = cell.find_all('a')
                                
                                if len(links) >= 2:
                                    # Souvent : artiste puis titre
                                    if not artist:
                                        artist = links[0].get_text(strip=True)
                                    if not title:
                                        title = links[1].get_text(strip=True)
                                elif len(links) == 1:
                                    # Un seul lien, peut contenir "Artiste - Titre"
                                    link_text = links[0].get_text(strip=True)
                                    if ' - ' in link_text:
                                        parts = link_text.split(' - ', 1)
                                        artist = parts[0].strip()
                                        title = parts[1].strip()
                                    elif not title:
                                        title = link_text
                                else:
                                    # Pas de lien, texte brut
                                    if not artist and len(text) > 2:
                                        artist = text
                                    elif not title and len(text) > 2:
                                        title = text
                            
                            # Nettoyer
                            artist = re.sub(r'\s+', ' ', artist).strip()
                            title = re.sub(r'\s+', ' ', title).strip()
                            
                            if artist and title:
                                # Extraire la position précédente si disponible
                                previous_pos = None
                                movement = "same"
                                
                                # Chercher des indices de mouvement dans les cellules
                                for cell in cells:
                                    cell_text = cell.get_text(strip=True)
                                    
                                    if 'new' in cell_text.lower() or 'entrée' in cell_text.lower():
                                        movement = "new"
                                        break
                                    elif re.search(r'\d+', cell_text):
                                        # Pourrait être la position précédente
                                        prev_match = re.search(r'(\d+)', cell_text)
                                        if prev_match:
                                            prev = int(prev_match.group(1))
                                            if prev != rank and prev <= 50:
                                                previous_pos = prev
                                                if prev > rank:
                                                    movement = "up"
                                                elif prev < rank:
                                                    movement = "down"
                                                break
                                
                                entries.append({
                                    "position": rank,
                                    "track": {
                                        "title": title,
                                        "artist": artist
                                    },
                                    "previousPosition": previous_pos,
                                    "movement": movement,
                                    "weeksOnChart": 1,
                                    "peakPosition": rank,
                                    "source": "top_archives"
                                })
        
        # Stratégie 2 : Si pas de tableau, chercher dans des divs/listes
        if len(entries) < 10:
            items = soup.find_all(['div', 'li', 'p'], class_=re.compile(r'track|song|position|chart|top', re.I))
            
            for item in items[:50]:
                text = item.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text.split('|') if p.strip()]
                
                if len(parts) >= 2:
                    # Chercher un rang
                    rank = None
                    for part in parts:
                        if part.isdigit() and int(part) <= 50:
                            rank = int(part)
                            break
                    
                    if rank:
                        # Extraire artiste et titre
                        artist = ""
                        title = ""
                        
                        for j in range(len(parts) - 1):
                            if len(parts[j]) > 2 and len(parts[j+1]) > 2:
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
                                "source": "top_archives"
                            })
        
        if entries:
            # Trier par position et dédoublonner
            entries.sort(key=lambda x: x["position"])
            
            # Supprimer les doublons
            seen_positions = set()
            unique_entries = []
            for entry in entries:
                if entry["position"] not in seen_positions:
                    seen_positions.add(entry["position"])
                    unique_entries.append(entry)
            
            entries = unique_entries[:50]
            
            archive_data = {
                "week": week_num,
                "year": year,
                "date": date_str,
                "week_id": week_id,
                "entries": entries,
                "cached_at": datetime.now().strftime('%Y-%m-%d')
            }
            
            cache[cache_key] = archive_data
            
            print(f"    ✅ {len(entries)} entrées trouvées")
            
            # Afficher le top 3
            if entries:
                print(f"    📊 Top 3 :")
                for entry in entries[:3]:
                    print(f"       {entry['position']}. {entry['track']['artist']} - {entry['track']['title']}")
            
            # Délai pour être poli avec le serveur
            time.sleep(2)
            
            return True
        else:
            print(f"    ❌ Aucune entrée trouvée")
            return False
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Télécharge les archives du Top 50 depuis top-archives.fr')
    parser.add_argument('--year', type=int, required=True, help='Année (1984-1993)')
    
    args = parser.parse_args()
    
    year = args.year
    
    if year < 1984 or year > 1993:
        print(f"❌ top-archives.fr couvre seulement 1984-1993")
        print(f"   Année demandée : {year}")
        sys.exit(1)
    
    print(f"📅 Archives Top 50 France - Année {year}")
    print(f"   Source : top-archives.fr (archives 1984-1993)")
    print(f"{'='*60}\n")
    
    # Étape 1 : Récupérer la liste des semaines
    week_links = get_week_links_for_year(year)
    
    if not week_links:
        print(f"\n❌ Impossible de récupérer les semaines pour {year}")
        sys.exit(1)
    
    # Étape 2 : Télécharger chaque semaine
    cache = load_retro_cache()
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for week_info in week_links:
        week_id = week_info['week_id']
        date_str = week_info['date_str']
        week_num = week_info['week_num']
        
        cache_key = f"{year}-{week_num:02d}"
        
        if cache_key in cache:
            skip_count += 1
            continue
        
        result = fetch_week_top50(week_id, date_str, year, week_num, cache)
        
        if result:
            success_count += 1
        else:
            fail_count += 1
        
        # Sauvegarder toutes les 5 semaines
        if (success_count + fail_count) % 5 == 0 and success_count > 0:
            save_retro_cache(cache)
            print(f"\n  💾 Cache sauvegardé ({len(cache)} archives)\n")
    
    # Sauvegarde finale
    save_retro_cache(cache)
    
    print(f"\n{'='*60}")
    print(f"✅ Téléchargement terminé")
    print(f"   - {success_count} nouvelles archives")
    print(f"   - {skip_count} déjà en cache")
    print(f"   - {fail_count} échecs")
    print(f"   - Total en cache : {len(cache)} archives")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()