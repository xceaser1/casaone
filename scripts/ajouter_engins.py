"""Migration : ajoute le module Materiel & engins a une installation existante.

Cree la table des engins et les permissions associees, sans toucher aux
donnees existantes. Accorde aussi aux conducteurs (role USER) le droit de saisir.

    python scripts/ajouter_engins.py
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
    print("Module Materiel & engins installe.")
    print("Vos donnees existantes n'ont pas ete modifiees.")


if __name__ == "__main__":
    principal()
