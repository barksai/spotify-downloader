"""
Onglet 2 : File de Téléchargement, Suivi de Progression et Console de Logs.
"""
import os
import subprocess
import time
from typing import Dict
import customtkinter as ctk

from ...queue_manager import queue_manager, DownloadTask, TaskStatus
from ...config import config
from ..components.track_row import TrackRow


class QueueTab(ctk.CTkFrame):
    """Vue de gestion de la file de téléchargement."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.track_rows: Dict[str, TrackRow] = {}
        self.show_logs = False

        self._setup_ui()
        self._wire_events()

    def _setup_ui(self):
        # 1. Bannière de progression globale
        self.progress_banner = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#1E1E1E"))
        self.progress_banner.pack(fill="x", padx=15, pady=(15, 10))

        self.stats_lbl = ctk.CTkLabel(
            self.progress_banner,
            text="File d'attente vide",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        self.stats_lbl.pack(fill="x", padx=15, pady=(12, 4))

        self.global_progress = ctk.CTkProgressBar(self.progress_banner, height=10, corner_radius=5)
        self.global_progress.pack(fill="x", padx=15, pady=(0, 12))
        self.global_progress.set(0.0)
        self.global_progress.configure(progress_color="#1DB954")

        # 2. Barre d'outils et de contrôle
        self.ctrl_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.ctrl_bar.pack(fill="x", padx=15, pady=5)

        self.btn_toggle_run = ctk.CTkButton(
            self.ctrl_bar,
            text="⏸ Pause",
            width=95,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#D0D0D0", "#333333"),
            hover_color=("#B0B0B0", "#444444"),
            command=self._handle_toggle_pause
        )
        self.btn_toggle_run.pack(side="left", padx=(0, 6))

        self.btn_retry = ctk.CTkButton(
            self.ctrl_bar,
            text="🔄 Réessayer échecs",
            width=135,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#D0D0D0", "#333333"),
            hover_color=("#B0B0B0", "#444444"),
            command=queue_manager.retry_failed
        )
        self.btn_retry.pack(side="left", padx=6)

        self.btn_clear_done = ctk.CTkButton(
            self.ctrl_bar,
            text="🧹 Nettoyer terminés",
            width=135,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#D0D0D0", "#333333"),
            hover_color=("#B0B0B0", "#444444"),
            command=self._handle_clear_completed
        )
        self.btn_clear_done.pack(side="left", padx=6)

        self.btn_clear_all = ctk.CTkButton(
            self.ctrl_bar,
            text="🗑 Tout vider",
            width=100,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#EF5350", "#C62828"),
            hover_color=("#E53935", "#B71C1C"),
            command=self._handle_clear_all
        )
        self.btn_clear_all.pack(side="left", padx=6)

        self.btn_open_folder = ctk.CTkButton(
            self.ctrl_bar,
            text="📂 Dossier de sortie",
            width=130,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1DB954",
            hover_color="#1AA34A",
            text_color="#FFFFFF",
            command=self._open_download_dir
        )
        self.btn_open_folder.pack(side="right", padx=(6, 0))

        # 3. Liste scrollable des pistes en cours
        self.queue_container = ctk.CTkScrollableFrame(self, corner_radius=10, label_text="Tâches actives")
        self.queue_container.pack(fill="both", expand=True, padx=15, pady=5)

        self.empty_label = ctk.CTkLabel(
            self.queue_container,
            text="Aucun morceau dans la file d'attente.",
            font=ctk.CTkFont(size=13),
            text_color="gray50"
        )
        self.empty_label.pack(pady=40)

        # 4. Console de Logs escamotable
        self.log_section = ctk.CTkFrame(self, corner_radius=10, fg_color=("#E5E5E5", "#181818"))
        self.log_section.pack(fill="x", padx=15, pady=(5, 15))

        self.log_header = ctk.CTkFrame(self.log_section, fg_color="transparent")
        self.log_header.pack(fill="x", padx=10, pady=5)

        self.log_title = ctk.CTkLabel(
            self.log_header,
            text="📜 Journal des opérations (Logs en direct)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray70"
        )
        self.log_title.pack(side="left")

        self.log_textbox = ctk.CTkTextbox(
            self.log_section,
            height=90,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("#FFFFFF", "#121212")
        )
        self.log_textbox.pack(fill="x", padx=10, pady=(0, 8))

    def _wire_events(self):
        """Connecte les callbacks du gestionnaire de file d'attente."""
        queue_manager.on_task_updated = self._on_task_updated_gui
        queue_manager.on_queue_stats = self._on_stats_updated_gui
        queue_manager.on_log = self._on_log_gui

    def _on_task_updated_gui(self, task: DownloadTask):
        def _apply():
            if self.empty_label.winfo_exists():
                self.empty_label.pack_forget()

            if task.id in self.track_rows:
                row = self.track_rows[task.id]
                row.update_display(task)
            else:
                row = TrackRow(
                    self.queue_container,
                    task=task,
                    on_cancel=queue_manager.cancel_task
                )
                row.pack(fill="x", pady=3, padx=2)
                self.track_rows[task.id] = row

        self.after(0, _apply)

    def _on_stats_updated_gui(self, stats: dict):
        def _apply():
            total = stats.get("total", 0)
            completed = stats.get("completed", 0)
            skipped = stats.get("skipped", 0)
            failed = stats.get("failed", 0)
            in_prog = stats.get("in_progress", 0)
            pct = stats.get("overall_percent", 0.0)
            is_paused = stats.get("is_paused", False)

            done = completed + skipped
            if total == 0:
                self.stats_lbl.configure(text="File d'attente vide")
                self.global_progress.set(0.0)
                if not self.track_rows:
                    self.empty_label.pack(pady=40)
            else:
                status_str = f"Progression : {done} / {total} pistes ({pct:.1f}%) • En cours : {in_prog} • Échecs : {failed}"
                if is_paused:
                    status_str += " [EN PAUSE]"
                self.stats_lbl.configure(text=status_str)
                self.global_progress.set(pct / 100.0)

            if is_paused:
                self.btn_toggle_run.configure(text="▶ Reprendre", fg_color="#1DB954", hover_color="#1AA34A")
            else:
                self.btn_toggle_run.configure(text="⏸ Pause", fg_color=("#D0D0D0", "#333333"), hover_color=("#B0B0B0", "#444444"))

        self.after(0, _apply)

    def _on_log_gui(self, msg: str, level: str):
        def _apply():
            t_str = time.strftime("%H:%M:%S")
            line = f"[{t_str}] [{level}] {msg}\n"
            self.log_textbox.insert("end", line)
            self.log_textbox.see("end")

        self.after(0, _apply)

    def _handle_toggle_pause(self):
        if queue_manager.is_paused:
            queue_manager.resume()
        else:
            queue_manager.pause()

    def _handle_clear_completed(self):
        queue_manager.clear_completed()
        # Supprimer les widgets des tâches terminées
        remaining_ids = {t.id for t in queue_manager.tasks}
        for task_id in list(self.track_rows.keys()):
            if task_id not in remaining_ids:
                widget = self.track_rows.pop(task_id)
                widget.destroy()

    def _handle_clear_all(self):
        queue_manager.clear_all()
        for widget in self.track_rows.values():
            widget.destroy()
        self.track_rows.clear()
        self.empty_label.pack(pady=40)

    def _open_download_dir(self):
        target_dir = config.get("download_dir")
        if os.path.exists(target_dir):
            try:
                os.startfile(os.path.normpath(target_dir))
            except Exception as e:
                print(f"[QueueTab] Impossible d'ouvrir le dossier: {e}")
        else:
            os.makedirs(target_dir, exist_ok=True)
            os.startfile(os.path.normpath(target_dir))
