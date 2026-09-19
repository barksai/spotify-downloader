"""
Onglet 1 : Explorateur & Recherche d'Albums et de Playlists.
Prend en charge la recherche d'albums sans clé API et le téléchargement complet en 1 clic.
"""
import threading
from typing import List, Dict, Callable, Optional
import customtkinter as ctk
from tkinter import messagebox

from ...spotify_client import spotify_manager, SpotifyPlaylist, SpotifyTrack
from ...album_search import search_albums, fetch_album_tracks
from ...queue_manager import queue_manager
from ...config import config
from ..components.playlist_card import PlaylistCard


class TrackSelectionDialog(ctk.CTkToplevel):
    """Fenêtre modale permettant d'explorer et sélectionner des pistes individuelles."""

    def __init__(self, master, playlist: SpotifyPlaylist, on_add_tracks: Callable[[List[SpotifyTrack], str], None]):
        super().__init__(master)
        self.playlist = playlist
        self.on_add_tracks = on_add_tracks
        self.track_vars: Dict[str, ctk.BooleanVar] = {}

        self.title(f"Explorer : {playlist.name} ({playlist.total_tracks} titres)")
        self.geometry("700x600")
        self.minsize(580, 420)
        self.grab_set()

        self._setup_ui()

    def _setup_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text=self.playlist.name,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        title_lbl.pack(fill="x")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text=f"{self.playlist.total_tracks} titres • {self.playlist.owner}",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
            anchor="w"
        )
        sub_lbl.pack(fill="x", pady=(2, 0))

        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=20, pady=5)

        self.btn_select_all = ctk.CTkButton(
            action_bar,
            text="Tout cocher",
            width=100,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#333333"),
            hover_color=("gray65", "#444444"),
            command=lambda: self._set_all_checkboxes(True)
        )
        self.btn_select_all.pack(side="left", padx=(0, 8))

        self.btn_deselect_all = ctk.CTkButton(
            action_bar,
            text="Tout décocher",
            width=100,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#333333"),
            hover_color=("gray65", "#444444"),
            command=lambda: self._set_all_checkboxes(False)
        )
        self.btn_deselect_all.pack(side="left")

        self.count_lbl = ctk.CTkLabel(
            action_bar,
            text=f"{len(self.playlist.tracks)} / {len(self.playlist.tracks)} sélectionnés",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1DB954"
        )
        self.count_lbl.pack(side="right")

        self.scroll_tracks = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.scroll_tracks.pack(fill="both", expand=True, padx=20, pady=10)

        for track in self.playlist.tracks:
            var = ctk.BooleanVar(value=True)
            self.track_vars[track.id] = var

            row = ctk.CTkFrame(self.scroll_tracks, fg_color="transparent")
            row.pack(fill="x", pady=2)

            cb = ctk.CTkCheckBox(
                row,
                text=f"{track.track_number:02d}. {track.artist} - {track.title}",
                variable=var,
                font=ctk.CTkFont(size=12),
                command=self._update_selected_count
            )
            cb.pack(side="left", fill="x", expand=True, padx=5)

            dur_lbl = ctk.CTkLabel(
                row,
                text=track.duration_str,
                font=ctk.CTkFont(size=11),
                text_color="gray50"
            )
            dur_lbl.pack(side="right", padx=10)

        bot_bar = ctk.CTkFrame(self, fg_color="transparent")
        bot_bar.pack(fill="x", padx=20, pady=(0, 15))

        self.add_btn = ctk.CTkButton(
            bot_bar,
            text="➕ Ajouter la sélection à la file d'attente",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=self._confirm_add
        )
        self.add_btn.pack(fill="x")

    def _set_all_checkboxes(self, checked: bool):
        for var in self.track_vars.values():
            var.set(checked)
        self._update_selected_count()

    def _update_selected_count(self):
        selected_count = sum(1 for v in self.track_vars.values() if v.get())
        self.count_lbl.configure(text=f"{selected_count} / {len(self.playlist.tracks)} sélectionnés")

    def _confirm_add(self):
        selected_tracks = [t for t in self.playlist.tracks if self.track_vars.get(t.id, ctk.BooleanVar(value=False)).get()]
        if not selected_tracks:
            messagebox.showwarning("Aucune piste", "Veuillez sélectionner au moins une piste.")
            return

        self.on_add_tracks(selected_tracks, self.playlist.name)
        self.destroy()


class PlaylistsTab(ctk.CTkFrame):
    """Vue principale avec Recherche d'Albums et Liens Spotify."""

    def __init__(self, master, on_switch_to_queue: Optional[Callable] = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_switch_to_queue = on_switch_to_queue
        self.saved_playlists: List[SpotifyPlaylist] = []
        self.album_search_results: List[SpotifyPlaylist] = []

        self._setup_ui()
        self._load_saved_playlists()

    def _setup_ui(self):
        # 1. Sélecteur de Mode (Recherche d'Album / Lien Spotify)
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(fill="x", padx=15, pady=(12, 6))

        self.mode_selector = ctk.CTkSegmentedButton(
            mode_frame,
            values=["💿 Rechercher un Album", "🔗 Lien direct Spotify"],
            font=ctk.CTkFont(size=13, weight="bold"),
            selected_color="#1DB954",
            selected_hover_color="#1AA34A",
            command=self._on_mode_change
        )
        self.mode_selector.pack(side="left")
        self.mode_selector.set("💿 Rechercher un Album")

        # 2. Section Mode Recherche d'Album
        self.album_search_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        self.album_search_frame.pack(fill="x", padx=15, pady=5)

        self.album_entry = ctk.CTkEntry(
            self.album_search_frame,
            placeholder_text="Tapez le nom d'un album ou d'un artiste (ex: Daft Punk Discovery, Nirvana Nevermind, Jul Décennie)...",
            height=42,
            font=ctk.CTkFont(size=13)
        )
        self.album_entry.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=12)
        self.album_entry.bind("<Return>", lambda e: self._handle_album_search())

        self.album_search_btn = ctk.CTkButton(
            self.album_search_frame,
            text="🔍 Rechercher l'album",
            width=170,
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=self._handle_album_search
        )
        self.album_search_btn.pack(side="left", padx=(0, 15), pady=12)

        # 3. Section Mode Lien Spotify (alternative)
        self.url_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        # Non packée par défaut, affichée selon le segmented button

        self.url_entry = ctk.CTkEntry(
            self.url_frame,
            placeholder_text="Collez un lien Spotify : https://open.spotify.com/playlist/... ou album/... ou track/...",
            height=42,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=12)
        self.url_entry.bind("<Return>", lambda e: self._handle_load_url())

        self.load_url_btn = ctk.CTkButton(
            self.url_frame,
            text="📥 Charger & Explorer",
            width=160,
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=self._handle_load_url
        )
        self.load_url_btn.pack(side="left", padx=(0, 15), pady=12)

        # 4. Barre de titre et filtre
        self.actions_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.actions_bar.pack(fill="x", padx=15, pady=(8, 4))

        self.lbl_section_title = ctk.CTkLabel(
            self.actions_bar,
            text="💿 Résultats de recherche d'albums :",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.lbl_section_title.pack(side="left")

        self.search_filter_entry = ctk.CTkEntry(
            self.actions_bar,
            placeholder_text="🔍 Filtrer l'affichage...",
            width=200,
            height=30,
            font=ctk.CTkFont(size=12)
        )
        self.search_filter_entry.pack(side="right")
        self.search_filter_entry.bind("<KeyRelease>", lambda e: self._filter_displayed_items())

        # 5. Conteneur scrollable des cartes (Albums recherchés ou Playlists)
        self.scroll_container = ctk.CTkScrollableFrame(self, corner_radius=10)
        self.scroll_container.pack(fill="both", expand=True, padx=15, pady=(4, 15))

        self._show_search_placeholder()

    def _on_mode_change(self, mode: str):
        if mode == "💿 Rechercher un Album":
            self.url_frame.pack_forget()
            self.album_search_frame.pack(fill="x", padx=15, pady=5, after=self.mode_selector.master)
            self.lbl_section_title.configure(text="💿 Résultats de recherche d'albums :")
            if self.album_search_results:
                self._render_items(self.album_search_results)
            else:
                self._show_search_placeholder()
        else:
            self.album_search_frame.pack_forget()
            self.url_frame.pack(fill="x", padx=15, pady=5, after=self.mode_selector.master)
            self.lbl_section_title.configure(text="📚 Mes Playlists et Albums mémorisés :")
            self._render_items(self.saved_playlists)

    def _show_search_placeholder(self):
        for w in self.scroll_container.winfo_children():
            w.destroy()
        lbl = ctk.CTkLabel(
            self.scroll_container,
            text="Saisissez un nom d'album ou d'artiste ci-dessus (ex: Discovery Daft Punk, Nevermind Nirvana, Thriller...)\npour explorer les pistes ou télécharger l'album complet en MP3 320 kbps !",
            font=ctk.CTkFont(size=13),
            text_color="gray55"
        )
        lbl.pack(pady=50)

    # -------------------------------------------------------------
    # Logique de recherche d'albums
    # -------------------------------------------------------------
    def _handle_album_search(self):
        query = self.album_entry.get().strip()
        if not query:
            messagebox.showwarning("Champ vide", "Veuillez saisir un nom d'album ou d'artiste.")
            return

        # Si l'utilisateur colle une URL Spotify dans la recherche d'album, la traiter automatiquement
        if query.startswith("http://") or query.startswith("https://") or query.startswith("spotify:"):
            self._handle_load_url_custom(query)
            return

        self.album_search_btn.configure(state="disabled", text="⏳ Recherche...")

        def _search():
            try:
                results = search_albums(query, limit=15)
                self.album_search_results = results
                def _done():
                    self.album_search_btn.configure(state="normal", text="🔍 Rechercher l'album")
                    if not results:
                        for w in self.scroll_container.winfo_children():
                            w.destroy()
                        lbl = ctk.CTkLabel(
                            self.scroll_container,
                            text=f"Aucun album trouvé pour '{query}'. Essayez avec d'autres mots-clés.",
                            font=ctk.CTkFont(size=13),
                            text_color="gray50"
                        )
                        lbl.pack(pady=40)
                    else:
                        self._render_items(results)
                self.after(0, _done)
            except Exception as e:
                def _err():
                    self.album_search_btn.configure(state="normal", text="🔍 Rechercher l'album")
                    messagebox.showerror("Erreur de recherche", f"La recherche a échoué: {e}")
                self.after(0, _err)

        threading.Thread(target=_search, daemon=True).start()

    # -------------------------------------------------------------
    # Rendu des cartes (Albums & Playlists)
    # -------------------------------------------------------------
    def _render_items(self, items: List[SpotifyPlaylist]):
        for widget in self.scroll_container.winfo_children():
            widget.destroy()

        if not items:
            lbl = ctk.CTkLabel(
                self.scroll_container,
                text="Aucun élément à afficher.",
                text_color="gray50",
                font=ctk.CTkFont(size=13)
            )
            lbl.pack(pady=40)
            return

        for p in items:
            card = PlaylistCard(
                self.scroll_container,
                playlist=p,
                on_explore=self._explore_item,
                on_download_all=self._download_full_item
            )
            card.pack(fill="x", pady=4, padx=5)

    def _filter_displayed_items(self):
        query = self.search_filter_entry.get().strip().lower()
        current_list = self.album_search_results if self.mode_selector.get() == "💿 Rechercher un Album" else self.saved_playlists
        if not query:
            self._render_items(current_list)
            return
        filtered = [p for p in current_list if query in p.name.lower() or query in p.owner.lower()]
        self._render_items(filtered)

    # -------------------------------------------------------------
    # Actions sur les albums et playlists
    # -------------------------------------------------------------
    def _explore_item(self, playlist: SpotifyPlaylist):
        """Ouvre la boîte de dialogue de sélection des pistes d'un album ou playlist."""
        # Si c'est un album issu de la recherche
        if playlist.id.startswith("deezer_") or playlist.id.startswith("itunes_"):
            def _fetch():
                try:
                    full_alb = fetch_album_tracks(playlist.id, playlist.name, playlist.owner, playlist.cover_url)
                    self.after(0, lambda: TrackSelectionDialog(self, full_alb, self._add_tracks_to_queue))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Erreur", f"Impossible de charger les pistes: {e}"))
            threading.Thread(target=_fetch, daemon=True).start()
        elif not playlist.tracks:
            def _fetch_sp():
                try:
                    url = f"https://open.spotify.com/playlist/{playlist.id}"
                    full_p = spotify_manager.fetch_by_url(url)
                    self.after(0, lambda: TrackSelectionDialog(self, full_p, self._add_tracks_to_queue))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Erreur", f"Échec du chargement: {e}"))
            threading.Thread(target=_fetch_sp, daemon=True).start()
        else:
            TrackSelectionDialog(self, playlist, self._add_tracks_to_queue)

    def _download_full_item(self, playlist: SpotifyPlaylist):
        """Télécharge directement l'intégralité d'un album ou d'une playlist."""
        if playlist.id.startswith("deezer_") or playlist.id.startswith("itunes_"):
            def _fetch_and_dl():
                try:
                    full_alb = fetch_album_tracks(playlist.id, playlist.name, playlist.owner, playlist.cover_url)
                    self.after(0, lambda: self._add_tracks_to_queue(full_alb.tracks, full_alb.name))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Erreur", f"Impossible de télécharger l'album: {e}"))
            threading.Thread(target=_fetch_and_dl, daemon=True).start()
        elif not playlist.tracks:
            def _fetch():
                try:
                    url = f"https://open.spotify.com/playlist/{playlist.id}"
                    full_p = spotify_manager.fetch_by_url(url)
                    self.after(0, lambda: self._add_tracks_to_queue(full_p.tracks, full_p.name))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Erreur", f"Échec du chargement: {e}"))
            threading.Thread(target=_fetch, daemon=True).start()
        else:
            self._add_tracks_to_queue(playlist.tracks, playlist.name)

    def _add_tracks_to_queue(self, tracks: List[SpotifyTrack], playlist_name: str):
        added = queue_manager.add_tracks(tracks, playlist_name)
        queue_manager.start()
        if self.on_switch_to_queue:
            self.on_switch_to_queue()

    # -------------------------------------------------------------
    # Mode Lien direct Spotify
    # -------------------------------------------------------------
    def _load_saved_playlists(self):
        self.saved_playlists = spotify_manager.fetch_user_playlists()

    def _handle_load_url(self):
        url = self.url_entry.get().strip()
        self._handle_load_url_custom(url)

    def _handle_load_url_custom(self, url: str):
        if not url:
            messagebox.showwarning("Champ vide", "Veuillez coller un lien Spotify.")
            return

        self.load_url_btn.configure(state="disabled", text="⏳ Chargement...")

        def _fetch():
            try:
                playlist_obj = spotify_manager.fetch_by_url(url)
                def _done():
                    self.url_entry.delete(0, "end")
                    self._load_saved_playlists()
                    if self.mode_selector.get() == "🔗 Lien direct Spotify":
                        self._render_items(self.saved_playlists)
                    self._explore_item(playlist_obj)
                self.after(0, _done)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur de chargement", f"Impossible de charger ce lien Spotify :\n\n{e}"))
            finally:
                self.after(0, lambda: self.load_url_btn.configure(state="normal", text="📥 Charger & Explorer"))

        threading.Thread(target=_fetch, daemon=True).start()
