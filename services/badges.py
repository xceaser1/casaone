"""Badges QR des ouvriers : jetons signes + generation des QR (SVG).

Le badge encode un jeton signe (itsdangerous) contenant projet + matricule +
nom. Signe => infalsifiable ; le pointage reste par ailleurs protege par
l'authentification. Le QR est genere en pur Python avec segno (aucune image
binaire, du SVG inline directement dans la page).
"""
import segno
from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from models.db import db
from models.mainoeuvre import Ouvrier

_SALT = "badge-ouvrier-v1"


def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def encoder_token(projet_id, matricule, nom):
    return _serializer().dumps({"p": projet_id, "m": (matricule or "").strip(), "n": (nom or "").strip()})


def decoder_token(token):
    """Renvoie (projet_id, matricule, nom) ou None si le jeton est invalide."""
    try:
        d = _serializer().loads(token)
        return int(d["p"]), d.get("m", ""), d.get("n", "")
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def travailleurs(projet_id):
    """Liste dedupliquee des ouvriers d'un projet (matricule+nom), fonction la
    plus recente. Tries par nom."""
    rows = (
        db.session.query(Ouvrier.matricule_chantier, Ouvrier.nom, Ouvrier.fonction)
        .filter(Ouvrier.projet_id == projet_id)
        .order_by(Ouvrier.mois.desc())
        .all()
    )
    vus = {}
    for mat, nom, fonction in rows:
        mat = (mat or "").strip()
        nom = (nom or "").strip()
        if not (mat or nom):
            continue
        cle = f"{mat}|{nom}"
        if cle not in vus:
            vus[cle] = {"matricule": mat, "nom": nom, "fonction": (fonction or "").strip()}

    def _ordre(t):
        # Matricules numeriques d'abord, tries du n0 1 au dernier ; le reste par nom.
        mat = t["matricule"]
        if mat.isdigit():
            return (0, int(mat), "")
        return (1, 0, t["nom"].upper())

    return sorted(vus.values(), key=_ordre)


def qr_svg(donnee, scale=None, dark="#000000", border=4):
    """QR au format SVG inline, construit a la main pour un rendu fiable.

    On dessine nous-memes le SVG (au lieu de svg_inline) pour garantir :
    - un `viewBox` (sinon les cotes sont rognes au redimensionnement) ;
    - une zone de silence (quiet zone) obligatoire, sinon illisible ;
    - un fond blanc plein (les modules clairs sont blancs sur tout fond) ;
    - des aretes nettes (crispEdges) et un carre parfait.
    `error='l'` : QR le moins dense possible, plus facile a scanner.
    """
    qr = segno.make(donnee, error="l")
    rows = list(qr.matrix_iter(scale=1, border=border))
    n = len(rows)  # taille totale en modules, zone de silence incluse
    segments = []
    for y, row in enumerate(rows):
        x = 0
        largeur = len(row)
        while x < largeur:
            if row[x]:
                debut = x
                while x < largeur and row[x]:
                    x += 1
                segments.append(f"M{debut} {y}h{x - debut}v1h-{x - debut}z")
            else:
                x += 1
    chemin = "".join(segments)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'width="100%" height="100%" shape-rendering="crispEdges" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block">'
        f'<rect width="{n}" height="{n}" fill="#ffffff"/>'
        f'<path fill="{dark}" d="{chemin}"/></svg>'
    )


def badges(projet_id, base_url=None):
    """(worker, token, svg) pour chaque ouvrier du projet.

    Si `base_url` est fourni, le QR encode l'URL publique de pointage
    ``{base_url}/p/{token}`` : l'ouvrier peut scanner son propre badge avec
    l'appareil photo de son telephone. Sinon le QR encode le jeton seul.
    """
    resultat = []
    for t in travailleurs(projet_id):
        token = encoder_token(projet_id, t["matricule"], t["nom"])
        contenu = f"{base_url.rstrip('/')}/p/{token}" if base_url else token
        resultat.append({**t, "token": token, "svg": qr_svg(contenu)})
    return resultat
