"""Modele Projet : portefeuille de chantiers.

Portee "portfolio" : chaque projet est une fiche (nom, client, budget,
avancement, statut...). Les tableaux de bord detailles restent rattaches au
projet principal (CASA ONE / CFAO) tant que les donnees d'un autre projet ne
sont pas importees.
"""
from datetime import date, datetime

from .db import db

# Statuts possibles : code -> (libelle, classe CSS de pastille)
STATUTS = {
    "planifie": ("Planifié", "bleu"),
    "en_cours": ("En cours", "vert"),
    "en_pause": ("En pause", "ambre"),
    "termine": ("Terminé", "gris"),
}


class Projet(db.Model):
    __tablename__ = "projets"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(24), unique=True, nullable=False, index=True)  # ex : CFAO
    nom = db.Column(db.String(120), nullable=False)                           # ex : CASA ONE
    client = db.Column(db.String(120))
    ville = db.Column(db.String(80))
    date_debut = db.Column(db.Date)
    date_fin = db.Column(db.Date)
    budget = db.Column(db.Float, default=0.0)
    avancement = db.Column(db.Float, default=0.0)          # 0..100
    statut = db.Column(db.String(16), default="en_cours", nullable=False)
    couleur = db.Column(db.String(9), default="#14683f")   # accent de la fiche
    est_principal = db.Column(db.Boolean, default=False, nullable=False)  # relie aux donnees live
    archive = db.Column(db.Boolean, default=False, nullable=False)
    # Code de pointage : si renseigne, l'auto-pointage (badge scanne par l'ouvrier
    # lui-meme) exige ce code. Vide = auto-pointage libre.
    pin_pointage = db.Column(db.String(12))
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    # --- affichage --------------------------------------------------------
    @property
    def statut_libelle(self):
        return STATUTS.get(self.statut, (self.statut, "gris"))[0]

    @property
    def statut_classe(self):
        return STATUTS.get(self.statut, (self.statut, "gris"))[1]

    @property
    def avancement_pct(self):
        return round(max(0.0, min(100.0, self.avancement or 0.0)), 1)

    @property
    def initiales(self):
        source = (self.code or self.nom or "?").strip()
        return source[:2].upper()

    def __repr__(self):
        return f"<Projet {self.code}>"

    # --- requetes utilitaires --------------------------------------------
    @staticmethod
    def actifs():
        """Projets non archives, principal d'abord puis par date de creation."""
        return (
            Projet.query.filter_by(archive=False)
            .order_by(Projet.est_principal.desc(), Projet.cree_le.asc())
            .all()
        )

    @staticmethod
    def principal():
        return Projet.query.filter_by(est_principal=True).first()
