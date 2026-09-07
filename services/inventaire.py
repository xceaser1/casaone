"""Inventaire physique : comptage, ecarts, regularisation.

Le stock affiche par l'application est THEORIQUE — il se deduit du journal des
mouvements. Sur un chantier il derive du reel : casse, perte, sortie non
saisie. Sans moyen de le recaler, les chiffres cessent d'etre crus et le module
entier perd son interet.

Un inventaire fige le theorique au moment du comptage, recoit les quantites
reellement comptees, puis ecrit a la validation les mouvements de
regularisation correspondants. L'ecart reste ainsi visible et justifie dans le
journal, au lieu d'etre corrige en silence.

Comme pour les demandes, toute la logique vit ici et jamais dans les routes :
une regle oubliee dans un formulaire serait contournable ailleurs.
"""
from datetime import date, datetime

from sqlalchemy import func

from models.db import db
from models.stock import Article, Depot, Inventaire, LigneInventaire, Mouvement
from services import stock as svc_stock
from services.contexte import projet_actif_id


class Refus(Exception):
    """Regle metier non respectee. Le message est destine a l'utilisateur."""


def _inventaire(inventaire_id, projet_id=None):
    pid = projet_id or projet_actif_id()
    inv = Inventaire.query.filter_by(id=inventaire_id, projet_id=pid).first()
    if inv is None:
        raise Refus("Inventaire introuvable.")
    return inv


def prochain_numero(projet_id=None):
    pid = projet_id or projet_actif_id()
    dernier = db.session.query(func.max(Inventaire.numero)).filter(
        Inventaire.projet_id == pid
    ).scalar()
    return (dernier or 0) + 1


def lister(projet_id=None, statut=None):
    pid = projet_id or projet_actif_id()
    q = Inventaire.query.filter(Inventaire.projet_id == pid)
    if statut:
        q = q.filter(Inventaire.statut == statut)
    return q.order_by(Inventaire.numero.desc()).all()


def ouvrir(depot_id, par, projet_id=None, note=None, date_comptage=None):
    """Ouvre un inventaire et fige le theorique de chaque article du depot.

    Un seul inventaire ouvert par depot a la fois : deux comptages simultanes
    sur le meme magasin produiraient des regularisations contradictoires.
    """
    pid = projet_id or projet_actif_id()
    depot = Depot.query.filter_by(id=depot_id, projet_id=pid).first()
    if depot is None:
        raise Refus("Dépôt introuvable.")

    deja = Inventaire.query.filter_by(projet_id=pid, depot_id=depot_id, statut="ouvert").first()
    if deja is not None:
        raise Refus(f"Un inventaire est déjà en cours sur « {depot.code} » (n°{deja.numero}).")

    par_cle = svc_stock.stocks(pid)
    articles = (Article.query.filter_by(projet_id=pid, actif=True)
                .order_by(Article.designation).all())
    if not articles:
        raise Refus("Aucun article à compter : créez d'abord des articles.")

    inv = Inventaire(
        projet_id=pid, numero=prochain_numero(pid), depot_id=depot_id,
        date_comptage=date_comptage or date.today(), ouvert_par=par,
        note=(note or "").strip() or None,
    )
    for a in articles:
        inv.lignes.append(LigneInventaire(
            article_id=a.id, theorique=round(par_cle.get((a.id, depot_id), 0.0), 3),
        ))
    db.session.add(inv)
    db.session.commit()
    return inv


def saisir(inventaire_id, comptes, projet_id=None):
    """Enregistre les quantites comptees. `comptes` : {ligne_id: quantite|None}."""
    inv = _inventaire(inventaire_id, projet_id)
    if not inv.ouvert:
        raise Refus("Cet inventaire est validé : les quantités ne sont plus modifiables.")

    par_id = {l.id: l for l in inv.lignes}
    for lid, valeur in (comptes or {}).items():
        ligne = par_id.get(lid)
        if ligne is None:
            continue
        if valeur is None or valeur == "":
            ligne.compte = None
            continue
        try:
            qte = float(str(valeur).replace(",", "."))
        except (TypeError, ValueError):
            raise Refus(f"Quantité illisible pour « {ligne.article.designation} ».")
        if qte < 0:
            raise Refus(f"Quantité négative pour « {ligne.article.designation} ».")
        ligne.compte = qte
    db.session.commit()
    return inv


def valider(inventaire_id, par, projet_id=None):
    """Cloture l'inventaire et ecrit les regularisations.

    Une ligne non comptee est ignoree : ne pas avoir compte un article n'est
    pas la meme chose que l'avoir compte a zero, et confondre les deux
    viderait le stock de tout ce qu'on n'a pas eu le temps de verifier.
    """
    pid = projet_id or projet_actif_id()
    inv = _inventaire(inventaire_id, pid)
    if not inv.ouvert:
        raise Refus("Cet inventaire est déjà validé.")

    comptees = [l for l in inv.lignes if l.compte is not None]
    if not comptees:
        raise Refus("Aucun article compté : rien à valider.")

    mouvements = []
    for ligne in comptees:
        ecart = ligne.ecart
        if not ligne.ecart_significatif:
            continue
        # Un ecart positif credite le depot, un ecart negatif le debite : on
        # reutilise la mecanique des depots source/destination, sur laquelle
        # le calcul du stock se fonde deja.
        mouvements.append(Mouvement(
            projet_id=pid,
            type="regularisation",
            article_id=ligne.article_id,
            depot_dest_id=inv.depot_id if ecart > 0 else None,
            depot_source_id=inv.depot_id if ecart < 0 else None,
            quantite=abs(ecart),
            date_mouvement=inv.date_comptage,
            reference=f"INV-{inv.numero}",
            motif=f"Inventaire #{inv.numero} — écart {ecart:+g}",
            saisi_par=par,
        ))

    for m in mouvements:
        db.session.add(m)
    inv.statut = "valide"
    inv.valide_par = par
    inv.valide_le = datetime.utcnow()
    db.session.commit()
    return inv, len(mouvements)


def supprimer(inventaire_id, projet_id=None):
    """Supprime un inventaire encore ouvert.

    Un inventaire valide a genere des regularisations : le supprimer laisserait
    ces ecritures sans justification.
    """
    inv = _inventaire(inventaire_id, projet_id)
    if not inv.ouvert:
        raise Refus("Un inventaire validé ne peut pas être supprimé : il justifie des régularisations.")
    db.session.delete(inv)
    db.session.commit()
