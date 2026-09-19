"""
Tests unitaires pour le moteur de recherche d'albums.
"""
from spotify_mp3_downloader.album_search import search_albums, fetch_album_tracks


def test_search_albums_returns_results():
    results = search_albums("Discovery Daft Punk", limit=5)
    assert len(results) > 0
    first = results[0]
    assert "discovery" in first.name.lower()
    assert "daft punk" in first.owner.lower()
    assert first.total_tracks > 0
    assert first.cover_url is not None


def test_fetch_album_tracks():
    results = search_albums("Discovery Daft Punk", limit=1)
    assert len(results) > 0
    alb = results[0]
    
    full_album = fetch_album_tracks(alb.id, alb.name, alb.owner, alb.cover_url)
    assert len(full_album.tracks) > 0
    assert full_album.total_tracks == len(full_album.tracks)
    
    t1 = full_album.tracks[0]
    assert t1.title != ""
    assert t1.artist != ""
    assert t1.album == full_album.name
    assert t1.duration_ms > 0
    assert t1.track_number == 1
    assert t1.track_number_padded == "01"
