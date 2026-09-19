"""
Spotify MP3 Downloader - Configuration Manager
Gère la persistance et les valeurs par défaut des réglages utilisateur dans %APPDATA%.
"""
import os
import json
from pathlib import Path
from typing import Any, Dict, List

def _get_default_download_dir() -> str:
    env_download = os.getenv("DOWNLOAD_DIR")
    if env_download:
        return env_download
    if os.path.exists("/music") and os.path.isdir("/music"):
        return "/music"
    return os.path.join(os.path.expanduser("~"), "Music", "SpotifyDownloads")


DEFAULT_SETTINGS = {
    # Chemins & Organisation
    "download_dir": _get_default_download_dir(),
    "filename_template": "{Artist}/{Album}/{TrackNumber} - {Title}.mp3",
    "on_duplicate": "skip",  # 'skip', 'overwrite', 'rename'
    
    # Qualité audio & Métadonnées
    "audio_quality": "320k",  # '320k', '256k', '192k', '128k', 'V0'
    "embed_cover": True,
    "embed_metadata": True,
    
    # Multithreading
    "max_threads": 3,
    
    # Identifiants Spotify API (Optionnel)
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "redirect_port": 8888,
    
    # Playlists sauvegardées localement (permet l'accès sans compte Premium)
    "saved_playlists": [
        {
            "id": "37i9dQZF1DXcBWIGoYBM5M",
            "name": "Today's Top Hits",
            "owner": "Spotify",
            "total_tracks": 50,
            "url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            "cover_url": "https://i.scdn.co/image/ab67706f0000000277c25630aff0901ed026d2d4"
        }
    ],
    
    # Interface
    "theme": "dark",
    "color_theme": "green",
}

PRESET_TEMPLATES = {
    "Artiste / Album / [Num] Titre": "{Artist}/{Album}/{TrackNumber} - {Title}.mp3",
    "Artiste / [Num] Titre": "{Artist}/{TrackNumber} - {Title}.mp3",
    "Playlist / [Num] Artiste - Titre": "{Playlist}/{TrackNumber} - {Artist} - {Title}.mp3",
    "Playlist / Artiste / Titre": "{Playlist}/{Artist}/{Title}.mp3",
    "Tout à plat (Artiste - Titre)": "{Artist} - {Title}.mp3",
    "Année - Album / [Num] Titre": "{Year} - {Album}/{TrackNumber} - {Title}.mp3",
}


class ConfigManager:
    """Gestionnaire de configuration persistante en JSON dans AppData Windows."""
    
    def __init__(self, app_name: str = "SpotifyMP3Downloader"):
        self.app_name = app_name
        env_config = os.getenv("CONFIG_DIR")
        if env_config:
            self.app_dir = Path(env_config)
        elif os.path.exists("/config") and os.path.isdir("/config"):
            self.app_dir = Path("/config")
        else:
            self.app_dir = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / self.app_name
        self.config_path = self.app_dir / "settings.json"
        self.settings: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Charge les paramètres depuis le disque ou initialise avec les valeurs par défaut."""
        self.settings = DEFAULT_SETTINGS.copy()
        try:
            self.app_dir.mkdir(parents=True, exist_ok=True)
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.settings.update(loaded)
        except Exception as e:
            print(f"[ConfigManager] Erreur chargement réglages: {e}. Valeurs par défaut utilisées.")
        return self.settings

    def save(self) -> bool:
        """Enregistre les réglages actuels dans le fichier JSON."""
        try:
            self.app_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] Erreur enregistrement réglages: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        self.settings[key] = value
        if auto_save:
            self.save()

    def get_saved_playlists(self) -> List[Dict[str, Any]]:
        return self.get("saved_playlists", [])

    def add_saved_playlist(self, p_dict: Dict[str, Any]) -> None:
        playlists = self.get_saved_playlists()
        # Éviter les doublons par ID
        playlists = [p for p in playlists if p.get("id") != p_dict.get("id")]
        playlists.insert(0, p_dict)
        self.set("saved_playlists", playlists)

    def remove_saved_playlist(self, playlist_id: str) -> None:
        playlists = self.get_saved_playlists()
        playlists = [p for p in playlists if p.get("id") != playlist_id]
        self.set("saved_playlists", playlists)


# Instance globale
config = ConfigManager()
