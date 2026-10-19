"""
Configuration commune des tests : isole la configuration et le dossier musique dans des
répertoires temporaires AVANT l'import du package (l'instance `config` est créée à l'import).
"""
import os
import tempfile

_TEST_ROOT = tempfile.mkdtemp(prefix="spotify_dl_tests_")
os.environ["CONFIG_DIR"] = os.path.join(_TEST_ROOT, "config")
os.environ["DOWNLOAD_DIR"] = os.path.join(_TEST_ROOT, "music")
os.environ["QUEUE_PERSISTENCE"] = "0"
os.environ.pop("APP_PASSWORD", None)
os.environ.pop("MUSIC_ROOT", None)
os.environ.pop("PUBLIC_PORT", None)
os.environ.pop("PUBLIC_HOST", None)
os.makedirs(os.environ["DOWNLOAD_DIR"], exist_ok=True)
