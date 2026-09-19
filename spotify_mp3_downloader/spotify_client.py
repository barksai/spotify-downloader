"""
Spotify MP3 Downloader - Spotify Web API & Public Metadata Scraper
Supporte le mode Public Web Scraper (100% Gratuit, sans compte Premium) et le mode API OAuth.
"""
import os
import re
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from pathlib import Path

import requests
try:
    import spotipy
    from spotipy.oauth2 import SpotifyPKCE, SpotifyOAuth, SpotifyClientCredentials
except ImportError:
    spotipy = None
    SpotifyPKCE = None
    SpotifyOAuth = None
    SpotifyClientCredentials = None

from .config import config

SPOTIFY_SCOPES = "playlist-read-private playlist-read-collaborative user-library-read user-read-private"
WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr,en-US;q=0.9,en;q=0.8"
}


@dataclass
class SpotifyTrack:
    """Structure représentant un morceau Spotify avec toutes ses métadonnées."""
    id: str
    title: str
    artist: str
    artists: List[str]
    album: str
    album_artist: str
    year: str
    release_date: str
    track_number: int
    track_number_padded: str
    disc_number: int
    total_tracks: int
    duration_ms: int
    duration_str: str
    isrc: Optional[str] = None
    cover_url: Optional[str] = None
    spotify_url: str = ""
    playlist_name: str = "Spotify"
    genre: Optional[str] = None
    disc_total: int = 1

    @classmethod
    def from_spotify_dict(cls, item: Dict[str, Any], playlist_name: str = "Spotify") -> "SpotifyTrack":
        track_data = item.get("track") if "track" in item and item["track"] else item
        
        track_id = track_data.get("id") or f"local_{hash(track_data.get('name', ''))}"
        title = track_data.get("name") or "Unknown Title"
        
        raw_artists = track_data.get("artists") or []
        artist_names = [a.get("name", "Unknown") for a in raw_artists if a.get("name")]
        artist_main = artist_names[0] if artist_names else "Unknown Artist"
        
        album_data = track_data.get("album") or {}
        album_name = album_data.get("name") or "Unknown Album"
        album_artists = [a.get("name", "") for a in album_data.get("artists", []) if a.get("name")]
        album_artist = album_artists[0] if album_artists else artist_main
        
        release_date = album_data.get("release_date") or ""
        year = release_date[:4] if release_date else "Unknown Year"
        
        track_num = track_data.get("track_number") or 1
        disc_num = track_data.get("disc_number") or 1
        total_tracks = album_data.get("total_tracks") or track_num
        track_num_padded = f"{track_num:02d}"
        
        duration_ms = track_data.get("duration_ms") or 0
        total_sec = duration_ms // 1000
        mins = total_sec // 60
        secs = total_sec % 60
        duration_str = f"{mins}:{secs:02d}"
        
        external_ids = track_data.get("external_ids") or {}
        isrc = external_ids.get("isrc")
        
        images = album_data.get("images") or []
        cover_url = images[0].get("url") if images else None
        
        external_urls = track_data.get("external_urls") or {}
        spotify_url = external_urls.get("spotify") or f"https://open.spotify.com/track/{track_id}"
        
        return cls(
            id=track_id,
            title=title,
            artist=artist_main,
            artists=artist_names,
            album=album_name,
            album_artist=album_artist,
            year=year,
            release_date=release_date,
            track_number=track_num,
            track_number_padded=track_num_padded,
            disc_number=disc_num,
            total_tracks=total_tracks,
            duration_ms=duration_ms,
            duration_str=duration_str,
            isrc=isrc,
            cover_url=cover_url,
            spotify_url=spotify_url,
            playlist_name=playlist_name,
        )


@dataclass
class SpotifyPlaylist:
    """Structure représentant une playlist ou un album Spotify."""
    id: str
    name: str
    description: str
    owner: str
    total_tracks: int
    cover_url: Optional[str]
    is_public: bool
    tracks: List[SpotifyTrack] = field(default_factory=list)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.endswith("/favicon.ico") or parsed.path == "/robots.txt":
            self.send_response(204)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            status = "Connexion réussie !"
            msg = "Votre compte Spotify est maintenant connecté. Vous pouvez fermer cet onglet."
            color = "#1DB954"
            code = 200
        elif "error" in params:
            OAuthCallbackHandler.error = params["error"][0]
            status = "Erreur de connexion"
            msg = f"Détail : {OAuthCallbackHandler.error}"
            color = "#E22134"
            code = 400
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Spotify Downloader</h1></body></html>")
            return

        html = f"""<!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>Spotify Auth</title>
        <style>body {{ font-family: sans-serif; background: #121212; color: #FFF; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ background: #282828; padding: 40px 50px; border-radius: 12px; text-align: center; max-width: 480px; }}
        h1 {{ color: {color}; font-size: 24px; }} p {{ color: #B3B3B3; }}</style></head>
        <body><div class="card"><h1>{status}</h1><p>{msg}</p></div></body></html>"""

        self.send_response(code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


class SpotifyManager:
    """Gestionnaire unifié supportant l'extraction Web directe sans clé et l'API Spotify."""

    def __init__(self):
        self.sp: Optional[spotipy.Spotify] = None
        self.cache_dir = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / "SpotifyMP3Downloader"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = str(self.cache_dir / ".spotify_token_cache")
        self.current_user_data: Optional[Dict[str, Any]] = None
        self._try_restore_session()

    def _try_restore_session(self) -> bool:
        if spotipy is None:
            return False
        try:
            client_id = config.get("spotify_client_id")
            if not client_id:
                return False
            client_secret = config.get("spotify_client_secret")
            redirect_port = config.get("redirect_port", 8888)
            redirect_uri = f"http://127.0.0.1:{redirect_port}/callback"

            if client_secret:
                auth_mgr = SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri, scope=SPOTIFY_SCOPES, cache_path=self.cache_path, open_browser=False)
            else:
                auth_mgr = SpotifyPKCE(client_id=client_id, redirect_uri=redirect_uri, scope=SPOTIFY_SCOPES, cache_path=self.cache_path, open_browser=False)

            token_info = auth_mgr.get_cached_token()
            if token_info:
                self.sp = spotipy.Spotify(auth_manager=auth_mgr)
                self.current_user_data = self.sp.current_user()
                return True
        except Exception:
            pass
        return False

    def is_authenticated(self) -> bool:
        return self.sp is not None

    def get_user_name(self) -> str:
        if self.current_user_data:
            return self.current_user_data.get("display_name") or self.current_user_data.get("id") or "Utilisateur Spotify"
        return "Non connecté (Mode Public Actif)"

    def login_pkce(self, client_id: str = "", client_secret: str = "", redirect_port: int = 8888, callback_fn: Optional[Callable] = None) -> bool:
        c_id = client_id.strip() if client_id and client_id.strip() else config.get("spotify_client_id", "").strip()
        c_sec = client_secret.strip() if client_secret and client_secret.strip() else config.get("spotify_client_secret", "").strip()

        if not c_id:
            if callback_fn:
                callback_fn(False, "Client ID manquant.")
            return False

        redirect_uri = f"http://127.0.0.1:{redirect_port}/callback"
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except Exception:
                pass

        try:
            if c_sec:
                auth_mgr = SpotifyOAuth(client_id=c_id, client_secret=c_sec, redirect_uri=redirect_uri, scope=SPOTIFY_SCOPES, cache_path=self.cache_path, open_browser=False)
            else:
                auth_mgr = SpotifyPKCE(client_id=c_id, redirect_uri=redirect_uri, scope=SPOTIFY_SCOPES, cache_path=self.cache_path, open_browser=False)
            auth_url = auth_mgr.get_authorize_url()
        except Exception as e:
            if callback_fn:
                callback_fn(False, str(e))
            return False

        OAuthCallbackHandler.auth_code = None
        OAuthCallbackHandler.error = None

        try:
            httpd = HTTPServer(("127.0.0.1", redirect_port), OAuthCallbackHandler)
        except Exception as e:
            if callback_fn:
                callback_fn(False, f"Port {redirect_port} indisponible: {e}")
            return False

        webbrowser.open(auth_url)
        timeout = 120
        start_time = time.time()
        httpd.timeout = 1.0
        while time.time() - start_time < timeout:
            httpd.handle_request()
            if OAuthCallbackHandler.auth_code or OAuthCallbackHandler.error:
                break
        httpd.server_close()

        if OAuthCallbackHandler.auth_code:
            try:
                token = auth_mgr.get_access_token(OAuthCallbackHandler.auth_code, check_cache=False)
                if token:
                    self.sp = spotipy.Spotify(auth_manager=auth_mgr)
                    self.current_user_data = self.sp.current_user()
                    config.set("spotify_client_id", c_id)
                    if c_sec:
                        config.set("spotify_client_secret", c_sec)
                    if callback_fn:
                        callback_fn(True, self.get_user_name())
                    return True
            except Exception as e:
                err = str(e)
                if "Active premium subscription required" in err or "403" in err:
                    err = "Spotify restreint désormais l'API développeur aux comptes Premium.\n\nUtilisez le mode sans clé en collant directement le lien de votre playlist !"
                if callback_fn:
                    callback_fn(False, err)
                return False

        err_msg = OAuthCallbackHandler.error or "Délai expiré."
        if callback_fn:
            callback_fn(False, err_msg)
        return False

    def logout(self) -> None:
        self.sp = None
        self.current_user_data = None
        if os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except Exception:
                pass

    # =========================================================================
    # EXTRACTEUR WEB PUBLIC DIRECT (100% Gratuit, Aucune clé ni Premium requis)
    # =========================================================================

    def fetch_via_public_embed(self, item_type: str, item_id: str) -> SpotifyPlaylist:
        """
        Extrait toutes les métadonnées officielles depuis la page Embed publique Spotify.
        Fonctionne pour tous les comptes (Gratuit et Premium), sans clé API.
        """
        embed_url = f"https://open.spotify.com/embed/{item_type}/{item_id}"
        resp = requests.get(embed_url, headers=WEB_HEADERS, timeout=12)
        
        if resp.status_code != 200:
            raise RuntimeError(f"Impossible de joindre la page Spotify ({resp.status_code}).")

        match_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text)
        if not match_next:
            raise RuntimeError("Données de la playlist introuvables. Vérifiez que le lien Spotify est public/partageable.")

        try:
            data = json.loads(match_next.group(1))
            props = data.get("props", {}).get("pageProps", {})
            entity = props.get("state", {}).get("data", {}).get("entity", {})
        except Exception as e:
            raise RuntimeError(f"Erreur d'analyse des métadonnées: {e}")

        entity_type = entity.get("type") or item_type
        name = entity.get("name") or entity.get("title") or "Playlist Spotify"
        subtitle = entity.get("subtitle") or ""
        
        # Artistes / Créateur
        creator = subtitle
        if not creator and entity.get("artists"):
            creator = ", ".join([a.get("name", "") for a in entity.get("artists") if a.get("name")])
        if not creator:
            creator = "Spotify"

        # Pochette
        cover_sources = entity.get("coverArt", {}).get("sources", [])
        cover_url = cover_sources[0].get("url") if cover_sources else None
        if not cover_url and entity.get("visualIdentity", {}).get("image"):
            cover_url = entity["visualIdentity"]["image"][0].get("url")

        # Cas 1 : Titre Unique (Single Track)
        if entity_type == "track" or item_type == "track":
            duration_ms = entity.get("duration") or 0
            total_sec = duration_ms // 1000
            mins = total_sec // 60
            secs = total_sec % 60
            dur_str = f"{mins}:{secs:02d}"

            artist_list = [a.get("name") for a in entity.get("artists", []) if a.get("name")]
            artist_main = artist_list[0] if artist_list else (subtitle or "Artiste inconnu")
            
            rel_date = entity.get("releaseDate", {}).get("isoString", "") if isinstance(entity.get("releaseDate"), dict) else str(entity.get("releaseDate") or "")
            year = rel_date[:4] if rel_date else ""

            t = SpotifyTrack(
                id=item_id,
                title=entity.get("title") or name,
                artist=artist_main,
                artists=artist_list if artist_list else [artist_main],
                album=name,
                album_artist=artist_main,
                year=year,
                release_date=rel_date,
                track_number=1,
                track_number_padded="01",
                disc_number=1,
                total_tracks=1,
                duration_ms=duration_ms,
                duration_str=dur_str,
                cover_url=cover_url,
                spotify_url=f"https://open.spotify.com/track/{item_id}",
                playlist_name="Titre Spotify"
            )
            return SpotifyPlaylist(
                id=item_id,
                name=t.title,
                description=f"Titre de {t.artist}",
                owner=t.artist,
                total_tracks=1,
                cover_url=cover_url,
                is_public=True,
                tracks=[t]
            )

        # Cas 2 : Playlist ou Album
        raw_tracklist = entity.get("trackList", [])
        tracks: List[SpotifyTrack] = []

        rel_date = entity.get("releaseDate", {}).get("isoString", "") if isinstance(entity.get("releaseDate"), dict) else str(entity.get("releaseDate") or "")
        year = rel_date[:4] if rel_date else ""

        for idx, item in enumerate(raw_tracklist, start=1):
            t_uri = item.get("uri") or ""
            t_id = t_uri.split(":")[-1] if ":" in t_uri else f"t_{idx}"
            t_title = item.get("title") or "Unknown Title"
            t_sub = item.get("subtitle") or creator
            
            # Artistes
            t_artists = [a.strip() for a in t_sub.split(",") if a.strip()]
            t_artist_main = t_artists[0] if t_artists else t_sub

            dur_ms = item.get("duration") or 0
            t_sec = dur_ms // 1000
            m = t_sec // 60
            s = t_sec % 60
            dur_str = f"{m}:{s:02d}"

            # Pochette spécifique ou globale
            t_cover = cover_url

            track_obj = SpotifyTrack(
                id=t_id,
                title=t_title,
                artist=t_artist_main,
                artists=t_artists,
                album=name,
                album_artist=creator,
                year=year,
                release_date=rel_date,
                track_number=idx,
                track_number_padded=f"{idx:02d}",
                disc_number=1,
                disc_total=1,
                total_tracks=len(raw_tracklist),
                duration_ms=dur_ms,
                duration_str=dur_str,
                cover_url=t_cover,
                spotify_url=f"https://open.spotify.com/track/{t_id}",
                playlist_name=name
            )
            tracks.append(track_obj)

        return SpotifyPlaylist(
            id=item_id,
            name=name,
            description=f"Playlist de {creator} ({len(tracks)} titres)",
            owner=creator,
            total_tracks=len(tracks),
            cover_url=cover_url,
            is_public=True,
            tracks=tracks
        )

    # =========================================================================
    # ANALYSE & RÉSOLUTION UNIFIÉE D'URL
    # =========================================================================

    @staticmethod
    def parse_spotify_url(url_or_uri: str) -> Tuple[Optional[str], Optional[str]]:
        text = url_or_uri.strip()
        if not text:
            return None, None
            
        uri_match = re.match(r'spotify:(playlist|album|track):([a-zA-Z0-9]+)', text)
        if uri_match:
            return uri_match.group(1), uri_match.group(2)
            
        url_match = re.search(r'open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album|track)/([a-zA-Z0-9]+)', text)
        if url_match:
            return url_match.group(1), url_match.group(2)
            
        return None, None

    def fetch_by_url(self, url: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> SpotifyPlaylist:
        """Charge n'importe quelle URL Spotify sans nécessiter de compte Premium."""
        item_type, item_id = self.parse_spotify_url(url)
        if not item_type or not item_id:
            raise ValueError("URL Spotify invalide. Format attendu : https://open.spotify.com/playlist/...")

        # 1. Tenter avec l'extracteur direct (rapide, sans clé, 100% gratuit)
        try:
            playlist_obj = self.fetch_via_public_embed(item_type, item_id)
            if playlist_obj and playlist_obj.tracks:
                # Sauvegarder automatiquement dans les playlists locales
                config.add_saved_playlist({
                    "id": playlist_obj.id,
                    "name": playlist_obj.name,
                    "owner": playlist_obj.owner,
                    "total_tracks": playlist_obj.total_tracks,
                    "url": f"https://open.spotify.com/{item_type}/{item_id}",
                    "cover_url": playlist_obj.cover_url
                })
                return playlist_obj
        except Exception as e:
            print(f"[SpotifyManager] Extraction embed a échoué: {e}. Essai via API...")

        # 2. Fallback via Spotipy si connecté
        if self.sp:
            if item_type == "playlist":
                return self.sp.playlist(item_id)
            elif item_type == "album":
                return self.sp.album(item_id)
            elif item_type == "track":
                return self.sp.track(item_id)

        raise RuntimeError("Impossible de charger les morceaux de ce lien. Vérifiez que la playlist est bien publique ou partageable.")

    def fetch_user_playlists(self) -> List[SpotifyPlaylist]:
        """Retourne la liste des playlists sauvegardées en mode gratuit ou API."""
        saved = config.get_saved_playlists()
        result = []
        for s in saved:
            result.append(SpotifyPlaylist(
                id=s.get("id", ""),
                name=s.get("name", "Playlist"),
                description="",
                owner=s.get("owner", "Spotify"),
                total_tracks=s.get("total_tracks", 0),
                cover_url=s.get("cover_url"),
                is_public=True,
                tracks=[]
            ))
        return result


# Instance globale
spotify_manager = SpotifyManager()
