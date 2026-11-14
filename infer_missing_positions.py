#!/usr/bin/env python3
"""
Infère les titres manquants en utilisant les métadonnées de mouvement
de la semaine SUIVANTE.

Principe :
  Si en semaine S+1, une entrée à la position P a previousPosition == Q,
  alors le titre était à la position Q en semaine S.

Limites :
  - Dernières semaines : pas de S+1 disponible
  - Nouveautés : previousPosition = None, non inférables
  - Titres sortis du classement en S+1 : non inférables

Usage :
  python infer_missing_positions.py                    # dry-run global
  python infer_missing_positions.py --keys 2010-17     # dry-run ciblé
  python infer_missing_positions.py --apply            # appliquer
"""
import json, os, re, argparse, copy
from datetime import datetime

CACHE = "data/cache/retro_archives.json"
REPORT = "data/missing_inferred_report.json"


def next_week_key(key):
    """Retourne la clé de la semaine suivante (AAAA-SS)."""
    m = re.match(r"^(\d{4})-(\d{1,2})$", key)
    if not m:
        return None
    year, week = int(m.group(1)), int(m.group(2))
    if week < 52:
        return f"{year}-{week + 1:02d}"
    return f"{year + 1}-01"


def positions_map(arch):
    """Retourne {position: entry} pour une archive."""
    out = {}
    for e in (arch.get("entries") or []):
        p = e.get("position")
        if isinstance(p, int):
            out[p] = e
    return out


def infer_from_next(cache, key):
    """
    Pour chaque trou interne en semaine S, regarde si S+1 contient
    une entrée dont previousPosition pointe vers ce trou.
    Retourne la liste des inférences possibles.
    """
    arch = cache.get(key)
    if not arch or not isinstance(arch, dict):
        return []

    entries = arch.get("entries") or []
    pos_set = {e.get("position") for e in entries if isinstance(e.get("position"), int)}
    if not pos_set:
        return []

    max_pos = max(pos_set)
    holes = sorted(set(range(1, max_pos + 1)) - pos_set)
    if not holes:
        return []

    next_key = next_week_key(key)
    if not next_key or next_key not in cache:
        return [{"hole": h, "status": "pas_de_semaine_suivante"} for h in holes]

    next_arch = cache[next_key]
    next_entries = next_arch.get("entries") or []

    # Index des previousPosition en S+1
    prev_to_entry = {}
    for e in next_entries:
        pp = e.get("previousPosition")
        if isinstance(pp, int):
            prev_to_entry[pp] = e

    infers = []
    for h in holes:
        if h in prev_to_entry:
            src = prev_to_entry[h]
            tr = src.get("track") or {}
            infers.append({
                "hole": h,
                "status": "inferable",
                "next_key": next_key,
                "next_position": src.get("position"),
                "artist": tr.get("artist", ""),
                "title": tr.get("title", ""),
                "label": tr.get("label") or (src.get("track") or {}).get("label"),
                "movement": src.get("movement"),
            })
        else:
            infers.append({
                "hole": h,
                "status": "non_inferable",
                "reason": "aucune_entree_en_S+1_avec_previousPosition_correspondant"
            })

    return infers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", help="semaines à traiter (séparées par virgules, vide = toutes)")
    ap.add_argument("--apply", action="store_true", help="appliquer les inférences")
    args = ap.parse_args()

    if not os.path.exists(CACHE):
        print(f"❌ cache absent : {CACHE}")
        return

    with open(CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    keys = (
        [k.strip() for k in args.keys.split(",") if k.strip()]
        if args.keys
        else sorted(cache.keys())
    )

    print(f"🔎 Inférence de positions manquantes — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"   mode : {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"   {len(keys)} semaine(s) à examiner\n")

    total_inferred = 0
    total_non_inferable = 0
    total_no_next = 0
    report = []

    for key in keys:
        infers = infer_from_next(cache, key)
        if not infers:
            continue

        week_report = {
            "key": key,
            "inferred": [],
            "non_inferable": [],
            "no_next": [],
        }

        for inf in infers:
            if inf["status"] == "inferable":
                week_report["inferred"].append(inf)
                total_inferred += 1
            elif inf["status"] == "pas_de_semaine_suivante":
                week_report["no_next"].append(inf)
                total_no_next += 1
            else:
                week_report["non_inferable"].append(inf)
                total_non_inferable += 1

        if not (week_report["inferred"] or week_report["non_inferable"] or week_report["no_next"]):
            continue

        report.append(week_report)

        if week_report["inferred"]:
            print(f"\n{key} — {len(week_report['inferred'])} inférable(s) :")
            for inf in week_report["inferred"]:
                mv = inf.get("movement", "?")
                print(f"   #{inf['hole']:3d}  {inf['artist']} — {inf['title']}  (vu en {inf['next_key']} #{inf['next_position']}, mv={mv})")

        if week_report["non_inferable"]:
            holes = [inf["hole"] for inf in week_report["non_inferable"]]
            print(f"   non inférables : {holes}")

        if week_report["no_next"]:
            holes = [inf["hole"] for inf in week_report["no_next"]]
            print(f"   pas de semaine suivante : {holes}")

    print(f"\n{'='*70}")
    print("BILAN")
    print("="*70)
    print(f"  positions inférables     : {total_inferred}")
    print(f"  positions non inférables : {total_non_inferable}")
    print(f"  pas de semaine suivante  : {total_no_next}")
    print("="*70)

    if not args.apply:
        print("\n(dry-run : aucune modification)")
        os.makedirs(os.path.dirname(REPORT) or ".", exist_ok=True)
        with open(REPORT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"💾 rapport : {REPORT}")
        return

    if not total_inferred:
        print("\nAucune inférence à appliquer.")
        return

    print(f"\n💾 Application de {total_inferred} inférence(s)...")

    for week_report in report:
        key = week_report["key"]
        arch = cache.get(key)
        if not arch:
            continue

        for inf in week_report["inferred"]:
            new_entry = {
                "position": inf["hole"],
                "track": {
                    "artist": inf["artist"],
                    "title": inf["title"],
                },
                "previousPosition": None,
                "movement": "unknown",
                "weeksOnChart": None,
                "peakPosition": None,
                "source": "inferred_from_next_week",
                "inferred_from": inf["next_key"],
            }
            if inf.get("label"):
                new_entry["track"]["label"] = inf["label"]

            arch.setdefault("entries", []).append(new_entry)
            print(f"   ✅ {key} #{inf['hole']} : {inf['artist']} — {inf['title']}")

    # Trier les entrées par position pour chaque archive modifiée
    for week_report in report:
        if week_report["inferred"]:
            arch = cache[week_report["key"]]
            arch["entries"] = sorted(
                arch["entries"],
                key=lambda e: e.get("position", 0)
            )

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Cache mis à jour avec {total_inferred} position(s) inférée(s)")
    print("   Pense à régénérer l'index artiste.")


if __name__ == "__main__":
    main()