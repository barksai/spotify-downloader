@echo off
title Spotify MP3 Downloader
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "spotify_mp3_downloader\main.py"
) else (
    python spotify_mp3_downloader\main.py
)
pause
