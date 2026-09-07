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


# --------------------------------------------------------------------------
# Valorisation
# --------------------------------------------------------------------------
def valoriser(projet_id=None):
    """Valeur du stock, par article et au total.

    Le prix unitaire vaut 0 tant qu'il n'est pas renseigne : la ligne est alors
    comptee pour zero et signalee, plutot que d'etre exclue en silence — un
    total qui ignore la moitie du magasin serait trompeur.
    """
    pid = projet_id or projet_actif_id()
    _, lignes, _ = tableau(pid)

    total, sans_prix = 0.0, 0
    for l in lignes:
        prix = l["article"].prix_unitaire or 0.0
        l["prix"] = prix
        l["valeur"] = round(l["total"] * prix, 2)
        total += l["valeur"]
        if prix <= 0 and l["total"] > 0:
            sans_prix += 1
    return {"lignes": lignes, "valeur_totale": round(total, 2), "sans_prix": sans_prix}


def consommation(projet_id=None, depuis=None):
    """Ce que le chantier a consomme : quantites sorties, valorisees.

    Seules les SORTIES comptent : un transfert deplace la marchandise sans la
    consommer, et une regularisation constate un ecart, elle ne mesure pas un
    usage.
    """
    pid = projet_id or projet_actif_id()
    q = (
        db.session.query(
            Mouvement.article_id,
            func.coalesce(func.sum(Mouvement.quantite), 0.0),
        )
        .filter(Mouvement.projet_id == pid, Mouvement.type == "sortie")
    )
    if depuis:
        q = q.filter(Mouvement.date_mouvement >= depuis)
    quantites = dict(q.group_by(Mouvement.article_id).all())

    articles = {a.id: a for a in Article.query.filter_by(projet_id=pid).all()}
    lignes, total = [], 0.0
    for aid, qte in quantites.items():
        a = articles.get(aid)
        if a is None:
            continue
        valeur = round((qte or 0.0) * (a.prix_unitaire or 0.0), 2)
        total += valeur
        lignes.append({"article": a, "quantite": round(qte or 0.0, 3), "valeur": valeur})
    lignes.sort(key=lambda x: -x["valeur"])
    return {"lignes": lignes, "valeur_totale": round(total, 2)}


# --------------------------------------------------------------------------
# Fiche article
# --------------------------------------------------------------------------
def fiche_article(article_id, projet_id=None):
    """Tout ce qu'on sait d'un article : stock par depot, histoire, consommation.

    L'information existait deja, eparpillee dans le journal ; la rassembler est
    ce qui permet de repondre a « ou en est cet article ».
    """
    pid = projet_id or projet_actif_id()
    article = Article.query.filter_by(id=article_id, projet_id=pid).first()
    if article is None:
        return None

    par_cle = stocks(pid)
    depots = Depot.query.filter_by(projet_id=pid, actif=True).order_by(Depot.code).all()
    par_depot = [
        {"depot": d, "quantite": round(par_cle.get((article.id, d.id), 0.0), 3)}
        for d in depots
    ]
    total = round(sum(x["quantite"] for x in par_depot), 3)

    mouvements = (
        Mouvement.query.filter_by(projet_id=pid, article_id=article.id)
        .order_by(Mouvement.date_mouvement.desc(), Mouvement.id.desc())
        .limit(60).all()
    )

    # Consommation mensuelle : uniquement les sorties, agregees en SQL.
    # L'expression de mois est nommee puis reutilisee : SQLAlchemy n'accepte
    # pas la position ordinale (GROUP BY 1) que tolerent certains SGBD.
    if db.engine.dialect.name == "sqlite":
        expr_mois = func.strftime("%Y-%m", Mouvement.date_mouvement)
    else:
        expr_mois = func.to_char(Mouvement.date_mouvement, "YYYY-MM")
    mois = (
        db.session.query(expr_mois.label("mois"),
                         func.coalesce(func.sum(Mouvement.quantite), 0.0))
        .filter(Mouvement.projet_id == pid, Mouvement.article_id == article.id,
                Mouvement.type == "sortie")
        .group_by(expr_mois).order_by(expr_mois).all()
    )

    return {
        "article": article,
        "par_depot": par_depot,
        "total": total,
        "sous_seuil": bool(article.seuil_alerte) and total < article.seuil_alerte,
        "valeur": round(total * (article.prix_unitaire or 0.0), 2),
        "mouvements": mouvements,
        "consommation_mois": [{"mois": m, "quantite": round(q or 0.0, 3)} for m, q in mois],
    }
