"""Gestion de stock : depots, articles et mouvements.

Principe : le stock n'est PAS stocke dans une colonne modifiable, il est
recalcule a partir du journal des mouvements. C'est plus sur sur un chantier :
chaque quantite est justifiee par une ecriture datee et nominative, et on peut
reconstituer l'historique complet d'un article ou d'un depot.

Trois types de mouvement :
  - entree    : reception fournisseur          -> + sur le depot de destination
  - sortie    : consommation sur le chantier   -> - sur le depot source
  - transfert : deplacement entre deux depots  -> - sur la source, + sur la destination

Toutes les tables sont rattachees a un projet : aucun melange entre chantiers.
"""
from datetime import date, datetime

from .db import db

TYPES = (
    ("entree", "Entree"),
    ("sortie", "Sortie"),
    ("transfert", "Transfert"),
)


class Depot(db.Model):
    """Lieu de stockage : magasin central, aire de ferraillage, base vie..."""

    __tablename__ = "depots"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    code = db.Column(db.String(24), nullable=False, index=True)
    nom = db.Column(db.String(120), nullable=False)
    emplacement = db.Column(db.String(120))
    responsable = db.Column(db.String(120))
    actif = db.Column(db.Boolean, default=True, nullable=False)
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("projet_id", "code", name="uq_depot_projet_code"),)

    @property
    def initiales(self):
        return (self.code or self.nom or "?")[:2].upper()

    def __repr__(self):
        return f"<Depot {self.code}>"


class Article(db.Model):
    """Reference stockee : ciment, acier, coffrage, carburant..."""

    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    code = db.Column(db.String(32), nullable=False, index=True)
    designation = db.Column(db.String(160), nullable=False)
    categorie = db.Column(db.String(64), index=True)
    unite = db.Column(db.String(16), default="U")        # U, kg, t, m3, sac, ml...
    seuil_alerte = db.Column(db.Float, default=0.0)      # 0 = pas d'alerte
    actif = db.Column(db.Boolean, default=True, nullable=False)
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("projet_id", "code", name="uq_article_projet_code"),)

    def __repr__(self):
        return f"<Article {self.code}>"


class Mouvement(db.Model):
    """Une ecriture de stock. Source de verite des quantites."""

    __tablename__ = "mouvements_stock"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    type = db.Column(db.String(12), nullable=False, index=True)   # entree / sortie / transfert
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # Depot d'ou sort la marchandise (sortie, transfert)
    depot_source_id = db.Column(db.Integer, db.ForeignKey("depots.id", ondelete="CASCADE"), index=True)
    # Depot ou entre la marchandise (entree, transfert)
    depot_dest_id = db.Column(db.Integer, db.ForeignKey("depots.id", ondelete="CASCADE"), index=True)
    quantite = db.Column(db.Float, nullable=False, default=0.0)
    date_mouvement = db.Column(db.Date, default=date.today, index=True)
    reference = db.Column(db.String(64))     # bon de livraison, bon de sortie...
    motif = db.Column(db.String(255))
    saisi_par = db.Column(db.String(64))
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    article = db.relationship("Article", lazy="joined")
    source = db.relationship("Depot", foreign_keys=[depot_source_id], lazy="joined")
    destination = db.relationship("Depot", foreign_keys=[depot_dest_id], lazy="joined")

    @property
    def type_libelle(self):
        return dict(TYPES).get(self.type, self.type)

    def __repr__(self):
        return f"<Mouvement {self.type} {self.quantite}>"
