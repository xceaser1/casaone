@echo off
REM =====================================================================
REM  URBAGEC - CASA ONE : demarrage en mode MOBILE (HTTPS)
REM  A utiliser pour le POINTAGE PAR SCAN sur telephone.
REM  L'appareil photo des telephones exige HTTPS : ce script lance donc
REM  le serveur en HTTPS avec un certificat auto-signe.
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

set HTTPS=1
set PORT=5000

echo.
echo ============================================================
echo   MODE MOBILE (HTTPS) - Pointage par scan
echo.
echo   1. Laissez cette fenetre ouverte.
echo   2. Sur le telephone, ouvrez l'adresse "Acces reseau"
echo      affichee ci-dessous (https://...).
echo   3. Acceptez l'alerte de securite du navigateur
echo      (certificat auto-signe) : Avance ^> Continuer.
echo   4. Connectez-vous, ouvrez "Scanner", autorisez la camera.
echo ============================================================
echo.
python app.py
pause
