"""Connexion / deconnexion, avec protection anti-force brute."""
import time
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from models.auth import User
from models.db import db

bp = Blueprint("auth", __name__)

# --------------------------------------------------------------------------
# Limitation des tentatives de connexion (en memoire, par client).
# Au-dela de MAX_ECHECS sur FENETRE secondes -> blocage pendant BLOCAGE.
# Suffisant pour un serveur mono-processus ; remis a zero au redemarrage.
# --------------------------------------------------------------------------
MAX_ECHECS = 8
FENETRE = 600      # 10 min : fenetre de comptage
BLOCAGE = 600      # 10 min : duree de blocage
_tentatives = {}   # cle client -> [nb_echecs, horodatage_premier]


def _cle_client():
    transmis = request.headers.get("X-Forwarded-For", "")
    ip = transmis.split(",")[0].strip() if transmis else (request.remote_addr or "?")
    return ip


def _secondes_blocage(cle):
    infos = _tentatives.get(cle)
    if not infos:
        return 0
    nb, depuis = infos
    ecoule = time.time() - depuis
    if nb >= MAX_ECHECS and ecoule < BLOCAGE:
        return int(BLOCAGE - ecoule)
    if ecoule > FENETRE:
        _tentatives.pop(cle, None)
    return 0


def _noter_echec(cle):
    infos = _tentatives.get(cle)
    maintenant = time.time()
    if not infos or (maintenant - infos[1]) > FENETRE:
        _tentatives[cle] = [1, maintenant]
    else:
        infos[0] += 1


def _reinitialiser(cle):
    _tentatives.pop(cle, None)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))

    if request.method == "POST":
        cle = _cle_client()
        restant = _secondes_blocage(cle)
        if restant:
            flash(f"Trop de tentatives. Réessayez dans {restant // 60 + 1} minute(s).", "erreur")
            return render_template("login.html")

        identifiant = (request.form.get("username") or "").strip()
        mot_de_passe = request.form.get("password") or ""
        utilisateur = User.query.filter(
            db.func.lower(User.username) == identifiant.lower()
        ).first()

        if utilisateur is None or not utilisateur.check_password(mot_de_passe):
            _noter_echec(cle)
            flash("Identifiant ou mot de passe incorrect.", "erreur")
        elif not utilisateur.actif:
            flash("Ce compte est desactive. Contactez un administrateur.", "erreur")
        else:
            _reinitialiser(cle)
            login_user(utilisateur, remember=bool(request.form.get("remember")))
            utilisateur.derniere_connexion = datetime.utcnow()
            db.session.commit()
            suivant = request.args.get("next")
            # On n'accepte qu'une redirection interne (evite l'open redirect).
            if suivant and suivant.startswith("/") and not suivant.startswith("//"):
                return redirect(suivant)
            return redirect(url_for("pages.dashboard"))

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
