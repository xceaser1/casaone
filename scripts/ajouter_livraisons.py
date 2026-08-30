"""Migration : ajoute le module Livraisons de beton a une installation existante.

Cree la table des livraisons et les permissions associees, sans toucher aux
donnees existantes. Accorde aussi aux conducteurs (role USER) le droit de saisir
les livraisons.

    python scripts/ajouter_livraisons.py
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from app import app, initialiser_referentiel_droits  # noqa: E402
from models.db import db  # noqa: E402


def principal():
    with app.app_context():
        db.create_all()
        initialiser_referentiel_droits()
    print("Module Livraisons de beton installe.")
    print("Vos donnees existantes n'ont pas ete modifiees.")
    print("Les conducteurs peuvent desormais saisir les livraisons.")


if __name__ == "__main__":
    principal()
