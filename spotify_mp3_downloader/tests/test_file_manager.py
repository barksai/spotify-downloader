"""
Tests unitaires pour le moteur de template et l'assainissement de chemins Windows.
"""
import os
import tempfile
import pytest
from spotify_mp3_downloader.file_manager import (
    sanitize_component,
    render_template,
    resolve_destination_path,
    extract_metadata_vars,
    WINDOWS_RESERVED_NAMES
)


def test_sanitize_forbidden_chars():
    # Test caractères interdits Windows : < > : " / \ | ? *
    bad_title = 'Can You Feel The Love Tonight? / Yes: Always *Special* <Deluxe> "Edition" | Remastered'
    clean = sanitize_component(bad_title)
    
    for forbidden in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        assert forbidden not in clean
    assert clean == "Can You Feel The Love Tonight - Yes - Always Special (Deluxe) 'Edition' - Remastered"


def test_sanitize_trailing_dots_and_spaces():
    # Windows NTFS interdit les points et espaces en fin de composant
    bad_name = "Greatest Hits...    "
    clean = sanitize_component(bad_name)
    assert clean == "Greatest Hits"


def test_sanitize_reserved_names():
    # Windows réserve CON, PRN, AUX, NUL, COM1-9, LPT1-9
    for reserved in ["CON", "prn", "Aux", "nul", "COM1", "lpt9"]:
        clean = sanitize_component(reserved)
        assert clean.upper() not in WINDOWS_RESERVED_NAMES
        assert clean.upper() == f"{reserved.upper()}_"


def test_render_template_standard():
    meta = {
        "title": "Around the World",
        "artist": "Daft Punk",
        "album": "Homework",
        "year": "1997",
        "track_number": 7,
        "disc_number": 1,
        "isrc": "FRZ029700070"
    }
    
    tmpl = "{Artist}/{Album}/{TrackNumber} - {Title}.mp3"
    result = render_template(tmpl, meta)
    
    expected = os.path.join("Daft Punk", "Homework", "07 - Around the World.mp3")
    assert result == expected


def test_render_template_with_special_characters():
    meta = {
        "title": "Highway to Hell / Live",
        "artist": "AC/DC",
        "album": "Back In Black: 2020 Edition?",
        "year": "1980",
        "track_number": 1,
    }
    
    tmpl = "{Artist}/{Album}/{TrackNumber} - {Title}.mp3"
    result = render_template(tmpl, meta)
    
    expected = os.path.join("AC-DC", "Back In Black - 2020 Edition", "01 - Highway to Hell - Live.mp3")
    assert result == expected


def test_resolve_destination_path_duplicates():
    with tempfile.TemporaryDirectory() as tmpdir:
        meta = {
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "track_number": 1
        }
        tmpl = "{Artist}/{Title}.mp3"
        
        # 1. Premier calcul (fichier non existant)
        p1, skip1 = resolve_destination_path(tmpdir, tmpl, meta, on_duplicate="skip")
        assert skip1 is False
        assert os.path.exists(os.path.dirname(p1))
        
        # Créer le fichier fictif
        with open(p1, "w", encoding="utf-8") as f:
            f.write("fake mp3 data")
            
        # 2. Test "skip"
        p2, skip2 = resolve_destination_path(tmpdir, tmpl, meta, on_duplicate="skip")
        assert p2 == p1
        assert skip2 is True
        
        # 3. Test "overwrite"
        p3, skip3 = resolve_destination_path(tmpdir, tmpl, meta, on_duplicate="overwrite")
        assert p3 == p1
        assert skip3 is False
        
        # 4. Test "rename"
        p4, skip4 = resolve_destination_path(tmpdir, tmpl, meta, on_duplicate="rename")
        assert p4 != p1
        assert "(1)" in p4
        assert skip4 is False
