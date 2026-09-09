"""Agenda du chantier : evenements saisis a la main.

Le calendrier montre deux choses de nature differente. D'un cote ce que
l'application sait deja — coulages, livraisons, echeances de demandes,
comptages : ces dates existent en base, personne n'a a les ressaisir, et les
reproduire ici serait le meilleur moyen de les voir diverger. De l'autre ce
qu'elle ignore — une reunion de chantier, la visite du bureau de controle, un
jalon contractuel, une coupure d'eau annoncee. Seule cette seconde categorie a
besoin d'une table.

Un evenement est a la journee par defaut : sur un chantier on retient « jeudi,
reception des aciers », rarement « jeudi 14h07 ». L'heure reste possible mais
facultative.
"""
from datetime import date, datetime

from .db import db

# Type d'evenement : determine la couleur et l'icone. Volontairement court —
# une liste de vingt categories finit toujours en « Autre ».
TYPES_EVENEMENT = [
    ("jalon", "Jalon"),
    ("reunion", "Réunion"),
    ("visite", "Visite / contrôle"),
    ("intervention", "Intervention"),
    ("conge", "Congé / arrêt"),
    ("autre", "Autre"),
]

COULEURS = {
    "jalon": "violet",
    "reunion": "bleu",
    "visite": "cyan",
    "intervention": "ambre",
    "conge": "gris",
    "autre": "gris",
}

ICONES = {
    "jalon": "validation",
    "reunion": "mainoeuvre",
    "visite": "recherche",
    "intervention": "engins",
    "conge": "presence",
    "autre": "dashboard",
}


class Evenement(db.Model):
    """Un rendez-vous, un jalon, une intervention — ce que la base ignore."""

    __tablename__ = "evenements"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)

    titre = db.Column(db.String(160), nullable=False)
    type_evenement = db.Column(db.String(16), default="autre", nullable=False, index=True)

    # `fin` est inclusive : un evenement du 3 au 5 occupe bien trois cases du
    # calendrier. Une fin nulle vaut « le meme jour que le debut ».
    debut = db.Column(db.Date, nullable=False, index=True)
    fin = db.Column(db.Date, index=True)
    heure = db.Column(db.String(5))          # "08:30", facultatif
    lieu = db.Column(db.String(120))
    description = db.Column(db.Text)

    cree_par = db.Column(db.String(64))
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    projet = db.relationship("Projet", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("fin IS NULL OR fin >= debut", name="ck_evenement_ordre_dates"),
    )

    # --- affichage ----------------------------------------------------------
    @property
    def type_libelle(self):
        return dict(TYPES_EVENEMENT).get(self.type_evenement, self.type_evenement)

    @property
    def couleur(self):
        return COULEURS.get(self.type_evenement, "gris")

    @property
    def icone(self):
        return ICONES.get(self.type_evenement, "dashboard")

    @property
    def fin_effective(self):
        return self.fin or self.debut

    @property
    def duree_jours(self):
        return (self.fin_effective - self.debut).days + 1

    @property
    def passe(self):
        return self.fin_effective < date.today()

    def couvre(self, jour):
        return self.debut <= jour <= self.fin_effective

    def __repr__(self):
        return f"<Evenement {self.debut} {self.titre!r}>"
