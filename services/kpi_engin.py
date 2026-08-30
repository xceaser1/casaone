"""Indicateurs du parc materiel (engins)."""
from sqlalchemy import func

from models.db import db
from models.engin import Engin
from services.contexte import projet_actif_id


def kpis():
    pid = projet_actif_id()
    total = db.session.query(func.count(Engin.id)).filter(Engin.projet_id == pid).scalar()
    en_service = db.session.query(func.count(Engin.id)).filter(Engin.projet_id == pid, Engin.etat == "En service").scalar()
    en_panne = db.session.query(func.count(Engin.id)).filter(Engin.projet_id == pid, Engin.etat == "En panne").scalar()
    nb_types = db.session.query(func.count(func.distinct(Engin.type_engin))).filter(Engin.projet_id == pid).scalar()
    return {
        "total": total,
        "en_service": en_service,
        "en_panne": en_panne,
        "nb_types": nb_types,
        "taux_dispo": round(100.0 * en_service / total, 1) if total else 0.0,
    }


def par_type():
    lignes = (
        db.session.query(Engin.type_engin, func.count(Engin.id))
        .filter(Engin.projet_id == projet_actif_id())
        .group_by(Engin.type_engin)
        .order_by(func.count(Engin.id).desc())
        .all()
    )
    return [{"type": t or "Non renseigne", "nombre": n} for t, n in lignes]


def par_etat():
    lignes = (
        db.session.query(Engin.etat, func.count(Engin.id))
        .filter(Engin.projet_id == projet_actif_id())
        .group_by(Engin.etat).all()
    )
    return [{"etat": e or "Non renseigne", "nombre": n} for e, n in lignes]


def tout():
    return {"kpis": kpis(), "par_type": par_type(), "par_etat": par_etat()}
