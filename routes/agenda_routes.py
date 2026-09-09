"""Calendrier du chantier.

Les routes lisent le formulaire, appellent le service et rendent la page :
aucune regle metier ici, comme pour les demandes et le stock.
"""
from datetime import date

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from models.agenda import TYPES_EVENEMENT
from services import agenda as svc
from services.security import exige

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


def _jour(valeur):
    try:
        return date.fromisoformat((valeur or "").strip())
    except ValueError:
        return None


def _peut(module, action="view"):
    return current_user.is_authenticated and current_user.peut(module, action)


def _retour():
    """Revient au mois d'ou l'on vient, pas au mois courant.

    Sans cela, ajouter un evenement en novembre renvoie en septembre et on
    croit que la saisie a echoue.
    """
    annee = request.form.get("retour_annee", type=int)
    mois = request.form.get("retour_mois", type=int)
    if annee and mois and 1 <= mois <= 12:
        return redirect(url_for("agenda.index", annee=annee, mois=mois))
    return redirect(url_for("agenda.index"))


@bp.route("/")
@login_required
@exige("agenda")
def index():
    aujourdhui = date.today()
    annee = request.args.get("annee", type=int) or aujourdhui.year
    mois = request.args.get("mois", type=int) or aujourdhui.month
    if not 1 <= mois <= 12:
        mois = aujourdhui.month
    # Bornes larges mais finies : une annee absurde ferait planter date().
    annee = max(2000, min(2100, annee))

    calendrier = svc.mois(annee, mois, _peut, url_for)
    return render_template(
        "agenda.html", page="agenda", cal=calendrier,
        types=TYPES_EVENEMENT, jours=svc.JOURS_COURTS,
        prochains=svc.prochains(_peut, url_for),
        aujourdhui=aujourdhui,
        # La page reprend ces evenements pour remplir le formulaire de
        # modification sans aller-retour reseau. Le filtre `|tojson` de Flask
        # echappe < > & et ' : rien de ce qu'un utilisateur a saisi ne peut
        # fermer la balise <script> qui les porte.
        evenements=svc.evenements_bruts(annee, mois),
    )


@bp.route("/evenements", methods=["POST"])
@login_required
@exige("agenda", "create")
def creer():
    try:
        svc.creer(
            titre=request.form.get("titre"),
            debut=_jour(request.form.get("debut")),
            fin=_jour(request.form.get("fin")),
            heure=request.form.get("heure"),
            type_evenement=request.form.get("type_evenement"),
            lieu=request.form.get("lieu"),
            description=request.form.get("description"),
            par=current_user.username,
        )
        flash("Événement ajouté au calendrier.", "ok")
    except svc.Refus as e:
        flash(str(e), "erreur")
    return _retour()


@bp.route("/evenements/<int:eid>", methods=["POST"])
@login_required
@exige("agenda", "edit")
def modifier(eid):
    try:
        svc.modifier(
            eid,
            titre=request.form.get("titre"),
            debut=_jour(request.form.get("debut")),
            fin=_jour(request.form.get("fin")),
            heure=request.form.get("heure"),
            type_evenement=request.form.get("type_evenement"),
            lieu=request.form.get("lieu"),
            description=request.form.get("description"),
        )
        flash("Événement modifié.", "ok")
    except svc.Refus as e:
        flash(str(e), "erreur")
    return _retour()


@bp.route("/evenements/<int:eid>/supprimer", methods=["POST"])
@login_required
@exige("agenda", "delete")
def supprimer(eid):
    try:
        svc.supprimer(eid)
        flash("Événement supprimé.", "ok")
    except svc.Refus as e:
        flash(str(e), "erreur")
    return _retour()
