"""
Lanceur universel du serveur Web Spotify MP3 Downloader.
Compatible Windows 10/11 sans probleme d'encodage de terminal.
"""
import os
import sys
import socket
from pathlib import Path

# Configuration UTF-8 robuste pour console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Désactiver le QuickEdit Mode de Windows CMD pour éviter que le clic de souris gèle l'application
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        hStdin = kernel32.GetStdHandle(-10) # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
            new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(hStdin, new_mode)
    except Exception:
        pass

# Ajouter le dossier racine au sys.path
p1 = Path(__file__).resolve().parent
p2 = p1.parent
for p in [str(p1), str(p2)]:
    if p not in sys.path:
        sys.path.insert(0, p)

def get_local_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append("127.0.0.1")
    return ips

def main():
    import uvicorn

    local_ips = get_local_ips()

    print("====================================================================")
    print("   Spotify & Album MP3 Downloader - Serveur Web Auto-heberge")
    print("   Version : v2.2.0 [Moteur Deno EJS + Anti-403 + Tags Jellyfin]")
    print("====================================================================")
    print()
    print("  Accès depuis ce PC :           http://localhost:8000")
    for ip in local_ips:
        print(f"  Accès depuis votre smartphone: http://{ip}:8000")
    print()
    print("--------------------------------------------------------------------")
    print("  Serveur Web actif sur le port 8000.")
    print("  Laissez cette fenêtre ouverte ou minimisée en arrière-plan.")
    print("====================================================================")
    print()

    uvicorn.run(
        "spotify_mp3_downloader.web.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    main()
