#!/usr/bin/env python3
"""Top Singles V2.2.1 — Collecte hebdo + enrichissement YouTube/Deezer/Apple/Dailymotion"""
import json, requests, re, os, time, urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
YOUTUBE_LIMIT_PER_COUNTRY = 20
DEEZER_LIMIT_PER_COUNTRY = 20
APPLE_LIMIT_PER_COUNTRY = 20
DAILYMOTION_LIMIT_PER_COUNTRY = 20
CACHE_DIR = "data/cache"
CACHE_FILE = os.path.join(CACHE_DIR, "streaming_ids.json")
CACHE_MAX_AGE_DAYS = 730

SOURCES = {
 "us": {"name":"États-Unis","flag":"🇺🇸","region":"anglo","source":"acharts","acharts_url":"https://acharts.co/us_singles_top_100"},
 "fr": {"name":"France","flag":"🇫🇷","region":"europe","source":"snep"},
 "gb": {"name":"Royaume-Uni","flag":"🇬🇧","region":"europe","source":"acharts","acharts_url":"https://acharts.co/uk_singles_top_75"},
 "gb_indie": {"name":"UK Indie","flag":"🇬🇧🎸","region":"europe","source":"official_charts"},
 "de": {"name":"Allemagne","flag":"🇩🇪","region":"europe","source":"kworb_itunes","kworb_url":"https://kworb.net/charts/itunes/de.html"},
 "ch": {"name":"Suisse","flag":"🇨🇭","region":"europe","source":"acharts","acharts_url":"https://acharts.co/swiss_singles_top_100"},
 "br": {"name":"Brésil","flag":"🇧🇷","region":"latam","source":"billboard_brasil"},
 "sg": {"name":"Singapour","flag":"🇸🇬","region":"asia","source":"itunes_rss","itunes_url":"https://itunes.apple.com/sg/rss/topsongs/limit=50/json"}
}

HEADERS = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
youtube_quota_exceeded = False

# ===== CACHE =====
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE,'r',encoding='utf-8') as f: cache=json.load(f)
            print(f"📦 Cache chargé : {len(cache)} titres")
            return clean_cache(cache)
        except Exception as e:
            print(f"⚠️ Erreur cache: {e}")
    else:
        print("📦 Nouveau cache")
    return {}

def clean_cache(cache, max_age_days=CACHE_MAX_AGE_DAYS):
    if not cache: return cache
    cutoff = datetime.now()-timedelta(days=max_age_days)
    out={}; removed=0
    for k,v in cache.items():
        try:
            d=datetime.strptime(v.get('cached_at','2020-01-01'),'%Y-%m-%d')
            if d>=cutoff: out[k]=v
            else: removed+=1
        except (ValueError,TypeError): out[k]=v
    if removed: print(f"🧹 {removed} entrées purgées (> {max_age_days}j) — reste {len(out)}")
    return out

def save_cache(cache):
    try:
        os.makedirs(CACHE_DIR,exist_ok=True)
        with open(CACHE_FILE,'w',encoding='utf-8') as f: json.dump(cache,f,ensure_ascii=False,indent=2)
        print(f"💾 Cache sauvegardé : {len(cache)} titres")
    except Exception as e: print(f"⚠️ Erreur sauvegarde: {e}")

def get_cache_key(artist,title):
    a=re.sub(r'\(.*?\)','',artist).lower().strip()
    t=re.sub(r'\(.*?\)','',title).lower().strip()
    a=re.sub(r'[^\w\s]','',a).strip(); t=re.sub(r'[^\w\s]','',t).strip()
    return f"{a}|{t}"

def get_week_info():
    n=datetime.now()
    return {"week":n.isocalendar()[1],"year":n.year,"date":n.strftime("%Y-%m-%d"),"label":f"Semaine {n.isocalendar()[1]}/{n.year}"}

def get_scraper():
    try:
        import cloudscraper
        return cloudscraper.create_scraper(browser={'browser':'chrome','platform':'windows','mobile':False})
    except ImportError:
        print("    ⚠️ cloudscraper absent → requests")
        return requests

# ===== DEEZER =====
def fetch_deezer_track_id(artist,title):
    try:
        t=re.sub(r'\(.*?\)','',title).strip(); a=re.sub(r'\(.*?\)','',artist).strip()
        url=f"https://api.deezer.com/search?q={urllib.parse.quote(f'{a} {t}')}&limit=1"
        r=requests.get(url,headers=HEADERS,timeout=10)
        if r.status_code==200:
            d=r.json().get('data')
            if d:
                tr=d[0]
                return {'deezer_id':tr.get('id'),'deezer_url':tr.get('link'),'artwork':tr.get('album',{}).get('cover_medium','')}
    except Exception: pass
    return None

# ===== APPLE MUSIC (iTunes Search, sans clé) =====
def fetch_apple_music_track_id(artist,title):
    try:
        t=re.sub(r'\(.*?\)','',title).strip(); a=re.sub(r'\(.*?\)','',artist).strip()
        if not t: return None
        url="https://itunes.apple.com/search"
        p={'term':f"{a} {t}",'entity':'song','media':'music','limit':1}
        r=requests.get(url,params=p,headers=HEADERS,timeout=15)
        if r.status_code in (403,429):
            time.sleep(10); r=requests.get(url,params=p,headers=HEADERS,timeout=15)
        res=r.json().get('results',[]) if r.status_code==200 else []
        if not res:
            time.sleep(3); p['term']=t
            r=requests.get(url,params=p,headers=HEADERS,timeout=15)
            if r.status_code==200: res=r.json().get('results',[])
        if not res: return None
        tr=res[0]; u=tr.get('trackViewUrl'); i=tr.get('trackId')
        if not u or not i: return None
        art=tr.get('artworkUrl100','')
        if art: art=art.replace('100x100bb','300x300bb').replace('100x100','300x300')
        return {'apple_id':i,'apple_url':u,'artwork':art}
    except Exception: return None

# ===== DAILYMOTION (API legacy publique, sans clé) =====
def fetch_dailymotion_video_id(artist,title):
    try:
        t=re.sub(r'\(.*?\)','',title).strip(); a=re.sub(r'\(.*?\)','',artist).strip()
        if not t: return None
        url="https://api.dailymotion.com/videos"
        p={'search':f"{a} {t}",'fields':'id,title,duration','limit':5}
        r=requests.get(url,params=p,headers=HEADERS,timeout=15)
        items=r.json().get('list',[]) if r.status_code==200 else []
        if not items:
            time.sleep(1); p['search']=t
            r=requests.get(url,params=p,headers=HEADERS,timeout=15)
            if r.status_code==200: items=r.json().get('list',[])
        if not items: return None
        excl=['lyrics','lyric','paroles','karaoke','karaoké','cover','remix','instrumental','tutorial','tuto']
        best=None
        for it in items:
            ti=(it.get('title') or '').lower(); du=it.get('duration') or 0
            if any(k in ti for k in excl): continue
            if du and (du<60 or du>900): continue
            if 'official' in ti or 'officiel' in ti or 'clip' in ti:
                best=it; break
            if best is None: best=it
        if not best: best=items[0]
        vid=best.get('id')
        if not vid: return None
        return {'dailymotion_id':vid,'dailymotion_url':f"https://www.dailymotion.com/video/{vid}"}
    except Exception: return None

# ===== YOUTUBE =====
def fetch_youtube_video_id_official(artist,title):
    global youtube_quota_exceeded
    if youtube_quota_exceeded: return fetch_youtube_video_id_ytdlp(artist,title)
    if not YOUTUBE_API_KEY: return fetch_youtube_video_id_ytdlp(artist,title)
    try:
        t=re.sub(r'\(.*?\)','',title).strip(); a=re.sub(r'\(.*?\)','',artist).strip()
        p={'part':'snippet','q':f"{a} {t} official video",'type':'video','maxResults':5,'key':YOUTUBE_API_KEY,'order':'relevance'}
        r=requests.get("https://www.googleapis.com/youtube/v3/search",params=p,timeout=10)
        if r.status_code==429: return fetch_youtube_video_id_ytdlp(artist,title)
        if r.status_code==403:
            msg=r.json().get('error',{}).get('message','')
            if 'quota' in msg.lower(): youtube_quota_exceeded=True
            return fetch_youtube_video_id_ytdlp(artist,title)
        if r.status_code!=200: return fetch_youtube_video_id_ytdlp(artist,title)
        items=r.json().get('items',[])
        if not items: return None
        excl=['lyrics','lyric','audio only','cover','live','karaoke','remix']
        best=None
        for it in items:
            vt=it['snippet']['title'].lower(); ch=it['snippet']['channelTitle'].lower()
            off=any(k in vt for k in ['official video','official','clip officiel','official clip'])
            if not any(k in vt for k in excl) and (off or 'vevo' in ch):
                best=it; break
        if not best:
            for it in items:
                if not any(k in it['snippet']['title'].lower() for k in excl):
                    best=it; break
        if best:
            vid=best['id']['videoId']
            return {'youtube_id':vid,'youtube_url':f"https://www.youtube.com/watch?v={vid}"}
    except Exception: return fetch_youtube_video_id_ytdlp(artist,title)
    return None

def fetch_youtube_video_id_ytdlp(artist,title):
    try:
        import yt_dlp
        t=re.sub(r'\(.*?\)','',title).strip(); a=re.sub(r'\(.*?\)','',artist).strip()
        opts={'quiet':True,'no_warnings':True,'extract_flat':True,'default_search':'ytsearch5','playlistend':5,'format':'best'}
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                res=ydl.extract_info(f"ytsearch5:{a} {t} official video",download=False)
                if not res or 'entries' not in res: return None
                excl=['lyrics','lyric','audio only','cover','live','karaoke','remix']
                for it in res['entries']:
                    if not it: continue
                    vt=(it.get('title') or '').lower(); ch=(it.get('channel') or '').lower()
                    off=any(k in vt for k in ['official video','official','clip officiel','official clip'])
                    if not any(k in vt for k in excl) and (off or 'vevo' in ch):
                        vid=it.get('id')
                        if vid: return {'youtube_id':vid,'youtube_url':f"https://www.youtube.com/watch?v={vid}"}
                for it in res['entries']:
                    if not it: continue
                    if not any(k in (it.get('title') or '').lower() for k in excl):
                        vid=it.get('id')
                        if vid: return {'youtube_id':vid,'youtube_url':f"https://www.youtube.com/watch?v={vid}"}
            except Exception: return None
        return None
    except ImportError: return None
    except Exception: return None

# ===== ENRICHISSEMENT =====
def enrich_with_cache(entries,cache,country_name):
    print(f"  📊 Enrichissement pour {country_name}...")
    c={'yt':0,'dz':0,'ap':0,'dm':0}; fc={'yt':0,'dz':0,'ap':0,'dm':0}; updates=0
    lim={'yt':YOUTUBE_LIMIT_PER_COUNTRY,'dz':DEEZER_LIMIT_PER_COUNTRY,'ap':APPLE_LIMIT_PER_COUNTRY,'dm':DAILYMOTION_LIMIT_PER_COUNTRY}

    for e in entries:
        artist=e['track']['artist']; title=e['track']['title']; key=get_cache_key(artist,title)
        has={'yt':bool(e.get('youtube_id')),'dz':bool(e.get('deezer_id')),'ap':bool(e.get('apple_id')),'dm':bool(e.get('dailymotion_id'))}

        if key in cache:
            cd=cache[key]
            if not has['yt'] and cd.get('youtube_id'):
                e['youtube_id']=cd['youtube_id']; e['youtube_url']=cd['youtube_url']; has['yt']=True; fc['yt']+=1
            if not has['dz'] and cd.get('deezer_id'):
                e['deezer_id']=cd['deezer_id']; e['deezer_url']=cd['deezer_url']
                if cd.get('artwork'): e['track']['artwork']=cd['artwork']
                has['dz']=True; fc['dz']+=1
            if not has['ap'] and cd.get('apple_id'):
                e['apple_id']=cd['apple_id']; e['apple_url']=cd['apple_url']
                if cd.get('apple_artwork') and not e['track'].get('artwork'): e['track']['artwork']=cd['apple_artwork']
                has['ap']=True; fc['ap']+=1
            if not has['dm'] and cd.get('dailymotion_id'):
                e['dailymotion_id']=cd['dailymotion_id']; e['dailymotion_url']=cd['dailymotion_url']; has['dm']=True; fc['dm']+=1

        if key not in cache:
            cache[key]={'artist':artist,'title':title,'cached_at':datetime.now().strftime('%Y-%m-%d')}
        upd=False

        if not has['yt'] and c['yt']<lim['yt']:
            i=fetch_youtube_video_id_official(artist,title)
            if i:
                e['youtube_id']=i['youtube_id']; e['youtube_url']=i['youtube_url']; c['yt']+=1
                cache[key]['youtube_id']=i['youtube_id']; cache[key]['youtube_url']=i['youtube_url']; upd=True
            time.sleep(0.5)

        if not has['dz'] and c['dz']<lim['dz']:
            i=fetch_deezer_track_id(artist,title)
            if i:
                e['deezer_id']=i['deezer_id']; e['deezer_url']=i['deezer_url']
                if i.get('artwork'): e['track']['artwork']=i['artwork']
                c['dz']+=1
                cache[key]['deezer_id']=i['deezer_id']; cache[key]['deezer_url']=i['deezer_url']
                if i.get('artwork'): cache[key]['artwork']=i['artwork']
                upd=True
            time.sleep(0.2)

        if not has['ap'] and c['ap']<lim['ap']:
            i=fetch_apple_music_track_id(artist,title)
            if i:
                e['apple_id']=i['apple_id']; e['apple_url']=i['apple_url']
                if i.get('artwork') and not e['track'].get('artwork'): e['track']['artwork']=i['artwork']
                c['ap']+=1
                cache[key]['apple_id']=i['apple_id']; cache[key]['apple_url']=i['apple_url']
                if i.get('artwork'): cache[key]['apple_artwork']=i['artwork']
                upd=True
            time.sleep(3)

        if not has['dm'] and c['dm']<lim['dm']:
            i=fetch_dailymotion_video_id(artist,title)
            if i:
                e['dailymotion_id']=i['dailymotion_id']; e['dailymotion_url']=i['dailymotion_url']; c['dm']+=1
                cache[key]['dailymotion_id']=i['dailymotion_id']; cache[key]['dailymotion_url']=i['dailymotion_url']; upd=True
            time.sleep(1)

        if upd: updates+=1

    n=len(entries)
    print(f"  📊 Cache: {sum(fc.values())} titres utilisés")
    print(f"  🎧 Deezer: {c['dz']}/{min(lim['dz'],n)} trouvés"+(f" (dont {fc['dz']} cache)" if fc['dz'] else ""))
    msg=f"  ▶️ YouTube: {c['yt']}/{min(lim['yt'],n)} trouvés"+(f" (dont {fc['yt']} cache)" if fc['yt'] else "")
    if youtube_quota_exceeded: msg+=" 🔄 via yt-dlp"
    print(msg)
    print(f"  🍎 Apple: {c['ap']}/{min(lim['ap'],n)} trouvés"+(f" (dont {fc['ap']} cache)" if fc['ap'] else ""))
    print(f"  📺 Dailymotion: {c['dm']}/{min(lim['dm'],n)} trouvés"+(f" (dont {fc['dm']} cache)" if fc['dm'] else ""))
    if updates: print(f"  💾 {updates} nouvelles entrées au cache")
    return entries

# ===== SOURCES =====
def fetch_acharts(url,country_name):
    print(f"  🔍 acharts.co — {country_name}...")
    try:
        r=requests.get(url,headers=HEADERS,timeout=30); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        table=soup.find('table',id='ChartTable') or soup.find('table')
        if not table:
            print("    ❌ Aucun tableau"); return []
        entries=[]
        for row in table.find_all('tr')[1:]:
            cells=row.find_all('td')
            if len(cells)<6: continue
            pc=cells[0]; sp=pc.find('span',itemprop='position')
            if sp:
                txt=sp.get_text(strip=True)
                if not txt.isdigit(): continue
                pos=int(txt)
            else:
                m=re.match(r'^(\d+)',pc.get_text(separator=' ',strip=True))
                if not m: continue
                pos=int(m.group(1))
            if not 1<=pos<=100: continue
            prev=None; mv="same"; pt=cells[1].get_text(strip=True)
            if pt.isdigit(): prev=int(pt)
            else:
                m=re.search(r'\(([^)]+)\)',pc.get_text(strip=True))
                if m:
                    v=m.group(1).strip().lower()
                    if v in ('new','re-entry','re'): mv="new"
                    elif v.isdigit(): prev=int(v)
            if prev is not None and mv=="same":
                mv="up" if prev>pos else ("down" if prev<pos else "same")
            tc=cells[2]; ts=tc.find('span',itemprop='name')
            if not ts: continue
            title=ts.get_text(strip=True)
            parts=[p.strip() for p in tc.get_text(separator='|',strip=True).split('|') if p.strip()]
            if len(parts)<2: continue
            skip=['peak position:','total weeks:','Longest on Chart','Highest Debut','Biggest Fall','Best Comeback']
            ap=[]; found=False
            for p in parts:
                if p==title: found=True; continue
                if found:
                    if any(s in p for s in skip): break
                    ap.append(p)
            if not ap: continue
            artist=' '.join(ap); peak=pos; weeks=1
            if cells[4].get_text(strip=True).isdigit(): peak=int(cells[4].get_text(strip=True))
            if cells[5].get_text(strip=True).isdigit(): weeks=int(cells[5].get_text(strip=True))
            if len(title)>1 and len(artist)>1:
                entries.append({"position":pos,"track":{"title":title,"artist":artist},"previousPosition":prev,"movement":mv,"weeksOnChart":weeks,"peakPosition":peak,"source":"acharts"})
        entries.sort(key=lambda x:x["position"])
        seen=set(); uniq=[]
        for e in entries:
            if e["position"] not in seen: seen.add(e["position"]); uniq.append(e)
        entries=uniq[:100]
        print(f"    ✅ {len(entries)} entrées")
        for e in entries[:3]:
            s="▲" if e['movement']=='up' else ("▼" if e['movement']=='down' else "●")
            print(f"       {e['position']}. {e['track']['artist']} - {e['track']['title']} {s}")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_official_charts_indie():
    print("  🔍 Official Charts UK Indie...")
    try:
        sc=get_scraper()
        h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
           'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Language':'en-GB,en;q=0.9,fr;q=0.8',
           'Referer':'https://www.officialcharts.com/','Upgrade-Insecure-Requests':'1'}
        r=sc.get("https://www.officialcharts.com/charts/independent-singles-chart/",headers=h,timeout=30); r.raise_for_status()
        lines=[l.strip() for l in BeautifulSoup(r.text,'html.parser').get_text(separator='\n',strip=True).split('\n') if l.strip()]
        entries=[]; i=0
        while i<len(lines):
            if lines[i]=='Number' and i+2<len(lines):
                pl=lines[i+1]
                if not re.match(r'^\d+$',pl): i+=1; continue
                pos=int(pl)
                if not 1<=pos<=100: i+=1; continue
                title=lines[i+2]; ap=[]; j=i+3
                while j<len(lines):
                    if lines[j]=='LW:': break
                    ap.append(lines[j]); j+=1
                cl=[p.rstrip('/').strip() for p in ap if p.rstrip('/').strip()]
                artist=' feat. '.join(cl)
                prev=None; peak=pos; weeks=1; mv="same"
                bt=' '.join(lines[j:min(j+20,len(lines))])
                m=re.search(r'LW:\s*([A-Z0-9-]+)',bt)
                if m:
                    v=m.group(1).strip()
                    if v in ('RE','-'): mv="new"
                    elif v.isdigit():
                        prev=int(v); mv="up" if prev>pos else ("down" if prev<pos else "same")
                else: mv="new"
                m=re.search(r'Peak:\s*(\d+)',bt)
                if m: peak=int(m.group(1))
                m=re.search(r'Weeks:\s*(\d+)',bt)
                if m: weeks=int(m.group(1))
                if len(title)>1 and len(artist)>1 and not any(k in title.lower() for k in ['copyright','fonticons','official charts']):
                    entries.append({"position":pos,"track":{"title":title,"artist":artist},"previousPosition":prev,"movement":mv,"weeksOnChart":weeks,"peakPosition":peak,"source":"official_charts"})
            i+=1
        entries.sort(key=lambda x:x["position"])
        seen=set(); uniq=[]
        for e in entries:
            if e["position"] not in seen: seen.add(e["position"]); uniq.append(e)
        entries=uniq[:100]
        print(f"    ✅ {len(entries)} entrées")
        for e in entries[:3]:
            s="▲" if e['movement']=='up' else ("▼" if e['movement']=='down' else ("✦" if e['movement']=='new' else "●"))
            print(f"       {e['position']}. {e['track']['artist']} - {e['track']['title']} {s}")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_billboard_brasil():
    print("  🔍 Billboard Brasil Hot 100...")
    try:
        sc=get_scraper()
        h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
           'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Language':'pt-BR,pt;q=0.9,en;q=0.7',
           'Referer':'https://billboard.com.br/','Upgrade-Insecure-Requests':'1'}
        r=sc.get("https://billboard.com.br/billboard-brasil-hot-100/",headers=h,timeout=30); r.raise_for_status()
        lines=[l.strip() for l in BeautifulSoup(r.text,'html.parser').get_text(separator='\n',strip=True).split('\n') if l.strip()]
        entries=[]; i=0
        while i<len(lines):
            if re.match(r'^\d+$',lines[i]):
                pos=int(lines[i])
                if 1<=pos<=100 and i+3<len(lines):
                    title=lines[i+1]; artist=lines[i+2]; nl=lines[i+3]
                    if 'Últ' in nl or 'Semana' in nl:
                        prev=None; peak=pos; weeks=1; mv="same"
                        for j in range(i+3,min(i+12,len(lines))):
                            b=lines[j]
                            if re.match(r'^\d+$',b) and j>i+3: break
                            nxt=lines[j+1] if j+1<len(lines) else ''
                            if 'Últ' in b and 'Semana' in b and re.match(r'^\d+$',nxt):
                                prev=int(nxt); mv="up" if prev>pos else ("down" if prev<pos else "same")
                            elif 'Pos' in b and 'xima' in b and re.match(r'^\d+$',nxt): peak=int(nxt)
                            elif 'Semanas no Chart' in b and re.match(r'^\d+$',nxt): weeks=int(nxt)
                        if prev is None: mv="new"
                        if len(title)>1 and len(artist)>1:
                            entries.append({"position":pos,"track":{"title":title,"artist":artist},"previousPosition":prev,"movement":mv,"weeksOnChart":weeks,"peakPosition":peak,"source":"billboard_brasil"})
            i+=1
        entries.sort(key=lambda x:x["position"])
        seen=set(); uniq=[]
        for e in entries:
            if e["position"] not in seen: seen.add(e["position"]); uniq.append(e)
        entries=uniq[:100]
        print(f"    ✅ {len(entries)} entrées")
        for e in entries[:3]:
            s="▲" if e['movement']=='up' else ("▼" if e['movement']=='down' else ("✦" if e['movement']=='new' else "●"))
            print(f"       {e['position']}. {e['track']['artist']} - {e['track']['title']} {s}")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_brazil_promusica():
    print("  🔍 Pro-Música Brasil (fallback)...")
    try:
        r=requests.get("https://pro-musicabr.org.br/home/top-50-streaming/",headers=HEADERS,timeout=30); r.raise_for_status()
        table=BeautifulSoup(r.text,'html.parser').find('table')
        if not table:
            print("    ❌ Aucun tableau"); return []
        entries=[]
        for row in table.find_all('tr'):
            cells=row.find_all('td')
            if len(cells)>=3:
                m=re.search(r'\d+',cells[0].get_text(strip=True))
                if m:
                    rank=int(m.group())
                    if rank<=50:
                        parts=[p.strip() for p in cells[2].get_text(separator='|',strip=True).split('|') if p.strip()]
                        if len(parts)>=2 and parts[0] and parts[1]:
                            entries.append({"position":rank,"track":{"title":parts[1],"artist":parts[0]},"previousPosition":None,"movement":"same","weeksOnChart":1,"peakPosition":rank,"source":"promusica"})
        print(f"    ✅ {len(entries)} entrées")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_kworb_itunes(url,country_name):
    print(f"  🔍 kworb.net — {country_name}...")
    try:
        r=requests.get(url,headers=HEADERS,timeout=30); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        table=soup.find('table',class_='chartlist') or soup.find('table')
        entries=[]
        if table:
            for row in table.find_all('tr')[1:]:
                cells=row.find_all('td')
                if len(cells)<3: continue
                m=re.search(r'\d+',cells[0].get_text(strip=True))
                if not m: continue
                rank=int(m.group()); mt=cells[1].get_text(strip=True)
                tc=cells[2]; title=None; artist=None
                tl=tc.find('a')
                if tl:
                    title=tl.get_text(strip=True)
                    ac=cells[3] if len(cells)>3 else None
                    if ac:
                        al=ac.find('a'); artist=al.get_text(strip=True) if al else ac.get_text(strip=True)
                else:
                    parts=[p.strip() for p in tc.get_text(separator='|',strip=True).split('|') if p.strip()]
                    if len(parts)>=2: title,artist=parts[0],parts[1]
                    elif len(parts)==1:
                        if ' - ' in parts[0]: artist,title=parts[0].split(' - ',1)
                        else: title=parts[0]
                if not (title and artist): continue
                prev=None; mv="new"
                if mt in ('new',''): mv="new"
                elif mt.startswith('+'):
                    try: prev=rank+int(mt[1:]); mv="up"
                    except: prev=rank; mv="same"
                elif mt.startswith('-'):
                    try: prev=rank-int(mt[1:]); mv="down"
                    except: prev=rank; mv="same"
                else: prev=rank; mv="same"
                entries.append({"position":rank,"track":{"title":title,"artist":artist},"previousPosition":prev,"movement":mv,"weeksOnChart":1,"peakPosition":rank,"source":"kworb_itunes"})
        print(f"    ✅ {len(entries)} entrées")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_itunes_rss(url,country_name):
    print(f"  🔍 iTunes RSS — {country_name}...")
    try:
        r=requests.get(url,headers=HEADERS,timeout=30); r.raise_for_status()
        feed=r.json().get('feed',{}).get('entry',[])
        entries=[]
        for idx,e in enumerate(feed):
            try:
                title=e.get('im:name',{}).get('label',''); artist=e.get('im:artist',{}).get('label','')
                imgs=e.get('im:image',[]); art=imgs[-1].get('label','') if imgs else ''
                au=e.get('id',{}).get('label',''); ai=None
                if au and 'music.apple.com' in au:
                    m=re.search(r'/(\d+)(?:\?|$)',au)
                    if m: ai=int(m.group(1))
                else: au=''
                if title and artist:
                    it={"position":idx+1,"track":{"title":title,"artist":artist,"artwork":art},"previousPosition":None,"movement":"new" if idx==0 else "same","weeksOnChart":1,"peakPosition":idx+1,"source":"itunes_rss"}
                    if ai and au: it["apple_id"]=ai; it["apple_url"]=au
                    entries.append(it)
            except Exception: continue
        print(f"    ✅ {len(entries)} entrées")
        return entries
    except Exception as ex:
        print(f"    ❌ {ex}"); return []

def fetch_snep_latest():
    print("  🔍 snepmusique.com (officiel)...")
    try:
        r=requests.get("https://snepmusique.com/classement-radio/",headers=HEADERS,timeout=30)
        if r.status_code==404:
            print("    ❌ 404"); return []
        r.raise_for_status()
        if "Aucun classement" in r.text or len(r.text)<1000:
            print("    ❌ Aucune donnée"); return []
        entries=parse_snep_html(r.text)
        if not entries:
            print("    ❌ Aucune entrée parsée"); return []
        entries.sort(key=lambda x:x["position"])
        seen=set(); uniq=[]
        for e in entries:
            if e["position"] not in seen: seen.add(e["position"]); uniq.append(e)
        entries=uniq[:200]
        print(f"    ✅ {len(entries)} entrées via SNEP")
        n=sum(1 for e in entries if e.get('movement')=='new')
        u=sum(1 for e in entries if e.get('movement')=='up')
        d=sum(1 for e in entries if e.get('movement')=='down')
        print(f"       📊 {n} nouvelles, {u} ▲, {d} ▼")
        return entries
    except Exception as ex:
        print(f"    ❌ SNEP: {ex}"); return []

def parse_snep_html(html):
    lines=[l.strip() for l in BeautifulSoup(html,'html.parser').get_text(separator='\n',strip=True).split('\n') if l.strip()]
    labels=['SONY MUSIC','UNIVERSAL','WARNER MUSIC','BELIEVE','WAGRAM','WAGRAM MUSIC','IDOL','SCORPIO','HAPPY MUSIC',
            'THIRTY KNOTS','NOJOKE RECORDS','AWAL','EMPIRE','BECAUSE MUSIC','LEVEL UP MUSIC','YPDP','ARGENTIC MUSIC',
            'STMPD RCRDS','FIDEL','TRINITY','LORE','THE ORCHARD','UNIVERSAL MUSIC','POLYDOR','VIRGIN','PARLOPHONE',
            'EPIC','COLUMBIA','RCA','ATLANTIC','ELEKTRA','DEF JAM','PLAY TWO','EARLY BIRD','TÔT OU TARD','NAÏVE','PIAS',
            'WARNER','SONY','BECAUSE','3EME OEIL']
    lu=[l.upper().strip() for l in labels]
    entries=[]; i=0
    while i<len(lines):
        m=re.match(r'^(\d{1,3})$',lines[i])
        if m:
            pos=int(m.group(1))
            if 1<=pos<=200:
                block=lines[i+1:min(i+13,len(lines))]
                if len(block)>=5:
                    title=block[0]; artist=block[1]; label=""
                    prev=None; mv="same"; weeks=1
                    if block[2].upper() in lu: label=block[2]; start=3
                    else: start=2
                    for k,b in enumerate(block[start:],start=start):
                        if 'La Semaine Dernière' in b and k>=2 and block[k-2].isdigit():
                            prev=int(block[k-2]); mv="up" if prev>pos else ("down" if prev<pos else "same")
                        elif 'Semaine dans le Top' in b and k>=2 and block[k-2].isdigit():
                            weeks=int(block[k-2])
                            if weeks==1: mv="new"; prev=None
                    if len(title)>2 and len(artist)>2 and not any(k in title.lower() for k in ['semaine','top radio','actualités','les tops','news','newsletter']):
                        entries.append({"position":pos,"track":{"title":title,"artist":artist},"label":label or None,"previousPosition":prev,"movement":mv,"weeksOnChart":weeks,"peakPosition":pos,"source":"snep"})
        i+=1
    return entries

# ===== MAIN =====
def main():
    global youtube_quota_exceeded
    print(f"🎵 Collecte — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    cache=load_cache()
    print("✅ YouTube API configurée" if YOUTUBE_API_KEY else "⚠️ Pas de clé YouTube → yt-dlp")
    print(f"   Limites/pays : YT {YOUTUBE_LIMIT_PER_COUNTRY} · Deezer {DEEZER_LIMIT_PER_COUNTRY} · Apple {APPLE_LIMIT_PER_COUNTRY} · Dailymotion {DAILYMOTION_LIMIT_PER_COUNTRY}")
    print("🍎 Apple + 📺 Dailymotion : API publiques sans clé\n")
    w=get_week_info()
    data={"meta":{"weekLabel":w["label"],"week":w["week"],"year":w["year"],"updatedAt":w["date"],"sourceNote":"","hasStreamingIds":True,"cacheSize":len(cache)},
          "countries":{},"regions":{"europe":{"label":"Europe","countries":[]},"anglo":{"label":"Pays anglo-saxons","countries":[]},
          "latam":{"label":"Amérique du Sud","countries":[]},"asia":{"label":"Asie","countries":[]}}}
    ok=[]; ko=[]
    for code,ci in SOURCES.items():
        print(f"\n📊 {ci['name']} {ci['flag']}...")
        s=ci["source"]; entries=[]
        if s=="acharts": entries=fetch_acharts(ci["acharts_url"],ci["name"])
        elif s=="billboard_brasil":
            entries=fetch_billboard_brasil()
            if not entries or len(entries)<5:
                print("  🔄 Fallback Pro-Música..."); entries=fetch_brazil_promusica()
        elif s=="official_charts": entries=fetch_official_charts_indie()
        elif s=="kworb_itunes": entries=fetch_kworb_itunes(ci["kworb_url"],ci["name"])
        elif s=="promusica": entries=fetch_brazil_promusica()
        elif s=="itunes_rss": entries=fetch_itunes_rss(ci["itunes_url"],ci["name"])
        elif s=="snep": entries=fetch_snep_latest()
        if entries and len(entries)>=5:
            entries=enrich_with_cache(entries,cache,ci["name"])
            data["countries"][code]={"name":ci["name"],"flag":ci["flag"],"region":ci["region"],"chart":entries,"sourceType":s}
            data["regions"][ci["region"]]["countries"].append(code)
            ok.append(ci["name"]); print(f"  ✅ {len(entries)} titres via {s}")
        else:
            ko.append(ci["name"]); print("  ❌ Échec")
    save_cache(cache)
    if youtube_quota_exceeded: print("\n⚠️ Quota YouTube dépassé → yt-dlp utilisé")
    if ok and ko: data["meta"]["sourceNote"]=f"✅ {len(ok)} sources OK. ❌ {len(ko)} échouées."
    elif ok: data["meta"]["sourceNote"]=f"✅ Toutes les sources : {len(ok)} tops collectés."
    else: data["meta"]["sourceNote"]="❌ Aucune source collectée."
    os.makedirs("data",exist_ok=True)
    for path in ["data/charts-latest.json",f"data/charts-{w['date']}.json"]:
        with open(path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
    print(f"\n{'='*60}\n✅ Terminée — {len(ok)} OK / {len(ko)} KO — cache {len(cache)} titres\n{'='*60}")

if __name__=="__main__":
    main()