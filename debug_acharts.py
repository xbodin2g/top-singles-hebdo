#!/usr/bin/env python3
"""
Script de debug pour comprendre pourquoi acharts.co ne parse pas correctement
"""

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}

URLS_TO_TEST = [
    ("US", "https://acharts.co/us_singles_top_100"),
    ("UK", "https://acharts.co/uk_singles_top_75"),
    ("Suisse", "https://acharts.co/swiss_singles_top_100"),
]

def debug_acharts(url, country_name):
    print(f"\n{'='*70}")
    print(f"🔍 DEBUG acharts.co pour {country_name}")
    print(f"{'='*70}")
    print(f"URL : {url}\n")
    
    try:
        # Étape 1 : Récupérer la page
        print("📥 Étape 1 : Récupération de la page...")
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        print(f"   Status code : {response.status_code}")
        print(f"   Taille HTML : {len(response.text)} caractères")
        
        if response.status_code != 200:
            print(f"   ❌ ÉCHEC : Status code {response.status_code}")
            return
        
        print(f"   ✅ Page récupérée avec succès\n")
        
        # Étape 2 : Parser avec BeautifulSoup
        print("🔍 Étape 2 : Parsing HTML...")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Étape 3 : Chercher les tableaux
        print("📊 Étape 3 : Recherche de tableaux...")
        tables = soup.find_all('table')
        print(f"   Nombre de tableaux trouvés : {len(tables)}")
        
        if len(tables) == 0:
            print(f"   ❌ AUCUN TABLEAU TROUVÉ")
            print(f"\n   HTML brut (500 premiers caractères) :")
            print(f"   {response.text[:500]}")
            return
        
        print(f"\n📋 Étape 4 : Analyse du premier tableau...")
        table = tables[0]
        
        # Afficher les classes du tableau
        if table.get('class'):
            print(f"   Classes du tableau : {table.get('class')}")
        if table.get('id'):
            print(f"   ID du tableau : {table.get('id')}")
        
        # Chercher les lignes
        rows = table.find_all('tr')
        print(f"   Nombre de lignes : {len(rows)}")
        
        if len(rows) == 0:
            print(f"   ❌ Aucune ligne trouvée dans le tableau")
            return
        
        print(f"\n📝 Étape 5 : Affichage des 5 premières lignes...")
        for i, row in enumerate(rows[:5]):
            print(f"\n   === Ligne {i} ===")
            cells = row.find_all(['td', 'th'])
            print(f"   Nombre de cellules : {len(cells)}")
            
            for j, cell in enumerate(cells):
                cell_text = cell.get_text(strip=True)[:50]
                cell_html = str(cell)[:100]
                print(f"   Cellule {j}: '{cell_text}'")
                if j < 3:  # Afficher le HTML pour les 3 premières
                    print(f"      HTML : {cell_html}")
        
        # Étape 6 : Tester le parsing
        print(f"\n🧪 Étape 6 : Test du parsing sur les lignes 1-5...")
        
        for i, row in enumerate(rows[1:6], start=1):  # Ignorer l'en-tête
            cells = row.find_all('td')
            
            if len(cells) < 3:
                print(f"   Ligne {i}: Moins de 3 cellules, skip")
                continue
            
            print(f"\n   === Ligne {i} (données) ===")
            
            # Cellule 0 : Position
            pos_cell = cells[0]
            pos_text = pos_cell.get_text(separator='|', strip=True)
            print(f"   Position (texte) : '{pos_text}'")
            print(f"   Position (HTML) : {str(pos_cell)[:150]}")
            
            current_match = re.search(r'^(\d+)\.', pos_text)
            if current_match:
                current_pos = int(current_match.group(1))
                print(f"   ✅ Position actuelle extraite : {current_pos}")
            else:
                print(f"   ❌ Impossible d'extraire la position")
            
            # Chercher la position précédente
            prev_match = re.search(r'\(([^)]+)\)', pos_text)
            if prev_match:
                prev_value = prev_match.group(1).strip()
                print(f"   ✅ Position précédente trouvée : '{prev_value}'")
            else:
                print(f"   ⚠️ Pas de position précédente trouvée")
            
            # Cellule 2 : Titre et artiste
            if len(cells) > 2:
                title_cell = cells[2]
                cell_text = title_cell.get_text(separator='|', strip=True)
                print(f"   Titre/Artiste (texte) : '{cell_text[:100]}'")
                print(f"   Titre/Artiste (HTML) : {str(title_cell)[:200]}")
                
                parts = [p.strip() for p in cell_text.split('|') if p.strip()]
                print(f"   Parties séparées : {parts[:5]}")
                
                if len(parts) >= 2:
                    print(f"   ✅ Titre : '{parts[0]}'")
                    print(f"   ✅ Artiste : '{parts[1]}'")
        
        print(f"\n{'='*70}")
        print(f"✅ DEBUG TERMINÉ pour {country_name}")
        print(f"{'='*70}\n")
        
    except Exception as e:
        print(f"   ❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()

def main():
    print("\n" + "="*70)
    print("🔍 SCRIPT DE DEBUG ACHARTS.CO")
    print("="*70)
    
    for country_name, url in URLS_TO_TEST:
        debug_acharts(url, country_name)
        print("\n⏸️ Pause de 2 secondes avant le prochain pays...\n")
        import time
        time.sleep(2)

if __name__ == "__main__":
    main()