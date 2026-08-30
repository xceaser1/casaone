"""Modele Livraison de beton (saisie manuelle dans l'application).

Une ligne = une livraison de beton par une centrale, rattachee a une zone et
un niveau. Le mois est derive de la date pour les agregats.
"""
from datetime import datetime

from .db import db


class Livraison(db.Model):
    __tablename__ = "livraisons"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    date_livraison = db.Column(db.Date, nullable=False, index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), index=True)
    niveau_id = db.Column(db.Integer, db.ForeignKey("niveaux.id"), index=True)
    fournisseur = db.Column(db.String(96), index=True)
    volume = db.Column(db.Float, default=0.0)          # m3 livres
    classe_beton = db.Column(db.String(24))            # B25, B30, B35...
    bon_livraison = db.Column(db.String(48))           # n0 du bon
    mois = db.Column(db.String(7), index=True)         # AAAA-MM (agregats)
    saisi_par = db.Column(db.String(64))
    maj_le = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = db.relationship("Zone", lazy="joined")
    niveau = db.relationship("Niveau", lazy="joined")
