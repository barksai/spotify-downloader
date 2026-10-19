"""
Tests de la file d'attente : limite de concurrence, annulation, persistance.
Le téléchargeur est remplacé par un faux : aucun accès YouTube.
"""
import os
import threading
import time

import pytest

from spotify_mp3_downloader import queue_manager as qm_module
from spotify_mp3_downloader.config import config
from spotify_mp3_downloader.queue_manager import QueueManager, TaskStatus
from spotify_mp3_downloader.spotify_client import SpotifyTrack


def make_track(i: int) -> SpotifyTrack:
    return SpotifyTrack(
        id=f"t{i}", title=f"Titre {i}", artist="Artiste", artists=["Artiste"], album="Album",
        album_artist="Artiste", year="2020", release_date="2020-01-01", track_number=i,
        track_number_padded=f"{i:02d}", disc_number=1, total_tracks=10, duration_ms=1000, duration_str="0:01",
    )


def wait_for(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class FakeDownloader:
    """Simule un téléchargement : progresse tant que `release` n'est pas positionné."""

    def __init__(self):
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.running = 0
        self.max_running = 0

    def download_track(self, track, output_filepath, audio_quality, progress_cb):
        with self.lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            while not self.release.is_set():
                progress_cb("Téléchargement 50%", 50.0)
                time.sleep(0.02)
            os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
            with open(output_filepath, "wb") as f:
                f.write(b"mp3")
        finally:
            with self.lock:
                self.running -= 1
        return True


@pytest.fixture
def env(monkeypatch, tmp_path):
    fake = FakeDownloader()
    monkeypatch.setattr(qm_module, "downloader", fake)
    old = {k: config.get(k) for k in ("download_dir", "max_threads", "on_duplicate", "audio_quality")}
    config.set("download_dir", str(tmp_path / "music"), auto_save=False)
    config.set("max_threads", 2, auto_save=False)
    config.set("on_duplicate", "skip", auto_save=False)
    config.set("audio_quality", "256k", auto_save=False)
    manager = QueueManager()
    yield manager, fake, tmp_path
    fake.release.set()
    wait_for(lambda: not manager.is_running)
    for k, v in old.items():
        config.set(k, v, auto_save=False)


def test_respects_max_threads(env):
    manager, fake, _ = env
    manager.add_tracks([make_track(i) for i in range(1, 6)])
    manager.start()

    assert wait_for(lambda: fake.running == 2)
    time.sleep(0.3)
    assert fake.max_running == 2
    # Les autres tâches restent réellement « En attente » (et non « Recherche... »)
    assert sum(1 for t in manager.tasks if t.status == TaskStatus.QUEUED) == 3

    fake.release.set()
    assert wait_for(lambda: all(t.status == TaskStatus.COMPLETED for t in manager.tasks))
    # Le message reflète la qualité réellement configurée (et non « 320 kbps » en dur)
    assert manager.tasks[0].status_message == "Téléchargé et tagué avec succès (MP3 256 kbps)"


def test_max_threads_change_applies_without_restart(env):
    manager, fake, _ = env
    manager.add_tracks([make_track(i) for i in range(1, 6)])
    manager.start()
    assert wait_for(lambda: fake.running == 2)

    config.set("max_threads", 4, auto_save=False)
    assert wait_for(lambda: fake.running == 4)


def test_start_is_idempotent(env):
    manager, fake, _ = env
    manager.add_tracks([make_track(1)])
    manager.start()
    first_loop = manager._loop_thread
    manager.pause()
    manager.start()
    manager.resume()
    assert manager._loop_thread is first_loop
    assert sum(1 for th in threading.enumerate() if th.name == "QueueSupervisor") == 1


def test_cancel_running_task_is_marked_cancelled(env):
    manager, fake, tmp_path = env
    manager.add_tracks([make_track(1)])
    manager.start()
    assert wait_for(lambda: manager.tasks[0].status == TaskStatus.DOWNLOADING)

    manager.cancel_task(manager.tasks[0].id)
    assert wait_for(lambda: manager.tasks[0].status == TaskStatus.CANCELLED)
    # Aucun dossier vide laissé derrière
    assert not (tmp_path / "music").exists()


def test_cancel_queued_task(env):
    manager, fake, _ = env
    config.set("max_threads", 1, auto_save=False)
    manager.add_tracks([make_track(1), make_track(2)])
    manager.start()
    assert wait_for(lambda: fake.running == 1)

    queued = manager.tasks[1]
    manager.cancel_task(queued.id)
    assert queued.status == TaskStatus.CANCELLED
    fake.release.set()
    assert wait_for(lambda: manager.tasks[0].status == TaskStatus.COMPLETED)
    assert queued.status == TaskStatus.CANCELLED


def test_persistence_roundtrip(env):
    manager, fake, tmp_path = env
    persist = tmp_path / "queue.json"
    manager.load_persisted(persist)
    manager.add_tracks([make_track(1), make_track(2)])
    assert persist.exists()

    restored = QueueManager()
    assert restored.load_persisted(persist) == 2
    assert [t.track.title for t in restored.tasks] == ["Titre 1", "Titre 2"]
    assert all(t.status == TaskStatus.QUEUED for t in restored.tasks)
