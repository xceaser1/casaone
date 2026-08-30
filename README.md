# URBAGEC — Tableau de bord CASA ONE

Application web interne de suivi du projet **CASA ONE**, construite à partir du classeur
`TABLEAU_DE_BORD_URB_PROJET_CASAONE.xlsx`. Elle fonctionne sur un PC du bureau faisant office de
serveur, et reste accessible depuis tous les postes du réseau local via un simple navigateur.

Aucune connexion Internet n'est nécessaire : toutes les bibliothèques (y compris Chart.js) sont
embarquées dans le projet.

---

## 1. Ce que fait l'application

| Module | Contenu |
|---|---|
| **Dashboard** | 7 indicateurs clés, bétonnage mensuel, coupe du projet niveau par niveau, avancement par type de dalle, statuts des plans, surfaces par bloc, décomptes cumulés |
| **Plan du projet** | Plan de zonage interactif : les 9 zones se colorent selon l'avancement, avec animation de la progression mois par mois |
| **Tableau de surfaces** | Surface prévue / coulée / reste / avancement par zone et par niveau |
| **Bétonnage mensuelle** | Journal des coulages (date, bloc, niveau, surface) avec filtre par période |
| **Validation des plans** | Statut de chaque plan (Validé / En cours / Non validé) |
| **Dalles** | Réticulée, Pleine, Post-Tension, Hourdis — une page par type |
| **Diagrammes** | Avancement par type de dalle et par niveau |
| **Suivi des coûts** | Décomptes, cumul payé, reste à payer, consommation du marché |
| **Main-d'œuvre** | Effectif, présence, heures supp, registre des ouvriers, croisement effectif / production |
| **Administration** | Utilisateurs, rôles, permissions, import Excel, journal des imports |

Chaque page de données propose : recherche globale, filtres par colonne, tri, pagination,
export Excel, export CSV et réinitialisation des filtres.

---

## 2. Installation sur le PC serveur (Windows)

### 2.1 Installer Python

1. Télécharger Python 3.11 ou 3.12 sur <https://www.python.org/downloads/windows/>
2. Lancer l'installateur et **cocher « Add Python to PATH »** avant de cliquer sur *Install Now*
3. Vérifier dans une invite de commandes (`Win + R` → `cmd`) :

```bat
python --version
```

### 2.2 Copier le projet

Placer le dossier `casaone` sur le PC serveur, par exemple dans `C:\URBAGEC\casaone`.

### 2.3 Créer l'environnement virtuel

```bat
cd C:\URBAGEC\casaone
python -m venv venv
venv\Scripts\activate
```

### 2.4 Installer les dépendances

```bat
pip install -r requirements.txt
```

### 2.5 Initialiser la base et importer le classeur

```bat
python scripts\initialiser.py
```

Le script :

- crée les tables SQLite dans `database\casaone.db` ;
- installe le référentiel des rôles et permissions ;
- demande l'identifiant et le mot de passe du **premier compte administrateur** ;
- importe automatiquement le classeur trouvé dans `uploads\`.

Pour importer un autre fichier :

```bat
python scripts\initialiser.py --excel "C:\chemin\vers\MON_FICHIER.xlsx"
```

### 2.6 Lancer le serveur

```bat
python app.py
```

La console affiche les deux adresses d'accès :

```
==============================================================
  URBAGEC - CASA ONE
  Acces local   : http://127.0.0.1:5000
  Acces reseau  : http://192.168.1.42:5000
==============================================================
```

> **Raccourci** : un double-clic sur `demarrer.bat` enchaîne automatiquement les étapes 2.3 à 2.6.

---

## 3. Accès depuis les autres PC du réseau local

Le serveur écoute sur `0.0.0.0`, il est donc joignable par tous les postes du même réseau.

### 3.1 Relever l'adresse IP du PC serveur

```bat
ipconfig
```

Noter la ligne **Adresse IPv4** (exemple : `192.168.1.42`).

### 3.2 Autoriser le port 5000 dans le pare-feu Windows

À exécuter **une seule fois**, dans une invite de commandes **en tant qu'administrateur** :

```bat
netsh advfirewall firewall add rule name="URBAGEC CASA ONE" dir=in action=allow protocol=TCP localport=5000
```

### 3.3 Se connecter depuis un autre poste

Ouvrir un navigateur et saisir :

```
http://192.168.1.42:5000
```

(en remplaçant par l'IP relevée à l'étape 3.1). L'interface est adaptée au PC comme à la tablette.

> **Conseil** : demandez à votre informaticien de réserver une **IP fixe** pour le PC serveur, sinon
> l'adresse peut changer après un redémarrage.

### 3.4 Changer le port

```bat
set PORT=8080
python app.py
```

---

## 4. Comptes et permissions

### Rôles fournis

| Rôle | Droits |
|---|---|
| **ADMIN** | Accès complet : consulter, ajouter, modifier, supprimer, gérer les utilisateurs et leurs permissions, importer et exporter |
| **USER** | Consulter, rechercher, filtrer, trier et exporter sur les modules métier. Aucun accès à l'administration |

L'administrateur peut accorder à un utilisateur des droits supplémentaires (ou en retirer), module
par module et action par action, depuis **Administration → Permissions**.

### Actions disponibles par module

`view` · `create` · `edit` · `delete` · `import` · `export`

Modules : `dashboard`, `surfaces`, `betonnage`, `validation`, `dalles`, `diagrammes`, `couts`, `admin`.

### Créer un administrateur en ligne de commande

```bat
set FLASK_APP=app.py
flask creer-admin --username chef --password MotDePasse123
```

---

## 5. Import et synchronisation Excel

Depuis **Administration → Import Excel** :

1. choisir un fichier `.xlsx` ou `.xlsm` ;
2. cliquer sur **Analyser le fichier** : l'application affiche chaque feuille, son nombre de lignes
   réelles et son état (reconnue / vide / non utilisée) ;
3. cliquer sur **Confirmer et importer**.

Garanties :

- le classeur source n'est **jamais modifié**, il est seulement lu ;
- l'import est transactionnel : en cas d'erreur, tout est annulé et **les données existantes sont
  conservées** ;
- chaque import est tracé dans le **Journal des imports** (date, fichier, auteur, résultat) ;
- le bouton **Resynchroniser** relance l'import du dernier fichier chargé.

En ligne de commande :

```bat
flask importer-excel "uploads\TABLEAU_DE_BORD_URB_PROJET_CASAONE.xlsx"
```

---

## 6. Comment le classeur est interprété

Le classeur est composé de **tableaux croisés** : une paire de colonnes par niveau
(`PHSS3 | PC`, `PHSS2 | PC`, …), la première colonne portant la surface prévue et la seconde la
surface coulée (ou le statut du plan pour la feuille *Validation*).

L'application convertit ces tableaux en **format long** — une ligne = une zone × un niveau — qui se
filtre, s'agrège et se met à jour beaucoup plus facilement.

### Référentiels reconstitués

- **14 niveaux** : `DALL`, `PHSS3`, `PHSS2`, `PHMSS1`, `PHSS1`, `PHRDC`, `PH ETG 1` à `PH ETG 8`
- **29 zones** : `A1`→`A9`, `B1`→`B11`, `C1`→`C8`, `H`
- **9 blocs** : `MAO`, `MAC`, `MAE`, `IMM1`, `IMMA`, `IMMB`, `HOTEL`, `GBM`, `ESP`

### Nettoyages appliqués à la lecture

- libellés de niveaux saisis librement (`PH1ER ETAGE`, `RDC`, `DALLAGE`) ramenés aux codes officiels ;
- libellés de blocs avec cote (`C7 95,90`, `A6 100,55`, `H2`) ramenés au code de zone (`C7`, `A6`, `H`) ;
- statuts uniformisés (`En  Cours`, `EN Cours` → `En Cours`) ;
- feuille `Feuil1`, vide, ignorée ;
- lignes résiduelles de la feuille *Tableau de surfaces* (lignes 6886 et 8576, contenant `*` et
  `%µµµ…`) écartées.

### Convention des totaux

Le dallage (`DALL`) est un ouvrage sur terre-plein : votre classeur l'exclut des totaux
« planchers ». **L'application reprend exactement la même convention**, ce qui donne des chiffres
identiques aux vôtres :

| Indicateur | Application | Classeur Excel |
|---|---|---|
| Surface totale planchers | 160 539,40 m² | 160 539,40 m² |
| Surface bétonnée | 73 618,45 m² | 73 618,45 m² |
| Avancement planchers | 45,86 % | 45,86 % |
| Plans validés | 55,31 % | 55,31 % |
| Montant payé | 122 933 307,62 MAD | 122 933 307,62 MAD |
| Consommation du marché | 51,81 % | 51,81 % |

Le dallage reste visible séparément sur le dashboard (92,28 % d'avancement).

### ⚠️ Écart détecté dans le classeur

Feuille **Dalle réticulée**, colonne `Q` (`PH ETG 2`) : la formule de somme de la ligne 35 n'inclut
pas la ligne 27 (`GBM C6` = 947,13 m²). Le total réel est **121 590,37 m²** au lieu des
120 643,24 m² affichés. L'application retient la somme correcte. À corriger dans le classeur si vous
souhaitez que les deux sources concordent parfaitement.

---

## 7. Plan du projet (plan interactif)

La page **Plan du projet** affiche un plan de zonage schématique des 9 grandes zones du chantier
(Mall Ouest, Central, Est, Global Media, Esplanade, Bureaux A/B, IMM, Hôtel). Chaque zone se colore
selon son avancement réel, calculé à partir de vos surfaces coulées :

- vert très clair : 0–33 %
- vert clair : 34–66 %
- vert : 67–89 %
- vert foncé : 90–100 %

Le bouton **« Rejouer la progression »** anime le remplissage des zones **mois par mois**, du premier
bétonnage jusqu'à aujourd'hui, à partir du journal de bétonnage. Un curseur permet aussi de se placer
manuellement sur un mois donné. Le plan PDF original reste consultable via le bouton « Voir le plan PDF ».

Ce module **ne nécessite aucune migration** : il lit vos données existantes (surfaces et bétonnage).
Pour l'activer sur une installation en service, il suffit de remplacer les fichiers du projet et de
relancer `python app.py`.

---

## 8. Module Main-d'œuvre (canevas de pointage)

Ce module suit l'effectif du chantier à partir de votre **canevas de pointage mensuel**
(`canevas_<Mois>_AAAA.xlsx`). Il ne remplace pas votre Excel de paie : il l'importe pour donner
une vue de pilotage que l'Excel ne calcule pas.

### Ce qu'il affiche

- **Effectif** : nombre d'ouvriers du mois, nombre de fonctions, présence moyenne, présents à ≥ 90 %,
  heures supplémentaires (total et moyenne par ouvrier)
- **Répartition par fonction** (ouvrier, boiseur, maçon, grutier, chef d'équipe…)
- **Évolution de l'effectif** mois par mois, avec la présence moyenne
- **Croisement main-d'œuvre / production** : effectif du mois face aux m² coulés le même mois, avec le
  ratio m²/ouvrier — le seul indicateur de productivité que votre Excel ne fournit pas
- **Registre des ouvriers** : tableau nominatif (matricule, nom, CIN, fonction, situation, date
  d'entrée, présence), avec recherche, filtres, tri et export

### Comment le canevas est lu

L'import détecte la feuille au format `MM-AAAA` (ex. `08-2026`) et en déduit le mois automatiquement.
Il lit une ligne par ouvrier à partir de la ligne 13, et calcule pour chacun, sur les 31 colonnes de
jours (celles qui portent une date) : les jours travaillés (1 = présent, 0,5 = demi-journée, 0 =
absent ; les codes AT/ML/SO comptent comme absence), les heures supplémentaires et le taux de
présence. Les colonnes de totaux en fin de tableau (« Total Présence », « Observations ») sont
ignorées.

Réimporter le même mois **remplace** ses données ; les autres mois sont conservés. Vous ajoutez donc
`canevas_Sept_2026`, `canevas_Oct_2026`… au fil de l'eau.

### ⚠️ Données personnelles — accès restreint

Ce module contient des **noms** et des **numéros CIN**. L'accès est protégé par une permission dédiée
`mainoeuvre`, **réservée à l'administrateur par défaut** et volontairement exclue du rôle USER. Un
utilisateur sans cette permission ne voit même pas la page dans le menu.

N'accordez cet accès qu'aux personnes habilitées (paie, direction), depuis
**Administration → Permissions**. Vous êtes responsable de la protection de ces données.

### Importer un pointage

**Administration → Import pointage** → choisir le fichier → **Analyser le canevas** (affiche le mois,
le nombre d'ouvriers et de jours détectés) → **Confirmer et importer**. Comme pour l'autre import :
rien n'est écrit avant confirmation, et un échec conserve les données existantes.

### Ajouter ce module à une installation déjà en service

Si vous mettez à jour une installation existante (vous aviez déjà le tableau de bord sans la
main-d'œuvre) : remplacez les fichiers du projet par la nouvelle version, puis lancez **une fois** :

```bat
cd C:\URBAGEC\casaone
venv\Scripts\activate
python scripts\ajouter_mainoeuvre.py
```

Cette commande crée la table des ouvriers et les nouvelles permissions **sans toucher à vos données
existantes** (surfaces, bétonnage, coûts, utilisateurs). Ensuite, importez votre canevas depuis la
page Administration.

---

## 8. Structure du projet

```
casaone/
├── app.py                     Application Flask, commandes CLI, lancement du serveur
├── config.py                  Configuration (base, sessions, uploads, pagination)
├── requirements.txt
├── demarrer.bat               Lancement en un double-clic (Windows)
├── README.md
│
├── database/
│   └── casaone.db             Base SQLite
│
├── models/
│   ├── db.py                  Instance SQLAlchemy
│   ├── auth.py                User, Role, Permission, UserPermission
│   └── metier.py              Niveau, Bloc, Zone, Surface, ValidationPlan,
│                              Betonnage, DalleSurface, Decompte, Parametre, JournalImport
│
├── routes/
│   ├── auth_routes.py         Connexion / déconnexion
│   ├── page_routes.py         Rendu des pages
│   ├── api_routes.py          API JSON : lecture, CRUD, KPI, exports
│   └── admin_routes.py        Utilisateurs, permissions, import Excel
│
├── services/
│   ├── excel_import.py        Lecture, nettoyage et import du classeur
│   ├── kpi.py                 Calcul des indicateurs et des séries de graphiques
│   ├── tables.py              Registre des tables : colonnes, filtres, tri, pagination SQL
│   ├── export.py              Génération des exports Excel et CSV
│   └── security.py            Décorateurs de contrôle d'accès
│
├── templates/
│   ├── base.html              Sidebar, topbar, icônes
│   ├── login.html
│   ├── dashboard.html
│   ├── table.html             Page de tableau générique (réutilisée par 5 modules)
│   ├── couts.html
│   ├── diagrammes.html
│   ├── detail_zone.html
│   ├── admin.html
│   └── erreur.html
│
├── static/
│   ├── css/style.css
│   ├── js/app.js              Utilitaires communs (formatage, modales, notifications)
│   ├── js/table.js            Moteur du tableau générique
│   ├── js/vendor/chart.min.js Chart.js embarqué (fonctionne sans Internet)
│   └── images/
│
├── scripts/
│   └── initialiser.py         Initialisation complète en une commande
│
└── uploads/                   Classeurs Excel importés
```

---

## 8. Base de données

| Table | Rôle |
|---|---|
| `users`, `roles`, `permissions`, `role_permissions`, `user_permissions` | Comptes et droits |
| `niveaux`, `blocs`, `zones` | Référentiels du projet |
| `surfaces` | Surface prévue / coulée par zone × niveau |
| `validations_plans` | Statut des plans par zone × niveau |
| `betonnages` | Journal des coulages |
| `dalles_surfaces` | Surfaces par type de dalle × zone × niveau |
| `decomptes` | Situations budgétaires |
| `parametres` | Montant du marché, date du dernier import |
| `journal_imports` | Historique des imports |

Les tables métier portent des contraintes d'unicité (`zone` × `niveau`) et des index sur les
colonnes servant aux filtres et aux tris.

### Passer à PostgreSQL ou MySQL

Aucune modification de code n'est nécessaire — seulement une variable d'environnement :

```bat
set DATABASE_URL=postgresql+psycopg2://utilisateur:motdepasse@serveur/urbagec
pip install psycopg2-binary
python scripts\initialiser.py
```

---

## 9. Sécurité

- mots de passe hachés (`werkzeug.security`, jamais stockés en clair) ;
- sessions signées, cookies `HttpOnly` et `SameSite=Lax`, expiration après 12 h ;
- **toutes** les routes protégées vérifient les droits **côté serveur** : masquer un bouton en
  JavaScript ne suffit jamais à autoriser une action ;
- un utilisateur non autorisé qui saisit directement `/admin/` ou appelle `/api/data/...` en
  écriture reçoit une erreur 403 ;
- validation des données côté serveur (types, valeurs négatives refusées, surface coulée qui ne peut
  pas dépasser la surface totale) ;
- confirmation obligatoire avant toute suppression ;
- taille des fichiers importés limitée à 32 Mo, extensions restreintes à `.xlsx` / `.xlsm` ;
- un administrateur ne peut ni se désactiver, ni se supprimer lui-même, ni supprimer le dernier
  compte administrateur.

### Avant la mise en service

Définir une clé secrète propre à votre installation :

```bat
set SECRET_KEY=une-longue-chaine-aleatoire-a-vous
```

Sur `demarrer.bat`, ajoutez cette ligne juste avant `python app.py` pour la rendre permanente.

---

## 10. Utilisation quotidienne

**Saisir un coulage du jour** — *Bétonnage mensuelle* → **Ajouter** → date, zone, niveau, surface.
Le dashboard et la courbe mensuelle se mettent à jour immédiatement.

**Mettre à jour un avancement** — *Tableau de surfaces* → filtrer sur la zone → **Modifier** →
saisir la surface coulée.

**Valider un plan** — *Validation des plans* → filtrer sur le niveau → **Modifier** → statut *Validé*.

**Sortir un point d'avancement** — n'importe quelle page → appliquer les filtres → **Excel**.
L'export ne contient que les lignes filtrées, en-têtes mis en forme et filtres automatiques inclus.

**Consulter une zone en détail** — *Tableau de surfaces* → coupe de la zone, surfaces par niveau et
derniers coulages enregistrés.

---

## 11. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `python n'est pas reconnu` | Python absent du PATH | Réinstaller en cochant « Add Python to PATH » |
| Les autres PC n'accèdent pas au site | Pare-feu | Exécuter la commande `netsh` du § 3.2 |
| L'adresse réseau ne fonctionne plus | IP du serveur modifiée | Relancer `ipconfig`, ou demander une IP fixe |
| `Port 5000 already in use` | Un serveur tourne déjà | Fermer l'autre fenêtre, ou `set PORT=8080` |
| Import refusé | Feuille renommée ou colonnes déplacées | Vérifier les noms de feuilles ; le détail de l'erreur figure dans le journal des imports |
| Mot de passe oublié | — | Un autre administrateur le réinitialise, sinon `flask creer-admin` |
| Chiffres différents du classeur | Convention des totaux | Voir § 6 : le dallage est exclu des totaux « planchers », comme dans votre Excel |

---

## 12. Sauvegarde

Toutes les données tiennent dans un seul fichier : `database\casaone.db`.

Il suffit de le copier régulièrement (serveur de fichiers, disque externe) **serveur arrêté** :

```bat
copy database\casaone.db "\\SERVEUR\Sauvegardes\casaone_%date:~-4%%date:~3,2%%date:~0,2%.db"
```

Pour restaurer : remettre le fichier `.db` en place et relancer `python app.py`.

---

*URBAGEC — Projet CASA ONE. Application interne, réseau local uniquement.*
