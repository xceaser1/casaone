"""URBAGEC - CASA ONE : point d'entree de l'application Flask."""
import os
import socket

import click
from flask import Flask, jsonify, render_template, request, url_for
from flask_login import LoginManager, current_user

from config import Config
from models.auth import ACTIONS, MODULES, Permission, Role, User
from models.db import db
from models import mainoeuvre as _mainoeuvre_models  # noqa: F401  (enregistre la table ouvriers)
from models import livraison as _livraison_models  # noqa: F401  (enregistre la table livraisons)
from models import engin as _engin_models  # noqa: F401  (enregistre la table engins)
from models import metier as _metier_models  # noqa: F401
from models import presence as _presence_models  # noqa: F401  (enregistre la table presences)
from models import stock as _stock_models  # noqa: F401  (depots, articles, mouvements)
from models.projet import Projet

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Merci de vous connecter."
login_manager.login_message_category = "info"


def creer_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "database"), exist_ok=True)

    # Garde-fou hebergement : en production le stockage disque est ephemere.
    # Sans base PostgreSQL, les donnees seraient perdues a chaque redemarrage.
    if os.environ.get("PRODUCTION", "").strip() in ("1", "true", "oui", "on"):
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            raise RuntimeError(
                "PRODUCTION=1 mais DATABASE_URL n'est pas defini : ajoutez une base "
                "PostgreSQL a votre service, sinon les donnees seront perdues a chaque redemarrage."
            )

    db.init_app(app)
    login_manager.init_app(app)

    from routes.admin_routes import bp as admin_bp
    from routes.api_routes import bp as api_bp
    from routes.auth_routes import bp as auth_bp
    from routes.page_routes import bp as pages_bp
    from routes.pointage_routes import bp as pointage_bp
    from routes.projet_routes import bp as projets_bp
    from routes.stock_routes import bp as stock_bp
    from routes.mobile_routes import bp as mobile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(projets_bp)
    app.register_blueprint(pointage_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(mobile_bp)

    _enregistrer_contexte(app)
    _enregistrer_erreurs(app)
    _enregistrer_securite(app)
    _enregistrer_pwa(app)
    _enregistrer_compression(app)
    _enregistrer_cli(app)

    with app.app_context():
        db.create_all()
        migrer_schema_projets()
        initialiser_referentiel_droits()
        initialiser_projet_principal(app)

    return app


def _enregistrer_compression(app):
    """Compresse les reponses texte (HTML, CSS, JS, JSON).

    Sur une connexion mobile, c'est le gain le plus important : les fichiers
    de la librairie de graphiques ou la feuille de style passent de plusieurs
    centaines de kilo-octets a quelques dizaines.
    """
    import gzip

    TYPES = ("text/html", "text/css", "application/javascript", "text/javascript",
             "application/json", "image/svg+xml", "text/plain")
    SEUIL = 1024  # inutile de compresser les toutes petites reponses

    @app.after_request
    def _compresser(reponse):
        if "gzip" not in (request.headers.get("Accept-Encoding") or ""):
            return reponse
        if reponse.status_code < 200 or reponse.status_code >= 300:
            return reponse
        if reponse.headers.get("Content-Encoding"):
            return reponse
        if not (reponse.mimetype or "").startswith(TYPES):
            return reponse
        # Les fichiers statiques sont servis en flux direct : il faut desactiver
        # ce mode pour pouvoir lire puis compresser leur contenu. C'est le gain
        # le plus important (la librairie de graphiques passe de 205 a ~60 Ko).
        if reponse.direct_passthrough:
            taille = reponse.headers.get("Content-Length", type=int) or 0
            if taille > 4 * 1024 * 1024:      # trop gros : on laisse tel quel
                return reponse
            reponse.direct_passthrough = False
        donnees = reponse.get_data()
        if len(donnees) < SEUIL:
            return reponse
        compresse = gzip.compress(donnees, 6)
        if len(compresse) >= len(donnees):
            return reponse
        reponse.set_data(compresse)
        reponse.headers["Content-Encoding"] = "gzip"
        reponse.headers["Content-Length"] = str(len(compresse))
        reponse.headers.add("Vary", "Accept-Encoding")
        return reponse


def _enregistrer_pwa(app):
    """Sert le service worker a la racine (scope "/") pour l'installation PWA."""
    from flask import send_from_directory

    @app.route("/sw.js")
    def service_worker():
        reponse = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
        reponse.headers["Content-Type"] = "application/javascript"
        reponse.headers["Service-Worker-Allowed"] = "/"
        reponse.headers["Cache-Control"] = "no-cache"
        return reponse

    # La file d'attente est importee par le service worker via importScripts.
    # Servie depuis /static, elle heriterait du cache d'un an et le worker
    # pourrait continuer a executer une version perimee apres un deploiement.
    @app.route("/file-attente.js")
    def file_attente():
        reponse = send_from_directory(os.path.join(app.static_folder, "js"), "file-attente.js")
        reponse.headers["Content-Type"] = "application/javascript"
        reponse.headers["Cache-Control"] = "no-cache"
        return reponse


def initialiser_projet_principal(app):
    """Cree la fiche du projet principal (CASA ONE / CFAO) si aucune n'existe."""
    if Projet.query.first() is not None:
        return
    projet = Projet(
        code="CFAO",
        nom=app.config["PROJET_NOM"],
        client="CFAO",
        ville="Casablanca",
        statut="en_cours",
        est_principal=True,
    )
    db.session.add(projet)
    db.session.commit()


def migrer_schema_projets():
    """Rend etanches les donnees existantes : ajoute projet_id partout et
    rattache tout l'historique au projet principal. Idempotent (SQLite).

    - Tables simples : ALTER ADD COLUMN projet_id + backfill.
    - ouvriers / parametres : changement structurel (contrainte/PK) -> table
      renommee, recreee au nouveau schema, puis donnees recopiees.
    - Codes niveaux/blocs/zones : unicite desormais par projet.

    Cette migration ne concerne QUE les anciennes bases SQLite locales : elle
    utilise du SQL specifique (sqlite_master, PRAGMA). Sur PostgreSQL (heberge),
    les tables sont creees directement au bon schema par db.create_all() :
    on sort immediatement.
    """
    from sqlalchemy import text

    if db.engine.dialect.name != "sqlite":
        return

    def existe(conn, table):
        r = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": table}
        ).first()
        return r is not None

    def colonnes(conn, table):
        return {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}

    def index_nommes(conn, table):
        return [
            r[0] for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t "
                     "AND name NOT LIKE 'sqlite_%'"), {"t": table}
            ).fetchall()
        ]

    # Colonnes purement schema, AVANT tout acces ORM a Projet (l'ORM
    # selectionnerait sinon des colonnes qui n'existent pas encore en base).
    with db.engine.begin() as conn:
        if existe(conn, "projets") and "pin_pointage" not in colonnes(conn, "projets"):
            conn.execute(text("ALTER TABLE projets ADD COLUMN pin_pointage VARCHAR(12)"))

    principal = Projet.principal() or Projet.query.order_by(Projet.id).first()
    if principal is None:
        return
    pid = principal.id

    simples = [
        "niveaux", "blocs", "zones", "surfaces", "validations_plans", "betonnages",
        "dalles_surfaces", "decomptes", "journal_imports", "livraisons", "engins",
    ]

    with db.engine.begin() as conn:
        for t in simples:
            if existe(conn, t) and "projet_id" not in colonnes(conn, t):
                conn.execute(text(f"ALTER TABLE {t} ADD COLUMN projet_id INTEGER"))
                conn.execute(
                    text(f"UPDATE {t} SET projet_id = :pid WHERE projet_id IS NULL"), {"pid": pid}
                )
        # ouvriers / parametres : changement de contrainte -> table renommee.
        # On supprime d'abord ses index nommes (ils sont globaux et entreraient
        # sinon en collision quand create_all recree la table).
        for t in ("ouvriers", "parametres"):
            if existe(conn, t) and "projet_id" not in colonnes(conn, t):
                for idx in index_nommes(conn, t):
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                conn.execute(text(f"ALTER TABLE {t} RENAME TO {t}_old"))
        # Reprise d'une migration interrompue : nettoie les index restes sur *_old
        # et supprime une table cible vide recreee a moitie.
        for base in ("ouvriers", "parametres"):
            if existe(conn, f"{base}_old"):
                for idx in index_nommes(conn, f"{base}_old"):
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                if existe(conn, base):
                    conn.execute(text(f"DROP TABLE {base}"))

    besoin = False
    with db.engine.begin() as conn:
        besoin = existe(conn, "ouvriers_old") or existe(conn, "parametres_old")

    if besoin:
        db.create_all()  # recree ouvriers / parametres au nouveau schema
        with db.engine.begin() as conn:
            if existe(conn, "ouvriers_old"):
                cols = ("id, mois, matricule_chantier, matricule_sage, nom, cin, section, "
                        "fonction, situation, date_entree, jours_travailles, jours_ouvres, "
                        "heures_supp, taux_presence, maj_le")
                conn.execute(
                    text(f"INSERT INTO ouvriers ({cols}, projet_id) "
                         f"SELECT {cols}, :pid FROM ouvriers_old"), {"pid": pid}
                )
                conn.execute(text("DROP TABLE ouvriers_old"))
            if existe(conn, "parametres_old"):
                conn.execute(
                    text("INSERT INTO parametres (projet_id, cle, valeur, libelle) "
                         "SELECT :pid, cle, valeur, libelle FROM parametres_old"), {"pid": pid}
                )
                conn.execute(text("DROP TABLE parametres_old"))

    # Unicite des codes desormais par projet (au lieu de globale)
    with db.engine.begin() as conn:
        for t, uq in (("niveaux", "uq_niveau_projet_code"),
                      ("blocs", "uq_bloc_projet_code"),
                      ("zones", "uq_zone_projet_code")):
            if not existe(conn, t):
                continue
            conn.execute(text(f"DROP INDEX IF EXISTS ix_{t}_code"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t}_code ON {t} (code)"))
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {uq} ON {t} (projet_id, code)"))


@login_manager.user_loader
def charger_utilisateur(user_id):
    return db.session.get(User, int(user_id))


# --------------------------------------------------------------------------
def _enregistrer_contexte(app):
    @app.context_processor
    def injecter():
        """Expose les droits et le projet actif aux templates (affichage)."""
        from flask import session

        def peut(module, action="view"):
            return current_user.is_authenticated and current_user.peut(module, action)

        def statique(fichier):
            """URL d'un fichier statique avec empreinte de version.

            Ajoute ?v=<date de modification> : des qu'on modifie le CSS ou le JS,
            l'URL change et le navigateur recharge le fichier au lieu de servir
            une version en cache (sinon il faut un Ctrl+F5 apres chaque deploiement).
            """
            try:
                version = int(os.path.getmtime(os.path.join(app.static_folder, fichier)))
            except OSError:
                version = 0
            return url_for("static", filename=fichier, v=version)

        projet_actif = None
        projets = []
        if current_user.is_authenticated:
            projets = Projet.actifs()
            if projets:
                choisi = session.get("projet_id")
                projet_actif = next((p for p in projets if p.id == choisi), None) or projets[0]

        def presents_aujourdhui():
            """Nombre d'ouvriers pointes en entree ce jour, pour la pastille du menu.

            Simple COUNT sur un index existant (projet + jour) : appele une fois
            par rendu de page, le cout est negligeable. Renvoie 0 des que
            l'utilisateur n'a pas acces au pointage.
            """
            if projet_actif is None or not peut("pointage"):
                return 0
            from datetime import date
            from models.presence import Presence
            return Presence.query.filter_by(
                projet_id=projet_actif.id, jour=date.today(), type="entree"
            ).count()

        return {
            "peut": peut,
            "statique": statique,
            "presents_aujourdhui": presents_aujourdhui,
            "projet_nom": projet_actif.nom if projet_actif else app.config["PROJET_NOM"],
            "societe": app.config["SOCIETE"],
            "projet_actif": projet_actif,
            "projets": projets,
        }


def _enregistrer_securite(app):
    """En-tetes de securite HTTP appliques a toutes les reponses."""

    # CSP compatible avec les scripts/styles inline de l'application (dashboards,
    # scanner...). Bloque toute ressource externe, les <object>/<embed> et le
    # cadrage cross-origin (clickjacking).
    CSP = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self'"
    )

    @app.after_request
    def _entetes(reponse):
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        reponse.headers.setdefault("Referrer-Policy", "same-origin")
        # Camera autorisee uniquement sur notre origine (scanner de pointage).
        reponse.headers.setdefault(
            "Permissions-Policy", "camera=(self), microphone=(), geolocation=()"
        )
        reponse.headers.setdefault("Content-Security-Policy", CSP)
        if request.is_secure:
            reponse.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return reponse


def _enregistrer_erreurs(app):
    def _json_ou_html(code, message, gabarit):
        if request.path.startswith("/api/"):
            return jsonify({"erreur": message}), code
        return render_template(gabarit, message=message), code

    @app.errorhandler(403)
    def acces_refuse(_e):
        return _json_ou_html(403, "Vous n'avez pas les droits necessaires.", "erreur.html")

    @app.errorhandler(404)
    def introuvable(_e):
        return _json_ou_html(404, "Page introuvable.", "erreur.html")

    @app.errorhandler(500)
    def erreur_serveur(_e):
        db.session.rollback()
        return _json_ou_html(500, "Erreur interne. L'operation a ete annulee.", "erreur.html")


# --------------------------------------------------------------------------
def initialiser_referentiel_droits():
    """Cree les permissions et les deux roles de base (idempotent)."""
    cree = False
    for module, _libelle in MODULES:
        for action in ACTIONS:
            code = f"{module}.{action}"
            if not Permission.query.filter_by(code=code).first():
                db.session.add(
                    Permission(code=code, module=module, action=action, libelle=f"{_libelle} - {action}")
                )
                cree = True
    db.session.flush()

    admin = Role.query.filter_by(nom="ADMIN").first()
    if admin is None:
        admin = Role(nom="ADMIN", libelle="Administrateur", est_admin=True)
        db.session.add(admin)
        cree = True

    user = Role.query.filter_by(nom="USER").first()
    if user is None:
        user = Role(nom="USER", libelle="Utilisateur", est_admin=False)
        db.session.add(user)
        db.session.flush()
        # Par defaut : lecture + export sur les modules metier, sauf admin,
        # main-d'oeuvre et pointage (acces sensible accorde au cas par cas).
        lecture = Permission.query.filter(
            Permission.action.in_(["view", "export"]),
            Permission.module.notin_(["admin", "mainoeuvre", "pointage"]),
        ).all()
        # Les conducteurs saisissent les livraisons : CRUD complet sur ce module.
        livraisons = Permission.query.filter(
            Permission.module == "livraisons",
            Permission.action.in_(["create", "edit", "delete"]),
        ).all()
        user.permissions = lecture + livraisons
        cree = True

    # Idempotent : garantit que le role USER a bien les droits sur livraisons
    # et engins (utile pour les installations creees avant l'ajout des modules).
    if user is not None:
        codes_actuels = {p.code for p in user.permissions}
        manquantes = Permission.query.filter(
            db.or_(
                db.and_(
                    Permission.module.in_(["livraisons", "engins"]),
                    Permission.action.in_(["view", "create", "edit", "delete", "export"]),
                ),
                # Projets : lecture seule pour les utilisateurs (gestion = admin).
                db.and_(Permission.module == "projets", Permission.action.in_(["view", "export"])),
            )
        ).all()
        ajout = [p for p in manquantes if p.code not in codes_actuels]
        if ajout:
            user.permissions = list(user.permissions) + ajout
            cree = True

    # Role dedie au pointage par badge : acces au scanner / presences / badges
    # et rien d'autre (ni dashboards, ni donnees financieres ou nominatives).
    pointeur = Role.query.filter_by(nom="POINTEUR").first()
    if pointeur is None:
        pointeur = Role(nom="POINTEUR", libelle="Pointeur (badges QR)", est_admin=False)
        db.session.add(pointeur)
        db.session.flush()
        pointeur.permissions = Permission.query.filter(
            db.or_(
                db.and_(Permission.module == "pointage", Permission.action.in_(["view", "export"])),
                db.and_(Permission.module == "projets", Permission.action == "view"),
            )
        ).all()
        cree = True

    if cree:
        db.session.commit()


# --------------------------------------------------------------------------
def _enregistrer_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Cree les tables et le referentiel de droits."""
        db.create_all()
        initialiser_referentiel_droits()
        click.echo("Base initialisee.")

    @app.cli.command("creer-admin")
    @click.option("--username", prompt="Identifiant")
    @click.option("--password", prompt="Mot de passe", hide_input=True, confirmation_prompt=True)
    @click.option("--nom", default="")
    def creer_admin(username, password, nom):
        """Cree (ou met a jour) un compte administrateur."""
        if len(password) < 6:
            raise click.ClickException("Mot de passe trop court (6 caracteres minimum).")
        role = Role.query.filter_by(nom="ADMIN").first()
        u = User.query.filter_by(username=username).first()
        if u is None:
            u = User(username=username, nom_complet=nom or username, role_id=role.id, actif=True)
            db.session.add(u)
        u.role_id = role.id
        u.set_password(password)
        db.session.commit()
        click.echo(f"Administrateur « {username} » pret.")

    @app.cli.command("importer-excel")
    @click.argument("chemin")
    def importer_excel(chemin):
        """Importe un classeur Excel dans la base."""
        from services import excel_import

        ok, resume = excel_import.importer(chemin, utilisateur="cli")
        if ok:
            click.echo("Import termine : " + ", ".join(f"{k}={v}" for k, v in resume.items()))
        else:
            raise click.ClickException(resume.get("erreur", "echec"))


def _ip_locale():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


app = creer_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # HTTPS=1 : certificat auto-signe (cryptography). Indispensable pour que la
    # camera d'un telephone fonctionne quand on accede via l'IP reseau (les
    # navigateurs bloquent la camera hors HTTPS et hors localhost).
    https = os.environ.get("HTTPS", "").strip() in ("1", "true", "oui", "on")
    schema = "https" if https else "http"
    ssl_context = "adhoc" if https else None
    print("=" * 62)
    print("  URBAGEC - CASA ONE")
    print(f"  Acces local   : {schema}://127.0.0.1:{port}")
    print(f"  Acces reseau  : {schema}://{_ip_locale()}:{port}")
    if https:
        print("  Camera mobile : activee (HTTPS auto-signe - acceptez l'alerte)")
    else:
        print("  Camera mobile : lancez avec HTTPS=1 pour scanner sur telephone")
    print("=" * 62)
    # 0.0.0.0 : indispensable pour que les autres PC du reseau se connectent
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, ssl_context=ssl_context)
