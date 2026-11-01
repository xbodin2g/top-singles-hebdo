# Top Singles Hebdo - Données Officielles

Application web de suivi des tops musicaux officiels avec collecte automatisée hebdomadaire.

**🌐 Site hébergé** : https://xbodin2g.github.io/top-singles-hebdo/

## 🎯 Fonctionnalités

- ✅ Collecte automatique des tops officiels (UK, Allemagne, Suisse, US, France, Brésil)
- ✅ Synthèse régionale (Europe, pays anglo-saxons, Amérique du Sud)
- ✅ Vue détaillée par pays
- ✅ Interface responsive avec thème clair/sombre
- ✅ Exécution hebdomadaire automatisée via GitHub Actions

## 📋 Sources officielles

Actuellement implémentées :
- 🇫🇷 France : SNEP (Syndicat National de l'Édition Phonographique)
- 🇬🇧 Royaume-Uni : Official Charts Company
- 🇩🇪 Allemagne : Offizielle Deutsche Charts (GfK)
- 🇨🇭 Suisse : Swiss Hitparade
- 🇺🇸 États-Unis : Billboard Hot 100
- 🇧🇷 Brésil : Pro-Música Brasil Top 50 Streaming

## 🚀 Installation rapide

### Option 1 : GitHub Actions (recommandé)

1. ✅ Créez un dépôt GitHub avec ces fichiers
2. ✅ Activez GitHub Pages dans Settings > Pages
3. ✅ Configurez les permissions : Settings > Actions > General > Workflow permissions > **Read and write permissions**
4. ✅ Le workflow s'exécutera automatiquement chaque samedi à midi (heure de Paris)
5. ✅ Vous pouvez aussi le déclencher manuellement depuis l'onglet Actions

### Option 2 : Exécution locale

```bash
# Installer les dépendances
pip install requests beautifulsoup4

# Exécuter le script de collecte
python fetch_charts.py

# Ouvrir l'application
open index.html  # macOS
# ou
xdg-open index.html  # Linux
# ou double-cliquer sur index.html  # Windows