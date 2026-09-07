"""Gestion de stock : etat des depots, mouvements et transferts.

Toutes les ecritures passent par le journal des mouvements : une entree, une
sortie ou un transfert cree une ligne datee et nominative. Le stock affiche
est toujours recalcule a partir de ce journal.
"""
import csv
import io
from datetime import date

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from models.db import db
from models.stock import (STATUTS_INVENTAIRE, TYPES, Article, Depot,
                          Inventaire, Mouvement, PieceMouvement)
from services import inventaire as svc_inv
from services import pieces as svc_pieces
from services import stock as svc
from services.contexte import projet_actif_id
from services.security import exige

bp = Blueprint("stock", __name__, url_prefix="/stock")


def _nombre(valeur, defaut=0.0):
    valeur = (valeur or "").strip().replace(" ", "").replace(",", ".")
    if not valeur:
        return defaut
    try:
        return float(valeur)
    except ValueError:
        return defaut


def _jour(valeur):
    try:
        return date.fromisoformat((valeur or "").strip())
    except ValueError:
        return date.today()


# --------------------------------------------------------------- Etat du stock
@bp.route("/")
@login_required
@exige("stock")
def index():
    pid = projet_actif_id()
    depots, lignes, alertes = svc.tableau(pid)
    # Categories reellement presentes : un filtre ne doit proposer que des
    # valeurs qui donnent un resultat.
    categories = sorted({
        (l["article"].categorie or "").strip()
        for l in lignes if (l["article"].categorie or "").strip()
    })
    return render_template(
        "stock.html", page="stock", depots=depots, lignes=lignes,
        alertes=alertes, filtres=svc.valeurs_filtres(pid), types=TYPES,
        categories=categories, aujourdhui=date.today(),
    )


# ------------------------------------------------------------- Mouvements
@bp.route("/mouvements")
@login_required
@exige("stock")
def mouvements():
    pid = projet_actif_id()
    q = Mouvement.query.filter_by(projet_id=pid)

    type_ = request.args.get("type")
    if type_ in dict(TYPES):
        q = q.filter(Mouvement.type == type_)
    if request.args.get("article"):
        q = q.filter(Mouvement.article_id == request.args.get("article", type=int))
    if request.args.get("depot"):
        d = request.args.get("depot", type=int)
        q = q.filter(db.or_(Mouvement.depot_source_id == d, Mouvement.depot_dest_id == d))
    if request.args.get("du"):
        q = q.filter(Mouvement.date_mouvement >= _jour(request.args["du"]))
    if request.args.get("au"):
        q = q.filter(Mouvement.date_mouvement <= _jour(request.args["au"]))

    lignes = q.order_by(Mouvement.date_mouvement.desc(), Mouvement.id.desc()).limit(500).all()
    return render_template(
        "stock_mouvements.html", page="stock-mouvements", lignes=lignes,
        filtres=svc.valeurs_filtres(pid), types=TYPES, args=request.args,
        aujourdhui=date.today(),
    )


@bp.route("/mouvements/nouveau", methods=["POST"])
@login_required
@exige("stock", "create")
def creer_mouvement():
    pid = projet_actif_id()
    type_ = request.form.get("type")
    # La regularisation ne se saisit pas a la main : elle est ecrite par la
    # validation d'un inventaire, ce qui garantit qu'un ecart reste toujours
    # rattache au comptage qui l'a constate.
    if type_ not in ("entree", "sortie", "transfert"):
        flash("Type de mouvement inconnu.", "erreur")
        return redirect(url_for("stock.index"))

    article_id = request.form.get("article_id", type=int)
    quantite = _nombre(request.form.get("quantite"))
    source = request.form.get("depot_source_id", type=int)
    dest = request.form.get("depot_dest_id", type=int)

    # --- controles metier
    erreur = None
    if not article_id:
        erreur = "Choisissez un article."
    elif quantite <= 0:
        erreur = "La quantite doit etre superieure a zero."
    elif type_ == "entree" and not dest:
        erreur = "Choisissez le depot de destination."
    elif type_ == "sortie" and not source:
        erreur = "Choisissez le depot d'origine."
    elif type_ == "transfert":
        if not source or not dest:
            erreur = "Un transfert exige un depot d'origine et un depot de destination."
        elif source == dest:
            erreur = "Les deux depots d'un transfert doivent etre differents."

    # Le stock ne doit jamais devenir negatif : le magasinier regularise
    # d'abord l'entree correspondante.
    if erreur is None and type_ in ("sortie", "transfert"):
        dispo = svc.stock_article_depot(article_id, source, pid)
        if quantite > dispo + 1e-9:
            art = db.session.get(Article, article_id)
            unite = art.unite if art else ""
            erreur = f"Stock insuffisant : {dispo:g} {unite} disponible(s) dans ce depot."

    if erreur:
        flash(erreur, "erreur")
        return redirect(request.referrer or url_for("stock.index"))

    db.session.add(Mouvement(
        projet_id=pid, type=type_, article_id=article_id,
        depot_source_id=source if type_ in ("sortie", "transfert") else None,
        depot_dest_id=dest if type_ in ("entree", "transfert") else None,
        quantite=quantite, date_mouvement=_jour(request.form.get("date_mouvement")),
        reference=(request.form.get("reference") or "").strip(),
        fournisseur=(request.form.get("fournisseur") or "").strip() or None,
        motif=(request.form.get("motif") or "").strip(),
        saisi_par=current_user.username,
    ))
    db.session.commit()
    flash({"entree": "Entree enregistree.", "sortie": "Sortie enregistree.",
           "transfert": "Transfert enregistre."}[type_], "succes")
    return redirect(request.referrer or url_for("stock.index"))


@bp.route("/mouvements/<int:mid>/supprimer", methods=["POST"])
@login_required
@exige("stock", "delete")
def supprimer_mouvement(mid):
    m = Mouvement.query.filter_by(id=mid, projet_id=projet_actif_id()).first_or_404()
    db.session.delete(m)
    db.session.commit()
    flash("Mouvement supprime.", "succes")
    return redirect(request.referrer or url_for("stock.mouvements"))


# ------------------------------------------------------------------ Depots
@bp.route("/depots", methods=["POST"])
@login_required
@exige("stock", "create")
def creer_depot():
    pid = projet_actif_id()
    code = (request.form.get("code") or "").strip().upper()
    nom = (request.form.get("nom") or "").strip()
    if len(code) < 2 or not nom:
        flash("Code (2 caracteres minimum) et nom sont obligatoires.", "erreur")
    elif Depot.query.filter(Depot.projet_id == pid, db.func.upper(Depot.code) == code).first():
        flash("Ce code de depot existe deja.", "erreur")
    else:
        db.session.add(Depot(
            projet_id=pid, code=code, nom=nom,
            emplacement=(request.form.get("emplacement") or "").strip(),
            responsable=(request.form.get("responsable") or "").strip(),
        ))
        db.session.commit()
        flash("Depot cree.", "succes")
    return redirect(url_for("stock.index"))


# ---------------------------------------------------------------- Articles
@bp.route("/articles", methods=["POST"])
@login_required
@exige("stock", "create")
def creer_article():
    pid = projet_actif_id()
    code = (request.form.get("code") or "").strip().upper()
    designation = (request.form.get("designation") or "").strip()
    if not code or not designation:
        flash("Code et designation sont obligatoires.", "erreur")
    elif Article.query.filter(Article.projet_id == pid,
                              db.func.upper(Article.code) == code).first():
        flash("Ce code article existe deja.", "erreur")
    else:
        db.session.add(Article(
            projet_id=pid, code=code, designation=designation,
            categorie=(request.form.get("categorie") or "").strip(),
            unite=(request.form.get("unite") or "U").strip(),
            seuil_alerte=_nombre(request.form.get("seuil_alerte")),
            prix_unitaire=_nombre(request.form.get("prix_unitaire")),
        ))
        db.session.commit()
        flash("Article cree.", "succes")
    return redirect(url_for("stock.index"))


# ------------------------------------------------------------------ Export
@bp.route("/export.<fmt>")
@login_required
@exige("stock", "export")
def export(fmt):
    pid = projet_actif_id()
    depots, lignes, _ = svc.tableau(pid)
    entetes = ["Code", "Designation", "Categorie", "Unite"] + [d.code for d in depots] + ["Total"]

    def cellules(l):
        a = l["article"]
        return ([a.code, a.designation, a.categorie or "", a.unite]
                + [l["detail"].get(d.id, 0) for d in depots] + [l["total"]])

    nom = "stock_" + date.today().isoformat()

    if fmt == "csv":
        tampon = io.StringIO()
        w = csv.writer(tampon, delimiter=";")
        w.writerow(entetes)
        for l in lignes:
            w.writerow(cellules(l))
        return Response(
            tampon.getvalue().encode("utf-8-sig"),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="' + nom + '.csv"'})

    if fmt in ("xlsx", "excel"):
        wb = Workbook()
        ws = wb.active
        ws.title = "Stock"
        ws.append(entetes)
        fill = PatternFill("solid", fgColor="1D4ED8")
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = fill
            c.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
        for l in lignes:
            ws.append(cellules(l))
        flux = io.BytesIO()
        wb.save(flux)
        return Response(
            flux.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="' + nom + '.xlsx"'})

    return redirect(url_for("stock.index"))


# ------------------------------------------------------------- Fiche article
@bp.route("/articles/<int:aid>")
@login_required
@exige("stock")
def article(aid):
    """Tout ce qu'on sait d'un article, rassemble en une page."""
    fiche = svc.fiche_article(aid, projet_actif_id())
    if fiche is None:
        abort(404)
    return render_template("article.html", page="stock", f=fiche, types=TYPES,
                           depots=Depot.query.filter_by(projet_id=projet_actif_id(), actif=True)
                                  .order_by(Depot.code).all(),
                           aujourdhui=date.today())


# --------------------------------------------------------------- Inventaires
@bp.route("/inventaires")
@login_required
@exige("stock")
def inventaires():
    pid = projet_actif_id()
    return render_template(
        "inventaires.html", page="inventaires",
        lignes=svc_inv.lister(pid), statuts=STATUTS_INVENTAIRE,
        depots=Depot.query.filter_by(projet_id=pid, actif=True).order_by(Depot.code).all(),
        aujourdhui=date.today(),
    )


@bp.route("/inventaires/nouveau", methods=["POST"])
@login_required
@exige("stock", "create")
def ouvrir_inventaire():
    try:
        inv = svc_inv.ouvrir(
            request.form.get("depot_id", type=int), current_user.username,
            note=request.form.get("note"),
            date_comptage=_jour(request.form.get("date_comptage")),
        )
    except svc_inv.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("stock.inventaires"))
    flash(f"Inventaire #{inv.numero} ouvert · {len(inv.lignes)} articles à compter.", "succes")
    return redirect(url_for("stock.inventaire", iid=inv.id))


@bp.route("/inventaires/<int:iid>")
@login_required
@exige("stock")
def inventaire(iid):
    pid = projet_actif_id()
    inv = Inventaire.query.filter_by(id=iid, projet_id=pid).first_or_404()
    return render_template("inventaire.html", page="inventaires", inv=inv)


@bp.route("/inventaires/<int:iid>/saisir", methods=["POST"])
@login_required
@exige("stock", "edit")
def saisir_inventaire(iid):
    comptes = {}
    for cle, valeur in request.form.items():
        if cle.startswith("compte_"):
            try:
                comptes[int(cle[7:])] = valeur
            except ValueError:
                continue
    try:
        svc_inv.saisir(iid, comptes)
    except svc_inv.Refus as e:
        flash(str(e), "erreur")
    else:
        flash("Comptage enregistré.", "succes")
    return redirect(url_for("stock.inventaire", iid=iid))


@bp.route("/inventaires/<int:iid>/valider", methods=["POST"])
@login_required
@exige("stock", "edit")
def valider_inventaire(iid):
    try:
        inv, nb = svc_inv.valider(iid, current_user.username)
    except svc_inv.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("stock.inventaire", iid=iid))
    flash(f"Inventaire #{inv.numero} validé · {nb} régularisation(s) écrite(s) au journal.",
          "succes")
    return redirect(url_for("stock.inventaire", iid=iid))


@bp.route("/inventaires/<int:iid>/supprimer", methods=["POST"])
@login_required
@exige("stock", "delete")
def supprimer_inventaire(iid):
    try:
        svc_inv.supprimer(iid)
    except svc_inv.Refus as e:
        flash(str(e), "erreur")
        return redirect(url_for("stock.inventaire", iid=iid))
    flash("Inventaire supprimé.", "succes")
    return redirect(url_for("stock.inventaires"))


# -------------------------------------------------- Bons de livraison joints
SOUS_DOSSIER_BL = "mouvements"


def _mouvement_du_projet(mid):
    return Mouvement.query.filter_by(id=mid, projet_id=projet_actif_id()).first()


@bp.route("/mouvements/<int:mid>/pieces", methods=["POST"])
@login_required
@exige("stock", "create")
def joindre_bon(mid):
    if _mouvement_du_projet(mid) is None:
        abort(404)
    try:
        for fichier in request.files.getlist("piece"):
            if fichier and fichier.filename:
                nom, interne, mime, taille = svc_pieces.enregistrer(
                    fichier, current_app.config, SOUS_DOSSIER_BL)
                db.session.add(PieceMouvement(
                    mouvement_id=mid, nom=nom, fichier=interne, type_mime=mime,
                    taille=taille, ajoute_par=current_user.username))
        db.session.commit()
    except svc_pieces.FichierRefuse as e:
        db.session.rollback()
        flash(str(e), "erreur")
        return redirect(request.referrer or url_for("stock.mouvements"))
    flash("Bon de livraison joint.", "succes")
    return redirect(request.referrer or url_for("stock.mouvements"))


@bp.route("/pieces/<int:pid_piece>")
@login_required
@exige("stock")
def voir_bon(pid_piece):
    """Sert un bon joint, apres verification des droits ET du projet actif."""
    piece = (PieceMouvement.query.join(Mouvement)
             .filter(PieceMouvement.id == pid_piece,
                     Mouvement.projet_id == projet_actif_id()).first())
    if piece is None:
        abort(404)
    return send_from_directory(
        svc_pieces.dossier(current_app.config, SOUS_DOSSIER_BL), piece.fichier,
        as_attachment=not (piece.est_image or (piece.type_mime or "").endswith("pdf")),
        download_name=piece.nom,
    )


@bp.route("/pieces/<int:pid_piece>/supprimer", methods=["POST"])
@login_required
@exige("stock", "edit")
def supprimer_bon(pid_piece):
    piece = (PieceMouvement.query.join(Mouvement)
             .filter(PieceMouvement.id == pid_piece,
                     Mouvement.projet_id == projet_actif_id()).first())
    if piece is None:
        abort(404)
    fichier = piece.fichier
    db.session.delete(piece)
    db.session.commit()
    svc_pieces.effacer(fichier, current_app.config, SOUS_DOSSIER_BL)
    flash("Bon supprimé.", "succes")
    return redirect(request.referrer or url_for("stock.mouvements"))
