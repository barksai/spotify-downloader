"""
Onglet 3 : Paramètres de l'application, Moteur de Templates et Qualité Audio.
"""
import os
import webbrowser
from typing import Dict
import customtkinter as ctk
from tkinter import filedialog, messagebox

from ...config import config, PRESET_TEMPLATES
from ...file_manager import preview_template
from ...spotify_client import spotify_manager


class SettingsTab(ctk.CTkScrollableFrame):
    """Vue de configuration des réglages utilisateur."""

    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)

        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        # -------------------------------------------------------------
        # Section 1 : Organisation des Fichiers Windows & Templates
        # -------------------------------------------------------------
        sec1 = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        sec1.pack(fill="x", padx=15, pady=(15, 10))

        lbl_sec1 = ctk.CTkLabel(
            sec1,
            text="📁 Organisation des Fichiers Windows & Structure des Dossiers",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl_sec1.pack(fill="x", padx=15, pady=(15, 10))

        # Dossier de destination
        lbl_dir = ctk.CTkLabel(sec1, text="Dossier racine de téléchargement :", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_dir.pack(fill="x", padx=15, pady=(5, 2))

        dir_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        dir_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.entry_dir = ctk.CTkEntry(dir_frame, height=34, font=ctk.CTkFont(size=12))
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_browse = ctk.CTkButton(
            dir_frame,
            text="📂 Parcourir...",
            width=110,
            height=34,
            command=self._handle_browse_dir
        )
        self.btn_browse.pack(side="right")

        # Modèle de chemin (Template)
        lbl_template = ctk.CTkLabel(sec1, text="Modèle de chemin & nommage (Template) :", font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl_template.pack(fill="x", padx=15, pady=(5, 2))

        self.entry_template = ctk.CTkEntry(sec1, height=34, font=ctk.CTkFont(size=12))
        self.entry_template.pack(fill="x", padx=15, pady=(0, 6))
        self.entry_template.bind("<KeyRelease>", lambda e: self._update_preview())

        # Boutons d'insertion rapide de tags
        lbl_tags = ctk.CTkLabel(sec1, text="Cliquez pour insérer une variable :", font=ctk.CTkFont(size=11), text_color="gray60", anchor="w")
        lbl_tags.pack(fill="x", padx=15, pady=(0, 2))

        tags_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        tags_frame.pack(fill="x", padx=15, pady=(0, 10))

        tags = ["{Artist}", "{AlbumArtist}", "{Album}", "{TrackNumber}", "{Title}", "{Playlist}", "{Year}", "{DiscNumber}"]
        for tag in tags:
            btn_tag = ctk.CTkButton(
                tags_frame,
                text=f"+ {tag}",
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color=("gray75", "#2E2E2E"),
                hover_color=("gray65", "#3E3E3E"),
                command=lambda t=tag: self._insert_tag(t)
            )
            btn_tag.pack(side="left", padx=(0, 5), pady=2)

        # Préréglages rapides
        preset_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        preset_frame.pack(fill="x", padx=15, pady=(0, 10))

        lbl_preset = ctk.CTkLabel(preset_frame, text="Préréglages :", font=ctk.CTkFont(size=11, weight="bold"), anchor="w")
        lbl_preset.pack(side="left", padx=(0, 10))

        self.combo_presets = ctk.CTkOptionMenu(
            preset_frame,
            values=list(PRESET_TEMPLATES.keys()),
            width=260,
            height=30,
            command=self._handle_preset_change
        )
        self.combo_presets.pack(side="left")

        # Aperçu en temps réel
        preview_box = ctk.CTkFrame(sec1, corner_radius=6, fg_color=("#D8D8D8", "#121212"))
        preview_box.pack(fill="x", padx=15, pady=(5, 15))

        lbl_prev_title = ctk.CTkLabel(preview_box, text="Aperçu du chemin Windows résultant :", font=ctk.CTkFont(size=11, weight="bold"), text_color="#1DB954", anchor="w")
        lbl_prev_title.pack(fill="x", padx=10, pady=(6, 2))

        self.lbl_preview_path = ctk.CTkLabel(
            preview_box,
            text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="gray80",
            anchor="w",
            wraplength=700
        )
        self.lbl_preview_path.pack(fill="x", padx=10, pady=(0, 8))

        # Gestion des doublons
        dup_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        dup_frame.pack(fill="x", padx=15, pady=(0, 15))

        lbl_dup = ctk.CTkLabel(dup_frame, text="En cas de fichier déjà existant :", font=ctk.CTkFont(size=12), anchor="w")
        lbl_dup.pack(side="left", padx=(0, 10))

        self.combo_dup = ctk.CTkOptionMenu(
            dup_frame,
            values=["Ignorer (recommandé)", "Écraser", "Renommer automatiquement"],
            width=220,
            height=30
        )
        self.combo_dup.pack(side="left")

        # -------------------------------------------------------------
        # Section 2 : Qualité Audio & Performance Multithread
        # -------------------------------------------------------------
        sec2 = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        sec2.pack(fill="x", padx=15, pady=10)

        lbl_sec2 = ctk.CTkLabel(
            sec2,
            text="🎧 Qualité Audio MP3 & Téléchargements Parallèles",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl_sec2.pack(fill="x", padx=15, pady=(15, 10))

        # Bitrate MP3
        bitrate_frame = ctk.CTkFrame(sec2, fg_color="transparent")
        bitrate_frame.pack(fill="x", padx=15, pady=(0, 10))

        lbl_bitrate = ctk.CTkLabel(bitrate_frame, text="Débit Audio (Bitrate) :", font=ctk.CTkFont(size=12), anchor="w")
        lbl_bitrate.pack(side="left", padx=(0, 10))

        self.bitrate_options = {
            "320 kbps (Qualité Maximale CBR)": "320k",
            "256 kbps (Très haute qualité)": "256k",
            "192 kbps (Qualité standard)": "192k",
            "128 kbps (Économie d'espace)": "128k",
            "V0 (VBR Haute Qualité)": "V0",
        }
        self.combo_bitrate = ctk.CTkOptionMenu(
            bitrate_frame,
            values=list(self.bitrate_options.keys()),
            width=280,
            height=30
        )
        self.combo_bitrate.pack(side="left")

        # Threads simultanés
        threads_frame = ctk.CTkFrame(sec2, fg_color="transparent")
        threads_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.lbl_threads = ctk.CTkLabel(threads_frame, text="Téléchargements simultanés (3) :", font=ctk.CTkFont(size=12), anchor="w")
        self.lbl_threads.pack(side="left", padx=(0, 10))

        self.slider_threads = ctk.CTkSlider(
            threads_frame,
            from_=1,
            to=6,
            number_of_steps=5,
            width=180,
            command=self._handle_threads_slider
        )
        self.slider_threads.pack(side="left")

        # -------------------------------------------------------------
        # Section 3 : Identifiants Spotify API
        # -------------------------------------------------------------
        sec3 = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        sec3.pack(fill="x", padx=15, pady=10)

        lbl_sec3 = ctk.CTkLabel(
            sec3,
            text="🔑 Identifiants Spotify Developer Dashboard",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl_sec3.pack(fill="x", padx=15, pady=(15, 5))

        lbl_sec3_sub = ctk.CTkLabel(
            sec3,
            text="Pour obtenir votre Client ID gratuit en 1 minute : Créez une application sur developer.spotify.com, ajoutez l'URI de redirection ci-dessous, puis collez votre Client ID.",
            font=ctk.CTkFont(size=11),
            text_color="gray65",
            anchor="w",
            wraplength=700
        )
        lbl_sec3_sub.pack(fill="x", padx=15, pady=(0, 8))

        # Bouton lien rapide vers dashboard
        f_dash = ctk.CTkFrame(sec3, fg_color="transparent")
        f_dash.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkButton(
            f_dash,
            text="🔗 Ouvrir developer.spotify.com/dashboard",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: webbrowser.open("https://developer.spotify.com/dashboard")
        ).pack(side="left")

        # Redirect URI
        f_red = ctk.CTkFrame(sec3, fg_color="transparent")
        f_red.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(f_red, text="Redirect URI :", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        
        red_uri_str = f"http://127.0.0.1:{config.get('redirect_port', 8888)}/callback"
        entry_red = ctk.CTkEntry(f_red, height=30, font=ctk.CTkFont(family="Consolas", size=11))
        entry_red.insert(0, red_uri_str)
        entry_red.configure(state="readonly")
        entry_red.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _copy_red():
            self.clipboard_clear()
            self.clipboard_append(red_uri_str)
            messagebox.showinfo("Copié", f"URI copiée : {red_uri_str}")

        ctk.CTkButton(f_red, text="📋 Copier", width=70, height=30, font=ctk.CTkFont(size=11), command=_copy_red).pack(side="right")

        # Client ID
        f_cid = ctk.CTkFrame(sec3, fg_color="transparent")
        f_cid.pack(fill="x", padx=15, pady=(0, 6))
        ctk.CTkLabel(f_cid, text="Client ID :", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.entry_cid = ctk.CTkEntry(f_cid, height=32, font=ctk.CTkFont(size=12))
        self.entry_cid.pack(side="left", fill="x", expand=True)

        # Client Secret
        f_csec = ctk.CTkFrame(sec3, fg_color="transparent")
        f_csec.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(f_csec, text="Client Secret :", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.entry_csec = ctk.CTkEntry(f_csec, height=32, show="•", font=ctk.CTkFont(size=12))
        self.entry_csec.pack(side="left", fill="x", expand=True)

        # Boutons API
        f_api_btns = ctk.CTkFrame(sec3, fg_color="transparent")
        f_api_btns.pack(fill="x", padx=15, pady=(0, 15))

        self.btn_test_api = ctk.CTkButton(
            f_api_btns,
            text="⚡ Tester les identifiants Client Secret",
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#D0D0D0", "#333333"),
            hover_color=("#B0B0B0", "#444444"),
            command=self._handle_test_api
        )
        self.btn_test_api.pack(side="left", padx=(0, 10))

        # -------------------------------------------------------------
        # Bouton Enregistrer Final
        # -------------------------------------------------------------
        btn_save_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_save_frame.pack(fill="x", padx=15, pady=(15, 25))

        self.btn_save = ctk.CTkButton(
            btn_save_frame,
            text="💾 Enregistrer les paramètres",
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=self._save_values
        )
        self.btn_save.pack(side="left", padx=(0, 15))

        self.status_save_lbl = ctk.CTkLabel(
            btn_save_frame,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1DB954"
        )
        self.status_save_lbl.pack(side="left")

    def _load_values(self):
        self.entry_dir.insert(0, config.get("download_dir"))
        self.entry_template.insert(0, config.get("filename_template"))

        # Duplicata
        dup_val = config.get("on_duplicate", "skip")
        dup_map = {"skip": "Ignorer (recommandé)", "overwrite": "Écraser", "rename": "Renommer automatiquement"}
        self.combo_dup.set(dup_map.get(dup_val, "Ignorer (recommandé)"))

        # Bitrate
        q_val = config.get("audio_quality", "320k")
        for label, val in self.bitrate_options.items():
            if val == q_val:
                self.combo_bitrate.set(label)
                break

        # Threads
        threads = int(config.get("max_threads", 3))
        self.slider_threads.set(threads)
        self.lbl_threads.configure(text=f"Téléchargements simultanés ({threads}) :")

        # Spotify API
        cid = config.get("spotify_client_id", "")
        if cid:
            self.entry_cid.insert(0, cid)
        csec = config.get("spotify_client_secret", "")
        if csec:
            self.entry_csec.insert(0, csec)

        self._update_preview()

    def _save_values(self):
        d_dir = self.entry_dir.get().strip()
        tmpl = self.entry_template.get().strip()

        if not d_dir:
            messagebox.showwarning("Champ obligatoire", "Veuillez spécifier un dossier de téléchargement valide.")
            return

        if not tmpl:
            tmpl = "{Artist}/{Album}/{TrackNumber} - {Title}.mp3"

        config.set("download_dir", d_dir, auto_save=False)
        config.set("filename_template", tmpl, auto_save=False)

        # Doublons
        dup_rev = {"Ignorer (recommandé)": "skip", "Écraser": "overwrite", "Renommer automatiquement": "rename"}
        config.set("on_duplicate", dup_rev.get(self.combo_dup.get(), "skip"), auto_save=False)

        # Bitrate
        bitrate_code = self.bitrate_options.get(self.combo_bitrate.get(), "320k")
        config.set("audio_quality", bitrate_code, auto_save=False)

        # Threads
        threads = int(self.slider_threads.get())
        config.set("max_threads", threads, auto_save=False)

        # Spotify Credentials
        config.set("spotify_client_id", self.entry_cid.get().strip(), auto_save=False)
        config.set("spotify_client_secret", self.entry_csec.get().strip(), auto_save=False)

        if config.save():
            self.status_save_lbl.configure(text="✅ Paramètres enregistrés avec succès !")
            self.after(3000, lambda: self.status_save_lbl.configure(text=""))
        else:
            messagebox.showerror("Erreur", "Impossible de sauvegarder la configuration.")

    def _handle_browse_dir(self):
        selected = filedialog.askdirectory(initialdir=self.entry_dir.get() or os.path.expanduser("~"))
        if selected:
            self.entry_dir.delete(0, "end")
            self.entry_dir.insert(0, selected)
            self._update_preview()

    def _insert_tag(self, tag: str):
        self.entry_template.insert("insert", tag)
        self._update_preview()

    def _handle_preset_change(self, choice: str):
        if choice in PRESET_TEMPLATES:
            self.entry_template.delete(0, "end")
            self.entry_template.insert(0, PRESET_TEMPLATES[choice])
            self._update_preview()

    def _update_preview(self):
        tmpl = self.entry_template.get().strip()
        d_dir = self.entry_dir.get().strip() or "D:\\Musique"
        rel_preview = preview_template(tmpl)
        full_preview = os.path.normpath(os.path.join(d_dir, rel_preview))
        self.lbl_preview_path.configure(text=full_preview)

    def _handle_threads_slider(self, val):
        threads = int(val)
        self.lbl_threads.configure(text=f"Téléchargements simultanés ({threads}) :")

    def _handle_test_api(self):
        cid = self.entry_cid.get().strip()
        csec = self.entry_csec.get().strip()
        if not cid or not csec:
            messagebox.showinfo("Clés requises", "Veuillez renseigner un Client ID et un Client Secret pour tester le mode Développeur.")
            return

        success = spotify_manager.login_client_credentials(cid, csec)
        if success:
            messagebox.showinfo("Succès API", "Connexion API réussie avec succès !")
        else:
            messagebox.showerror("Échec API", "Identifiants Spotify invalides. Vérifiez votre configuration sur developer.spotify.com.")
