"""Meteo du chantier.

Pourquoi cote serveur ? La politique de securite de l'application (CSP,
`connect-src 'self'`) interdit a la page d'appeler un service externe, et c'est
voulu : une page qui peut joindre n'importe quel domaine est une page qui peut
faire fuir des donnees. Le serveur interroge donc le fournisseur, met le
resultat en cache, et n'expose que le strict necessaire.

Le cache est partage par tous les utilisateurs d'un meme chantier : trente
personnes qui ouvrent l'application le matin ne declenchent qu'un seul appel.

Fournisseur : Open-Meteo. Gratuit, sans cle d'API — rien a stocker ni a faire
tourner. Si l'appel echoue (reseau coupe, service indisponible), la fonction
renvoie None et l'interface n'affiche simplement rien : une meteo est un
agrement, jamais une raison de degrader la page.
"""
import json
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

# Villes marocaines ou URBAGEC intervient. La fiche projet porte deja un nom de
# ville : on s'en sert plutot que d'ajouter des coordonnees a saisir a la main.
VILLES = {
    "casablanca": (33.5731, -7.5898),
    "mohammedia": (33.6866, -7.3830),
    "rabat": (34.0209, -6.8416),
    "sale": (34.0531, -6.7985),
    "temara": (33.9287, -6.9067),
    "kenitra": (34.2610, -6.5802),
    "marrakech": (31.6295, -7.9811),
    "agadir": (30.4278, -9.5981),
    "tanger": (35.7595, -5.8340),
    "tetouan": (35.5785, -5.3684),
    "fes": (34.0331, -5.0003),
    "meknes": (33.8935, -5.5473),
    "oujda": (34.6867, -1.9114),
    "nador": (35.1681, -2.9335),
    "el jadida": (33.2316, -8.5007),
    "safi": (32.2994, -9.2372),
    "essaouira": (31.5085, -9.7595),
    "beni mellal": (32.3373, -6.3498),
    "settat": (33.0011, -7.6166),
    "berrechid": (33.2655, -7.5877),
    "khouribga": (32.8811, -6.9063),
    "ouarzazate": (30.9335, -6.9370),
    "errachidia": (31.9314, -4.4244),
    "al hoceima": (35.2517, -3.9372),
    "taza": (34.2100, -4.0100),
    "larache": (35.1932, -6.1557),
    "laayoune": (27.1536, -13.2033),
    "dakhla": (23.6848, -15.9579),
    "guelmim": (28.9870, -10.0574),
}
VILLE_DEFAUT = "casablanca"

DUREE_CACHE = 900          # 15 min : la meteo ne bouge pas plus vite que ca
DUREE_CACHE_ECHEC = 120    # 2 min : un echec passager ne doit pas tenir un quart d'heure
DELAI_RESEAU = 6           # secondes : jamais bloquer le rendu d'une page

# Codes WMO renvoyes par le fournisseur -> libelle et famille d'icone.
# Le regroupement est volontairement grossier : sur un chantier, ce qui compte
# est « est-ce qu'il pleut », pas la nuance entre bruine et bruine verglacante.
CODES = {
    0: ("Ciel dégagé", "soleil"),
    1: ("Peu nuageux", "soleil-nuage"),
    2: ("Partiellement nuageux", "soleil-nuage"),
    3: ("Couvert", "nuage"),
    45: ("Brouillard", "brume"),
    48: ("Brouillard givrant", "brume"),
    51: ("Bruine légère", "pluie"),
    53: ("Bruine", "pluie"),
    55: ("Bruine forte", "pluie"),
    56: ("Bruine verglaçante", "pluie"),
    57: ("Bruine verglaçante", "pluie"),
    61: ("Pluie faible", "pluie"),
    63: ("Pluie", "pluie"),
    65: ("Forte pluie", "pluie"),
    66: ("Pluie verglaçante", "pluie"),
    67: ("Pluie verglaçante", "pluie"),
    71: ("Neige faible", "neige"),
    73: ("Neige", "neige"),
    75: ("Forte neige", "neige"),
    77: ("Grains de neige", "neige"),
    80: ("Averses", "pluie"),
    81: ("Averses", "pluie"),
    82: ("Fortes averses", "pluie"),
    85: ("Averses de neige", "neige"),
    86: ("Averses de neige", "neige"),
    95: ("Orage", "orage"),
    96: ("Orage et grêle", "orage"),
    99: ("Orage et grêle", "orage"),
}

_cache = {}
_verrou = threading.Lock()


def normaliser(ville):
    """« Fès » -> « fes » : accents et casse ne doivent pas empecher la
    correspondance avec le referentiel."""
    if not ville:
        return ""
    sans_accent = unicodedata.normalize("NFKD", ville)
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    return " ".join(sans_accent.lower().split())


def coordonnees(ville):
    """Coordonnees de la ville du projet, Casablanca par defaut."""
    cle = normaliser(ville)
    if cle in VILLES:
        return VILLES[cle], ville
    # Tolerance : « Casablanca - Ain Sebaa » doit encore trouver Casablanca.
    for nom, position in VILLES.items():
        if cle.startswith(nom):
            return position, ville
    return VILLES[VILLE_DEFAUT], VILLE_DEFAUT.capitalize()


def _interroger(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 1,
    })
    requete = urllib.request.Request(url, headers={"User-Agent": "CASA-ONE/1.0"})
    with urllib.request.urlopen(requete, timeout=DELAI_RESEAU) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def releve(ville=None):
    """Meteo du moment pour la ville du projet, ou None si indisponible.

    Toute erreur est absorbee : le reseau du chantier tombe regulierement, et
    la barre du haut doit continuer a afficher le reste.
    """
    (lat, lon), nom = coordonnees(ville)
    cle = (round(lat, 2), round(lon, 2))

    with _verrou:
        garde = _cache.get(cle)
        if garde and time.time() - garde["a"] < DUREE_CACHE:
            return garde["v"]
        _cache.pop(cle, None)

    try:
        brut = _interroger(lat, lon)
        actuel = brut.get("current") or {}
        jour = brut.get("daily") or {}
        code = int(actuel.get("weather_code", 0))
        libelle, icone = CODES.get(code, ("Temps variable", "nuage"))
        valeur = {
            "ville": nom,
            "temperature": round(float(actuel["temperature_2m"])),
            "vent": round(float(actuel.get("wind_speed_10m") or 0)),
            "code": code,
            "libelle": libelle,
            "icone": icone,
            "maxi": round(float((jour.get("temperature_2m_max") or [0])[0])),
            "mini": round(float((jour.get("temperature_2m_min") or [0])[0])),
        }
    except Exception as erreur:      # noqa: BLE001 — voir ci-dessous
        # Toute panne est absorbee : reseau coupe, DNS bloque, fournisseur en
        # rade, reponse inattendue. Une meteo est un agrement, jamais une raison
        # de renvoyer une erreur a l'utilisateur.
        #
        # La raison est conservee : sans elle, « la meteo ne s'affiche pas » en
        # production est indiagnosticable — on ne sait pas distinguer un reseau
        # sortant bloque d'un fournisseur en panne.
        with _verrou:
            _cache[cle] = {
                "a": time.time() - DUREE_CACHE + DUREE_CACHE_ECHEC,
                "v": None,
                "erreur": type(erreur).__name__ + ": " + str(erreur)[:120],
            }
        return None

    with _verrou:
        _cache[cle] = {"a": time.time(), "v": valeur}
    return valeur


def derniere_erreur(ville=None):
    """Pourquoi le dernier appel a echoue, ou None s'il a reussi.

    Sert au diagnostic : reservee aux administrateurs par la route qui
    l'expose, car un message d'erreur reseau decrit l'infrastructure.
    """
    (lat, lon), _ = coordonnees(ville)
    with _verrou:
        garde = _cache.get((round(lat, 2), round(lon, 2)))
    return garde.get("erreur") if garde else None
