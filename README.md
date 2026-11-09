# Top Singles Hebdo - Données Officielles
# 🎵 Top Singles — Classements musicaux & archives officielles

Application web de suivi des classements musicaux officiels avec archives historiques, fiches artistes et outils d'export de playlists.

**🌐 Site hébergé** : https://xbodin2g.github.io/top-singles-hebdo/

## ✨ Fonctionnalités

### 📊 Vue Hebdo
- Classements hebdomadaires de 8 sources officielles
- Synthèse par région (Europe, Anglo-saxons, Amérique du Sud, Asie)
- Détail par pays avec mouvements (▲ ▼ ✦ ●)
- Recherche par titre ou artiste
- Liens directs YouTube / Spotify / Deezer / Amazon

### 📼 Vue Rétro
- Archives du Top 50 français depuis 1984
- Navigation automatique par année et semaine
- Mouvements, semaines dans le top, pics
- Enrichissement streaming à la demande (YouTube + Deezer)
- Gestion du cache par plage d'années

### 🎤 Vue Artistes
- Fiches artistes générées automatiquement depuis les archives
- Statistiques : entrée, pic, durée, sortie
- Recherche par nom d'artiste ou titre classé
- Navigation croisée : top → artiste → semaine du top
- Export playlist artiste vers TuneMyMusic

### 🧰 Outils & Exports
- Export vers TuneMyMusic (Deezer, YouTube, Spotify…)
- Playlist YouTube directe
- Export CSV
- Copie dans le presse-papier
- Partage natif (Android/iOS)
- Inversion de l'ordre des titres

## 📡 Sources de données

### Classements hebdomadaires

| Pays | Source | Type |
|------|--------|------|
| 🇫🇷 France | SNEP (snepmusique.com) | Officiel |
| 🇺🇸 États-Unis | acharts.co | Agrégateur |
| 🇬🇧 Royaume-Uni | acharts.co | Agrégateur |
| 🇬🇧🎸 UK Indie | Official Charts Company | Officiel |
| 🇩🇪 Allemagne | kworb.net | iTunes |
| 🇨🇭 Suisse | acharts.co | Agrégateur |
| 🇧🇷 Brésil | Billboard Brasil + Pro-Música | Officiel |
| 🇸🇬 Singapour | iTunes RSS | Officiel |

### Archives rétro (France)

| Période | Source |
|---------|--------|
| 1984 → 1993 S35 | top-archives.fr |
| 1993 S36 → 2014 S15 | chartsinfrance.net |
| 2014 S16 → aujourd'hui | SNEP |

## 🏗️ Architecture

- index.html — Application web (V2.1.2)
- fetch_charts.py — Collecte hebdomadaire
- fetch_archive_batch.py — Collecte archives rétro
- build_artist_index.py — Génération index artiste
- data/charts-latest.json — Dernier top hebdo
- data/charts-YYYY-MM-DD.json — Tops datés
- data/cache/retro_archives.json — Toutes les archives rétro
- data/cache/streaming_ids.json — Cache IDs YouTube/Deezer
- data/cache/artist_index.json — Index artistes précalculé
- .github/workflows/fetch-charts.yml — Hebdo (samedi 18h UTC)
- .github/workflows/fetch-retro-archives.yml — Archives (manuel)
- .github/workflows/build-artist-index.yml — Index artiste (auto)

## ⚙️ Scripts Python

### fetch_charts.py
Collecte les tops hebdomadaires depuis les 8 sources, enrichit avec les IDs YouTube/Deezer (avec fallback yt-dlp), et génère charts-latest.json.

### fetch_archive_batch.py
Télécharge les archives du Top 50 français depuis 3 sources selon la période. Gère la pagination et les mouvements.

Exemple : python fetch_archive_batch.py --year 1995 --weeks 1-52

### build_artist_index.py
Analyse toutes les archives et génère un index artiste précalculé avec :
- Liste des titres par artiste
- Date d'entrée / sortie
- Meilleure place + date du pic
- Durée dans le top

## 🔄 Automatisation GitHub Actions

| Workflow | Déclenchement | Description |
|----------|--------------|-------------|
| Fetch Weekly Charts | Samedi 18h UTC + manuel | Collecte les tops hebdo |
| Fetch Retro Archives | Manuel | Télécharge une année d'archives |
| Build Artist Index | Auto (push archives) + mensuel | Régénère l'index artiste |

## 🚀 Installation locale (optionnel)

1. Cloner le dépôt
2. Installer les dépendances : pip install requests beautifulsoup4 yt-dlp cloudscraper
3. Lancer la collecte hebdo : python fetch_charts.py
4. Lancer la collecte archives : python fetch_archive_batch.py --year 2000
5. Générer l'index artiste : python build_artist_index.py
6. Servir localement : python -m http.server 8000

## 🔑 Variables d'environnement

| Variable | Description | Obligatoire |
|----------|-------------|-------------|
| YOUTUBE_API_KEY | Clé API YouTube Data v3 | Non (fallback yt-dlp) |

La clé API YouTube est à configurer dans les Secrets GitHub du dépôt.

## 🎨 Interface

### Thèmes
Clair / Sombre (persistant via localStorage)

### Navigation
- 📊 Hebdo : tops de la semaine
- 📼 Rétro : archives 1984-2026
- 🎤 Artistes : fiches et statistiques

### Tiroir d'outils (⚙️ en bas à droite)
- Exports (TuneMyMusic, YouTube, CSV, Copier, Partager)
- Inversion de l'ordre des playlists
- Configuration API YouTube
- Rechargement des données
- Gestion du cache streaming

## 📱 Compatibilité

- Desktop (Chrome, Firefox, Safari, Edge)
- Mobile Android (testé)
- Mobile iOS
- Responsive (3 breakpoints : 900px, 820px, 640px)

## 🗺️ Historique des versions

| Version | Description |
|---------|-------------|
| 2.1.2 | Correctif mouvements (nouvelles entrées multi-sources) |
| 2.1.1 | Tiroir d'outils, recherche artiste par titre, navigation top→artiste |
| 2.1 | Onglet Artistes avec fiches et index précalculé |
| 2.0 | Refonte ergonomique (onglets, rétro automatisé, panneaux repliables) |
| 1.0 | Playlist hebdo inversée + TuneMyMusic |
| 0.x | Développement initial (sources, cache, enrichissement) |

## 📄 Licence

Projet personnel. Les données de classement appartiennent à leurs sources respectives (SNEP, Official Charts Company, Billboard, etc.).

## 🙏 Remerciements

- SNEP — Classement officiel français
- Official Charts Company — Classements UK
- Billboard Brasil — Classement brésilien
- acharts.co — Agrégation multi-pays
- chartsinfrance.net — Archives françaises
- top-archives.fr — Archives 1984-1993