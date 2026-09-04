"""Demandes d'approvisionnement : saisie, circuit de validation, service.

Les routes ne portent aucune regle metier : elles lisent le formulaire,
appellent le service et rendent la page. Toute la logique du circuit vit dans
services/demandes.py, sinon l'API mobile pourrait la contourner.
"""
from datetime import date

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required

from models.demande import STATUTS, TYPES_BESOIN, URGENCES, Demande
from models.stock import Article, Depot
from services import demandes as svc
from services.contexte import projet_actif_id
from services.security import exige

bp = Blueprint("demandes", __name__, url_prefix="/demandes")


def _jour(valeur):
    try:
        return date.fromisoformat((valeur or "").strip())
    except ValueError:
        return None


def _lignes_du_formulaire():
    """Reconstitue les lignes a partir des champs paralleles du formulaire.

    Le formulaire envoie des listes de meme longueur (article[], libre[],
    quantite[]...) : on les recoud ici.
    """
    articles = request.form.getlist("ligne_article")
    libres = request.form.getlist("ligne_libre")
    quantites = request.form.getlist("ligne_quantite")
    unites = request.form.getlist("ligne_unite")
    notes = request.form.getlist("ligne_note")

    lignes = []
    for i in range(max(len(articles), len(libres), len(quantites))):
        lignes.append({
            "article_id": articles[i] if i < len(articles) else None,
            "designation_libre": libres[i] if i < len(libres) else None,
            "quantite": quantites[i] if i < len(quantites) else 0,
            "unite": unites[i] if i < len(unites) else "U",
            "note": notes[i] if i < len(notes) else None,
        })
    return lignes


def _contexte_saisie(pid):
    return {
        "articles": Article.query.filter_by(projet_id=pid, actif=True)
                    .order_by(Article.designation).all(),
        "depots": Depot.query.filter_by(projet_id=pid, actif=True)
                  .order_by(Depot.code).all(),
        "urgences": URGENCES,
        "types_besoin": TYPES_BESOIN,
        "statuts": STATUTS,
    }


# ------------------------------------------------------------------ Liste
@bp.route("/")
@login_required
@exige("demandes")
def index():
    pid = projet_actif_id()
    args = request.args
    lignes = svc.lister(
        pid,
        statut=args.get("statut") or None,
        urgence=args.get("urgence") or None,
        demandeur=args.get("demandeur") or None,
        recherche=args.get("q") or None,
        type_besoin=args.get("type") or None,
    )
    return render_template(
        "demandes.html", page="demandes", lignes=lignes,
        compteurs=svc.compteurs(pid), filtres=svc.valeurs_filtres(pid),
        args=args, aujourdhui=date.today(), **_contexte_saisie(pid),
    )


# ------------------------------------------------------------------ Detail
@bp.route("/<int:did>")
@login_required
@exige("demandes")
def detail(did):
    pid = projet_actif_id()
    d = Demande.query.filter_by(id=did, projet_id=pid).first_or_404()
    return render_template(
        "demande_detail.html", page="demandes", d=d,
        aujourdhui=date.today(), **_contexte_saisie(pid),
    )


# ------------------------------------------------------------------ Creation
@bp.route("/nouvelle", methods=["GET", "POST"])
@login_required
@exige("demandes", "create")
def nouvelle():
    pid = projet_actif_id()
    if request.method == "POST":
        try:
            d = svc.creer(
                objet=request.form.get("objet", ""),
                demandeur=current_user.username,
                lignes=_lignes_du_formulaire(),
                localisation=request.form.get("localisation"),
                urgence=request.form.get("urgence", "normale"),
                type_besoin=request.form.get("type_besoin", "materiel"),
                besoin_pour=_jour(request.form.get("besoin_pour")),
                commentaire=request.form.get("commentaire"),
                projet_id=pid,
                soumettre=bool(request.form.get("soumettre")),
            )
        except svc.Refus as e:
            flash(str(e), "erreur")
            return render_template(
                "demande_form.html", page="demandes", d=None,
                formulaire=request.form, **_contexte_saisie(pid),
            )
        flash(f"Demande #{d.numero} enregistrée.", "succes")
        return redirect(url_for("demandes.detail", did=d.id))

    return render_template(
        "demande_form.html", page="demandes", d=None, formulaire={},
        **_contexte_saisie(pid),
    )


@bp.route("/<int:did>/modifier", methods=["GET", "POST"])
@login_required
@exige("demandes", "edit")
def modifier(did):
    pid = projet_actif_id()
    d = Demande.query.filter_by(id=did, projet_id=pid).first_or_404()

    if request.method == "POST":
        try:
            svc.modifier(
                did,
                objet=request.form.get("objet", ""),
                localisation=request.form.get("localisation"),
                urgence=request.form.get("urgence"),
                type_besoin=request.form.get("type_besoin"),
                besoin_pour=_jour(request.form.get("besoin_pour")),
                commentaire=request.form.get("commentaire"),
                lignes=_lignes_du_formulaire(),
                projet_id=pid,
            )
        except svc.Refus as e:
            flash(str(e), "erreur")
            return redirect(url_for("demandes.modifier", did=did))
        flash("Demande mise à jour.", "succes")
        return redirect(url_for("demandes.detail", did=did))

    return render_template(
        "demande_form.html", page="demandes", d=d, formulaire={},
        **_contexte_saisie(pid),
    )


# ------------------------------------------------------- Circuit de validation
@bp.route("/<int:did>/statut", methods=["POST"])
@login_required
@exige("demandes")
def statut(did):
    vers = request.form.get("vers", "")
    # Decider du sort d'une demande n'est pas la meme chose que la saisir :
    # valider, refuser ou servir exige le droit de modification.
    if vers in ("validee", "refusee") and not current_user.peut("demandes", "edit"):
        flash("Vous n'avez pas le droit de décider d'une demande.", "erreur")
        return redirect(url_for("demandes.detail", did=did))

    try:
        svc.changer_statut(did, vers, current_user.username,
                           motif=request.form.get("motif"))
    except svc.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("demandes.detail", did=did))

    flash({"soumise": "Demande soumise.", "validee": "Demande validée.",
           "refusee": "Demande refusée.", "brouillon": "Demande rouverte."}
          .get(vers, "Demande mise à jour."), "succes")
    return redirect(url_for("demandes.detail", did=did))


@bp.route("/<int:did>/servir", methods=["POST"])
@login_required
@exige("demandes", "edit")
def servir(did):
    # Servir ecrit dans le journal de stock : le droit d'y ecrire est requis.
    if not current_user.peut("stock", "create"):
        flash("Servir une demande écrit une sortie de stock : droit « stock » requis.", "erreur")
        return redirect(url_for("demandes.detail", did=did))

    quantites = {}
    for cle, valeur in request.form.items():
        if cle.startswith("servi_"):
            try:
                quantites[int(cle[6:])] = float((valeur or "0").replace(",", "."))
            except ValueError:
                continue
    try:
        d, nb = svc.servir(did, request.form.get("depot_id", type=int),
                           current_user.username, quantites=quantites)
    except svc.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("demandes.detail", did=did))

    flash(f"Demande #{d.numero} servie · {nb} sortie(s) de stock enregistrée(s).", "succes")
    return redirect(url_for("demandes.detail", did=did))


@bp.route("/<int:did>/supprimer", methods=["POST"])
@login_required
@exige("demandes", "delete")
def supprimer(did):
    try:
        svc.supprimer(did)
    except svc.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("demandes.detail", did=did))
    flash("Demande supprimée.", "succes")
    return redirect(url_for("demandes.index"))


# --------------------------------------------------------------------- API
@bp.route("/api/demandes", methods=["POST"])
@login_required
@exige("demandes", "create")
def api_creer():
    """Creation depuis l'application mobile : une demande saisie au pied du mur."""
    d = request.get_json(silent=True) or {}
    try:
        demande = svc.creer(
            objet=d.get("objet", ""),
            demandeur=current_user.username,
            lignes=d.get("lignes") or [],
            localisation=d.get("localisation"),
            urgence=d.get("urgence", "normale"),
            type_besoin=d.get("type_besoin", "materiel"),
            besoin_pour=_jour(d.get("besoin_pour")),
            commentaire=d.get("commentaire"),
            soumettre=bool(d.get("soumettre", True)),
        )
    except svc.Refus as e:
        return jsonify({"ok": False, "erreur": str(e)}), 400
    return jsonify({"ok": True, "id": demande.id, "numero": demande.numero,
                    "statut": demande.statut})


# ------------------------------------------------------------ Pieces jointes
@bp.route("/<int:did>/pieces", methods=["POST"])
@login_required
@exige("demandes", "create")
def ajouter_piece(did):
    try:
        for fichier in request.files.getlist("piece"):
            if fichier and fichier.filename:
                svc.ajouter_piece(did, fichier, current_user.username, current_app.config)
    except svc.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("demandes.detail", did=did))
    flash("Pièce jointe ajoutée.", "succes")
    return redirect(url_for("demandes.detail", did=did))


@bp.route("/pieces/<int:pid_piece>")
@login_required
@exige("demandes")
def voir_piece(pid_piece):
    """Sert un fichier joint.

    Passe par une route plutot que par /static : le controle de droits et
    l'appartenance au projet actif sont ainsi verifies a chaque acces.
    """
    piece = svc.piece(pid_piece)
    if piece is None:
        abort(404)
    return send_from_directory(
        svc.dossier_pieces(current_app.config), piece.fichier,
        # Les images et PDF s'affichent ; le nom d'origine est restitue au
        # telechargement, jamais le nom interne.
        as_attachment=not (piece.est_image or (piece.type_mime or "").endswith("pdf")),
        download_name=piece.nom,
    )


@bp.route("/pieces/<int:pid_piece>/supprimer", methods=["POST"])
@login_required
@exige("demandes", "edit")
def supprimer_piece(pid_piece):
    piece = svc.piece(pid_piece)
    did = piece.demande_id if piece else None
    try:
        svc.supprimer_piece(pid_piece, current_app.config)
    except svc.Refus as e:
        flash(str(e), "erreur")
    else:
        flash("Pièce supprimée.", "succes")
    return redirect(url_for("demandes.detail", did=did) if did else url_for("demandes.index"))


# ----------------------------------------------------------------- Messages
@bp.route("/<int:did>/messages", methods=["POST"])
@login_required
@exige("demandes")
def ajouter_message(did):
    try:
        svc.ajouter_message(did, current_user.username, request.form.get("texte"))
    except svc.Refus as e:
        flash(str(e), "erreur")
    return redirect(url_for("demandes.detail", did=did) + "#echange")
