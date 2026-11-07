#!/usr/bin/env python3
"""Debug pour voir le HTML réel renvoyé par cloudscraper"""

import re

try:
    import cloudscraper
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False
        }
    )
except ImportError:
    print("❌ cloudscraper non installé")
    exit(1)

from bs4 import BeautifulSoup

def debug_official_charts():
    print("\n" + "="*70)
    print("🔍 DEBUG Official Charts UK Indie")
    print("="*70)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Referer': 'https://www.officialcharts.com/',
    }
    
    url = "https://www.officialcharts.com/charts/independent-singles-chart/"
    
    try:
        response = scraper.get(url, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Taille HTML: {len(response.text)} caractères\n")
        
        if response.status_code != 200:
            print(f"❌ Erreur HTTP {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Chercher "Number" dans le texte
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        print(f"Nombre de lignes: {len(lines)}\n")
        
        # Afficher les 50 premières lignes
        print("📋 50 premières lignes :")
        for i, line in enumerate(lines[:50], 1):
            print(f"  [{i:3d}] {line[:80]}")
        
        # Chercher "Number" spécifiquement
        print("\n🔍 Recherche de 'Number' :")
        number_count = 0
        for i, line in enumerate(lines):
            if 'Number' in line:
                number_count += 1
                if number_count <= 5:
                    print(f"  [{i:3d}] {line}")
        
        if number_count == 0:
            print("  ❌ Aucun 'Number' trouvé")
            print("\n🔍 Recherche d'alternatives :")
            
            # Chercher des patterns alternatifs
            for i, line in enumerate(lines):
                if re.match(r'^\d+$', line):
                    print(f"  [{i:3d}] Nombre seul: {line}")
                elif 'LW:' in line or 'Peak:' in line or 'Weeks:' in line:
                    print(f"  [{i:3d}] Métadonnées: {line[:60]}")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

def debug_billboard_brasil():
    print("\n" + "="*70)
    print("🔍 DEBUG Billboard Brasil Hot 100")
    print("="*70)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Accept-Language': 'pt-BR,pt;q=0.9',
        'Referer': 'https://billboard.com.br/',
    }
    
    url = "https://billboard.com.br/billboard-brasil-hot-100/"
    
    try:
        response = scraper.get(url, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Taille HTML: {len(response.text)} caractères\n")
        
        if response.status_code != 200:
            print(f"❌ Erreur HTTP {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        print(f"Nombre de lignes: {len(lines)}\n")
        
        # Afficher les 50 premières lignes
        print("📋 50 premières lignes :")
        for i, line in enumerate(lines[:50], 1):
            print(f"  [{i:3d}] {line[:80]}")
        
        # Chercher des nombres seuls
        print("\n🔍 Recherche de nombres seuls (positions) :")
        number_count = 0
        for i, line in enumerate(lines):
            if re.match(r'^\d+$', line):
                number_count += 1
                if number_count <= 10:
                    print(f"  [{i:3d}] {line}")
        
        if number_count == 0:
            print("  ❌ Aucun nombre seul trouvé")
        
        # Chercher "Últ. Semana"
        print("\n🔍 Recherche de 'Últ. Semana' :")
        ult_count = 0
        for i, line in enumerate(lines):
            if 'Últ' in line or 'Semana' in line:
                ult_count += 1
                if ult_count <= 5:
                    print(f"  [{i:3d}] {line[:80]}")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_official_charts()
    debug_billboard_brasil()