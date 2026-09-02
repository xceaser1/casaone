"""Calcul des stocks a partir du journal des mouvements.

Tout est agrege en SQL : on ne charge jamais l'historique complet en memoire.
"""
from sqlalchemy import func

from models.db import db
from models.stock import Article, Depot, Mouvement
from services.contexte import projet_actif_id


def stocks(projet_id=None):
    """Quantite en stock par (article_id, depot_id).

    Entrees et transferts entrants creditent la destination ; sorties et
    transferts sortants debitent la source.
    """
    pid = projet_id or projet_actif_id()

    lignes = {}

    entrants = (
        db.session.query(Mouvement.article_id, Mouvement.depot_dest_id,
                         func.coalesce(func.sum(Mouvement.quantite), 0.0))
        .filter(Mouvement.projet_id == pid, Mouvement.depot_dest_id.isnot(None))
        .group_by(Mouvement.article_id, Mouvement.depot_dest_id).all()
    )
    for art, dep, qte in entrants:
        lignes[(art, dep)] = lignes.get((art, dep), 0.0) + (qte or 0.0)

    sortants = (
        db.session.query(Mouvement.article_id, Mouvement.depot_source_id,
                         func.coalesce(func.sum(Mouvement.quantite), 0.0))
        .filter(Mouvement.projet_id == pid, Mouvement.depot_source_id.isnot(None))
        .group_by(Mouvement.article_id, Mouvement.depot_source_id).all()
    )
    for art, dep, qte in sortants:
        lignes[(art, dep)] = lignes.get((art, dep), 0.0) - (qte or 0.0)

    return {k: round(v, 3) for k, v in lignes.items()}


def tableau(projet_id=None):
    """Vue complete : un article par ligne, une colonne par depot.

    Renvoie (depots, lignes, alertes) pret a afficher.
    """
    pid = projet_id or projet_actif_id()
    deps = Depot.query.filter_by(projet_id=pid, actif=True).order_by(Depot.code).all()
    arts = Article.query.filter_by(projet_id=pid, actif=True).order_by(Article.designation).all()
    par_cle = stocks(pid)

    lignes, alertes = [], 0
    for a in arts:
        detail = {d.id: par_cle.get((a.id, d.id), 0.0) for d in deps}
        total = round(sum(detail.values()), 3)
        sous_seuil = bool(a.seuil_alerte) and total < a.seuil_alerte
        if sous_seuil:
            alertes += 1
        lignes.append({
            "article": a, "detail": detail, "total": total, "alerte": sous_seuil,
        })
    return deps, lignes, alertes


def stock_article_depot(article_id, depot_id, projet_id=None):
    """Quantite disponible d'un article dans un depot (controle avant sortie)."""
    return stocks(projet_id).get((article_id, depot_id), 0.0)


def valeurs_filtres(projet_id=None):
    """Listes pour alimenter les menus deroulants."""
    pid = projet_id or projet_actif_id()
    return {
        "depots": Depot.query.filter_by(projet_id=pid, actif=True).order_by(Depot.code).all(),
        "articles": Article.query.filter_by(projet_id=pid, actif=True)
                                 .order_by(Article.designation).all(),
        "categories": [c[0] for c in db.session.query(Article.categorie)
                       .filter(Article.projet_id == pid, Article.categorie.isnot(None))
                       .distinct().order_by(Article.categorie).all() if c[0]],
    }
