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
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from ..config import config, PRESET_TEMPLATES
from ..spotify_client import spotify_manager, SpotifyTrack, SpotifyPlaylist
from ..album_search import search_albums, fetch_album_tracks
from ..queue_manager import queue_manager, DownloadTask
from ..file_manager import preview_template

# Gestionnaire d'abonnés SSE (Server-Sent Events) pour la progression en direct
sse_subscribers: set[asyncio.Queue] = set()
event_loop: Optional[asyncio.AbstractEventLoop] = None


def get_local_ip_addresses() -> List[str]:
    """Détecte les adresses IP locales de la machine pour faciliter l'accès smartphone."""
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
        task_data = {
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
        loop.call_soon_threadsafe(broadcast_event, {"type": "task_update", "task": task_data})

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
    version="2.0.0",
    lifespan=lifespan
)

# Configuration CORS pour accès réseau local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates_dir = BASE_DIR / "templates"
static_dir = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


# =========================================================================
# ROUTES FRONTEND
# =========================================================================

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Page principale SPA responsive."""
    return templates.TemplateResponse(request, "index.html")


# =========================================================================
# ROUTES API : SYSTÈME & INFOS SERVEUR
# =========================================================================

@app.get("/api/system/info")
async def get_system_info():
    """Informations de connexion pour accès depuis smartphone et PC."""
    local_ips = get_local_ip_addresses()
    return {
        "hostname": socket.gethostname(),
        "local_ips": local_ips,
        "port": 8000,
        "access_urls": [f"http://{ip}:8000" for ip in local_ips],
        "download_dir": config.get("download_dir"),
        "audio_quality": config.get("audio_quality", "320k"),
        "max_threads": config.get("max_threads", 3),
        "preset_templates": PRESET_TEMPLATES
    }


# =========================================================================
# ROUTES API : RECHERCHE & ANALYSE D'ALBUMS ET URLS
# =========================================================================

@app.get("/api/search")
async def api_search(q: str = Query(..., description="Terme de recherche")):
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
    return {
        "id": album.id,
        "name": album.name,
        "owner": album.owner,
        "total_tracks": album.total_tracks,
        "cover_url": album.cover_url,
        "tracks": [
            {
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "duration_str": t.duration_str,
                "duration_ms": t.duration_ms,
                "track_number": t.track_number,
                "track_number_padded": t.track_number_padded,
                "cover_url": t.cover_url
            }
            for t in album.tracks
        ]
    }


@app.post("/api/spotify/resolve")
async def api_resolve_spotify_url(payload: Dict[str, str] = Body(...)):
    """Analyse et extrait les pistes d'une URL Spotify (playlist, album ou titre)."""
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Veuillez fournir une URL Spotify.")

    try:
        playlist = await asyncio.to_thread(spotify_manager.fetch_by_url, url)
        return {
            "id": playlist.id,
            "name": playlist.name,
            "owner": playlist.owner,
            "total_tracks": playlist.total_tracks,
            "cover_url": playlist.cover_url,
            "tracks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "album": t.album,
                    "duration_str": t.duration_str,
                    "duration_ms": t.duration_ms,
                    "track_number": t.track_number,
                    "track_number_padded": t.track_number_padded,
                    "cover_url": t.cover_url
                }
                for t in playlist.tracks
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================================
# ROUTES API : FILE DE TÉLÉCHARGEMENT & TEMPS RÉEL (SSE)
# =========================================================================

@app.post("/api/queue/add")
async def api_queue_add(payload: Dict[str, Any] = Body(...)):
    """Ajoute des pistes ou un album entier à la file de téléchargement."""
    playlist_name = payload.get("playlist_name", "Album")
    raw_tracks = payload.get("tracks", [])
    if not raw_tracks:
        raise HTTPException(status_code=400, detail="Aucune piste à ajouter.")

    tracks: List[SpotifyTrack] = []
    for t in raw_tracks:
        tracks.append(SpotifyTrack(
            id=str(t.get("id")),
            title=t.get("title", "Titre inconnu"),
            artist=t.get("artist", "Artiste inconnu"),
            artists=[t.get("artist", "Artiste inconnu")],
            album=t.get("album", playlist_name),
            album_artist=t.get("artist", "Artiste inconnu"),
            year=str(t.get("year", "")),
            release_date=str(t.get("release_date", "")),
            track_number=int(t.get("track_number", 1)),
            track_number_padded=str(t.get("track_number_padded") or f"{int(t.get('track_number', 1)):02d}"),
            disc_number=int(t.get("disc_number", 1)),
            total_tracks=len(raw_tracks),
            duration_ms=int(t.get("duration_ms", 0)),
            duration_str=str(t.get("duration_str", "0:00")),
            cover_url=t.get("cover_url"),
            playlist_name=playlist_name
        ))

    added_count = queue_manager.add_tracks(tracks, playlist_name)
    queue_manager.start()
    return {"status": "success", "added_count": added_count, "total_in_queue": len(queue_manager.tasks)}


@app.get("/api/queue")
async def api_get_queue():
    """Retourne la liste complète des tâches et statistiques de la file."""
    stats = queue_manager.get_stats()
    tasks_data = []
    for t in queue_manager.tasks:
        tasks_data.append({
            "id": t.id,
            "title": t.track.title,
            "artist": t.track.artist,
            "album": t.track.album,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "status_message": t.status_message,
            "progress": t.progress,
            "target_path": t.target_path,
            "error_message": t.error_message
        })
    return {"stats": stats, "tasks": tasks_data}


@app.post("/api/queue/action")
async def api_queue_action(payload: Dict[str, str] = Body(...)):
    """Contrôle de la file d'attente (pause, resume, retry, clear)."""
    action = payload.get("action", "")
    task_id = payload.get("task_id", "")

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
    elif action == "cancel" and task_id:
        queue_manager.cancel_task(task_id)
    else:
        raise HTTPException(status_code=400, detail="Action non reconnue.")

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

@app.get("/api/library")
async def api_get_library():
    """Scanne le dossier local de téléchargement configuré sur le serveur."""
    download_dir_str = config.get("download_dir")
    download_dir = Path(os.path.expandvars(os.path.expanduser(download_dir_str)))
    if not download_dir.exists():
        return {"download_dir": str(download_dir), "albums": [], "total_tracks": 0}

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


@app.get("/api/stream")
async def api_stream_file(path: str = Query(..., description="Chemin relatif du fichier MP3")):
    """
    Diffuse le MP3 en streaming natif (content-disposition: inline)
    avec support du seek/scrubbing (HTTP Range) pour le lecteur audio.
    """
    download_dir_str = config.get("download_dir")
    download_dir = Path(os.path.expandvars(os.path.expanduser(download_dir_str))).resolve()
    target_path = (download_dir / path).resolve()

    if not str(target_path).startswith(str(download_dir)) or not target_path.exists():
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

    return {
        "download_dir": curr_dir,
        "filename_template": curr_template,
        "audio_quality": config.get("audio_quality", "320k"),
        "max_threads": config.get("max_threads", 3),
        "on_duplicate": config.get("on_duplicate", "skip"),
        "preview": sample_preview,
        "full_preview": full_sample_path,
        "preset_templates": PRESET_TEMPLATES
    }


@app.post("/api/settings")
async def api_save_settings(payload: Dict[str, Any] = Body(...)):
    """Enregistre le chemin local et la structure de dossiers sur le serveur."""
    if "download_dir" in payload and payload["download_dir"]:
        raw_path = payload["download_dir"].strip()
        # Création automatique du dossier s'il n'existe pas
        try:
            expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
            expanded.mkdir(parents=True, exist_ok=True)
            config.set("download_dir", str(expanded), auto_save=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Chemin invalide sur le serveur : {e}")

    if "filename_template" in payload and payload["filename_template"]:
        config.set("filename_template", payload["filename_template"].strip(), auto_save=False)
    if "audio_quality" in payload:
        config.set("audio_quality", payload["audio_quality"], auto_save=False)
    if "max_threads" in payload:
        config.set("max_threads", int(payload["max_threads"]), auto_save=False)
    if "on_duplicate" in payload:
        config.set("on_duplicate", payload["on_duplicate"], auto_save=False)

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
