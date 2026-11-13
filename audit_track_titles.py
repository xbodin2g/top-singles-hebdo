#!/usr/bin/env python3
"""
Audit v2 des archives rétro — détection précise, sans faux positifs.

Signaux retenus :
  CRITIQUE  champ vide / artiste purement numérique
            / titre numérique VARIABLE selon les semaines  ← vrai bug
  ELEVE     bruit d'interface (tokens exacts) / titre == position
  INFO      titre numérique STABLE (ex. "22", "19") → probablement légitime

Supprimés volontairement : titre == artiste (éponymes), titre court (19, 7, 22).

Usage :
  python audit_track_titles.py
  python audit_track_titles.py --min-count 2 --limit 40
"""
import json, os, re, argparse, unicodedata
from collections import defaultdict, Counter
from datetime import datetime

CACHE_PATH = "data/cache/retro_archives.json"
SUGGEST_PATH = "data/track_overrides_suggestions.json"

# Tokens d'interface : comparés au champ ENTIER (pas en sous-chaîne)
UI_EXACT = {
    "n", "n°", "singles", "single", "star", "timeline", "chevron", "menu",
    "search", "close", "newsletter", "arrow right", "arrow top", "arrow bot",
    "arrow", "top singles", "classement", "voir les stats", "peak position",
    "total weeks", "la semaine derniere", "semaine dans le top", "current",
    "previous", "title", "peak", "weeks",
}
# Phrases longues non ambiguës : sous-chaîne autorisée
UI_PHRASES = ["voir les stats", "peak position", "total weeks",
              "la semaine derniere", "semaine dans le top",
              "copyright", "fonticons", "chevron_right", "chevron_bot"]


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_numeric(s):
    s = str(s or "").strip()
    if not s:
        return False
    return re.fullmatch(r"[\d\s\.\-–—#/°]+", s) is not None


def has_noise(s):
    n = norm(s)
    if not n:
        return False
    if n in UI_EXACT:
        return True
    return any(p in n for p in UI_PHRASES)


def is_clean(title, artist):
    t, a = str(title or "").strip(), str(artist or "").strip()
    if not t or not a:
        return False
    if is_numeric(t) or is_numeric(a):
        return False
    if has_noise(t) or has_noise(a):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--no-suggest", action="store_true")
    args = ap.parse_args()

    print(f"🔍 Audit v2 — {datetime.now():%Y-%m-%d %H:%M:%S}")

    if not os.path.exists(CACHE_PATH):
        print(f"❌ Cache absent : {CACHE_PATH}")
        return
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    # ---- Passe 1 : référence propre + titres numériques par artiste ----
    known_artists = set()
    title_ref = defaultdict(Counter)          # titre_norm -> Counter(artiste)
    numeric_by_artist = defaultdict(set)      # artiste_norm -> {titres numériques}
    total = 0

    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            t, a = tr.get("title", ""), tr.get("artist", "")
            total += 1
            if is_clean(t, a):
                known_artists.add(norm(a))
                title_ref[norm(t)][str(a).strip()] += 1
            if is_numeric(t) and str(a or "").strip():
                numeric_by_artist[norm(a)].add(str(t).strip())

    print(f"📚 {len(cache)} archives · {total} entrées")
    print(f"   référence : {len(known_artists)} artistes · {len(title_ref)} titres propres")

    # ---- Passe 2 : classification ----
    groups = {}
    sev_count = Counter()
    order = {"CRITIQUE": 3, "ELEVE": 2, "INFO": 1}

    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        m = re.match(r"^(\d{4})-(\d{1,2})$", str(key))
        try:
            year = int(m.group(1)) if m else int(arch.get("year"))
        except (TypeError, ValueError):
            year = None

        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            t, a = str(tr.get("title", "")), str(tr.get("artist", ""))
            pos = e.get("position")
            sig = []

            if not t.strip() or not a.strip():
                sig.append("champ_vide")
            if is_numeric(a):
                sig.append("artiste_numerique")

            variable = False
            if is_numeric(t):
                variants = numeric_by_artist.get(norm(a), set())
                if len(variants) >= 2:
                    sig.append("titre_numerique_VARIABLE")
                    variable = True
                else:
                    sig.append("titre_numerique_stable")

            if t.strip() and t.strip() == str(pos):
                sig.append("titre_egal_position")
            if has_noise(t) or has_noise(a):
                sig.append("bruit_interface")

            if not sig:
                continue

            if any(s in sig for s in ("champ_vide", "artiste_numerique", "titre_numerique_VARIABLE")):
                sev = "CRITIQUE"
            elif any(s in sig for s in ("bruit_interface", "titre_egal_position")):
                sev = "ELEVE"
            else:
                sev = "INFO"

            gk = (norm(a), norm(t) if not variable else "__numeric__")
            g = groups.get(gk)
            if g is None:
                g = {"count": 0, "weeks": [], "years": set(), "signals": set(),
                     "sev": sev, "title": t, "artist": a,
                     "num_titles": set(), "variable": variable}
                groups[gk] = g
            g["count"] += 1
            g["signals"].update(sig)
            if variable:
                g["variable"] = True
                g["num_titles"].add(t.strip())
            if len(g["weeks"]) < 10:
                g["weeks"].append(key)
            if year:
                g["years"].add(year)
            if order[sev] > order[g["sev"]]:
                g["sev"] = sev
            sev_count[sev] += 1

    if not groups:
        print("\n✅ Aucune entrée suspecte.")
        if not args.no_suggest:
            os.makedirs(os.path.dirname(SUGGEST_PATH), exist_ok=True)
            with open(SUGGEST_PATH, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        return

    ranked = sorted(groups.values(), key=lambda g: (-order[g["sev"]], -g["count"]))
    ranked = [g for g in ranked if g["count"] >= args.min_count]

    print(f"\n{'='*72}")
    print(f"SUSPECTS : {sum(sev_count.values())} entrées · {len(groups)} groupes")
    print(f"  CRITIQUE {sev_count['CRITIQUE']} · ELEVE {sev_count['ELEVE']} · INFO {sev_count['INFO']}")
    print("="*72)

    suggestions = []
    for g in ranked[:args.limit]:
        yrs = sorted(g["years"])
        print(f"\n[{g['sev']}] {g['count']}× — {', '.join(sorted(g['signals']))}")
        print(f"   artiste : {g['artist']!r}")
        if g["variable"]:
            nums = sorted(g["num_titles"], key=lambda x: (len(x), x))
            print(f"   titres  : {', '.join(nums[:14])}{' …' if len(nums) > 14 else ''}  ← VARIABLE = bug")
        else:
            print(f"   titre   : {g['title']!r}")
        print(f"   années  : {yrs}")
        print(f"   semaines: {', '.join(g['weeks'][:8])}{' …' if g['count'] > 8 else ''}")

        if g["sev"] != "CRITIQUE":
            continue

        field = g["artist"].strip()
        if not field or is_numeric(field):
            print("   ⚠️ champ artiste inexploitable → règle manuelle nécessaire")
            continue

        nf = norm(field)
        if nf in known_artists:
            # le champ artiste est un VRAI artiste → titre à retrouver
            print(f"   → artiste reconnu : {field} (titre à renseigner)")
            suggestions.append({
                "artist_match": field,
                "new_artist": field,
                "new_title": "A_RENSEIGNER",
                "years": yrs,
                "only_if_numeric_title": True,
                "comment": f"Titre numérique variable ({g['count']}×) — artiste OK, titre à retrouver"
            })
        elif nf in title_ref:
            # le champ artiste contient en fait le TITRE → inversion
            real_artist = title_ref[nf].most_common(1)[0][0]
            print(f"   💡 inversion détectée → {real_artist} — {field}")
            suggestions.append({
                "artist_match": field,
                "new_artist": real_artist,
                "new_title": field,
                "years": yrs,
                "only_if_numeric_title": True,
                "comment": f"Champs inversés ({g['count']}×) — artiste déduit par recoupement"
            })
        else:
            print("   ⚠️ champ non reconnu → à vérifier manuellement")
            suggestions.append({
                "artist_match": field,
                "new_artist": "A_RENSEIGNER",
                "new_title": "A_RENSEIGNER",
                "years": yrs,
                "only_if_numeric_title": True,
                "comment": f"Titre numérique variable ({g['count']}×) — champs à identifier"
            })

    if len(ranked) > args.limit:
        print(f"\n… {len(ranked)-args.limit} autre(s) groupe(s). Augmente --limit.")

    # ---- Écriture : TOUOURS créer le fichier (même vide) ----
    if not args.no_suggest:
        seen, uniq = set(), []
        for s in suggestions:
            k = (norm(s["artist_match"]), norm(s["new_title"]), norm(s["new_artist"]))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(s)
        os.makedirs(os.path.dirname(SUGGEST_PATH), exist_ok=True)
        with open(SUGGEST_PATH, "w", encoding="utf-8") as f:
            json.dump(uniq, f, ensure_ascii=False, indent=2)
        print(f"\n💾 {len(uniq)} suggestion(s) → {SUGGEST_PATH}")
        todo = sum(1 for s in uniq if "A_RENSEIGNER" in s["new_artist"] + s["new_title"])
        if todo:
            print(f"   ✏️ {todo} à compléter manuellement")
        print("   ⚠️ Relire avant de recopier dans data/track_overrides.json")

    print(f"\n{'='*72}")
    print("INFO = titres numériques stables, probablement légitimes (19, 22, 7…)")
    print("Seuls les CRITIQUE génèrent des suggestions.")


if __name__ == "__main__":
    main()