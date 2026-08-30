# Mettre CASA ONE en ligne (hébergement)

Objectif : une adresse fixe du type `https://casaone.onrender.com`, accessible
depuis n'importe où (chantier, 4G, iPhone), **sans** IP qui change, **sans**
règle de pare-feu et **sans** alerte de certificat.

---

## Étape 1 — Mettre le code sur GitHub

L'hébergeur récupère le code depuis GitHub.

1. Créer un compte sur <https://github.com> (gratuit).
2. Créer un dépôt **privé** nommé `casaone`.
3. Dans le dossier du projet, exécuter :

```bash
git init
git add .
git commit -m "CASA ONE - suivi de chantier URBAGEC"
git branch -M main
git remote add origin https://github.com/VOTRE-COMPTE/casaone.git
git push -u origin main
```

> Le fichier `.gitignore` exclut déjà la base locale, la clé secrète et les
> fichiers Excel importés : aucune donnée sensible n'est envoyée.

---

## Étape 2 — Déployer sur Render

1. Aller sur <https://render.com> → **Sign up with GitHub**.
2. **New → Blueprint**, choisir le dépôt `casaone`.
3. Render lit le fichier **`render.yaml`** et crée automatiquement :
   - le service web (avec HTTPS et un domaine),
   - la base **PostgreSQL** (`casaone-db`),
   - la variable `SECRET_KEY` (générée),
   - `PRODUCTION=1` et `DATABASE_URL` (branchée sur la base).
4. Cliquer **Apply**. Le premier déploiement prend ~5 minutes.

À la fin, Render affiche l'adresse : `https://casaone-xxxx.onrender.com`

### Créer le compte administrateur
Dans Render : service `casaone` → onglet **Shell** :

```bash
flask creer-admin --username admin
```

(ou `python scripts/initialiser.py` selon votre besoin)

---

## Étape 3 — Transférer les données existantes

Depuis votre PC (une seule fois). Récupérer l'URL de la base dans Render
(base `casaone-db` → **External Database URL**), puis :

```bash
set DATABASE_URL=postgresql://...    (l'URL copiée)
venv\Scripts\python.exe scripts\migrer_vers_postgres.py
```

Le script copie projets, ouvriers, surfaces, bétonnage, présences, etc.
Rien n'est supprimé côté local.

---

## Étape 4 — Pointer l'application mobile

Dans l'app Android : menu **⋮ → Changer l'adresse** → coller
`https://casaone-xxxx.onrender.com`.

Sur iPhone : ouvrir l'adresse dans **Safari** → **Partager → Sur l'écran
d'accueil**. La caméra du scanner fonctionnera (vrai certificat HTTPS).

---

## Coûts indicatifs

| Formule | Prix | Remarque |
|---|---|---|
| Free | 0 € | Pour tester. Le service s'endort après 15 min d'inactivité (~30 s au réveil). |
| Starter + base 256 Mo | ~7 $/mois | Recommandé pour un usage réel sur chantier. |

Pour rester en **Free** au début : dans `render.yaml`, remplacer
`plan: starter` par `plan: free` et `plan: basic-256mb` par `plan: free`.

---

## Bon à savoir

- **Les fichiers importés ne sont pas conservés** entre deux redémarrages
  (disque éphémère). Les données lues depuis l'Excel sont, elles, bien
  enregistrées en base : seul le fichier source disparaît. Pour conserver les
  fichiers, ajouter un disque persistant Render ou un stockage type S3.
- **Sauvegardes** : Render sauvegarde la base automatiquement selon la formule.
- **Alternative Railway** : même principe (<https://railway.app>), utilisez
  le `Procfile` fourni ; ajoutez un service PostgreSQL et les variables
  `PRODUCTION=1` et `SECRET_KEY`.
- La variable `PRODUCTION=1` **empêche le démarrage** si `DATABASE_URL`
  n'est pas défini : c'est une sécurité contre la perte de données.
