#!/usr/bin/env python3
"""
Identifie les semaines candidates à un re-scraping ciblé.
Lecture seule : ne modifie ni le cache ni les archives.

Critère : positions absentes dans la séquence attendue.
  trous épars  (1 à 5)   → fantôme supprimé, candidat au re-scraping
  trous massifs (> 5)    → autre cause, à examiner séparément

Paliers de taille attendue (limitations réelles des sources) :
  top-archives.fr                 → 50
  chartsinfrance <  1998-10       → 50
  chartsinfrance >= 1998-10       → 100
  chartsinfrance >= 2014-01       → 25
"""
import json, os, re, argparse
from collections import defaultdict

CACHE = "data/cache/retro_archives.json"
TARGETS = "data/rescrape_targets.json"


def expected_size(key, source):
    s = (source or "").lower()
    k = str(key)
    if "top-archives" in s:
        return 50
    if "chartsinfrance" in s:
        if k >= "2014-01":
            return 25
        if k >= "1998-10":
            return 100
        return 50
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gaps", type=int, default=5,
                    help="nombre max de trous pour retenir une semaine (défaut 5)")
    ap.add_argument("--limit", type=int, default=50, help="lignes affichées")
    args = ap.parse_args()

    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}")
        return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    sparse, massive, clean = [], [], 0
    per_year = defaultdict(lambda: {"weeks": 0, "sparse": 0, "massive": 0})

    for key, a in cache.items():
        if not isinstance(a, dict):
            continue
        src = a.get("source", "")
        exp = expected_size(key, src)
        if not exp:
            continue

        entries = a.get("entries") or []
        pos = {e.get("position") for e in entries if isinstance(e.get("position"), int)}
        gaps = sorted(set(range(1, exp + 1)) - pos)
        if not gaps:
            clean += 1
            continue

        m = re.match(r"^(\d{4})-", str(key))
        yr = int(m.group(1)) if m else 0
        y = per_year[(yr, src)]
        y["weeks"] += 1

        rec = {"key": key, "source": src, "entries": len(entries),
               "expected": exp, "gaps": gaps}
        if len(gaps) <= args.max_gaps:
            sparse.append(rec)
            y["sparse"] += 1
        else:
            massive.append(rec)
            y["massive"] += 1

    print("=" * 76)
    print("RÉSUMÉ")
    print("=" * 76)
    print(f"  archives complètes (aucun trou)      : {clean}")
    print(f"  trous épars  (≤ {args.max_gaps}) → candidats : {len(sparse)}")
    print(f"  trous massifs (> {args.max_gaps}) → à part  : {len(massive)}")

    print("\n" + "=" * 76)
    print("PAR ANNÉE / SOURCE")
    print("=" * 76)
    for (yr, src), y in sorted(per_year.items()):
        print(f"{yr}  {src:22s} épars {y['sparse']:3d}   massifs {y['massive']:3d}")

    print("\n" + "=" * 76)
    print(f"CANDIDATS AU RE-SCRAPING (trous épars) — {len(sparse)}")
    print("=" * 76)
    for r in sorted(sparse, key=lambda x: x["key"])[:args.limit]:
        g = ", ".join(str(x) for x in r["gaps"])
        print(f"  {r['key']}  {r['entries']:3d}/{r['expected']:3d}  trous : {g}")
    if len(sparse) > args.limit:
        print(f"  … et {len(sparse) - args.limit} autres")

    if massive:
        print("\n" + "=" * 76)
        print(f"TROUS MASSIFS — à examiner séparément, {len(massive)}")
        print("=" * 76)
        for r in sorted(massive, key=lambda x: -len(x["gaps"]))[:15]:
            print(f"  {r['key']}  {r['entries']:3d}/{r['expected']:3d}  {len(r['gaps'])} trous")
        if len(massive) > 15:
            print(f"  … et {len(massive) - 15} autres")

    os.makedirs(os.path.dirname(TARGETS), exist_ok=True)
    with open(TARGETS, "w", encoding="utf-8") as f:
        json.dump([r["key"] for r in sorted(sparse, key=lambda x: x["key"])],
                  f, ensure_ascii=False, indent=2)
    print(f"\n💾 {len(sparse)} clé(s) écrite(s) : {TARGETS}")
    print("   ⚠️ Liste de CANDIDATS, pas une certitude. À relire avant re-scraping.")
    print("   Ce script n'a rien modifié dans le cache.")


if __name__ == "__main__":
    main()