"""Point d'entree WSGI pour l'hebergement (gunicorn).

Utilisation :  gunicorn wsgi:app
Le serveur de developpement (`python app.py`) reste utilisable en local.
"""
from app import app

if __name__ == "__main__":
    app.run()
