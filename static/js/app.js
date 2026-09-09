/* Utilitaires partages par toutes les pages. */

const CSS = getComputedStyle(document.documentElement);
const T = {
  vert: CSS.getPropertyValue('--vert').trim() || '#35a46a',
  vertFonce: CSS.getPropertyValue('--vert-fonce').trim() || '#14603c',
  vert40: CSS.getPropertyValue('--vert-40').trim() || '#8fd3ae',
  vert20: CSS.getPropertyValue('--vert-20').trim() || '#c9e8d7',
  vert10: CSS.getPropertyValue('--vert-10').trim() || '#e2f2e9',
  bord: CSS.getPropertyValue('--bord').trim() || '#e4efe8',
  doux: CSS.getPropertyValue('--doux').trim() || '#6d8378',
  ambre: '#c88a1e',
  rouge: '#c0503f'
};

const nf0 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function nombre(v, dec = 2) {
  if (v === null || v === undefined || v === '') return '—';
  return dec === 0 ? nf0.format(v) : nf2.format(v);
}
function pourcent(v) {
  if (v === null || v === undefined || v === '') return '—';
  return nf2.format(v).replace(',00', '') + ' %';
}
function monnaie(v) {
  if (v === null || v === undefined || v === '') return '—';
  return nf0.format(v) + ' MAD';
}
function moisLisible(cle) {
  if (!cle) return '';
  const [a, m] = cle.split('-');
  const noms = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  return noms[parseInt(m, 10) - 1] + ' ' + a.slice(2);
}
function echapper(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function notifier(message, type = 'ok') {
  const zone = document.getElementById('notifs');
  if (!zone) return;
  const el = document.createElement('div');
  el.className = 'notif' + (type === 'erreur' ? ' erreur' : '');
  el.textContent = message;
  zone.appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

async function api(url, options = {}) {
  const rep = await fetch(url, {
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    ...options
  });
  let donnees = null;
  try { donnees = await rep.json(); } catch (e) { /* reponse non JSON */ }
  if (!rep.ok) {
    const msg = donnees?.erreur || (donnees?.erreurs || []).join(' ') || `Erreur ${rep.status}`;
    throw new Error(msg);
  }
  return donnees;
}

/* --------------------------------------------------------------- Modale */
function ouvrirModale(id) { document.getElementById(id)?.classList.add('ouverte'); }
function fermerModale(id) { document.getElementById(id)?.classList.remove('ouverte'); }

document.addEventListener('click', e => {
  if (e.target.classList?.contains('modale-fond')) e.target.classList.remove('ouverte');
  const f = e.target.closest('[data-fermer]');
  if (f) fermerModale(f.dataset.fermer);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.modale-fond.ouverte').forEach(m => m.classList.remove('ouverte'));
});

/* Confirmation avant toute suppression */
function confirmerSuppression(texte) {
  return window.confirm(texte + '\n\nCette action est définitive.');
}

/* --------------------------------------- Tiroir de navigation (mobile)
   La barre laterale coulisse depuis la gauche. Fermeture au clic sur le
   voile, sur un lien, par Echap ou par un glissement vers la gauche. */
(function () {
  const voile = document.getElementById('voile-nav');
  const sidebar = document.querySelector('.sidebar');
  if (!voile || !sidebar) return;

  const ouvrants = [document.getElementById('burger'), document.getElementById('onglet-menu')].filter(Boolean);

  function ouvrir(oui) {
    if (oui) {
      // On insere le voile AVANT d'animer, sinon la transition d'opacite
      // ne demarre pas (l'element vient d'apparaitre dans la mise en page).
      voile.hidden = false;
      requestAnimationFrame(() => document.body.classList.add('nav-ouverte'));
    } else {
      document.body.classList.remove('nav-ouverte');
      // On retire le voile a la fin du fondu pour qu'il ne bloque plus les appuis.
      setTimeout(() => {
        if (!document.body.classList.contains('nav-ouverte')) voile.hidden = true;
      }, 280);
    }
    // Empeche le defilement du contenu pendant que le tiroir est ouvert
    document.body.style.overflow = oui ? 'hidden' : '';
    ouvrants.forEach(b => b.setAttribute('aria-expanded', String(oui)));
  }

  ouvrants.forEach(b => b.addEventListener('click', e => {
    e.preventDefault();
    ouvrir(!document.body.classList.contains('nav-ouverte'));
  }));
  voile.addEventListener('click', () => ouvrir(false));
  sidebar.addEventListener('click', e => { if (e.target.closest('a[href]')) ouvrir(false); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.body.classList.contains('nav-ouverte')) ouvrir(false);
  });

  /* Glissement vers la gauche pour refermer */
  let xDepart = null;
  sidebar.addEventListener('touchstart', e => { xDepart = e.touches[0].clientX; }, { passive: true });
  sidebar.addEventListener('touchmove', e => {
    if (xDepart === null) return;
    if (xDepart - e.touches[0].clientX > 60) { ouvrir(false); xDepart = null; }
  }, { passive: true });
  sidebar.addEventListener('touchend', () => { xDepart = null; }, { passive: true });
})();

/* ------------------------------------------- Navigation : retour immediat
   Au clic sur un lien de la barre laterale, l'onglet devient actif tout de
   suite (sans attendre le chargement) et une barre de progression fine
   s'affiche : la sidebar reste "liee" a la page en cours de chargement. */
(function () {
  const nav = document.querySelector('.nav');
  if (!nav) return;

  const barre = document.createElement('div');
  barre.className = 'barre-chargement';
  document.body.appendChild(barre);

  nav.addEventListener('click', e => {
    const lien = e.target.closest('a[href]');
    if (!lien || lien.target === '_blank' || e.metaKey || e.ctrlKey) return;
    if (lien.classList.contains('actif')) { e.preventDefault(); return; }
    nav.querySelectorAll('a.actif').forEach(a => a.classList.remove('actif'));
    lien.classList.add('actif');
    barre.classList.add('active');
  });

  // Le retour arriere restaure l'etat correct de la barre laterale
  window.addEventListener('pageshow', e => {
    barre.classList.remove('active');
    if (e.persisted) location.reload();
  });
})();

/* ------------------------------------------------ Bascule de theme
   Le theme clair remplace le degrade bleu nuit par un fond doux ; la barre
   laterale, elle, reste sombre : c'est le contraste avec un contenu clair qui
   rend le menu lisible.

   La classe est deja posee avant le premier rendu par un script en tete de
   <body> ; ici on ne gere que la bascule et sa memorisation. */
(function () {
  const bouton = document.getElementById('bascule-theme');
  if (!bouton) return;
  const CLE = 'casaone.theme';
  const libelle = bouton.querySelector('.lib');

  function appliquer(sombre) {
    document.body.classList.toggle('theme-sombre', sombre);
    bouton.setAttribute('aria-pressed', String(sombre));
    // Le libelle annonce ce vers quoi on bascule, pas l'etat courant.
    if (libelle) libelle.textContent = sombre ? 'Thème clair' : 'Thème sombre';
    bouton.setAttribute('data-libelle', sombre ? 'Thème clair' : 'Thème sombre');

    // L'interrupteur porte son propre etat, comme dans le modele.
    const inter = bouton.querySelector('.interrupteur');
    if (inter) inter.classList.toggle('on', sombre);

    // La couleur de la barre systeme suit, sur telephone comme dans la fenetre
    // installee : sinon un lisere clair subsiste au-dessus d'un fond sombre.
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', sombre ? '#14141a' : '#e8eaee');
  }

  appliquer(document.body.classList.contains('theme-sombre'));

  bouton.addEventListener('click', () => {
    const sombre = !document.body.classList.contains('theme-sombre');
    appliquer(sombre);
    try { localStorage.setItem(CLE, sombre ? 'sombre' : 'clair'); } catch (e) { /* mode prive */ }
  });
})();

/* ------------------------------------------------ Sidebar : mode rail
   Reduction du panneau a ses icones seules. La classe est deja posee avant le
   premier rendu par un script en tete de <body> : ici on ne gere que la
   bascule et sa memorisation. */
(function () {
  const bascule = document.getElementById('rail-bascule');
  if (!bascule) return;
  const CLE = 'casaone.nav.rail';

  // En mode rail les intitules disparaissent : une pastille chiffree n'y a plus
  // sa place, on marque la section pour afficher un simple point.
  document.querySelectorAll('.nav-sect').forEach((sect) => {
    if (sect.querySelector('.nav-badge')) sect.classList.add('a-badge');
  });

  function appliquer(actif) {
    document.body.classList.toggle('rail', actif);
    const texte = actif ? 'Deplier le menu' : 'Reduire le menu';
    bascule.setAttribute('aria-label', texte);
    bascule.setAttribute('title', texte);
    bascule.setAttribute('aria-expanded', String(!actif));
  }

  appliquer(document.body.classList.contains('rail'));

  bascule.addEventListener('click', () => {
    const actif = !document.body.classList.contains('rail');
    appliquer(actif);
    try { localStorage.setItem(CLE, actif ? '1' : '0'); } catch (e) { /* mode prive */ }
  });
})();

/* ------------------------------------------ Consultation hors ligne
   Quand le service worker sert une page depuis son cache, il pose sur <body>
   un attribut data-hors-ligne portant la date de mise en cache. La page
   affiche alors ce qu'elle est reellement : un etat passe, en lecture seule.
   Laisser croire qu'une saisie a ete enregistree serait pire que la refuser. */
(function () {
  const marque = document.body.dataset.horsLigne;
  if (marque === undefined) return;

  document.body.classList.add('hors-ligne');

  let quand = 'une date inconnue';
  const d = new Date(marque);
  if (marque && !isNaN(d)) {
    quand = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })
          + ' à ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }

  const bandeau = document.createElement('div');
  bandeau.className = 'bandeau-hl';
  bandeau.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>'
    + '<span>Hors ligne — données du <b>' + quand + '</b>. La saisie est indisponible.</span>'
    + '<button type="button">Réessayer</button>';
  bandeau.querySelector('button').addEventListener('click', () => location.reload());

  const hote = document.querySelector('.contenu') || document.querySelector('.zone') || document.body;
  hote.insertBefore(bandeau, hote.firstChild);

  // Garde-fou serveur-independant : aucune ecriture ne peut partir d'une page
  // qui n'a pas de reseau. On bloque a la source plutot que d'echouer plus tard.
  document.addEventListener('submit', (e) => {
    if (e.target.method && e.target.method.toLowerCase() === 'post') {
      e.preventDefault();
      bandeau.classList.add('secoue');
      setTimeout(() => bandeau.classList.remove('secoue'), 500);
    }
  }, true);

  // Le retour du reseau recharge la page pour retrouver les donnees fraiches.
  window.addEventListener('online', () => location.reload());
})();

/* ------------------------------------ Sidebar : sections repliables
   Chaque groupe de la barre laterale est un <details> : il fonctionne donc
   sans JavaScript. Le script ajoute deux choses : la memorisation de l'etat
   ouvert/ferme d'une page a l'autre, et le reperage de la section qui
   contient la page courante. */
(function () {
  const sections = document.querySelectorAll('.nav .nav-sect');
  if (!sections.length) return;

  const CLE = 'casaone.nav.sections';
  const lire = () => {
    try { return JSON.parse(localStorage.getItem(CLE)) || {}; } catch (e) { return {}; }
  };
  const ecrire = (etat) => {
    try { localStorage.setItem(CLE, JSON.stringify(etat)); } catch (e) { /* mode prive */ }
  };

  const etat = lire();
  sections.forEach(sect => {
    const id = sect.dataset.sect;
    const porteActif = !!sect.querySelector('a.actif');
    if (porteActif) sect.classList.add('contient-actif');

    // Un choix explicite de l'utilisateur prime. A defaut on garde l'etat rendu
    // par le serveur, qui deplie deja la section de la page courante.
    if (id in etat) sect.open = etat[id];

    sect.addEventListener('toggle', () => {
      const courant = lire();
      courant[id] = sect.open;
      ecrire(courant);
    });
  });
})();

/* ------------------------------------------------------------ Graphiques */
if (window.Chart) {
  Chart.defaults.font.family = CSS.getPropertyValue('--police') || 'sans-serif';
  Chart.defaults.font.size = 11.5;
  Chart.defaults.color = T.doux;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.tooltip.backgroundColor = '#10241a';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.maintainAspectRatio = false;
}

const AXE_SOBRE = {
  grid: { color: T.bord, drawTicks: false },
  border: { display: false },
  ticks: { padding: 8 }
};
const AXE_NU = { grid: { display: false }, border: { display: false }, ticks: { padding: 6 } };

/* ------------------------------------- Barre de reperes : etat du reseau
   La seule tuile que le serveur ne peut pas remplir : une page rendue en
   ligne puis relue depuis le cache afficherait une connexion qui n'existe
   plus. Elle reste masquee tant que tout va bien — une tuile permanente
   « en ligne » n'apprend rien et prend la place des chiffres utiles. */
(function () {
  const tuile = document.getElementById('bi-reseau');
  if (!tuile) return;

  const valeur = document.getElementById('bi-reseau-val');
  const note = document.getElementById('bi-reseau-note');

  function enAttente() {
    if (typeof FileAttente === 'undefined') return Promise.resolve(0);
    return FileAttente.compter().catch(() => 0);
  }

  function rafraichir() {
    return enAttente().then(n => {
      const horsLigne = !navigator.onLine;
      if (!horsLigne && !n) { tuile.hidden = true; return; }

      tuile.hidden = false;
      tuile.classList.toggle('en-attente', !horsLigne);
      if (horsLigne) {
        valeur.textContent = 'Hors ligne';
        note.textContent = n
          ? n + (n > 1 ? ' saisies conservées' : ' saisie conservée')
          : 'saisies conservées sur l’appareil';
      } else {
        valeur.textContent = 'Envoi en cours';
        note.textContent = n + (n > 1 ? ' saisies à transmettre' : ' saisie à transmettre');
      }
    });
  }

  window.addEventListener('online', rafraichir);
  window.addEventListener('offline', rafraichir);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) rafraichir();
  });
  // La file se vide en arriere-plan (envoi immediat ou Background Sync) sans
  // prevenir la page : on la relit periodiquement. Un COUNT IndexedDB local,
  // donc sans reseau ni serveur.
  setInterval(rafraichir, 30000);
  rafraichir();
})();

/* ------------------------------------------- Horloge de la barre du haut
   L'heure de l'APPAREIL, pas celle du serveur : c'est celle que porte la
   montre de la personne, et celle qui datera ses pointages hors ligne. On se
   recale sur le debut de la minute suivante plutot que de battre toutes les
   secondes — une horloge qui n'affiche pas les secondes n'a rien a y gagner. */
(function () {
  const cible = document.getElementById('horloge-heure');
  if (!cible) return;

  function afficher() {
    const d = new Date();
    cible.textContent = String(d.getHours()).padStart(2, '0') + ':'
                      + String(d.getMinutes()).padStart(2, '0');
    const restant = (60 - d.getSeconds()) * 1000 - d.getMilliseconds();
    setTimeout(afficher, Math.max(1000, restant));
  }
  afficher();
  // Un telephone met l'onglet en veille : au retour, l'heure affichee est
  // fausse tant que le minuteur n'a pas repris.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) afficher(); });
})();

/* -------------------------------------------- Meteo de la barre du haut
   Le serveur interroge le fournisseur et met en cache ; la page ne fait qu'un
   appel a sa propre origine. Indisponible n'est pas une erreur : la tuile
   reste simplement masquee. */
(function () {
  const bloc = document.getElementById('outil-meteo');
  if (!bloc) return;

  const DESSINS = {
    'soleil': '<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/>',
    'soleil-nuage': '<circle cx="8.5" cy="8" r="3"/><path d="M8.5 2.5v1.4M3.5 8H2.1M4.9 4.4 3.9 3.4M12.1 4.4l1-1"/><path d="M17.5 12.5a3.5 3.5 0 0 1 0 7H8a4 4 0 0 1 0-8 5 5 0 0 1 9.5 1z"/>',
    'nuage': '<path d="M17.5 10.5a4 4 0 0 1 0 8H8a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 9.5 1z"/>',
    'brume': '<path d="M17.5 8.5a4 4 0 0 1 0 8H8a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 9.5 1z"/><path d="M4 20h6M14 20h6"/>',
    'pluie': '<path d="M17.5 7.5a4 4 0 0 1 0 8H8a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 9.5 1z"/><path d="M8 18.5 7 21M12 18.5 11 21M16 18.5 15 21"/>',
    'neige': '<path d="M17.5 7.5a4 4 0 0 1 0 8H8a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 9.5 1z"/><path d="M8 19.5v.01M12 19.5v.01M16 19.5v.01M10 21.5v.01M14 21.5v.01"/>',
    'orage': '<path d="M17.5 6.5a4 4 0 0 1 0 8H8a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 9.5 1z"/><path d="m13 15-3 4h3l-1.5 3.5"/>'
  };

  function dessiner(nom) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
         + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         + (DESSINS[nom] || DESSINS.nuage) + '</svg>';
  }

  fetch('/api/meteo', { headers: { 'Accept': 'application/json' } })
    .then(r => (r.ok ? r.json() : null))
    .then(m => {
      if (!m || !m.disponible) return;
      const ic = document.getElementById('meteo-ic');
      ic.className = 'meteo-ic ' + m.icone;
      ic.innerHTML = dessiner(m.icone);
      document.getElementById('meteo-temp').textContent = m.temperature + ' °C';
      document.getElementById('meteo-lib').textContent = m.libelle + ' · ' + m.ville;
      bloc.title = m.libelle + ' à ' + m.ville + ' — ' + m.mini + '/' + m.maxi
                 + ' °C, vent ' + m.vent + ' km/h';
      bloc.hidden = false;
    })
    .catch(() => { /* hors ligne : la meteo reste masquee */ });
})();

/* Un seul menu ouvert a la fois dans la barre du haut : cliquer ailleurs
   referme la cloche, comme pour le selecteur de projet. */
document.addEventListener('click', (e) => {
  const cloche = document.getElementById('cloche');
  if (cloche && cloche.open && !cloche.contains(e.target)) cloche.open = false;
});
