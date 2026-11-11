#!/usr/bin/env python3
"""
Répare les titres erronés dans les archives rétro.
Applique data/track_overrides.json sur :
  - data/cache/retro_archives.json
  - data/archives/top50-*.json (si présents)

Usage :
  python fix_track_titles.py --dry-run     # aperçu sans écriture
  python fix_track_titles.py               # applique
  python fix_track_titles.py --force       # ignore only_if_numeric_title
"""
import json, os, re, glob, argparse, unicodedata
from datetime import datetime

CACHE_PATH = "data/cache/retro_archives.json"
ARCH_GLOB  = "data/archives/top50-*.json"
OVERRIDES  = "data/track_overrides.json"


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_numeric_title(t):
    """Signature du bug : titre vide ou composé uniquement de chiffres/ponctuation."""
    t = str(t or "").strip()
    if not t:
        return True
    return re.fullmatch(r"[\d\s\.\-–—#/°]+", t) is not None


def load_overrides():
    if not os.path.exists(OVERRIDES):
        print(f"❌ Table d'overrides absente : {OVERRIDES}")
        return []
    with open(OVERRIDES, "r", encoding="utf-8") as f:
        rules = json.load(f)
    out = []
    for r in rules:
        am = r.get("artist_match", "").strip()
        nt = r.get("new_title", "").strip()
        if not am or not nt:
            continue
        out.append({
            "needle": am.lower(),
            "needle_norm": norm(am),
            "new_title": nt,
            "new_artist": (r.get("new_artist") or "").strip() or None,
            "years": set(r.get("years") or []),
            "numeric_only": bool(r.get("only_if_numeric_title", True)),
        })
    print(f"📋 {len(out)} règle(s) de correction chargée(s)")
    return out


def match_rule(rule, artist, title, year, force):
    # filtre année
    if rule["years"] and year not in rule["years"]:
        return False
    # pré-filtre rapide (substring brut) puis vérification normalisée
    a_low = str(artist or "").lower()
    t_low = str(title or "").lower()
    hit_artist = rule["needle"] in a_low
    hit_title  = rule["needle"] in t_low   # cas d'inversion artiste/titre
    if not (hit_artist or hit_title):
        return False
    if not (rule["needle_norm"] in norm(artist) or rule["needle_norm"] in norm(title)):
        return False
    # garde-fou : ne toucher que les titres numériques, sauf --force
    if rule["numeric_only"] and not force and not is_numeric_title(title):
        return False
    return True


def fix_archive(key, archive, rules, force, dry, report):
    if not isinstance(archive, dict):
        return 0
    m = re.match(r"^(\d{4})-(\d{1,2})$", str(key))
    year = int(m.group(1)) if m else archive.get("year")
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = None

    changed = 0
    for entry in archive.get("entries") or []:
        track = entry.get("track")
        if not isinstance(track, dict):
            continue
        old_title  = track.get("title", "")
        old_artist = track.get("artist", "")
        for rule in rules:
            if not match_rule(rule, old_artist, old_title, year, force):
                continue
            new_title  = rule["new_title"]
            new_artist = rule["new_artist"] or (
                old_artist if rule["needle_norm"] in norm(old_artist) else rule["new_title"] and old_title
            )
            # si l'artiste était dans le champ titre (inversion), on remet l'artiste propre
            if rule["needle_norm"] in norm(old_title) and rule["needle_norm"] not in norm(old_artist):
                new_artist = rule["new_artist"] or rule["needle"].title()
            if new_title == old_title and new_artist == old_artist:
                break
            report.append({
                "week": key, "position": entry.get("position"),
                "before": f"{old_artist} — {old_title}",
                "after":  f"{new_artist} — {new_title}",
            })
            if not dry:
                track["title"]  = new_title
                track["artist"] = new_artist
            changed += 1
            break
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien")
    ap.add_argument("--force", action="store_true", help="corrige même si le titre n'est pas numérique")
    args = ap.parse_args()

    print(f"🔧 Correction des titres — {datetime.now():%Y-%m-%d %H:%M:%S}")
    if args.dry_run: print("   (mode aperçu)")
    if args.force:   print("   (mode force)")

    rules = load_overrides()
    if not rules:
        return

    total = 0
    report = []

    # 1) Cache principal
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        n = 0
        for key, arch in cache.items():
            n += fix_archive(key, arch, rules, args.force, args.dry_run, report)
        print(f"📦 {CACHE_PATH} : {n} entrée(s) concernée(s) sur {len(cache)} archives")
        if n and not args.dry_run:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print("   💾 écrit")
        total += n
    else:
        print(f"⚠️ Absent : {CACHE_PATH}")

    # 2) Fichiers individuels éventuels
    paths = sorted(glob.glob(ARCH_GLOB))
    if paths:
        n_files = 0
        for p in paths:
            key = None
            m = re.search(r"top50-(\d{4})-(\d{1,2})\.json$", os.path.basename(p))
            if m:
                key = f"{m.group(1)}-{int(m.group(2)):02d}"
            try:
                with open(p, "r", encoding="utf-8") as f:
                    arch = json.load(f)
            except Exception:
                continue
            n = fix_archive(key or "", arch, rules, args.force, args.dry_run, report)
            if n:
                n_files += 1
                total += n
                if not args.dry_run:
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(arch, f, ensure_ascii=False, indent=2)
        print(f"📂 {len(paths)} fichier(s) analysé(s), {n_files} modifié(s)")

    # Rapport
    print(f"\n{'='*66}")
    if not report:
        print("✅ Aucune correction nécessaire.")
        return
    print(f"{'APERÇU' if args.dry_run else 'CORRECTIONS'} : {len(report)} entrée(s)")
    print("="*66)
    for r in report[:60]:
        print(f"  {r['week']} · #{r['position']}")
        print(f"     avant : {r['before']}")
        print(f"     après : {r['after']}")
    if len(report) > 60:
        print(f"  … et {len(report)-60} autre(s)")
    print("="*66)
    print(f"Total : {total} entrée(s) {'à corriger' if args.dry_run else 'corrigée(s)'}")
    if not args.dry_run:
        print("\n⚠️ Pense à régénérer l'index artiste (Build Artist Index).")


if __name__ == "__main__":
    main()