# ==============================================================================
# Dockerfile - Spotify & Album MP3 Downloader Web Server
# Base: Python 3.11 Slim (Debian) + FFmpeg
# ==============================================================================
FROM python:3.11-slim

# Copier le binaire Deno officiel (moteur JavaScript recommandé par yt-dlp pour résoudre les défis YouTube EJS)
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

# Empêcher Python de générer des fichiers .pyc et forcer l'affichage immédiat des logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONFIG_DIR=/config \
    DOWNLOAD_DIR=/music

# Installer FFmpeg et curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier les fichiers du projet
COPY run_server.py .
COPY spotify_mp3_downloader/ ./spotify_mp3_downloader/

# Créer les répertoires de volumes persistants
RUN mkdir -p /config /music

# Exposer le port du serveur web
EXPOSE 8000

# Vérification de santé du conteneur (Healthcheck)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/settings || exit 1

# Démarrage de l'application
CMD ["python", "run_server.py"]
