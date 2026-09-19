"""
Spotify MP3 Downloader - File Manager & Windows Path Engine
Gère l'assainissement des chemins Windows et le rendu des templates de dossiers.
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, Tuple

# Caractères strictement interdits dans les noms de fichiers et dossiers Windows
WINDOWS_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Noms de périphériques réservés par MS-DOS / Windows
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

# Remplacements intelligents des caractères spéciaux pour préserver la lisibilité
CHAR_REPLACEMENTS = {
    ":": " -",
    "/": "-",
    "\\": "-",
    "\"": "'",
    "?": "",
    "*": "",
    "<": "(",
    ">": ")",
    "|": "-",
}


def sanitize_component(text: str, max_length: int = 120) -> str:
    """
    Assainit un nom de dossier ou un nom de fichier pour Windows :
    - Remplace les caractères interdits par des équivalents sûrs.
    - Supprime les espaces et points terminaux (interdits par Windows NTFS).
    - Empêche l'utilisation des noms de périphériques réservés (CON, PRN, etc.).
    - Tronque à une longueur raisonnable pour éviter l'erreur MAX_PATH (260 caractères).
    """
    if not text:
        return "Unknown"
    
    cleaned = str(text)
    
    # 1. Remplacement intelligent
    for char, repl in CHAR_REPLACEMENTS.items():
        cleaned = cleaned.replace(char, repl)
        
    # 2. Nettoyage de tout autre caractère de contrôle non imprimable
    cleaned = WINDOWS_FORBIDDEN_CHARS.sub("", cleaned)
    
    # 3. Réduction des espaces multiples
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 4. Suppression des points et espaces de fin (interdits sur Windows)
    cleaned = cleaned.rstrip('. ')
    
    if not cleaned:
        cleaned = "Unknown"
        
    # 5. Vérification des noms réservés Windows (insensible à la casse)
    base_name = cleaned.split('.')[0].upper()
    if base_name in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_"
        
    # 6. Tronquage sécurisé
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip('. ')
        
    return cleaned


def extract_metadata_vars(metadata: Dict[str, Any], playlist_name: str = "Playlist") -> Dict[str, str]:
    """Extrait et formate les variables disponibles pour le moteur de template."""
    track_num = metadata.get("track_number", 1)
    try:
        track_num_int = int(track_num)
        track_num_padded = f"{track_num_int:02d}"
    except (ValueError, TypeError):
        track_num_padded = "01"
        track_num_int = 1

    disc_num = metadata.get("disc_number", 1)
    try:
        disc_num_int = int(disc_num)
    except (ValueError, TypeError):
        disc_num_int = 1

    artists = metadata.get("artists", [])
    artist_main = metadata.get("artist") or (artists[0] if artists else "Unknown Artist")
    album_artist = metadata.get("album_artist") or artist_main
    album = metadata.get("album") or "Unknown Album"
    title = metadata.get("title") or "Unknown Title"
    year = str(metadata.get("year") or "")
    if not year and metadata.get("release_date"):
        year = str(metadata["release_date"])[:4]
    if not year:
        year = "Unknown Year"
        
    isrc = metadata.get("isrc") or ""

    return {
        "Artist": sanitize_component(artist_main),
        "AlbumArtist": sanitize_component(album_artist),
        "Album": sanitize_component(album),
        "Title": sanitize_component(title),
        "Year": sanitize_component(year),
        "TrackNumber": track_num_padded,
        "TrackNumberRaw": str(track_num_int),
        "DiscNumber": str(disc_num_int),
        "Playlist": sanitize_component(playlist_name or "Playlist"),
        "ISRC": sanitize_component(isrc),
    }


def render_template(template: str, metadata: Dict[str, Any], playlist_name: str = "Playlist") -> str:
    """
    Applique le template de chemin avec assainissement de chaque segment :
    Supporte les barres obliques (/ ou \\) pour créer l'arborescence de sous-dossiers.
    Garantit l'extension .mp3 finale.
    """
    if not template or not template.strip():
        template = "{Artist}/{Album}/{TrackNumber} - {Title}.mp3"
        
    vars_dict = extract_metadata_vars(metadata, playlist_name)
    
    # 1. Normaliser les séparateurs de dossiers en /
    norm_template = template.replace("\\", "/")
    
    # 2. Remplacer les variables dans la chaîne
    formatted = norm_template
    for key, val in vars_dict.items():
        formatted = formatted.replace(f"{{{key}}}", val)
        
    # Nettoyer les balises inconnues {Inconnu} résiduelles
    formatted = re.sub(r'\{[a-zA-Z0-9_]+\}', '', formatted)
    
    # 3. Découper par segment de dossier
    segments = [s.strip() for s in formatted.split("/") if s.strip()]
    if not segments:
        segments = [f"{vars_dict['Artist']} - {vars_dict['Title']}.mp3"]
        
    # 4. Assainir individuellement chaque dossier et le nom du fichier
    sanitized_segments = []
    for i, seg in enumerate(segments):
        is_filename = (i == len(segments) - 1)
        if is_filename:
            # Retirer l'extension si présente pour assainir le tronc puis réajouter .mp3
            if seg.lower().endswith(".mp3"):
                seg_base = seg[:-4]
            else:
                seg_base = seg
            clean_base = sanitize_component(seg_base)
            sanitized_segments.append(f"{clean_base}.mp3")
        else:
            sanitized_segments.append(sanitize_component(seg))
            
    # 5. Reconstruire le chemin relatif
    return os.path.join(*sanitized_segments)


def resolve_destination_path(
    root_dir: str,
    template: str,
    metadata: Dict[str, Any],
    playlist_name: str = "Playlist",
    on_duplicate: str = "skip"
) -> Tuple[str, bool]:
    """
    Calcule le chemin absolu final sur le système Windows.
    Gère la création automatique des dossiers parents et la résolution des doublons.
    
    Retourne : (absolute_path: str, should_skip: bool)
    """
    rel_path = render_template(template, metadata, playlist_name)
    full_path = os.path.abspath(os.path.join(root_dir, rel_path))
    
    # Créer les répertoires parents en amont
    parent_dir = os.path.dirname(full_path)
    os.makedirs(parent_dir, exist_ok=True)
    
    # Gestion des doublons
    if os.path.exists(full_path):
        if on_duplicate == "skip":
            return full_path, True
        elif on_duplicate == "overwrite":
            return full_path, False
        elif on_duplicate == "rename":
            base, ext = os.path.splitext(full_path)
            counter = 1
            new_path = f"{base} ({counter}){ext}"
            while os.path.exists(new_path):
                counter += 1
                new_path = f"{base} ({counter}){ext}"
            return new_path, False
            
    return full_path, False


def preview_template(template: str, sample_meta: Dict[str, Any] = None, playlist_name: str = "Mes Coups de Cœur") -> str:
    """Génère un exemple de chemin prévisualisé pour l'interface graphique."""
    if sample_meta is None:
        sample_meta = {
            "title": "One More Time",
            "artist": "Daft Punk",
            "album_artist": "Daft Punk",
            "album": "Discovery",
            "year": "2001",
            "track_number": 1,
            "disc_number": 1,
            "isrc": "FRZ020100010"
        }
    return render_template(template, sample_meta, playlist_name)
