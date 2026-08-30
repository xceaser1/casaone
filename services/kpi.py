"""Calcul des indicateurs et des series de graphiques.

Tous les calculs sont faits en SQL (agregats) : rien n'est charge inutilement
en memoire, ce qui permet de tenir la charge quel que soit le volume.
"""
from sqlalchemy import func

from models.db import db
from models.metier import Betonnage, Bloc, DalleSurface, Decompte, Niveau, Parametre, Surface, ValidationPlan, Zone
from services.contexte import projet_actif_id


def _pct(numerateur, denominateur):
    if not denominateur:
        return 0.0
    return round(100.0 * numerateur / denominateur, 2)


def _id_dallage(pid):
    """Le dallage (DALL) est un ouvrage sur terre-plein : le classeur Excel
    l'exclut des totaux « planchers ». On reprend la meme convention."""
    niveau = Niveau.query.filter_by(code="DALL", projet_id=pid).first()
    return niveau.id if niveau else -1


def kpis():
    """Indicateurs de tete du dashboard."""
    pid = projet_actif_id()
    dall = _id_dallage(pid)

    total, coule = db.session.query(
        func.coalesce(func.sum(Surface.surface_totale), 0.0),
        func.coalesce(func.sum(Surface.surface_coulee), 0.0),
    ).filter(Surface.projet_id == pid, Surface.niveau_id != dall).one()

    dall_total, dall_coule = db.session.query(
        func.coalesce(func.sum(Surface.surface_totale), 0.0),
        func.coalesce(func.sum(Surface.surface_coulee), 0.0),
    ).filter(Surface.projet_id == pid, Surface.niveau_id == dall).one()

    surf_validee = (
        db.session.query(func.coalesce(func.sum(ValidationPlan.surface), 0.0))
        .filter(ValidationPlan.projet_id == pid, ValidationPlan.statut == "Valide", ValidationPlan.niveau_id != dall)
        .scalar()
    )
    surf_plans = (
        db.session.query(func.coalesce(func.sum(ValidationPlan.surface), 0.0))
        .filter(ValidationPlan.projet_id == pid, ValidationPlan.niveau_id != dall)
        .scalar()
    )

    paye = db.session.query(func.coalesce(func.sum(Decompte.montant), 0.0)).filter(Decompte.projet_id == pid).scalar()
    marche = Parametre.get_float("montant_global_marche", 0.0, projet_id=pid)

    nb_zones = db.session.query(func.count(Zone.id)).filter(Zone.projet_id == pid).scalar()
    nb_blocs = db.session.query(func.count(Bloc.id)).filter(Bloc.projet_id == pid).scalar()
    nb_coulages = db.session.query(func.count(Betonnage.id)).filter(Betonnage.projet_id == pid).scalar()

    dernier_mois = (
        db.session.query(Betonnage.mois, func.sum(Betonnage.surface))
        .filter(Betonnage.projet_id == pid)
        .group_by(Betonnage.mois)
        .order_by(Betonnage.mois.desc())
        .first()
    )

    return {
        "surface_totale": round(total, 2),
        "surface_coulee": round(coule, 2),
        "surface_restante": round(total - coule, 2),
        "avancement": _pct(coule, total),
        "dallage_totale": round(dall_total, 2),
        "dallage_coulee": round(dall_coule, 2),
        "dallage_avancement": _pct(dall_coule, dall_total),
        "plans_valides_pct": _pct(surf_validee, surf_plans),
        "plans_valides_surface": round(surf_validee, 2),
        "montant_paye": round(paye, 2),
        "montant_marche": round(marche, 2),
        "consommation_pct": _pct(paye, marche),
        "reste_a_payer": round(marche - paye, 2),
        "nb_zones": nb_zones,
        "nb_blocs": nb_blocs,
        "nb_coulages": nb_coulages,
        "dernier_mois": dernier_mois[0] if dernier_mois else None,
        "dernier_mois_surface": round(dernier_mois[1], 2) if dernier_mois else 0.0,
    }


def betonnage_mensuel():
    """Surface coulee par mois + cumul (serie temporelle)."""
    lignes = (
        db.session.query(Betonnage.mois, func.sum(Betonnage.surface))
        .filter(Betonnage.projet_id == projet_actif_id(), Betonnage.mois.isnot(None))
        .group_by(Betonnage.mois)
        .order_by(Betonnage.mois)
        .all()
    )
    cumul, series = 0.0, []
    for mois, surface in lignes:
        cumul += surface or 0
        series.append({"mois": mois, "surface": round(surface or 0, 2), "cumul": round(cumul, 2)})
    return series


def avancement_par_niveau():
    lignes = (
        db.session.query(
            Niveau.code,
            Niveau.ordre,
            func.coalesce(func.sum(Surface.surface_totale), 0.0),
            func.coalesce(func.sum(Surface.surface_coulee), 0.0),
        )
        .join(Surface, Surface.niveau_id == Niveau.id)
        .filter(Niveau.projet_id == projet_actif_id())
        .group_by(Niveau.id)
        .order_by(Niveau.ordre)
        .all()
    )
    return [
        {
            "niveau": code,
            "total": round(tot, 2),
            "coule": round(coul, 2),
            "avancement": _pct(coul, tot),
        }
        for code, _ordre, tot, coul in lignes
    ]


def avancement_par_type_dalle():
    lignes = (
        db.session.query(
            DalleSurface.type_dalle,
            func.coalesce(func.sum(DalleSurface.surface_totale), 0.0),
            func.coalesce(func.sum(DalleSurface.surface_coulee), 0.0),
        )
        .filter(DalleSurface.projet_id == projet_actif_id())
        .group_by(DalleSurface.type_dalle)
        .all()
    )
    return [
        {"type": t, "total": round(tot, 2), "coule": round(coul, 2), "avancement": _pct(coul, tot)}
        for t, tot, coul in lignes
    ]


def repartition_par_bloc():
    lignes = (
        db.session.query(
            Bloc.code,
            func.coalesce(func.sum(Surface.surface_totale), 0.0),
            func.coalesce(func.sum(Surface.surface_coulee), 0.0),
        )
        .join(Zone, Zone.bloc_id == Bloc.id)
        .join(Surface, Surface.zone_id == Zone.id)
        .filter(Bloc.projet_id == projet_actif_id())
        .group_by(Bloc.id)
        .order_by(func.sum(Surface.surface_totale).desc())
        .all()
    )
    return [
        {"bloc": code, "total": round(tot, 2), "coule": round(coul, 2), "avancement": _pct(coul, tot)}
        for code, tot, coul in lignes
    ]


def statuts_validation():
    lignes = (
        db.session.query(
            ValidationPlan.statut,
            func.count(ValidationPlan.id),
            func.coalesce(func.sum(ValidationPlan.surface), 0.0),
        )
        .filter(ValidationPlan.projet_id == projet_actif_id())
        .group_by(ValidationPlan.statut)
        .all()
    )
    return [{"statut": s or "Non renseigne", "nombre": n, "surface": round(surf, 2)} for s, n, surf in lignes]


def couts_cumules():
    lignes = Decompte.query.filter_by(projet_id=projet_actif_id()).order_by(Decompte.ordre).all()
    cumul, series = 0.0, []
    for d in lignes:
        cumul += d.montant or 0
        series.append({"libelle": d.libelle, "montant": round(d.montant or 0, 2), "cumul": round(cumul, 2)})
    return series


def tout():
    """Paquet complet consomme par le dashboard (un seul appel reseau)."""
    return {
        "kpis": kpis(),
        "betonnage_mensuel": betonnage_mensuel(),
        "avancement_niveau": avancement_par_niveau(),
        "avancement_type": avancement_par_type_dalle(),
        "repartition_bloc": repartition_par_bloc(),
        "statuts_validation": statuts_validation(),
        "couts": couts_cumules(),
    }
