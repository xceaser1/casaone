@echo off
REM =====================================================================
REM  URBAGEC - CASA ONE : demarrage du serveur local
REM  Double-cliquez sur ce fichier pour lancer l'application.
REM =====================================================================
cd /d "%~dp0"

if not exist venv (
    echo Creation de l'environnement virtuel...
    python -m venv venv
    call venv\Scripts\activate
    echo Installation des dependances...
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)

if not exist database\casaone.db (
    echo Premiere utilisation : initialisation de la base...
    python scripts\initialiser.py
)

echo.
echo ============================================================
echo   Serveur en cours de demarrage...
echo   Laissez cette fenetre ouverte pendant l'utilisation.
echo ============================================================
echo.
python app.py
pause
