"""
Tests unitaires pour le client Spotify et l'analyse des URLs.
"""
from spotify_mp3_downloader.spotify_client import SpotifyManager, SpotifyTrack


def test_parse_spotify_urls():
    # URL Track
    t_type, t_id = SpotifyManager.parse_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert t_type == "track"
    assert t_id == "4cOdK2wGLETKBW3PvgPWqT"

    # URL Album
    a_type, a_id = SpotifyManager.parse_spotify_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3?si=abcdef123")
    assert a_type == "album"
    assert a_id == "1DFixLWuPkv3KT3TnV35m3"

    # URL Playlist avec langue internationale
    p_type, p_id = SpotifyManager.parse_spotify_url("https://open.spotify.com/intl-fr/playlist/37i9dQZF1DXcBWIGoYBM5M")
    assert p_type == "playlist"
    assert p_id == "37i9dQZF1DXcBWIGoYBM5M"

    # URI Spotify standard
    u_type, u_id = SpotifyManager.parse_spotify_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
    assert u_type == "track"
    assert u_id == "4cOdK2wGLETKBW3PvgPWqT"

    # Invalide
    inv_type, inv_id = SpotifyManager.parse_spotify_url("https://youtube.com/watch?v=12345")
    assert inv_type is None
    assert inv_id is None


def test_spotify_track_from_dict():
    sample_payload = {
        "track": {
            "id": "trk123",
            "name": "Harder, Better, Faster, Stronger",
            "artists": [
                {"name": "Daft Punk"},
                {"name": "Romanthony"}
            ],
            "album": {
                "name": "Discovery",
                "release_date": "2001-03-12",
                "total_tracks": 14,
                "images": [
                    {"url": "https://i.scdn.co/image/ab67616d0000b273discovery"}
                ]
            },
            "track_number": 4,
            "disc_number": 1,
            "duration_ms": 224000,
            "external_ids": {
                "isrc": "FRZ020100040"
            },
            "external_urls": {
                "spotify": "https://open.spotify.com/track/trk123"
            }
        }
    }

    track = SpotifyTrack.from_spotify_dict(sample_payload, playlist_name="Daft Hits")

    assert track.id == "trk123"
    assert track.title == "Harder, Better, Faster, Stronger"
    assert track.artist == "Daft Punk"
    assert track.artists == ["Daft Punk", "Romanthony"]
    assert track.album == "Discovery"
    assert track.year == "2001"
    assert track.track_number == 4
    assert track.track_number_padded == "04"
    assert track.total_tracks == 14
    assert track.duration_str == "3:44"
    assert track.isrc == "FRZ020100040"
    assert track.cover_url == "https://i.scdn.co/image/ab67616d0000b273discovery"
