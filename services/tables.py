"""Registre des tables metier exposees par l'interface.

Chaque table declare ses colonnes, sa requete de base et la fa�on de serialiser
une ligne. Les routes generiques (/data/<table>) s'appuient dessus : ajouter une
nouvelle table ne demande donc ni nouvelle route ni nouveau template.

Pagination, recherche, filtres et tri sont TOUJOURS executes en SQL.
"""
from sqlalchemy import asc, desc, func, or_

from models.db import db
from models.livraison import Livraison
from models.engin import Engin
from models.mainoeuvre import Ouvrier
from models.metier import Betonnage, Bloc, DalleSurface, Decompte, Niveau, Surface, ValidationPlan, Zone
from services.contexte import projet_actif_id


class TableSpec:
    def __init__(self, cle, titre, module, modele, colonnes, base_query, serialiser, champs_edition):
        self.cle = cle
        self.titre = titre
        self.module = module
        self.modele = modele
        self.colonnes = colonnes          # liste de dicts {cle,label,type,tri,filtre}
        self.base_query = base_query      # callable -> Query
        self.serialiser = serialiser      # callable(obj) -> dict
        self.champs_edition = champs_edition  # {champ: type} pour le CRUD

    def colonne(self, cle):
        return next((c for c in self.colonnes if c["cle"] == cle), None)


# --------------------------------------------------------------------------
# Expressions SQL reutilisables
# --------------------------------------------------------------------------
def _q_surfaces():
    return (
        Surface.query.join(Zone, Surface.zone_id == Zone.id)
        .join(Bloc, Zone.bloc_id == Bloc.id)
        .join(Niveau, Surface.niveau_id == Niveau.id)
    )


def _q_validations():
    return (
        ValidationPlan.query.join(Zone, ValidationPlan.zone_id == Zone.id)
        .join(Bloc, Zone.bloc_id == Bloc.id)
        .join(Niveau, ValidationPlan.niveau_id == Niveau.id)
    )


def _q_dalles():
    return (
        DalleSurface.query.join(Zone, DalleSurface.zone_id == Zone.id)
        .join(Bloc, Zone.bloc_id == Bloc.id)
        .join(Niveau, DalleSurface.niveau_id == Niveau.id)
    )


def _q_betonnage():
    return (
        Betonnage.query.outerjoin(Zone, Betonnage.zone_id == Zone.id)
        .outerjoin(Bloc, Zone.bloc_id == Bloc.id)
        .outerjoin(Niveau, Betonnage.niveau_id == Niveau.id)
    )


def _q_livraisons():
    return (
        Livraison.query.outerjoin(Zone, Livraison.zone_id == Zone.id)
        .outerjoin(Bloc, Zone.bloc_id == Bloc.id)
        .outerjoin(Niveau, Livraison.niveau_id == Niveau.id)
    )


def _q_engins():
    return Engin.query.outerjoin(Zone, Engin.zone_id == Zone.id).outerjoin(Bloc, Zone.bloc_id == Bloc.id)


# --------------------------------------------------------------------------
# Colonnes triables / filtrables : cle -> expression SQL
# --------------------------------------------------------------------------
EXPRESSIONS = {
    "surfaces": {
        "bloc": Bloc.code,
        "zone": Zone.code,
        "niveau": Niveau.code,
        "_ordre_niveau": Niveau.ordre,
        "surface_totale": Surface.surface_totale,
        "surface_coulee": Surface.surface_coulee,
        "reste": Surface.surface_totale - Surface.surface_coulee,
        "avancement": func.round(
            100.0 * Surface.surface_coulee / func.nullif(Surface.surface_totale, 0), 2
        ),
    },
    "validation": {
        "bloc": Bloc.code,
        "zone": Zone.code,
        "niveau": Niveau.code,
        "_ordre_niveau": Niveau.ordre,
        "surface": ValidationPlan.surface,
        "statut": ValidationPlan.statut,
    },
    "dalles": {
        "type_dalle": DalleSurface.type_dalle,
        "bloc": Bloc.code,
        "zone": Zone.code,
        "niveau": Niveau.code,
        "_ordre_niveau": Niveau.ordre,
        "surface_totale": DalleSurface.surface_totale,
        "surface_coulee": DalleSurface.surface_coulee,
        "avancement": func.round(
            100.0 * DalleSurface.surface_coulee / func.nullif(DalleSurface.surface_totale, 0), 2
        ),
    },
    "betonnage": {
        "date_coulage": Betonnage.date_coulage,
        "mois": Betonnage.mois,
        "bloc": Bloc.code,
        "zone": Zone.code,
        "niveau": Niveau.code,
        "bloc_libelle": Betonnage.bloc_libelle,
        "niveau_libelle": Betonnage.niveau_libelle,
        "surface": Betonnage.surface,
    },
    "couts": {
        "libelle": Decompte.libelle,
        "ordre": Decompte.ordre,
        "montant": Decompte.montant,
    },
    "ouvriers": {
        "mois": Ouvrier.mois,
        "matricule_chantier": Ouvrier.matricule_chantier,
        "nom": Ouvrier.nom,
        "cin": Ouvrier.cin,
        "fonction": Ouvrier.fonction,
        "situation": Ouvrier.situation,
        "jours_travailles": Ouvrier.jours_travailles,
        "heures_supp": Ouvrier.heures_supp,
        "taux_presence": Ouvrier.taux_presence,
    },
    "livraisons": {
        "date_livraison": Livraison.date_livraison,
        "mois": Livraison.mois,
        "bloc": Bloc.code,
        "zone": Zone.code,
        "niveau": Niveau.code,
        "fournisseur": Livraison.fournisseur,
        "classe_beton": Livraison.classe_beton,
        "volume": Livraison.volume,
        "bon_livraison": Livraison.bon_livraison,
    },
    "engins": {
        "type_engin": Engin.type_engin,
        "designation": Engin.designation,
        "marque": Engin.marque,
        "etat": Engin.etat,
        "zone": Zone.code,
        "fournisseur": Engin.fournisseur,
        "date_entree": Engin.date_entree,
    },
}

# Colonnes prises en compte par la recherche globale
RECHERCHE = {
    "surfaces": [Bloc.code, Zone.code, Niveau.code],
    "validation": [Bloc.code, Zone.code, Niveau.code, ValidationPlan.statut],
    "dalles": [DalleSurface.type_dalle, Bloc.code, Zone.code, Niveau.code],
    "betonnage": [Bloc.code, Zone.code, Niveau.code, Betonnage.bloc_libelle, Betonnage.niveau_libelle],
    "couts": [Decompte.libelle],
    "ouvriers": [Ouvrier.nom, Ouvrier.matricule_chantier, Ouvrier.cin, Ouvrier.fonction],
    "livraisons": [Zone.code, Niveau.code, Livraison.fournisseur, Livraison.classe_beton, Livraison.bon_livraison],
    "engins": [Engin.type_engin, Engin.designation, Engin.marque, Engin.fournisseur],
}


# --------------------------------------------------------------------------
# Serialiseurs
# --------------------------------------------------------------------------
def _ser_surface(o):
    return {
        "id": o.id,
        "bloc": o.zone.bloc.code,
        "zone": o.zone.code,
        "niveau": o.niveau.code,
        "surface_totale": round(o.surface_totale or 0, 2),
        "surface_coulee": round(o.surface_coulee or 0, 2),
        "reste": o.reste,
        "avancement": o.avancement,
    }


def _ser_validation(o):
    return {
        "id": o.id,
        "bloc": o.zone.bloc.code,
        "zone": o.zone.code,
        "niveau": o.niveau.code,
        "surface": round(o.surface or 0, 2),
        "statut": o.statut,
    }


def _ser_dalle(o):
    return {
        "id": o.id,
        "type_dalle": o.type_dalle,
        "bloc": o.zone.bloc.code,
        "zone": o.zone.code,
        "niveau": o.niveau.code,
        "surface_totale": round(o.surface_totale or 0, 2),
        "surface_coulee": round(o.surface_coulee or 0, 2),
        "avancement": o.avancement,
    }


def _ser_betonnage(o):
    return {
        "id": o.id,
        "date_coulage": o.date_coulage.isoformat() if o.date_coulage else "",
        "mois": o.mois or "",
        "bloc": o.zone.bloc.code if o.zone else "",
        "zone": o.zone.code if o.zone else "",
        "niveau": o.niveau.code if o.niveau else "",
        "bloc_libelle": o.bloc_libelle or "",
        "niveau_libelle": o.niveau_libelle or "",
        "surface": round(o.surface or 0, 2),
    }


def _ser_cout(o):
    return {"id": o.id, "ordre": o.ordre, "libelle": o.libelle, "montant": round(o.montant or 0, 2)}


def _ser_ouvrier(o):
    return {
        "id": o.id,
        "mois": o.mois,
        "matricule_chantier": o.matricule_chantier or "",
        "nom": o.nom or "",
        "cin": o.cin or "",
        "fonction": o.fonction or "",
        "situation": o.situation or "",
        "date_entree": o.date_entree.isoformat() if o.date_entree else "",
        "jours_travailles": round(o.jours_travailles or 0, 2),
        "heures_supp": round(o.heures_supp or 0, 2),
        "taux_presence": round(o.taux_presence or 0, 2),
    }


def _ser_livraison(o):
    return {
        "id": o.id,
        "date_livraison": o.date_livraison.isoformat() if o.date_livraison else "",
        "mois": o.mois or "",
        "bloc": o.zone.bloc.code if o.zone else "",
        "zone": o.zone.code if o.zone else "",
        "niveau": o.niveau.code if o.niveau else "",
        "fournisseur": o.fournisseur or "",
        "classe_beton": o.classe_beton or "",
        "volume": round(o.volume or 0, 2),
        "bon_livraison": o.bon_livraison or "",
    }


def _ser_engin(o):
    return {
        "id": o.id,
        "type_engin": o.type_engin or "",
        "designation": o.designation or "",
        "marque": o.marque or "",
        "etat": o.etat or "",
        "zone": o.zone.code if o.zone else "",
        "fournisseur": o.fournisseur or "",
        "date_entree": o.date_entree.isoformat() if o.date_entree else "",
    }


# --------------------------------------------------------------------------
# Declaration des tables
# --------------------------------------------------------------------------
def col(cle, label, type_="texte", filtre=None, tri=True, edit=False):
    return {"cle": cle, "label": label, "type": type_, "filtre": filtre, "tri": tri, "edit": edit}


TABLES = {
    "surfaces": TableSpec(
        "surfaces",
        "Tableau de surfaces",
        "surfaces",
        Surface,
        [
            col("bloc", "Bloc", filtre="select"),
            col("zone", "Zone", filtre="select"),
            col("niveau", "Niveau", filtre="select"),
            col("surface_totale", "Surface totale (m2)", "nombre", edit=True),
            col("surface_coulee", "Surface coulee (m2)", "nombre", edit=True),
            col("reste", "Reste (m2)", "nombre"),
            col("avancement", "Avancement", "pourcent"),
        ],
        _q_surfaces,
        _ser_surface,
        {"surface_totale": float, "surface_coulee": float, "zone_id": int, "niveau_id": int},
    ),
    "betonnage": TableSpec(
        "betonnage",
        "Betonnage mensuelle",
        "betonnage",
        Betonnage,
        [
            col("date_coulage", "Date", "date", filtre="date", edit=True),
            col("mois", "Mois", filtre="select"),
            col("bloc", "Bloc", filtre="select"),
            col("zone", "Zone", filtre="select"),
            col("niveau", "Niveau", filtre="select"),
            col("bloc_libelle", "Libelle Excel", filtre="texte"),
            col("surface", "Surface coulee (m2)", "nombre", edit=True),
        ],
        _q_betonnage,
        _ser_betonnage,
        {"surface": float, "zone_id": int, "niveau_id": int, "date_coulage": "date"},
    ),
    "validation": TableSpec(
        "validation",
        "Validation des plans",
        "validation",
        ValidationPlan,
        [
            col("bloc", "Bloc", filtre="select"),
            col("zone", "Zone", filtre="select"),
            col("niveau", "Niveau", filtre="select"),
            col("surface", "Surface (m2)", "nombre", edit=True),
            col("statut", "Statut", "statut", filtre="select", edit=True),
        ],
        _q_validations,
        _ser_validation,
        {"surface": float, "statut": str, "zone_id": int, "niveau_id": int},
    ),
    "dalles": TableSpec(
        "dalles",
        "Dalles",
        "dalles",
        DalleSurface,
        [
            col("type_dalle", "Type de dalle", filtre="select"),
            col("bloc", "Bloc", filtre="select"),
            col("zone", "Zone", filtre="select"),
            col("niveau", "Niveau", filtre="select"),
            col("surface_totale", "Surface totale (m2)", "nombre", edit=True),
            col("surface_coulee", "Surface coulee (m2)", "nombre", edit=True),
            col("avancement", "Avancement", "pourcent"),
        ],
        _q_dalles,
        _ser_dalle,
        {"surface_totale": float, "surface_coulee": float, "type_dalle": str, "zone_id": int, "niveau_id": int},
    ),
    "couts": TableSpec(
        "couts",
        "Suivi des couts",
        "couts",
        Decompte,
        [
            col("ordre", "N ordre", "nombre"),
            col("libelle", "Decompte", filtre="texte", edit=True),
            col("montant", "Montant (MAD)", "monnaie", edit=True),
        ],
        lambda: Decompte.query,
        _ser_cout,
        {"libelle": str, "montant": float, "ordre": int},
    ),
    "ouvriers": TableSpec(
        "ouvriers",
        "Main-d'oeuvre",
        "mainoeuvre",
        Ouvrier,
        [
            col("mois", "Mois", filtre="select"),
            col("matricule_chantier", "Matricule"),
            col("nom", "Nom & Prenom", filtre="texte"),
            col("cin", "CIN"),
            col("fonction", "Fonction", filtre="select"),
            col("situation", "Situation", filtre="select"),
            col("date_entree", "Date d'entree", "date"),
            col("jours_travailles", "Jours travailles", "nombre"),
            col("heures_supp", "H. supp", "nombre"),
            col("taux_presence", "Presence", "pourcent"),
        ],
        lambda: Ouvrier.query,
        _ser_ouvrier,
        {},  # pas d'edition manuelle : la source fait foi (import mensuel)
    ),
    "livraisons": TableSpec(
        "livraisons",
        "Livraisons de beton",
        "livraisons",
        Livraison,
        [
            col("date_livraison", "Date", "date", filtre="date", edit=True),
            col("mois", "Mois", filtre="select"),
            col("zone", "Zone", filtre="select"),
            col("niveau", "Niveau", filtre="select"),
            col("fournisseur", "Fournisseur", filtre="select", edit=True),
            col("classe_beton", "Classe", filtre="select", edit=True),
            col("volume", "Volume (m3)", "nombre", edit=True),
            col("bon_livraison", "N. bon", edit=True),
        ],
        _q_livraisons,
        _ser_livraison,
        {
            "date_livraison": "date",
            "zone_id": int,
            "niveau_id": int,
            "fournisseur": str,
            "classe_beton": str,
            "volume": float,
            "bon_livraison": str,
        },
    ),
    "engins": TableSpec(
        "engins",
        "Materiel et engins",
        "engins",
        Engin,
        [
            col("type_engin", "Type", filtre="select", edit=True),
            col("designation", "Designation / N", edit=True),
            col("marque", "Marque", edit=True),
            col("etat", "Etat", filtre="select", edit=True),
            col("zone", "Zone", filtre="select"),
            col("fournisseur", "Fournisseur", filtre="select", edit=True),
            col("date_entree", "Entree chantier", "date", edit=True),
        ],
        _q_engins,
        _ser_engin,
        {
            "type_engin": str,
            "designation": str,
            "marque": str,
            "etat": str,
            "zone_id": int,
            "fournisseur": str,
            "date_entree": "date",
        },
    ),
}


# --------------------------------------------------------------------------
# Requete paginee generique
# --------------------------------------------------------------------------
def interroger(cle_table, params, page_size_max=200):
    """Applique recherche + filtres + tri + pagination, cote serveur."""
    spec = TABLES[cle_table]
    q = spec.base_query().filter(spec.modele.projet_id == projet_actif_id())
    exprs = EXPRESSIONS[cle_table]

    # --- recherche globale
    recherche = (params.get("q") or "").strip()
    if recherche:
        motif = f"%{recherche}%"
        q = q.filter(or_(*[c.like(motif) for c in RECHERCHE[cle_table]]))

    # --- filtres par colonne (f_<colonne>=valeur)
    for cle, valeur in params.items():
        if not cle.startswith("f_") or not valeur:
            continue
        nom = cle[2:]
        expr = exprs.get(nom)
        if expr is None:
            continue
        valeurs = [v for v in str(valeur).split("|") if v]
        q = q.filter(expr.in_(valeurs)) if len(valeurs) > 1 else q.filter(expr == valeurs[0])

    # --- plage de dates (betonnage)
    if cle_table == "betonnage":
        if params.get("date_min"):
            q = q.filter(Betonnage.date_coulage >= params["date_min"])
        if params.get("date_max"):
            q = q.filter(Betonnage.date_coulage <= params["date_max"])

    total = q.order_by(None).count()

    # --- tri
    tri = params.get("tri") or ("date_coulage" if cle_table == "betonnage" else "zone")
    sens = (params.get("sens") or "asc").lower()
    expr_tri = exprs.get(tri)
    if expr_tri is not None:
        q = q.order_by(desc(expr_tri) if sens == "desc" else asc(expr_tri))
    if "_ordre_niveau" in exprs and tri != "niveau":
        q = q.order_by(asc(exprs["_ordre_niveau"]))

    # --- pagination
    try:
        page = max(1, int(params.get("page", 1)))
        taille = min(int(params.get("taille", 25)), page_size_max)
    except (TypeError, ValueError):
        page, taille = 1, 25

    lignes = q.limit(taille).offset((page - 1) * taille).all()

    return {
        "total": total,
        "page": page,
        "taille": taille,
        "pages": max(1, (total + taille - 1) // taille),
        "lignes": [spec.serialiser(o) for o in lignes],
    }


def valeurs_filtres(cle_table):
    """Valeurs distinctes pour alimenter les listes deroulantes de filtres."""
    spec = TABLES[cle_table]
    exprs = EXPRESSIONS[cle_table]
    pid = projet_actif_id()
    resultat = {}
    for c in spec.colonnes:
        if c["filtre"] != "select":
            continue
        expr = exprs.get(c["cle"])
        if expr is None:
            continue
        base = spec.base_query().filter(spec.modele.projet_id == pid).with_entities(expr).distinct()
        valeurs = [v[0] for v in base.all() if v[0] not in (None, "")]
        if c["cle"] == "niveau":
            ordres = {n.code: n.ordre for n in Niveau.query.filter_by(projet_id=pid).all()}
            valeurs.sort(key=lambda v: ordres.get(v, 99))
        else:
            valeurs.sort(key=str)
        resultat[c["cle"]] = valeurs
    return resultat


def totaux(cle_table, params):
    """Totaux de la selection courante (affiches en pied de tableau)."""
    spec = TABLES[cle_table]
    exprs = EXPRESSIONS[cle_table]
    q = spec.base_query().filter(spec.modele.projet_id == projet_actif_id())
    recherche = (params.get("q") or "").strip()
    if recherche:
        motif = f"%{recherche}%"
        q = q.filter(or_(*[c.like(motif) for c in RECHERCHE[cle_table]]))
    for cle, valeur in params.items():
        if cle.startswith("f_") and valeur and exprs.get(cle[2:]) is not None:
            q = q.filter(exprs[cle[2:]] == valeur)
    champs = {
        "surfaces": [("surface_totale", Surface.surface_totale), ("surface_coulee", Surface.surface_coulee)],
        "validation": [("surface", ValidationPlan.surface)],
        "dalles": [
            ("surface_totale", DalleSurface.surface_totale),
            ("surface_coulee", DalleSurface.surface_coulee),
        ],
        "betonnage": [("surface", Betonnage.surface)],
        "couts": [("montant", Decompte.montant)],
        "ouvriers": [
            ("jours_travailles", Ouvrier.jours_travailles),
            ("heures_supp", Ouvrier.heures_supp),
        ],
        "livraisons": [("volume", Livraison.volume)],
        "engins": [],
    }[cle_table]
    res = {}
    for nom, expr in champs:
        val = q.with_entities(func.coalesce(func.sum(expr), 0.0)).scalar() or 0.0
        res[nom] = round(val, 2)
    return res


def toutes_les_lignes(cle_table, params, limite=100000):
    """Lignes completes filtrees (pour l'export Excel/CSV)."""
    p = dict(params)
    p["page"] = 1
    p["taille"] = limite
    return interroger(cle_table, p, page_size_max=limite)["lignes"]
