@echo off
setlocal enabledelayedexpansion
title BrewHome - Installation

echo.
echo  ==========================================
echo    BrewHome ^| Installation Windows
echo  ==========================================
echo.

:: ── Se placer dans le répertoire du script ──────────────────────────────────
cd /d "%~dp0"

:: ── Détecter Python ──────────────────────────────────────────────────────────
set PYTHON=
python --version >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    py --version >nul 2>&1 && set PYTHON=py
)
if "%PYTHON%"=="" (
    echo  [ERREUR] Python est introuvable.
    echo.
    echo  Telechargez Python 3.10 ou plus recent sur :
    echo    https://www.python.org/downloads/
    echo.
    echo  Cochez "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do set PYVER=%%v
echo  [OK] !PYVER! detecte

:: ── Créer l'environnement virtuel ────────────────────────────────────────────
if exist "venv\" (
    echo  [OK] Environnement virtuel existant
) else (
    echo.
    echo  Creation de l'environnement virtuel...
    !PYTHON! -m venv venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
    echo  [OK] Environnement virtuel cree
)

:: ── Installer les dépendances ─────────────────────────────────────────────────
echo.
echo  Installation des dependances Python...
venv\Scripts\pip install -q --upgrade pip
venv\Scripts\pip install -q -r requirements.txt
if errorlevel 1 (
    echo  [ERREUR] Echec de l'installation des dependances.
    pause
    exit /b 1
)
echo  [OK] Dependances installees (Flask)

:: ── Raccourci Bureau ──────────────────────────────────────────────────────────
echo.
echo  Creation du raccourci sur le bureau...
set "DESK=%USERPROFILE%\Desktop"
set "LINK=%DESK%\BrewHome.lnk"
set "TARGET=%~dp0start.bat"
set "ICON=%~dp0start.bat"

powershell -ExecutionPolicy Bypass -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LINK%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%~dp0start_silent.vbs\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'BrewHome - Gestion Brasserie'; $s.Save()" >nul 2>&1

if exist "%LINK%" (
    echo  [OK] Raccourci cree sur le bureau
) else (
    echo  [INFO] Raccourci non cree ^(droits insuffisants ou bureau indisponible^)
)

:: ── Démarrage automatique (optionnel) ─────────────────────────────────────────
echo.
set /p AUTOSTART="  Demarrer BrewHome automatiquement a l'ouverture de session ? (o/n) : "
if /i "%AUTOSTART%"=="o" (
    set "VBS_PATH=%~dp0start_silent.vbs"
    schtasks /create ^
        /tn "BrewHome" ^
        /tr "wscript.exe \"!VBS_PATH!\"" ^
        /sc ONLOGON ^
        /rl LIMITED ^
        /f >nul 2>&1
    if errorlevel 1 (
        echo  [AVERT] Impossible de planifier le demarrage automatique.
        echo          Essayez d'executer install.bat en tant qu'Administrateur.
    ) else (
        echo  [OK] Demarrage automatique active
    )
)

echo.
echo  ==========================================
echo    Installation terminee !
echo.
echo    start.bat          ^> Lance avec console ^(logs visibles^)
echo    start_silent.vbs   ^> Lance en arriere-plan
echo    stop.bat           ^> Arrete l'application
echo  ==========================================
echo.
pause
