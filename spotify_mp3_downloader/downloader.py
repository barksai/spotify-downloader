"""
Spotify MP3 Downloader - Audio Acquisition & ID3 Tagging Engine
Recherche YouTube Music / YouTube par ISRC / Titre + Artiste, téléchargement audio,
encodage FFmpeg 320 kbps et injection des métadonnées ID3v2.3 avec pochette HD via Mutagen.
"""
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import requests
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3, TIT2, TPE1, TPE2, TALB, TDRC, TYER, TDAT, TRCK, TPOS, TSRC, TCON, TCMP, COMM, APIC, ID3NoHeaderError
)

from .spotify_client import SpotifyTrack
from .config import config


class AudioDownloader:
    """Moteur de téléchargement audio et de tagging ID3."""

    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "SpotifyMP3Downloader"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _get_best_youtube_url(self, track: SpotifyTrack, progress_cb: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """
        Recherche intelligente sur YouTube / YouTube Music :
        1. Priorité au code ISRC officiel studio (le matching le plus fiable).
        2. Fallback avec Artiste + Titre + Audio.
        3. Fallback standard Artiste + Titre.
        Valide la concordance de durée pour éviter les remix, clips rallongés ou lives.
        """
        ydl_search_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "socket_timeout": 15,
            "source_address": "0.0.0.0",
        }

        queries = []
        if track.isrc:
            queries.append(f"ytsearch3:isrc:{track.isrc}")
        queries.append(f"ytsearch5:{track.artist} - {track.title} Audio")
        queries.append(f"ytsearch5:{track.artist} - {track.title} Official Audio")
        queries.append(f"ytsearch5:{track.artist} - {track.title}")

        expected_duration = track.duration_ms / 1000.0

        for query in queries:
            if progress_cb:
                progress_cb(f"Recherche: {query[:45]}...")
            try:
                with yt_dlp.YoutubeDL(ydl_search_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    entries = info.get("entries", [])
                    if not entries:
                        continue

                    best_entry = None
                    min_diff = float("inf")

                    for entry in entries:
                        if not entry:
                            continue
                        e_duration = entry.get("duration")
                        if e_duration is not None and expected_duration > 0:
                            diff = abs(e_duration - expected_duration)
                            # Rejeter les morceaux ayant plus de 15 secondes d'écart
                            if diff < 15 and diff < min_diff:
                                min_diff = diff
                                best_entry = entry
                        else:
                            # Si durée indisponible, garder le premier résultat
                            if best_entry is None:
                                best_entry = entry

                    if best_entry:
                        v_id = best_entry.get("id") or best_entry.get("url")
                        if v_id:
                            return f"https://www.youtube.com/watch?v={v_id}"
            except Exception as e:
                print(f"[Downloader] Erreur recherche query '{query}': {e}")
                continue

        return None

    def _find_ffmpeg(self) -> Optional[str]:
        candidates = [
            Path.cwd() / "ffmpeg.exe",
            Path(__file__).resolve().parent / "ffmpeg.exe",
            Path(__file__).resolve().parent.parent / "ffmpeg.exe",
            Path.cwd() / "dist" / "SpotifyMP3Downloader" / "ffmpeg.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return shutil.which("ffmpeg")

    def download_track(
        self,
        track: SpotifyTrack,
        output_filepath: str,
        audio_quality: str = "320k",
        progress_cb: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """
        Exécute le pipeline complet pour une piste :
        1. Recherche du flux audio
        2. Téléchargement et encodage MP3 via FFmpeg
        3. Écriture des tags ID3v2.3 et pochette HD
        4. Déplacement sécurisé vers le chemin final Windows
        """
        task_id = str(uuid.uuid4())[:8]
        temp_base = self.temp_dir / f"track_{task_id}"
        temp_mp3 = self.temp_dir / f"track_{task_id}.mp3"

        def _ydl_hook(d):
            if d.get("status") == "downloading" and progress_cb:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = (downloaded / total * 100.0) if total > 0 else 0.0
                speed = d.get("speed") or 0
                speed_kb = speed / 1024.0 if speed else 0
                status_text = f"Téléchargement {pct:.1f}% ({speed_kb:.0f} Ko/s)"
                progress_cb(status_text, min(pct, 90.0))
            elif d.get("status") == "finished" and progress_cb:
                progress_cb("Encodage MP3 en cours...", 92.0)

        # 1. Recherche
        if progress_cb:
            progress_cb("Recherche de la piste...", 5.0)

        video_url = self._get_best_youtube_url(
            track,
            progress_cb=lambda s: progress_cb(s, 10.0) if progress_cb else None
        )

        if not video_url:
            raise RuntimeError(f"Aucune source audio trouvée pour '{track.artist} - {track.title}'")

        # 2. Téléchargement & Extraction Audio MP3
        if progress_cb:
            progress_cb("Initialisation du téléchargement...", 15.0)

        bitrate_value = "320"
        if audio_quality == "256k":
            bitrate_value = "256"
        elif audio_quality == "192k":
            bitrate_value = "192"
        elif audio_quality == "128k":
            bitrate_value = "128"
        elif audio_quality == "V0":
            bitrate_value = "0"  # VBR

        ydl_opts = {
            "format": "ba/b/bestaudio/best",
            "outtmpl": str(temp_base) + ".%(ext)s",
            "progress_hooks": [_ydl_hook],
            "quiet": False,
            "no_warnings": False,
            "noprogress": True,
            "source_address": "0.0.0.0",  # Force IPv4 (évite le blocage IPv6 dans Docker)
            "http_chunk_size": 10485760,  # Découpage en blocs de 10 Mo pour contourner le bridage
            "throttled_rate": 102400,     # Seuil 100 Ko/s pour forcer la reconnexion automatique
            "socket_timeout": 20,
            "retries": 10,
            "fragment_retries": 10,
            "js_runtimes": {"node": {}},  # Utiliser Node.js pour résoudre le défi n-sig
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "web"],
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            },
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate_value,
            }],
        }

        ffmpeg_bin = self._find_ffmpeg()
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        except Exception as e:
            self._cleanup(temp_base, temp_mp3)
            raise RuntimeError(f"Erreur de téléchargement/conversion audio: {e}")

        if not temp_mp3.exists():
            self._cleanup(temp_base, temp_mp3)
            raise RuntimeError("Le fichier MP3 temporaire n'a pas été généré par FFmpeg.")

        # 3. Injection des tags ID3v2.3
        if progress_cb:
            progress_cb("Injection des métadonnées ID3 & pochette...", 95.0)

        cover_bytes = None
        try:
            cover_bytes = self._tag_mp3(str(temp_mp3), track)
        except Exception as e:
            print(f"[Downloader] Avertissement tagging ID3: {e}")

        # 4. Déplacement vers le dossier final
        if progress_cb:
            progress_cb("Finalisation...", 98.0)

        try:
            target_dir = os.path.dirname(output_filepath)
            os.makedirs(target_dir, exist_ok=True)
            
            # Écrasement atomique sécurisé
            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            shutil.move(str(temp_mp3), output_filepath)

            # Sauvegarde de la pochette cover.jpg / folder.jpg pour Jellyfin / Plex / Picard
            if cover_bytes:
                self._save_folder_cover(target_dir, cover_bytes)
        except Exception as e:
            self._cleanup(temp_base, temp_mp3)
            raise RuntimeError(f"Impossible de déplacer le fichier vers la destination: {e}")

        if progress_cb:
            progress_cb("Terminé avec succès", 100.0)

        return True

    def _save_folder_cover(self, target_dir: str, cover_data: bytes) -> None:
        """Sauvegarde cover.jpg et folder.jpg dans le dossier d'album pour Jellyfin / Plex / Navidrome."""
        try:
            for cover_name in ("cover.jpg", "folder.jpg"):
                c_path = os.path.join(target_dir, cover_name)
                if not os.path.exists(c_path):
                    with open(c_path, "wb") as f:
                        f.write(cover_data)
        except Exception as e:
            print(f"[Downloader] Note enregistrement cover.jpg: {e}")

    def _tag_mp3(self, mp3_path: str, track: SpotifyTrack) -> Optional[bytes]:
        """
        Injecte tous les tags ID3v2.3 conformes aux exigences de Jellyfin, MusicBrainz Picard,
        Windows Explorer et autoradios, avec encodage UTF-16, pochette HD et sauvegarde ID3v1.
        Retourne les octets de la pochette pour création éventuelle de cover.jpg.
        """
        try:
            audio = MP3(mp3_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(mp3_path)
            audio.add_tags(ID3=ID3)

        if audio.tags is None:
            audio.add_tags(ID3=ID3)

        # Nettoyage préalable des tags existants pour éviter les doublons ou scories yt-dlp
        audio.tags.clear()

        # 1. Titre (TIT2)
        audio.tags.add(TIT2(encoding=1, text=track.title))

        # 2. Artistes interprètes (TPE1)
        artists_list = track.artists if track.artists else [track.artist]
        audio.tags.add(TPE1(encoding=1, text=artists_list))

        # 3. Artiste de l'album (TPE2) - Crucial pour le regroupement dans Jellyfin & Picard
        album_artist = track.album_artist or track.artist or "Various Artists"
        audio.tags.add(TPE2(encoding=1, text=album_artist))

        # 4. Album (TALB)
        audio.tags.add(TALB(encoding=1, text=track.album))

        # 5. Date & Année (TYER / TDAT / TDRC)
        year_str = str(track.year or "").strip()
        rel_date_str = str(track.release_date or "").strip()
        if not year_str and rel_date_str:
            year_str = rel_date_str[:4]
        if year_str:
            audio.tags.add(TYER(encoding=1, text=year_str))
        if rel_date_str:
            audio.tags.add(TDRC(encoding=1, text=rel_date_str))
            if len(rel_date_str) >= 10 and "-" in rel_date_str:
                try:
                    parts = rel_date_str[:10].split("-")
                    # TDAT in ID3v2.3 is DDMM
                    audio.tags.add(TDAT(encoding=1, text=f"{parts[2]}{parts[1]}"))
                except Exception:
                    pass

        # 6. Numéro de piste / Total (TRCK) - format standard "01/12" ou "1/12"
        if track.total_tracks:
            trck_str = f"{track.track_number}/{track.total_tracks}"
        else:
            trck_str = str(track.track_number)
        audio.tags.add(TRCK(encoding=1, text=trck_str))

        # 7. Numéro de disque / Total disques (TPOS) - format standard "1/1"
        disc_num = track.disc_number or 1
        disc_total = getattr(track, "disc_total", 1) or 1
        audio.tags.add(TPOS(encoding=1, text=f"{disc_num}/{disc_total}"))

        # 8. Genre musical (TCON)
        genre_val = getattr(track, "genre", None)
        if genre_val:
            audio.tags.add(TCON(encoding=1, text=genre_val))

        # 9. ISRC (TSRC)
        if track.isrc:
            audio.tags.add(TSRC(encoding=1, text=track.isrc))

        # 10. Tag Compilation (TCMP)
        if album_artist.lower() in ("various artists", "divers artistes", "compilation", "soundtrack", "various"):
            audio.tags.add(TCMP(encoding=1, text="1"))

        # 11. Commentaire de source (COMM)
        audio.tags.add(COMM(encoding=1, lang="eng", desc="Comment", text="Exporté via Spotify MP3 Downloader"))

        # 12. Pochette HD (APIC)
        cover_bytes: Optional[bytes] = None
        if track.cover_url:
            try:
                resp = requests.get(track.cover_url, timeout=10)
                if resp.status_code == 200 and resp.content:
                    raw_content = resp.content
                    try:
                        from io import BytesIO
                        from PIL import Image
                        if not raw_content.startswith(b"\xff\xd8\xff"):
                            img = Image.open(BytesIO(raw_content)).convert("RGB")
                            buf = BytesIO()
                            img.save(buf, format="JPEG", quality=95)
                            cover_bytes = buf.getvalue()
                        else:
                            cover_bytes = raw_content
                    except Exception:
                        cover_bytes = raw_content

                    audio.tags.add(APIC(
                        encoding=0,
                        mime="image/jpeg",
                        type=3,  # Front cover
                        desc="Front Cover",
                        data=cover_bytes
                    ))
            except Exception as e:
                print(f"[Downloader] Impossible de télécharger la pochette ({track.cover_url}): {e}")

        # Sauvegarde en ID3v2.3 (standard Jellyfin/Picard/Windows) + ID3v1 compatible
        audio.save(v2_version=3, v1=2)
        return cover_bytes

    def _cleanup(self, temp_base: Path, temp_mp3: Path) -> None:
        """Nettoie les fichiers temporaires éventuels."""
        try:
            if temp_mp3.exists():
                temp_mp3.unlink()
            # Nettoyer les éventuels fichiers de travail partiels
            for f in self.temp_dir.glob(f"{temp_base.name}*"):
                try:
                    f.unlink()
                except Exception:
                    pass
        except Exception:
            pass


# Instance globale
downloader = AudioDownloader()
