"""Modeles metier issus du fichier TABLEAU_DE_BORD_URB_PROJET_CASAONE.xlsx.

Le classeur Excel est organise en tableaux croises (une colonne par niveau).
En base on stocke le format long (une ligne = zone x niveau), beaucoup plus
souple pour filtrer, agreger et alimenter les graphiques.
"""
from datetime import datetime

from .db import db


class Niveau(db.Model):
    """Niveau de plancher : DALL, PHSS3 ... PH ETG 8. `ordre` = ordre physique."""

    __tablename__ = "niveaux"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    code = db.Column(db.String(24), nullable=False, index=True)  # unique par projet
    libelle = db.Column(db.String(64))
    ordre = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("projet_id", "code", name="uq_niveau_projet_code"),)

    def __repr__(self):
        return f"<Niveau {self.code}>"


class Bloc(db.Model):
    """Entite / batiment : MAO, MAC, MAE, IMM1, IMMA, IMMB, HOTEL, GBM, ESP."""

    __tablename__ = "blocs"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    code = db.Column(db.String(24), nullable=False, index=True)  # unique par projet
    libelle = db.Column(db.String(64))

    zones = db.relationship("Zone", back_populates="bloc")

    __table_args__ = (db.UniqueConstraint("projet_id", "code", name="uq_bloc_projet_code"),)


class Zone(db.Model):
    """Zone de coulage : A1..A9, B1..B11, C1..C8, H."""

    __tablename__ = "zones"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    code = db.Column(db.String(24), nullable=False, index=True)  # unique par projet
    bloc_id = db.Column(db.Integer, db.ForeignKey("blocs.id"), nullable=False)
    ordre = db.Column(db.Integer, default=0)

    bloc = db.relationship("Bloc", back_populates="zones", lazy="joined")

    __table_args__ = (db.UniqueConstraint("projet_id", "code", name="uq_zone_projet_code"),)


class Surface(db.Model):
    """Feuille "Tableau de surfaces" : surface prevue / surface coulee."""

    __tablename__ = "surfaces"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    niveau_id = db.Column(db.Integer, db.ForeignKey("niveaux.id", ondelete="CASCADE"), nullable=False, index=True)
    surface_totale = db.Column(db.Float, default=0.0)
    surface_coulee = db.Column(db.Float, default=0.0)
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
    niveau = db.relationship("Niveau", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("zone_id", "niveau_id", name="uq_surface_zone_niveau"),
        db.Index("ix_surface_niveau_zone", "niveau_id", "zone_id"),
    )

    @property
    def reste(self):
        return round((self.surface_totale or 0) - (self.surface_coulee or 0), 2)

    @property
    def avancement(self):
        if not self.surface_totale:
            return 0.0
        return round(100.0 * (self.surface_coulee or 0) / self.surface_totale, 2)


class ValidationPlan(db.Model):
    """Feuille "VALIDATION DES PLANS" : statut du plan par zone x niveau."""

    __tablename__ = "validations_plans"

    STATUTS = ["Valide", "En Cours", "Non Valide"]

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    niveau_id = db.Column(db.Integer, db.ForeignKey("niveaux.id", ondelete="CASCADE"), nullable=False, index=True)
    surface = db.Column(db.Float, default=0.0)
    statut = db.Column(db.String(24), default="En Cours", index=True)
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
    niveau = db.relationship("Niveau", lazy="joined")

    __table_args__ = (db.UniqueConstraint("zone_id", "niveau_id", name="uq_valid_zone_niveau"),)


class Betonnage(db.Model):
    """Feuille "Betonnage mensuelle" : journal des coulages (1 ligne = 1 coulage)."""

    __tablename__ = "betonnages"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    date_coulage = db.Column(db.Date, nullable=False, index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), index=True)
    niveau_id = db.Column(db.Integer, db.ForeignKey("niveaux.id"), index=True)
    bloc_libelle = db.Column(db.String(64))   # valeur brute Excel (ex "C7 95,90")
    niveau_libelle = db.Column(db.String(64))  # valeur brute Excel (ex "PH1ER ETAGE")
    surface = db.Column(db.Float, default=0.0)
    mois = db.Column(db.String(7), index=True)  # AAAA-MM, pour les agregats rapides
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
    niveau = db.relationship("Niveau", lazy="joined")


class DalleSurface(db.Model):
    """Feuilles "Dalle reticulee / Pleine / Post-Tension / Hourdis"."""

    __tablename__ = "dalles_surfaces"

    TYPES = ["Dalle Reticulee", "Dalle Pleine", "Dalle Post-Tension", "Dalle Hourdis"]

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    type_dalle = db.Column(db.String(48), nullable=False, index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    niveau_id = db.Column(db.Integer, db.ForeignKey("niveaux.id", ondelete="CASCADE"), nullable=False, index=True)
    surface_totale = db.Column(db.Float, default=0.0)
    surface_coulee = db.Column(db.Float, default=0.0)
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
    niveau = db.relationship("Niveau", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("type_dalle", "zone_id", "niveau_id", name="uq_dalle_zone_niveau"),
    )

    @property
    def avancement(self):
        if not self.surface_totale:
            return 0.0
        return round(100.0 * (self.surface_coulee or 0) / self.surface_totale, 2)


class Decompte(db.Model):
    """Feuille "SUIVIE DES COUTS" : situations budgetaires successives."""

    __tablename__ = "decomptes"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    libelle = db.Column(db.String(48), nullable=False)
    ordre = db.Column(db.Integer, default=0)
    montant = db.Column(db.Float, default=0.0)
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Parametre(db.Model):
    """Parametres d'un projet (montant marche, dates d'import, ...).

    Chaque parametre est rattache a un projet : deux projets peuvent avoir un
    montant de marche different sous la meme cle. Sans projet_id explicite, les
    helpers utilisent le projet actif (session) via services.contexte.
    """

    __tablename__ = "parametres"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    cle = db.Column(db.String(64), nullable=False, index=True)
    valeur = db.Column(db.String(255))
    libelle = db.Column(db.String(128))

    __table_args__ = (db.UniqueConstraint("projet_id", "cle", name="uq_parametre_projet_cle"),)

    @staticmethod
    def _pid(projet_id):
        if projet_id is not None:
            return projet_id
        from services.contexte import projet_actif_id
        return projet_actif_id()

    @staticmethod
    def get(cle, defaut=None, projet_id=None):
        p = Parametre.query.filter_by(cle=cle, projet_id=Parametre._pid(projet_id)).first()
        return p.valeur if p else defaut

    @staticmethod
    def get_float(cle, defaut=0.0, projet_id=None):
        try:
            return float(Parametre.get(cle, defaut, projet_id))
        except (TypeError, ValueError):
            return defaut

    @staticmethod
    def set(cle, valeur, libelle=None, projet_id=None):
        pid = Parametre._pid(projet_id)
        p = Parametre.query.filter_by(cle=cle, projet_id=pid).first()
        if p is None:
            p = Parametre(cle=cle, valeur=str(valeur), libelle=libelle, projet_id=pid)
            db.session.add(p)
        else:
            p.valeur = str(valeur)
            if libelle:
                p.libelle = libelle
        return p


class JournalImport(db.Model):
    """Historique des imports Excel (tracabilite)."""

    __tablename__ = "journal_imports"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    fichier = db.Column(db.String(255))
    utilisateur = db.Column(db.String(64))
    date_import = db.Column(db.DateTime, default=datetime.utcnow)
    statut = db.Column(db.String(16))  # OK / ERREUR
    resume = db.Column(db.Text)
