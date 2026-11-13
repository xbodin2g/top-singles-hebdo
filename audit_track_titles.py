#!/usr/bin/env python3
"""
Audit des archives rétro : détecte les entrées suspectes et propose des corrections.

Signaux détectés :
  - titre purement numérique        (bug de colonne)
  - titre == position               (inversion forte)
  - artiste purement numérique      (inversion)
  - champ vide / titre == artiste
  - bruit d'interface (star, timeline, N°…)
  - titre très court (<= 2 car.)    (faible : peut être légitime, ex. "19")

Astuce : si un titre est correct dans d'autres semaines, l'artiste réel est
déduit automatiquement par recoupement.

Usage :
  python audit_track_titles.py
  python audit_track_titles.py --min-count 2 --limit 40
"""
import json, os, re, argparse, unicodedata
from collections import defaultdict, Counter
from datetime import datetime

CACHE_PATH = "data/cache/retro_archives.json"
SUGGEST_PATH = "data/track_overrides_suggestions.json"

UI_NOISE = ["semaine", "timeline", "arrow", "star", "n°", "voir les stats",
            "chevron", "classement", "top singles", "peak position", "total weeks",
            "copyright", "fonticons", "newsletter", "menu", "search"]


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
    low = str(s or "").lower()
    return any(k in low for k in UI_NOISE)


def signals(title, artist, position):
    """Retourne (liste_signaux, sévérité)."""
    sig = []
    t = str(title or "").strip()
    a = str(artist or "").strip()

    if not t or not a:
        sig.append("champ_vide")
    if is_numeric(t):
        sig.append("titre_numerique")
    if is_numeric(a):
        sig.append("artiste_numerique")
    if t and t == str(position):
        sig.append("titre_egal_position")
    if t and a and norm(t) == norm(a):
        sig.append("titre_egal_artiste")
    if has_noise(t) or has_noise(a):
        sig.append("bruit_interface")
    if t and len(t) <= 2 and not is_numeric(t):
        sig.append("titre_tres_court")

    if any(s in sig for s in ("champ_vide", "titre_numerique", "artiste_numerique")):
        sev = "CRITIQUE"
    elif any(s in sig for s in ("titre_egal_position", "titre_egal_artiste", "bruit_interface")):
        sev = "ELEVE"
    elif "titre_tres_court" in sig:
        sev = "FAIBLE"
    else:
        sev = None
    return sig, sev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-count", type=int, default=1, help="occurrences minimum par groupe")
    ap.add_argument("--limit", type=int, default=60, help="groupes affichés")
    ap.add_argument("--no-suggest", action="store_true", help="ne pas écrire de suggestions")
    args = ap.parse_args()

    print(f"🔍 Audit des titres — {datetime.now():%Y-%m-%d %H:%M:%S}")

    if not os.path.exists(CACHE_PATH):
        print(f"❌ Cache absent : {CACHE_PATH}")
        return
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    # ---- Passe 1 : référence des titres propres ----
    ref = defaultdict(Counter)   # titre_norm -> Counter(artiste_display)
    total_entries = 0
    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            total_entries += 1
            t, a = tr.get("title", ""), tr.get("artist", "")
            _, sev = signals(t, a, e.get("position"))
            if sev is None:
                ref[norm(t)][str(a).strip()] += 1

    print(f"📚 {len(cache)} archives · {total_entries} entrées · {len(ref)} titres de référence")

    # ---- Passe 2 : regroupement des suspects ----
    groups = defaultdict(lambda: {"count": 0, "weeks": [], "years": set(),
                                  "signals": set(), "sev": None,
                                  "title": "", "artist": "", "positions": set()})
    sev_count = Counter()

    for key, arch in cache.items():
        if not isinstance(arch, dict):
            continue
        m = re.match(r"^(\d{4})-(\d{1,2})$", str(key))
        year = int(m.group(1)) if m else arch.get("year")
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None

        for e in arch.get("entries") or []:
            tr = e.get("track") or {}
            t, a = str(tr.get("title", "")), str(tr.get("artist", ""))
            sig, sev = signals(t, a, e.get("position"))
            if not sev:
                continue
            gk = (norm(a), norm(t))
            g = groups[gk]
            g["count"] += 1
            g["title"], g["artist"] = t, a
            g["signals"].update(sig)
            g["positions"].add(e.get("position"))
            if len(g["weeks"]) < 12:
                g["weeks"].append(key)
            if year:
                g["years"].add(year)
            order = {"CRITIQUE": 3, "ELEVE": 2, "FAIBLE": 1}
            if g["sev"] is None or order[sev] > order[g["sev"]]:
                g["sev"] = sev
            sev_count[sev] += 1

    if not groups:
        print("\n✅ Aucune entrée suspecte détectée.")
        return

    # ---- Rapport ----
    ranked = sorted(groups.values(),
                    key=lambda g: ({"CRITIQUE": 3, "ELEVE": 2, "FAIBLE": 1}[g["sev"]], -g["count"]))
    ranked = [g for g in ranked if g["count"] >= args.min_count]

    print(f"\n{'='*70}")
    print(f"SUSPECTS : {sum(sev_count.values())} entrées · {len(groups)} groupes")
    print(f"  CRITIQUE {sev_count['CRITIQUE']} · ELEVE {sev_count['ELEVE']} · FAIBLE {sev_count['FAIBLE']}")
    print("="*70)

    suggestions = []
    for g in ranked[:args.limit]:
        yrs = sorted(g["years"])
        print(f"\n[{g['sev']}] {g['count']}× — {', '.join(sorted(g['signals']))}")
        print(f"   artiste : {g['artist']!r}")
        print(f"   titre   : {g['title']!r}")
        print(f"   années  : {yrs}")
        print(f"   semaines: {', '.join(g['weeks'][:8])}{' …' if g['count'] > 8 else ''}")

        if g["sev"] == "FAIBLE":
            continue

        # Cas A : titre numérique, artiste = vrai titre (inversion)
        if is_numeric(g["title"]) and not is_numeric(g["artist"]) and g["artist"]:
            real_title = g["artist"].strip()
            cand = ref.get(norm(real_title))
            real_artist = cand.most_common(1)[0][0] if cand else ""
            if real_artist:
                print(f"   💡 déduit par recoupement → {real_artist} — {real_title}")
            else:
                print(f"   ⚠️ artiste à renseigner manuellement")
            suggestions.append({
                "artist_match": real_title,
                "new_artist": real_artist or "A_RENSEIGNER",
                "new_title": real_title,
                "years": yrs,
                "only_if_numeric_title": True,
                "comment": f"Auto-détecté (inversion, {g['count']} occurrences) — À VÉRIFIER"
            })

        # Cas B : artiste propre, titre numérique
        elif is_numeric(g["title"]) and not is_numeric(g["artist"]) is False and g["artist"]:
            suggestions.append({
                "artist_match": g["artist"].strip(),
                "new_artist": g["artist"].strip(),
                "new_title": "A_RENSEIGNER",
                "years": yrs,
                "only_if_numeric_title": True,
                "comment": f"Auto-détecté (titre numérique, {g['count']} occurrences) — À VÉRIFIER"
            })

    if len(ranked) > args.limit:
        print(f"\n… {len(ranked)-args.limit} autre(s) groupe(s). Augmente --limit.")

    # ---- Suggestions ----
    if suggestions and not args.no_suggest:
        # déduplique
        seen = set()
        uniq = []
        for s in suggestions:
            k = (norm(s["artist_match"]), norm(s["new_title"]))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(s)
        os.makedirs(os.path.dirname(SUGGEST_PATH), exist_ok=True)
        with open(SUGGEST_PATH, "w", encoding="utf-8") as f:
            json.dump(uniq, f, ensure_ascii=False, indent=2)
        print(f"\n💾 {len(uniq)} suggestion(s) écrite(s) : {SUGGEST_PATH}")
        print("   ⚠️ À relire avant de recopier dans data/track_overrides.json")
        todo = sum(1 for s in uniq if "A_RENSEIGNER" in (s["new_artist"] + s["new_title"]))
        if todo:
            print(f"   ✏️ {todo} suggestion(s) contiennent A_RENSEIGNER")

    print(f"\n{'='*70}")
    print("Prochaine étape : compléter track_overrides.json puis lancer Fix Track Titles.")


if __name__ == "__main__":
    main()