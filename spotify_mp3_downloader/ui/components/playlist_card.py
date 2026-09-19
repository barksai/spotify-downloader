"""
Composant visuel pour l'affichage d'une carte de playlist ou d'album.
"""
import io
import threading
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image
import requests

from ...spotify_client import SpotifyPlaylist

# Cache mémoire pour les miniatures d'images
IMAGE_CACHE = {}


class PlaylistCard(ctk.CTkFrame):
    """Carte représentant une playlist ou un album Spotify."""

    def __init__(
        self,
        master,
        playlist: SpotifyPlaylist,
        on_explore: Callable[[SpotifyPlaylist], None],
        on_download_all: Callable[[SpotifyPlaylist], None],
        **kwargs
    ):
        super().__init__(master, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"), **kwargs)
        self.playlist = playlist
        self.on_explore = on_explore
        self.on_download_all = on_download_all

        self.grid_columnconfigure(1, weight=1)

        # Image de pochette / Miniature
        self.cover_label = ctk.CTkLabel(
            self,
            text="🎵",
            width=64,
            height=64,
            corner_radius=8,
            fg_color=("#D0D0D0", "#2A2A2A"),
            font=ctk.CTkFont(size=24)
        )
        self.cover_label.grid(row=0, column=0, rowspan=2, padx=10, pady=10)

        # Informations textuelles
        self.title_label = ctk.CTkLabel(
            self,
            text=self.playlist.name,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.title_label.grid(row=0, column=1, sticky="w", padx=(5, 10), pady=(10, 0))

        sub_text = f"Par {self.playlist.owner} • {self.playlist.total_tracks} titres"
        self.subtitle_label = ctk.CTkLabel(
            self,
            text=sub_text,
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
            anchor="w"
        )
        self.subtitle_label.grid(row=1, column=1, sticky="w", padx=(5, 10), pady=(0, 10))

        # Boutons d'action
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=0, column=2, rowspan=2, padx=15, pady=10, sticky="e")

        self.explore_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔍 Explorer",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#D0D0D0", "#333333"),
            hover_color=("#B0B0B0", "#444444"),
            command=lambda: self.on_explore(self.playlist)
        )
        self.explore_btn.pack(side="left", padx=5)

        self.download_btn = ctk.CTkButton(
            self.btn_frame,
            text="⬇ Télécharger tout",
            width=130,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=lambda: self.on_download_all(self.playlist)
        )
        self.download_btn.pack(side="left", padx=5)

        # Chargement asynchrone de la miniature
        if self.playlist.cover_url:
            threading.Thread(target=self._load_cover_async, daemon=True).start()

    def _load_cover_async(self):
        url = self.playlist.cover_url
        if not url:
            return

        try:
            if url in IMAGE_CACHE:
                ctk_img = IMAGE_CACHE[url]
            else:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    pil_img = Image.open(io.BytesIO(resp.content)).resize((64, 64), Image.Resampling.LANCZOS)
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(64, 64))
                    IMAGE_CACHE[url] = ctk_img
                else:
                    return

            def _update():
                try:
                    self.cover_label.configure(image=ctk_img, text="")
                except Exception:
                    pass

            self.after(0, _update)
        except Exception:
            pass
