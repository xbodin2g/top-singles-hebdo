#!/usr/bin/env python3
"""
Re-scraping ciblé, à l'unité ou en lot.
Par défaut : dry-run, aucune écriture. --apply pour enregistrer.

Référence de comparaison : plus grande position présente (avant ∪ après).
Aucun plafond arbitraire — les classements courts ne génèrent plus de faux trous.

Sécurités :
  - échec du scraping     → archive d'origine restaurée
  - position(s) perdue(s) → semaine rejetée, archive d'origine restaurée
  - sauvegarde périodique en mode lot
"""
import json, os, re, argparse, copy
from datetime import datetime
import fetch_archive_batch as fab

REPORT = "data/rescrape_test_report.json"
TARGETS = "data/rescrape_targets.json"
SAVE_EVERY = 25


def positions(arch):
    out = {}
    for e in (arch.get("entries") or []):
        p = e.get("position")
        if isinstance(p, int):
            tr = e.get("track") or {}
            out[p] = f"{tr.get('artist','')} — {tr.get('title','')}"
    return out


def resolve_keys(args):
    if args.keys:
        return [k.strip() for k in args.keys.split(",") if k.strip()]
    path = args.list or TARGETS
    if not os.path.exists(path):
        print(f"❌ liste absente : {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        keys = [str(k) for k in json.load(f)]
    if args.year:
        keys = [k for k in keys if k.startswith(str(args.year) + "-")]
    keys.sort()
    if args.limit and args.limit > 0:
        keys = keys[:args.limit]
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys")
    ap.add_argument("--list")
    ap.add_argument("--year")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    keys = resolve_keys(args)
    if not keys:
        print("Aucune clé à traiter.")
        return

    print(f"🧪 Re-scraping ciblé — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("   mode : " + ("APPLY (écriture)" if args.apply else "DRY-RUN (aucune écriture)"))
    print(f"   {len(keys)} semaine(s) à traiter")
    if args.year:
        print(f"   filtre année : {args.year}")

    cache = fab.load_retro_cache()
    fab._load_overrides()

    report = []
    n_ok = n_fail = n_reject = 0
    rec_total = lost_total = 0
    done = 0

    for raw in keys:
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
        pb = positions(before)

        print(f"\n{'='*70}")
        print(f"{key}  source={src}")
        print(f"  avant : {len(pb)} entrées, max #{max(pb) if pb else 0}")

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
            n_fail += 1
            print("  ❌ échec → archive d'origine restaurée")
            report.append({"key": key, "status": "echec"})
            continue

        fab.apply_track_overrides({key: cache[key]})
        pa = positions(cache[key])

        ref = max(max(pb) if pb else 0, max(pa) if pa else 0)
        gaps_before = sorted(set(range(1, ref + 1)) - set(pb))
        gaps_after = sorted(set(range(1, ref + 1)) - set(pa))

        print(f"  après : {len(pa)} entrées, max #{max(pa) if pa else 0}  (référence {ref})")
        print(f"  trous avant : {gaps_before}")
        print(f"  trous après : {gaps_after}")

        recovered = [p for p in gaps_before if p in pa]
        still = [p for p in gaps_before if p not in pa]
        lost = [p for p in pb if p not in pa]

        if lost:
            cache[key] = before
            n_reject += 1
            lost_total += len(lost)
            print(f"  🔴 REJETÉE — {len(lost)} position(s) perdue(s) : {lost}")
            for p in lost:
                print(f"     #{p}  était : {pb[p]}")
            if recovered:
                print(f"  (récupérées mais annulées : {recovered})")
            report.append({"key": key, "status": "rejetee",
                           "lost": {str(p): pb[p] for p in lost},
                           "recovered_annulees": {str(p): pa[p] for p in recovered}})
            continue

        n_ok += 1
        rec_total += len(recovered)
        if recovered:
            print(f"  ✅ {len(recovered)} récupérée(s) :")
            for p in recovered:
                print(f"     #{p}  {pa[p]}")
        if still:
            print(f"  ⚪ {len(still)} toujours absente(s) : {still}")
        if not recovered and not still:
            print("  ⚪ aucun changement")

        report.append({"key": key, "status": "ok",
                       "entries_before": len(pb), "entries_after": len(pa),
                       "reference": ref,
                       "gaps_before": gaps_before, "gaps_after": gaps_after,
                       "recovered": {str(p): pa[p] for p in recovered},
                       "still_missing": still})

        done += 1
        if args.apply and done % SAVE_EVERY == 0:
            fab.save_retro_cache(cache)
            print(f"  💾 sauvegarde intermédiaire ({done} semaines)")

    print(f"\n{'='*70}")
    print("BILAN")
    print("="*70)
    print(f"  semaines améliorées  : {n_ok}")
    print(f"  échecs (restaurées)  : {n_fail}")
    print(f"  rejetées (régression): {n_reject}")
    print(f"  positions récupérées : {rec_total}")
    print(f"  positions perdues    : {lost_total}  (toutes restaurées)")
    print("="*70)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 rapport : {REPORT}")

    if args.apply:
        if n_ok:
            fab.save_retro_cache(cache)
            print("\n✅ Cache mis à jour. Pense à régénérer l'index artiste.")
        else:
            print("\nAucune semaine améliorée — cache non modifié.")
    else:
        print("\n(dry-run : le cache n'a pas été modifié)")


if __name__ == "__main__":
    main()