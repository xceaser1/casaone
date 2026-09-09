"""Barre d'informations de l'entete.

Une bande de reperes affichee en haut de chaque page : la date, l'avancement
du projet, les presents du jour, les demandes en attente et les alertes de
stock. Ces chiffres existaient deja, mais chacun sur sa propre page : il
fallait aller les chercher pour savoir si quelque chose demandait une
reaction. Les remonter en tete les rend visibles sans detour.

Contrainte : cette barre est rendue a CHAQUE page. Chaque indicateur est donc
une requete etroite et indexee, jamais un recalcul des tableaux complets, et
le resultat est memorise pour la duree de la requete HTTP — la barre laterale
affiche les memes compteurs et ne doit pas les interroger une seconde fois.
"""
from datetime import date, datetime, timedelta

from flask import g, has_request_context
from sqlalchemy import case, func

from models.db import db
from models.demande import Demande
from models.metier import Niveau, Surface
from models.presence import Presence
from models.stock import Article, Inventaire, Mouvement

MOIS_AFFICHE = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                "août", "septembre", "octobre", "novembre", "décembre")
JOURS_AFFICHE = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
# Formes abregees, pour les ecrans etroits ou la date longue mangerait la
# largeur des autres reperes.
JOURS_COURT = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS_COURT = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
              "août", "sept.", "oct.", "nov.", "déc.")


def _memo(cle, calcul):
    """Memorise un compteur pour la duree de la requete HTTP.

    Hors contexte de requete (tache, import), on calcule sans memoriser.
    """
    if not has_request_context():
        return calcul()
    cache = getattr(g, "_entete_cache", None)
    if cache is None:
        cache = g._entete_cache = {}
    if cle not in cache:
        cache[cle] = calcul()
    return cache[cle]


def presents(projet_id):
    """Ouvriers pointes en entree aujourd'hui (COUNT sur l'index projet+jour)."""
    if not projet_id:
        return 0
    return _memo(("presents", projet_id), lambda: Presence.query.filter_by(
        projet_id=projet_id, jour=date.today(), type="entree"
    ).count())


def demandes_en_attente(projet_id):
    """Demandes soumises, en attente d'une decision."""
    if not projet_id:
        return 0
    return _memo(("demandes", projet_id), lambda: Demande.query.filter_by(
        projet_id=projet_id, statut="soumise"
    ).count())


def _compter_alertes(projet_id):
    """Articles actifs dont le stock total est passe sous leur seuil.

    Requete dediee, volontairement plus etroite que `stock.tableau()` : seuls
    les articles ayant un seuil sont agreges, et le total se calcule en un
    seul passage sans detail par depot. Un transfert s'annule de lui-meme
    (il credite et debite le meme article), ce qui est correct : le seuil
    porte sur le stock tous depots confondus.
    """
    recu = func.coalesce(func.sum(case(
        (Mouvement.depot_dest_id.isnot(None), Mouvement.quantite), else_=0.0)), 0.0)
    sorti = func.coalesce(func.sum(case(
        (Mouvement.depot_source_id.isnot(None), Mouvement.quantite), else_=0.0)), 0.0)

    return (
        db.session.query(Article.id)
        .outerjoin(Mouvement, Mouvement.article_id == Article.id)
        .filter(Article.projet_id == projet_id, Article.actif.is_(True),
                Article.seuil_alerte.isnot(None), Article.seuil_alerte > 0)
        .group_by(Article.id, Article.seuil_alerte)
        .having((recu - sorti) < Article.seuil_alerte)
        .count()
    )


def alertes_stock(projet_id):
    if not projet_id:
        return 0
    return _memo(("alertes", projet_id), lambda: _compter_alertes(projet_id))


def _mesurer_avancement(projet_id):
    """Surface coulee / surface totale, dallage exclu comme au dashboard."""
    dallage = Niveau.query.filter_by(code="DALL", projet_id=projet_id).first()
    total, coule = db.session.query(
        func.coalesce(func.sum(Surface.surface_totale), 0.0),
        func.coalesce(func.sum(Surface.surface_coulee), 0.0),
    ).filter(
        Surface.projet_id == projet_id,
        Surface.niveau_id != (dallage.id if dallage else -1),
    ).one()
    pct = round(100.0 * coule / total, 1) if total else 0.0
    return {"total": round(total, 2), "coule": round(coule, 2), "pct": pct}


def avancement(projet_id):
    if not projet_id:
        return {"total": 0.0, "coule": 0.0, "pct": 0.0}
    return _memo(("avancement", projet_id), lambda: _mesurer_avancement(projet_id))


def date_lisible(jour=None):
    """« mardi 9 septembre », sans dependre de la locale du serveur.

    strftime('%A') renvoie l'anglais sous Windows et sur Render : on ne peut
    pas s'y fier pour une chaine que l'utilisateur lit.
    """
    jour = jour or date.today()
    return f"{JOURS_AFFICHE[jour.weekday()]} {jour.day} {MOIS_AFFICHE[jour.month - 1]}"


def date_courte(jour=None):
    """« mer. 9 sept. » — meme date, pour les petites largeurs."""
    jour = jour or date.today()
    return f"{JOURS_COURT[jour.weekday()]} {jour.day} {MOIS_COURT[jour.month - 1]}"


def _nb(valeur):
    """Sépare les milliers par une espace fine insecable (usage francais)."""
    return f"{valeur:,.0f}".replace(",", " ")


def infos(projet_id, peut, url_pour):
    """Les reperes de la barre, dans l'ordre d'affichage.

    `peut` et `url_pour` sont injectes par l'appelant : ce module n'a pas a
    connaitre ni le modele de droits ni le nommage des routes, et reste
    testable sans contexte applicatif.
    """
    chips = [{
        "cle": "date",
        "icone": "presence",
        "libelle": "Aujourd'hui",
        "valeur": date_lisible(),
        "court": date_courte(),
        "note": f"semaine {date.today().isocalendar()[1]}",
        "ton": "neutre",
    }]

    if projet_id and peut("dashboard"):
        av = avancement(projet_id)
        chips.append({
            "cle": "avancement",
            "icone": "diagrammes",
            "libelle": "Avancement",
            "valeur": f"{av['pct']:g} %",
            "note": f"{_nb(av['coule'])} / {_nb(av['total'])} m² coulés",
            "jauge": av["pct"],
            "url": url_pour("pages.dashboard"),
            "ton": "accent",
        })

    if projet_id and peut("pointage"):
        n = presents(projet_id)
        chips.append({
            "cle": "presents",
            "icone": "mainoeuvre",
            "libelle": "Sur le chantier",
            "valeur": str(n),
            "note": ("pointé" + ("s" if n > 1 else "") + " ce matin") if n else "aucun pointage",
            "url": url_pour("pointage.presences"),
            "ton": "ok" if n else "neutre",
        })

    if projet_id and peut("demandes"):
        n = demandes_en_attente(projet_id)
        chips.append({
            "cle": "demandes",
            "icone": "livraisons",
            "libelle": "Demandes",
            "valeur": str(n),
            "note": "à traiter" if n else "rien en attente",
            "url": url_pour("demandes.index"),
            "ton": "ambre" if n else "neutre",
        })

    if projet_id and peut("stock"):
        n = alertes_stock(projet_id)
        chips.append({
            "cle": "stock",
            "icone": "dalles",
            "libelle": "Stock",
            "valeur": str(n),
            "note": ("article" + ("s" if n > 1 else "") + " sous le seuil") if n else "aucune alerte",
            "url": url_pour("stock.index"),
            "ton": "alerte" if n else "neutre",
        })

    return chips


# ---------------------------------------------------------------- Notifications
#
# Volontairement DEDUITES de l'etat courant, sans drapeau « lu » en base : une
# notification n'est pas un evenement passe a archiver, c'est une chose qui
# reste a faire. Elle disparait quand le travail est fait, pas quand on l'a
# regardee — et deux responsables voient donc la meme liste, ce qui est le
# comportement attendu sur un chantier.
JOURS_RECENTS = 3


def _demandes_en_retard(projet_id):
    """Demandes attendues avant aujourd'hui et toujours pas servies."""
    return Demande.query.filter(
        Demande.projet_id == projet_id,
        Demande.statut.in_(("soumise", "validee")),
        Demande.besoin_pour.isnot(None),
        Demande.besoin_pour < date.today(),
    ).count()


def _inventaires_ouverts(projet_id):
    return Inventaire.query.filter_by(projet_id=projet_id, statut="ouvert").all()


def _mes_demandes_decidees(projet_id, utilisateur):
    """Demandes que J'AI emises et qui viennent d'etre tranchees.

    C'est la seule notification adressee a une personne en particulier : le
    demandeur n'a aucune raison de retourner voir sa demande tous les matins
    pour savoir si elle a ete acceptee.
    """
    if not utilisateur:
        return []
    depuis = datetime.utcnow() - timedelta(days=JOURS_RECENTS)
    return Demande.query.filter(
        Demande.projet_id == projet_id,
        Demande.demandeur == utilisateur,
        Demande.statut.in_(("validee", "refusee", "servie")),
        Demande.decide_le.isnot(None),
        Demande.decide_le >= depuis,
    ).order_by(Demande.decide_le.desc()).limit(5).all()


def notifications(projet_id, peut, url_pour, utilisateur=None):
    """Ce qui attend une action, du plus urgent au plus courant."""
    if not projet_id:
        return []
    items = []

    if peut("demandes"):
        for d in _mes_demandes_decidees(projet_id, utilisateur):
            items.append({
                "icone": "validation",
                "titre": f"Demande #{d.numero} {d.statut_libelle.lower()}",
                "detail": d.motif_decision or d.objet,
                "url": url_pour("demandes.detail", did=d.id),
                "ton": "alerte" if d.statut == "refusee" else "ok",
            })

        retard = _demandes_en_retard(projet_id)
        if retard:
            items.append({
                "icone": "livraisons",
                "titre": f"{retard} demande{'s' if retard > 1 else ''} en retard",
                "detail": "échéance dépassée, pas encore servie"
                          + ("s" if retard > 1 else ""),
                "url": url_pour("demandes.index"),
                "ton": "alerte",
            })

        attente = demandes_en_attente(projet_id)
        if attente:
            items.append({
                "icone": "livraisons",
                "titre": f"{attente} demande{'s' if attente > 1 else ''} à décider",
                "detail": "en attente de validation ou de refus",
                "url": url_pour("demandes.index"),
                "ton": "ambre",
            })

    if peut("stock"):
        sous_seuil = alertes_stock(projet_id)
        if sous_seuil:
            items.append({
                "icone": "dalles",
                "titre": f"{sous_seuil} article{'s' if sous_seuil > 1 else ''} sous le seuil",
                "detail": "à réapprovisionner",
                "url": url_pour("stock.index"),
                "ton": "alerte",
            })

        for inv in _inventaires_ouverts(projet_id):
            jours = (date.today() - inv.date_comptage).days if inv.date_comptage else 0
            items.append({
                "icone": "validation",
                "titre": f"Comptage #{inv.numero} en cours",
                "detail": (f"{inv.depot.code} — ouvert depuis {jours} jour"
                           + ("s" if jours > 1 else "")) if jours else
                          (f"{inv.depot.code} — ouvert aujourd'hui"),
                "url": url_pour("stock.inventaire", iid=inv.id),
                "ton": "ambre",
            })

    return items
