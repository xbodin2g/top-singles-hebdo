# En-têtes d'interface : comparaison EXACTE ou préfixe explicite.
# On ne cherche plus de sous-chaînes : "3 nuits par semaine" (Brett)
# est un vrai titre et était rejeté par l'ancien filtre.
UI_TITLE_EXACT = {
    'semaine', 'semaines', 'classement', 'charts',
    'top singles', 'top albums', 'top radio',
    'actualités', 'les tops', 'news', 'newsletter',
}
UI_TITLE_PATTERNS = (
    r'^semaine\s+(du|de|des|n|no|\d)',
    r'^classement\s+(du|de|des|n|no|\d)',
    r'^top\s+(singles|albums|radio)\s+(du|de|des|chart|\d)',
    r'^la\s+semaine\s+dern',
    r'^semaine\s+dans\s+le\s+top',
)


def is_ui_title(title):
    """True seulement si le champ est un en-tête, pas un titre contenant ces mots."""
    t = str(title or "").strip().lower()
    if not t:
        return False
    if t in UI_TITLE_EXACT:
        return True
    return any(re.search(p, t) for p in UI_TITLE_PATTERNS)