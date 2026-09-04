"""Demandes d'approvisionnement : ce dont le chantier a besoin.

Un chef d'equipe saisit ce qu'il lui faut, un responsable valide ou refuse,
puis la demande est servie — et c'est ce dernier geste qui ecrit la sortie
dans le journal de stock. Le besoin exprime et la consommation reelle sont
ainsi deux faces du meme fait, saisies une seule fois.

Une ligne designe soit un article du catalogue, soit un besoin libre. Sur un
chantier tout ne figure pas au catalogue : un engin a louer, une intervention,
de la main-d'oeuvre supplementaire. Les refuser obligerait a ressortir de
l'application, et le besoin ne laisserait aucune trace.

Comme partout ailleurs, tout est rattache a un projet : aucun melange entre
chantiers.
"""
from datetime import date, datetime

from .db import db

# Cycle de vie. Une demande refusee ou servie est terminale : on n'y revient
# pas, on en cree une nouvelle. C'est ce qui rend l'historique lisible.
STATUTS = (
    ("brouillon", "Brouillon"),
    ("soumise", "Soumise"),
    ("validee", "Validee"),
    ("refusee", "Refusee"),
    ("servie", "Servie"),
)

URGENCES = (
    ("normale", "Normale"),
    ("urgente", "Urgente"),
    ("critique", "Critique"),
)

# Statuts depuis lesquels une demande peut encore etre modifiee par son auteur.
MODIFIABLES = ("brouillon", "soumise")


class Demande(db.Model):
    """En-tete d'une demande : qui, pour ou, pour quand, et ou elle en est."""

    __tablename__ = "demandes"

    id = db.Column(db.Integer, primary_key=True)
    projet_id = db.Column(db.Integer, db.ForeignKey("projets.id", ondelete="CASCADE"), index=True)

    # Numero lisible, unique par projet : c'est lui qu'on cite sur le chantier
    # et qu'on retrouve en reference du mouvement de stock.
    numero = db.Column(db.Integer, nullable=False, index=True)

    objet = db.Column(db.String(160), nullable=False)
    localisation = db.Column(db.String(120))          # zone, bloc, niveau...
    urgence = db.Column(db.String(12), default="normale", nullable=False, index=True)
    besoin_pour = db.Column(db.Date)                  # date souhaitee
    commentaire = db.Column(db.Text)

    statut = db.Column(db.String(12), default="brouillon", nullable=False, index=True)

    demandeur = db.Column(db.String(64), index=True)
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)
    soumise_le = db.Column(db.DateTime)

    decide_par = db.Column(db.String(64))
    decide_le = db.Column(db.DateTime)
    motif_decision = db.Column(db.String(255))        # obligatoire pour un refus

    servie_par = db.Column(db.String(64))
    servie_le = db.Column(db.DateTime)
    # Depot d'ou la marchandise est sortie au moment de servir.
    depot_id = db.Column(db.Integer, db.ForeignKey("depots.id", ondelete="SET NULL"), index=True)

    lignes = db.relationship(
        "LigneDemande", back_populates="demande",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="LigneDemande.id",
    )
    depot = db.relationship("Depot", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("projet_id", "numero", name="uq_demande_projet_numero"),
    )

    # --- libelles -----------------------------------------------------------
    @property
    def statut_libelle(self):
        return dict(STATUTS).get(self.statut, self.statut)

    @property
    def urgence_libelle(self):
        return dict(URGENCES).get(self.urgence, self.urgence)

    @property
    def statut_classe(self):
        """Classe de pastille, alignee sur les couleurs deja utilisees."""
        return {
            "brouillon": "b-gris",
            "soumise": "b-bleu",
            "validee": "b-vert",
            "refusee": "b-rouge",
            "servie": "b-vert",
        }.get(self.statut, "b-gris")

    # --- etat ---------------------------------------------------------------
    @property
    def modifiable(self):
        return self.statut in MODIFIABLES

    @property
    def en_retard(self):
        """Echeance depassee sans que la demande soit servie."""
        if not self.besoin_pour or self.statut in ("servie", "refusee"):
            return False
        return self.besoin_pour < date.today()

    @property
    def nb_lignes(self):
        return len(self.lignes)

    def __repr__(self):
        return f"<Demande #{self.numero} {self.statut}>"


class LigneDemande(db.Model):
    """Une ligne : un article du catalogue, ou un besoin exprime librement."""

    __tablename__ = "lignes_demande"

    id = db.Column(db.Integer, primary_key=True)
    demande_id = db.Column(db.Integer, db.ForeignKey("demandes.id", ondelete="CASCADE"),
                           nullable=False, index=True)

    # Exactement l'un des deux est renseigne (voir la contrainte plus bas).
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    designation_libre = db.Column(db.String(160))

    unite = db.Column(db.String(16), default="U")
    quantite = db.Column(db.Float, nullable=False, default=0.0)
    # Ce qui a reellement ete remis : peut differer de ce qui etait demande.
    quantite_servie = db.Column(db.Float, default=0.0)
    note = db.Column(db.String(255))

    demande = db.relationship("Demande", back_populates="lignes")
    article = db.relationship("Article", lazy="joined")

    __table_args__ = (
        # Une ligne sans article ni libelle ne veut rien dire ; une ligne avec
        # les deux serait ambigue au moment de servir.
        db.CheckConstraint(
            "(article_id IS NOT NULL AND designation_libre IS NULL)"
            " OR (article_id IS NULL AND designation_libre IS NOT NULL)",
            name="ck_ligne_article_ou_libre",
        ),
    )

    @property
    def libelle(self):
        if self.article is not None:
            return self.article.designation
        return self.designation_libre or "—"

    @property
    def catalogue(self):
        """Vrai si la ligne pointe un article suivi en stock."""
        return self.article_id is not None

    def __repr__(self):
        return f"<LigneDemande {self.libelle} x{self.quantite}>"
