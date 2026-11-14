#!/usr/bin/env python3
"""
Diagnostique pourquoi une position est ignorée par le parser.
Affiche les lignes brutes autour de la position, sur toutes les pages.
Lecture seule.

Usage :
  python debug_position.py --key 1995-24 --position 41
  python debug_position.py --key 1994-07 --position 47
"""
import re, argparse, requests
from bs4 import BeautifulSoup
import fetch_archive_batch as fab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="ex: 1995-24")
    ap.add_argument("--position", type=int, required=True)
    ap.add_argument("--context", type=int, default=14)
    ap.add_argument("--max-pages", type=int, default=4)
    args = ap.parse_args()

    m = re.match(r"^(\d{4})-(\d{1,2})$", args.key.strip())
    if not m:
        print("❌ clé invalide, format attendu AAAA-SS")
        return
    year, week = int(m.group(1)), int(m.group(2))
    yy, nn = str(year)[2:], f"{week:02d}"
    target = args.position

    print(f"🔬 Diagnostic {year} S{week:02d} — position #{target}")
    print("=" * 74)

    found_any = False

    for page in range(1, args.max_pages + 1):
        url = f"https://www.chartsinfrance.net/charts/{yy}{nn}/singles.php"
        if page > 1:
            url += f"?page={page}"
        try:
            r = requests.get(url, headers=fab.HEADERS, timeout=30)
        except Exception as e:
            print(f"page {page} : ❌ {e}")
            continue
        if r.status_code != 200:
            print(f"page {page} : HTTP {r.status_code}")
            continue
        if "Aucun classement disponible" in r.text:
            print(f"page {page} : aucune donnée")
            continue

        lines = [l.strip() for l in
                 BeautifulSoup(r.text, "html.parser").get_text(separator="\n", strip=True).split("\n")
                 if l.strip()]

        # toutes les lignes qui pourraient être la position cherchée
        hits = []
        for i, l in enumerate(lines):
            mm = re.match(r"^(?:_star_\s*|star\s*)?(\d{1,3})$", l)
            if mm and int(mm.group(1)) == target:
                hits.append(i)
            elif l == str(target):
                hits.append(i)

        parsed = fab.parse_chartsinfrance_html(r.text)
        got = [e for e in parsed if e.get("position") == target]

        print(f"\n--- page {page} : {len(lines)} lignes, {len(parsed)} entrées parsées ---")
        if got:
            for e in got:
                tr = e.get("track") or {}
                print(f"  ✅ le parser a produit #{target} : {tr.get('artist')} — {tr.get('title')}")
        else:
            print(f"  ⚪ le parser n'a RIEN produit pour #{target} sur cette page")

        if not hits:
            print(f"  (aucune ligne ne ressemble à la position {target})")
            continue

        found_any = True
        for i in hits:
            lo, hi = max(0, i - 3), min(len(lines), i + args.context)
            print(f"\n  contexte autour de la ligne {i} :")
            for j in range(lo, hi):
                mark = ">>>" if j == i else "   "
                print(f"  {mark} [{j:5d}] {lines[j][:90]}")

        # ce que le parser a produit juste avant/après, pour repérer un décalage
        near = [e for e in parsed if abs(e.get("position", 0) - target) <= 2]
        if near:
            print("\n  entrées parsées voisines :")
            for e in sorted(near, key=lambda x: x["position"]):
                tr = e.get("track") or {}
                print(f"    #{e['position']:3d}  {tr.get('artist')} — {tr.get('title')}")

    print("\n" + "=" * 74)
    if not found_any:
        print(f"Aucune ligne correspondant à #{target} trouvée sur les {args.max_pages} pages.")
        print("La position n'est peut-être pas publiée par la source pour cette semaine.")
    print("Ce script n'a rien modifié.")


if __name__ == "__main__":
    main()