"""Indicateurs des livraisons de beton et croisement livre / coule."""
from sqlalchemy import func

from models.db import db
from models.livraison import Livraison
from models.metier import Betonnage
from services.contexte import projet_actif_id


def _mois_courant(pid):
    return db.session.query(func.max(Livraison.mois)).filter(Livraison.projet_id == pid).scalar()


def kpis(mois=None):
    pid = projet_actif_id()
    mois = mois or _mois_courant(pid)
    total = db.session.query(func.coalesce(func.sum(Livraison.volume), 0.0)).filter(Livraison.projet_id == pid).scalar()
    nb = db.session.query(func.count(Livraison.id)).filter(Livraison.projet_id == pid).scalar()
    nb_fourn = (
        db.session.query(func.count(func.distinct(Livraison.fournisseur)))
        .filter(Livraison.projet_id == pid).scalar()
    )
    vol_mois = 0.0
    if mois:
        vol_mois = (
            db.session.query(func.coalesce(func.sum(Livraison.volume), 0.0))
            .filter(Livraison.projet_id == pid, Livraison.mois == mois)
            .scalar()
        )
    return {
        "volume_total": round(total, 2),
        "nb_livraisons": nb,
        "nb_fournisseurs": nb_fourn,
        "mois": mois,
        "volume_mois": round(vol_mois, 2),
    }


def par_fournisseur():
    lignes = (
        db.session.query(
            Livraison.fournisseur,
            func.count(Livraison.id),
            func.coalesce(func.sum(Livraison.volume), 0.0),
        )
        .filter(Livraison.projet_id == projet_actif_id())
        .group_by(Livraison.fournisseur)
        .order_by(func.sum(Livraison.volume).desc())
        .all()
    )
    return [
        {"fournisseur": f or "Non renseigne", "nombre": n, "volume": round(v, 2)}
        for f, n, v in lignes
    ]


def volume_mensuel():
    lignes = (
        db.session.query(Livraison.mois, func.coalesce(func.sum(Livraison.volume), 0.0))
        .filter(Livraison.projet_id == projet_actif_id(), Livraison.mois.isnot(None))
        .group_by(Livraison.mois)
        .order_by(Livraison.mois)
        .all()
    )
    return [{"mois": m, "volume": round(v, 2)} for m, v in lignes]


def croisement_coule():
    """Volume de beton livre vs surface coulee, mois par mois."""
    pid = projet_actif_id()
    livre = dict(
        db.session.query(Livraison.mois, func.coalesce(func.sum(Livraison.volume), 0.0))
        .filter(Livraison.projet_id == pid, Livraison.mois.isnot(None))
        .group_by(Livraison.mois)
        .all()
    )
    coule = dict(
        db.session.query(Betonnage.mois, func.coalesce(func.sum(Betonnage.surface), 0.0))
        .filter(Betonnage.projet_id == pid, Betonnage.mois.isnot(None))
        .group_by(Betonnage.mois)
        .all()
    )
    mois_tries = sorted(set(livre) | set(coule))
    serie = []
    for m in mois_tries:
        v = round(livre.get(m, 0.0), 2)
        s = round(coule.get(m, 0.0), 2)
        serie.append({
            "mois": m,
            "volume_livre": v,
            "surface_coulee": s,
            "ratio": round(v / s, 3) if s else 0.0,  # m3 livres par m2 coule
        })
    return serie


def tout():
    return {
        "kpis": kpis(),
        "par_fournisseur": par_fournisseur(),
        "volume_mensuel": volume_mensuel(),
        "croisement": croisement_coule(),
    }
