"""API JSON : lecture paginee, CRUD, KPI, exports.

Toutes les routes verifient les droits cote serveur avant d'agir.
"""
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from models.db import db
from models.livraison import Livraison
from models.metier import Betonnage, Niveau, Surface, Zone
from services import export as svc_export
from services import kpi as svc_kpi
from services import kpi_livraison as svc_liv
from services import kpi_engin as svc_eng
from services import kpi_mainoeuvre as svc_mo
from services import plan_interactif as svc_plan
from services.contexte import projet_actif_id
from services.security import exige
from services.tables import TABLES, interroger, totaux, valeurs_filtres

bp = Blueprint("api", __name__, url_prefix="/api")


def _params():
    p = request.args.to_dict()
    return p


def _verifier_table(cle):
    if cle not in TABLES:
        return None
    return TABLES[cle]


# --------------------------------------------------------------------------
# Dashboard / diagrammes
# --------------------------------------------------------------------------
@bp.route("/dashboard")
@login_required
@exige("dashboard")
def dashboard():
    return jsonify(svc_kpi.tout())


@bp.route("/diagrammes/<axe>")
@login_required
@exige("diagrammes")
def diagrammes(axe):
    if axe == "type":
        return jsonify({"donnees": svc_kpi.avancement_par_type_dalle()})
    if axe == "niveau":
        return jsonify({"donnees": svc_kpi.avancement_par_niveau()})
    return jsonify({"erreur": "axe inconnu"}), 404


@bp.route("/couts")
@login_required
@exige("couts")
def couts():
    return jsonify({"kpis": svc_kpi.kpis(), "decomptes": svc_kpi.couts_cumules()})


@bp.route("/mainoeuvre")
@login_required
@exige("mainoeuvre")
def mainoeuvre():
    mois = request.args.get("mois")
    if mois:
        return jsonify(
            {"kpis": svc_mo.kpis(mois), "par_fonction": svc_mo.par_fonction(mois)}
        )
    return jsonify(svc_mo.tout())


@bp.route("/plan")
@login_required
@exige("surfaces")
def plan():
    """Donnees du plan interactif : avancement par bloc + timeline mensuelle."""
    return jsonify(svc_plan.tout())


@bp.route("/livraisons")
@login_required
@exige("livraisons")
def livraisons_dashboard():
    """Indicateurs des livraisons de beton + croisement avec le betonnage."""
    return jsonify(svc_liv.tout())


@bp.route("/engins")
@login_required
@exige("engins")
def engins_dashboard():
    """Indicateurs du parc materiel."""
    return jsonify(svc_eng.tout())


# --------------------------------------------------------------------------
# Lecture des tables
# --------------------------------------------------------------------------
@bp.route("/data/<cle>")
@login_required
def lire(cle):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "view"):
        return jsonify({"erreur": "Acces refuse"}), 403

    params = _params()
    resultat = interroger(cle, params, current_app.config["PAGE_SIZE_MAX"])
    resultat["totaux"] = totaux(cle, params)
    resultat["droits"] = {
        a: current_user.peut(spec.module, a) for a in ("create", "edit", "delete", "export")
    }
    return jsonify(resultat)


@bp.route("/data/<cle>/filtres")
@login_required
def filtres(cle):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "view"):
        return jsonify({"erreur": "Acces refuse"}), 403
    return jsonify(valeurs_filtres(cle))


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
def _convertir(valeur, type_attendu):
    if type_attendu is float:
        if valeur in (None, ""):
            return 0.0
        return float(str(valeur).replace(",", "."))
    if type_attendu is int:
        return int(valeur)
    if type_attendu == "date":
        return datetime.strptime(str(valeur)[:10], "%Y-%m-%d").date()
    return str(valeur).strip()


def _appliquer(objet, spec, donnees):
    """Validation cote serveur puis affectation des champs autorises."""
    erreurs = []
    for champ, type_attendu in spec.champs_edition.items():
        if champ not in donnees:
            continue
        try:
            valeur = _convertir(donnees[champ], type_attendu)
        except (ValueError, TypeError):
            erreurs.append(f"Valeur invalide pour « {champ} ».")
            continue
        if type_attendu is float and valeur < 0:
            erreurs.append(f"« {champ} » ne peut pas etre negatif.")
            continue
        setattr(objet, champ, valeur)
    # Coherence metier : la surface coulee ne depasse pas la surface prevue
    for tot, coul in (("surface_totale", "surface_coulee"),):
        if hasattr(objet, tot) and hasattr(objet, coul):
            if (getattr(objet, coul) or 0) > (getattr(objet, tot) or 0) + 0.01:
                erreurs.append("La surface coulee ne peut pas depasser la surface totale.")
    if isinstance(objet, Betonnage) and objet.date_coulage:
        objet.mois = objet.date_coulage.strftime("%Y-%m")
    if isinstance(objet, Livraison) and objet.date_livraison:
        objet.mois = objet.date_livraison.strftime("%Y-%m")
        if current_user.is_authenticated:
            objet.saisi_par = current_user.username
    return erreurs


@bp.route("/data/<cle>", methods=["POST"])
@login_required
def creer(cle):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "create"):
        return jsonify({"erreur": "Acces refuse"}), 403

    donnees = request.get_json(silent=True) or {}
    objet = spec.modele()
    objet.projet_id = projet_actif_id()  # rattache la ligne au projet actif
    erreurs = _appliquer(objet, spec, donnees)
    if erreurs:
        return jsonify({"erreurs": erreurs}), 400
    try:
        db.session.add(objet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"erreurs": [f"Enregistrement impossible : {exc.__class__.__name__}"]}), 400
    return jsonify({"ok": True, "ligne": spec.serialiser(objet)}), 201


@bp.route("/data/<cle>/<int:ident>", methods=["PUT"])
@login_required
def modifier(cle, ident):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "edit"):
        return jsonify({"erreur": "Acces refuse"}), 403

    objet = spec.modele.query.filter_by(id=ident, projet_id=projet_actif_id()).first_or_404()
    erreurs = _appliquer(objet, spec, request.get_json(silent=True) or {})
    if erreurs:
        db.session.rollback()
        return jsonify({"erreurs": erreurs}), 400
    db.session.commit()
    return jsonify({"ok": True, "ligne": spec.serialiser(objet)})


@bp.route("/data/<cle>/<int:ident>", methods=["DELETE"])
@login_required
def supprimer(cle, ident):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "delete"):
        return jsonify({"erreur": "Acces refuse"}), 403
    objet = spec.modele.query.filter_by(id=ident, projet_id=projet_actif_id()).first_or_404()
    db.session.delete(objet)
    db.session.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
@bp.route("/export/<cle>.<format_>")
@login_required
def exporter(cle, format_):
    spec = _verifier_table(cle)
    if spec is None:
        return jsonify({"erreur": "table inconnue"}), 404
    if not current_user.peut(spec.module, "export"):
        return jsonify({"erreur": "Acces refuse"}), 403

    params = _params()
    if format_ == "csv":
        contenu = svc_export.vers_csv(cle, params)
        mime = "text/csv; charset=utf-8"
    elif format_ in ("xlsx", "excel"):
        contenu = svc_export.vers_excel(cle, params)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        format_ = "xlsx"
    else:
        return jsonify({"erreur": "format inconnu"}), 400

    nom = svc_export.nom_fichier(cle, format_)
    return Response(
        contenu, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{nom}"'}
    )


# --------------------------------------------------------------------------
# Detail d'une zone
# --------------------------------------------------------------------------
@bp.route("/zone/<int:zone_id>")
@login_required
@exige("surfaces")
def detail_zone(zone_id):
    pid = projet_actif_id()
    zone = Zone.query.filter_by(id=zone_id, projet_id=pid).first_or_404()
    lignes = (
        Surface.query.join(Niveau, Surface.niveau_id == Niveau.id)
        .filter(Surface.zone_id == zone_id, Surface.projet_id == pid)
        .order_by(Niveau.ordre)
        .all()
    )
    coulages = (
        Betonnage.query.filter(Betonnage.zone_id == zone_id, Betonnage.projet_id == pid)
        .order_by(Betonnage.date_coulage.desc())
        .limit(40)
        .all()
    )
    total = sum(l.surface_totale or 0 for l in lignes)
    coule = sum(l.surface_coulee or 0 for l in lignes)
    return jsonify(
        {
            "zone": {"id": zone.id, "code": zone.code, "bloc": zone.bloc.code, "bloc_libelle": zone.bloc.libelle},
            "resume": {
                "total": round(total, 2),
                "coule": round(coule, 2),
                "reste": round(total - coule, 2),
                "avancement": round(100.0 * coule / total, 2) if total else 0.0,
                "nb_niveaux": len(lignes),
            },
            "niveaux": [
                {
                    "niveau": l.niveau.code,
                    "surface_totale": round(l.surface_totale or 0, 2),
                    "surface_coulee": round(l.surface_coulee or 0, 2),
                    "avancement": l.avancement,
                }
                for l in lignes
            ],
            "coulages": [
                {
                    "date": c.date_coulage.isoformat() if c.date_coulage else "",
                    "niveau": c.niveau.code if c.niveau else c.niveau_libelle,
                    "surface": round(c.surface or 0, 2),
                }
                for c in coulages
            ],
        }
    )


@bp.route("/zones")
@login_required
@exige("surfaces")
def liste_zones():
    lignes = (
        db.session.query(
            Zone.id,
            Zone.code,
            func.coalesce(func.sum(Surface.surface_totale), 0.0),
            func.coalesce(func.sum(Surface.surface_coulee), 0.0),
        )
        .outerjoin(Surface, Surface.zone_id == Zone.id)
        .filter(Zone.projet_id == projet_actif_id())
        .group_by(Zone.id)
        .order_by(Zone.ordre)
        .all()
    )
    return jsonify(
        [
            {
                "id": i,
                "code": code,
                "total": round(t, 2),
                "coule": round(c, 2),
                "avancement": round(100.0 * c / t, 2) if t else 0.0,
            }
            for i, code, t, c in lignes
        ]
    )
