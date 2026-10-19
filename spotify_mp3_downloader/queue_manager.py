"""
Spotify MP3 Downloader - Multithreaded Queue & Task Manager
Gère l'ordonnancement parallèle des téléchargements, la répartition des threads,
le suivi de progression en temps réel et les callbacks pour l'interface graphique.
"""
import json
import os
import threading
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict, fields
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any, Set

from .spotify_client import SpotifyTrack
from .downloader import downloader, quality_label
from .file_manager import resolve_destination_path
from .config import config, MAX_THREADS_LIMIT

# Nombre maximal de tâches terminées conservées en mémoire (les plus anciennes sont purgées)
MAX_FINISHED_TASKS = 500


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


ACTIVE_STATUSES = (TaskStatus.SEARCHING, TaskStatus.DOWNLOADING, TaskStatus.CONVERTING, TaskStatus.TAGGING)
FINISHED_STATUSES = (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED, TaskStatus.CANCELLED)


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
    cancel_requested: bool = False


class QueueManager:
    """Gestionnaire de file d'attente multithreadée."""

    def __init__(self):
        self.tasks: List[DownloadTask] = []
        self._task_map: Dict[str, DownloadTask] = {}
        self._lock = threading.RLock()

        # Pool dimensionné au maximum autorisé : la concurrence effective suit config["max_threads"]
        self.executor: Optional[ThreadPoolExecutor] = None
        self._futures: Dict[str, Future] = {}
        self._loop_thread: Optional[threading.Thread] = None
        self._reserved_paths: Set[str] = set()
        self._persist_path: Optional[Path] = None

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

    # ------------------------------------------------------------------
    # Persistance de la file (reprise après redémarrage du serveur)
    # ------------------------------------------------------------------

    def load_persisted(self, path: Path) -> int:
        """Active la sauvegarde de la file dans `path` et recharge les tâches non terminées."""
        self._persist_path = Path(path)
        if not self._persist_path.exists():
            return 0

        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._log(f"Impossible de relire la file sauvegardée : {e}", "WARNING")
            return 0

        track_fields = {f.name for f in fields(SpotifyTrack)}
        restored = 0
        with self._lock:
            for item in data.get("tasks", []):
                try:
                    track_data = {k: v for k, v in item["track"].items() if k in track_fields}
                    track = SpotifyTrack(**track_data)
                except Exception:
                    continue
                if item.get("id") in self._task_map:
                    continue
                failed = item.get("status") == TaskStatus.FAILED.name
                task = DownloadTask(
                    id=item.get("id") or str(uuid.uuid4())[:8],
                    track=track,
                    playlist_name=item.get("playlist_name", "Playlist"),
                    status=TaskStatus.FAILED if failed else TaskStatus.QUEUED,
                    status_message=item.get("status_message", "Échec") if failed else "En attente (reprise)",
                    error_message=item.get("error_message") if failed else None,
                )
                self.tasks.append(task)
                self._task_map[task.id] = task
                restored += 1

        if restored:
            self._log(f"{restored} tâche(s) restaurée(s) depuis la dernière session.", "INFO")
            self._notify_stats()
        return restored

    def _persist(self):
        """Sauvegarde les tâches en attente, en cours et en échec (écriture atomique)."""
        if not self._persist_path:
            return
        with self._lock:
            payload = {
                "tasks": [
                    {
                        "id": t.id,
                        "playlist_name": t.playlist_name,
                        "status": t.status.name,
                        "status_message": t.status_message,
                        "error_message": t.error_message,
                        "track": asdict(t.track),
                    }
                    for t in self.tasks
                    if t.status == TaskStatus.QUEUED or t.status in ACTIVE_STATUSES or t.status == TaskStatus.FAILED
                ]
            }
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp_path, self._persist_path)
        except Exception as e:
            print(f"[QueueManager] Erreur sauvegarde file: {e}")

    def _prune_finished(self):
        """Limite la mémoire : ne garde que les MAX_FINISHED_TASKS tâches terminées les plus récentes."""
        finished = [t for t in self.tasks if t.status in FINISHED_STATUSES and t.status != TaskStatus.FAILED]
        excess = len(finished) - MAX_FINISHED_TASKS
        if excess <= 0:
            return
        finished.sort(key=lambda t: t.finished_at or t.created_at)
        to_remove = {t.id for t in finished[:excess]}
        self.tasks = [t for t in self.tasks if t.id not in to_remove]
        self._task_map = {t.id: t for t in self.tasks}

    # ------------------------------------------------------------------
    # Gestion de la file
    # ------------------------------------------------------------------

    def add_tracks(self, tracks: List[SpotifyTrack], playlist_name: str = "Playlist") -> int:
        """Ajoute une liste de pistes Spotify à la file d'attente."""
        added_count = 0
        with self._lock:
            for track in tracks:
                # Éviter les doublons stricts en attente ou en cours dans la file courante
                if any(
                    t.track.id == track.id and (t.status == TaskStatus.QUEUED or t.status in ACTIVE_STATUSES)
                    for t in self.tasks
                ):
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
            self._prune_finished()

        if added_count > 0:
            self._log(f"Ajout de {added_count} morceau(x) à la file d'attente ({playlist_name}).", "INFO")
            self._persist()
        return added_count

    def start(self):
        """Démarre le traitement de la file de téléchargement (idempotent)."""
        with self._lock:
            self.is_running = True
            self.is_paused = False

            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=MAX_THREADS_LIMIT, thread_name_prefix="SpotifyWorker")

            if self._loop_thread is not None and self._loop_thread.is_alive():
                return

            self._loop_thread = threading.Thread(target=self._process_queue_loop, daemon=True, name="QueueSupervisor")
            self._loop_thread.start()

        self._log(f"Démarrage du traitement de la file ({self._max_concurrency()} threads simultanés).", "INFO")

    def pause(self):
        """Met en pause la file d'attente (les morceaux en cours se terminent)."""
        with self._lock:
            self.is_paused = True
        self._log("Mise en pause de la file d'attente.", "WARNING")
        self._notify_stats()

    def resume(self):
        """Reprend le traitement de la file d'attente."""
        self._log("Reprise de la file d'attente.", "INFO")
        self.start()

    @staticmethod
    def _max_concurrency() -> int:
        try:
            value = int(config.get("max_threads", 3))
        except (TypeError, ValueError):
            value = 3
        return max(1, min(value, MAX_THREADS_LIMIT))

    def _process_queue_loop(self):
        """Boucle de soumission des tâches aux workers, dans la limite de max_threads."""
        while True:
            with self._lock:
                if not self.is_running:
                    break

                self._futures = {tid: f for tid, f in self._futures.items() if not f.done()}
                queued_tasks = [t for t in self.tasks if t.status == TaskStatus.QUEUED]

                if not queued_tasks and not self._futures:
                    self.is_running = False
                    self._log("Toutes les tâches de la file sont terminées !", "SUCCESS")
                    self._notify_stats()
                    break

                if not self.is_paused and queued_tasks and len(self._futures) < self._max_concurrency():
                    task = queued_tasks[0]
                    task.status = TaskStatus.SEARCHING
                    task.status_message = "Initialisation..."
                    self._notify_task(task)
                    self._futures[task.id] = self.executor.submit(self._worker_execute_task, task)
                    continue

            time.sleep(0.2)

        with self._lock:
            if self._loop_thread is threading.current_thread():
                self._loop_thread = None

    def _worker_execute_task(self, task: DownloadTask):
        """Exécution du pipeline de téléchargement pour une piste par un worker thread."""
        reserved_path: Optional[str] = None
        try:
            download_dir = config.get("download_dir")
            template = config.get("filename_template")
            audio_quality = config.get("audio_quality", "320k")
            on_duplicate = config.get("on_duplicate", "skip")

            # 1. Calcul du chemin cible (réservé pour éviter que deux workers visent le même fichier)
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

            with self._lock:
                dest_path, should_skip = resolve_destination_path(
                    root_dir=download_dir,
                    template=template,
                    metadata=meta_dict,
                    playlist_name=task.playlist_name,
                    on_duplicate=on_duplicate,
                    reserved_paths=self._reserved_paths,
                )
                if not should_skip:
                    reserved_path = os.path.normcase(dest_path)
                    self._reserved_paths.add(reserved_path)
            task.target_path = dest_path

            if should_skip:
                task.status = TaskStatus.SKIPPED
                task.status_message = "Fichier déjà existant sur le disque"
                task.progress = 100.0
                task.finished_at = time.time()
                self._log(f"Fichier déjà existant (ignoré) : {task.track.artist} - {task.track.title}", "INFO")
                return

            # Callback de progression pour yt-dlp & tagging
            def _progress_callback(msg: str, pct: float):
                if task.cancel_requested:
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
            task.status_message = f"Téléchargé et tagué avec succès ({quality_label(audio_quality)})"
            task.progress = 100.0
            task.finished_at = time.time()
            self._log(f"Succès : {task.track.artist} - {task.track.title} -> {dest_path}", "SUCCESS")

        except Exception as e:
            task.finished_at = time.time()
            if task.cancel_requested or isinstance(e, InterruptedError):
                task.status = TaskStatus.CANCELLED
                task.status_message = "Téléchargement annulé"
                task.progress = 0.0
                self._log(f"Annulé : {task.track.artist} - {task.track.title}", "WARNING")
            else:
                task.status = TaskStatus.FAILED
                task.status_message = f"Erreur : {str(e)}"
                task.error_message = str(e)
                task.progress = 0.0
                self._log(f"Échec pour '{task.track.artist} - {task.track.title}' : {e}", "ERROR")

        finally:
            if reserved_path:
                with self._lock:
                    self._reserved_paths.discard(reserved_path)
            self._notify_task(task)
            self._persist()

    def cancel_task(self, task_id: str):
        """Annule une tâche spécifique (en attente ou en cours)."""
        with self._lock:
            task = self._task_map.get(task_id)
            if not task:
                return
            if task.status == TaskStatus.QUEUED:
                task.cancel_requested = True
                task.status = TaskStatus.CANCELLED
                task.status_message = "Annulé par l'utilisateur"
                task.finished_at = time.time()
            elif task.status in ACTIVE_STATUSES:
                # Le worker s'arrête au prochain point de contrôle et marque la tâche « Annulé »
                task.cancel_requested = True
                task.status_message = "Annulation en cours..."
            else:
                return
            self._notify_task(task)
        self._persist()

    def cancel_all(self):
        """Annule toutes les tâches en attente et en cours."""
        with self._lock:
            for task in self.tasks:
                if task.status == TaskStatus.QUEUED or task.status in ACTIVE_STATUSES:
                    task.cancel_requested = True
                    if task.status == TaskStatus.QUEUED:
                        task.status = TaskStatus.CANCELLED
                        task.status_message = "Annulé"
                        task.finished_at = time.time()
                    else:
                        task.status_message = "Annulation en cours..."
                    self._notify_task(task)
        self._log("Toutes les tâches ont été annulées.", "WARNING")
        self._persist()

    def retry_failed(self):
        """Remet dans la file d'attente toutes les pistes ayant échoué ou annulées."""
        retried_count = 0
        with self._lock:
            for task in self.tasks:
                if task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                    task.status = TaskStatus.QUEUED
                    task.status_message = "En attente (réessai)"
                    task.progress = 0.0
                    task.error_message = None
                    task.cancel_requested = False
                    task.finished_at = None
                    retried_count += 1
                    self._notify_task(task)

        if retried_count > 0:
            self._log(f"Réessai de {retried_count} tâche(s) échouée(s).", "INFO")
            self._persist()
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
            # Les tâches en cours restent référencées par leur worker jusqu'à leur arrêt
            self.tasks.clear()
            self._task_map.clear()
        self._persist()
        self._notify_stats()

    def get_stats(self) -> Dict[str, Any]:
        """Calcule les statistiques globales actuelles."""
        with self._lock:
            total = len(self.tasks)
            completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
            skipped = sum(1 for t in self.tasks if t.status == TaskStatus.SKIPPED)
            failed = sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
            in_progress = sum(1 for t in self.tasks if t.status in ACTIVE_STATUSES)
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
