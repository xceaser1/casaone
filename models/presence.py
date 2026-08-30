"""Pointage par badge QR : une ligne = un evenement de presence.

Un ouvrier possede un badge QR (encode un jeton signe identifiant projet +
matricule + nom). Le pointeur scanne le badge sur son telephone : on enregistre
une entree (et eventuellement une sortie) pour la journee. Un seul enregistrement
par ouvrier / jour / type : re-scanner met a jour l'heure.

Donnees rattachees au projet du badge : aucun melange entre projets.
"""
from datetime import date, datetime

from .db import db

TYPES = ("entree", "sortie")


class Presence(db.Model):
    __tablename__ = "presences"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    matricule = db.Column(db.String(24), index=True)
    nom = db.Column(db.String(128), index=True)
    jour = db.Column(db.Date, default=date.today, index=True)
    type = db.Column(db.String(8), default="entree", nullable=False)  # entree / sortie
    heure = db.Column(db.DateTime, default=datetime.now)
    methode = db.Column(db.String(8), default="scan")  # scan / manuel
    saisi_par = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint("projet_id", "jour", "matricule", "nom", "type", name="uq_presence_jour"),
    )
