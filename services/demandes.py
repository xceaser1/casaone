"""Circuit de vie d'une demande d'approvisionnement.

Toutes les transitions passent par ici, jamais par les routes : c'est le seul
endroit ou l'on decide qu'une demande peut changer d'etat, et le seul qui
ecrive dans le journal de stock. Une regle metier oubliee dans un formulaire
serait contournable par l'API mobile.
"""
from datetime import datetime

from sqlalchemy import func

from models.db import db
from models.demande import Demande, LigneDemande
from models.stock import Mouvement
from services import stock as svc_stock
from services.contexte import projet_actif_id

# Transitions autorisees. Tout ce qui n'y figure pas est refuse : mieux vaut un
# refus explicite qu'une demande qui remonte le circuit sans qu'on sache
# comment.
TRANSITIONS = {
    "brouillon": ("soumise",),
    "soumise": ("validee", "refusee", "brouillon"),
    "validee": ("servie", "refusee"),
    "refusee": (),
    "servie": (),
}


class Refus(Exception):
    """Regle metier non respectee. Le message est destine a l'utilisateur."""


def _demande(demande_id, projet_id=None):
    pid = projet_id or projet_actif_id()
    d = Demande.query.filter_by(id=demande_id, projet_id=pid).first()
    if d is None:
        raise Refus("Demande introuvable.")
    return d


def prochain_numero(projet_id=None):
    """Numero suivant pour ce projet. Les numeros ne sont pas partages."""
    pid = projet_id or projet_actif_id()
    dernier = db.session.query(func.max(Demande.numero)).filter(
        Demande.projet_id == pid
    ).scalar()
    return (dernier or 0) + 1


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def lister(projet_id=None, statut=None, urgence=None, demandeur=None, recherche=None):
    """Demandes du projet, les plus recentes d'abord."""
    pid = projet_id or projet_actif_id()
    q = Demande.query.filter(Demande.projet_id == pid)

    if statut:
        q = q.filter(Demande.statut == statut)
    if urgence:
        q = q.filter(Demande.urgence == urgence)
    if demandeur:
        q = q.filter(Demande.demandeur == demandeur)
    if recherche:
        motif = f"%{recherche.strip()}%"
        q = q.filter(db.or_(Demande.objet.ilike(motif),
                            Demande.localisation.ilike(motif)))

    return q.order_by(Demande.numero.desc()).all()


def compteurs(projet_id=None):
    """Nombre de demandes par statut, pour les tuiles et la pastille du menu."""
    pid = projet_id or projet_actif_id()
    lignes = (
        db.session.query(Demande.statut, func.count(Demande.id))
        .filter(Demande.projet_id == pid)
        .group_by(Demande.statut).all()
    )
    par_statut = {s: n for s, n in lignes}
    return {
        "brouillon": par_statut.get("brouillon", 0),
        "soumise": par_statut.get("soumise", 0),
        "validee": par_statut.get("validee", 0),
        "refusee": par_statut.get("refusee", 0),
        "servie": par_statut.get("servie", 0),
        # Ce qui attend une decision : le chiffre utile au responsable.
        "a_traiter": par_statut.get("soumise", 0),
    }


def valeurs_filtres(projet_id=None):
    """Valeurs distinctes proposees dans les filtres de la liste."""
    pid = projet_id or projet_actif_id()
    demandeurs = [
        d for (d,) in db.session.query(Demande.demandeur)
        .filter(Demande.projet_id == pid, Demande.demandeur.isnot(None))
        .distinct().order_by(Demande.demandeur).all()
    ]
    return {"demandeurs": demandeurs}


# --------------------------------------------------------------------------
# Ecriture
# --------------------------------------------------------------------------
def creer(objet, demandeur, lignes, localisation=None, urgence="normale",
          besoin_pour=None, commentaire=None, projet_id=None, soumettre=False):
    """Cree une demande et ses lignes.

    `lignes` : liste de dicts {article_id | designation_libre, quantite, unite, note}.
    """
    pid = projet_id or projet_actif_id()
    if not (objet or "").strip():
        raise Refus("L'objet de la demande est requis.")

    propres = _nettoyer_lignes(lignes)
    if not propres:
        raise Refus("Ajoutez au moins une ligne a la demande.")

    d = Demande(
        projet_id=pid,
        numero=prochain_numero(pid),
        objet=objet.strip(),
        localisation=(localisation or "").strip() or None,
        urgence=urgence if urgence in ("normale", "urgente", "critique") else "normale",
        besoin_pour=besoin_pour,
        commentaire=(commentaire or "").strip() or None,
        demandeur=demandeur,
        statut="soumise" if soumettre else "brouillon",
        soumise_le=datetime.utcnow() if soumettre else None,
    )
    for ligne in propres:
        d.lignes.append(LigneDemande(**ligne))

    db.session.add(d)
    db.session.commit()
    return d


def modifier(demande_id, objet=None, localisation=None, urgence=None,
             besoin_pour=None, commentaire=None, lignes=None, projet_id=None):
    """Modifie une demande encore ouverte.

    Une demande validee, refusee ou servie n'est plus modifiable : elle a
    servi de base a une decision, la changer apres coup la rendrait fausse.
    """
    d = _demande(demande_id, projet_id)
    if not d.modifiable:
        raise Refus(f"Une demande {d.statut_libelle.lower()} ne peut plus etre modifiee.")

    if objet is not None:
        if not objet.strip():
            raise Refus("L'objet de la demande est requis.")
        d.objet = objet.strip()
    if localisation is not None:
        d.localisation = localisation.strip() or None
    if urgence in ("normale", "urgente", "critique"):
        d.urgence = urgence
    if besoin_pour is not None:
        d.besoin_pour = besoin_pour
    if commentaire is not None:
        d.commentaire = commentaire.strip() or None

    if lignes is not None:
        propres = _nettoyer_lignes(lignes)
        if not propres:
            raise Refus("Une demande doit garder au moins une ligne.")
        d.lignes.clear()
        for ligne in propres:
            d.lignes.append(LigneDemande(**ligne))

    db.session.commit()
    return d


def changer_statut(demande_id, vers, par, motif=None, projet_id=None):
    """Applique une transition du circuit."""
    d = _demande(demande_id, projet_id)
    if vers not in TRANSITIONS.get(d.statut, ()):
        raise Refus(f"Passage de « {d.statut_libelle} » a « {vers} » impossible.")

    if vers == "refusee" and not (motif or "").strip():
        # Un refus sans raison est incomprehensible pour le demandeur, qui
        # refera la meme demande.
        raise Refus("Indiquez le motif du refus.")

    maintenant = datetime.utcnow()
    if vers == "soumise":
        d.soumise_le = maintenant
    elif vers in ("validee", "refusee"):
        d.decide_par = par
        d.decide_le = maintenant
        d.motif_decision = (motif or "").strip() or None
    elif vers == "brouillon":
        d.soumise_le = None

    d.statut = vers
    db.session.commit()
    return d


def servir(demande_id, depot_id, par, quantites=None, projet_id=None):
    """Marque la demande servie et ecrit les sorties de stock correspondantes.

    C'est le point ou le besoin devient une consommation. Les lignes libres
    (hors catalogue) sont marquees servies mais ne generent aucun mouvement :
    elles ne correspondent a rien de suivi en stock.

    `quantites` : {ligne_id: quantite reellement remise}. A defaut, la quantite
    demandee est retenue.
    """
    pid = projet_id or projet_actif_id()
    d = _demande(demande_id, pid)
    if "servie" not in TRANSITIONS.get(d.statut, ()):
        raise Refus(f"Une demande {d.statut_libelle.lower()} ne peut pas etre servie.")
    if not depot_id:
        raise Refus("Choisissez le depot qui fournit la marchandise.")

    quantites = quantites or {}
    mouvements = []

    for ligne in d.lignes:
        qte = quantites.get(ligne.id, ligne.quantite)
        try:
            qte = float(qte)
        except (TypeError, ValueError):
            raise Refus(f"Quantite illisible pour « {ligne.libelle} ».")
        if qte < 0:
            raise Refus(f"Quantite negative pour « {ligne.libelle} ».")

        ligne.quantite_servie = qte
        if not ligne.catalogue or qte == 0:
            continue

        # Meme garde-fou que la saisie manuelle d'un mouvement : on ne sort pas
        # d'un depot ce qu'il ne contient pas.
        dispo = svc_stock.stock_article_depot(ligne.article_id, depot_id, pid)
        if qte > dispo + 1e-9:
            raise Refus(
                f"Stock insuffisant pour « {ligne.libelle} » : "
                f"{dispo:g} {ligne.unite} disponible(s) dans ce depot."
            )
        mouvements.append(Mouvement(
            projet_id=pid,
            type="sortie",
            article_id=ligne.article_id,
            depot_source_id=depot_id,
            quantite=qte,
            reference=f"DEM-{d.numero}",
            motif=f"Demande #{d.numero} — {d.objet}",
            saisi_par=par,
        ))

    # Tout ou rien : une demande a moitie servie laisserait un stock faux et
    # une demande dans un etat impossible a interpreter.
    for m in mouvements:
        db.session.add(m)
    d.statut = "servie"
    d.servie_par = par
    d.servie_le = datetime.utcnow()
    d.depot_id = depot_id
    db.session.commit()
    return d, len(mouvements)


def supprimer(demande_id, projet_id=None):
    """Supprime une demande encore ouverte.

    Une demande servie a genere des mouvements de stock : la supprimer
    laisserait ces ecritures sans justification.
    """
    d = _demande(demande_id, projet_id)
    if d.statut == "servie":
        raise Refus("Une demande servie ne peut pas etre supprimee : elle justifie des sorties de stock.")
    db.session.delete(d)
    db.session.commit()


# --------------------------------------------------------------------------
def _nettoyer_lignes(lignes):
    """Valide et normalise les lignes recues d'un formulaire ou de l'API."""
    propres = []
    for brute in lignes or []:
        article_id = brute.get("article_id") or None
        libre = (brute.get("designation_libre") or "").strip() or None
        if article_id and libre:
            # L'un exclut l'autre : au moment de servir, on ne saurait pas
            # laquelle des deux fait foi.
            libre = None
        if not article_id and not libre:
            continue

        try:
            qte = float(brute.get("quantite") or 0)
        except (TypeError, ValueError):
            raise Refus("Quantite illisible.")
        if qte <= 0:
            raise Refus(f"La quantite de « {libre or 'la ligne'} » doit etre positive.")

        propres.append({
            "article_id": int(article_id) if article_id else None,
            "designation_libre": libre,
            "quantite": qte,
            "unite": (brute.get("unite") or "U").strip()[:16] or "U",
            "note": (brute.get("note") or "").strip()[:255] or None,
        })
    return propres
