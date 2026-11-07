#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version avec SNEP comme source principale pour la France.
Sources multiples : acharts.co, kworb iTunes, SNEP, Pro-Música Brasil, iTunes RSS
YouTube : API + yt-dlp comme fallback automatique
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import os
import time
import urllib.parse

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

YOUTUBE_LIMIT_PER_COUNTRY = 20
DEEZER_LIMIT_PER_COUNTRY = 20

CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "streaming_ids.json")
CACHE_MAX_AGE_DAYS = 730

SOURCES = {
    "us": {
        "name": "États-Unis", 
        "flag": "🇺🇸", 
        "region": "anglo", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/us_singles_top_100"
    },
    "fr": {
        "name": "France", 
        "flag": "🇫🇷", 
        "region": "europe", 
        "source": "snep"  # ← SNEP comme source principale
    },
    "gb": {
        "name": "Royaume-Uni", 
        "flag": "🇬🇧", 
        "region": "europe", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/uk_singles_top_75"
    },
    "de": {
        "name": "Allemagne", 
        "flag": "🇩🇪", 
        "region": "europe", 
        "source": "kworb_itunes",
        "kworb_url": "https://kworb.net/charts/itunes/de.html"
    },
    "ch": {
        "name": "Suisse", 
        "flag": "🇨🇭", 
        "region": "europe", 
        "source": "acharts",
        "acharts_url": "https://acharts.co/swiss_singles_top_100"
    },
    "br": {
        "name": "Brésil", 
        "flag": "🇧🇷", 
        "region": "latam", 
        "source": "promusica",
        "primary_url": "https://pro-musicabr.org.br/home/top-50-streaming/"
    },
    "sg": {
        "name": "Singapour", 
        "flag": "🇸🇬", 
        "region": "asia", 
        "source": "itunes_rss",
        "itunes_url": "https://itunes.apple.com/sg/rss/topsongs/limit=50/json"
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

youtube_quota_exceeded = False

# ===== GESTION DU CACHE =====

def load_cache():
    cache = {}
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"📦 Cache chargé : {len(cache)} titres en mémoire")
            cache = clean_cache(cache)
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement du cache: {e}")
            cache = {}
    else:
        print(f"📦 Pas de cache trouvé, création d'un nouveau cache")
    
    return cache

def clean_cache(cache, max_age_days=CACHE_MAX_AGE_DAYS):
    if not cache:
        return cache
    
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    cleaned_cache = {}
    removed_count = 0
    
    for key, value in cache.items():
        cached_at_str = value.get('cached_at', '2020-01-01')
        
        try:
            cached_at = datetime.strptime(cached_at_str, '%Y-%m-%d')
            
            if cached_at >= cutoff_date:
                cleaned_cache[key] = value
            else:
                removed_count += 1
        except (ValueError, TypeError):
            cleaned_cache[key] = value
    
    if removed_count > 0:
        print(f"🧹 Nettoyage automatique du cache : {removed_count} entrées supprimées (> {max_age_days} jours)")
        print(f"   Cache restant : {len(cleaned_cache)} entrées")
    
    return cleaned_cache

def save_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} titres au total")
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde du cache: {e}")

def get_cache_key(artist, title):
    artist_clean = re.sub(r'\(.*?\)', '', artist).lower().strip()
    title_clean = re.sub(r'\(.*?\)', '', title).lower().strip()
    
    artist_clean = re.sub(r'[^\w\s]', '', artist_clean).strip()
    title_clean = re.sub(r'[^\w\s]', '', title_clean).strip()
    
    return f"{artist_clean}|{title_clean}"

# ===== FONCTIONS DE BASE =====

def get_week_info():
    now = datetime.now()
    return {
        "week": now.isocalendar()[1],
        "year": now.year,
        "date": now.strftime("%Y-%m-%d"),
        "label": f"Semaine {now.isocalendar()[1]}/{now.year}"
    }

def calculate_movement(current_pos, previous_pos):
    if previous_pos is None or previous_pos == 0:
        return "new"
    if current_pos < previous_pos:
        return "up"
    elif current_pos > previous_pos:
        return "down"
    else:
        return "same"

# ===== RECHERCHE DEEZER =====

def fetch_deezer_track_id(artist, title):
    try:
        clean_title = re.sub(r'\(.*?\)', '', title).strip()
        clean_artist = re.sub(r'\(.*?\)', '', artist).strip()
        
        query = f"{clean_artist} {clean_title}"
        url = f"https://api.deezer.com/search?q={urllib.parse.quote(query)}&limit=1"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                track = data['data'][0]
                return {
                    'deezer_id': track.get('id'),
                    'deezer_url': track.get('link'),
                    'artwork': track.get('album', {}).get('cover_medium', '')
                }
    except Exception:
        pass
    
    return None

# ===== RECHERCHE YOUTUBE (API + yt-dlp FALLBACK) =====

def fetch_youtube_video_id_official(artist, title):
    global youtube_quota_exceeded
    
    # Si quota dépassé, utiliser directement yt-dlp
    if youtube_quota_exceeded:
        return fetch_youtube_video_id_ytdlp(artist, title)
    
    if not YOUTUBE_API_KEY:
        return None
    
    try:
        clean_title = re.sub(r'\(.*?\)', '', title).strip()
        clean_artist = re.sub(r'\(.*?\)', '', artist).strip()
        
        query = f"{clean_artist} {clean_title} official video"
        
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': 5,
            'key': YOUTUBE_API_KEY,
            'order': 'relevance'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        # Gestion du rate limiting (429) - fallback yt-dlp
        if response.status_code == 429:
            print(f"      ⚠️ Rate limit YouTube (429) - Tentative via yt-dlp...")
            return fetch_youtube_video_id_ytdlp(artist, title)
        
        if response.status_code == 403:
            error_data = response.json()
            error_message = error_data.get('error', {}).get('message', '')
            
            if 'quota' in error_message.lower():
                youtube_quota_exceeded = True
                print(f"      ⚠️ QUOTA YOUTUBE DÉPASSÉ - Tentative via yt-dlp...")
                return fetch_youtube_video_id_ytdlp(artist, title)
            else:
                print(f"      ⚠️ Erreur API YouTube 403: {error_message[:100]} - Tentative yt-dlp...")
                return fetch_youtube_video_id_ytdlp(artist, title)
        
        if response.status_code != 200:
            print(f"      ⚠️ Erreur API YouTube: HTTP {response.status_code} - Tentative yt-dlp...")
            return fetch_youtube_video_id_ytdlp(artist, title)
        
        data = response.json()
        items = data.get('items', [])
        
        if not items:
            return None
        
        exclude_keywords = ['lyrics', 'lyric', 'audio only', 'cover', 'live', 'karaoke', 'remix']
        
        best_video = None
        
        for item in items:
            video_title = item['snippet']['title'].lower()
            channel = item['snippet']['channelTitle'].lower()
            
            is_official = any(keyword in video_title for keyword in ['official video', 'official', 'clip officiel', 'official clip'])
            is_vevo = 'vevo' in channel
            
            is_excluded = any(keyword in video_title for keyword in exclude_keywords)
            
            if not is_excluded and (is_official or is_vevo):
                best_video = item
                break
        
        if not best_video:
            for item in items:
                video_title = item['snippet']['title'].lower()
                is_excluded = any(keyword in video_title for keyword in exclude_keywords)
                
                if not is_excluded:
                    best_video = item
                    break
        
        if best_video:
            video_id = best_video['id']['videoId']
            return {
                'youtube_id': video_id,
                'youtube_url': f"https://www.youtube.com/watch?v={video_id}"
            }
    
    except Exception as e:
        print(f"      ⚠️ Erreur YouTube API: {e} - Tentative yt-dlp...")
        return fetch_youtube_video_id_ytdlp(artist, title)
    
    return None

def fetch_youtube_video_id_ytdlp(artist, title):
    """
    Recherche YouTube via yt-dlp (fallback quand l'API échoue)
    Pas de quota, pas de clé API nécessaire
    """
    try:
        import yt_dlp
        
        clean_title = re.sub(r'\(.*?\)', '', title).strip()
        clean_artist = re.sub(r'\(.*?\)', '', artist).strip()
        
        query = f"{clean_artist} {clean_title} official video"
        
        # Configuration yt-dlp pour recherche uniquement (pas de téléchargement)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Ne pas télécharger, juste chercher
            'default_search': 'ytsearch5',  # Chercher 5 résultats
            'playlistend': 5,
            'format': 'best',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                result = ydl.extract_info(f"ytsearch5:{query}", download=False)
                
                if not result or 'entries' not in result:
                    return None
                
                exclude_keywords = ['lyrics', 'lyric', 'audio only', 'cover', 'live', 'karaoke', 'remix']
                
                for item in result['entries']:
                    if not item:
                        continue
                    
                    video_title = (item.get('title') or '').lower()
                    channel = (item.get('channel') or '').lower()
                    
                    is_official = any(keyword in video_title for keyword in 
                                    ['official video', 'official', 'clip officiel', 'official clip'])
                    is_vevo = 'vevo' in channel
                    is_excluded = any(keyword in video_title for keyword in exclude_keywords)
                    
                    if not is_excluded and (is_official or is_vevo):
                        video_id = item.get('id')
                        if video_id:
                            return {
                                'youtube_id': video_id,
                                'youtube_url': f"https://www.youtube.com/watch?v={video_id}"
                            }
                
                # Fallback : première vidéo non-exclue
                for item in result['entries']:
                    if not item:
                        continue
                    
                    video_title = (item.get('title') or '').lower()
                    is_excluded = any(keyword in video_title for keyword in exclude_keywords)
                    
                    if not is_excluded:
                        video_id = item.get('id')
                        if video_id:
                            return {
                                'youtube_id': video_id,
                                'youtube_url': f"https://www.youtube.com/watch?v={video_id}"
                            }
            
            except Exception as e:
                print(f"      ⚠️ Erreur yt-dlp: {e}")
                return None
        
        return None
    
    except ImportError:
        print(f"      ⚠️ yt-dlp non installé - fallback impossible")
        return None
    except Exception as e:
        print(f"      ⚠️ Erreur yt-dlp: {e}")
        return None

# ===== ENRICHISSEMENT AVEC CACHE =====

def enrich_with_cache(entries, cache, country_name):
    print(f"  📊 Enrichissement avec cache pour {country_name}...")
    
    youtube_count = 0
    deezer_count = 0
    youtube_from_cache = 0
    deezer_from_cache = 0
    cache_updates = 0
    
    for entry in entries:
        artist = entry['track']['artist']
        title = entry['track']['title']
        cache_key = get_cache_key(artist, title)
        
        has_youtube = bool(entry.get('youtube_id'))
        has_deezer = bool(entry.get('deezer_id'))
        
        can_search_youtube = youtube_count < YOUTUBE_LIMIT_PER_COUNTRY
        can_search_deezer = deezer_count < DEEZER_LIMIT_PER_COUNTRY
        
        if cache_key in cache:
            cached = cache[cache_key]
            
            if not has_youtube and cached.get('youtube_id'):
                entry['youtube_id'] = cached['youtube_id']
                entry['youtube_url'] = cached['youtube_url']
                has_youtube = True
                youtube_from_cache += 1
            
            if not has_deezer and cached.get('deezer_id'):
                entry['deezer_id'] = cached['deezer_id']
                entry['deezer_url'] = cached['deezer_url']
                if cached.get('artwork'):
                    entry['track']['artwork'] = cached['artwork']
                has_deezer = True
                deezer_from_cache += 1
        
        needs_update = False
        
        if not has_youtube and can_search_youtube and not youtube_quota_exceeded:
            youtube_info = fetch_youtube_video_id_official(artist, title)
            if youtube_info:
                entry['youtube_id'] = youtube_info['youtube_id']
                entry['youtube_url'] = youtube_info['youtube_url']
                youtube_count += 1
                
                if cache_key not in cache:
                    cache[cache_key] = {
                        'artist': artist,
                        'title': title,
                        'cached_at': datetime.now().strftime('%Y-%m-%d')
                    }
                cache[cache_key]['youtube_id'] = youtube_info['youtube_id']
                cache[cache_key]['youtube_url'] = youtube_info['youtube_url']
                needs_update = True
            
            time.sleep(0.5)  # Délai entre requêtes
        
        if not has_deezer and can_search_deezer:
            deezer_info = fetch_deezer_track_id(artist, title)
            if deezer_info:
                entry['deezer_id'] = deezer_info['deezer_id']
                entry['deezer_url'] = deezer_info['deezer_url']
                if deezer_info.get('artwork'):
                    entry['track']['artwork'] = deezer_info['artwork']
                deezer_count += 1
                
                if cache_key not in cache:
                    cache[cache_key] = {
                        'artist': artist,
                        'title': title,
                        'cached_at': datetime.now().strftime('%Y-%m-%d')
                    }
                cache[cache_key]['deezer_id'] = deezer_info['deezer_id']
                cache[cache_key]['deezer_url'] = deezer_info['deezer_url']
                if deezer_info.get('artwork'):
                    cache[cache_key]['artwork'] = deezer_info['artwork']
                needs_update = True
            
            time.sleep(0.2)
        
        if needs_update:
            cache_updates += 1
    
    print(f"  📊 Cache: {youtube_from_cache + deezer_from_cache} titres utilisés")
    print(f"  📊 Deezer: {deezer_count}/{min(DEEZER_LIMIT_PER_COUNTRY, len(entries))} trouvés" +
          (f" (dont {deezer_from_cache} complétés depuis le cache)" if deezer_from_cache > 0 else ""))
    print(f"  📊 YouTube: {youtube_count}/{min(YOUTUBE_LIMIT_PER_COUNTRY, len(entries))} trouvés" +
          (f" (dont {youtube_from_cache} complétés depuis le cache)" if youtube_from_cache > 0 else ""))
    
    if cache_updates > 0:
        print(f"  💾 {cache_updates} nouvelles entrées ajoutées au cache")
    
    return entries

# ===== SOURCES DE DONNÉES =====

def fetch_acharts(url, country_name):
    """
    Parse acharts.co (VERSION FINALE CORRIGÉE)
    Utilise itemprop="position" pour la position et gère les cas spéciaux
    """
    print(f"  🔍 Scraping acharts.co pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher le tableau avec id="ChartTable"
        table = soup.find('table', id='ChartTable')
        if not table:
            table = soup.find('table')
        
        if not table:
            print(f"    ❌ Aucun tableau trouvé")
            return []
        
        rows = table.find_all('tr')[1:]  # Ignorer l'en-tête
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) < 6:
                continue
            
            # ===== EXTRACTION POSITION ACTUELLE =====
            pos_cell = cells[0]
            
            # Méthode 1 : Chercher itemprop="position"
            pos_span = pos_cell.find('span', itemprop='position')
            if pos_span:
                current_pos_text = pos_span.get_text(strip=True)
                if current_pos_text.isdigit():
                    current_pos = int(current_pos_text)
                else:
                    continue
            else:
                # Méthode 2 : Regex sur le texte
                pos_text = pos_cell.get_text(separator=' ', strip=True)
                pos_match = re.match(r'^(\d+)', pos_text)
                if not pos_match:
                    continue
                current_pos = int(pos_match.group(1))
            
            if current_pos < 1 or current_pos > 100:
                continue
            
            # ===== EXTRACTION POSITION PRÉCÉDENTE =====
            previous_pos = None
            movement = "same"
            
            # Méthode 1 : Utiliser la cellule "Previous" (cells[1])
            prev_cell = cells[1]
            prev_text = prev_cell.get_text(strip=True)
            
            if prev_text and prev_text.isdigit():
                previous_pos = int(prev_text)
            else:
                # Méthode 2 : Chercher dans la cellule position
                prev_match = re.search(r'\(([^)]+)\)', pos_cell.get_text(strip=True))
                if prev_match:
                    prev_value = prev_match.group(1).strip().lower()
                    
                    if prev_value == 'new':
                        movement = "new"
                        previous_pos = None
                    elif prev_value == 're-entry' or prev_value == 're':
                        movement = "new"  # Traiter comme nouvelle entrée
                        previous_pos = None
                    elif prev_value.isdigit():
                        previous_pos = int(prev_value)
            
            # Déterminer le mouvement si on a previous_pos
            if previous_pos is not None and movement == "same":
                if previous_pos > current_pos:
                    movement = "up"
                elif previous_pos < current_pos:
                    movement = "down"
                else:
                    movement = "same"
            
            # ===== EXTRACTION TITRE ET ARTISTE =====
            title_cell = cells[2]
            
            # Chercher le titre dans itemprop="name"
            title_link = title_cell.find('a', itemprop='url')
            title_span = title_cell.find('span', itemprop='name')
            
            if title_span:
                title = title_span.get_text(strip=True)
            else:
                continue
            
            # Construire l'artiste en récupérant tout le texte après le titre
            cell_text = title_cell.get_text(separator='|', strip=True)
            parts = [p.strip() for p in cell_text.split('|') if p.strip()]
            
            if len(parts) < 2:
                continue
            
            # Ignorer les textes parasites
            skip_texts = ['peak position:', 'total weeks:', 'Longest on Chart', 
                         'Highest Debut', 'Biggest Fall', 'Best Comeback']
            
            # Trouver l'artiste (après le titre)
            artist_parts = []
            found_title = False
            
            for part in parts:
                if part == title:
                    found_title = True
                    continue
                
                if found_title:
                    # Arrêter si on rencontre un texte parasite
                    if any(skip in part for skip in skip_texts):
                        break
                    artist_parts.append(part)
            
            if not artist_parts:
                continue
            
            artist = ' '.join(artist_parts)
            
            # ===== EXTRACTION PEAK ET WEEKS =====
            peak_position = current_pos
            weeks_on_chart = 1
            
            if len(cells) > 4 and cells[4].get_text(strip=True).isdigit():
                peak_position = int(cells[4].get_text(strip=True))
            
            if len(cells) > 5 and cells[5].get_text(strip=True).isdigit():
                weeks_on_chart = int(cells[5].get_text(strip=True))
            
            # ===== VALIDATION =====
            if title and artist and len(title) > 1 and len(artist) > 1:
                entries.append({
                    "position": current_pos,
                    "track": {"title": title, "artist": artist},
                    "previousPosition": previous_pos,
                    "movement": movement,
                    "weeksOnChart": weeks_on_chart,
                    "peakPosition": peak_position,
                    "source": "acharts"
                })
        
        # Trier par position
        entries.sort(key=lambda x: x["position"])
        
        # Dédupliquer
        seen = set()
        unique_entries = []
        for entry in entries:
            if entry["position"] not in seen:
                seen.add(entry["position"])
                unique_entries.append(entry)
        
        entries = unique_entries[:100]
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        
        # Afficher quelques exemples
        if entries:
            print(f"       📊 Exemples :")
            for e in entries[:3]:
                move_symbol = "▲" if e['movement'] == 'up' else ("▼" if e['movement'] == 'down' else "●")
                print(f"          {e['position']}. {e['track']['artist']} - {e['track']['title']} {move_symbol}")
        
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []

def fetch_brazil_promusica():
    """Récupère le top brésilien via Pro-Música Brasil (VERSION CORRIGÉE)"""
    print(f"  🔍 Scraping Pro-Música Brasil...")
    
    try:
        url = "https://pro-musicabr.org.br/home/top-50-streaming/"
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher le tableau
        table = soup.find('table')
        
        if not table:
            print(f"    ❌ Aucun tableau trouvé")
            return []
        
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                # Cellule 0 : Position
                pos_text = cells[0].get_text(strip=True)
                rank_match = re.search(r'\d+', pos_text)
                
                if rank_match:
                    rank = int(rank_match.group())
                    
                    if rank <= 50:
                        # Cellule 2 : Artiste en gras + <br> + Titre
                        title_cell = cells[2]
                        cell_text = title_cell.get_text(separator='|', strip=True)
                        
                        # Séparer par |
                        parts = [p.strip() for p in cell_text.split('|') if p.strip()]
                        
                        if len(parts) >= 2:
                            artist = parts[0]
                            title = parts[1]
                            
                            if title and artist:
                                entries.append({
                                    "position": rank,
                                    "track": {"title": title, "artist": artist},
                                    "previousPosition": None,
                                    "movement": "same",
                                    "weeksOnChart": 1,
                                    "peakPosition": rank,
                                    "source": "promusica"
                                })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_kworb_itunes(url, country_name):
    print(f"  🔍 Scraping kworb.net pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        table = soup.find('table', class_='chartlist')
        
        if not table:
            table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                cells = row.find_all('td')
                
                if len(cells) >= 3:
                    pos_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', pos_text)
                    
                    if rank_match:
                        rank = int(rank_match.group())
                        
                        movement_cell = cells[1]
                        movement_text = movement_cell.get_text(strip=True)
                        
                        title_cell = cells[2]
                        title = None
                        artist = None
                        
                        title_link = title_cell.find('a')
                        
                        if title_link:
                            title = title_link.get_text(strip=True)
                            
                            artist_cell = cells[3] if len(cells) > 3 else None
                            
                            if artist_cell:
                                artist_link = artist_cell.find('a')
                                if artist_link:
                                    artist = artist_link.get_text(strip=True)
                                else:
                                    artist = artist_cell.get_text(strip=True)
                        else:
                            text = title_cell.get_text(separator='|', strip=True)
                            parts = [p.strip() for p in text.split('|') if p.strip()]
                            
                            if len(parts) >= 2:
                                title = parts[0]
                                artist = parts[1]
                            elif len(parts) == 1:
                                if ' - ' in parts[0]:
                                    artist, title = parts[0].split(' - ', 1)
                                else:
                                    title = parts[0]
                        
                        if title and artist:
                            previous_pos = None
                            movement = "new"
                            
                            if movement_text == 'new' or movement_text == '':
                                movement = "new"
                            elif movement_text.startswith('+'):
                                try:
                                    diff = int(movement_text[1:])
                                    previous_pos = rank + diff
                                    movement = "up"
                                except:
                                    movement = "same"
                                    previous_pos = rank
                            elif movement_text.startswith('-'):
                                try:
                                    diff = int(movement_text[1:])
                                    previous_pos = rank - diff
                                    movement = "down"
                                except:
                                    movement = "same"
                                    previous_pos = rank
                            else:
                                movement = "same"
                                previous_pos = rank
                            
                            entries.append({
                                "position": rank,
                                "track": {"title": title, "artist": artist},
                                "previousPosition": previous_pos,
                                "movement": movement,
                                "weeksOnChart": 1,
                                "peakPosition": rank,
                                "source": "kworb_itunes"
                            })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_itunes_rss(url, country_name):
    print(f"  🔍 Scraping iTunes RSS pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        entries = []
        feed_entries = data.get('feed', {}).get('entry', [])
        
        for index, entry in enumerate(feed_entries):
            try:
                title = entry.get('im:name', {}).get('label', '')
                artist = entry.get('im:artist', {}).get('label', '')
                
                images = entry.get('im:image', [])
                artwork = images[-1].get('label', '') if images else ''
                
                if title and artist:
                    entries.append({
                        "position": index + 1,
                        "track": {
                            "title": title,
                            "artist": artist,
                            "artwork": artwork
                        },
                        "previousPosition": None,
                        "movement": "new" if index == 0 else "same",
                        "weeksOnChart": 1,
                        "peakPosition": index + 1,
                        "source": "itunes_rss"
                    })
            except Exception:
                continue
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

# ===== SOURCE SNEP (SOURCE OFFICIELLE FRANCE) =====

def fetch_snep_latest():
    """
    Récupère le dernier top singles depuis snepmusique.com (SOURCE OFFICIELLE SNEP)
    """
    print(f"  🔍 Tentative snepmusique.com (source officielle SNEP)...")
    
    url = "https://snepmusique.com/classement-radio/"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 404:
            print(f"    ❌ Page non trouvée (404)")
            return []
        
        response.raise_for_status()
        
        if "Aucun classement" in response.text or len(response.text) < 1000:
            print(f"    ❌ Aucune donnée disponible")
            return []
        
        entries = parse_snep_html(response.text)
        
        if not entries:
            print(f"    ❌ Aucune entrée parsée")
            return []
        
        entries.sort(key=lambda x: x["position"])
        
        seen = set()
        unique_entries = []
        for entry in entries:
            if entry["position"] not in seen:
                seen.add(entry["position"])
                unique_entries.append(entry)
        
        entries = unique_entries[:200]
        
        if entries:
            print(f"    ✅ {len(entries)} entrées trouvées via SNEP (source officielle)")
            
            new_count = sum(1 for e in entries if e.get('movement') == 'new')
            up_count = sum(1 for e in entries if e.get('movement') == 'up')
            down_count = sum(1 for e in entries if e.get('movement') == 'down')
            print(f"       📊 {new_count} nouvelles, {up_count} ▲, {down_count} ▼")
            
            return entries
    
    except Exception as e:
        print(f"    ❌ Erreur SNEP: {e}")
    
    return []

def parse_snep_html(html_text):
    """
    Parse le HTML de snepmusique.com (VERSION FINALE CORRIGÉE)
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
    
    nav_keywords = [
        'Semaine précédente', 'Semaine suivante', 'Télécharger en PDF', 
        'Voir les filtres', 'Top Radio', 'Top Outre-mer', 'Abonnement',
        'newsletter', 'Twitter', 'LinkedIn', 'Email', 'Copy link',
        'Merci de partager', 'AddToAny', 'FERMER', 'Marketing Permissions'
    ]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        pos_match = re.match(r'^(\d{1,3})$', line)
        
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
                            if k >= 2:
                                prev_line = block[k - 2]
                                if prev_line.isdigit():
                                    previous_pos = int(prev_line)
                                    if previous_pos > position:
                                        movement = "up"
                                    elif previous_pos < position:
                                        movement = "down"
                                    else:
                                        movement = "same"
                        
                        elif 'Semaine dans le Top' in bline:
                            if k >= 2:
                                prev_line = block[k - 2]
                                if prev_line.isdigit():
                                    weeks_on_chart = int(prev_line)
                                    if weeks_on_chart == 1:
                                        movement = "new"
                                        previous_pos = None
                    
                    if title and artist and len(title) > 2 and len(artist) > 2:
                        if not any(kw in title.lower() for kw in ['semaine', 'top radio', 'actualités', 'les tops', 'news', 'newsletter']):
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

# ===== FONCTION PRINCIPALE =====

def main():
    global youtube_quota_exceeded
    
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    cache = load_cache()
    
    if YOUTUBE_API_KEY:
        print(f"✅ Clé API YouTube configurée")
        print(f"   Limite: {YOUTUBE_LIMIT_PER_COUNTRY} titres/pays")
        print(f"   Cache: réduction automatique des recherches")
        print(f"   yt-dlp: fallback automatique en cas de rate limiting\n")
    else:
        print("⚠️ Pas de clé API YouTube - seul Deezer fournira des IDs directs\n")
    
    week_info = get_week_info()
    
    charts_data = {
        "meta": {
            "weekLabel": week_info["label"],
            "week": week_info["week"],
            "year": week_info["year"],
            "updatedAt": week_info["date"],
            "sourceNote": "",
            "hasStreamingIds": True,
            "cacheSize": len(cache)
        },
        "countries": {},
        "regions": {
            "europe": {"label": "Europe", "countries": []},
            "anglo": {"label": "Pays anglo-saxons", "countries": []},
            "latam": {"label": "Amérique du Sud", "countries": []},
            "asia": {"label": "Asie", "countries": []}
        }
    }
    
    successful_sources = []
    failed_sources = []
    
    for code, country_info in SOURCES.items():
        print(f"\n📊 Traitement de {country_info['name']} {country_info['flag']}...")
        
        source_used = country_info["source"]
        entries = []
        
        if source_used == "acharts":
            entries = fetch_acharts(country_info["acharts_url"], country_info["name"])
        elif source_used == "kworb_itunes":
            entries = fetch_kworb_itunes(country_info["kworb_url"], country_info["name"])
        elif source_used == "promusica":
            entries = fetch_brazil_promusica()
        elif source_used == "itunes_rss":
            entries = fetch_itunes_rss(country_info["itunes_url"], country_info["name"])
        elif source_used == "snep":
            entries = fetch_snep_latest()
        
        if entries and len(entries) >= 5:
            entries = enrich_with_cache(entries, cache, country_info["name"])
        
        if entries and len(entries) >= 5:
            charts_data["countries"][code] = {
                "name": country_info["name"],
                "flag": country_info["flag"],
                "region": country_info["region"],
                "chart": entries,
                "sourceType": source_used
            }
            
            charts_data["regions"][country_info["region"]]["countries"].append(code)
            successful_sources.append(country_info["name"])
            print(f"  ✅ {len(entries)} titres collectés via {source_used}")
        else:
            failed_sources.append(country_info["name"])
            print(f"  ❌ Échec")
    
    save_cache(cache)
    
    if youtube_quota_exceeded:
        print(f"\n⚠️ ATTENTION : Le quota YouTube a été dépassé pendant la collecte")
        print(f"   Les titres non trouvés ont été recherchés via yt-dlp")
    
    if successful_sources and failed_sources:
        charts_data["meta"]["sourceNote"] = f"✅ {len(successful_sources)} sources OK. ❌ {len(failed_sources)} échouées."
    elif successful_sources:
        charts_data["meta"]["sourceNote"] = f"✅ Toutes les sources : {len(successful_sources)} tops collectés."
    else:
        charts_data["meta"]["sourceNote"] = "❌ Aucune source collectée."
    
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/charts-latest.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    with open(f"{output_dir}/charts-{week_info['date']}.json", "w", encoding="utf-8") as f:
        json.dump(charts_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ Collecte terminée")
    print(f"   - {len(successful_sources)} sources réussies")
    print(f"   - {len(failed_sources)} sources échouées")
    print(f"   - Cache: {len(cache)} titres en mémoire")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()