#!/usr/bin/env python3
"""
Script de collecte hebdomadaire des tops musicaux officiels.
Version complète avec :
- Cache intelligent + correction du bug des IDs manquants
- chartsinfrance.net comme source officielle pour la France (SNEP/SCPP)
- Fallback automatique entre sources
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

# Configuration - Limite à 20 par pays
YOUTUBE_LIMIT_PER_COUNTRY = 20
DEEZER_LIMIT_PER_COUNTRY = 20

# Configuration du cache
CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "streaming_ids.json")
CACHE_MAX_AGE_DAYS = 730  # 2 ans

SOURCES = {
    "us": {
        "name": "États-Unis", 
        "flag": "🇺🇸", 
        "region": "anglo", 
        "source": "billboard"
    },
    "fr": {
        "name": "France", 
        "flag": "🇫🇷", 
        "region": "europe", 
        "source": "chartsinfrance"  # Source officielle SNEP/SCPP
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
    """Charge le cache et applique le nettoyage automatique"""
    cache = {}
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"📦 Cache chargé : {len(cache)} titres en mémoire")
            
            # Appliquer le nettoyage automatique
            cache = clean_cache(cache)
            
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement du cache: {e}")
            cache = {}
    else:
        print(f"📦 Pas de cache trouvé, création d'un nouveau cache")
    
    return cache

def clean_cache(cache, max_age_days=CACHE_MAX_AGE_DAYS):
    """Nettoie le cache en supprimant les entrées de plus de max_age_days"""
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
            # Si la date est invalide, garder l'entrée par sécurité
            cleaned_cache[key] = value
    
    if removed_count > 0:
        print(f"🧹 Nettoyage automatique du cache : {removed_count} entrées supprimées (> {max_age_days} jours)")
        print(f"   Cache restant : {len(cleaned_cache)} entrées")
    
    return cleaned_cache

def save_cache(cache):
    """Sauvegarde le cache dans le fichier JSON"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} titres au total")
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde du cache: {e}")

def get_cache_key(artist, title):
    """Génère une clé unique pour un titre (normalisée)"""
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
    """Récupère l'ID Deezer d'un titre via l'API publique"""
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

# ===== RECHERCHE YOUTUBE =====

def fetch_youtube_video_id_official(artist, title):
    """Récupère l'ID vidéo YouTube en privilégiant les vidéos officielles"""
    global youtube_quota_exceeded
    
    if youtube_quota_exceeded:
        return None
    
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
        
        if response.status_code == 403:
            error_data = response.json()
            error_message = error_data.get('error', {}).get('message', '')
            
            if 'quota' in error_message.lower():
                youtube_quota_exceeded = True
                print(f"      ⚠️ QUOTA YOUTUBE DÉPASSÉ - Arrêt des recherches YouTube")
                return None
            else:
                print(f"      ⚠️ Erreur API YouTube 403: {error_message[:100]}")
                return None
        
        if response.status_code != 200:
            print(f"      ⚠️ Erreur API YouTube: HTTP {response.status_code}")
            return None
        
        data = response.json()
        items = data.get('items', [])
        
        if not items:
            return None
        
        exclude_keywords = ['lyrics', 'lyric', 'audio only', 'cover', 'live', 'karaoke', 'remix']
        
        best_video = None
        
        # Chercher une vidéo officielle
        for item in items:
            video_title = item['snippet']['title'].lower()
            channel = item['snippet']['channelTitle'].lower()
            
            is_official = any(keyword in video_title for keyword in ['official video', 'official', 'clip officiel', 'official clip'])
            is_vevo = 'vevo' in channel
            
            is_excluded = any(keyword in video_title for keyword in exclude_keywords)
            
            if not is_excluded and (is_official or is_vevo):
                best_video = item
                break
        
        # Fallback : première vidéo non-exclue
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
        print(f"      ⚠️ Erreur YouTube: {e}")
    
    return None

# ===== ENRICHISSEMENT AVEC CACHE (VERSION CORRIGÉE) =====

def enrich_with_cache(entries, cache, country_name):
    """
    Enrichit les entrées avec les IDs Deezer et YouTube en utilisant le cache.
    Version corrigée qui recherche les IDs manquants même si l'autre plateforme est en cache.
    """
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
        
        # Vérifier si on a déjà des IDs
        has_youtube = bool(entry.get('youtube_id'))
        has_deezer = bool(entry.get('deezer_id'))
        
        # Compter les limites
        can_search_youtube = youtube_count < YOUTUBE_LIMIT_PER_COUNTRY
        can_search_deezer = deezer_count < DEEZER_LIMIT_PER_COUNTRY
        
        # Vérifier le cache
        if cache_key in cache:
            cached = cache[cache_key]
            
            # Appliquer les IDs YouTube depuis le cache si absents
            if not has_youtube and cached.get('youtube_id'):
                entry['youtube_id'] = cached['youtube_id']
                entry['youtube_url'] = cached['youtube_url']
                has_youtube = True
                youtube_from_cache += 1
            
            # Appliquer les IDs Deezer depuis le cache si absents
            if not has_deezer and cached.get('deezer_id'):
                entry['deezer_id'] = cached['deezer_id']
                entry['deezer_url'] = cached['deezer_url']
                if cached.get('artwork'):
                    entry['track']['artwork'] = cached['artwork']
                has_deezer = True
                deezer_from_cache += 1
        
        # Rechercher les IDs manquants (même si l'autre est en cache)
        needs_update = False
        
        # Rechercher YouTube si manquant et dans la limite
        if not has_youtube and can_search_youtube:
            youtube_info = fetch_youtube_video_id_official(artist, title)
            if youtube_info:
                entry['youtube_id'] = youtube_info['youtube_id']
                entry['youtube_url'] = youtube_info['youtube_url']
                youtube_count += 1
                
                # Mettre à jour le cache
                if cache_key not in cache:
                    cache[cache_key] = {
                        'artist': artist,
                        'title': title,
                        'cached_at': datetime.now().strftime('%Y-%m-%d')
                    }
                cache[cache_key]['youtube_id'] = youtube_info['youtube_id']
                cache[cache_key]['youtube_url'] = youtube_info['youtube_url']
                needs_update = True
            
            time.sleep(0.3)
        
        # Rechercher Deezer si manquant et dans la limite
        if not has_deezer and can_search_deezer:
            deezer_info = fetch_deezer_track_id(artist, title)
            if deezer_info:
                entry['deezer_id'] = deezer_info['deezer_id']
                entry['deezer_url'] = deezer_info['deezer_url']
                if deezer_info.get('artwork'):
                    entry['track']['artwork'] = deezer_info['artwork']
                deezer_count += 1
                
                # Mettre à jour le cache
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
    """Récupère le top via acharts.co"""
    print(f"  🔍 Scraping acharts.co pour {country_name}...")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        table = soup.find('table', class_='detail')
        
        if not table:
            table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                cells = row.find_all('td')
                
                if len(cells) >= 4:
                    # Position
                    pos_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', pos_text)
                    
                    if not rank_match:
                        continue
                    
                    rank = int(rank_match.group())
                    
                    # Mouvement
                    movement_text = cells[1].get_text(strip=True).lower()
                    
                    # Titre et artiste
                    title_cell = cells[3] if len(cells) > 3 else cells[2]
                    title = None
                    artist = None
                    
                    # Chercher les liens
                    title_link = title_cell.find('a')
                    if title_link:
                        title = title_link.get_text(strip=True)
                        
                        # L'artiste est souvent dans la cellule suivante ou dans un lien séparé
                        artist_cell = cells[4] if len(cells) > 4 else cells[3]
                        artist_link = artist_cell.find('a')
                        
                        if artist_link:
                            artist = artist_link.get_text(strip=True)
                        else:
                            # Parfois l'artiste est dans la même cellule après un <br>
                            artist_text = artist_cell.get_text(strip=True)
                            if artist_text and artist_text != title:
                                artist = artist_text
                    else:
                        # Pas de lien, essayer de parser le texte
                        text = title_cell.get_text(separator='|', strip=True)
                        parts = [p.strip() for p in text.split('|') if p.strip()]
                        if len(parts) >= 2:
                            title = parts[0]
                            artist = parts[1]
                    
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
                            "source": "acharts"
                        })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur: {e}")
        return []

def fetch_brazil_promusica():
    """Récupère le top brésilien via Pro-Música Brasil"""
    print(f"  🔍 Scraping Pro-Música Brasil...")
    
    try:
        url = "https://pro-musicabr.org.br/home/top-50-streaming/"
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        entries = []
        
        # Chercher les lignes du classement
        rows = soup.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) >= 3:
                # Position
                pos_text = cells[0].get_text(strip=True)
                rank_match = re.search(r'\d+', pos_text)
                
                if rank_match:
                    rank = int(rank_match.group())
                    
                    if rank <= 50:
                        # Titre et artiste
                        title_cell = cells[1]
                        artist_cell = cells[2]
                        
                        title = title_cell.get_text(strip=True)
                        artist = artist_cell.get_text(strip=True)
                        
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
    """Récupère le top via kworb.net (iTunes)"""
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
                    # Position
                    pos_text = cells[0].get_text(strip=True)
                    rank_match = re.search(r'\d+', pos_text)
                    
                    if rank_match:
                        rank = int(rank_match.group())
                        
                        # Mouvement
                        movement_cell = cells[1]
                        movement_text = movement_cell.get_text(strip=True)
                        
                        # Titre et artiste
                        title_cell = cells[2]
                        title = None
                        artist = None
                        
                        # Parser la cellule titre/artiste
                        title_link = title_cell.find('a')
                        
                        if title_link:
                            title = title_link.get_text(strip=True)
                            
                            # Chercher l'artiste
                            artist_cell = cells[3] if len(cells) > 3 else None
                            
                            if artist_cell:
                                artist_link = artist_cell.find('a')
                                if artist_link:
                                    artist = artist_link.get_text(strip=True)
                                else:
                                    artist = artist_cell.get_text(strip=True)
                        else:
                            # Pas de lien, parser le texte
                            text = title_cell.get_text(separator='|', strip=True)
                            parts = [p.strip() for p in text.split('|') if p.strip()]
                            
                            if len(parts) >= 2:
                                title = parts[0]
                                artist = parts[1]
                            elif len(parts) == 1:
                                # Essayer de séparer artiste - titre
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
    """Récupère le top via l'API iTunes RSS"""
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

def fetch_billboard_hot100():
    """Récupère le Billboard Hot 100"""
    print(f"  🔍 Tentative avec billboard.py...")
    
    try:
        import billboard
        
        chart = billboard.ChartData('hot-100')
        entries = []
        
        for i, entry in enumerate(chart.entries[:50]):
            lw = getattr(entry, 'lastPos', None)
            peak = getattr(entry, 'peakPos', i + 1)
            weeks = getattr(entry, 'weeks', 1)
            
            if lw == 0:
                lw = None
            
            movement = calculate_movement(i + 1, lw)
            
            entries.append({
                "position": i + 1,
                "track": {"title": entry.title, "artist": entry.artist},
                "previousPosition": lw,
                "movement": movement,
                "weeksOnChart": weeks,
                "peakPosition": peak,
                "source": "billboard"
            })
        
        print(f"    ✅ {len(entries)} entrées trouvées")
        return entries
    
    except Exception as e:
        print(f"    ❌ Erreur billboard.py: {e}")
    
    return fetch_acharts("https://acharts.co/us_singles_top_100", "US")

# ===== SOURCE CHARTSINFRANCE.NET (NOUVELLE) =====

def fetch_chartsinfrance_latest():
    """
    Récupère le dernier top singles depuis chartsinfrance.net
    Source officielle SNEP/SCPP (Syndicat National de l'Édition Phonographique)
    """
    print(f"  🔍 Tentative chartsinfrance.net (source officielle SNEP)...")
    
    # Point de référence : 8645 = 6 novembre 1986
    REF_WEEK = 8645
    REF_DATE = datetime(1986, 11, 6)
    
    # Calculer le numéro de semaine pour aujourd'hui
    today = datetime.now()
    delta_days = (today - REF_DATE).days
    delta_weeks = delta_days // 7
    current_week_num = REF_WEEK + delta_weeks
    
    # Essayer cette semaine et les 2 précédentes
    for offset in range(0, 3):
        week_num = current_week_num - offset
        url = f"https://www.chartsinfrance.net/charts/{week_num}/singles.php"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            
            if response.status_code == 404:
                print(f"    ⚠️ Semaine {week_num} non trouvée, essai suivant...")
                continue
            
            if "Aucun classement disponible" in response.text:
                print(f"    ⚠️ Aucune donnée pour semaine {week_num}, essai suivant...")
                continue
            
            response.raise_for_status()
            
            # Parser le HTML
            entries = []
            lines = response.text.split('\n')
            
            for i, line in enumerate(lines):
                # Chercher les positions (nombres seuls sur une ligne)
                if re.search(r'^\s*\d{1,2}\s*$', line.strip()):
                    position = int(line.strip())
                    
                    if position <= 50:
                        title = ""
                        artist = ""
                        
                        # Chercher titre et artiste dans les lignes suivantes
                        for j in range(i+1, min(i+5, len(lines))):
                            next_line = lines[j].strip()
                            
                            # Ignorer les lignes vides ou avec des underscores
                            if next_line and not next_line.startswith('_') and len(next_line) > 3:
                                if not title:
                                    title = next_line
                                elif not artist:
                                    artist = next_line
                                    break
                        
                        if title and artist:
                            # Déterminer le mouvement
                            movement = "same"
                            previous_pos = None
                            
                            # Chercher les indicateurs de mouvement
                            for j in range(i+1, min(i+10, len(lines))):
                                line_lower = lines[j].lower()
                                
                                if 'arrow_top' in line_lower or '▲' in lines[j]:
                                    movement = "up"
                                    # Essayer d'extraire le nombre de places gagnées
                                    num_match = re.search(r'(\d+)', lines[j])
                                    if num_match:
                                        diff = int(num_match.group(1))
                                        previous_pos = position + diff
                                    break
                                elif 'arrow_bot' in line_lower or '▼' in lines[j]:
                                    movement = "down"
                                    num_match = re.search(r'(\d+)', lines[j])
                                    if num_match:
                                        diff = int(num_match.group(1))
                                        previous_pos = position - diff
                                    break
                                elif 'new' in line_lower:
                                    movement = "new"
                                    break
                                elif 'arrow_right' in line_lower or '→' in lines[j]:
                                    movement = "same"
                                    previous_pos = position
                                    break
                            
                            if previous_pos is None and movement != "new":
                                previous_pos = position
                            
                            entries.append({
                                "position": position,
                                "track": {"title": title, "artist": artist},
                                "previousPosition": previous_pos,
                                "movement": movement,
                                "weeksOnChart": 1,
                                "peakPosition": position,
                                "source": "chartsinfrance"
                            })
            
            # Dédupliquer par position
            seen = set()
            unique_entries = []
            for entry in entries:
                if entry["position"] not in seen:
                    seen.add(entry["position"])
                    unique_entries.append(entry)
            
            entries = sorted(unique_entries, key=lambda x: x["position"])[:50]
            
            if entries:
                # Calculer la date de la semaine
                week_date = REF_DATE + timedelta(weeks=(week_num - REF_WEEK))
                
                print(f"    ✅ {len(entries)} entrées trouvées via chartsinfrance.net (semaine du {week_date.strftime('%d/%m/%Y')})")
                return entries
        
        except Exception as e:
            print(f"    ⚠️ Erreur chartsinfrance semaine {week_num}: {e}")
            continue
    
    print(f"    ❌ Échec : aucune semaine disponible")
    return []

# ===== FONCTION PRINCIPALE =====

def main():
    global youtube_quota_exceeded
    
    print(f"🎵 Début de la collecte - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Charger le cache (avec nettoyage automatique)
    cache = load_cache()
    
    if YOUTUBE_API_KEY:
        print(f"✅ Clé API YouTube configurée")
        print(f"   Limite: {YOUTUBE_LIMIT_PER_COUNTRY} titres/pays")
        print(f"   Cache: réduction automatique des recherches\n")
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
        
        # Récupérer les données selon la source
        if source_used == "billboard":
            entries = fetch_billboard_hot100()
        elif source_used == "acharts":
            entries = fetch_acharts(country_info["acharts_url"], country_info["name"])
        elif source_used == "kworb_itunes":
            entries = fetch_kworb_itunes(country_info["kworb_url"], country_info["name"])
        elif source_used == "promusica":
            entries = fetch_brazil_promusica()
        elif source_used == "itunes_rss":
            entries = fetch_itunes_rss(country_info["itunes_url"], country_info["name"])
        elif source_used == "chartsinfrance":
            entries = fetch_chartsinfrance_latest()
        
        # Fallback pour la France : si chartsinfrance échoue, essayer acharts
        if code == "fr" and (not entries or len(entries) < 5):
            print(f"  🔄 Fallback sur acharts.co pour la France...")
            entries = fetch_acharts("https://acharts.co/france_singles_top_100", country_info["name"])
        
        # Enrichir avec le cache (version corrigée)
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
    
    # Sauvegarder le cache mis à jour
    save_cache(cache)
    
    # Message final sur le quota
    if youtube_quota_exceeded:
        print(f"\n⚠️ ATTENTION : Le quota YouTube a été dépassé pendant la collecte")
        print(f"   Les titres non trouvés seront recherchés à la prochaine exécution")
    
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