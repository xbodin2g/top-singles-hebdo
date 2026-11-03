#!/usr/bin/env python3
"""
Script pour récupérer les archives du Top 50 français depuis lescharts.com.
Exécution : python fetch_archive.py --year 1995 --week 23
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

def fetch_top50_archive(year, week):
    """
    Récupère le Top 50 français pour une année et semaine données.
    Source : lescharts.com
    """
    print(f"📅 Récupération du Top 50 - Semaine {week}/{year}...")
    
    # lescharts.com utilise le format : weekchart.asp?cat=s&week=XX&year=YYYY
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
            
            for row in rows[1:51]:  # 50 premiers
                cells = row.find_all('td')
                
                if len(cells) >= 3:
                    rank_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', rank_text)
                    
                    if rank_match:
                        rank = int(rank_match.group())
                        
                        # Extraire artiste et titre
                        text = row.get_text(separator='|', strip=True)
                        parts = [p.strip() for p in text.split('|') if p.strip()]
                        
                        if len(parts) >= 3:
                            # Format généralement : rang | artiste | titre
                            artist = parts[1]
                            title = parts[2]
                            
                            # Nettoyer les titres
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
            # Trier par position
            entries.sort(key=lambda x: x["position"])
            print(f"  ✅ {len(entries)} entrées trouvées")
            
            # Afficher les 3 premiers
            print(f"  📊 Top 3 :")
            for entry in entries[:3]:
                print(f"     {entry['position']}. {entry['track']['artist']} - {entry['track']['title']}")
            
            return {
                "week": week,
                "year": year,
                "date": f"Semaine {week}/{year}",
                "entries": entries
            }
        else:
            print(f"  ❌ Aucune entrée trouvée")
            return None
    
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return None

def get_available_archives():
    """Liste les archives disponibles de 1984 à l'année actuelle"""
    current_year = datetime.now().year
    archives = []
    
    # Le Top 50 a commencé en novembre 1984
    for year in range(1984, current_year + 1):
        # Calculer le nombre de semaines (52 ou 53)
        weeks = 52
        archives.append({"year": year, "weeks": weeks})
    
    return archives

def main():
    parser = argparse.ArgumentParser(description='Récupère les archives du Top 50 français')
    parser.add_argument('--year', type=int, help='Année (ex: 1995)')
    parser.add_argument('--week', type=int, help='Semaine (ex: 23)')
    parser.add_argument('--list', action='store_true', help='Lister les archives disponibles')
    
    args = parser.parse_args()
    
    if args.list:
        print("📚 Archives disponibles :")
        print("   De 1984 à aujourd'hui, 52 semaines par an")
        print("   Exemple : python fetch_archive.py --year 1995 --week 23")
        return
    
    if not args.year or not args.week:
        print("❌ Veuillez spécifier --year et --week")
        print("   Exemple : python fetch_archive.py --year 1995 --week 23")
        sys.exit(1)
    
    # Récupérer l'archive
    archive_data = fetch_top50_archive(args.year, args.week)
    
    if archive_data:
        # Sauvegarder dans data/archives/
        output_dir = "data/archives"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/top50-{args.year}-{args.week:02d}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Archive sauvegardée : {filename}")
    else:
        print(f"\n❌ Impossible de récupérer l'archive")
        sys.exit(1)

if __name__ == "__main__":
    main()