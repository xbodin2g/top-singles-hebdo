#!/usr/bin/env python3
"""Mesure la complétude des archives : entrées/semaine, positions manquantes."""
import json, os, re
from collections import defaultdict

CACHE = "data/cache/retro_archives.json"

def main():
    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}"); return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    by_src = defaultdict(lambda: {"weeks": 0, "entries": 0, "min": 999, "max": 0})
    by_year = defaultdict(lambda: {"weeks": 0, "entries": 0, "thin": 0})
    thin = []

    for key, a in cache.items():
        if not isinstance(a, dict): continue
        src = a.get("source", "?")
        m = re.match(r"^(\d{4})-", str(key))
        yr = int(m.group(1)) if m else 0
        entries = a.get("entries") or []
        n = len(entries)
        positions = {e.get("position") for e in entries if isinstance(e.get("position"), int)}
        expected = 50 if "top-archives" in src else 100
        holes = sorted(set(range(1, min(expected, max(positions) if positions else 1) + 1)) - positions)

        s = by_src[src]
        s["weeks"] += 1; s["entries"] += n
        s["min"] = min(s["min"], n); s["max"] = max(s["max"], n)

        y = by_year[(yr, src)]
        y["weeks"] += 1; y["entries"] += n
        if n < expected * 0.8:
            y["thin"] += 1
            thin.append((key, src, n, len(holes)))

    print("="*74)
    print("PAR SOURCE")
    print("="*74)
    for src, s in sorted(by_src.items()):
        avg = s["entries"] / s["weeks"] if s["weeks"] else 0
        print(f"{src:24s} {s['weeks']:5d} sem.  moy {avg:6.1f}  min {s['min']:3d}  max {s['max']:3d}")

    print("\n" + "="*74)
    print("PAR ANNÉE / SOURCE  (thin = < 80 % du top attendu)")
    print("="*74)
    for (yr, src), y in sorted(by_year.items()):
        avg = y["entries"] / y["weeks"] if y["weeks"] else 0
        flag = "  ⚠️" if y["thin"] else ""
        print(f"{yr}  {src:22s} {y['weeks']:3d} sem.  moy {avg:6.1f}  thin {y['thin']:3d}{flag}")

    print("\n" + "="*74)
    print(f"ARCHIVES INCOMPLÈTES : {len(thin)}")
    print("="*74)
    for key, src, n, h in sorted(thin)[:40]:
        print(f"  {key}  {src:22s} {n:3d} entrées  ({h} trous)")
    if len(thin) > 40:
        print(f"  … et {len(thin)-40} autres")

if __name__ == "__main__":
    main()