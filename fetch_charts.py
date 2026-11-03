def fetch_uk_indie_wayback(country_name):
    """Récupère UK Indie via Wayback Machine (contourne le 403)"""
    print(f"  🔍 Scraping UK Indie via Wayback Machine pour {country_name}...")
    
    # URL Wayback Machine qui récupère la dernière archive de 2026
    wayback_url = "https://web.archive.org/web/2026/https://www.officialcharts.com/charts/independent-singles-chart/"
    
    try:
        response = requests.get(wayback_url, headers=HEADERS, timeout=45, allow_redirects=True)
        
        if response.status_code == 404:
            print(f"    ❌ Pas d'archive trouvée (404)")
            return []
        
        response.raise_for_status()
        text = response.text
        
        print(f"    📄 Taille HTML : {len(text)} caractères")
        
        # Parser le contenu (même structure que le site officiel)
        entries = []
        
        # Pattern 1 : Number **X**
        sections = re.split(r'Number\s+\*\*(\d+)\*\*', text)
        
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break
            
            rank = int(sections[i])
            content = sections[i + 1]
            
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            title = lines[0]
            artist = lines[1]
            
            lw_match = re.search(r'LW:\s*(\d+)', content)
            peak_match = re.search(r'Peak:\s*(\d+)', content)
            weeks_match = re.search(r'Weeks:\s*(\d+)', content)
            
            lw = int(lw_match.group(1)) if lw_match else None
            peak = int(peak_match.group(1)) if peak_match else rank
            weeks = int(weeks_match.group(1)) if weeks_match else 1
            
            movement = calculate_movement(rank, lw)
            
            entries.append({
                "position": rank,
                "track": {"title": title, "artist": artist},
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "wayback_official_charts"
            })
        
        entries.sort(key=lambda x: x["position"])
        entries = entries[:50]
        
        if entries:
            print(f"    ✅ {len(entries)} entrées trouvées via Wayback Machine")
            print(f"    📊 Top 3 :")
            for i, entry in enumerate(entries[:3]):
                print(f"       {entry['position']}. {entry['track']['title']} - {entry['track']['artist']} ({entry['movement']})")
            return entries
        
        print(f"    ❌ 0 entrées trouvées")
        return []
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []