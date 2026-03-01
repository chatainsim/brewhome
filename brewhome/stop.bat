@echo off
title BrewHome - Arret

echo.
echo  Arret de BrewHome...

:: Chercher le PID qui ecoute sur le port 5000 et le tuer
set FOUND=0
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /r ":5000 "') do (
    if not "%%p"=="0" (
        taskkill /PID %%p /F >nul 2>&1
        if not errorlevel 1 (
            set FOUND=1
        )
    )
)

if "%FOUND%"=="1" (
    echo  [OK] BrewHome arrete.
) else (
    echo  [INFO] Aucune instance BrewHome trouvee sur le port 5000.
)

echo.
timeout /t 2 /nobreak >nul
