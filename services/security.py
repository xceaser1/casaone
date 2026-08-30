"""Controle d'acces cote serveur.

Toutes les routes protegees passent par ces decorateurs. Le JavaScript ne sert
qu'a masquer des boutons : il n'accorde jamais un droit.
"""
from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user


def _refuser():
    if request.accept_mimetypes.best == "application/json" or request.path.startswith("/api/"):
        return jsonify({"erreur": "Acces refuse"}), 403
    abort(403)


def exige(module, action="view"):
    """Verifie que l'utilisateur connecte possede <module>.<action>."""

    def decorateur(vue):
        @wraps(vue)
        def enveloppe(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.peut(module, action):
                return _refuser()
            return vue(*args, **kwargs)

        return enveloppe

    return decorateur


def admin_requis(vue):
    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.est_admin:
            return _refuser()
        return vue(*args, **kwargs)

    return enveloppe
