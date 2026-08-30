"""Resolution du projet actif.

Le projet actif est stocke en session (choisi via le selecteur de la barre
laterale). Hors requete HTTP (import en ligne de commande, taches), on retombe
sur le projet principal. Toutes les requetes metier filtrent sur cet id afin de
garantir l'etancheite des donnees entre projets.
"""
from flask import has_request_context, session

from models.projet import Projet


def projet_actif_id():
    """Id du projet actif : session -> principal -> premier projet -> None."""
    if has_request_context():
        pid = session.get("projet_id")
        if pid:
            return pid
    principal = Projet.principal()
    if principal:
        return principal.id
    premier = Projet.query.order_by(Projet.id).first()
    return premier.id if premier else None
