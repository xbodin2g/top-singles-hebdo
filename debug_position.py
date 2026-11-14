#!/usr/bin/env python3
"""
Diagnostique pourquoi une position est ignorée. Lecture seule.
Sources : chartsinfrance.net, snepmusique.com.

Pour SNEP, affiche l'index de "La Semaine Dernière" dans le bloc :
c'est le critère de validation structurelle (attendu 4 ou 5).
"""
import re, argparse, requests
from bs4 import BeautifulSoup
import fetch_archive_batch as fab

LSD = "La Semaine Dernière"
SDT = "Semaine dans le Top"


def build_urls(key, source):
    m = re.match(r"^(\d{4})-(\d{1,2})$", key)
    year, week = int(m.group(1)), int(m.group(2))
    s = (source or "").lower()
    if "snep" in s:
        return [f"https://snepmusique.com/classement-radio/?annee={year}&semaine={week}"], "snep"
    if "chartsinfrance" in s:
        yy, nn = str(year)[2:], f"{week:02d}"
        base = f"https://www.chartsinfrance.net/charts/{yy}{nn}/singles.php"
        return [base] + [f"{base}?page={p}" for p in range(2, 5)], "chartsinfrance"
    return [], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--position", type=int, required=True)
    ap.add_argument("--context", type=int, default=14)
    args = ap.parse_args()

    m = re.match(r"^(\d{4})-(\d{1,2})$", args.key.strip())
    if not m:
        print("❌ format attendu AAAA-SS")
        return
    key = f"{int(m.group(1))}-{int(m.group(2)):02d}"
    target = args.position

    cache = fab.load_retro_cache()
    source = (cache.get(key) or {}).get("source", "chartsinfrance.net")
    urls, kind = build_urls(key, source)
    if not urls:
        print(f"❌ source non supportée : {source}")
        return

    print(f"🔬 {key} — position #{target}  (source : {source})")
    print("=" * 74)

    found = False
    for url in urls:
        try:
            r = requests.get(url, headers=fab.HEADERS, timeout=30)
        except Exception as e:
            print(f"\n{url}\n  ❌ {e}")
            continue
        if r.status_code != 200:
            print(f"\n{url}\n  HTTP {r.status_code}")
            continue
        if "Aucun classement" in r.text:
            print(f"\n{url}\n  aucune donnée")
            continue

        lines = [l.strip() for l in
                 BeautifulSoup(r.text, "html.parser").get_text(separator="\n", strip=True).split("\n")
                 if l.strip()]

        parsed = (fab.parse_snep_html(r.text) if kind == "snep"
                  else fab.parse_chartsinfrance_html(r.text))
        got = [e for e in parsed if e.get("position") == target]

        print(f"\n--- {url}")
        print(f"    {len(lines)} lignes, {len(parsed)} entrées parsées")
        if got:
            for e in got:
                tr = e.get("track") or {}
                print(f"  ✅ parsé #{target} : {tr.get('artist')} — {tr.get('title')}")
        else:
            print(f"  ⚪ rien de parsé pour #{target}")

        hits = []
        for i, l in enumerate(lines):
            mm = re.match(r"^(?:_star_\s*|star\s*)?(\d{1,3})$", l)
            if mm and int(mm.group(1)) == target:
                hits.append(i)

        if not hits:
            print(f"  (aucune ligne ne ressemble à la position {target})")
            continue

        found = True
        for i in hits:
            lo, hi = max(0, i - 3), min(len(lines), i + args.context)
            print(f"\n  contexte autour de la ligne {i} :")
            for j in range(lo, hi):
                mark = ">>>" if j == i else "   "
                print(f"  {mark} [{j:5d}] {lines[j][:90]}")

            block = lines[i + 1:min(i + 14, len(lines))]
            if i + 2 < len(lines):
                t, a = lines[i + 1], lines[i + 2]
                print(f"\n  filtres sur title={t!r} / artist={a!r} :")
                print(f"    is_phantom   : {fab.is_phantom(t, a)}")
                print(f"    is_ui_title  : {fab.is_ui_title(t)}")
                print(f"    longueur ok  : {len(t) >= 1 and len(a) >= 1}")

            if kind == "snep":
                lsd = next((k for k in range(2, min(7, len(block))) if block[k] == LSD), None)
                sdt = None
                if lsd is not None:
                    sdt = next((k for k in range(lsd + 1, min(lsd + 5, len(block))) if block[k] == SDT), None)
                print(f"\n  validation structurelle SNEP :")
                print(f"    longueur du bloc : {len(block)}  (minimum 6)")
                print(f"    index de '{LSD}' : {lsd}   → attendu 4 ou 5")
                print(f"    index de '{SDT}' : {sdt}")
                print(f"    verdict : {'ACCEPTÉ' if lsd in (4, 5) else 'REJETÉ (ancrage)'}")
                print(f"    bloc[0..8] : {block[:9]}")

        near = [e for e in parsed if abs(e.get("position", 0) - target) <= 2]
        if near:
            print("\n  entrées voisines :")
            for e in sorted(near, key=lambda x: x["position"]):
                tr = e.get("track") or {}
                print(f"    #{e['position']:3d}  {tr.get('artist')} — {tr.get('title')}")

    print("\n" + "=" * 74)
    if not found:
        print(f"Aucune ligne #{target} trouvée. Position peut-être non publiée.")
    print("Ce script n'a rien modifié.")


if __name__ == "__main__":
    main()