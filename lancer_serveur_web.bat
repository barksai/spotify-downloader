@echo off
title Spotify and Album Downloader - Serveur Web
cd /d "%~dp0"

:: 1. Detection de l'executable Python
set PYTHON_EXE=python
if exist "%~dp0.venv\Scripts\python.exe" (
    set PYTHON_EXE="%~dp0.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=".venv\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set PYTHON_EXE="%~dp0..\.venv\Scripts\python.exe"
)

:: 2. Verification automatique des dependances requises
%PYTHON_EXE% -c "import fastapi, uvicorn, yt_dlp, mutagen, requests, spotipy" 2>nul
if %errorlevel% neq 0 (
    echo ====================================================================
    echo   Installation automatique des dependances sur ce PC...
    echo   (Cette operation n'a lieu qu'une seule fois au premier lancement)
    echo ====================================================================
    %PYTHON_EXE% -m pip install fastapi "uvicorn[standard]" yt-dlp mutagen requests jinja2 python-multipart spotipy
    echo.
)

:: 3. Localisation du script de demarrage
set RUN_SCRIPT=""
if exist "%~dp0run_server.py" (
    set RUN_SCRIPT="%~dp0run_server.py"
) else if exist "%~dp0spotify_mp3_downloader\run_server.py" (
    set RUN_SCRIPT="%~dp0spotify_mp3_downloader\run_server.py"
)

:: 4. Lancement du serveur Web
if exist %RUN_SCRIPT% (
    %PYTHON_EXE% %RUN_SCRIPT%
) else (
    echo [i] Lancement direct via Uvicorn sur le port 8000...
    %PYTHON_EXE% -m uvicorn spotify_mp3_downloader.web.server:app --host 0.0.0.0 --port 8000
)

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] Le serveur s'est arrete avec une erreur.
    pause
)
