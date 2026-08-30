"""Pages de l'application (rendu HTML). Les donnees arrivent via /api."""
from flask import Blueprint, abort, render_template
from flask_login import login_required

from models.metier import Niveau, Zone
from services.contexte import projet_actif_id
from services.security import exige
from services.tables import TABLES, valeurs_filtres

bp = Blueprint("pages", __name__)


@bp.route("/")
@login_required
def accueil():
    return render_template("accueil.html", page="accueil")


@bp.route("/dashboard")
@login_required
@exige("dashboard")
def dashboard():
    return render_template("dashboard.html", page="dashboard")


def _page_table(cle, page, titre=None, filtres_fixes=None):
    spec = TABLES[cle]
    pid = projet_actif_id()
    return render_template(
        "table.html",
        page=page,
        spec=spec,
        titre=titre or spec.titre,
        colonnes=spec.colonnes,
        filtres=valeurs_filtres(cle),
        filtres_fixes=filtres_fixes or {},
        zones=Zone.query.filter_by(projet_id=pid).order_by(Zone.ordre).all(),
        niveaux=Niveau.query.filter_by(projet_id=pid).order_by(Niveau.ordre).all(),
    )


@bp.route("/surfaces")
@login_required
@exige("surfaces")
def surfaces():
    return _page_table("surfaces", "surfaces")


@bp.route("/betonnage")
@login_required
@exige("betonnage")
def betonnage():
    return _page_table("betonnage", "betonnage")


@bp.route("/validation")
@login_required
@exige("validation")
def validation():
    return _page_table("validation", "validation")


TYPES_DALLE_URL = {
    "reticulee": "Dalle Reticulee",
    "pleine": "Dalle Pleine",
    "post-tension": "Dalle Post-Tension",
    "hourdis": "Dalle Hourdis",
}


@bp.route("/dalles")
@bp.route("/dalles/<slug>")
@login_required
@exige("dalles")
def dalles(slug=None):
    if slug is None:
        return _page_table("dalles", "dalles")
    if slug not in TYPES_DALLE_URL:
        abort(404)
    type_dalle = TYPES_DALLE_URL[slug]
    return _page_table(
        "dalles", f"dalles-{slug}", titre=type_dalle, filtres_fixes={"type_dalle": type_dalle}
    )


@bp.route("/couts")
@login_required
@exige("couts")
def couts():
    return render_template("couts.html", page="couts", spec=TABLES["couts"])


@bp.route("/mainoeuvre")
@login_required
@exige("mainoeuvre")
def mainoeuvre():
    """Vue effectif : KPI et graphiques de la main-d'oeuvre."""
    return render_template("mainoeuvre.html", page="mainoeuvre")


@bp.route("/mainoeuvre/registre")
@login_required
@exige("mainoeuvre")
def mainoeuvre_registre():
    """Registre nominatif des ouvriers (tableau)."""
    return _page_table("ouvriers", "mainoeuvre-registre", titre="Registre des ouvriers")


@bp.route("/plan")
@login_required
@exige("surfaces")
def plan_interactif():
    """Plan de zonage interactif : les blocs se colorent selon l'avancement."""
    return render_template("plan.html", page="plan")


@bp.route("/livraisons")
@login_required
@exige("livraisons")
def livraisons():
    """Vue synthese des livraisons de beton : KPI et graphiques."""
    return render_template("livraisons.html", page="livraisons")


@bp.route("/livraisons/registre")
@login_required
@exige("livraisons")
def livraisons_registre():
    """Tableau des livraisons (saisie, filtres, export)."""
    return _page_table("livraisons", "livraisons-registre", titre="Journal des livraisons")


@bp.route("/engins")
@login_required
@exige("engins")
def engins():
    """Vue synthese du parc materiel."""
    return render_template("engins.html", page="engins")


@bp.route("/engins/registre")
@login_required
@exige("engins")
def engins_registre():
    """Tableau du parc materiel (saisie, filtres, export)."""
    return _page_table("engins", "engins-registre", titre="Parc materiel")


@bp.route("/diagrammes/<axe>")
@login_required
@exige("diagrammes")
def diagrammes(axe):
    if axe not in ("type", "niveau"):
        abort(404)
    return render_template("diagrammes.html", page=f"diag-{axe}", axe=axe)


@bp.route("/zone/<int:zone_id>")
@login_required
@exige("surfaces")
def detail_zone(zone_id):
    zone = Zone.query.filter_by(id=zone_id, projet_id=projet_actif_id()).first_or_404()
    return render_template("detail_zone.html", page="surfaces", zone=zone)
