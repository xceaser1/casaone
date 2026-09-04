# CASA ONE — application Android

Application Android du système CASA ONE (URBAGEC). Elle vit désormais **dans le
dépôt du serveur**, à côté de l'application Flask avec laquelle elle doit rester
synchronisée : le pont JavaScript et les routes `/api/mobile/*` forment un
contrat entre les deux.

## Ce que fait l'application

L'interface (navigation, onglets, transitions) reste fournie par le web. Une
seule interface à maintenir, et **un changement de design se déploie côté
serveur, sans réinstaller l'application**. C'est aussi pourquoi la coque
n'ajoute pas sa propre barre d'onglets : elle ferait doublon avec celle que la
page affiche déjà sur téléphone.

Le natif apporte ce qu'un navigateur ne sait pas faire :

| Capacité | Détail |
|---|---|
| **Scanner de badges natif** | ML Kit embarqué : plus rapide que jsQR, tolère la basse lumière et les badges abîmés. Aucun service en ligne. |
| **Notifications** | Veille périodique (30 min) : stock sous le seuil, plans à valider. |
| **Tuile d'écran d'accueil** | Avancement du chantier et présents du jour. |
| **Raccourcis** | Appui long sur l'icône : Scanner · Présences · Stock. |
| **Contrôle de version** | Compare avec `/api/mobile/version` et propose la mise à jour. |
| **Exports** | Téléchargement natif et feuille de partage Android. |
| **Plein écran** | Bord à bord, encoches gérées en CSS par la page. |

## Compiler

```bash
cd android
./gradlew assembleDebug
```

L'APK sort dans `app/build/outputs/apk/debug/app-debug.apk`.

### Version de Java

Gradle **9.1** et AGP **8.13** sont requis pour fonctionner avec le JDK 25
fourni par Android Studio récent. Si le sync échoue sur
`Unsupported class file major version`, c'est que le couple Gradle/AGP est trop
ancien pour le JDK utilisé — ne rétrogradez pas le JDK, mettez à jour Gradle.

## Signature de production

L'APK est signé en **debug** par défaut. Tel quel il ne peut être ni publié sur
le Play Store, ni mis à jour plus tard avec une autre clé.

> ⚠️ **Le jour où vous signerez avec une vraie clé, chaque utilisateur devra
> désinstaller puis réinstaller l'application** — ce qui effacera les données
> locales de l'appareil, **y compris les pointages encore en attente d'envoi**.
> Faites-le donc *avant* de déployer largement, et à un moment où aucune file
> n'est en attente.

Créer la clé (une seule fois) :

```bash
keytool -genkeypair -v -keystore casaone-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias casaone
```

Puis copier `keystore.properties.exemple` en `keystore.properties` et le
compléter. Ce fichier et le `.jks` sont ignorés par git.

**Perdre cette clé rend toute mise à jour impossible.** Sauvegardez-la ailleurs
que sur cette machine.

## Diffuser une mise à jour

1. Incrémenter `versionCode` et `versionName` dans `app/build.gradle`.
2. `./gradlew assembleRelease`.
3. Déposer l'APK quelque part de téléchargeable.
4. Côté serveur, renseigner les variables d'environnement :
   `APK_VERSION_CODE`, `APK_VERSION_NOM`, `APK_URL`, `APK_NOTES`.

Au démarrage suivant, les téléphones proposeront la mise à jour — une seule fois
par version, l'utilisateur décide.

## Contrat avec le serveur

| Élément | Côté serveur | Côté Android |
|---|---|---|
| État du chantier | `GET /api/mobile/etat` | `Veille`, `WidgetChantier` |
| Version publiée | `GET /api/mobile/version` | `VerificationVersion` |
| Scanner | `templates/scan.html` appelle `CasaOneNatif.scanner(rappel)` | `MainActivity.Pont` → `ScannerActivity` |

La page web teste `CasaOneNatif.scannerDisponible()` : dans un navigateur
ordinaire elle retombe automatiquement sur jsQR, sans rien changer d'autre.

## Pourquoi pas de notifications poussées (FCM)

Firebase exigerait de créer un projet Google, d'embarquer `google-services.json`
et de faire dépendre le chantier d'un service tiers. La veille périodique
interroge directement **votre** serveur, ne demande aucun compte, et suffit :
un stock sous le seuil ne se joue pas à la minute.

Le prix à payer est la latence : Android n'autorise pas mieux que 15 minutes
entre deux vérifications, et espace davantage quand la batterie faiblit.

## Réduction de code (R8)

`minifyEnabled` est volontairement à `false`. R8 supprimerait les méthodes du
pont JavaScript — il ne peut pas voir qu'elles sont appelées depuis la page.
L'application compilerait, s'installerait, et **le scanner natif cesserait
silencieusement de répondre**. Les règles nécessaires sont déjà écrites dans
`app/proguard-rules.pro` : à activer seulement avec un test sur appareil réel.
