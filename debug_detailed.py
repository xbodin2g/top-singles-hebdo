#!/usr/bin/env python3
"""Debug détaillé pour voir la structure réelle autour des positions"""

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

def debug_official_charts_detailed():
    print("\n" + "="*70)
    print("🔍 DEBUG DÉTAILLÉ Official Charts UK Indie")
    print("="*70)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Referer': 'https://www.officialcharts.com/',
    }
    
    url = "https://www.officialcharts.com/charts/independent-singles-chart/"
    
    try:
        response = scraper.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Chercher les 5 premiers "Number" et afficher 15 lignes autour
        print("\n📋 Structure autour des 5 premiers 'Number' :\n")
        
        number_positions = []
        for i, line in enumerate(lines):
            if line == 'Number':
                number_positions.append(i)
                if len(number_positions) >= 5:
                    break
        
        for pos in number_positions[:3]:
            print(f"--- Position {pos} ---")
            start = max(0, pos - 2)
            end = min(len(lines), pos + 15)
            for i in range(start, end):
                marker = ">>> " if i == pos else "    "
                print(f"{marker}[{i:3d}] {lines[i][:80]}")
            print()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

def debug_billboard_detailed():
    print("\n" + "="*70)
    print("🔍 DEBUG DÉTAILLÉ Billboard Brasil Hot 100")
    print("="*70)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Accept-Language': 'pt-BR,pt;q=0.9',
        'Referer': 'https://billboard.com.br/',
    }
    
    url = "https://billboard.com.br/billboard-brasil-hot-100/"
    
    try:
        response = scraper.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Chercher les positions et afficher 20 lignes autour
        print("\n📋 Structure autour des 3 premières positions :\n")
        
        # Trouver les premières positions (nombres seuls entre 1 et 100)
        position_indices = []
        for i, line in enumerate(lines):
            if re.match(r'^\d+$', line) and 1 <= int(line) <= 3:
                position_indices.append(i)
                if len(position_indices) >= 3:
                    break
        
        for pos in position_indices:
            print(f"--- Position {pos} (valeur: {lines[pos]}) ---")
            start = max(0, pos - 3)
            end = min(len(lines), pos + 20)
            for i in range(start, end):
                marker = ">>> " if i == pos else "    "
                print(f"{marker}[{i:3d}] {lines[i][:80]}")
            print()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_official_charts_detailed()
    debug_billboard_detailed()