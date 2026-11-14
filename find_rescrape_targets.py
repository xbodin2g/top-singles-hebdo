#!/usr/bin/env python3
"""
Cibles de re-scraping. Lecture seule.

Distinction fondamentale :
  trou INTERNE  = position absente SOUS la dernière position présente
                  → vraie anomalie, candidat au re-scraping
  trou de QUEUE = positions au-delà de la dernière présente
                  → la source a publié moins de titres, pas un bug

SNEP : taille attendue inconnue → seuls les trous internes sont évalués.
"""
import json, os, re, argparse
from collections import defaultdict

CACHE = "data/cache/retro_archives.json"
TARGETS = "data/rescrape_targets.json"


def cap_size(key, source):
    """Plafond théorique, ou None si inconnu."""
    s = (source or "").lower()
    k = str(key)
    if "top-archives" in s:
        return 50
    if "chartsinfrance" in s:
        if k >= "2012-06":
            return 25
        if k >= "1998-10":
            return 100
        return 50
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gaps", type=int, default=5)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}")
        return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    sparse, massive, short_tail = [], [], []
    clean = 0
    per_year = defaultdict(lambda: {"sparse": 0, "massive": 0, "tail": 0})

    for key, a in cache.items():
        if not isinstance(a, dict):
            continue
        src = a.get("source", "")
        pos = {e.get("position") for e in (a.get("entries") or [])
               if isinstance(e.get("position"), int)}
        if not pos:
            continue

        maxpos = max(pos)
        cap = cap_size(key, src)
        internal = sorted(set(range(1, maxpos + 1)) - pos)
        tail = sorted(set(range(maxpos + 1, cap + 1)) - pos) if cap else []

        m = re.match(r"^(\d{4})-", str(key))
        yr = int(m.group(1)) if m else 0
        y = per_year[(yr, src)]

        if not internal:
            clean += 1
            if tail:
                short_tail.append({"key": key, "source": src, "entries": len(pos),
                                   "cap": cap, "tail": tail})
                y["tail"] += 1
            continue

        rec = {"key": key, "source": src, "entries": len(pos),
               "maxpos": maxpos, "cap": cap, "gaps": internal, "tail": tail}
        if len(internal) <= args.max_gaps:
            sparse.append(rec)
            y["sparse"] += 1
        else:
            massive.append(rec)
            y["massive"] += 1

    print("=" * 78)
    print("RÉSUMÉ")
    print("=" * 78)
    print(f"  sans trou interne                    : {clean}")
    print(f"  trous internes épars (≤ {args.max_gaps}) → candidats : {len(sparse)}")
    print(f"  trous internes massifs (> {args.max_gaps})         : {len(massive)}")
    print(f"  queues courtes (source, non bug)     : {len(short_tail)}")

    print("\n" + "=" * 78)
    print("PAR ANNÉE / SOURCE")
    print("=" * 78)
    for (yr, src), y in sorted(per_year.items()):
        if not (y["sparse"] or y["massive"] or y["tail"]):
            continue
        print(f"{yr}  {src:22s} épars {y['sparse']:3d}  massifs {y['massive']:3d}  queue {y['tail']:3d}")

    print("\n" + "=" * 78)
    print(f"CANDIDATS — trous internes épars : {len(sparse)}")
    print("=" * 78)
    for r in sorted(sparse, key=lambda x: x["key"])[:args.limit]:
        g = ", ".join(str(x) for x in r["gaps"])
        print(f"  {r['key']}  {r['entries']:3d} titres, max #{r['maxpos']:3d}  trous : {g}")
    if len(sparse) > args.limit:
        print(f"  … et {len(sparse) - args.limit} autres")

    if massive:
        print("\n" + "=" * 78)
        print(f"TROUS INTERNES MASSIFS : {len(massive)}")
        print("=" * 78)
        for r in sorted(massive, key=lambda x: -len(x["gaps"]))[:20]:
            g = ", ".join(str(x) for x in r["gaps"][:20])
            print(f"  {r['key']}  {r['entries']:3d} titres  {len(r['gaps'])} trous : {g}")
        if len(massive) > 20:
            print(f"  … et {len(massive) - 20} autres")

    if short_tail:
        print("\n" + "=" * 78)
        print(f"QUEUES COURTES — la source a publié moins, aucune action : {len(short_tail)}")
        print("=" * 78)
        for r in sorted(short_tail, key=lambda x: x["key"])[:15]:
            print(f"  {r['key']}  {r['entries']:3d}/{r['cap']:3d}  absent au-delà de #{r['entries']}")
        if len(short_tail) > 15:
            print(f"  … et {len(short_tail) - 15} autres")

    os.makedirs(os.path.dirname(TARGETS), exist_ok=True)
    with open(TARGETS, "w", encoding="utf-8") as f:
        json.dump([r["key"] for r in sorted(sparse, key=lambda x: x["key"])],
                  f, ensure_ascii=False, indent=2)
    print(f"\n💾 {len(sparse)} clé(s) : {TARGETS}")
    print("   Seuls les trous INTERNES sont retenus. Ce script n'a rien modifié.")


if __name__ == "__main__":
    main()