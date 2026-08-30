"""Indicateurs de la main-d'oeuvre et croisement effectif / avancement.

Tout est calcule en SQL : aucune donnee nominative n'est chargee en memoire
pour produire les agregats.
"""
from sqlalchemy import func

from models.db import db
from models.mainoeuvre import Ouvrier
from models.metier import Betonnage
from services.contexte import projet_actif_id


def _mois_courant(pid):
    """Mois le plus recent present dans le pointage (AAAA-MM), ou None."""
    return db.session.query(func.max(Ouvrier.mois)).filter(Ouvrier.projet_id == pid).scalar()


def kpis(mois=None):
    pid = projet_actif_id()
    mois = mois or _mois_courant(pid)
    if mois is None:
        return {"mois": None, "effectif": 0, "fonctions": 0, "presence_moyenne": 0.0,
                "heures_supp": 0.0, "heures_supp_moyenne": 0.0, "presents_pleins": 0}

    base = Ouvrier.query.filter_by(mois=mois, projet_id=pid)
    effectif = base.count()
    fonctions = (
        db.session.query(func.count(func.distinct(Ouvrier.fonction)))
        .filter(Ouvrier.projet_id == pid, Ouvrier.mois == mois).scalar()
    )
    presence = (
        db.session.query(func.avg(Ouvrier.taux_presence))
        .filter(Ouvrier.projet_id == pid, Ouvrier.mois == mois).scalar() or 0.0
    )
    supp = (
        db.session.query(func.coalesce(func.sum(Ouvrier.heures_supp), 0.0))
        .filter(Ouvrier.projet_id == pid, Ouvrier.mois == mois).scalar()
    )
    pleins = base.filter(Ouvrier.taux_presence >= 90).count()

    return {
        "mois": mois,
        "effectif": effectif,
        "fonctions": fonctions,
        "presence_moyenne": round(presence, 2),
        "heures_supp": round(supp, 2),
        "heures_supp_moyenne": round(supp / effectif, 1) if effectif else 0.0,
        "presents_pleins": pleins,
    }


def par_fonction(mois=None):
    pid = projet_actif_id()
    mois = mois or _mois_courant(pid)
    lignes = (
        db.session.query(
            Ouvrier.fonction,
            func.count(Ouvrier.id),
            func.avg(Ouvrier.taux_presence),
        )
        .filter(Ouvrier.projet_id == pid, Ouvrier.mois == mois)
        .group_by(Ouvrier.fonction)
        .order_by(func.count(Ouvrier.id).desc())
        .all()
    )
    return [
        {"fonction": f, "effectif": n, "presence": round(p or 0, 2)}
        for f, n, p in lignes
    ]


def effectif_mensuel():
    """Evolution de l'effectif et de la presence moyenne, mois par mois."""
    lignes = (
        db.session.query(
            Ouvrier.mois,
            func.count(Ouvrier.id),
            func.avg(Ouvrier.taux_presence),
        )
        .filter(Ouvrier.projet_id == projet_actif_id())
        .group_by(Ouvrier.mois)
        .order_by(Ouvrier.mois)
        .all()
    )
    return [
        {"mois": m, "effectif": n, "presence": round(p or 0, 2)}
        for m, n, p in lignes
    ]


def croisement_avancement():
    """Effectif du mois vs surface coulee le meme mois (productivite).

    Rapproche le pointage et le journal de betonnage par mois commun.
    """
    pid = projet_actif_id()
    effectifs = {m: (n, p) for m, n, p in (
        db.session.query(Ouvrier.mois, func.count(Ouvrier.id), func.avg(Ouvrier.taux_presence))
        .filter(Ouvrier.projet_id == pid)
        .group_by(Ouvrier.mois).all()
    )}
    coulages = dict(
        db.session.query(Betonnage.mois, func.coalesce(func.sum(Betonnage.surface), 0.0))
        .filter(Betonnage.projet_id == pid, Betonnage.mois.isnot(None))
        .group_by(Betonnage.mois).all()
    )
    mois_tries = sorted(set(effectifs) | set(coulages))
    serie = []
    for m in mois_tries:
        effectif = effectifs.get(m, (0, 0))[0]
        surface = round(coulages.get(m, 0.0), 2)
        serie.append({
            "mois": m,
            "effectif": effectif,
            "surface_coulee": surface,
            "m2_par_ouvrier": round(surface / effectif, 2) if effectif else 0.0,
        })
    return serie


def tout():
    pid = projet_actif_id()
    mois = _mois_courant(pid)
    return {
        "mois_disponibles": [
            m[0] for m in db.session.query(Ouvrier.mois)
            .filter(Ouvrier.projet_id == pid).distinct().order_by(Ouvrier.mois).all()
        ],
        "kpis": kpis(mois),
        "par_fonction": par_fonction(mois),
        "effectif_mensuel": effectif_mensuel(),
        "croisement": croisement_avancement(),
    }
