# Guide de Déploiement Docker & Portainer (Debian)
## Spotify & Album MP3 Downloader

Ce guide vous explique étape par étape comment déployer l'application sur votre serveur **Debian** avec **Portainer**.

---

### 📦 Fichiers inclus pour Docker

- **`Dockerfile`** : Image basée sur Debian (`python:3.11-slim`) avec **FFmpeg** préinstallé pour l'encodage MP3 320 kbps et le tagging ID3.
- **`.dockerignore`** : Évite d'alourdir l'image avec les fichiers Windows (`.exe`, `.bat`, `.venv`, caches).
- **`requirements.txt`** : Dépendances Python allégées pour le serveur (sans GUI desktop).
- **`docker-compose.yml`** : Fichier de configuration prêt à l'emploi pour Portainer.

---

### 📂 Volumes et Chemins

L'image est conçue pour être totalement sans état (stateless) en dehors des deux volumes persistants :

| Volume Conteneur | Description | Exemple Hôte Debian |
| :--- | :--- | :--- |
| `/music` | Destination des musiques téléchargées | `/srv/musique` ou `/mnt/stockage/musique` |
| `/config` | Fichier `settings.json` persistant | `./config` ou `/opt/spotify-downloader/config` |

---

### 🚀 Méthode 1 : Déploiement via Portainer (Recommandé)

#### Étape 1 : Copier le projet sur votre serveur Debian

Copiez le dossier du projet sur votre serveur Debian (par exemple dans `/opt/spotify-downloader` ou dans votre dossier utilisateur `/home/votre-user/spotify-downloader`) :

```bash
# Exemple depuis votre PC Windows avec PowerShell ou SCP :
scp -r C:\chemin\vers\projet user@ip-serveur-debian:/opt/spotify-downloader
```

Les fichiers indispensables à copier sont :
- `run_server.py`
- `spotify_mp3_downloader/`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `requirements.txt`

#### Étape 2 : Préparer les dossiers et permissions sur Debian

Connectez-vous en SSH à votre serveur Debian et configurez le dossier de musique :

```bash
# Créer le dossier où seront stockés vos MP3 (si pas déjà fait)
sudo mkdir -p /srv/musique
sudo chmod -R 775 /srv/musique

# Aller dans le dossier du projet
cd /opt/spotify-downloader
```

#### Étape 3 : Construire l'image Docker

Exécutez cette commande sur votre serveur Debian :

```bash
docker build -t spotify-downloader:latest .
```
*(Le téléchargement de Debian slim, l'installation de FFmpeg et des modules Python se fait automatiquement en 1 à 2 minutes).*

#### Étape 4 : Déployer dans Portainer

1. Ouvrez votre interface **Portainer** (`https://ip-serveur:9443`).
2. Allez dans **Stacks** dans le menu de gauche.
3. Cliquez sur le bouton **+ Add stack**.
4. Donnez un nom à votre stack (ex: `spotify-downloader`).
5. Choisissez **Web editor** et collez le contenu ci-dessous :

```yaml
version: "3.8"

services:
  spotify-downloader:
    image: spotify-downloader:latest
    container_name: spotify-downloader
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Europe/Paris
      - CONFIG_DIR=/config
      - DOWNLOAD_DIR=/music
    volumes:
      - /opt/spotify-downloader/config:/config
      - /srv/musique:/music
```
*(Adaptez `/srv/musique` avec le chemin réel de votre disque de stockage sur Debian).*

6. Cliquez sur **Deploy the stack** en bas de la page.

---

### 🛠️ Méthode 2 : Création directe d'un conteneur dans Portainer (Sans Stack)

Si vous préférez utiliser l'assistant graphique de Portainer sans docker-compose :

1. Construisez d'abord l'image sur le serveur Debian : `docker build -t spotify-downloader:latest .`
2. Dans Portainer, cliquez sur **Containers** -> **+ Add container**.
3. Remplissez les champs :
   - **Name** : `spotify-downloader`
   - **Image** : `spotify-downloader:latest`
   - **Port mapping** : Host `8000` -> Container `8000`
4. Dans la section **Advanced container settings** en bas :
   - **Volumes** -> Cliquez sur **+ map additional volume** :
     - Container `/config` -> Bind `/opt/spotify-downloader/config` (Writable)
     - Container `/music` -> Bind `/srv/musique` (Writable)
   - **Env** -> Ajoutez :
     - `TZ` = `Europe/Paris`
     - `CONFIG_DIR` = `/config`
     - `DOWNLOAD_DIR` = `/music`
   - **Restart policy** : Sélectionnez `Unless stopped`.
5. Cliquez sur **Deploy the container**.

---

### 🌐 Accéder à l'application

Une fois le conteneur démarré :
- Ouvrez votre navigateur sur votre PC, smartphone ou tablette connecté au même réseau :
  ```
  http://<IP_DE_VOTRE_SERVEUR_DEBIAN>:8000
  ```
- **Configuration** : Dans l'onglet **Paramètres**, le dossier de téléchargement sera automatiquement configuré sur `/music` (qui pointe directement sur votre dossier hôte `/srv/musique`).
- **Lecteur Audio** : Tous les titres téléchargés seront immédiatement consultables et écoutables en streaming dans l'onglet **Serveur**.

---

### 🔄 Mettre à jour l'application à l'avenir

Lorsque vous modifiez du code :
1. Remplacez les fichiers sur votre serveur Debian.
2. Reconstruisez l'image :
   ```bash
   cd /opt/spotify-downloader
   docker build -t spotify-downloader:latest .
   ```
3. Dans Portainer -> **Containers** -> `spotify-downloader` -> Cliquez sur **Restart** (ou dans Stacks -> cliquez sur **Update the stack**).
