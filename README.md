# 🎵 Spotify & Album MP3 Downloader + Serveur Web (Docker / Portainer)

Application complète de recherche, d'écoute et de téléchargement d'albums et playlists musicales en **MP3 haute fidélité (320 kbps)** avec pochettes HD et métadonnées ID3v2 complètes.

Fonctionne soit en **serveur web auto-hébergé sous Docker / Portainer (Debian)** avec interface responsive pour PC et smartphone, soit en **application desktop / service local sous Windows**.

---

## ✨ Fonctionnalités

- **🔍 Recherche d'albums intégrée (Deezer & iTunes)** : 100% gratuit, aucun compte Spotify Premium ni clé API requis pour rechercher et télécharger un album complet en 1 clic.
- **🔗 Support des URLs Spotify** : Collez n'importe quel lien d'album, de playlist ou de titre Spotify.
- **⚡ Moteur d'acquisition haute fidélité** : Recherche intelligente par code **ISRC** et titre/artiste sur YouTube Music via `yt-dlp` et encodage MP3 jusqu'à **320 kbps** via `FFmpeg`.
- **🏷️ Tagging ID3v2.3 complet (`mutagen`)** :
  - Titre, artiste(s), nom de l'album, année, numéro de piste et pochette officielle HD injectée dans le fichier.
- **📁 Structure de dossiers personnalisable** :
  - Modèle par défaut : `{Artist}/{Album}/{TrackNumber} - {Title}.mp3`
  - Personnalisable avec variables : `{Playlist}`, `{Artist}`, `{Album}`, `{Year}`, `{TrackNumber}`, `{Title}`, `{ISRC}`.
- **🌐 Serveur Web Responsive (FastAPI + SSE)** :
  - Interface tactile moderne et fluide pour PC, tablette et smartphone.
  - Suivi des téléchargements en temps réel via Server-Sent Events (SSE).
- **📻 Lecteur Audio Streaming Intégré** :
  - Écoute directe des morceaux présents sur le serveur sans avoir à les télécharger sur votre smartphone.
  - Support du saut temporel (HTTP Range 206) et enchaînement automatique des morceaux.
- **🐳 Prêt pour Docker & Portainer (Debian / Linux)** :
  - Image légère basée sur `python:3.11-slim` avec FFmpeg préinstallé.
  - Volumes persistants pour la configuration (`/config`) et le stockage de vos fichiers musicaux (`/music`).

---

## 🐳 Déploiement Docker & Portainer (Debian)

### Fichier `docker-compose.yml`

```yaml
version: "3.8"

services:
  spotify-downloader:
    image: spotify-downloader:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: spotify-downloader
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Europe/Paris
      - CONFIG_DIR=/config
      - DOWNLOAD_DIR=/music
    volumes:
      # Configuration persistante (settings.json)
      - ./config:/config
      # Dossier hôte Debian où sont stockés vos MP3
      # Remplacez /srv/musique par le chemin de votre disque ou dossier de stockage
      - /srv/musique:/music
```

### Déploiement via Portainer (Stacks)

1. Dans Portainer, allez dans **Stacks** -> **Add stack**.
2. Nommez la stack `spotify-downloader`.
3. Vous pouvez soit :
   - Choisir **Repository** et indiquer l'URL Git : `https://github.com/barksai/spotify-downloader.git`
   - Ou choisir **Web editor**, coller le `docker-compose.yml` ci-dessus (après avoir construit l'image avec `docker build -t spotify-downloader:latest .`).
4. Cliquez sur **Deploy the stack**.
5. Accédez à l'interface depuis votre navigateur : `http://<IP_SERVEUR>:8000`.

Pour plus de détails, consultez le guide complet : [DOCKER_PORTAINER.md](DOCKER_PORTAINER.md).

---

## 💻 Utilisation sous Windows (Local)

1. Double-cliquez sur `lancer_serveur_web.bat` pour démarrer le serveur.
2. Ouvrez votre navigateur sur `http://localhost:8000`.
3. (Optionnel) Pour lancer le serveur automatiquement au démarrage de Windows, exécutez `installer_demarrage_windows.bat`.

---

## 🛠️ Stack Technique

- **Backend** : Python 3.10+, FastAPI, Uvicorn, yt-dlp, Mutagen, Requests.
- **Frontend** : HTML5, CSS3 responsive (mobile-first), JavaScript Vanilla, Server-Sent Events (SSE).
- **Traitement Audio** : FFmpeg.
- **Conteneurisation** : Docker, Docker Compose, Portainer.
