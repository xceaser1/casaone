"""Calendrier du chantier : ce qui est deja en base + ce qu'on y ajoute.

Le mois affiche agrege plusieurs sources. Les coulages, les livraisons, les
echeances de demandes et les comptages d'inventaire ne sont PAS recopies dans
une table d'agenda : ils sont lus la ou ils vivent. Recopier une date, c'est
accepter qu'elle diverge de l'original le jour ou quelqu'un la corrige d'un
seul cote.

Seuls les evenements que l'application ne peut pas deviner (reunions, jalons,
visites) ont leur propre table.

Chaque source est bornee au mois demande et n'est lue que si l'utilisateur a le
droit de voir le module correspondant : un pointeur ne doit pas decouvrir le
planning des coulages par le calendrier.
"""
import calendar
from datetime import date, timedelta

from models.agenda import TYPES_EVENEMENT, Evenement
from models.db import db
from models.demande import Demande
from models.livraison import Livraison
from models.metier import Betonnage
from models.stock import Inventaire
from services.contexte import projet_actif_id

MOIS_NOMS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre")
JOURS_COURTS = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")


class Refus(Exception):
    """Regle metier non respectee. Le message est destine a l'utilisateur."""


# --------------------------------------------------------------- utilitaires

def bornes(annee, mois_numero):
    """Premier et dernier jour du mois."""
    dernier = calendar.monthrange(annee, mois_numero)[1]
    return date(annee, mois_numero, 1), date(annee, mois_numero, dernier)


def mois_precedent(annee, mois_numero):
    return (annee - 1, 12) if mois_numero == 1 else (annee, mois_numero - 1)


def mois_suivant(annee, mois_numero):
    return (annee + 1, 1) if mois_numero == 12 else (annee, mois_numero + 1)


def libelle_mois(annee, mois_numero):
    return MOIS_NOMS[mois_numero - 1] + " " + str(annee)


def grille(annee, mois_numero):
    """Les semaines affichees, du lundi au dimanche, debordant sur les mois voisins.

    Un calendrier qui s'arrete au 1er du mois coupe la semaine en deux et cache
    ce qui tombe le lundi precedent — souvent la reunion de lancement.
    """
    premier, dernier = bornes(annee, mois_numero)
    depart = premier - timedelta(days=premier.weekday())
    arrivee = dernier + timedelta(days=6 - dernier.weekday())
    semaines, jour = [], depart
    while jour <= arrivee:
        semaines.append([jour + timedelta(days=i) for i in range(7)])
        jour += timedelta(days=7)
    return semaines, depart, arrivee


def _ajouter(index, jour, element):
    index.setdefault(jour, []).append(element)


def _pluriel(nb, mot):
    return str(nb) + " " + mot + ("s" if nb > 1 else "")


# ------------------------------------------------------------------ sources

def _evenements(pid, depart, arrivee, index):
    lignes = Evenement.query.filter(
        Evenement.projet_id == pid,
        Evenement.debut <= arrivee,
        db.func.coalesce(Evenement.fin, Evenement.debut) >= depart,
    ).order_by(Evenement.debut, Evenement.heure).all()

    for e in lignes:
        jour = max(e.debut, depart)
        fin = min(e.fin_effective, arrivee)
        while jour <= fin:
            _ajouter(index, jour, {
                "source": "evenement", "id": e.id,
                "titre": e.titre, "detail": e.lieu or e.type_libelle,
                "heure": e.heure, "couleur": e.couleur, "icone": e.icone,
                "url": None, "multi": e.duree_jours > 1,
            })
            jour += timedelta(days=1)
    return len(lignes)


def _coulages(pid, depart, arrivee, index, url_pour):
    lignes = (
        db.session.query(Betonnage.date_coulage,
                         db.func.count(Betonnage.id),
                         db.func.coalesce(db.func.sum(Betonnage.surface), 0.0))
        .filter(Betonnage.projet_id == pid,
                Betonnage.date_coulage >= depart, Betonnage.date_coulage <= arrivee)
        .group_by(Betonnage.date_coulage).all()
    )
    for jour, nb, surface in lignes:
        _ajouter(index, jour, {
            "source": "coulage", "id": None,
            "titre": _pluriel(nb, "coulage"),
            "detail": "{:,.0f} m²".format(surface).replace(",", " "),
            "heure": None, "couleur": "vert", "icone": "betonnage",
            "url": url_pour("pages.betonnage"), "multi": False,
        })
    return len(lignes)


def _livraisons(pid, depart, arrivee, index, url_pour):
    lignes = (
        db.session.query(Livraison.date_livraison,
                         db.func.count(Livraison.id),
                         db.func.coalesce(db.func.sum(Livraison.volume), 0.0))
        .filter(Livraison.projet_id == pid,
                Livraison.date_livraison >= depart, Livraison.date_livraison <= arrivee)
        .group_by(Livraison.date_livraison).all()
    )
    for jour, nb, volume in lignes:
        _ajouter(index, jour, {
            "source": "livraison", "id": None,
            "titre": _pluriel(nb, "livraison"),
            "detail": "{:g} m³".format(volume or 0.0),
            "heure": None, "couleur": "bleu", "icone": "livraisons",
            "url": url_pour("pages.livraisons"), "multi": False,
        })
    return len(lignes)


def _echeances_demandes(pid, depart, arrivee, index, url_pour):
    lignes = Demande.query.filter(
        Demande.projet_id == pid,
        Demande.besoin_pour.isnot(None),
        Demande.besoin_pour >= depart, Demande.besoin_pour <= arrivee,
        Demande.statut != "brouillon",
    ).order_by(Demande.besoin_pour).all()

    for d in lignes:
        # Une echeance depassee sans que la demande soit servie est un probleme,
        # pas une information : elle se distingue a l'oeil.
        en_retard = d.statut in ("soumise", "validee") and d.besoin_pour < date.today()
        _ajouter(index, d.besoin_pour, {
            "source": "demande", "id": d.id,
            "titre": "#" + str(d.numero) + " " + d.objet,
            "detail": "en retard" if en_retard else d.statut_libelle,
            "heure": None,
            "couleur": "rouge" if en_retard else "ambre",
            "icone": d.type_icone,
            "url": url_pour("demandes.detail", did=d.id), "multi": False,
        })
    return len(lignes)


def _inventaires(pid, depart, arrivee, index, url_pour):
    lignes = Inventaire.query.filter(
        Inventaire.projet_id == pid,
        Inventaire.date_comptage >= depart,
        Inventaire.date_comptage <= arrivee,
    ).all()
    for i in lignes:
        _ajouter(index, i.date_comptage, {
            "source": "inventaire", "id": i.id,
            "titre": "Comptage #" + str(i.numero),
            "detail": (i.depot.code if i.depot else "") + " · " + i.statut_libelle,
            "heure": None,
            "couleur": "ambre" if i.ouvert else "cyan",
            "icone": "dalles",
            "url": url_pour("stock.inventaire", iid=i.id), "multi": False,
        })
    return len(lignes)


# --------------------------------------------------------------------- mois

def mois(annee, mois_numero, peut, url_pour, projet_id=None):
    """Tout ce qui se passe ce mois-la, jour par jour.

    Renvoie la grille d'affichage, l'index {jour: [elements]} et le compte par
    source, pour que la page puisse dire ce qu'elle montre.
    """
    pid = projet_id or projet_actif_id()
    semaines, depart, arrivee = grille(annee, mois_numero)
    index, comptes = {}, {}

    if pid:
        comptes["evenement"] = _evenements(pid, depart, arrivee, index)
        if peut("betonnage"):
            comptes["coulage"] = _coulages(pid, depart, arrivee, index, url_pour)
        if peut("livraisons"):
            comptes["livraison"] = _livraisons(pid, depart, arrivee, index, url_pour)
        if peut("demandes"):
            comptes["demande"] = _echeances_demandes(pid, depart, arrivee, index, url_pour)
        if peut("stock"):
            comptes["inventaire"] = _inventaires(pid, depart, arrivee, index, url_pour)

    # Les evenements dates a l'heure passent devant, puis les journees entieres.
    for jour in index:
        index[jour].sort(key=lambda e: (e["heure"] is None, e["heure"] or "", e["titre"]))

    return {
        "annee": annee, "mois": mois_numero,
        "libelle": libelle_mois(annee, mois_numero),
        "semaines": semaines, "index": index, "comptes": comptes,
        "precedent": mois_precedent(annee, mois_numero),
        "suivant": mois_suivant(annee, mois_numero),
        "aujourdhui": date.today(),
    }


def evenements_bruts(annee, mois_numero, projet_id=None):
    """Les evenements du mois, tels quels, pour le formulaire de modification.

    Ils sont deja charges pour dessiner le mois : les renvoyer a la page evite
    un aller-retour reseau a chaque clic, ce qui compte sur le reseau d'un
    chantier. Aucune donnee sensible — c'est ce que la grille affiche deja.
    """
    pid = projet_id or projet_actif_id()
    if not pid:
        return {}
    _, depart, arrivee = grille(annee, mois_numero)
    lignes = Evenement.query.filter(
        Evenement.projet_id == pid,
        Evenement.debut <= arrivee,
        db.func.coalesce(Evenement.fin, Evenement.debut) >= depart,
    ).all()
    return {
        str(e.id): {
            "titre": e.titre, "type": e.type_evenement,
            "debut": e.debut.isoformat(),
            "fin": e.fin.isoformat() if e.fin else "",
            "heure": e.heure or "", "lieu": e.lieu or "",
            "description": e.description or "",
        }
        for e in lignes
    }


def prochains(peut, url_pour, projet_id=None, jours=14, limite=12):
    """Les echeances des deux prochaines semaines, pour la colonne laterale.

    Memes sources que la grille : une colonne qui annoncerait « rien de prevu »
    pendant que le mois affiche trois coulages la semaine suivante serait pire
    qu'absente.
    """
    pid = projet_id or projet_actif_id()
    depart = date.today()
    arrivee = depart + timedelta(days=jours)
    index = {}
    if pid:
        _evenements(pid, depart, arrivee, index)
        if peut("betonnage"):
            _coulages(pid, depart, arrivee, index, url_pour)
        if peut("livraisons"):
            _livraisons(pid, depart, arrivee, index, url_pour)
        if peut("demandes"):
            _echeances_demandes(pid, depart, arrivee, index, url_pour)
        if peut("stock"):
            _inventaires(pid, depart, arrivee, index, url_pour)

    liste = []
    for jour in sorted(index):
        for element in index[jour]:
            liste.append(dict(element, jour=jour))
    return liste[:limite]


# --------------------------------------------------------------------- CRUD

def _evenement(evenement_id, projet_id=None):
    pid = projet_id or projet_actif_id()
    e = Evenement.query.filter_by(id=evenement_id, projet_id=pid).first()
    if e is None:
        raise Refus("Événement introuvable.")
    return e


def creer(titre, debut, par, type_evenement="autre", fin=None, heure=None,
          lieu=None, description=None, projet_id=None):
    pid = projet_id or projet_actif_id()
    if not pid:
        raise Refus("Aucun projet actif.")
    titre = (titre or "").strip()
    if not titre:
        raise Refus("Le titre est obligatoire.")
    if debut is None:
        raise Refus("La date de début est obligatoire.")
    if fin and fin < debut:
        raise Refus("La date de fin précède la date de début.")
    if type_evenement not in dict(TYPES_EVENEMENT):
        type_evenement = "autre"

    e = Evenement(
        projet_id=pid, titre=titre[:160], type_evenement=type_evenement,
        debut=debut, fin=fin if fin and fin != debut else None,
        heure=(heure or "").strip() or None,
        lieu=(lieu or "").strip() or None,
        description=(description or "").strip() or None,
        cree_par=par,
    )
    db.session.add(e)
    db.session.commit()
    return e


def modifier(evenement_id, projet_id=None, **champs):
    e = _evenement(evenement_id, projet_id)
    if "titre" in champs:
        titre = (champs["titre"] or "").strip()
        if not titre:
            raise Refus("Le titre est obligatoire.")
        e.titre = titre[:160]
    if champs.get("debut"):
        e.debut = champs["debut"]
    if "fin" in champs:
        fin = champs["fin"]
        if fin and fin < e.debut:
            raise Refus("La date de fin précède la date de début.")
        e.fin = fin if fin and fin != e.debut else None
    if champs.get("type_evenement") in dict(TYPES_EVENEMENT):
        e.type_evenement = champs["type_evenement"]
    for cle in ("heure", "lieu", "description"):
        if cle in champs:
            setattr(e, cle, (champs[cle] or "").strip() or None)
    db.session.commit()
    return e


def supprimer(evenement_id, projet_id=None):
    e = _evenement(evenement_id, projet_id)
    db.session.delete(e)
    db.session.commit()
