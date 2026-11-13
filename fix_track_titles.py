#!/usr/bin/env python3
"""
Répare les archives rétro via data/track_overrides.json.
Actions : rename (défaut) | delete (entrées fantômes)

Usage :
  python fix_track_titles.py --dry-run
  python fix_track_titles.py
  python fix_track_titles.py --force
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
    t = str(t or "").strip()
    if not t:
        return True
    return re.fullmatch(r"[\d\s\.\-–—#/°]+", t) is not None


def load_rules():
    if not os.path.exists(OVERRIDES):
        print(f"❌ Table absente : {OVERRIDES}")
        return []
    with open(OVERRIDES, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for r in raw:
        am = (r.get("artist_match") or "").strip()
        if not am:
            continue
        action = (r.get("action") or "rename").lower()
        if action == "rename" and not (r.get("new_title") or "").strip():
            continue
        out.append({
            "action": action,
            "needle": am.lower(),
            "needle_norm": norm(am),
            "title_needle": (r.get("title_match") or "").strip().lower(),
            "title_needle_norm": norm(r.get("title_match") or ""),
            "new_title": (r.get("new_title") or "").strip(),
            "new_artist": (r.get("new_artist") or am).strip(),
            "years": set(r.get("years") or []),
            "numeric_only": bool(r.get("only_if_numeric_title", True)),
        })
    n_del = sum(1 for r in out if r["action"] == "delete")
    print(f"📋 {len(out)} règle(s) : {len(out)-n_del} renommage(s), {n_del} suppression(s)")
    return out


def matches(rule, artist, title, year, force):
    if rule["years"] and year not in rule["years"]:
        return False
    a_low, t_low = str(artist or "").lower(), str(title or "").lower()
    if rule["needle"] not in a_low and rule["needle"] not in t_low:
        return False
    if not (rule["needle_norm"] in norm(artist) or rule["needle_norm"] in norm(title)):
        return False
    if rule["title_needle"]:
        if rule["title_needle"] not in t_low and rule["title_needle"] not in a_low:
            return False
    if rule["action"] == "rename":
        if rule["numeric_only"] and not force and not is_numeric_title(title):
            return False
    return True


def process(key, archive, rules, force, dry, report):
    if not isinstance(archive, dict):
        return 0, 0
    m = re.match(r"^(\d{4})-(\d{1,2})$", str(key))
    try:
        year = int(m.group(1)) if m else int(archive.get("year"))
    except (TypeError, ValueError):
        year = None

    entries = archive.get("entries") or []
    kept = []
    renamed = deleted = 0

    for entry in entries:
        tr = entry.get("track")
        if not isinstance(tr, dict):
            kept.append(entry)
            continue
        old_t, old_a = tr.get("title", ""), tr.get("artist", "")
        drop = False
        for rule in rules:
            if not matches(rule, old_a, old_t, year, force):
                continue
            if rule["action"] == "delete":
                report.append({"week": key, "pos": entry.get("position"), "kind": "SUPPRESSION",
                               "before": f"{old_a} — {old_t}", "after": "(entrée fantôme supprimée)"})
                deleted += 1
                drop = True
            else:
                nt, na = rule["new_title"], rule["new_artist"]
                if nt != old_t or na != old_a:
                    report.append({"week": key, "pos": entry.get("position"), "kind": "RENOMMAGE",
                                   "before": f"{old_a} — {old_t}", "after": f"{na} — {nt}"})
                    if not dry:
                        tr["title"], tr["artist"] = nt, na
                    renamed += 1
            break
        if not drop:
            kept.append(entry)

    if deleted and not dry:
        archive["entries"] = kept
    return renamed, deleted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    print(f"🔧 Correction des archives — {datetime.now():%Y-%m-%d %H:%M:%S}")
    if args.dry_run: print("   (aperçu)")
    if args.force:   print("   (force)")

    rules = load_rules()
    if not rules:
        return

    report = []
    tot_r = tot_d = 0

    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        r = d = 0
        for key, arch in cache.items():
            a, b = process(key, arch, rules, args.force, args.dry_run, report)
            r += a; d += b
        print(f"📦 {CACHE_PATH} : {r} renommage(s), {d} suppression(s) / {len(cache)} archives")
        if (r or d) and not args.dry_run:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print("   💾 écrit")
        tot_r += r; tot_d += d
    else:
        print(f"⚠️ Absent : {CACHE_PATH}")

    paths = sorted(glob.glob(ARCH_GLOB))
    if paths:
        nf = 0
        for p in paths:
            m = re.search(r"top50-(\d{4})-(\d{1,2})\.json$", os.path.basename(p))
            key = f"{m.group(1)}-{int(m.group(2)):02d}" if m else ""
            try:
                with open(p, "r", encoding="utf-8") as f:
                    arch = json.load(f)
            except Exception:
                continue
            a, b = process(key, arch, rules, args.force, args.dry_run, report)
            if a or b:
                nf += 1; tot_r += a; tot_d += b
                if not args.dry_run:
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(arch, f, ensure_ascii=False, indent=2)
        print(f"📂 {len(paths)} fichier(s) analysé(s), {nf} modifié(s)")

    print(f"\n{'='*70}")
    if not report:
        print("✅ Aucune correction nécessaire.")
        return
    print(f"{'APERÇU' if args.dry_run else 'APPLIQUÉ'} : {tot_r} renommage(s), {tot_d} suppression(s)")
    print("="*70)
    for x in report[:50]:
        print(f"  [{x['kind']}] {x['week']} · #{x['pos']}")
        print(f"     avant : {x['before']}")
        print(f"     après : {x['after']}")
    if len(report) > 50:
        print(f"  … et {len(report)-50} autre(s)")
    print("="*70)
    if not args.dry_run:
        print("\n⚠️ Régénère l'index artiste (Build Artist Index).")
        if tot_d:
            print(f"ℹ️ {tot_d} entrée(s) fantôme(s) supprimée(s). Les vrais titres écrasés")
            print("   ne sont PAS restaurés : il faut re-scraper les semaines concernées.")


if __name__ == "__main__":
    main()