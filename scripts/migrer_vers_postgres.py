"""Copie les donnees de la base SQLite locale vers la base PostgreSQL hebergee.

A lancer UNE FOIS, apres le premier deploiement (les tables sont creees
automatiquement au demarrage de l'application hebergee).

Utilisation (depuis le dossier du projet) :

    set DATABASE_URL=postgresql://...        (URL fournie par l'hebergeur)
    venv\\Scripts\\python.exe scripts\\migrer_vers_postgres.py

Rien n'est efface cote SQLite : c'est une copie.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import config  # noqa: E402

# Ordre d'insertion : les tables referencees d'abord (cles etrangeres).
ORDRE = [
    "projets", "roles", "permissions", "users", "role_permissions", "user_permissions",
    "niveaux", "blocs", "zones", "surfaces", "validations_plans", "betonnages",
    "dalles_surfaces", "decomptes", "parametres", "journal_imports",
    "livraisons", "engins", "ouvriers", "presences",
]


def main():
    cible_url = config._normaliser_db(os.environ.get("DATABASE_URL"))
    if not cible_url or cible_url.startswith("sqlite"):
        print("ERREUR : definissez DATABASE_URL avec l'URL PostgreSQL de l'hebergeur.")
        return 1

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_url = "sqlite:///" + os.path.join(base_dir, "database", "casaone.db")

    src = create_engine(source_url)
    dst = create_engine(cible_url)
    insp_src, insp_dst = inspect(src), inspect(dst)

    tables_src = set(insp_src.get_table_names())
    tables_dst = set(insp_dst.get_table_names())
    if not tables_dst:
        print("ERREUR : la base cible est vide. Demarrez d'abord l'application hebergee")
        print("         (elle cree les tables), puis relancez ce script.")
        return 1

    SessionS, SessionD = sessionmaker(bind=src), sessionmaker(bind=dst)
    s, d = SessionS(), SessionD()
    total = 0
    try:
        for table in ORDRE:
            if table not in tables_src or table not in tables_dst:
                continue
            lignes = [dict(r._mapping) for r in s.execute(__import__("sqlalchemy").text(f'SELECT * FROM {table}'))]
            if not lignes:
                print(f"  {table}: vide")
                continue
            cols_dst = {c["name"] for c in insp_dst.get_columns(table)}
            lignes = [{k: v for k, v in l.items() if k in cols_dst} for l in lignes]
            colonnes = ", ".join(lignes[0].keys())
            valeurs = ", ".join(f":{k}" for k in lignes[0].keys())
            d.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
            d.execute(__import__("sqlalchemy").text(
                f"INSERT INTO {table} ({colonnes}) VALUES ({valeurs})"), lignes)
            d.commit()
            total += len(lignes)
            print(f"  {table}: {len(lignes)} ligne(s)")

        # Remet a jour les compteurs d'auto-increment PostgreSQL
        for table in ORDRE:
            if table in tables_dst and "id" in {c["name"] for c in insp_dst.get_columns(table)}:
                d.execute(__import__("sqlalchemy").text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"))
        d.commit()
        print(f"\nTermine : {total} lignes copiees vers PostgreSQL.")
        return 0
    except Exception as exc:
        d.rollback()
        print("ECHEC :", exc)
        return 1
    finally:
        s.close(); d.close()


if __name__ == "__main__":
    raise SystemExit(main())
