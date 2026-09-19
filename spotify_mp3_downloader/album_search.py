"""
Spotify MP3 Downloader - Album Search Engine
Recherche d'albums complète (via Deezer et iTunes APIs publiques, gratuites et sans clé)
permettant d'explorer et de télécharger un album complet en MP3 320 kbps.
"""
from typing import List, Optional
import requests

from .spotify_client import SpotifyPlaylist, SpotifyTrack

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def search_albums(query: str, limit: int = 15) -> List[SpotifyPlaylist]:
    """
    Recherche des albums correspondant à la requête texte (artiste ou nom d'album).
    Utilise les API publiques de Deezer et iTunes pour un résultat exhaustif et rapide sans clé API.
    """
    q = query.strip()
    if not q:
        return []

    albums: List[SpotifyPlaylist] = []
    seen_keys = set()

    # 1. Recherche principale via Deezer API (très bon classement par pertinence et pochettes 1000x1000)
    try:
        resp = requests.get(
            "https://api.deezer.com/search/album",
            params={"q": q, "limit": limit},
            headers=HEADERS,
            timeout=8
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for item in data:
                title = item.get("title") or "Album inconnu"
                artist = item.get("artist", {}).get("name") or "Artiste inconnu"
                dedup_key = f"{title.lower()}___{artist.lower()}"
                
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    cover = item.get("cover_xl") or item.get("cover_big") or item.get("cover_medium")
                    nb_tracks = item.get("nb_tracks", 0)
                    album_id = f"deezer_{item.get('id')}"
                    
                    albums.append(SpotifyPlaylist(
                        id=album_id,
                        name=title,
                        description=f"Album de {artist}",
                        owner=artist,
                        total_tracks=nb_tracks,
                        cover_url=cover,
                        is_public=True,
                        tracks=[]
                    ))
    except Exception as e:
        print(f"[AlbumSearch] Erreur recherche Deezer: {e}")

    # 2. Complément via iTunes Search API si peu de résultats
    if len(albums) < 5:
        try:
            resp = requests.get(
                "https://itunes.apple.com/search",
                params={"term": q, "entity": "album", "limit": limit},
                headers=HEADERS,
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json().get("results", [])
                for item in data:
                    title = item.get("collectionName") or "Album inconnu"
                    artist = item.get("artistName") or "Artiste inconnu"
                    dedup_key = f"{title.lower()}___{artist.lower()}"
                    
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        art = item.get("artworkUrl100", "")
                        if art:
                            art = art.replace("100x100bb.jpg", "600x600bb.jpg")
                        nb_tracks = item.get("trackCount", 0)
                        album_id = f"itunes_{item.get('collectionId')}"
                        year = item.get("releaseDate", "")[:4]
                        
                        albums.append(SpotifyPlaylist(
                            id=album_id,
                            name=title,
                            description=f"Album de {artist} ({year})" if year else f"Album de {artist}",
                            owner=artist,
                            total_tracks=nb_tracks,
                            cover_url=art,
                            is_public=True,
                            tracks=[]
                        ))
        except Exception as e:
            print(f"[AlbumSearch] Erreur recherche iTunes: {e}")

    return albums


def fetch_album_tracks(album_id: str, album_name: str, artist_name: str, cover_url: Optional[str] = None) -> SpotifyPlaylist:
    """
    Récupère la liste complète des morceaux d'un album recherché et les convertit
    en objets SpotifyTrack directement compatibles avec le moteur de téléchargement.
    """
    tracks: List[SpotifyTrack] = []
    final_cover = cover_url
    owner = artist_name
    title_album = album_name

    # Source Deezer
    if album_id.startswith("deezer_"):
        clean_id = album_id.replace("deezer_", "")
        resp = requests.get(f"https://api.deezer.com/album/{clean_id}", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rel_date = data.get("release_date", "")
            year = rel_date[:4] if rel_date else ""
            final_cover = data.get("cover_xl") or data.get("cover_big") or final_cover
            owner = data.get("artist", {}).get("name") or owner
            title_album = data.get("title") or title_album
            
            raw_tracks = data.get("tracks", {}).get("data", [])
            total = len(raw_tracks)
            
            for idx, t in enumerate(raw_tracks, start=1):
                dur_sec = t.get("duration", 0)
                dur_ms = dur_sec * 1000
                m = dur_sec // 60
                s = dur_sec % 60
                dur_str = f"{m}:{s:02d}"
                pos = t.get("track_position") or idx
                t_artist = t.get("artist", {}).get("name") or owner
                t_title = t.get("title") or f"Piste {pos}"
                
                tracks.append(SpotifyTrack(
                    id=f"dz_{t.get('id')}",
                    title=t_title,
                    artist=t_artist,
                    artists=[t_artist],
                    album=title_album,
                    album_artist=owner,
                    year=year,
                    release_date=rel_date,
                    track_number=pos,
                    track_number_padded=f"{pos:02d}",
                    disc_number=t.get("disk_number", 1) or 1,
                    total_tracks=total,
                    duration_ms=dur_ms,
                    duration_str=dur_str,
                    cover_url=final_cover,
                    spotify_url="",
                    playlist_name=title_album
                ))

    # Source iTunes
    elif album_id.startswith("itunes_"):
        clean_id = album_id.replace("itunes_", "")
        resp = requests.get("https://itunes.apple.com/lookup", params={"id": clean_id, "entity": "song"}, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("results", [])
            if items:
                alb_meta = items[0]
                rel_date = alb_meta.get("releaseDate", "")
                year = rel_date[:4] if rel_date else ""
                art = alb_meta.get("artworkUrl100", "")
                if art:
                    final_cover = art.replace("100x100bb.jpg", "600x600bb.jpg")
                owner = alb_meta.get("artistName") or owner
                title_album = alb_meta.get("collectionName") or title_album
                
                song_items = [it for it in items[1:] if it.get("wrapperType") == "track"]
                total = len(song_items)
                
                for it in song_items:
                    dur_ms = it.get("trackTimeMillis", 0)
                    dur_sec = dur_ms // 1000
                    m = dur_sec // 60
                    s = dur_sec % 60
                    dur_str = f"{m}:{s:02d}"
                    pos = it.get("trackNumber", 1)
                    t_artist = it.get("artistName") or owner
                    t_title = it.get("trackName") or f"Piste {pos}"
                    
                    tracks.append(SpotifyTrack(
                        id=f"it_{it.get('trackId')}",
                        title=t_title,
                        artist=t_artist,
                        artists=[t_artist],
                        album=title_album,
                        album_artist=owner,
                        year=year,
                        release_date=rel_date,
                        track_number=pos,
                        track_number_padded=f"{pos:02d}",
                        disc_number=it.get("discNumber", 1) or 1,
                        total_tracks=total,
                        duration_ms=dur_ms,
                        duration_str=dur_str,
                        cover_url=final_cover,
                        spotify_url="",
                        playlist_name=title_album
                    ))

    return SpotifyPlaylist(
        id=album_id,
        name=title_album,
        description=f"Album de {owner} ({len(tracks)} titres)",
        owner=owner,
        total_tracks=len(tracks),
        cover_url=final_cover,
        is_public=True,
        tracks=tracks
    )
