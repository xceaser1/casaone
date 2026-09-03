/* Service worker CASA ONE.
 *
 * Trois roles :
 *   1. ressources statiques        -> cache d'abord (rapide, hors ligne)
 *   2. pages de consultation       -> reseau d'abord, cache en secours
 *   3. pointages hors ligne        -> file d'attente rejouee au retour du reseau
 *
 * CLOISONNEMENT : une page mise en cache contient des donnees authentifiees et
 * propres a UN projet. Elle est donc rangee dans un cache nomme d'apres la
 * "portee" (utilisateur + projet) annoncee par la page elle-meme, et n'est
 * jamais servie sous une autre portee. Tout est purge a la deconnexion.
 */
importScripts('/file-attente.js');

const STATIQUE = 'casaone-static-v2';
const PREFIXE_PAGES = 'casaone-pages-';
const PREFIXE_API = 'casaone-api-';

/* Pages consultables hors ligne. Volontairement limite aux vues de lecture :
   les ecrans de saisie n'ont pas de sens sans serveur. */
const PAGES_HORS_LIGNE = [
  '/dashboard', '/surfaces', '/betonnage', '/dalles', '/plan',
  '/stock/', '/stock/mouvements', '/couts', '/mainoeuvre',
  '/mainoeuvre/registre', '/livraisons', '/engins', '/presences',
  '/badges', '/projets/', '/validation', '/scan'
];

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((noms) => Promise.all(
        noms.filter((n) => n.startsWith('casaone-static-') && n !== STATIQUE)
            .map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

/* --------------------------------------------------------------- Aides */

function estPageHorsLigne(url) {
  return PAGES_HORS_LIGNE.indexOf(url.pathname) >= 0;
}

function cachePages(portee) {
  return PREFIXE_PAGES + portee;
}

function cacheApi(portee) {
  return PREFIXE_API + portee;
}

/**
 * Supprime tous les caches de donnees, sauf ceux de la portee gardee.
 *
 * Appele a la deconnexion et a chaque changement de projet : une page ou une
 * reponse JSON mise en cache pour un utilisateur / un projet ne doit jamais
 * pouvoir etre servie a un autre.
 */
function purgerDonnees(portee) {
  const gardes = portee ? [cachePages(portee), cacheApi(portee)] : [];
  return caches.keys().then((noms) => Promise.all(
    noms.filter((n) => (n.startsWith(PREFIXE_PAGES) || n.startsWith(PREFIXE_API))
                       && gardes.indexOf(n) < 0)
        .map((n) => caches.delete(n))
  ));
}

/**
 * Marque une reponse servie depuis le cache.
 *
 * L'attribut pose sur <body> permet a la page d'afficher un bandeau de
 * fraicheur et de neutraliser la saisie : ce qui est affiche est un etat
 * passe, pas l'etat courant.
 */
function marquerHorsLigne(reponse) {
  const date = reponse.headers.get('X-Casaone-Cache') || '';
  return reponse.text().then((html) => new Response(
    html.replace(/<body(\s|>)/i, `<body data-hors-ligne="${date}"$1`),
    {
      status: reponse.status,
      statusText: reponse.statusText,
      headers: new Headers({ 'Content-Type': 'text/html; charset=utf-8' })
    }
  ));
}

/** Copie la reponse en y ajoutant la date de mise en cache. */
function avecDate(reponse) {
  return reponse.blob().then((corps) => {
    const entetes = new Headers(reponse.headers);
    entetes.set('X-Casaone-Cache', new Date().toISOString());
    return new Response(corps, {
      status: reponse.status, statusText: reponse.statusText, headers: entetes
    });
  });
}

/* ------------------------------------------------------------- Requetes */

self.addEventListener('fetch', (e) => {
  const requete = e.request;
  if (requete.method !== 'GET') return;

  const url = new URL(requete.url);
  if (url.origin !== self.location.origin) return;

  // La deconnexion fait tomber la portee : plus rien ne doit rester en cache.
  if (url.pathname === '/logout') {
    e.respondWith(
      FileAttente.ecrirePortee(null)
        .then(() => purgerDonnees(null))
        .catch(() => null)
        .then(() => fetch(requete))
    );
    return;
  }

  // 1. Statiques : cache d'abord (ils sont versionnes par ?v=<mtime>).
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(STATIQUE).then((c) =>
        c.match(requete).then((hit) =>
          hit || fetch(requete).then((resp) => {
            if (resp && resp.ok) c.put(requete, resp.clone());
            return resp;
          })
        )
      )
    );
    return;
  }

  // 2. Donnees JSON : les pages ne sont que des coquilles, leurs tableaux et
  //    leurs indicateurs viennent de /api. Sans ce cache, une page hors ligne
  //    resterait bloquee sur "Chargement...".
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(requete)
        .then((resp) => {
          if (resp && resp.ok) {
            const enCache = FileAttente.lirePortee().then((portee) => {
              if (!portee) return null;
              return caches.open(cacheApi(portee))
                .then((c) => c.put(requete, resp.clone()));
            }).catch(() => null);
            try { e.waitUntil(enCache); } catch (err) { /* evenement deja clos */ }
          }
          return resp;
        })
        .catch(() =>
          FileAttente.lirePortee().then((portee) => {
            if (!portee) return Response.error();
            return caches.open(cacheApi(portee))
              .then((c) => c.match(requete))
              .then((hit) => hit || Response.error());
          })
        )
    );
    return;
  }

  // 3. Pages de consultation : reseau d'abord, cache en secours.
  if (requete.mode === 'navigate' && estPageHorsLigne(url)) {
    e.respondWith(
      fetch(requete)
        .then((resp) => {
          if (!resp || !resp.ok || (resp.headers.get('Content-Type') || '').indexOf('html') < 0) {
            return resp;
          }
          // Mise en cache en tache de fond : ne retarde pas l'affichage, et
          // ne doit en aucun cas empecher la reponse d'etre servie.
          const enCache = FileAttente.lirePortee().then((portee) => {
            if (!portee) return null;
            return avecDate(resp.clone())
              .then((copie) => caches.open(cachePages(portee))
                .then((c) => c.put(requete, copie)));
          }).catch(() => null);
          try { e.waitUntil(enCache); } catch (err) { /* evenement deja clos */ }
          return resp;
        })
        .catch(() =>
          FileAttente.lirePortee().then((portee) => {
            if (!portee) return Response.error();
            return caches.open(cachePages(portee))
              .then((c) => c.match(requete))
              .then((hit) => (hit ? marquerHorsLigne(hit) : Response.error()));
          })
        )
    );
  }
});

/* ------------------------------------------------- Synchronisation */

self.addEventListener('sync', (e) => {
  if (e.tag === FileAttente.TAG_SYNC) {
    // Un rejet replace la synchronisation dans la file du navigateur, qui
    // reessaiera tout seul avec un delai croissant.
    e.waitUntil(FileAttente.synchroniser().then(prevenirClients));
  }
});

self.addEventListener('message', (e) => {
  const d = e.data || {};
  if (d.type === 'portee') {
    // Changement d'utilisateur ou de projet : le cache de l'ancienne portee
    // ne doit plus jamais etre servi.
    e.waitUntil(
      FileAttente.ecrirePortee(d.valeur)
        .then(() => purgerDonnees(d.valeur))
        .catch(() => null)
    );
  } else if (d.type === 'synchroniser') {
    e.waitUntil(
      FileAttente.synchroniser().then(prevenirClients).catch(() => null)
    );
  }
});

/** Informe les onglets ouverts du resultat, pour rafraichir le compteur. */
function prevenirClients(bilan) {
  return self.clients.matchAll({ includeUncontrolled: true }).then((clients) => {
    clients.forEach((c) => c.postMessage({ type: 'file-synchronisee', bilan: bilan }));
  });
}
