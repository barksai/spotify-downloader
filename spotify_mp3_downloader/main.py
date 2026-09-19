"""
Point d'entrée principal de l'application Spotify MP3 Downloader.
Vérifie la présence de FFmpeg et lance l'interface graphique.
"""
import sys
import os
import shutil
from tkinter import messagebox

# Ajout du dossier parent au PYTHONPATH pour l'import relatif/absolu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spotify_mp3_downloader.ui.app import App


def check_ffmpeg() -> bool:
    """Vérifie la disponibilité de FFmpeg sur le système Windows."""
    return shutil.which("ffmpeg") is not None


def main():
    # Vérification FFmpeg
    if not check_ffmpeg():
        print("[Avertissement] FFmpeg n'a pas été détecté dans le PATH Windows.")
        print("L'encodage MP3 nécessite FFmpeg. Veuillez installer FFmpeg (ex: winget install Gyan.FFmpeg).")

    # Lancement de l'application
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
