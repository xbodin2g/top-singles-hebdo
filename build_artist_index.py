#!/usr/bin/env python3
"""
Génère un index artiste à partir des archives rétro.

Entrée :
- data/cache/retro_archives.json (prioritaire)
- ou data/archives/top50-*.json

Sortie :
- data/cache/artist_index.json
"""

import json
import os
import re
import glob
import unicodedata
from datetime import datetime, timezone

ARCHIVE_CACHE = os.path.join("data", "cache", "retro_archives.json")
ARCHIVE_GLOB = os.path.join("data", "archives", "top50-*.json")
OUTPUT_PATH = os.path.join("data", "cache", "artist_index.json")


def strip_accents(text):
    return "".join(
        ch for ch in unicodedata.normalize("NFD", str(text or ""))
        if unicodedata.category(ch) != "Mn"
    )


def normalize_space(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def remove_brackets(text):
    return re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(text or ""))


TITLE_NOISE_RE = re.compile(
    r"\b(?:official|video|clip|lyrics|lyric|audio|remix|edit|version|live|ao vivo|acoustique|instrumental)\b",
    re.I
)


def normalize_title(title):
    t = remove_brackets(title)
    t = strip_accents(t).lower()
    t = TITLE_NOISE_RE.sub(" ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return normalize_space(t)


# On sépare l'artiste principal :
# - avant une virgule
# - avant un slash
# - avant featuring / feat / ft / x
# On ne coupe PAS sur "&" ni "and" pour préserver les duos type "Felipe & Rodrigo"
ARTIST_SPLIT_RE = re.compile(
    r"\s*(?:,|/|\s+(?:featuring|feat\.?|ft\.?|x)\s+)\s*",
    re.I
)


def extract_primary_artist(raw_artist):
    s = normalize_space(remove_brackets(raw_artist))
    parts = ARTIST_SPLIT_RE.split(s, maxsplit=1)
    primary = parts[0].strip()
    primary = re.sub(r"^[\s\-–—&]+|[\s\-–—&]+$", "", primary)
    if not primary:
        primary = s
    return primary


def normalize_artist_key(primary):
    s = strip_accents(primary).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(?:feat|featuring|ft)\b.*$", "", s, flags=re.I)
    return normalize_space(s)


def parse_key_from_filename(path):
    m = re.search(r"top50-(\d{4})-(\d{1,2})\.json$", os.path.basename(path))
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None


def load_archives():
    archives = {}

    # 1) Cache principal
    if os.path.exists(ARCHIVE_CACHE):
        try:
            with open(ARCHIVE_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    archives.update(data)
            print(f"📦 Cache rétro chargé : {ARCHIVE_CACHE}")
        except Exception as e:
            print(f"⚠️ Erreur lecture du cache rétro : {e}")

    # 2) Fallback sur fichiers individuels
    if not archives:
        paths = sorted(glob.glob(ARCHIVE_GLOB))
        print(f"📂 Fallback sur {len(paths)} fichiers archives...")
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                key = None
                year = data.get("year")
                week = data.get("week")

                if year and week:
                    key = f"{int(year):04d}-{int(week):02d}"
                else:
                    key = parse_key_from_filename(path)

                if key:
                    archives[key] = data
            except Exception as e:
                print(f"⚠️ Erreur lecture {path} : {e}")

    return archives


def build_index(archives):
    track_stats = {}

    sorted_keys = sorted(archives.keys())

    for key in sorted_keys:
        archive = archives[key]
        if not isinstance(archive, dict):
            continue

        m = re.match(r"^(\d{4})-(\d{2})$", key)
        if m:
            year = int(m.group(1))
            week = int(m.group(2))
        else:
            year = archive.get("year")
            week = archive.get("week")
            if not year or not week:
                continue
            year = int(year)
            week = int(week)
            key = f"{year:04d}-{week:02d}"

        date = archive.get("date") or ""
        entries = archive.get("entries") or []

        for entry in entries:
            track = entry.get("track") or {}
            raw_title = str(track.get("title") or "").strip()
            raw_credit = str(track.get("artist") or "").strip()

            if not raw_title or not raw_credit:
                continue

            try:
                position = int(entry.get("position"))
            except Exception:
                continue

            if position <= 0:
                continue

            primary = extract_primary_artist(raw_credit)
            artist_id = normalize_artist_key(primary)
            title_norm = normalize_title(raw_title)

            if not artist_id or not title_norm:
                continue

            track_key = f"{title_norm}|{artist_id}"
            ts = track_stats.get(track_key)

            if ts is None:
                track_stats[track_key] = {
                    "track_key": track_key,
                    "title": raw_title,
                    "credit": raw_credit,
                    "artist_id": artist_id,
                    "artist_display": primary,
                    "first_key": key,
                    "first_date": date,
                    "first_year": year,
                    "first_week": week,
                    "first_position": position,
                    "last_key": key,
                    "last_date": date,
                    "last_year": year,
                    "last_week": week,
                    "last_position": position,
                    "weeks": 1,
                    "peak": position,
                    "peak_key": key,
                    "peak_date": date,
                    "peak_year": year,
                    "peak_week": week,
                    "last_seen_key": key,
                }
                continue

            # Éviter de compter deux fois la même semaine si doublon dans l'archive
            if ts.get("last_seen_key") == key:
                if position < ts["peak"] or (position == ts["peak"] and key < ts["peak_key"]):
                    ts["peak"] = position
                    ts["peak_key"] = key
                    ts["peak_date"] = date
                    ts["peak_year"] = year
                    ts["peak_week"] = week
                continue

            ts["last_seen_key"] = key

            # Première apparition
            if key < ts["first_key"]:
                ts["first_key"] = key
                ts["first_date"] = date
                ts["first_year"] = year
                ts["first_week"] = week
                ts["first_position"] = position

            # Dernière apparition
            if key > ts["last_key"]:
                ts["last_key"] = key
                ts["last_date"] = date
                ts["last_year"] = year
                ts["last_week"] = week
                ts["last_position"] = position

            ts["weeks"] += 1

            # Meilleure place
            if position < ts["peak"] or (position == ts["peak"] and key < ts["peak_key"]):
                ts["peak"] = position
                ts["peak_key"] = key
                ts["peak_date"] = date
                ts["peak_year"] = year
                ts["peak_week"] = week

    artists = {}

    for ts in track_stats.values():
        aid = ts["artist_id"]
        artist = artists.get(aid)

        if artist is None:
            artist = {
                "id": aid,
                "name": ts["artist_display"],
                "tracks": [],
                "trackCount": 0,
                "totalWeeks": 0,
                "bestPeak": 999,
                "firstYear": 9999,
                "lastYear": 0,
                "firstKey": None,
                "firstDate": "",
                "lastKey": None,
                "lastDate": "",
            }
            artists[aid] = artist

        artist["tracks"].append({
            "key": ts["track_key"],
            "title": ts["title"],
            "credit": ts["credit"],
            "firstKey": ts["first_key"],
            "firstDate": ts["first_date"],
            "lastKey": ts["last_key"],
            "lastDate": ts["last_date"],
            "weeks": ts["weeks"],
            "peak": ts["peak"],
            "peakKey": ts["peak_key"],
            "peakDate": ts["peak_date"],
        })

        artist["trackCount"] += 1
        artist["totalWeeks"] += ts["weeks"]
        artist["bestPeak"] = min(artist["bestPeak"], ts["peak"])
        artist["firstYear"] = min(artist["firstYear"], ts["first_year"])
        artist["lastYear"] = max(artist["lastYear"], ts["last_year"])

        if artist["firstKey"] is None or ts["first_key"] < artist["firstKey"]:
            artist["firstKey"] = ts["first_key"]
            artist["firstDate"] = ts["first_date"]

        if artist["lastKey"] is None or ts["last_key"] > artist["lastKey"]:
            artist["lastKey"] = ts["last_key"]
            artist["lastDate"] = ts["last_date"]

    artist_list = list(artists.values())

    for artist in artist_list:
        artist["tracks"].sort(
            key=lambda t: (
                t["peak"],
                -t["weeks"],
                t["title"].lower()
            )
        )

    artist_list.sort(
        key=lambda a: (
            -a["trackCount"],
            -a["totalWeeks"],
            a["bestPeak"],
            a["name"].lower()
        )
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "archiveCount": len(archives),
        "artistCount": len(artist_list),
        "trackCount": len(track_stats),
        "artists": artist_list
    }


def main():
    print("🎤 Génération de l’index artiste...")
    archives = load_archives()

    if not archives:
        print("❌ Aucune archive trouvée.")
        return

    print(f"📚 {len(archives)} archives analysées")

    index = build_index(archives)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"✅ Index généré : {OUTPUT_PATH}")
    print(f"   - {index['artistCount']} artistes")
    print(f"   - {index['trackCount']} titres uniques")
    print(f"   - {index['archiveCount']} archives scannées")


if __name__ == "__main__":
    main()