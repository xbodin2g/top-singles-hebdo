#!/usr/bin/env python3
"""
Synchronise le top France de la semaine courante dans le cache rétro.

Source : data/charts-latest.json (collecté par fetch_charts.py)
Destination : data/cache/retro_archives.json

Comportement :
  - Si la semaine est déjà dans le rétro : ne fait rien
  - Sinon : ajoute l'entrée avec la structure attendue
  - Applique les overrides de titres (track_overrides.json)

Usage :
  python sync_current_week_to_retro.py
  python sync_current_week_to_retro.py --force    # écrase si existe déjà
"""
import json, os, argparse
from datetime import datetime, timedelta
import fetch_archive_batch as fab

CHARTS_LATEST = "data/charts-latest.json"
CACHE_RETRO = "data/cache/retro_archives.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="écraser la semaine si elle existe déjà")
    args = ap.parse_args()

    # Charger le top hebdo
    if not os.path.exists(CHARTS_LATEST):
        print(f"❌ Fichier absent : {CHARTS_LATEST}")
        return

    with open(CHARTS_LATEST, "r", encoding="utf-8") as f:
        charts = json.load(f)

    # Trouver le top France
    fr = charts.get("countries", {}).get("fr")
    if not fr:
        print("❌ Pas de top France dans charts-latest.json")
        return

    # Extraire les métadonnées
    year = charts["meta"]["year"]
    week = charts["meta"]["week"]
    key = f"{year}-{week:02d}"

    # Charger le cache rétro
    if os.path.exists(CACHE_RETRO):
        with open(CACHE_RETRO, "r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}

    # Vérifier si déjà présent
    if key in cache and not args.force:
        print(f"⏭️  Semaine {key} déjà dans le rétro")
        return

    # Calculer la date du lundi de la semaine ISO
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    date_obj = start_of_week1 + timedelta(weeks=week - 1)

    # Construire l'entrée rétro
    entry = {
        "week": week,
        "year": year,
        "date": date_obj.strftime("%d/%m/%Y"),
        "entries": fr["chart"],
        "source": "snepmusique.com",
        "cached_at": datetime.now().strftime("%Y-%m-%d")
    }

    # Ajouter ou remplacer dans le cache
    action = "remplacée" if key in cache else "ajoutée"
    cache[key] = entry

    # Appliquer les overrides de titres
    fab.apply_track_overrides(cache)

    # Sauvegarder
    os.makedirs(os.path.dirname(CACHE_RETRO), exist_ok=True)
    with open(CACHE_RETRO, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"✅ Semaine {key} {action} dans le rétro ({len(fr['chart'])} entrées)")


if __name__ == "__main__":
    main()