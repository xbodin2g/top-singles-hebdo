# Top Singles Hebdo - Données Officielles

Application web de suivi des tops musicaux officiels avec collecte automatisée hebdomadaire.

## 🎯 Fonctionnalités

- ✅ Collecte automatique des tops officiels (UK, Allemagne, Suisse, US)
- ✅ Synthèse régionale (Europe, pays anglo-saxons, Amérique du Sud)
- ✅ Vue détaillée par pays
- ✅ Interface responsive avec thème clair/sombre
- ✅ Exécution hebdomadaire automatisée via GitHub Actions

## 📋 Sources officielles

Actuellement implémentées :
- 🇬🇧 Royaume-Uni : Official Charts Company
- 🇩🇪 Allemagne : Offizielle Deutsche Charts (GfK)
- 🇨🇭 Suisse : Swiss Hitparade
- 🇺🇸 États-Unis : Billboard Hot 100

## 🚀 Installation rapide

### Option 1 : GitHub Actions (recommandé)

1. Créez un dépôt GitHub avec ces fichiers
2. Activez GitHub Pages dans Settings > Pages
3. Le workflow s'exécutera automatiquement chaque samedi

### Option 2 : Exécution locale

```bash
# Installer les dépendances
pip install requests beautifulsoup4

# Exécuter le script de collecte
python fetch_charts.py

# Ouvrir l'application
open index.html