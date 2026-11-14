#!/usr/bin/env python3
"""
Test de re-scraping ciblé sur quelques semaines.
Par défaut : dry-run, aucune écriture. --apply pour enregistrer.
Si le scraping échoue, l'archive d'origine est restaurée.
Si une position régresse, rien n'est écrit.

Usage :
  python test_rescrape.py --keys 1993-37,1994-07,2003-15
  python test_rescrape.py --keys 1993-37 --apply
"""
import json, os, re, argparse, copy
from datetime import datetime
import fetch_archive_batch as fab

REPORT = "data/rescrape_test_report.json"


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
    return 100


def positions(arch):
    out = {}
    for e in (arch.get("entries") or []):
        p = e.get("position")
        if isinstance(p, int):
            tr = e.get("track") or {}
            out[p] = f"{tr.get('artist','')} — {tr.get('title','')}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True, help="clés séparées par des virgules")
    ap.add_argument("--apply", action="store_true", help="écrire dans le cache")
    args = ap.parse_args()

    print(f"🧪 Test de re-scraping — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("   mode : " + ("APPLY (écriture)" if args.apply else "DRY-RUN (aucune écriture)"))

    cache = fab.load_retro_cache()
    fab._load_overrides()

    report = []
    recovered_total = 0

    for raw in args.keys.split(","):
        raw = raw.strip()
        m = re.match(r"^(\d{4})-(\d{1,2})$", raw)
        if not m:
            print(f"\n⚠️ clé invalide ignorée : {raw}")
            continue
        year, week = int(m.group(1)), int(m.group(2))
        key = f"{year}-{week:02d}"

        before = copy.deepcopy(cache.get(key))
        if not before:
            print(f"\n⚠️ {key} absent du cache — ignoré")
            continue

        src = before.get("source", "")
        exp = expected_size(key, src)
        pb = positions(before)
        gaps_before = sorted(set(range(1, exp + 1)) - set(pb))

        print(f"\n{'='*70}")
        print(f"{key}  source={src}  attendu={exp}")
        print(f"{'='*70}")
        print(f"  avant : {len(pb)} entrées, trous = {gaps_before}")

        del cache[key]
        ok = False
        try:
            if "chartsinfrance" in src:
                ok = fab.fetch_chartsinfrance_week(year, week, cache)
            elif "top-archives" in src:
                ok = fab.fetch_toparchives_week(year, week, cache)
            elif "snep" in src:
                ok = fab.fetch_snep_week(year, week, cache)
            else:
                print(f"  ⚠️ source non gérée : {src}")
        except Exception as e:
            print(f"  ❌ exception : {e}")

        if not ok or key not in cache:
            cache[key] = before
            print("  ❌ re-scraping échoué → archive d'origine restaurée")
            report.append({"key": key, "status": "echec", "gaps_before": gaps_before})
            continue

        fab.apply_track_overrides(cache)
        after = cache[key]
        pa = positions(after)
        gaps_after = sorted(set(range(1, exp + 1)) - set(pa))

        print(f"  après : {len(pa)} entrées, trous = {gaps_after}")

        recovered = [p for p in gaps_before if p in pa]
        still = [p for p in gaps_before if p not in pa]
        lost = [p for p in pb if p not in pa]

        if recovered:
            print(f"  ✅ {len(recovered)} position(s) récupérée(s) :")
            for p in recovered:
                print(f"     #{p}  {pa[p]}")
        if still:
            print(f"  ⚪ {len(still)} toujours absente(s) : {still}")
        if lost:
            print(f"  🔴 {len(lost)} position(s) PERDUE(S) : {lost}")
            for p in lost:
                print(f"     #{p}  était : {pb[p]}")

        recovered_total += len(recovered)
        report.append({
            "key": key, "status": "ok",
            "entries_before": len(pb), "entries_after": len(pa),
            "gaps_before": gaps_before, "gaps_after": gaps_after,
            "recovered": {str(p): pa[p] for p in recovered},
            "still_missing": still,
            "lost": {str(p): pb[p] for p in lost},
        })

    print(f"\n{'='*70}")
    print(f"BILAN : {recovered_total} position(s) récupérée(s) au total")
    print("="*70)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 rapport : {REPORT}")

    if args.apply:
        if any(r.get("lost") for r in report):
            print("\n🔴 Des positions ont été perdues sur au moins une semaine.")
            print("   Par sécurité, RIEN n'a été écrit.")
        else:
            fab.save_retro_cache(cache)
            print("\n✅ Cache mis à jour (aucune perte détectée).")
            print("   Pense à régénérer l'index artiste.")
    else:
        print("\n(dry-run : le cache n'a pas été modifié)")


if __name__ == "__main__":
    main()