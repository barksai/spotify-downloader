"""
Tests unitaires pour le moteur de téléchargement et l'injection ID3v2 Mutagen.
"""
import os
import tempfile
import subprocess
import pytest
from mutagen.mp3 import MP3
from mutagen.id3 import ID3

from spotify_mp3_downloader.spotify_client import SpotifyTrack
from spotify_mp3_downloader.downloader import AudioDownloader


def create_silent_mp3(filepath: str):
    """Génère un court fichier MP3 valide de 1 seconde via FFmpeg."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1", "-acodec", "libmp3lame", "-b:a", "128k", filepath
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def test_mutagen_id3_tagging():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_mp3 = os.path.join(tmpdir, "test_audio.mp3")
        create_silent_mp3(test_mp3)

        track = SpotifyTrack(
            id="test1",
            title="Get Lucky",
            artist="Daft Punk",
            artists=["Daft Punk", "Pharrell Williams", "Nile Rodgers"],
            album="Random Access Memories",
            album_artist="Daft Punk",
            year="2013",
            release_date="2013-05-17",
            track_number=8,
            track_number_padded="08",
            disc_number=1,
            total_tracks=13,
            duration_ms=248000,
            duration_str="4:08",
            isrc="USQX91300108",
            cover_url=None,
            spotify_url="https://open.spotify.com/track/test1"
        )

        downloader = AudioDownloader()
        downloader._tag_mp3(test_mp3, track)

        # Vérification des tags injectés
        audio = MP3(test_mp3, ID3=ID3)
        tags = audio.tags

        assert tags is not None
        assert str(tags.get("TIT2")) == "Get Lucky"
        assert "Daft Punk" in str(tags.get("TPE1"))
        assert "Pharrell Williams" in str(tags.get("TPE1"))
        assert str(tags.get("TALB")) == "Random Access Memories"
        assert str(tags.get("TPE2")) == "Daft Punk"
        assert str(tags.get("TRCK")) == "8/13"
        assert str(tags.get("TPOS")) == "1/1"
        assert str(tags.get("TSRC")) == "USQX91300108"
        assert "Spotify MP3 Downloader" in str(tags.get("COMM:Comment:eng"))


def test_save_folder_cover_for_jellyfin():
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = AudioDownloader()
        dummy_cover = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        downloader._save_folder_cover(tmpdir, dummy_cover)

        assert os.path.exists(os.path.join(tmpdir, "cover.jpg"))
        assert os.path.exists(os.path.join(tmpdir, "folder.jpg"))
        with open(os.path.join(tmpdir, "cover.jpg"), "rb") as f:
            assert f.read() == dummy_cover

