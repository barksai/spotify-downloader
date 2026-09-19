"""
Application Principale : Fenêtre CustomTkinter et Navigation par Onglets.
"""
import customtkinter as ctk

from ..config import config
from ..queue_manager import queue_manager
from .tabs.playlists_tab import PlaylistsTab
from .tabs.queue_tab import QueueTab
from .tabs.settings_tab import SettingsTab


class App(ctk.CTk):
    """Fenêtre principale de l'application Spotify MP3 Downloader."""

    def __init__(self):
        super().__init__()

        # Configuration de l'apparence
        theme_mode = config.get("theme", "dark")
        ctk.set_appearance_mode(theme_mode)
        ctk.set_default_color_theme("green")

        self.title("Spotify MP3 Downloader • 320 kbps & Organisateur Windows")
        self.geometry("1080x740")
        self.minsize(940, 600)

        # En-tête principal
        self._setup_header()

        # Onglets principaux
        self._setup_tabs()

        # Surveillance de la file d'attente pour le badge
        self._setup_queue_badge_listener()

    def _setup_header(self):
        self.header_frame = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color=("#D5D5D5", "#121212"))
        self.header_frame.pack(fill="x", side="top")

        # Titre et Logo
        self.logo_lbl = ctk.CTkLabel(
            self.header_frame,
            text="🎧 Spotify MP3 Downloader",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#1DB954"
        )
        self.logo_lbl.pack(side="left", padx=20, pady=10)

        self.badge_lbl = ctk.CTkLabel(
            self.header_frame,
            text="MP3 320 kbps • ID3v2 Tags • Pochette HD",
            font=ctk.CTkFont(size=11),
            text_color="gray60"
        )
        self.badge_lbl.pack(side="right", padx=20, pady=10)

    def _setup_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=10)

        # Création des onglets
        self.tab_playlists = self.tabview.add("🎵 Playlists & Recherche")
        self.tab_queue = self.tabview.add("📥 File de Téléchargement")
        self.tab_settings = self.tabview.add("⚙️ Paramètres")

        # Initialisation des vues associées
        self.playlists_view = PlaylistsTab(self.tab_playlists, on_switch_to_queue=self.switch_to_queue_tab)
        self.playlists_view.pack(fill="both", expand=True)

        self.queue_view = QueueTab(self.tab_queue)
        self.queue_view.pack(fill="both", expand=True)

        self.settings_view = SettingsTab(self.tab_settings)
        self.settings_view.pack(fill="both", expand=True)

    def _setup_queue_badge_listener(self):
        """Met à jour le titre de l'onglet file d'attente avec le nombre de tâches."""
        prev_stats_callback = queue_manager.on_queue_stats

        def _combined_stats(stats: dict):
            if prev_stats_callback:
                try:
                    prev_stats_callback(stats)
                except Exception:
                    pass

            total = stats.get("total", 0)
            in_prog = stats.get("in_progress", 0)
            queued = stats.get("queued", 0)
            active_count = in_prog + queued

            def _update_tab_title():
                try:
                    if active_count > 0:
                        self.tabview._segmented_button._buttons_dict["📥 File de Téléchargement"].configure(
                            text=f"📥 File ({active_count})"
                        )
                    else:
                        self.tabview._segmented_button._buttons_dict["📥 File de Téléchargement"].configure(
                            text="📥 File de Téléchargement"
                        )
                except Exception:
                    pass

            self.after(0, _update_tab_title)

        queue_manager.on_queue_stats = _combined_stats

    def switch_to_queue_tab(self):
        """Bascule automatiquement sur l'onglet de la file de téléchargement."""
        try:
            self.tabview.set("📥 File de Téléchargement")
        except Exception:
            pass
