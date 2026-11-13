#!/usr/bin/env python3
"""
Audit v3 des archives rétro — détection précise, sans faux positifs.

CRITIQUE  champ vide
          artiste numérique SANS répertoire (fantôme)
          titre numérique VARIABLE selon les semaines   ← vrai bug
ELEVE     bruit d'interface (tokens non ambigus) / titre == position
INFO      titre numérique STABLE (19, 22, 1979…)  → légitime
          artiste numérique AVEC répertoire (113, 666, 702, 911, 112…) → légitime

Supprimés volontairement :
  titre == artiste   (chansons éponymes légitimes)
  titre court        (19, 7, 22 sont de vrais titres)
  tokens ambigus     ("singles", "star", "menu", "search"…)

Recoupement contraint par l'époque (±3 ans) pour éviter
"One" → Swedish House Mafia au lieu de U2.

Usage :
  python audit_track_titles.py
  python audit_track_titles.py --min-count 2 --limit 40
"""
import json, os, re, argparse, unicodedata
from collections import defaultdict, Counter
from datetime import datetime

CACHE_PATH = "data/cache/retro_archives.json"
SUGGEST_PATH = "data/track_overrides_suggestions.json"
OVERRIDES_PATH = "data/track_overrides.json"

ERA_WINDOW = 3   # années de tolérance pour le recoupement

# Tokens 100 % interface, sans ambiguïté possible
UI_EXACT = {
    "timeline", "voir les stats", "n", "n°",
    "arrow right", "arrow top", "arrow bot", "arrow",
    "chevron right", "chevron bot", "chevron left", "chevron",
}
UI_PHRASES = [
    "voir les stats", "peak position", "total weeks",
    "la semaine derniere", "semaine dans le top",
    "copyright", "fonticons", "chevron_",
]


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


def year_of(key, arch):
    m = re.match(r"^(\d{4})-", str(key))
    if m:
        return int(m.group(1))
    try:
        return int(arch.get("year"))
    except (TypeError, ValueError):
        return 0


def load_existing_matches():
    """Règles déjà en place : on ne re-suggère pas ce qui est déjà couvert."""
    out = set()
    if os.path.exists(OVERRIDES_PATH):
        try:
            with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
                for r in json.load(f):
                    am = (r.get("artist_match") or "").strip()
                    if am:
                        out.add(norm(am))
        except Exception:
            pass
    return out


def write_suggestions(items):
    os.makedirs(os.path.dirname(SUGGEST_PATH), exist_ok=True)
    with open(SUGGEST_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--no-suggest", action="store_true")
    args = ap.parse_args()

    print(f"🔍 Audit v3 — {datetime.now():%Y-%m-%d %H:%M:%S}")

    if not os.path.exists(CACHE_PATH):
        print(f"❌ Cache absent : {CACHE_PATH}")
        if not args.no_suggest:
            write_suggestions([])
        return

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    existing = load_existing_matches()

    # ---------- Passe 1 : références ----------
    known_artists = set()
    title_ref = defaultdict(Counter)        # titre_norm -> Counter((artiste, année))
    numeric_by_artist = defaultdict(set)    # artiste_norm -> {titres numériques}
    real_titles_by_artist = defaultdict(set)  # artiste_norm -> {titres NON numériques}
    total = 0

    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        yr = year_of(key, arch)
        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            t, a = tr.get("title", ""), tr.get("artist", "")
            total += 1
            na = norm(a)
            if is_clean(t, a):
                known_artists.add(na)
                title_ref[norm(t)][(str(a).strip(), yr)] += 1
            if str(a or "").strip() and str(t or "").strip() and not is_numeric(t):
                real_titles_by_artist[na].add(norm(t))
            if is_numeric(t) and str(a or "").strip():
                numeric_by_artist[na].add(str(t).strip())

    print(f"📚 {len(cache)} archives · {total} entrées")
    print(f"   référence : {len(known_artists)} artistes · {len(title_ref)} titres propres")
    if existing:
        print(f"   {len(existing)} règle(s) déjà en place dans track_overrides.json")

    # ---------- Passe 2 : classification ----------
    groups = {}
    sev_count = Counter()
    sig_count = Counter()
    order = {"CRITIQUE": 3, "ELEVE": 2, "INFO": 1}

    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        yr = year_of(key, arch)

        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            t, a = str(tr.get("title", "")), str(tr.get("artist", ""))
            pos = e.get("position")
            na = norm(a)
            sig = []

            if not t.strip() or not a.strip():
                sig.append("champ_vide")

            if is_numeric(a):
                if len(real_titles_by_artist.get(na, set())) >= 1:
                    sig.append("artiste_numerique_legitime")
                else:
                    sig.append("artiste_numerique")

            variable = False
            if is_numeric(t):
                variants = numeric_by_artist.get(na, set())
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

            gk = (na, "__numeric__" if variable else norm(t))
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
            if yr:
                g["years"].add(yr)
            if order[sev] > order[g["sev"]]:
                g["sev"] = sev

            sev_count[sev] += 1
            for s in sig:
                sig_count[s] += 1

    if not groups:
        print("\n✅ Aucune entrée suspecte.")
        if not args.no_suggest:
            write_suggestions([])
            print(f"💾 fichier vide écrit : {SUGGEST_PATH}")
        return

    ranked = sorted(groups.values(), key=lambda g: (-order[g["sev"]], -g["count"]))
    ranked = [g for g in ranked if g["count"] >= args.min_count]

    print(f"\n{'='*72}")
    print(f"SUSPECTS : {sum(sev_count.values())} entrées · {len(groups)} groupes")
    print(f"  CRITIQUE {sev_count['CRITIQUE']} · ELEVE {sev_count['ELEVE']} · INFO {sev_count['INFO']}")
    print("-"*72)
    for s, n in sig_count.most_common():
        print(f"  {s:32s} {n}")
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
        if nf in existing:
            print("   ✔ déjà couvert par une règle de track_overrides.json")
            continue

        if nf in known_artists:
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
            ref_year = min(yrs) if yrs else 0
            cands = Counter()
            for (cand_artist, cand_year), n in title_ref[nf].items():
                if ref_year and cand_year and abs(cand_year - ref_year) <= ERA_WINDOW:
                    cands[cand_artist] += n
            if not cands:
                print(f"   ⚠️ aucun artiste de la même époque (±{ERA_WINDOW} ans) → à vérifier")
                suggestions.append({
                    "artist_match": field,
                    "new_artist": "A_RENSEIGNER",
                    "new_title": field,
                    "years": yrs,
                    "only_if_numeric_title": True,
                    "comment": f"Inversion ({g['count']}×) — artiste non déductible à cette époque"
                })
            else:
                real_artist = cands.most_common(1)[0][0]
                print(f"   💡 inversion détectée → {real_artist} — {field}  (époque {ref_year})")
                suggestions.append({
                    "artist_match": field,
                    "new_artist": real_artist,
                    "new_title": field,
                    "years": yrs,
                    "only_if_numeric_title": True,
                    "comment": f"Champs inversés ({g['count']}×) — artiste déduit à ±{ERA_WINDOW} ans"
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

    # ---------- Écriture (toujours, même vide) ----------
    if not args.no_suggest:
        seen, uniq = set(), []
        for s in suggestions:
            k = (norm(s["artist_match"]), norm(s["new_title"]), norm(s["new_artist"]))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(s)
        write_suggestions(uniq)
        print(f"\n💾 {len(uniq)} suggestion(s) → {SUGGEST_PATH}")
        todo = sum(1 for s in uniq if "A_RENSEIGNER" in s["new_artist"] + s["new_title"])
        if todo:
            print(f"   ✏️ {todo} à compléter manuellement")
        print("   ⚠️ Relire avant de recopier dans data/track_overrides.json")

    print(f"\n{'='*72}")
    print("INFO = titres numériques stables (19, 22, 1979…) et groupes à nom numérique")
    print("       (113, 666, 702, 911, 112…) → légitimes, aucune action.")
    print("Seuls les CRITIQUE non déjà couverts génèrent des suggestions.")


if __name__ == "__main__":
    main()