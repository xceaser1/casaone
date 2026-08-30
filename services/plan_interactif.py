"""Donnees du plan interactif : avancement par bloc (etat actuel + timeline).

- Etat actuel : avancement de chaque bloc d'apres les surfaces coulees.
- Timeline : avancement cumule de chaque bloc, mois par mois, reconstitue a
  partir du journal de betonnage (feuille « Betonnage mensuelle »).

Le plan de zonage montre 9 grandes zones qui correspondent aux 9 blocs de la
base : MAO (Mall Ouest), MAC (Mall Central), MAE (Mall Est), GBM (Global Media),
ESP (Esplanade), IMMA/IMMB/IMM (Immeubles), HOTEL.
"""
from sqlalchemy import func

from models.db import db
from models.metier import Bloc, Betonnage, Surface, Zone
from services.contexte import projet_actif_id


def _pct(num, den):
    return round(100.0 * num / den, 2) if den else 0.0


def etat_actuel():
    """Avancement courant de chaque bloc (surface coulee / surface totale)."""
    lignes = (
        db.session.query(
            Bloc.code,
            Bloc.libelle,
            func.coalesce(func.sum(Surface.surface_totale), 0.0),
            func.coalesce(func.sum(Surface.surface_coulee), 0.0),
        )
        .join(Zone, Zone.bloc_id == Bloc.id)
        .outerjoin(Surface, Surface.zone_id == Zone.id)
        .filter(Bloc.projet_id == projet_actif_id())
        .group_by(Bloc.id)
        .all()
    )
    return {
        code: {
            "code": code,
            "libelle": libelle,
            "total": round(tot, 2),
            "coule": round(coul, 2),
            "avancement": _pct(coul, tot),
        }
        for code, libelle, tot, coul in lignes
    }


def timeline():
    """Avancement cumule par bloc et par mois (pour l'animation temporelle).

    Renvoie :
      - mois           : liste ordonnee des mois AAAA-MM
      - totaux         : surface totale prevue par bloc (denominateur fixe)
      - cumul[bloc]    : liste des % cumules, un par mois
    """
    pid = projet_actif_id()
    # Surface totale prevue par bloc (denominateur)
    totaux = dict(
        db.session.query(Bloc.code, func.coalesce(func.sum(Surface.surface_totale), 0.0))
        .join(Zone, Zone.bloc_id == Bloc.id)
        .outerjoin(Surface, Surface.zone_id == Zone.id)
        .filter(Bloc.projet_id == pid)
        .group_by(Bloc.id)
        .all()
    )

    # Surface coulee par bloc et par mois (via le journal de betonnage)
    lignes = (
        db.session.query(
            Bloc.code,
            Betonnage.mois,
            func.coalesce(func.sum(Betonnage.surface), 0.0),
        )
        .join(Zone, Betonnage.zone_id == Zone.id)
        .join(Bloc, Zone.bloc_id == Bloc.id)
        .filter(Betonnage.projet_id == pid, Betonnage.mois.isnot(None))
        .group_by(Bloc.code, Betonnage.mois)
        .all()
    )

    mois_set = sorted({m for _, m, _ in lignes})
    # coule[bloc][mois] = surface coulee ce mois-la
    par_bloc = {code: {} for code in totaux}
    for code, mois, surf in lignes:
        par_bloc.setdefault(code, {})[mois] = surf

    cumul = {}
    for code, total in totaux.items():
        acc = 0.0
        serie = []
        for m in mois_set:
            acc += par_bloc.get(code, {}).get(m, 0.0)
            serie.append(_pct(acc, total))
        cumul[code] = serie

    return {"mois": mois_set, "totaux": {k: round(v, 2) for k, v in totaux.items()}, "cumul": cumul}


def tout():
    return {"etat": etat_actuel(), "timeline": timeline()}
