/* File d'attente des pointages hors ligne.
 *
 * Ce fichier est charge tel quel DANS LA PAGE et DANS LE SERVICE WORKER
 * (via importScripts) : il ne doit donc toucher ni au DOM ni a `window`.
 *
 * Principe : quand le reseau manque, le pointage est ecrit dans IndexedDB avec
 * l'heure relevee par le telephone. Il repart plus tard vers /api/checkin/lot.
 * L'idempotence est garantie cote serveur par la contrainte d'unicite
 * (projet, jour, matricule, nom, type) : rejouer un lot ne cree pas de doublon.
 */
(function (global) {
  'use strict';

  var BASE = 'casaone';
  var VERSION = 1;
  var POINTAGES = 'pointages';
  var META = 'meta';
  var URL_LOT = '/api/checkin/lot';

  function ouvrir() {
    return new Promise(function (res, rej) {
      var r = indexedDB.open(BASE, VERSION);
      r.onupgradeneeded = function () {
        var db = r.result;
        if (!db.objectStoreNames.contains(POINTAGES)) {
          db.createObjectStore(POINTAGES, { keyPath: 'uuid' });
        }
        if (!db.objectStoreNames.contains(META)) {
          db.createObjectStore(META, { keyPath: 'cle' });
        }
      };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
  }

  function transaction(magasin, mode, action) {
    return ouvrir().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction(magasin, mode);
        var demande = action(tx.objectStore(magasin));
        tx.oncomplete = function () { db.close(); res(demande && demande.result); };
        tx.onerror = function () { db.close(); rej(tx.error); };
      });
    });
  }

  function identifiant() {
    if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
    return 'p-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  /* --------------------------------------------------------------- File */

  /** Empile un pointage. `charge` est le corps qui sera poste au serveur. */
  function ajouter(charge) {
    var ligne = {
      uuid: identifiant(),
      heure: charge.heure || new Date().toISOString(),
      cree: Date.now(),
      essais: 0
    };
    ['token', 'matricule', 'nom', 'type'].forEach(function (k) {
      if (charge[k] !== undefined) ligne[k] = charge[k];
    });
    return transaction(POINTAGES, 'readwrite', function (s) { return s.add(ligne); })
      .then(function () { return ligne; });
  }

  function tous() {
    return transaction(POINTAGES, 'readonly', function (s) { return s.getAll(); })
      .then(function (r) { return r || []; });
  }

  function compter() {
    return transaction(POINTAGES, 'readonly', function (s) { return s.count(); })
      .then(function (n) { return n || 0; });
  }

  function retirer(uuids) {
    if (!uuids || !uuids.length) return Promise.resolve();
    return transaction(POINTAGES, 'readwrite', function (s) {
      uuids.forEach(function (u) { s.delete(u); });
    });
  }

  /* ------------------------------------------------------------- Envoi */

  /**
   * Vide la file vers le serveur.
   *
   * Ne retire une ligne que si le serveur l'a acceptee, ou l'a rejetee
   * definitivement (badge inconnu) : sinon elle serait reessayee sans fin.
   * Toute erreur reseau laisse la file intacte et propage l'echec, pour que
   * le service worker puisse programmer une nouvelle tentative.
   */
  function synchroniser() {
    return tous().then(function (lignes) {
      if (!lignes.length) return { envoyes: 0, restants: 0, refuses: [] };

      return fetch(URL_LOT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ pointages: lignes })
      }).then(function (r) {
        // Une session expiree renvoie la page de connexion : surtout ne pas
        // vider la file, les pointages seraient perdus.
        var type = r.headers.get('Content-Type') || '';
        if (!r.ok || type.indexOf('json') < 0) {
          throw new Error(r.status === 401 || r.redirected ? 'session' : 'reseau');
        }
        return r.json();
      }).then(function (d) {
        var resultats = d.resultats || [];
        var refuses = resultats.filter(function (x) { return !x.ok && x.definitif; });
        var aRetirer = resultats
          .filter(function (x) { return x.ok || x.definitif; })
          .map(function (x) { return x.uuid; });
        return retirer(aRetirer).then(compter).then(function (restants) {
          return {
            envoyes: resultats.filter(function (x) { return x.ok; }).length,
            restants: restants,
            refuses: refuses,
            presents: d.presents
          };
        });
      });
    });
  }

  /* ------------------------------------------- Portee du cache de pages */
  /* Les pages mises en cache appartiennent a un utilisateur ET a un projet.
     La portee sert de cloisonnement : on ne sert jamais a quelqu'un une page
     mise en cache sous une autre portee. */

  function lirePortee() {
    return transaction(META, 'readonly', function (s) { return s.get('portee'); })
      .then(function (r) { return r ? r.valeur : null; })
      .catch(function () { return null; });
  }

  function ecrirePortee(valeur) {
    return transaction(META, 'readwrite', function (s) {
      return s.put({ cle: 'portee', valeur: valeur });
    });
  }

  global.FileAttente = {
    ajouter: ajouter,
    tous: tous,
    compter: compter,
    retirer: retirer,
    synchroniser: synchroniser,
    lirePortee: lirePortee,
    ecrirePortee: ecrirePortee,
    TAG_SYNC: 'casaone-pointages'
  };
})(typeof self !== 'undefined' ? self : this);
