"""Gestion du portefeuille de projets (fiches chantier).

- Liste / creation / modification / archivage des projets.
- Selection du projet actif (stocke en session, purement contextuel : les
  donnees detaillees restent rattachees au projet principal).
"""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required

from models.db import db
from models.projet import STATUTS, Projet
from services.security import exige

bp = Blueprint("projets", __name__, url_prefix="/projets")


def _parse_date(valeur):
    valeur = (valeur or "").strip()
    if not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None


def _parse_float(valeur, defaut=0.0):
    valeur = (valeur or "").strip().replace(" ", "").replace(",", ".")
    if not valeur:
        return defaut
    try:
        return float(valeur)
    except ValueError:
        return defaut


def _lire_formulaire(p):
    """Applique les champs du formulaire a une fiche projet."""
    p.nom = (request.form.get("nom") or "").strip()
    p.client = (request.form.get("client") or "").strip()
    p.ville = (request.form.get("ville") or "").strip()
    p.date_debut = _parse_date(request.form.get("date_debut"))
    p.date_fin = _parse_date(request.form.get("date_fin"))
    p.budget = _parse_float(request.form.get("budget"))
    p.avancement = max(0.0, min(100.0, _parse_float(request.form.get("avancement"))))
    statut = (request.form.get("statut") or "en_cours").strip()
    p.statut = statut if statut in STATUTS else "en_cours"
    couleur = (request.form.get("couleur") or "").strip()
    p.couleur = couleur if couleur.startswith("#") else "#14683f"
    # Code de pointage (auto-pointage). Vide = auto-pointage libre.
    p.pin_pointage = (request.form.get("pin_pointage") or "").strip() or None


# --------------------------------------------------------------------------
@bp.route("/")
@login_required
@exige("projets")
def index():
    return render_template(
        "projets.html",
        page="projets",
        projets=Projet.actifs(),
        statuts=STATUTS,
    )


@bp.route("/nouveau", methods=["POST"])
@login_required
@exige("projets", "create")
def creer():
    code = (request.form.get("code") or "").strip().upper()
    nom = (request.form.get("nom") or "").strip()

    if len(code) < 2:
        flash("Le code du projet doit contenir au moins 2 caractères.", "erreur")
    elif not nom:
        flash("Le nom du projet est obligatoire.", "erreur")
    elif Projet.query.filter(db.func.upper(Projet.code) == code).first():
        flash(f"Le code « {code} » existe déjà.", "erreur")
    else:
        p = Projet(code=code)
        _lire_formulaire(p)
        db.session.add(p)
        db.session.commit()
        flash(f"Projet « {p.nom} » créé.", "succes")
        session["projet_id"] = p.id  # on bascule sur le nouveau projet
    return redirect(url_for("projets.index"))


@bp.route("/<int:projet_id>", methods=["POST"])
@login_required
@exige("projets", "edit")
def modifier(projet_id):
    p = Projet.query.get_or_404(projet_id)
    action = request.form.get("action") or "profil"

    if action == "profil":
        if not (request.form.get("nom") or "").strip():
            flash("Le nom du projet est obligatoire.", "erreur")
        else:
            _lire_formulaire(p)
            flash("Projet mis à jour.", "succes")

    elif action == "archiver":
        if p.est_principal:
            flash("Le projet principal ne peut pas être archivé.", "erreur")
        else:
            p.archive = True
            if session.get("projet_id") == p.id:
                session.pop("projet_id", None)
            flash(f"Projet « {p.nom} » archivé.", "succes")

    db.session.commit()
    return redirect(url_for("projets.index"))


@bp.route("/<int:projet_id>/activer", methods=["POST"])
@login_required
@exige("projets")
def activer(projet_id):
    p = Projet.query.filter_by(id=projet_id, archive=False).first_or_404()
    session["projet_id"] = p.id
    flash(f"Projet actif : « {p.nom} ».", "succes")
    cible = request.form.get("suivant") or url_for("projets.index")
    return redirect(cible)
