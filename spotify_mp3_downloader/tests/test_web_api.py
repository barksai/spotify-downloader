"""
Tests unitaires pour l'API Web FastAPI (routes REST, système, recherche).
"""
import pytest
from fastapi.testclient import TestClient
from spotify_mp3_downloader.web.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Spotify MP3" in response.text
    assert "tab-search" in response.text


def test_api_system_info(client):
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "hostname" in data
    assert "local_ips" in data
    assert data["port"] == 8000
    assert len(data["access_urls"]) > 0


def test_api_settings(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "audio_quality" in data
    assert "filename_template" in data

    # Test update setting
    update_resp = client.post("/api/settings", json={"audio_quality": "320k"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "success"


def test_api_queue(client):
    response = client.get("/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "tasks" in data
    assert "overall_percent" in data["stats"]


def test_api_library(client):
    response = client.get("/api/library")
    assert response.status_code == 200
    data = response.json()
    assert "albums" in data
    assert "total_tracks" in data


def test_api_search_albums(client):
    response = client.get("/api/search?q=Discovery+Daft+Punk")
    assert response.status_code == 200
    albums = response.json()
    assert isinstance(albums, list)
    assert len(albums) > 0
    assert "discovery" in albums[0]["name"].lower()
