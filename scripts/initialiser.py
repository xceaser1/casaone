"""Initialisation complete de la base : tables, droits, import Excel, compte admin.

Usage :
    python scripts/initialiser.py
    python scripts/initialiser.py --excel uploads/MON_FICHIER.xlsx --admin chef --mdp Secret123
    python scripts/initialiser.py --reset          (repart d'une base vide)
"""
import argparse
import getpass
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from app import app, initialiser_referentiel_droits  # noqa: E402
from models.auth import Role, User  # noqa: E402
from models.db import db  # noqa: E402
from services import excel_import  # noqa: E402


def principal():
    ap = argparse.ArgumentParser(description="Initialisation URBAGEC - CASA ONE")
    ap.add_argument("--excel", help="Chemin du classeur a importer")
    ap.add_argument("--admin", help="Identifiant du compte administrateur")
    ap.add_argument("--mdp", help="Mot de passe (sinon demande de facon masquee)")
    ap.add_argument("--reset", action="store_true", help="Supprime toutes les tables avant de recreer")
    args = ap.parse_args()

    with app.app_context():
        if args.reset:
            reponse = input("Supprimer TOUTES les donnees existantes ? (oui/non) : ")
            if reponse.strip().lower() != "oui":
                print("Annule.")
                return
            db.drop_all()
            print("Tables supprimees.")

        db.create_all()
        initialiser_referentiel_droits()
        print("Tables et referentiel de droits en place.")

        # --- compte administrateur -----------------------------------------
        identifiant = args.admin
        if not identifiant and not User.query.filter_by(actif=True).first():
            identifiant = input("Identifiant de l'administrateur [admin] : ").strip() or "admin"

        if identifiant:
            mdp = args.mdp
            while not mdp or len(mdp) < 6:
                mdp = getpass.getpass("Mot de passe (6 caracteres minimum) : ")
                if len(mdp) < 6:
                    print("  Trop court.")
            role = Role.query.filter_by(nom="ADMIN").first()
            u = User.query.filter_by(username=identifiant).first()
            if u is None:
                u = User(username=identifiant, nom_complet=identifiant, role_id=role.id, actif=True)
                db.session.add(u)
            u.role_id = role.id
            u.set_password(mdp)
            db.session.commit()
            print(f"Administrateur « {identifiant} » pret.")

        # --- import du classeur --------------------------------------------
        chemin = args.excel
        if not chemin:
            dossier = os.path.join(RACINE, "uploads")
            classeurs = sorted(f for f in os.listdir(dossier) if f.lower().endswith((".xlsx", ".xlsm")))
            if classeurs:
                chemin = os.path.join(dossier, classeurs[-1])
                print(f"Classeur detecte : {classeurs[-1]}")

        if chemin and os.path.exists(chemin):
            ok, resume = excel_import.importer(chemin, utilisateur="initialisation")
            if ok:
                print("Import termine : " + ", ".join(f"{k}={v}" for k, v in resume.items()))
            else:
                print("ECHEC de l'import : " + str(resume.get("erreur")))
                print("Les donnees deja presentes sont conservees.")
        else:
            print("Aucun classeur importe (vous pourrez le faire depuis la page Administration).")

    print("\nInitialisation terminee. Lancez le serveur avec :  python app.py")


if __name__ == "__main__":
    principal()
