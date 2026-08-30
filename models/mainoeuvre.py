"""Modeles pour le suivi de la main-d'oeuvre (canevas de pointage mensuel).

Une ligne = un ouvrier sur un mois donne. Le detail jour par jour du pointage
reste dans le fichier Excel source ; ici on stocke l'identite de l'ouvrier et
les agregats du mois (jours travailles, taux de presence, heures supplementaires).

ATTENTION : ce modele contient des donnees personnelles (nom, CIN). L'acces est
protege par la permission dediee « mainoeuvre » et reserve par defaut a l'admin.
"""
from datetime import datetime

from .db import db


class Ouvrier(db.Model):
    __tablename__ = "ouvriers"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    mois = db.Column(db.String(7), nullable=False, index=True)  # AAAA-MM
    matricule_chantier = db.Column(db.String(24), index=True)
    matricule_sage = db.Column(db.String(24))
    nom = db.Column(db.String(128), index=True)
    cin = db.Column(db.String(24), index=True)
    section = db.Column(db.String(64))
    fonction = db.Column(db.String(64), index=True)
    situation = db.Column(db.String(48), index=True)
    date_entree = db.Column(db.Date)

    # Agregats du mois calcules a l'import depuis les colonnes de pointage
    jours_travailles = db.Column(db.Float, default=0.0)   # somme des presences (1 / 0,5)
    jours_ouvres = db.Column(db.Integer, default=0)       # nb de jours pointes dans le mois
    heures_supp = db.Column(db.Float, default=0.0)
    taux_presence = db.Column(db.Float, default=0.0)      # % = jours_travailles / jours_ouvres

    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("projet_id", "mois", "matricule_chantier", "nom", name="uq_ouvrier_mois"),
        db.Index("ix_ouvrier_mois_fonction", "mois", "fonction"),
    )

    @property
    def cin_masque(self):
        """CIN partiellement masque (utilise si un jour on veut la vue reduite)."""
        if not self.cin:
            return ""
        c = self.cin.strip()
        return c[:4] + "•" * max(0, len(c) - 4)
