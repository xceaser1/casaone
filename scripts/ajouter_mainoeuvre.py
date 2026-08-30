"""Migration : ajoute le module Main-d'oeuvre a une installation existante.

A lancer UNE fois sur votre PC serveur apres avoir remplace les fichiers du
projet. Ne touche a AUCUNE donnee existante : cree seulement la table des
ouvriers et les nouvelles permissions.

    python scripts/ajouter_mainoeuvre.py

Ensuite, importez votre canevas de pointage depuis Administration -> Import pointage.
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from app import app, initialiser_referentiel_droits  # noqa: E402
from models.db import db  # noqa: E402


def principal():
    with app.app_context():
        # cree uniquement les tables manquantes (dont « ouvriers »)
        db.create_all()
        # ajoute les permissions mainoeuvre.* et met a jour le role USER
        initialiser_referentiel_droits()
    print("Module Main-d'oeuvre installe.")
    print("Vos donnees existantes n'ont pas ete modifiees.")
    print("Importez votre pointage depuis : Administration -> Import pointage.")


if __name__ == "__main__":
    principal()
