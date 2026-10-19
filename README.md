# 🎵 Spotify & Album MP3 Downloader + Serveur Web (Docker / Portainer)

Application complète de recherche, d'écoute et de téléchargement d'albums et playlists musicales en **MP3** (jusqu'à 320 kbps) avec pochettes HD et métadonnées ID3v2 complètes, pensée pour alimenter une bibliothèque **Jellyfin / Plex / Navidrome**.

Fonctionne soit en **serveur web auto-hébergé sous Docker / Portainer (Debian)** avec interface responsive pour PC et smartphone, soit en **application desktop / service local sous Windows**.

---

## ✨ Fonctionnalités

- **🔍 Recherche d'albums intégrée (Deezer & iTunes)** : 100% gratuit, aucun compte Spotify Premium ni clé API requis pour rechercher et télécharger un album complet en 1 clic.
- **🔗 Support des URLs Spotify** : Collez n'importe quel lien d'album, de playlist ou de titre Spotify.
- **⚡ Moteur d'acquisition** : Recherche par code **ISRC** puis par titre/artiste sur YouTube via `yt-dlp` (avec contrôle de la durée pour écarter remix et lives), puis encodage MP3 via `FFmpeg`.
- **🏷️ Tagging ID3v2.3 complet (`mutagen`)** : titre, artiste(s), artiste de l'album (TPE2), album, année/date, piste/disque, genre, ISRC, pochette HD intégrée + `cover.jpg` / `folder.jpg`.
- **📁 Structure de dossiers personnalisable** :
  - Modèle par défaut : `{Artist}/{Album}/{TrackNumber} - {Title}.mp3`
  - Variables : `{Playlist}`, `{Artist}`, `{AlbumArtist}`, `{Album}`, `{Year}`, `{TrackNumber}`, `{DiscNumber}`, `{Title}`, `{ISRC}`.
- **🌐 Serveur Web Responsive (FastAPI + SSE)** : interface tactile pour PC, tablette et smartphone, suivi des téléchargements en temps réel.
- **🔒 Accès protégé par mot de passe** (`APP_PASSWORD`).
- **📻 Lecteur audio streaming intégré** avec saut temporel (HTTP Range) et enchaînement automatique.
- **💾 File d'attente persistante** : les téléchargements en attente reprennent après un redémarrage du conteneur.

> **ℹ️ À propos de la qualité audio** : YouTube diffuse un flux déjà compressé (Opus ~160 kbps ou AAC ~128 kbps).
> L'encodage en MP3 320 kbps évite d'ajouter des pertes supplémentaires, mais **ne restitue pas une qualité supérieure à celle de la source**.

---

## 🐳 Déploiement Docker & Portainer (Debian)

### Fichier `docker-compose.yml`

```yaml
services:
  spotify-downloader:
    image: spotify-downloader:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: spotify-downloader
    restart: unless-stopped
    ports:
      - "9000:8000"
    environment:
      - TZ=Europe/Paris
      - CONFIG_DIR=/config
      - DOWNLOAD_DIR=/music
      - APP_PASSWORD=${APP_PASSWORD:-}   # mot de passe de l'interface (recommandé)
      - PUBLIC_PORT=9000                 # port affiché dans l'interface
    volumes:
      - ./config:/config                 # settings.json, cookies.txt, queue.json
      - /srv/musique:/music              # dossier hôte où sont stockés vos MP3
    sysctls:
      - net.ipv4.tcp_mtu_probing=1
```

Le fichier complet (avec le réglage MTU du réseau) est fourni à la racine du dépôt.

### Variables d'environnement

| Variable | Défaut | Rôle |
| :--- | :--- | :--- |
| `APP_PASSWORD` | *(vide)* | Mot de passe de l'interface Web. **Vide = aucune protection** (un avertissement est affiché). |
| `DOWNLOAD_DIR` | `/music` | Dossier de téléchargement par défaut. |
| `MUSIC_ROOT` | `DOWNLOAD_DIR` | Racine autorisée : depuis l'interface, le dossier de téléchargement ne peut pas sortir de ce répertoire. |
| `CONFIG_DIR` | `/config` | Emplacement de `settings.json`, `cookies.txt` et `queue.json`. |
| `PORT` | `8000` | Port d'écoute dans le conteneur. |
| `PUBLIC_PORT` | `PORT` | Port affiché dans l'interface (ex. `9000` avec le mapping `9000:8000`). |
| `PUBLIC_HOST` | *(auto)* | Adresse(s) IP/nom affichées dans l'interface, séparées par des virgules (en Docker, l'IP détectée est celle du conteneur). |
| `QUEUE_PERSISTENCE` | `1` | `0` pour désactiver la reprise de la file d'attente au démarrage. |

### Déploiement via Portainer (Stacks)

1. Dans Portainer, allez dans **Stacks** -> **Add stack**.
2. Nommez la stack `spotify-downloader`.
3. Vous pouvez soit :
   - Choisir **Repository** et indiquer l'URL Git : `https://github.com/barksai/spotify-downloader.git`
   - Ou choisir **Web editor**, coller le `docker-compose.yml` ci-dessus (après avoir construit l'image avec `docker build -t spotify-downloader:latest .`).
4. Dans **Environment variables**, ajoutez `APP_PASSWORD` avec le mot de passe de votre choix.
5. Cliquez sur **Deploy the stack**.
6. Accédez à l'interface depuis votre navigateur : `http://<IP_SERVEUR>:9000`.

Pour plus de détails, consultez le guide complet : [DOCKER_PORTAINER.md](DOCKER_PORTAINER.md).

---

## 🔒 Sécurité

- Définissez **toujours** `APP_PASSWORD` : sans lui, toute personne ayant accès au réseau peut piloter le serveur et téléverser un `cookies.txt`.
- La session est conservée 30 jours dans un cookie `HttpOnly` / `SameSite=Strict`. Les scripts peuvent utiliser l'en-tête `Authorization: Bearer <APP_PASSWORD>`.
- Les requêtes de modification provenant d'un autre site sont refusées (protection CSRF).
- Le lecteur ne diffuse que des fichiers `.mp3` situés dans le dossier de téléchargement.
- N'exposez pas le port directement sur Internet : passez par un reverse proxy HTTPS (Caddy, Traefik, Nginx Proxy Manager) ou un VPN (WireGuard, Tailscale).

---

## 💻 Utilisation sous Windows (Local)

1. Double-cliquez sur `lancer_serveur_web.bat` pour démarrer le serveur (les dépendances de `requirements.txt` sont installées au premier lancement).
2. Ouvrez votre navigateur sur `http://localhost:8000`.
3. (Optionnel) Pour lancer le serveur automatiquement au démarrage de Windows, exécutez `installer_demarrage_windows.bat`.

L'application desktop CustomTkinter (`lancer_app.bat`) nécessite `pip install -r requirements-desktop.txt`.

---

## 🧪 Développement

```bash
pip install -r requirements-dev.txt
ruff check .
pytest spotify_mp3_downloader/tests
```

Les tests n'effectuent aucun appel réseau (Deezer, iTunes et YouTube sont simulés). La CI GitHub Actions exécute le lint, les tests et la construction de l'image Docker. `yt-dlp` est figé dans `requirements.txt` et mis à jour automatiquement via Dependabot.

---

## ⚖️ Avertissement

Ce projet est destiné à un usage personnel. Le téléchargement de contenus depuis YouTube peut être contraire à ses conditions d'utilisation et au droit d'auteur applicable dans votre pays : vous êtes seul responsable de l'usage que vous en faites.

---

## 🛠️ Stack Technique

- **Backend** : Python 3.11+, FastAPI, Pydantic, Uvicorn, yt-dlp, Mutagen, Requests.
- **Frontend** : HTML5, CSS3 responsive (mobile-first), JavaScript Vanilla, Server-Sent Events (SSE).
- **Traitement Audio** : FFmpeg.
- **Conteneurisation** : Docker, Docker Compose, Portainer.
