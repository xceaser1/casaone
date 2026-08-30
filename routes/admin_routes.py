"""Administration : utilisateurs, roles, permissions, import Excel."""
import os
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models.auth import ACTIONS, MODULES, Permission, Role, User, UserPermission
from models.db import db
from models.metier import JournalImport, Parametre
from services import excel_import
from services import pointage_import
from services.contexte import projet_actif_id
from services.security import admin_requis

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required
@admin_requis
def index():
    return render_template(
        "admin.html",
        page="admin",
        utilisateurs=User.query.order_by(User.username).all(),
        roles=Role.query.order_by(Role.nom).all(),
        modules=MODULES,
        actions=ACTIONS,
        imports=JournalImport.query.filter_by(projet_id=projet_actif_id())
        .order_by(JournalImport.date_import.desc()).limit(10).all(),
        dernier_import=Parametre.get("dernier_import"),
        fichier_source=Parametre.get("fichier_source"),
    )


# --------------------------------------------------------------------------
# Utilisateurs
# --------------------------------------------------------------------------
@bp.route("/utilisateurs", methods=["POST"])
@login_required
@admin_requis
def creer_utilisateur():
    identifiant = (request.form.get("username") or "").strip()
    mot_de_passe = request.form.get("password") or ""
    role_id = request.form.get("role_id")

    if len(identifiant) < 3:
        flash("L'identifiant doit contenir au moins 3 caracteres.", "erreur")
    elif len(mot_de_passe) < 6:
        flash("Le mot de passe doit contenir au moins 6 caracteres.", "erreur")
    elif User.query.filter(db.func.lower(User.username) == identifiant.lower()).first():
        flash("Cet identifiant existe deja.", "erreur")
    elif not role_id:
        flash("Le role est obligatoire.", "erreur")
    else:
        u = User(
            username=identifiant,
            nom_complet=(request.form.get("nom_complet") or "").strip(),
            email=(request.form.get("email") or "").strip(),
            role_id=int(role_id),
            actif=True,
        )
        u.set_password(mot_de_passe)
        db.session.add(u)
        db.session.commit()
        flash(f"Utilisateur « {identifiant} » cree.", "succes")
    return redirect(url_for("admin.index"))


@bp.route("/utilisateurs/<int:user_id>", methods=["POST"])
@login_required
@admin_requis
def modifier_utilisateur(user_id):
    u = User.query.get_or_404(user_id)
    action = request.form.get("action")

    if action == "profil":
        u.nom_complet = (request.form.get("nom_complet") or "").strip()
        u.email = (request.form.get("email") or "").strip()
        if request.form.get("role_id"):
            u.role_id = int(request.form["role_id"])
        flash("Profil mis a jour.", "succes")

    elif action == "activer":
        if u.id == current_user.id:
            flash("Vous ne pouvez pas desactiver votre propre compte.", "erreur")
        else:
            u.actif = not u.actif
            flash(f"Compte {'active' if u.actif else 'desactive'}.", "succes")

    elif action == "mot_de_passe":
        nouveau = request.form.get("password") or ""
        if len(nouveau) < 6:
            flash("Le mot de passe doit contenir au moins 6 caracteres.", "erreur")
        else:
            u.set_password(nouveau)
            flash("Mot de passe reinitialise.", "succes")

    elif action == "permissions":
        accordees = set(request.form.getlist("permissions"))
        UserPermission.query.filter_by(user_id=u.id).delete()
        codes_role = {p.code for p in (u.role.permissions if u.role else [])}
        for perm in Permission.query.all():
            dans_role = perm.code in codes_role
            demandee = perm.code in accordees
            if demandee != dans_role:  # on ne stocke que les ecarts au role
                db.session.add(
                    UserPermission(user_id=u.id, permission_id=perm.id, accorde=demandee)
                )
        flash("Permissions mises a jour.", "succes")

    elif action == "supprimer":
        if u.id == current_user.id:
            flash("Vous ne pouvez pas supprimer votre propre compte.", "erreur")
        elif u.est_admin and Role.query.filter_by(est_admin=True).first() and \
                User.query.filter_by(role_id=u.role_id).count() <= 1:
            flash("Impossible de supprimer le dernier administrateur.", "erreur")
        else:
            db.session.delete(u)
            flash("Utilisateur supprime.", "succes")

    db.session.commit()
    return redirect(url_for("admin.index"))


@bp.route("/utilisateurs/<int:user_id>/permissions")
@login_required
@admin_requis
def permissions_utilisateur(user_id):
    u = User.query.get_or_404(user_id)
    return jsonify({"codes": sorted(u.codes_permissions()), "admin": u.est_admin})


# --------------------------------------------------------------------------
# Import Excel
# --------------------------------------------------------------------------
def _extension_ok(nom):
    return os.path.splitext(nom)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


@bp.route("/import/apercu", methods=["POST"])
@login_required
@admin_requis
def apercu_import():
    """Etape 1 : analyse du fichier, aucun ecrit en base."""
    fichier = request.files.get("fichier")
    if not fichier or not fichier.filename:
        return jsonify({"erreur": "Aucun fichier recu."}), 400
    if not _extension_ok(fichier.filename):
        return jsonify({"erreur": "Format non supporte (.xlsx ou .xlsm attendu)."}), 400

    nom = secure_filename(fichier.filename)
    horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
    chemin = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{horodatage}_{nom}")
    fichier.save(chemin)

    try:
        rapport = excel_import.analyser(chemin)
    except Exception as exc:
        os.remove(chemin)
        return jsonify({"erreur": f"Lecture impossible : {exc}"}), 400

    return jsonify({"fichier": os.path.basename(chemin), "feuilles": rapport})


@bp.route("/import/confirmer", methods=["POST"])
@login_required
@admin_requis
def confirmer_import():
    """Etape 2 : import reel apres confirmation explicite."""
    donnees = request.get_json(silent=True) or {}
    nom = secure_filename(donnees.get("fichier") or "")
    chemin = os.path.join(current_app.config["UPLOAD_FOLDER"], nom)
    if not nom or not os.path.exists(chemin):
        return jsonify({"erreur": "Fichier introuvable. Relancez l'apercu."}), 400

    ok, resume = excel_import.importer(chemin, utilisateur=current_user.username)
    if not ok:
        return jsonify({"erreur": resume.get("erreur", "Import echoue"), "conserve": True}), 400
    return jsonify({"ok": True, "resume": resume})


@bp.route("/import/synchroniser", methods=["POST"])
@login_required
@admin_requis
def synchroniser():
    """Reimporte le dernier fichier connu (synchronisation avec l'Excel source)."""
    nom = Parametre.get("fichier_source")
    dossier = current_app.config["UPLOAD_FOLDER"]
    candidats = sorted(
        (f for f in os.listdir(dossier) if nom and f.endswith(nom)), reverse=True
    )
    if not candidats:
        return jsonify({"erreur": "Aucun fichier source disponible sur le serveur."}), 400
    ok, resume = excel_import.importer(
        os.path.join(dossier, candidats[0]), utilisateur=current_user.username
    )
    if not ok:
        return jsonify({"erreur": resume.get("erreur"), "conserve": True}), 400
    return jsonify({"ok": True, "resume": resume})


# --------------------------------------------------------------------------
# Import du canevas de pointage (main-d'oeuvre)
# --------------------------------------------------------------------------
@bp.route("/import/pointage/apercu", methods=["POST"])
@login_required
@admin_requis
def apercu_pointage():
    """Etape 1 : analyse du canevas de pointage, aucun ecrit en base."""
    fichier = request.files.get("fichier")
    if not fichier or not fichier.filename:
        return jsonify({"erreur": "Aucun fichier recu."}), 400
    if not _extension_ok(fichier.filename):
        return jsonify({"erreur": "Format non supporte (.xlsx ou .xlsm attendu)."}), 400

    nom = secure_filename(fichier.filename)
    horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
    chemin = os.path.join(current_app.config["UPLOAD_FOLDER"], f"pointage_{horodatage}_{nom}")
    fichier.save(chemin)

    try:
        rapport = pointage_import.analyser(chemin)
    except Exception as exc:
        os.remove(chemin)
        return jsonify({"erreur": f"Lecture impossible : {exc}"}), 400

    if not rapport.get("reconnu"):
        os.remove(chemin)
        return jsonify({"erreur": "Aucune feuille de pointage au format MM-AAAA (ex. « 08-2026 »)."}), 400

    rapport["fichier"] = os.path.basename(chemin)
    return jsonify(rapport)


@bp.route("/import/pointage/confirmer", methods=["POST"])
@login_required
@admin_requis
def confirmer_pointage():
    """Etape 2 : import reel du pointage apres confirmation."""
    donnees = request.get_json(silent=True) or {}
    nom = secure_filename(donnees.get("fichier") or "")
    chemin = os.path.join(current_app.config["UPLOAD_FOLDER"], nom)
    if not nom or not os.path.exists(chemin):
        return jsonify({"erreur": "Fichier introuvable. Relancez l'apercu."}), 400

    ok, resume = pointage_import.importer(chemin, utilisateur=current_user.username)
    if not ok:
        return jsonify({"erreur": resume.get("erreur", "Import echoue"), "conserve": True}), 400
    return jsonify({"ok": True, "resume": resume})
