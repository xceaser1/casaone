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
    ("regularisation", "Regularisation"),
)

# Etats d'un inventaire physique.
STATUTS_INVENTAIRE = (
    ("ouvert", "En cours de comptage"),
    ("valide", "Valide"),
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
    # Prix unitaire d'achat. Sert a valoriser le stock et a chiffrer la
    # consommation ; 0 signifie simplement "non renseigne".
    prix_unitaire = db.Column(db.Float, default=0.0)
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
    # Qui a livre. Sans ce champ, impossible de dire ce qui vient de qui.
    fournisseur = db.Column(db.String(120), index=True)
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


class Inventaire(db.Model):
    """Comptage physique d'un depot, a une date donnee.

    Le stock affiche par l'application est THEORIQUE : il se deduit du journal
    des mouvements. Sur un chantier, il derive du reel — casse, perte, sortie
    non saisie. Sans moyen de le recaler, les chiffres finissent par n'etre
    plus crus, et le module entier perd son interet.

    Un inventaire fige le theorique au moment du comptage, recoit les
    quantites reellement comptees, puis, a la validation, ecrit les mouvements
    de regularisation correspondants. L'ecart reste ainsi visible et justifie,
    au lieu d'etre corrige en silence.
    """

    __tablename__ = "inventaires"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    depot_id = db.Column(db.Integer, db.ForeignKey("depots.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    date_comptage = db.Column(db.Date, default=date.today, index=True)
    statut = db.Column(db.String(12), default="ouvert", nullable=False, index=True)
    note = db.Column(db.String(255))

    ouvert_par = db.Column(db.String(64))
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)
    valide_par = db.Column(db.String(64))
    valide_le = db.Column(db.DateTime)

    depot = db.relationship("Depot", lazy="joined")
    lignes = db.relationship(
        "LigneInventaire", back_populates="inventaire",
        cascade="all, delete-orphan", lazy="selectin", order_by="LigneInventaire.id",
    )

    __table_args__ = (
        db.UniqueConstraint("projet_id", "numero", name="uq_inventaire_projet_numero"),
    )

    @property
    def statut_libelle(self):
        return dict(STATUTS_INVENTAIRE).get(self.statut, self.statut)

    @property
    def ouvert(self):
        return self.statut == "ouvert"

    @property
    def nb_ecarts(self):
        return sum(1 for l in self.lignes if l.ecart_significatif)

    def __repr__(self):
        return f"<Inventaire #{self.numero} {self.statut}>"


class LigneInventaire(db.Model):
    """Un article compte : theorique fige, quantite comptee, ecart."""

    __tablename__ = "lignes_inventaire"

    id = db.Column(db.Integer, primary_key=True)
    inventaire_id = db.Column(db.Integer, db.ForeignKey("inventaires.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # Fige a l'ouverture : le theorique peut bouger pendant le comptage, et
    # l'ecart doit se lire par rapport a ce qui etait affiche ce jour-la.
    theorique = db.Column(db.Float, nullable=False, default=0.0)
    compte = db.Column(db.Float)          # None tant que l'article n'est pas compte
    note = db.Column(db.String(255))

    inventaire = db.relationship("Inventaire", back_populates="lignes")
    article = db.relationship("Article", lazy="joined")

    @property
    def ecart(self):
        """Compte moins theorique. Negatif = il manque."""
        if self.compte is None:
            return None
        return round(self.compte - self.theorique, 3)

    @property
    def ecart_significatif(self):
        e = self.ecart
        return e is not None and abs(e) > 1e-9

    def __repr__(self):
        return f"<LigneInventaire {self.article_id} ecart={self.ecart}>"


class PieceMouvement(db.Model):
    """Bon de livraison joint a un mouvement : photo ou PDF.

    Meme principe que les pieces des demandes : fichier stocke hors de /static
    et servi par une route qui verifie les droits.
    """

    __tablename__ = "pieces_mouvement"

    id = db.Column(db.Integer, primary_key=True)
    mouvement_id = db.Column(db.Integer, db.ForeignKey("mouvements_stock.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    nom = db.Column(db.String(255), nullable=False)
    fichier = db.Column(db.String(255), nullable=False)
    type_mime = db.Column(db.String(80))
    taille = db.Column(db.Integer, default=0)
    ajoute_par = db.Column(db.String(64))
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)

    mouvement = db.relationship("Mouvement", backref=db.backref(
        "pieces", cascade="all, delete-orphan", lazy="selectin"))

    @property
    def est_image(self):
        return (self.type_mime or "").startswith("image/")

    @property
    def taille_lisible(self):
        o = self.taille or 0
        if o < 1024:
            return f"{o} o"
        if o < 1024 * 1024:
            return f"{o / 1024:.0f} Ko"
        return f"{o / (1024 * 1024):.1f} Mo"

    def __repr__(self):
        return f"<PieceMouvement {self.nom}>"
