"""
Tests unitaires pour l'API Web FastAPI (routes REST, système, recherche, sécurité).
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spotify_mp3_downloader import __version__
from spotify_mp3_downloader.config import config
from spotify_mp3_downloader.spotify_client import SpotifyPlaylist
from spotify_mp3_downloader.web import server
from spotify_mp3_downloader.web.server import app

MUSIC_DIR = Path(os.environ["DOWNLOAD_DIR"]).resolve()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_download_dir():
    config.set("download_dir", str(MUSIC_DIR), auto_save=False)
    yield
    config.set("download_dir", str(MUSIC_DIR), auto_save=False)


@pytest.fixture
def password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    return "s3cret"


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Spotify MP3" in response.text
    assert "tab-search" in response.text
    assert f"v{__version__}" in response.text


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_api_system_info(client):
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "hostname" in data
    assert "local_ips" in data
    assert data["port"] == 8000
    assert data["version"] == __version__
    assert data["auth_enabled"] is False
    assert len(data["access_urls"]) > 0


def test_api_system_info_public_port_and_host(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_PORT", "9000")
    monkeypatch.setenv("PUBLIC_HOST", "192.168.1.10")
    data = client.get("/api/system/info").json()
    assert data["port"] == 9000
    assert data["access_urls"] == ["http://192.168.1.10:9000"]


def test_api_settings(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "audio_quality" in data
    assert "filename_template" in data

    update_resp = client.post("/api/settings", json={"audio_quality": "320k"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "success"


def test_api_settings_rejects_invalid_values(client):
    assert client.post("/api/settings", json={"audio_quality": "999k"}).status_code == 422
    assert client.post("/api/settings", json={"max_threads": 50}).status_code == 422
    assert client.post("/api/settings", json={"on_duplicate": "explode"}).status_code == 422


def test_api_settings_download_dir_restricted_to_music_root(client, tmp_path):
    outside = tmp_path / "ailleurs"
    resp = client.post("/api/settings", json={"download_dir": str(outside)})
    assert resp.status_code == 400
    assert not outside.exists()

    resp = client.post("/api/settings", json={"download_dir": "/"})
    assert resp.status_code == 400

    inside = MUSIC_DIR / "Sous-dossier"
    resp = client.post("/api/settings", json={"download_dir": str(inside)})
    assert resp.status_code == 200
    assert inside.is_dir()


def test_api_queue(client):
    response = client.get("/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "tasks" in data
    assert "overall_percent" in data["stats"]


def test_api_queue_action_validation(client):
    assert client.post("/api/queue/action", json={"action": "detonate"}).status_code == 422
    assert client.post("/api/queue/action", json={"action": "cancel"}).status_code == 400
    assert client.post("/api/queue/action", json={"action": "pause"}).status_code == 200


def test_api_queue_add_validates_tracks(client):
    resp = client.post("/api/queue/add", json={"tracks": [{"id": "x", "track_number": "pas un nombre"}]})
    assert resp.status_code == 422
    assert client.post("/api/queue/add", json={"tracks": []}).status_code == 400


def test_api_library(client):
    response = client.get("/api/library")
    assert response.status_code == 200
    data = response.json()
    assert "albums" in data
    assert "total_tracks" in data


def test_api_search_albums(client, monkeypatch):
    fake = [SpotifyPlaylist(id="deezer_1", name="Discovery", description="", owner="Daft Punk",
                            total_tracks=14, cover_url=None, is_public=True)]
    monkeypatch.setattr(server, "search_albums", lambda q, limit: fake)

    response = client.get("/api/search?q=Discovery+Daft+Punk")
    assert response.status_code == 200
    albums = response.json()
    assert len(albums) == 1
    assert albums[0]["name"] == "Discovery"


# -------------------------------------------------------------------------
# Streaming : seuls les .mp3 du dossier de téléchargement sont accessibles
# -------------------------------------------------------------------------

def test_stream_serves_mp3(client):
    track = MUSIC_DIR / "Artiste" / "01 - Titre.mp3"
    track.parent.mkdir(parents=True, exist_ok=True)
    track.write_bytes(b"ID3fake-mp3")
    resp = client.get("/api/stream", params={"path": "Artiste/01 - Titre.mp3"})
    assert resp.status_code == 200
    assert resp.content == b"ID3fake-mp3"


def test_stream_rejects_non_mp3_and_traversal(client):
    (MUSIC_DIR / "notes.txt").write_text("secret")
    assert client.get("/api/stream", params={"path": "notes.txt"}).status_code == 404
    assert client.get("/api/stream", params={"path": "../config/settings.json"}).status_code == 404
    assert client.get("/api/stream", params={"path": "/etc/passwd"}).status_code == 404


def test_stream_rejects_sibling_directory_with_same_prefix(client):
    sibling = MUSIC_DIR.parent / (MUSIC_DIR.name + "2")
    sibling.mkdir(exist_ok=True)
    (sibling / "leak.mp3").write_bytes(b"leak")
    resp = client.get("/api/stream", params={"path": f"../{sibling.name}/leak.mp3"})
    assert resp.status_code == 404


# -------------------------------------------------------------------------
# Authentification & CSRF
# -------------------------------------------------------------------------

def test_auth_required_when_password_set(client, password):
    assert client.get("/api/queue").status_code == 401
    assert client.get("/api/health").status_code == 200
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert client.get("/login").status_code == 200


def test_login_with_wrong_password(client, password, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401


def test_login_sets_session_cookie(password):
    with TestClient(app) as c:
        resp = c.post("/api/login", json={"password": password})
        assert resp.status_code == 200
        assert "httponly" in resp.headers["set-cookie"].lower()
        assert "samesite=strict" in resp.headers["set-cookie"].lower()
        assert c.get("/api/queue").status_code == 200

        c.post("/api/logout")
        c.cookies.clear()
        assert c.get("/api/queue").status_code == 401


def test_bearer_token(client, password):
    resp = client.get("/api/queue", headers={"Authorization": f"Bearer {password}"})
    assert resp.status_code == 200
    resp = client.get("/api/queue", headers={"Authorization": "Bearer mauvais"})
    assert resp.status_code == 401


def test_cross_origin_post_is_rejected(client):
    resp = client.post("/api/queue/action", json={"action": "pause"},
                       headers={"Origin": "https://site-malveillant.example"})
    assert resp.status_code == 403

    resp = client.post("/api/queue/action", json={"action": "pause"},
                       headers={"Origin": "http://testserver"})
    assert resp.status_code == 200


def test_cookies_upload(client):
    resp = client.post("/api/settings/cookies", files={"file": ("cookies.txt", b"# Netscape HTTP Cookie File\n")})
    assert resp.status_code == 200
    assert config.cookies_path.exists()

    resp = client.post("/api/settings/cookies", files={"file": ("cookies.txt", b"")})
    assert resp.status_code == 400

    big = b"x" * (server.MAX_COOKIES_SIZE + 10)
    resp = client.post("/api/settings/cookies", files={"file": ("cookies.txt", big)})
    assert resp.status_code == 413
