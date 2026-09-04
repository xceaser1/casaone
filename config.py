"""Configuration de l'application URBAGEC - CASA ONE."""
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _charger_secret():
    """Cle secrete forte et persistante.

    Priorite : variable d'environnement SECRET_KEY. Sinon on lit (ou on genere
    une fois pour toutes) une cle aleatoire stockee dans database/.secret_key.
    On n'utilise JAMAIS de cle par defaut ecrite dans le code : elle serait
    publique et permettrait de forger des sessions et des badges.
    """
    depuis_env = os.environ.get("SECRET_KEY")
    if depuis_env:
        return depuis_env
    chemin = os.path.join(BASE_DIR, "database", ".secret_key")
    try:
        if os.path.exists(chemin):
            with open(chemin, "r", encoding="utf-8") as f:
                cle = f.read().strip()
                if cle:
                    return cle
        cle = secrets.token_hex(32)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(cle)
        return cle
    except OSError:
        return secrets.token_hex(32)  # dernier recours : cle ephemere


def _normaliser_db(url):
    """Adapte l'URL fournie par l'hebergeur au format attendu par SQLAlchemy 2."""
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


_HTTPS = os.environ.get("HTTPS", "").strip() in ("1", "true", "oui", "on")
# En production (hebergement), tout passe par HTTPS : cookies securises.
_PROD = os.environ.get("PRODUCTION", "").strip() in ("1", "true", "oui", "on")


class Config:
    """Configuration de base (SQLite). Prete pour PostgreSQL/MySQL."""

    PROJET_NOM = "CASA ONE"
    SOCIETE = "URBAGEC"

    SECRET_KEY = _charger_secret()

    # DATABASE_URL permet de basculer vers PostgreSQL sans toucher au code :
    #   set DATABASE_URL=postgresql+psycopg2://user:pass@host/urbagec
    # Les hebergeurs (Railway, Render, Heroku) fournissent une URL "postgres://"
    # que SQLAlchemy 2 n'accepte plus : on la normalise ici.
    SQLALCHEMY_DATABASE_URI = _normaliser_db(
        os.environ.get("DATABASE_URL")
    ) or ("sqlite:///" + os.path.join(BASE_DIR, "database", "casaone.db"))
    # Les URL des fichiers statiques portent une empreinte de version
    # (?v=<date>) : on peut donc les mettre en cache tres longtemps.
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 an

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # En local, les gabarits sont relus a chaque requete : une modification de
    # page est visible sans redemarrer le serveur. Desactive en production
    # (gunicorn recharge de toute facon a chaque deploiement).
    TEMPLATES_AUTO_RELOAD = not _PROD

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 Mo max pour l'import Excel
    ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # En HTTPS, le cookie de session n'est transmis que sur des connexions
    # chiffrees (protege contre l'interception sur le reseau du chantier).
    SESSION_COOKIE_SECURE = _HTTPS or _PROD
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 h
    MAX_COOKIE_SIZE = 4093

    # --- Session longue pour le pointage hors ligne --------------------------
    # Un telephone qui pointe au portail a 7 h peut rester hors couverture
    # jusqu'au lendemain. Sans cookie "se souvenir de moi" de longue duree, la
    # session expire et la file d'attente locale ne peut plus etre envoyee :
    # les pointages seraient perdus. Le cookie reste HttpOnly et, en HTTPS,
    # limite aux connexions chiffrees.
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 30  # 30 jours
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _HTTPS or _PROD

    # --- Application Android ---------------------------------------------
    # Version publiee : l'APK compare son propre versionCode a celle-ci au
    # demarrage et propose la mise a jour. A incrementer a chaque diffusion.
    APK_VERSION_CODE = int(os.environ.get("APK_VERSION_CODE", "3"))
    APK_VERSION_NOM = os.environ.get("APK_VERSION_NOM", "2.1")
    # Fichier servi par /api/mobile/telecharger. Hors depot (voir .gitignore) :
    # un binaire de 26 Mo n'a pas sa place dans l'historique git.
    APK_FICHIER = os.environ.get("APK_FICHIER", os.path.join(BASE_DIR, "dist", "casaone.apk"))
    # Vide = le serveur annonce sa propre route de telechargement.
    APK_URL = os.environ.get("APK_URL", "")
    APK_NOTES = os.environ.get("APK_NOTES", "")

    PAGE_SIZE_DEFAULT = 25
    PAGE_SIZE_MAX = 200
