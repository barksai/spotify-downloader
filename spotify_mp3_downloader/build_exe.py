"""
Script de compilation et packaging autonome pour Windows via PyInstaller.
Génère l'exécutable autonome SpotifyMP3Downloader.exe avec inclusion des assets CustomTkinter.
"""
import os
import sys
import subprocess
import customtkinter


def build_executable():
    print("==================================================")
    print("  Construction de l'exécutable Windows (.exe)    ")
    print("==================================================")

    ctk_path = os.path.dirname(customtkinter.__file__)
    main_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

    # Arguments PyInstaller
    # --add-data sous Windows utilise le séparateur ';'
    add_data_arg = f"{ctk_path};customtkinter/"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",             # ou '--onefile' selon la préférence de distribution
        "--windowed",           # Pas de console noire en arrière-plan
        "--name=SpotifyMP3Downloader",
        f"--add-data={add_data_arg}",
        main_script,
    ]

    print(f"Commande d'exécution : {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n[SUCCÈS] Exécutable généré dans le dossier 'dist/SpotifyMP3Downloader/' !")
        print("Note : N'oubliez pas d'inclure 'ffmpeg.exe' dans le dossier dist ou dans le PATH Windows de l'utilisateur.")
    else:
        print("\n[ERREUR] La compilation a échoué.")


if __name__ == "__main__":
    build_executable()
