"""
Spotify MP3 Downloader - Multithreaded Queue & Task Manager
Gère l'ordonnancement parallèle des téléchargements, la répartition des threads,
le suivi de progression en temps réel et les callbacks pour l'interface graphique.
"""
import threading
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Dict, Optional, Callable, Any

from .spotify_client import SpotifyTrack
from .downloader import downloader
from .file_manager import resolve_destination_path
from .config import config


class TaskStatus(str, Enum):
    QUEUED = "En attente"
    SEARCHING = "Recherche..."
    DOWNLOADING = "Téléchargement..."
    CONVERTING = "Conversion MP3..."
    TAGGING = "Tagging ID3..."
    COMPLETED = "Terminé"
    FAILED = "Échec"
    SKIPPED = "Déjà téléchargé (ignoré)"
    CANCELLED = "Annulé"


@dataclass
class DownloadTask:
    id: str
    track: SpotifyTrack
    playlist_name: str
    status: TaskStatus = TaskStatus.QUEUED
    status_message: str = "En attente dans la file"
    progress: float = 0.0
    target_path: str = ""
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None


class QueueManager:
    """Gestionnaire de file d'attente multithreadée."""

    def __init__(self):
        self.tasks: List[DownloadTask] = []
        self._task_map: Dict[str, DownloadTask] = {}
        self._lock = threading.RLock()
        
        self.executor: Optional[ThreadPoolExecutor] = None
        self._futures: Dict[str, Future] = {}
        
        self.is_running = False
        self.is_paused = False
        
        # Callbacks pour la GUI
        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_queue_stats: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None

    def _log(self, msg: str, level: str = "INFO"):
        if self.on_log:
            try:
                self.on_log(msg, level)
            except Exception:
                pass
        else:
            print(f"[{level}] {msg}")

    def _notify_task(self, task: DownloadTask):
        if self.on_task_updated:
            try:
                self.on_task_updated(task)
            except Exception:
                pass
        self._notify_stats()

    def _notify_stats(self):
        if self.on_queue_stats:
            try:
                self.on_queue_stats(self.get_stats())
            except Exception:
                pass

    def add_tracks(self, tracks: List[SpotifyTrack], playlist_name: str = "Playlist") -> int:
        """Ajoute une liste de pistes Spotify à la file d'attente."""
        added_count = 0
        with self._lock:
            for track in tracks:
                # Éviter les doublons stricts en attente dans la file courante
                if any(t.track.id == track.id and t.status in (TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.SEARCHING) for t in self.tasks):
                    continue

                task_id = str(uuid.uuid4())[:8]
                task = DownloadTask(
                    id=task_id,
                    track=track,
                    playlist_name=playlist_name,
                    status=TaskStatus.QUEUED,
                    status_message="En attente",
                    progress=0.0
                )
                self.tasks.append(task)
                self._task_map[task_id] = task
                added_count += 1
                self._notify_task(task)

        if added_count > 0:
            self._log(f"Ajout de {added_count} morceau(x) à la file d'attente ({playlist_name}).", "INFO")
        return added_count

    def start(self):
        """Démarre le traitement de la file de téléchargement."""
        with self._lock:
            if self.is_running and not self.is_paused:
                return

            self.is_running = True
            self.is_paused = False
            max_workers = int(config.get("max_threads", 3))
            
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SpotifyWorker")

        self._log(f"Démarrage du traitement de la file ({config.get('max_threads', 3)} threads simultanés).", "INFO")
        
        # Lancer les tâches en attente dans un thread de supervision
        threading.Thread(target=self._process_queue_loop, daemon=True).start()

    def pause(self):
        """Met en pause la file d'attente."""
        with self._lock:
            self.is_paused = True
        self._log("Mise en pause de la file d'attente.", "WARNING")
        self._notify_stats()

    def resume(self):
        """Reprend le traitement de la file d'attente."""
        with self._lock:
            self.is_paused = False
        self._log("Reprise de la file d'attente.", "INFO")
        self.start()

    def _process_queue_loop(self):
        """Boucle de soumission des tâches aux workers."""
        while self.is_running:
            if self.is_paused:
                time.sleep(0.5)
                continue

            with self._lock:
                queued_tasks = [t for t in self.tasks if t.status == TaskStatus.QUEUED]
                if not queued_tasks:
                    # Vérifier s'il reste des tâches en cours d'exécution
                    running_tasks = [t for t in self.tasks if t.status in (TaskStatus.SEARCHING, TaskStatus.DOWNLOADING, TaskStatus.CONVERTING, TaskStatus.TAGGING)]
                    if not running_tasks:
                        self.is_running = False
                        self._log("Toutes les tâches de la file sont terminées !", "SUCCESS")
                        self._notify_stats()
                        break
                    time.sleep(0.5)
                    continue

                task = queued_tasks[0]
                task.status = TaskStatus.SEARCHING
                task.status_message = "Initialisation..."
                self._notify_task(task)

                if self.executor:
                    future = self.executor.submit(self._worker_execute_task, task)
                    self._futures[task.id] = future

            time.sleep(0.2)

    def _worker_execute_task(self, task: DownloadTask):
        """Exécution du pipeline de téléchargement pour une piste par un worker thread."""
        try:
            download_dir = config.get("download_dir")
            template = config.get("filename_template")
            audio_quality = config.get("audio_quality", "320k")
            on_duplicate = config.get("on_duplicate", "skip")

            # 1. Calcul du chemin cible
            meta_dict = {
                "title": task.track.title,
                "artist": task.track.artist,
                "artists": task.track.artists,
                "album": task.track.album,
                "album_artist": task.track.album_artist,
                "year": task.track.year,
                "release_date": task.track.release_date,
                "track_number": task.track.track_number,
                "disc_number": task.track.disc_number,
                "isrc": task.track.isrc,
            }

            dest_path, should_skip = resolve_destination_path(
                root_dir=download_dir,
                template=template,
                metadata=meta_dict,
                playlist_name=task.playlist_name,
                on_duplicate=on_duplicate
            )
            task.target_path = dest_path

            if should_skip:
                task.status = TaskStatus.SKIPPED
                task.status_message = "Fichier déjà existant sur le disque"
                task.progress = 100.0
                task.finished_at = time.time()
                self._log(f"Fichier déjà existant (ignoré) : {task.track.artist} - {task.track.title}", "INFO")
                self._notify_task(task)
                return

            # Callback de progression pour yt-dlp & tagging
            def _progress_callback(msg: str, pct: float):
                if task.status == TaskStatus.CANCELLED:
                    raise InterruptedError("Tâche annulée")
                task.status_message = msg
                task.progress = pct
                if pct < 20:
                    task.status = TaskStatus.SEARCHING
                elif pct < 90:
                    task.status = TaskStatus.DOWNLOADING
                elif pct < 95:
                    task.status = TaskStatus.CONVERTING
                elif pct < 99:
                    task.status = TaskStatus.TAGGING
                self._notify_task(task)

            # 2. Exécution du téléchargement & tagging
            downloader.download_track(
                track=task.track,
                output_filepath=dest_path,
                audio_quality=audio_quality,
                progress_cb=_progress_callback
            )

            task.status = TaskStatus.COMPLETED
            task.status_message = "Téléchargé et tagué avec succès (320 kbps)"
            task.progress = 100.0
            task.finished_at = time.time()
            self._log(f"Succès : {task.track.artist} - {task.track.title} -> {dest_path}", "SUCCESS")

        except InterruptedError:
            task.status = TaskStatus.CANCELLED
            task.status_message = "Téléchargement annulé"
            self._log(f"Annulé : {task.track.artist} - {task.track.title}", "WARNING")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.status_message = f"Erreur : {str(e)}"
            task.error_message = str(e)
            task.progress = 0.0
            task.finished_at = time.time()
            self._log(f"Échec pour '{task.track.artist} - {task.track.title}' : {e}", "ERROR")

        finally:
            self._notify_task(task)

    def cancel_task(self, task_id: str):
        """Annule une tâche spécifique."""
        with self._lock:
            task = self._task_map.get(task_id)
            if task and task.status in (TaskStatus.QUEUED, TaskStatus.SEARCHING, TaskStatus.DOWNLOADING):
                task.status = TaskStatus.CANCELLED
                task.status_message = "Annulé par l'utilisateur"
                self._notify_task(task)

    def cancel_all(self):
        """Annule toutes les tâches en attente et en cours."""
        with self._lock:
            self.is_running = False
            for task in self.tasks:
                if task.status in (TaskStatus.QUEUED, TaskStatus.SEARCHING, TaskStatus.DOWNLOADING, TaskStatus.CONVERTING, TaskStatus.TAGGING):
                    task.status = TaskStatus.CANCELLED
                    task.status_message = "Annulé"
                    self._notify_task(task)
        self._log("Toutes les tâches ont été annulées.", "WARNING")

    def retry_failed(self):
        """Remet dans la file d'attente toutes les pistes ayant échoué."""
        retried_count = 0
        with self._lock:
            for task in self.tasks:
                if task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                    task.status = TaskStatus.QUEUED
                    task.status_message = "En attente (réessai)"
                    task.progress = 0.0
                    task.error_message = None
                    retried_count += 1
                    self._notify_task(task)

        if retried_count > 0:
            self._log(f"Réessai de {retried_count} tâche(s) échouée(s).", "INFO")
            self.start()

    def clear_completed(self):
        """Supprime de la liste les tâches terminées ou ignorées."""
        with self._lock:
            self.tasks = [t for t in self.tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)]
            self._task_map = {t.id: t for t in self.tasks}
        self._notify_stats()

    def clear_all(self):
        """Vide complètement la file de téléchargement."""
        with self._lock:
            self.cancel_all()
            self.tasks.clear()
            self._task_map.clear()
        self._notify_stats()

    def get_stats(self) -> Dict[str, Any]:
        """Calcule les statistiques globales actuelles."""
        with self._lock:
            total = len(self.tasks)
            completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
            skipped = sum(1 for t in self.tasks if t.status == TaskStatus.SKIPPED)
            failed = sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
            in_progress = sum(1 for t in self.tasks if t.status in (TaskStatus.SEARCHING, TaskStatus.DOWNLOADING, TaskStatus.CONVERTING, TaskStatus.TAGGING))
            queued = sum(1 for t in self.tasks if t.status == TaskStatus.QUEUED)

            done_count = completed + skipped
            overall_pct = (done_count / total * 100.0) if total > 0 else 0.0

            return {
                "total": total,
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
                "in_progress": in_progress,
                "queued": queued,
                "done_count": done_count,
                "overall_percent": overall_pct,
                "is_running": self.is_running,
                "is_paused": self.is_paused
            }


# Instance globale
queue_manager = QueueManager()
