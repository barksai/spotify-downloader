"""
Spotify & Album MP3 Downloader - Web Application Server (FastAPI)
Serveur HTTP auto-hébergeable avec API REST, streaming temps réel (SSE) et lecteur audio streaming.
"""
import os
import sys
import json
import socket
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Query, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..config import (
    config, PRESET_TEMPLATES, ALLOWED_AUDIO_QUALITIES, ALLOWED_DUPLICATE_MODES,
    MAX_THREADS_LIMIT, get_music_root,
)
from ..spotify_client import spotify_manager, SpotifyTrack
from ..album_search import search_albums, fetch_album_tracks
from ..queue_manager import queue_manager, DownloadTask
from ..file_manager import preview_template
from . import auth

# Gestionnaire d'abonnés SSE (Server-Sent Events) pour la progression en direct
sse_subscribers: set[asyncio.Queue] = set()
event_loop: Optional[asyncio.AbstractEventLoop] = None

MAX_COOKIES_SIZE = 1024 * 1024  # 1 Mo
PUBLIC_PATHS = {"/login", "/api/login", "/api/health"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_local_ip_addresses() -> List[str]:
    """Détecte les adresses IP locales de la machine pour faciliter l'accès smartphone."""
    public_host = os.getenv("PUBLIC_HOST", "").strip()
    if public_host:
        return [h.strip() for h in public_host.split(",") if h.strip()]

    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append("127.0.0.1")
    return ips


def get_public_port() -> int:
    """Port visible depuis le réseau (PUBLIC_PORT, ex: 9000 avec le mapping Docker 9000:8000)."""
    for var in ("PUBLIC_PORT", "PORT"):
        value = os.getenv(var, "").strip()
        if value.isdigit():
            return int(value)
    return 8000


def resolve_download_dir() -> Path:
    return Path(os.path.expandvars(os.path.expanduser(config.get("download_dir")))).resolve()


def task_to_dict(task: DownloadTask) -> Dict[str, Any]:
    return {
        "id": task.id,
        "title": task.track.title,
        "artist": task.track.artist,
        "album": task.track.album,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "status_message": task.status_message,
        "progress": task.progress,
        "target_path": task.target_path,
        "error_message": task.error_message
    }


def track_to_dict(t: SpotifyTrack, fallback_album_artist: str) -> Dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "artist": t.artist,
        "artists": t.artists,
        "album": t.album,
        "album_artist": t.album_artist or fallback_album_artist,
        "year": t.year,
        "release_date": t.release_date,
        "genre": t.genre,
        "duration_str": t.duration_str,
        "duration_ms": t.duration_ms,
        "track_number": t.track_number,
        "track_number_padded": t.track_number_padded,
        "disc_number": t.disc_number,
        "disc_total": t.disc_total,
        "total_tracks": t.total_tracks,
        "isrc": t.isrc,
        "cover_url": t.cover_url
    }


def playlist_to_dict(playlist) -> Dict[str, Any]:
    return {
        "id": playlist.id,
        "name": playlist.name,
        "owner": playlist.owner,
        "total_tracks": playlist.total_tracks,
        "cover_url": playlist.cover_url,
        "tracks": [track_to_dict(t, playlist.owner) for t in playlist.tracks]
    }


def broadcast_event(data: Dict[str, Any]):
    """Diffuse un événement en temps réel à tous les clients Web connectés."""
    payload = json.dumps(data)
    for q in list(sse_subscribers):
        try:
            q.put_nowait(payload)
        except Exception:
            sse_subscribers.discard(q)


def _setup_queue_manager_events(loop: asyncio.AbstractEventLoop):
    def _on_task_update(task: DownloadTask):
        loop.call_soon_threadsafe(broadcast_event, {"type": "task_update", "task": task_to_dict(task)})

    def _on_stats_update(stats: Dict[str, Any]):
        loop.call_soon_threadsafe(broadcast_event, {"type": "stats", "stats": stats})

    def _on_log(msg: str, level: str):
        loop.call_soon_threadsafe(broadcast_event, {"type": "log", "message": msg, "level": level})

    queue_manager.on_task_updated = _on_task_update
    queue_manager.on_queue_stats = _on_stats_update
    queue_manager.on_log = _on_log


@asynccontextmanager
async def lifespan(app: FastAPI):
    global event_loop
    event_loop = asyncio.get_running_loop()
    _setup_queue_manager_events(event_loop)

    if not auth.auth_enabled():
        print("[Sécurité] APP_PASSWORD n'est pas défini : l'interface Web est accessible SANS mot de passe "
              "par toute personne du réseau. Définissez APP_PASSWORD pour la protéger.")

    # Reprise de la file d'attente sauvegardée avant le dernier arrêt
    if os.getenv("QUEUE_PERSISTENCE", "1") != "0":
        restored = queue_manager.load_persisted(config.app_dir / "queue.json")
        if restored:
            queue_manager.start()

    # Désactivation automatique du QuickEdit Mode sous Windows
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hStdin = kernel32.GetStdHandle(-10) # STD_INPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
                new_mode = (mode.value & ~0x0040) | 0x0080
                kernel32.SetConsoleMode(hStdin, new_mode)
        except Exception:
            pass

    yield


# Initialisation FastAPI
app = FastAPI(
    title="Spotify & Album MP3 Downloader",
    description="Application Web auto-hébergeable pour télécharger et écouter en streaming albums et playlists",
    version=__version__,
    lifespan=lifespan
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    1. Bloque les requêtes de modification provenant d'un autre site (protection CSRF).
    2. Exige une session valide lorsque APP_PASSWORD est défini.
    """
    path = request.url.path

    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host", ""):
            return JSONResponse({"detail": "Origine de la requête refusée."}, status_code=403)

    if path in PUBLIC_PATHS or path.startswith("/static/") or auth.is_authenticated(request):
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentification requise."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


BASE_DIR = Path(__file__).resolve().parent
templates_dir = BASE_DIR / "templates"
static_dir = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


# =========================================================================
# MODÈLES DE REQUÊTES (validation des entrées)
# =========================================================================

class TrackIn(BaseModel):
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    id: str
    title: str = "Titre inconnu"
    artist: str = "Artiste inconnu"
    artists: Optional[List[str]] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    year: Optional[str] = ""
    release_date: Optional[str] = ""
    track_number: int = Field(1, ge=0)
    track_number_padded: Optional[str] = None
    disc_number: int = Field(1, ge=0)
    disc_total: Optional[int] = Field(1, ge=0)
    total_tracks: Optional[int] = Field(None, ge=0)
    duration_ms: int = Field(0, ge=0)
    duration_str: Optional[str] = "0:00"
    genre: Optional[str] = None
    isrc: Optional[str] = None
    cover_url: Optional[str] = None


class QueueAddIn(BaseModel):
    playlist_name: str = "Album"
    playlist_owner: str = ""
    tracks: List[TrackIn] = Field(default_factory=list, max_length=5000)


class QueueActionIn(BaseModel):
    action: Literal["pause", "resume", "retry", "clear_completed", "clear_all", "cancel"]
    task_id: str = ""


class ResolveIn(BaseModel):
    url: str = ""


class SettingsIn(BaseModel):
    download_dir: Optional[str] = None
    filename_template: Optional[str] = Field(None, max_length=300)
    audio_quality: Optional[Literal[ALLOWED_AUDIO_QUALITIES]] = None
    max_threads: Optional[int] = Field(None, ge=1, le=MAX_THREADS_LIMIT)
    on_duplicate: Optional[Literal[ALLOWED_DUPLICATE_MODES]] = None


class LoginIn(BaseModel):
    password: str = ""


# =========================================================================
# ROUTES FRONTEND & AUTHENTIFICATION
# =========================================================================

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Page principale SPA responsive."""
    return templates.TemplateResponse(request, "index.html", {
        "version": __version__,
        "auth_enabled": auth.auth_enabled(),
    })


@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    if not auth.auth_enabled() or auth.is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"version": __version__})


@app.post("/api/login")
async def api_login(request: Request, payload: LoginIn):
    if not auth.auth_enabled():
        return {"status": "ok"}
    if not auth.check_password(payload.password):
        await asyncio.sleep(1.0)  # Ralentit les tentatives par force brute
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")

    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.session_token(),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return response


@app.post("/api/logout")
async def api_logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@app.get("/api/health")
async def api_health():
    """Vérification de santé publique (utilisée par le HEALTHCHECK Docker)."""
    return {"status": "ok", "version": __version__}


# =========================================================================
# ROUTES API : SYSTÈME & INFOS SERVEUR
# =========================================================================

@app.get("/api/system/info")
async def get_system_info():
    """Informations de connexion pour accès depuis smartphone et PC."""
    local_ips = get_local_ip_addresses()
    port = get_public_port()
    music_root = get_music_root()
    return {
        "hostname": socket.gethostname(),
        "local_ips": local_ips,
        "port": port,
        "access_urls": [f"http://{ip}:{port}" for ip in local_ips],
        "version": __version__,
        "auth_enabled": auth.auth_enabled(),
        "music_root": str(music_root) if music_root else None,
        "download_dir": config.get("download_dir"),
        "audio_quality": config.get("audio_quality", "320k"),
        "max_threads": config.get("max_threads", 3),
        "preset_templates": PRESET_TEMPLATES,
        "has_cookies": config.cookies_path.exists()
    }


# =========================================================================
# ROUTES API : RECHERCHE & ANALYSE D'ALBUMS ET URLS
# =========================================================================

@app.get("/api/search")
async def api_search(q: str = Query(..., description="Terme de recherche", max_length=200)):
    """Recherche d'albums via Deezer et iTunes (100% gratuit, sans clé)."""
    results = await asyncio.to_thread(search_albums, q, 15)
    return [
        {
            "id": p.id,
            "name": p.name,
            "owner": p.owner,
            "total_tracks": p.total_tracks,
            "cover_url": p.cover_url,
            "description": p.description
        }
        for p in results
    ]


@app.get("/api/album/{album_id}")
async def api_get_album_details(
    album_id: str,
    name: str = Query("", description="Nom de l'album"),
    artist: str = Query("", description="Artiste de l'album"),
    cover_url: str = Query("", description="Pochette")
):
    """Récupère la liste complète des morceaux d'un album avec durées et numéros de piste."""
    album = await asyncio.to_thread(fetch_album_tracks, album_id, name, artist, cover_url)
    return playlist_to_dict(album)


@app.post("/api/spotify/resolve")
async def api_resolve_spotify_url(payload: ResolveIn):
    """Analyse et extrait les pistes d'une URL Spotify (playlist, album ou titre)."""
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Veuillez fournir une URL Spotify.")

    try:
        playlist = await asyncio.to_thread(spotify_manager.fetch_by_url, url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return playlist_to_dict(playlist)


# =========================================================================
# ROUTES API : FILE DE TÉLÉCHARGEMENT & TEMPS RÉEL (SSE)
# =========================================================================

@app.post("/api/queue/add")
async def api_queue_add(payload: QueueAddIn):
    """Ajoute des pistes ou un album entier à la file de téléchargement."""
    playlist_name = payload.playlist_name
    if not payload.tracks:
        raise HTTPException(status_code=400, detail="Aucune piste à ajouter.")

    tracks: List[SpotifyTrack] = []
    for t in payload.tracks:
        artists_val = t.artists or [t.artist]
        track_number = t.track_number or 1
        tracks.append(SpotifyTrack(
            id=t.id,
            title=t.title,
            artist=t.artist,
            artists=artists_val,
            album=t.album or playlist_name,
            album_artist=t.album_artist or payload.playlist_owner or t.artist,
            year=t.year or "",
            release_date=t.release_date or "",
            track_number=track_number,
            track_number_padded=t.track_number_padded or f"{track_number:02d}",
            disc_number=t.disc_number or 1,
            disc_total=t.disc_total or 1,
            total_tracks=t.total_tracks or len(payload.tracks),
            duration_ms=t.duration_ms,
            duration_str=t.duration_str or "0:00",
            genre=t.genre,
            isrc=t.isrc,
            cover_url=t.cover_url,
            playlist_name=playlist_name
        ))

    added_count = queue_manager.add_tracks(tracks, playlist_name)
    queue_manager.start()
    return {"status": "success", "added_count": added_count, "total_in_queue": len(queue_manager.tasks)}


@app.get("/api/queue")
async def api_get_queue():
    """Retourne la liste complète des tâches et statistiques de la file."""
    return {"stats": queue_manager.get_stats(), "tasks": [task_to_dict(t) for t in list(queue_manager.tasks)]}


@app.post("/api/queue/action")
async def api_queue_action(payload: QueueActionIn):
    """Contrôle de la file d'attente (pause, resume, retry, clear, cancel)."""
    action = payload.action

    if action == "pause":
        queue_manager.pause()
    elif action == "resume":
        queue_manager.resume()
    elif action == "retry":
        queue_manager.retry_failed()
    elif action == "clear_completed":
        queue_manager.clear_completed()
    elif action == "clear_all":
        queue_manager.clear_all()
    elif action == "cancel":
        if not payload.task_id:
            raise HTTPException(status_code=400, detail="task_id requis pour annuler une tâche.")
        queue_manager.cancel_task(payload.task_id)

    return {"status": "ok", "action": action, "stats": queue_manager.get_stats()}


@app.get("/api/queue/events")
async def api_queue_events(request: Request):
    """Flux Server-Sent Events (SSE) pour mettre à jour l'interface Web en temps réel."""
    client_queue = asyncio.Queue()
    sse_subscribers.add(client_queue)

    async def event_generator():
        try:
            initial_stats = queue_manager.get_stats()
            yield f"data: {json.dumps({'type': 'stats', 'stats': initial_stats})}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(client_queue.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            sse_subscribers.discard(client_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# =========================================================================
# ROUTES API : BIBLIOTHÈQUE DU SERVEUR & STREAMING AUDIO
# =========================================================================

def _scan_library(download_dir: Path) -> Dict[str, Any]:
    albums_map: Dict[str, Dict[str, Any]] = {}
    total_tracks = 0

    for root, dirs, files in os.walk(download_dir):
        mp3_files = [f for f in files if f.lower().endswith(".mp3")]
        if not mp3_files:
            continue

        rel_folder = os.path.relpath(root, download_dir)
        folder_name = os.path.basename(root) if rel_folder != "." else "Musique"

        tracks_list = []
        for f in sorted(mp3_files):
            f_path = os.path.join(root, f)
            size_mb = os.path.getsize(f_path) / (1024 * 1024)
            rel_file_path = os.path.relpath(f_path, download_dir)
            tracks_list.append({
                "filename": f,
                "title": os.path.splitext(f)[0],
                "rel_path": rel_file_path.replace("\\", "/"),
                "size_mb": round(size_mb, 1)
            })
            total_tracks += 1

        albums_map[rel_folder] = {
            "folder_name": folder_name,
            "rel_folder": rel_folder.replace("\\", "/"),
            "track_count": len(tracks_list),
            "tracks": tracks_list
        }

    return {
        "download_dir": str(download_dir),
        "albums": list(albums_map.values()),
        "total_tracks": total_tracks
    }


@app.get("/api/library")
async def api_get_library():
    """Scanne le dossier local de téléchargement configuré sur le serveur."""
    download_dir = resolve_download_dir()
    if not download_dir.exists():
        return {"download_dir": str(download_dir), "albums": [], "total_tracks": 0}
    return await asyncio.to_thread(_scan_library, download_dir)


@app.get("/api/stream")
async def api_stream_file(path: str = Query(..., description="Chemin relatif du fichier MP3")):
    """
    Diffuse le MP3 en streaming natif (content-disposition: inline)
    avec support du seek/scrubbing (HTTP Range) pour le lecteur audio.
    Seuls les fichiers .mp3 situés dans le dossier de téléchargement sont accessibles.
    """
    download_dir = resolve_download_dir()
    target_path = (download_dir / path).resolve()

    if (
        not target_path.is_relative_to(download_dir)
        or target_path.suffix.lower() != ".mp3"
        or not target_path.is_file()
    ):
        raise HTTPException(status_code=404, detail="Fichier audio introuvable sur le serveur.")

    return FileResponse(
        str(target_path),
        media_type="audio/mpeg",
        content_disposition_type="inline"
    )


# =========================================================================
# ROUTES API : PARAMÈTRES DU SERVEUR
# =========================================================================

@app.get("/api/settings")
async def api_get_settings():
    curr_dir = config.get("download_dir")
    curr_template = config.get("filename_template")
    sample_preview = preview_template(curr_template)
    full_sample_path = os.path.join(curr_dir, sample_preview)
    music_root = get_music_root()

    return {
        "download_dir": curr_dir,
        "music_root": str(music_root) if music_root else None,
        "filename_template": curr_template,
        "audio_quality": config.get("audio_quality", "320k"),
        "max_threads": config.get("max_threads", 3),
        "on_duplicate": config.get("on_duplicate", "skip"),
        "preview": sample_preview,
        "full_preview": full_sample_path,
        "preset_templates": PRESET_TEMPLATES
    }


@app.post("/api/settings")
async def api_save_settings(payload: SettingsIn):
    """Enregistre le chemin local et la structure de dossiers sur le serveur."""
    if payload.download_dir and payload.download_dir.strip():
        raw_path = payload.download_dir.strip()
        expanded = Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()
        music_root = get_music_root()
        if music_root and not expanded.is_relative_to(music_root):
            raise HTTPException(
                status_code=400,
                detail=f"Le dossier de téléchargement doit se trouver dans {music_root}."
            )
        # Création automatique du dossier s'il n'existe pas
        try:
            expanded.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Chemin invalide sur le serveur : {e}")
        config.set("download_dir", str(expanded), auto_save=False)

    if payload.filename_template and payload.filename_template.strip():
        config.set("filename_template", payload.filename_template.strip(), auto_save=False)
    if payload.audio_quality is not None:
        config.set("audio_quality", payload.audio_quality, auto_save=False)
    if payload.max_threads is not None:
        config.set("max_threads", payload.max_threads, auto_save=False)
    if payload.on_duplicate is not None:
        config.set("on_duplicate", payload.on_duplicate, auto_save=False)

    config.save()
    curr_dir = config.get("download_dir")
    curr_tmpl = config.get("filename_template")

    return {
        "status": "success",
        "message": "Paramètres enregistrés",
        "download_dir": curr_dir,
        "filename_template": curr_tmpl,
        "preview": preview_template(curr_tmpl),
        "full_preview": os.path.join(curr_dir, preview_template(curr_tmpl))
    }


@app.post("/api/settings/cookies")
async def api_upload_cookies(file: UploadFile = File(...)):
    """Téléverse un fichier cookies.txt pour contourner le bridage YouTube."""
    content = await file.read(MAX_COOKIES_SIZE + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Fichier cookies.txt vide")
    if len(content) > MAX_COOKIES_SIZE:
        raise HTTPException(status_code=413, detail="Fichier cookies.txt trop volumineux (1 Mo maximum)")

    target_path = config.cookies_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(content)
    try:
        os.chmod(target_path, 0o600)
    except OSError:
        pass
    return {"status": "ok", "message": "Fichier cookies.txt activé avec succès !", "size": len(content)}
