#!/usr/bin/env python3
"""
Mesure la complétude des archives rétro. Lecture seule, ne modifie rien.

Tailles attendues :
  top-archives.fr                     → 50
  chartsinfrance.net < 1998-10        → 50   (Top 50 jusqu'au 26/02/1998)
  chartsinfrance.net >= 1998-10       → 100  (Top 100 à partir du 05/03/1998)
  snepmusique.com                     → non jugé (taille variable)
"""
import json, os, re
from collections import defaultdict

CACHE = "data/cache/retro_archives.json"
SWITCH_TOP100 = "1998-10"   # premier Top 100 chartsinfrance (05/03/1998)


def expected_size(key, source):
    s = (source or "").lower()
    if "top-archives" in s:
        return 50
    if "chartsinfrance" in s:
        return 100 if str(key) >= SWITCH_TOP100 else 50
    return None      # SNEP / inconnu : pas de jugement


def main():
    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}")
        return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    by_src = defaultdict(lambda: {"weeks": 0, "entries": 0, "min": 9999, "max": 0})
    by_year = defaultdict(lambda: {"weeks": 0, "entries": 0, "thin": 0, "missing": 0, "exp": 0})
    thin = []
    total_missing = 0

    for key, a in cache.items():
        if not isinstance(a, dict):
            continue
        src = a.get("source", "?")
        m = re.match(r"^(\d{4})-", str(key))
        yr = int(m.group(1)) if m else 0
        entries = a.get("entries") or []
        n = len(entries)
        exp = expected_size(key, src)

        s = by_src[src]
        s["weeks"] += 1
        s["entries"] += n
        s["min"] = min(s["min"], n)
        s["max"] = max(s["max"], n)

        y = by_year[(yr, src)]
        y["weeks"] += 1
        y["entries"] += n

        if exp:
            y["exp"] = exp
            gap = max(0, exp - n)
            if n < exp * 0.8:
                y["thin"] += 1
                y["missing"] += gap
                total_missing += gap
                positions = {e.get("position") for e in entries
                             if isinstance(e.get("position"), int)}
                holes = sorted(set(range(1, exp + 1)) - positions)
                thin.append((key, src, n, exp, len(holes)))

    print("=" * 78)
    print("PAR SOURCE")
    print("=" * 78)
    for src, s in sorted(by_src.items()):
        avg = s["entries"] / s["weeks"] if s["weeks"] else 0
        mn = s["min"] if s["min"] != 9999 else 0
        print(f"{src:24s} {s['weeks']:5d} sem.  moy {avg:6.1f}  min {mn:3d}  max {s['max']:3d}")

    print("\n" + "=" * 78)
    print("PAR ANNÉE / SOURCE   (thin = moins de 80 % du top attendu)")
    print("=" * 78)
    for (yr, src), y in sorted(by_year.items()):
        avg = y["entries"] / y["weeks"] if y["weeks"] else 0
        exp = f"attendu {y['exp']:3d}" if y["exp"] else "attendu  ? "
        flag = "  ⚠️" if y["thin"] else ""
        miss = f"  manque ~{y['missing']}" if y["missing"] else ""
        print(f"{yr}  {src:22s} {y['weeks']:3d} sem.  moy {avg:6.1f}  {exp}  thin {y['thin']:3d}{miss}{flag}")

    print("\n" + "=" * 78)
    print(f"ARCHIVES INCOMPLÈTES : {len(thin)}   ·   ENTRÉES MANQUANTES ≈ {total_missing}")
    print("=" * 78)
    for key, src, n, exp, h in sorted(thin)[:40]:
        print(f"  {key}  {src:22s} {n:3d}/{exp:3d}  ({h} positions absentes)")
    if len(thin) > 40:
        print(f"  … et {len(thin) - 40} autres")

    print("\n" + "=" * 78)
    print("Bascule Top 50 → Top 100 chartsinfrance : 1998-10 (05/03/1998)")
    print("SNEP n'est pas jugé : taille de classement variable selon les semaines.")
    print("Ce script ne modifie aucune donnée.")


if __name__ == "__main__":
    main()