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
