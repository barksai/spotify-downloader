@echo off
title Installation au Demarrage de Windows
cd /d "%~dp0"

echo ====================================================================
echo   Ajout de l'application Web au Demarrage automatique de Windows
echo ====================================================================
echo.

set TARGET_BAT=%~dp0lancer_serveur_web.bat
set SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_PATH=%SHORTCUT_DIR%\SpotifyDownloaderWeb.lnk

echo Creation du raccourci dans :
echo %SHORTCUT_PATH%
echo.

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [SUCCES] L'application se lancera desormais automatiquement
    echo          a chaque demarrage de votre PC Windows 10 !
) else (
    echo [ERREUR] Impossible de creer le raccourci automatiquement.
    echo Vous pouvez simplement copier 'lancer_serveur_web.bat' dans le dossier 'shell:startup'.
)

echo.
pause
