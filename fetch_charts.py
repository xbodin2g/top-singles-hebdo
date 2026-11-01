#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version améliorée avec scrapers robustes pour l'Europe.
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

# Configuration des sources
SOURCES = {
    "uk": {"name": "Royaume-Uni", "flag": "🇬🇧", "url": "https://www.officialcharts.com/charts/singles-chart/", "region": "europe"},
    "de": {"name": "Allemagne", "flag": "🇩🇪", "url": "https://www.offiziellecharts.de/charts", "region": "europe"},
    "ch": {"name": "Suisse", "flag": "🇨🇭", "url": "https://www.hitparade.ch/charts/singles", "region": "europe"},
    "us": {"name": "États-Unis", "flag": "🇺🇸", "url": "https://www.billboard.com/charts/hot-100/", "region": "anglo"},
    "fr": {"name": "France", "flag": "🇫🇷", "url": "https://snepmusique.com/les-tops/le-top-de-la-semaine/top-singles/", "region": "europe"},
    "br": {"name": "Brésil", "flag": "🇧🇷", "url": "https://pro-musicabr.org.br/home/top-50-streaming/", "region": "latam"}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def get_week_info():
    """Obtient les informations de la semaine en cours"""
    now = datetime.now()
    week_number = now.isocalendar()[1]
    year = now.year
    return {
        "week": week_number,
        "year": year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {week_number}/{year}"
    }

def fetch_with_retry(url, max_retries=3, timeout=30):
    """Fetch avec retry et gestion d'erreurs"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            print(f"    ⏱️ Timeout (tentative {attempt + 1}/{max_retries})")
        except requests.exceptions.RequestException as e:
            print(f"    ❌ Erreur réseau (tentative {attempt + 1}/{max_retries}): {str(e)[:100]}")
        
        if attempt < max_retries - 1:
            import time
            time.sleep(2 * (attempt + 1))  # Délai croissant
    
    return None

def scrape_uk_official_charts():
    """Scrape Official Charts UK - Version améliorée"""
    print("  🔍 Analyse de la structure UK...")
    
    response = fetch_with_retry(SOURCES["uk"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    # Méthode 1 : Chercher les articles avec "Number X"
    articles = soup.find_all(['article', 'div'], class_=re.compile(r'chart|song|track', re.I))
    
    if not articles:
        # Méthode 2 : Chercher dans tout le HTML
        articles = soup.find_all(['article', 'div'])
    
    for article in articles[:100]:
        text = article.get_text()
        
        # Pattern : Number X suivi de titre et artiste
        rank_match = re.search(r'Number\s+(\d+)', text, re.I)
        if rank_match:
            rank = int(rank_match.group(1))
            
            # Extraire les lignes de texte
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            title = ""
            artist = ""
            lw = None
            peak = None
            weeks = None
            
            # Chercher le titre (généralement après "Number X")
            for i, line in enumerate(lines):
                if 'Number' in line and i + 1 < len(lines):
                    title = lines[i + 1]
                    if i + 2 < len(lines):
                        artist = lines[i + 2]
                    break
            
            # Chercher les métadonnées
            lw_match = re.search(r'LW:\s*(\d+)', text, re.I)
            peak_match = re.search(r'Peak:\s*(\d+)', text, re.I)
            weeks_match = re.search(r'Weeks:\s*(\d+)', text, re.I)
            
            if lw_match:
                lw = int(lw_match.group(1))
            if peak_match:
                peak = int(peak_match.group(1))
            if weeks_match:
                weeks = int(weeks_match.group(1))
            
            if title and artist:
                movement = "same"
                if lw:
                    if lw > rank:
                        movement = "up"
                    elif lw < rank:
                        movement = "down"
                    else:
                        movement = "same"
                
                entries.append({
                    "position": rank,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": lw,
                    "movement": movement,
                    "weeksOnChart": weeks if weeks else 1,
                    "peakPosition": peak if peak else rank
                })
                
                if len(entries) >= 50:
                    break
    
    print(f"    📊 {len(entries)} entrées trouvées avec la méthode articles")
    
    # Méthode 3 : Fallback avec regex sur le HTML brut
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode regex fallback...")
        entries = []
        text = response.text
        
        # Pattern plus flexible
        pattern = r'Number\s+(\d+).*?<h[23][^>]*>(.*?)</h[23]>.*?<p[^>]*>(.*?)</p>'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        
        for rank_str, title, artist in matches[:50]:
            entries.append({
                "position": int(rank_str),
                "track": {"title": title.strip(), "artist": artist.strip()},
                "previousPosition": None,
                "movement": "same",
                "weeksOnChart": 1,
                "peakPosition": int(rank_str)
            })
        
        print(f"    📊 {len(entries)} entrées trouvées avec la méthode regex")
    
    return entries[:50]

def scrape_germany_offizielle_charts():
    """Scrape Offizielle Charts Allemagne - Version améliorée"""
    print("  🔍 Analyse de la structure Allemagne...")
    
    response = fetch_with_retry(SOURCES["de"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    # Chercher tous les tableaux
    tables = soup.find_all('table')
    print(f"    📋 {len(tables)} tableaux trouvés")
    
    for table_idx, table in enumerate(tables):
        rows = table.find_all('tr')
        
        for row in rows[:60]:
            cells = row.find_all(['td', 'th'])
            
            if len(cells) >= 3:
                # Colonne 0 : rang actuel
                rank_text = cells[0].get_text(strip=True)
                
                if rank_text.isdigit():
                    rank = int(rank_text)
                    
                    # Colonne 1 : rang précédent (parfois vide)
                    prev_rank = None
                    if len(cells) > 1:
                        prev_text = cells[1].get_text(strip=True)
                        if prev_text.isdigit():
                            prev_rank = int(prev_text)
                    
                    # Colonne 2 ou 3 : artiste et titre
                    info_cell = None
                    for i in range(2, min(len(cells), 4)):
                        if len(cells[i].get_text(strip=True)) > 5:
                            info_cell = cells[i]
                            break
                    
                    if info_cell:
                        # Extraire le texte complet
                        full_text = info_cell.get_text(separator='|', strip=True)
                        parts = [p.strip() for p in full_text.split('|') if p.strip()]
                        
                        title = ""
                        artist = ""
                        
                        if len(parts) >= 2:
                            # Généralement : Artiste | Titre | Label
                            artist = parts[0]
                            title = parts[1]
                        elif len(parts) == 1:
                            # Essayer de séparer par des patterns
                            text = parts[0]
                            # Pattern : ArtisteTitre ou Artiste - Titre
                            split_match = re.split(r'\s*[-–—]\s*|\s{2,}', text, maxsplit=1)
                            if len(split_match) == 2:
                                artist = split_match[0].strip()
                                title = split_match[1].strip()
                            else:
                                title = text
                        
                        # Extraire les métadonnées
                        weeks_match = re.search(r'In Charts:\s*(\d+)\s*W', full_text, re.I)
                        peak_match = re.search(r'Peak:\s*(\d+)', full_text, re.I)
                        
                        weeks = int(weeks_match.group(1)) if weeks_match else 1
                        peak = int(peak_match.group(1)) if peak_match else rank
                        
                        if title and artist:
                            movement = "same"
                            if prev_rank:
                                if prev_rank > rank:
                                    movement = "up"
                                elif prev_rank < rank:
                                    movement = "down"
                            
                            entries.append({
                                "position": rank,
                                "track": {"title": title, "artist": artist},
                                "previousPosition": prev_rank,
                                "movement": movement,
                                "weeksOnChart": weeks,
                                "peakPosition": peak
                            })
                            
                            if len(entries) >= 50:
                                break
        
        if len(entries) >= 50:
            break
    
    print(f"    📊 {len(entries)} entrées trouvées dans les tableaux")
    
    # Fallback : regex sur le HTML brut
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode regex fallback...")
        entries = []
        text = response.text
        
        # Pattern pour extraire les données des tableaux
        row_pattern = r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>'
        matches = re.findall(row_pattern, text, re.DOTALL | re.IGNORECASE)
        
        for rank_str, prev_str, info in matches[:50]:
            # Nettoyer le HTML
            info_clean = re.sub(r'<[^>]+>', ' ', info)
            info_clean = re.sub(r'\s+', ' ', info_clean).strip()
            
            # Extraire artiste et titre
            parts = info_clean.split('  ')  # Double espace comme séparateur
            artist = parts[0].strip() if len(parts) > 0 else ""
            title = parts[1].strip() if len(parts) > 1 else ""
            
            if artist and title:
                prev_rank = int(prev_str) if prev_str.isdigit() else None
                
                entries.append({
                    "position": int(rank_str),
                    "track": {"title": title, "artist": artist},
                    "previousPosition": prev_rank,
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": int(rank_str)
                })
        
        print(f"    📊 {len(entries)} entrées trouvées avec la méthode regex")
    
    return entries[:50]

def scrape_swiss_hitparade():
    """Scrape Hitparade Suisse - Version améliorée"""
    print("  🔍 Analyse de la structure Suisse...")
    
    response = fetch_with_retry(SOURCES["ch"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    # Méthode 1 : Tableaux
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        
        for row in rows[:60]:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                rank_text = cells[0].get_text(strip=True)
                
                if rank_text.isdigit():
                    rank = int(rank_text)
                    
                    # Extraire tout le texte de la ligne
                    row_text = row.get_text(separator='|', strip=True)
                    parts = [p.strip() for p in row_text.split('|') if p.strip()]
                    
                    title = ""
                    artist = ""
                    is_new = False
                    
                    # Pattern suisse : rang | mouvement | artiste | titre | ...
                    if len(parts) >= 4:
                        # Vérifier si c'est une nouvelle entrée
                        if 'neu' in parts[1].lower() or 'new' in parts[1].lower():
                            is_new = True
                        
                        # Artiste et titre
                        artist = parts[2] if len(parts) > 2 else ""
                        title = parts[3] if len(parts) > 3 else ""
                    
                    # Extraire semaines et peak
                    weeks_match = re.search(r'W\s*(\d+)', row_text)
                    peak_match = re.search(r'P\s*(\d+)', row_text)
                    
                    weeks = int(weeks_match.group(1)) if weeks_match else 1
                    peak = int(peak_match.group(1)) if peak_match else rank
                    
                    if title and artist:
                        movement = "new" if is_new else "same"
                        prev_rank = None if is_new else rank
                        
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist},
                            "previousPosition": prev_rank,
                            "movement": movement,
                            "weeksOnChart": weeks,
                            "peakPosition": peak
                        })
                        
                        if len(entries) >= 50:
                            break
        
        if len(entries) >= 50:
            break
    
    print(f"    📊 {len(entries)} entrées trouvées dans les tableaux")
    
    # Méthode 2 : Fallback avec divs
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode divs fallback...")
        entries = []
        
        # Chercher des divs avec des classes de chart
        chart_items = soup.find_all('div', class_=re.compile(r'chart|entry|song', re.I))
        
        for item in chart_items[:50]:
            text = item.get_text(separator='|', strip=True)
            parts = [p.strip() for p in text.split('|') if p.strip()]
            
            if len(parts) >= 3:
                # Chercher le rang
                rank = None
                for part in parts:
                    if part.isdigit():
                        rank = int(part)
                        break
                
                if rank:
                    # Extraire artiste et titre
                    artist = parts[1] if len(parts) > 1 else ""
                    title = parts[2] if len(parts) > 2 else ""
                    
                    if artist and title:
                        entries.append({
                            "position": rank,
                            "track": {"title": title, "artist": artist},
                            "previousPosition": None,
                            "movement": "same",
                            "weeksOnChart": 1,
                            "peakPosition": rank
                        })
        
        print(f"    📊 {len(entries)} entrées trouvées avec la méthode divs")
    
    return entries[:50]

def scrape_france_snep():
    """Scrape SNEP France - Version améliorée avec plusieurs stratégies"""
    print("  🔍 Analyse de la structure France (SNEP)...")
    
    response = fetch_with_retry(SOURCES["fr"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    # Méthode 1 : Chercher des données JSON embarquées
    scripts = soup.find_all('script')
    
    for script in scripts:
        if script.string:
            # Chercher des patterns JSON
            json_patterns = [
                r'var\s+chartData\s*=\s*(\[[\s\S]*?\]);',
                r'window\.chartData\s*=\s*(\[[\s\S]*?\]);',
                r'data:\s*(\[[\s\S]*?\])',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, script.string)
                for match in matches:
                    try:
                        # Essayer de parser le JSON
                        data = json.loads(match)
                        if isinstance(data, list):
                            for item in data[:50]:
                                if isinstance(item, dict):
                                    title = item.get('title', '') or item.get('titre', '')
                                    artist = item.get('artist', '') or item.get('artiste', '')
                                    
                                    if title and artist:
                                        entries.append({
                                            "position": len(entries) + 1,
                                            "track": {"title": title, "artist": artist},
                                            "previousPosition": None,
                                            "movement": "same",
                                            "weeksOnChart": 1,
                                            "peakPosition": len(entries) + 1
                                        })
                    except:
                        continue
    
    print(f"    📊 {len(entries)} entrées trouvées dans les scripts JSON")
    
    # Méthode 2 : Chercher dans le HTML avec des patterns
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode patterns HTML...")
        
        # Chercher des éléments avec des classes spécifiques
        selectors = [
            'div[class*="chart"]',
            'div[class*="top"]',
            'article[class*="single"]',
            'li[class*="track"]',
        ]
        
        for selector in selectors:
            items = soup.select(selector)
            
            for item in items[:50]:
                text = item.get_text(separator='|', strip=True)
                parts = [p.strip() for p in text.split('|') if p.strip()]
                
                if len(parts) >= 2:
                    # Chercher un rang
                    rank = None
                    for i, part in enumerate(parts):
                        if part.isdigit() and int(part) <= 100:
                            rank = int(part)
                            break
                    
                    if rank:
                        # Extraire artiste et titre
                        artist = ""
                        title = ""
                        
                        for i in range(len(parts) - 1):
                            if len(parts[i]) > 3 and len(parts[i+1]) > 3:
                                artist = parts[i]
                                title = parts[i+1]
                                break
                        
                        if artist and title:
                            entries.append({
                                "position": rank,
                                "track": {"title": title, "artist": artist},
                                "previousPosition": None,
                                "movement": "same",
                                "weeksOnChart": 1,
                                "peakPosition": rank
                            })
                            
                            if len(entries) >= 50:
                                break
            
            if len(entries) >= 50:
                break
        
        print(f"    📊 {len(entries)} entrées trouvées avec les patterns HTML")
    
    # Méthode 3 : Fallback avec regex sur le texte brut
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode regex texte brut...")
        text = response.text
        
        # Pattern pour extraire des lignes de classement
        lines = text.split('\n')
        current_rank = 0
        
        for i, line in enumerate(lines):
            # Chercher un rang seul sur une ligne
            if re.match(r'^\s*(\d{1,2})\s*$', line.strip()):
                current_rank = int(line.strip())
                
                # Chercher artiste et titre dans les lignes suivantes
                artist = ""
                title = ""
                
                for j in range(i+1, min(i+10, len(lines))):
                    next_line = lines[j].strip()
                    
                    if next_line and len(next_line) > 3 and not next_line.isdigit():
                        if not artist:
                            artist = next_line
                        elif not title:
                            title = next_line
                            break
                
                if artist and title and current_rank > 0:
                    entries.append({
                        "position": current_rank,
                        "track": {"title": title, "artist": artist},
                        "previousPosition": None,
                        "movement": "same",
                        "weeksOnChart": 1,
                        "peakPosition": current_rank
                    })
                    
                    if len(entries) >= 50:
                        break
        
        print(f"    📊 {len(entries)} entrées trouvées avec la méthode regex")
    
    return entries[:50]

def scrape_billboard_hot100():
    """Scrape Billboard Hot 100 - Version améliorée"""
    print("  🔍 Analyse de la structure Billboard...")
    
    response = fetch_with_retry(SOURCES["us"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    # Méthode 1 : Chercher les éléments de chart
    chart_items = soup.find_all(['li', 'div'], class_=re.compile(r'chart|result|song', re.I))
    
    for item in chart_items[:100]:
        text = item.get_text()
        
        # Pattern Billboard : ### Titre puis Artiste
        if '###' in text:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            title = ""
            artist = ""
            
            for i, line in enumerate(lines):
                if '###' in line:
                    title_match = re.search(r'###\s*(.+)', line)
                    if title_match:
                        title = title_match.group(1).strip()
                        
                        # Chercher l'artiste dans les lignes suivantes
                        for j in range(i+1, min(i+5, len(lines))):
                            if len(lines[j]) > 3 and not lines[j].startswith('#'):
                                artist = lines[j]
                                break
                        break
            
            if title and artist:
                entries.append({
                    "position": len(entries) + 1,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": None,
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": len(entries) + 1
                })
                
                if len(entries) >= 50:
                    break
    
    print(f"    📊 {len(entries)} entrées trouvées")
    
    # Méthode 2 : Fallback avec regex
    if len(entries) < 10:
        print("  🔄 Utilisation de la méthode regex fallback...")
        entries = []
        text = response.text
        
        # Pattern pour extraire les données
        pattern = r'<h3[^>]*>(.*?)</h3>.*?<span[^>]*>(.*?)</span>'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        
        for title, artist in matches[:50]:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            artist_clean = re.sub(r'<[^>]+>', '', artist).strip()
            
            if title_clean and artist_clean:
                entries.append({
                    "position": len(entries) + 1,
                    "track": {"title": title_clean, "artist": artist_clean},
                    "previousPosition": None,
                    "movement": "same",
                    "weeksOnChart": 1,
                    "peakPosition": len(entries) + 1
                })
        
        print(f"    📊 {len(entries)} entrées trouvées avec la méthode regex")
    
    return entries[:50]

def scrape_brazil_promusica():
    """Scrape Pro-Música Brasil - Version qui fonctionne bien"""
    print("  🔍 Analyse de la structure Brésil...")
    
    response = fetch_with_retry(SOURCES["br"]["url"])
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    
    for table in soup.find_all('table'):
        for row in table.find_all('tr', limit=51):
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                rank_text = cells[0].get_text(strip=True)
                
                if rank_text.isdigit():
                    rank = int(rank_text)
                    artist_cell = cells[2] if len(cells) > 2 else None
                    
                    if artist_cell:
                        artist_strong = artist_cell.find('strong')
                        
                        if artist_strong:
                            artist = artist_strong.get_text(strip=True)
                            title_parts = []
                            
                            for elem in artist_cell.descendants:
                                if isinstance(elem, str) and elem.strip():
                                    text = elem.strip()
                                    if text != artist and text:
                                        title_parts.append(text)
                            
                            title = ' '.join(title_parts) if title_parts else ""
                            
                            if title:
                                entries.append({
                                    "position": rank,
                                    "track": {"title": title, "artist": artist},
                                    "previousPosition": None,
                                    "movement": "same",
                                    "weeksOnChart": 1,
                                    "peakPosition": rank
                                })
    
    print(f"    📊 {len(entries)} entrées trouvées")
    return entries[:50]

def generate_demo_data(country_code, count=20):
    """Génère des données de démonstration réalistes"""
    demo_data = {
        "uk": {
            "titles": ["Babydoll", "Housewife", "Stop The Wedding", "Expectations", "Great Expectation", 
                      "Night Drive", "Golden Hour", "Silver Lining", "Wildfire", "Dancing Alone",
                      "Lumière", "Midnight Gold", "Baila Conmigo", "Évidence", "Rio de Janeiro",
                      "Electric Heart", "Soleil levant", "Northern Sky", "Doucement", "Paris Minuit"],
            "artists": ["Jamie Miller", "Tate McRae", "Ashe", "Olivia Rodrigo", "Sienna Spiro",
                       "Kai Rivers", "Aurora West", "Noor", "J.B. Monroe", "Mavie",
                       "Alya Nova", "The Amber Lines", "Luz Marina", "Léa Volney", "Marisol",
                       "Vesper", "Mika Ange", "Elias Vale", "Naya", "Jules et Lila"]
        },
        "de": {
            "titles": ["Housewife", "Dai dai", "Ain't In LA", "Self Aware", "Movin' To The Sun",
                      "Mr. Brightside", "Patient Zero", "Mi chico", "Mama (Remix)", "Stop The Wedding",
                      "Verschwommen", "Nicole Kidman", "Assalamualeikum", "Lush Life", "Dracula",
                      "Ordinary", "Expectations", "Issa", "Bby Wow", "Beauty And A Beat"],
            "artists": ["Tate McRae", "Shakira x Burna Boy", "Adéla", "Temper City", "Hugel",
                       "The Killers", "Taylor Swift", "DJ Goja", "Symba", "Ashe",
                       "Ski Aggu & Ericson", "Adéla", "Capital Bra / Samra", "Zara Larsson", "Tame Impala",
                       "Alex Warren", "Olivia Rodrigo", "Sido", "Karol G", "Justin Bieber"]
        },
        "ch": {
            "titles": ["Housewife", "Bby Wow", "Dai dai", "Mi chico", "Nicole Kidman",
                      "Lumière", "Midnight Gold", "Baila Conmigo", "Évidence", "Golden Hour",
                      "Rio de Janeiro", "Silver Lining", "La Vida Entera", "Electric Heart", "Soleil levant",
                      "Northern Sky", "Doucement", "Wildfire", "Paris Minuit", "Oceano Caminho"],
            "artists": ["Tate McRae", "Karol G, Judeline & Rusowsky", "Shakira x Burna Boy", "DJ Goja", "Adéla",
                       "Alya Nova", "The Amber Lines", "Luz Marina", "Léa Volney", "Aurora West",
                       "Marisol", "Noor", "Sofía del Mar", "Vesper", "Mika Ange",
                       "Elias Vale", "Naya", "J.B. Monroe", "Jules et Lila", "Bela Costa"]
        },
        "us": {
            "titles": ["Choosin' Texas", "Housewife", "Expectations", "Die With A Smile", "Birds Of A Feather",
                      "APT.", "Luther", "Timeless", "Sailor Song", "Taste",
                      "Beautiful Things", "Espresso", "Too Sweet", "Lose Control", "Stick Season",
                      "Cruel Summer", "Flowers", "Anti-Hero", "As It Was", "Heat Waves"],
            "artists": ["Ella Langley", "Tate McRae", "Olivia Rodrigo & Chappell Roan", "Lady Gaga & Bruno Mars", "Billie Eilish",
                       "Rosé & Bruno Mars", "SZA", "The Weeknd", "Gigi Perez", "Sabrina Carpenter",
                       "Benson Boone", "Sabrina Carpenter", "Hozier", "Teddy Swims", "Noah Kahan",
                       "Taylor Swift", "Miley Cyrus", "Taylor Swift", "Harry Styles", "Glass Animals"]
        },
        "fr": {
            "titles": ["Maladie", "Sexy Nana", "Dai Dai", "Pilé", "Sicario",
                      "Pocahontas", "Melodrama", "Bande organisée", "Je te promets", "Dernière danse",
                      "Tout oublier", "Au DD", "La grenade", "Papaoutai", "Formidable",
                      "Alors on danse", "Dernier jour", "Champs-Élysées", "Joe le taxi", "L'hymne de nos campagnes"],
            "artists": ["Mauvais Djo", "Aya Nakamura feat. La Rvfleuze", "Shakira & Burna Boy", "Mauvais Djo", "Timal",
                       "PLK", "Theodora", "SCH", "Johnny Hallyday", "Indila",
                       "Angèle", "PNL", "Clara Luciani", "Stromae", "Stromae",
                       "Stromae", "Grand Corps Malade", "Joe Dassin", "Vanessa Paradis", "Tryo"]
        }
    }
    
    data = demo_data.get(country_code, demo_data["uk"])
    entries = []
    
    for i in range(min(count, len(data["titles"]))):
        entries.append({
            "position": i + 1,
            "track": {
                "title": data["titles"][i],
                "artist": data["artists"][i]
            },
            "previousPosition": None if i == 0 else i + 2,
            "movement": "same" if i == 0 else "up" if i % 3 == 0 else "down",
            "weeksOnChart": 1 if i == 0 else (i % 10) + 1,
            "peakPosition": max(1, i + 1 - (i % 5))
        })
    
    return entries

def main():
    """Fonction principale de collecte"""
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    week_info = get_week_info()
    
    charts_data = {
        "meta": {
            "weekLabel": week_info["label"],
            "week": week_info["week"],
            "year": week_info["year"],
            "updatedAt": week_info["date"],
            "sourceNote": "",
            "successfulSources": [],
            "failedSources": []
        },
        "countries": {},
        "regions": {
            "europe": {"label": "Europe", "countries": []},
            "anglo": {"label": "Pays anglo-saxons", "countries": []},
            "latam": {"label": "Amérique du Sud", "countries": []}
        }
    }
    
    # Configurer les scrapers
    scrapers = {
        "uk": scrape_uk_official_charts,
        "de": scrape_germany_offizielle_charts,
        "ch": scrape_swiss_hitparade,
        "us": scrape_billboard_hot100,
        "fr": scrape_france_snep,
        "br": scrape_brazil_promusica
    }
    
    # Traiter chaque source
    for code, country_info in SOURCES.items():
        print(f"\n📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        # Essayer de scraper
        if code in scrapers:
            entries = scrapers[code]()
            is_demo = False
        else:
            entries = []
            is_demo = True
        
        # Si pas de données ou données insuffisantes, utiliser le fallback
        if not entries or len(entries) < 5:
            print(f"  ⚠️ Données insuffisantes ({len(entries) if entries else 0} trouvées), utilisation du fallback")
            entries = generate_demo_data(code, count=20)
            is_demo = True
            charts_data["meta"]["failedSources"].append(country_info["name"])
        else:
            print(f"  ✅ {len(entries)} entrées collectées avec succès")
            charts_data["meta"]["successfulSources"].append(country_info["name"])
        
        # Ajouter aux données
        charts_data["countries"][code] = {
            "name": country_info["name"],
            "flag": country_info["flag"],
            "region": country_info["region"],
            "chart": entries,
            "isDemo": is_demo
        }
        
        # Ajouter à la région
        charts_data["regions"][country_info["region"]]["countries"].append(code)
    
    # Générer le message de note
    successful = charts_data["meta"]["successfulSources"]
    failed = charts_data["meta"]["failedSources"]
    
    if successful and failed:
        charts_data["meta"]["sourceNote"] = (
            f"✅ Sources officielles : {', '.join(successful)}. "
            f"⚠️ Données de démonstration : {', '.join(failed)}."
        )
    elif successful:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources officielles ont été collectées : {', '.join(successful)}."
    else:
        charts_data["meta"]["sourceNote"] = "⚠️ Toutes les sources utilisent des données de démonstration."
    
    # Sauvegarder
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ Collecte terminée")
    print(f"   - {len(successful)} sources officielles réussies")
    print(f"   - {len(failed)} sources avec données de démonstration")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()