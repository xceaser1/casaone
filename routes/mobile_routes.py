"""Points d'entree destines a l'application Android.

Ces routes ne servent pas de pages : elles alimentent ce qui vit hors de la
vue web — la tuile de l'ecran d'accueil, la verification periodique qui
declenche les notifications, et le controle de version au demarrage.

Un seul appel suffit a tout cela : le telephone interroge peu, et souvent sur
un reseau de chantier mediocre. Toutes les valeurs viennent des services
existants, aucune logique metier n'est dupliquee ici.
"""
from datetime import date

from flask import Blueprint, current_app, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func

from models.db import db
from models.presence import Presence
from models.metier import Surface, ValidationPlan
from services import stock as svc_stock
from services.contexte import projet_actif_id
from services.security import exige

bp = Blueprint("mobile", __name__, url_prefix="/api/mobile")


def _peut(module):
    return current_user.is_authenticated and current_user.peut(module)


@bp.route("/etat")
@login_required
def etat():
    """Etat condense du projet actif, pour la tuile et les notifications.

    Chaque bloc n'est calcule que si l'utilisateur a le droit correspondant :
    une tuile ne doit pas reveler ce que la barre laterale lui cache.
    """
    pid = projet_actif_id()
    if pid is None:
        return jsonify({"ok": False, "erreur": "Aucun projet actif."}), 400

    donnees = {"ok": True, "projet": None, "avancement": None, "presents": None,
               "alertes_stock": None, "plans_en_attente": None}

    from models.projet import Projet
    projet = db.session.get(Projet, pid)
    donnees["projet"] = projet.nom if projet else None

    if _peut("dashboard") or _peut("surfaces"):
        total, coule = db.session.query(
            func.coalesce(func.sum(Surface.surface_totale), 0.0),
            func.coalesce(func.sum(Surface.surface_coulee), 0.0),
        ).filter(Surface.projet_id == pid).one()
        donnees["avancement"] = round(coule / total * 100, 2) if total else 0.0
        donnees["surface_coulee"] = round(coule, 0)
        donnees["surface_totale"] = round(total, 0)

    if _peut("pointage"):
        donnees["presents"] = Presence.query.filter_by(
            projet_id=pid, jour=date.today(), type="entree"
        ).count()

    if _peut("stock"):
        # tableau() renvoie (depots, lignes, alertes) ou alertes est deja un
        # compte d'articles sous le seuil.
        try:
            donnees["alertes_stock"] = svc_stock.tableau(pid)[2]
        except Exception:            # noqa: BLE001 - une tuile ne doit jamais casser l'app
            current_app.logger.exception("etat mobile : alertes stock indisponibles")
            donnees["alertes_stock"] = None

    if _peut("validation"):
        donnees["plans_en_attente"] = (
            ValidationPlan.query
            .filter(ValidationPlan.projet_id == pid, ValidationPlan.statut != "Valide")
            .count()
        )

    return jsonify(donnees)


@bp.route("/version")
def version():
    """Version publiee de l'application Android.

    Volontairement accessible sans session : le controle a lieu au demarrage,
    avant meme que l'utilisateur ne se connecte. Aucune donnee de chantier
    n'est exposee ici.
    """
    return jsonify({
        "version_code": current_app.config.get("APK_VERSION_CODE", 1),
        "version_nom": current_app.config.get("APK_VERSION_NOM", "1.0"),
        "url": current_app.config.get("APK_URL", ""),
        "notes": current_app.config.get("APK_NOTES", ""),
    })
