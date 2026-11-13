#!/usr/bin/env python3
"""
Détecte empiriquement les paliers de taille de classement chartsinfrance.
Lecture seule. Ne modifie rien.

Méthode : on cherche la première semaine à partir de laquelle
5 semaines consécutives ont moins de 40 entrées.
"""
import json, os, re
from collections import defaultdict

CACHE = "data/cache/retro_archives.json"
LOW_THRESHOLD = 40      # en dessous : régime "top court"
WINDOW = 5              # semaines consécutives pour confirmer


def main():
    if not os.path.exists(CACHE):
        print(f"❌ absent : {CACHE}")
        return
    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    rows = []
    for key, a in cache.items():
        if not isinstance(a, dict):
            continue
        if "chartsinfrance" not in (a.get("source", "").lower()):
            continue
        if not re.match(r"^\d{4}-\d{2}$", str(key)):
            continue
        rows.append((key, len(a.get("entries") or [])))
    rows.sort()

    if not rows:
        print("Aucune archive chartsinfrance.")
        return

    print("=" * 70)
    print("PAR ANNÉE — chartsinfrance.net")
    print("=" * 70)
    per_year = defaultdict(list)
    for k, n in rows:
        per_year[k[:4]].append(n)
    for yr in sorted(per_year):
        v = per_year[yr]
        v_sorted = sorted(v)
        med = v_sorted[len(v) // 2]
        print(f"{yr}  {len(v):3d} sem.  min {min(v):3d}  médiane {med:3d}  max {max(v):3d}")

    # détection du basculement
    switch = None
    for i in range(len(rows) - WINDOW + 1):
        if all(rows[i + j][1] < LOW_THRESHOLD for j in range(WINDOW)):
            switch = rows[i][0]
            break

    print("\n" + "=" * 70)
    if switch:
        print(f"BASCULEMENT DÉTECTÉ : {switch}")
        print(f"(première de {WINDOW} semaines consécutives sous {LOW_THRESHOLD} entrées)")
    else:
        print("Aucun basculement durable détecté.")
    print("=" * 70)

    if switch:
        idx = next(i for i, (k, _) in enumerate(rows) if k == switch)
        lo = max(0, idx - 8)
        hi = min(len(rows), idx + 8)
        print("\nAutour du basculement :")
        for k, n in rows[lo:hi]:
            mark = "  <<< bascule" if k == switch else ""
            print(f"  {k}  {n:3d} entrées{mark}")

    print("\n" + "=" * 70)
    print("Ce script n'a rien modifié.")
    print("Reporte la clé détectée dans expected_size() des scripts d'audit.")


if __name__ == "__main__":
    main()