"""Modele Engin : parc materiel du chantier (saisie manuelle)."""
from datetime import datetime

from .db import db


class Engin(db.Model):
    __tablename__ = "engins"

    ETATS = ["En service", "En panne", "A l'arret", "En maintenance"]

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    type_engin = db.Column(db.String(48), index=True)
    designation = db.Column(db.String(96))
    marque = db.Column(db.String(64))
    etat = db.Column(db.String(32), default="En service", index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), index=True)
    fournisseur = db.Column(db.String(96))
    date_entree = db.Column(db.Date)
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
