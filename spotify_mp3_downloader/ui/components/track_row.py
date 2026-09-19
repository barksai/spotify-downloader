"""
Composant visuel représentant une ligne de piste dans la file de téléchargement.
"""
import os
import subprocess
from typing import Callable, Optional
import customtkinter as ctk

from ...queue_manager import DownloadTask, TaskStatus


class TrackRow(ctk.CTkFrame):
    """Ligne de tâche avec progression et statut interactif."""

    STATUS_COLORS = {
        TaskStatus.QUEUED: ("#555555", "gray40"),
        TaskStatus.SEARCHING: ("#F57C00", "#FFB74D"),
        TaskStatus.DOWNLOADING: ("#1976D2", "#42A5F5"),
        TaskStatus.CONVERTING: ("#7B1FA2", "#BA68C8"),
        TaskStatus.TAGGING: ("#00897B", "#26A69A"),
        TaskStatus.COMPLETED: ("#2E7D32", "#4CAF50"),
        TaskStatus.SKIPPED: ("#455A64", "#78909C"),
        TaskStatus.FAILED: ("#C62828", "#EF5350"),
        TaskStatus.CANCELLED: ("#424242", "#757575"),
    }

    def __init__(
        self,
        master,
        task: DownloadTask,
        on_cancel: Callable[[str], None],
        **kwargs
    ):
        super().__init__(master, corner_radius=8, fg_color=("#ECECEC", "#1C1C1C"), **kwargs)
        self.task = task
        self.on_cancel = on_cancel

        self.grid_columnconfigure(0, weight=1)

        # Ligne supérieure : Titre et Bouton
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=12, pady=(8, 2))

        self.title_label = ctk.CTkLabel(
            self.top_frame,
            text=f"{self.task.track.artist} - {self.task.track.title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        self.btn_action = ctk.CTkButton(
            self.top_frame,
            text="✕",
            width=28,
            height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray80", "#2E2E2E"),
            hover_color=("#EF5350", "#C62828"),
            command=self._handle_action_btn
        )
        self.btn_action.pack(side="right", padx=(5, 0))

        # Ligne intermédiaire : Statut détaillé et pourcentage
        self.mid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.mid_frame.pack(fill="x", padx=12, pady=(0, 4))

        self.status_label = ctk.CTkLabel(
            self.mid_frame,
            text=self.task.status_message,
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w"
        )
        self.status_label.pack(side="left")

        self.pct_label = ctk.CTkLabel(
            self.mid_frame,
            text=f"{self.task.progress:.0f}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray70",
            anchor="e"
        )
        self.pct_label.pack(side="right")

        # Ligne inférieure : Barre de progression
        self.progress_bar = ctk.CTkProgressBar(self, height=6, corner_radius=3)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 8))
        self.progress_bar.set(self.task.progress / 100.0)

        self.update_display(self.task)

    def update_display(self, task: DownloadTask):
        """Met à jour l'affichage en direct."""
        self.task = task
        self.status_label.configure(text=task.status_message)
        self.pct_label.configure(text=f"{task.progress:.0f}%")
        self.progress_bar.set(task.progress / 100.0)

        # Couleurs de la barre et statut
        color = self.STATUS_COLORS.get(task.status, ("#1DB954", "#1DB954"))
        self.progress_bar.configure(progress_color=color[1])

        if task.status == TaskStatus.COMPLETED:
            self.btn_action.configure(text="📂", hover_color="#2E7D32")
        elif task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.btn_action.configure(text="✕", hover_color="#C62828")

    def _handle_action_btn(self):
        if self.task.status == TaskStatus.COMPLETED and self.task.target_path and os.path.exists(self.task.target_path):
            # Ouvrir le fichier dans l'explorateur Windows
            try:
                subprocess.Popen(f'explorer /select,"{os.path.normpath(self.task.target_path)}"')
            except Exception as e:
                print(f"[TrackRow] Erreur ouverture explorateur: {e}")
        else:
            self.on_cancel(self.task.id)
