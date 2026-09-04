"""Modeles d'authentification et d'autorisation.

Architecture volontairement evolutive :
  User -> Role -> Permission (permissions heritees du role)
  User -> UserPermission          (surcharges individuelles : grant / revoke)

Une permission est une chaine "module.action" (ex : "surfaces.edit").
Le module "*" signifie "tous les modules".
"""
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db

# Actions supportees par le systeme de droits
ACTIONS = ["view", "create", "edit", "delete", "import", "export"]

# Modules metier (correspondent aux pages de la sidebar)
MODULES = [
    ("projets", "Projets"),
    ("dashboard", "Dashboard"),
    ("surfaces", "Tableau de surfaces"),
    ("betonnage", "Betonnage mensuelle"),
    ("validation", "Validation des plans"),
    ("dalles", "Dalles (4 types)"),
    ("diagrammes", "Diagrammes"),
    ("couts", "Suivi des couts"),
    ("livraisons", "Livraisons de beton"),
    ("engins", "Materiel et engins"),
    ("mainoeuvre", "Main-d'oeuvre"),
    ("stock", "Stock et depots"),
    ("demandes", "Demandes d'approvisionnement"),
    ("pointage", "Pointage (badges QR)"),
    ("admin", "Administration"),
]

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)  # ex: surfaces.edit
    module = db.Column(db.String(32), nullable=False)
    action = db.Column(db.String(32), nullable=False)
    libelle = db.Column(db.String(128))

    def __repr__(self):
        return f"<Permission {self.code}>"


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(32), unique=True, nullable=False)
    libelle = db.Column(db.String(128))
    est_admin = db.Column(db.Boolean, default=False, nullable=False)

    permissions = db.relationship("Permission", secondary=role_permissions, lazy="joined")
    users = db.relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.nom}>"


class UserPermission(db.Model):
    """Surcharge individuelle : accorde (True) ou retire (False) une permission."""

    __tablename__ = "user_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    accorde = db.Column(db.Boolean, default=True, nullable=False)

    permission = db.relationship("Permission", lazy="joined")
    __table_args__ = (db.UniqueConstraint("user_id", "permission_id", name="uq_user_perm"),)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nom_complet = db.Column(db.String(128))
    email = db.Column(db.String(128))
    password_hash = db.Column(db.String(256), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    cree_le = db.Column(db.DateTime, default=datetime.utcnow)
    derniere_connexion = db.Column(db.DateTime)

    role = db.relationship("Role", back_populates="users", lazy="joined")
    surcharges = db.relationship(
        "UserPermission", lazy="joined", cascade="all, delete-orphan", backref="user"
    )

    # --- mot de passe -----------------------------------------------------
    def set_password(self, mot_de_passe):
        self.password_hash = generate_password_hash(mot_de_passe)

    def check_password(self, mot_de_passe):
        return check_password_hash(self.password_hash, mot_de_passe)

    # --- droits -----------------------------------------------------------
    @property
    def est_admin(self):
        return bool(self.role and self.role.est_admin)

    def codes_permissions(self):
        """Ensemble des codes de permission effectifs de l'utilisateur."""
        if self.est_admin:
            return {"*"}
        codes = {p.code for p in (self.role.permissions if self.role else [])}
        for s in self.surcharges:
            if s.accorde:
                codes.add(s.permission.code)
            else:
                codes.discard(s.permission.code)
        return codes

    def peut(self, module, action="view"):
        """Controle d'acces central - toujours appele cote serveur."""
        if not self.actif:
            return False
        if self.est_admin:
            return True
        return f"{module}.{action}" in self.codes_permissions()

    def __repr__(self):
        return f"<User {self.username}>"
