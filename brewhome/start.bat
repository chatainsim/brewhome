@echo off
setlocal enabledelayedexpansion
title BrewHome

cd /d "%~dp0"

:: ── Détecter Python si venv absent ───────────────────────────────────────────
if not exist "venv\" (
    echo  Environnement virtuel absent. Lancement de l'installation...
    echo.
    set PYTHON=
    python --version >nul 2>&1 && set PYTHON=python
    if "!PYTHON!"=="" py --version >nul 2>&1 && set PYTHON=py
    if "!PYTHON!"=="" (
        echo  [ERREUR] Python introuvable. Lancez install.bat d'abord.
        pause
        exit /b 1
    )
    !PYTHON! -m venv venv
    venv\Scripts\pip install -q -r requirements.txt
)

:: ── Ouvrir le navigateur après 2 s ───────────────────────────────────────────
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

echo.
echo  ==========================================
echo    BrewHome demarre sur http://localhost:5000
echo    Ctrl+C pour arreter
echo  ==========================================
echo.

venv\Scripts\python app.py
