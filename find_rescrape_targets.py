#!/usr/bin/env python3
"""
Identifie les semaines candidates à un re-scraping ciblé. Lecture seule.

Deux modes de référence :
  - taille attendue connue (top-archives, chartsinfrance) → trous sur 1..attendu
  - taille inconnue (SNEP) → trous INTERNES sur 1..max(position présente)
    (activé par --include-snep)

Limite du mode interne : un trou en toute dernière position est indétectable,
puisque la référence est la plus grande position présente.
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
    ap.add_argument("--include-snep", action="store_true",
                    help="inclure SNEP via détection de trous internes")
    args = ap.parse_args()

    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}")
        return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    sparse, massive, clean = [], [], 0
    per_year = defaultdict(lambda: {"weeks": 0, "sparse": 0, "massive": 0})
    mode_count = defaultdict(int)

    for key, a in cache.items():
        if not isinstance(a, dict):
            continue
        src = a.get("source", "")
        entries = a.get("entries") or []
        pos = {e.get("position") for e in entries if isinstance(e.get("position"), int)}
        if not pos:
            continue

        exp = expected_size(key, src)
        mode = "attendu"
        if exp is None:
            if not args.include_snep:
                continue
            exp = max(pos)          # référence interne
            mode = "interne"

        gaps = sorted(set(range(1, exp + 1)) - pos)
        if not gaps:
            clean += 1
            continue

        m = re.match(r"^(\d{4})-", str(key))
        yr = int(m.group(1)) if m else 0
        y = per_year[(yr, src)]
        y["weeks"] += 1
        mode_count[mode] += 1

        rec = {"key": key, "source": src, "entries": len(entries),
               "expected": exp, "gaps": gaps, "mode": mode}
        if len(gaps) <= args.max_gaps:
            sparse.append(rec)
            y["sparse"] += 1
        else:
            massive.append(rec)
            y["massive"] += 1

    print("=" * 78)
    print("RÉSUMÉ")
    print("=" * 78)
    print(f"  archives sans trou                  : {clean}")
    print(f"  trous épars  (≤ {args.max_gaps}) → candidats : {len(sparse)}")
    print(f"  trous massifs (> {args.max_gaps}) → à part  : {len(massive)}")
    print(f"  référence attendue : {mode_count['attendu']}   interne : {mode_count['interne']}")
    if not args.include_snep:
        print("  (SNEP ignoré — ajouter --include-snep pour les trous internes)")

    print("\n" + "=" * 78)
    print("PAR ANNÉE / SOURCE")
    print("=" * 78)
    for (yr, src), y in sorted(per_year.items()):
        print(f"{yr}  {src:22s} épars {y['sparse']:3d}   massifs {y['massive']:3d}")

    print("\n" + "=" * 78)
    print(f"CANDIDATS (trous épars) — {len(sparse)}")
    print("=" * 78)
    for r in sorted(sparse, key=lambda x: x["key"])[:args.limit]:
        g = ", ".join(str(x) for x in r["gaps"])
        tag = " [interne]" if r["mode"] == "interne" else ""
        print(f"  {r['key']}  {r['entries']:3d}/{r['expected']:3d}  trous : {g}{tag}")
    if len(sparse) > args.limit:
        print(f"  … et {len(sparse) - args.limit} autres")

    if massive:
        print("\n" + "=" * 78)
        print(f"TROUS MASSIFS — {len(massive)}")
        print("=" * 78)
        for r in sorted(massive, key=lambda x: -len(x["gaps"]))[:20]:
            g = ", ".join(str(x) for x in r["gaps"][:20])
            tag = " [interne]" if r["mode"] == "interne" else ""
            print(f"  {r['key']}  {r['entries']:3d}/{r['expected']:3d}  {len(r['gaps'])} trous : {g}{tag}")
        if len(massive) > 20:
            print(f"  … et {len(massive) - 20} autres")

    os.makedirs(os.path.dirname(TARGETS), exist_ok=True)
    with open(TARGETS, "w", encoding="utf-8") as f:
        json.dump([r["key"] for r in sorted(sparse, key=lambda x: x["key"])],
                  f, ensure_ascii=False, indent=2)
    print(f"\n💾 {len(sparse)} clé(s) : {TARGETS}")
    print("   ⚠️ Candidats, pas certitudes. Ce script n'a rien modifié.")


if __name__ == "__main__":
    main()