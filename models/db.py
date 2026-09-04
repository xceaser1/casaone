"""Instance SQLAlchemy partagee par tous les modeles."""
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _activer_cles_etrangeres(connexion, _record):
    """Fait respecter les cles etrangeres sur SQLite.

    SQLite les ignore par defaut : sans ce PRAGMA, tous les ondelete="CASCADE"
    declares dans les modeles sont lettre morte. Supprimer un projet laisserait
    ses surfaces, ses pointages et son stock derriere lui, rattaches a un projet
    qui n'existe plus — exactement ce que l'isolation par projet cherche a
    eviter. Le probleme est silencieux : rien ne signale que la cascade n'a pas
    eu lieu.

    PostgreSQL, lui, les applique toujours ; le test d'instance limite donc ce
    reglage aux connexions SQLite.
    """
    if isinstance(connexion, sqlite3.Connection):
        curseur = connexion.cursor()
        curseur.execute("PRAGMA foreign_keys=ON")
        curseur.close()
