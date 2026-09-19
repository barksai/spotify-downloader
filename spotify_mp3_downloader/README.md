# 🎧 Spotify MP3 Downloader (Windows)

Application desktop moderne et performante pour **Windows** permettant d'exporter vos playlists, albums et titres **Spotify** au format **MP3 haute fidélité (320 kbps)** avec pochettes HD intégrées et métadonnées ID3v2 complètes, rangés automatiquement dans une **arborescence de dossiers Windows personnalisable**.

---

## ✨ Fonctionnalités Principales

- **Authentification Spotify OAuth 2.0 (PKCE Flow)** : Connexion en 1 clic via le navigateur avec serveur de redirection local transparent (`127.0.0.1:8888/callback`). Aucun secret requis.
- **Support des URLs directes** : Collez n'importe quel lien Spotify (Playlist, Album, Titre individuel, Titres Likés).
- **Moteur d'acquisition Audio Haute Fidélité** : Recherche intelligente par code **ISRC** et titre/artiste sur YouTube Music via `yt-dlp` et encodage MP3 jusqu'à **320 kbps CBR / V0 VBR** avec `FFmpeg`.
- **Tagging ID3v2.3 Complet (`mutagen`)** :
  - Titre, Artistes principaux et collaborateurs (`TPE1`, `TPE2`)
  - Nom de l'album (`TALB`), Année/Date de sortie (`TDRC`, `TYER`)
  - Numéro de piste et de disque (`TRCK`, `TPOS`)
  - Code officiel ISRC (`TSRC`)
  - Pochette officielle haute résolution (640x640) injectée directement dans le fichier (`APIC`).
- **Moteur de Templates & Organisation Windows (`file_manager.py`)** :
  - Variables disponibles : `{Playlist}`, `{Artist}`, `{AlbumArtist}`, `{Album}`, `{Year}`, `{TrackNumber}`, `{Title}`, `{DiscNumber}`, `{ISRC}`.
  - Assainissement strict des caractères interdits sous Windows (`\ / : * ? " < > | \0`), gestion des points/espaces finaux et des noms réservés (`CON`, `PRN`, `AUX`, `NUL`, etc.).
  - Prévisualisation en direct (Live Preview) dans l'interface.
- **Gestionnaire de File d'Attente Multithread** : Téléchargements parallèles (1 à 6 threads), suivi de progression individuel et global, logs en direct, réessai automatique des échecs.
- **Interface Graphique Moderne (CustomTkinter)** : Thème sombre natif Windows, fluide, ergonomique et responsive.

---

## 📁 Architecture du Projet

```
spotify_mp3_downloader/
│
├── config.py                 # Gestion des réglages & persistance JSON (%APPDATA%)
├── spotify_client.py         # Client Spotify Web API (OAuth PKCE & extraction métadonnées)
├── file_manager.py           # Moteur de templates de dossiers & assainissement Windows
├── downloader.py             # Recherche YouTube/ISRC, extraction FFmpeg 320k, tags Mutagen
├── queue_manager.py          # File d'attente asynchrone multithreadée et statistiques
│
├── ui/                       # Interface Graphique (CustomTkinter)
│   ├── app.py                # Fenêtre principale et navigation par onglets
│   ├── components/
│   │   ├── playlist_card.py  # Carte visuelle de playlist avec cover
│   │   └── track_row.py      # Ligne de suivi de piste avec progression en direct
│   └── tabs/
│       ├── playlists_tab.py  # Onglet 1: Explorateur de playlists & saisie d'URLs
│       ├── queue_tab.py      # Onglet 2: File de téléchargement & console de logs
│       └── settings_tab.py   # Onglet 3: Paramètres, templates & qualité audio
│
├── tests/                    # Suite de tests unitaires (pytest)
│   ├── test_file_manager.py  # Tests des templates et assainissement Windows
│   ├── test_spotify.py       # Tests d'analyse des URLs et modèles
│   └── test_downloader.py    # Tests d'injection des tags ID3
│
├── main.py                   # Point d'entrée de l'application
├── build_exe.py              # Script de compilation autonome PyInstaller (.exe)
├── requirements.txt          # Dépendances Python
└── README.md                 # Documentation
```

---

## 🚀 Installation & Prérequis

### 1. Prérequis Système
- **Windows 10 / 11**
- **Python 3.10 ou supérieur**
- **FFmpeg** installé et accessible dans le PATH Windows.

#### Installer FFmpeg sous Windows en 1 commande :
Ouvrez un terminal PowerShell et exécutez :
```powershell
winget install Gyan.FFmpeg
```

### 2. Installation des dépendances Python
Dans le dossier du projet :
```powershell
pip install -r requirements.txt
```

---

## 💻 Utilisation

### Lancement de l'application
```powershell
python main.py
```

### Utilisation pas-à-pas :
1. **Connexion / Chargement** :
   - Cliquez sur **"Se connecter avec Spotify"** pour synchroniser automatiquement vos playlists et vos **Titres Likés**.
   - Ou collez directement un lien Spotify (ex: `https://open.spotify.com/playlist/...`) dans la barre de recherche.
2. **Sélection des morceaux** :
   - Cliquez sur **"Télécharger tout"** sur une playlist, ou sur **"Explorer"** pour cocher/décocher des morceaux spécifiques.
3. **Suivi des téléchargements** :
   - Rendez-vous sur l'onglet **"File de Téléchargement"** pour observer la progression en temps réel, mettre en pause ou ouvrir directement le dossier de sortie.
4. **Personnalisation** :
   - Rendez-vous sur l'onglet **"Paramètres"** pour modifier le dossier de destination, choisir votre structure de nommage avec prévisualisation en direct, et ajuster le débit MP3 (320 kbps par défaut).

---

## 📦 Compilation en Exécutable Autonome (.exe)

Pour générer un fichier `.exe` Windows autonome distribuable :

```powershell
python build_exe.py
```

L'exécutable compilé sera généré dans le dossier `dist/SpotifyMP3Downloader/`.

---

## 🧪 Exécution des Tests Unitaires

Pour valider l'intégrité de la suite de tests :
```powershell
pytest -v
```
