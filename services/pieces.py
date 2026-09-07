"""Fichiers joints : stockage, validation, suppression.

Mutualise entre les demandes et les mouvements de stock. Le mecanisme est le
meme et les regles de securite ne doivent surtout pas diverger d'un module a
l'autre : c'est ainsi qu'on finit par avoir un endroit ou un .exe passe.

Les fichiers vivent HORS de /static et sont servis par des routes qui
verifient les droits : sous static/, ils seraient accessibles a qui connait
leur URL, sans authentification.
"""
import os
import uuid

# Ce qu'un telephone de chantier produit naturellement.
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}
TAILLE_MAX = 8 * 1024 * 1024   # 8 Mo


class FichierRefuse(Exception):
    """Le message est destine a l'utilisateur."""


def dossier(app_config, sous_dossier):
    chemin = os.path.join(app_config["UPLOAD_FOLDER"], sous_dossier)
    os.makedirs(chemin, exist_ok=True)
    return chemin


def enregistrer(fichier, app_config, sous_dossier):
    """Valide et ecrit un fichier. Renvoie (nom_origine, nom_interne, mime, taille)."""
    nom = (getattr(fichier, "filename", "") or "").strip()
    if not nom:
        raise FichierRefuse("Aucun fichier reçu.")

    extension = os.path.splitext(nom)[1].lower()
    if extension not in EXTENSIONS:
        raise FichierRefuse("Formats acceptés : photo (JPG, PNG, WEBP, HEIC) ou PDF.")

    # Taille lue sur le flux : Content-Length est declaratif.
    fichier.stream.seek(0, os.SEEK_END)
    taille = fichier.stream.tell()
    fichier.stream.seek(0)
    if taille == 0:
        raise FichierRefuse("Le fichier est vide.")
    if taille > TAILLE_MAX:
        raise FichierRefuse(f"Fichier trop volumineux (maximum {TAILLE_MAX // (1024 * 1024)} Mo).")

    # Nom genere : un nom fourni par l'utilisateur pourrait remonter
    # l'arborescence ou ecraser un fichier voisin.
    interne = f"{uuid.uuid4().hex}{extension}"
    fichier.save(os.path.join(dossier(app_config, sous_dossier), interne))
    return nom[:255], interne, getattr(fichier, "mimetype", None), taille


def effacer(nom_interne, app_config, sous_dossier):
    """Retire le fichier du disque. Un fichier deja absent n'est pas une erreur."""
    try:
        os.remove(os.path.join(dossier(app_config, sous_dossier), nom_interne))
    except OSError:
        pass
