"""
Tests unitaires pour le moteur de recherche d'albums (réseau simulé : aucun appel Deezer/iTunes réel).
"""
import pytest

from spotify_mp3_downloader import album_search
from spotify_mp3_downloader.album_search import search_albums, fetch_album_tracks


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


DEEZER_SEARCH = {
    "data": [
        {
            "id": 302127,
            "title": "Discovery",
            "artist": {"name": "Daft Punk"},
            "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/discovery/1000x1000.jpg",
            "nb_tracks": 2,
        }
    ]
}

DEEZER_ALBUM = {
    "title": "Discovery",
    "release_date": "2001-03-07",
    "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/discovery/1000x1000.jpg",
    "artist": {"name": "Daft Punk"},
    "genres": {"data": [{"name": "Electro"}]},
    "tracks": {
        "data": [
            {"id": 1, "title": "One More Time", "duration": 320, "track_position": 1,
             "disk_number": 1, "artist": {"name": "Daft Punk"}, "isrc": "GBDUW0000053"},
            {"id": 2, "title": "Aerodynamic", "duration": 212, "track_position": 2,
             "disk_number": 1, "artist": {"name": "Daft Punk"}, "isrc": "GBDUW0000054"},
        ]
    },
}


@pytest.fixture
def fake_network(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if url == "https://api.deezer.com/search/album":
            return FakeResponse(DEEZER_SEARCH)
        if url.startswith("https://api.deezer.com/album/"):
            return FakeResponse(DEEZER_ALBUM)
        if url.startswith("https://itunes.apple.com/"):
            return FakeResponse({"results": []})
        raise AssertionError(f"URL inattendue : {url}")

    monkeypatch.setattr(album_search.requests, "get", fake_get)


def test_search_albums_returns_results(fake_network):
    results = search_albums("Discovery Daft Punk", limit=5)
    assert len(results) > 0
    first = results[0]
    assert first.id == "deezer_302127"
    assert "discovery" in first.name.lower()
    assert "daft punk" in first.owner.lower()
    assert first.total_tracks > 0
    assert first.cover_url is not None


def test_search_albums_empty_query_does_not_hit_network(monkeypatch):
    monkeypatch.setattr(album_search.requests, "get", lambda *a, **k: pytest.fail("appel réseau inattendu"))
    assert search_albums("   ") == []


def test_search_albums_survives_network_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("réseau indisponible")

    monkeypatch.setattr(album_search.requests, "get", boom)
    assert search_albums("Discovery") == []


def test_fetch_album_tracks(fake_network):
    full_album = fetch_album_tracks("deezer_302127", "Discovery", "Daft Punk", None)
    assert len(full_album.tracks) == 2
    assert full_album.total_tracks == len(full_album.tracks)

    t1 = full_album.tracks[0]
    assert t1.title == "One More Time"
    assert t1.artist == "Daft Punk"
    assert t1.album == full_album.name
    assert t1.duration_ms == 320000
    assert t1.duration_str == "5:20"
    assert t1.track_number == 1
    assert t1.track_number_padded == "01"
    assert t1.genre == "Electro"
    assert t1.isrc == "GBDUW0000053"
