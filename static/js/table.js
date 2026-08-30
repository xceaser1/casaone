/* Tableau de donnees : recherche, filtres, tri, pagination, CRUD, export.
   Tout est calcule cote serveur : le navigateur ne recoit qu'une page. */

const carte = document.getElementById('table-carte');
const CLE = carte.dataset.cle;
const FIXES = JSON.parse(carte.dataset.fixes || '{}');
const COLONNES = JSON.parse(carte.dataset.colonnes || '[]');

const etat = {
  page: 1,
  taille: 25,
  tri: CLE === 'betonnage' ? 'date_coulage' : 'zone',
  sens: CLE === 'betonnage' ? 'desc' : 'asc',
  q: '',
  filtres: {},
  date_min: '',
  date_max: '',
  droits: {}
};

let idEnCours = null;

/* --------------------------------------------------------- Parametres */
function parametres() {
  const p = new URLSearchParams();
  p.set('page', etat.page);
  p.set('taille', etat.taille);
  p.set('tri', etat.tri);
  p.set('sens', etat.sens);
  if (etat.q) p.set('q', etat.q);
  for (const [k, v] of Object.entries({ ...etat.filtres, ...FIXES })) if (v) p.set('f_' + k, v);
  if (etat.date_min) p.set('date_min', etat.date_min);
  if (etat.date_max) p.set('date_max', etat.date_max);
  return p;
}

/* ------------------------------------------------------------- Rendu */
function cellule(col, ligne) {
  const v = ligne[col.cle];
  switch (col.type) {
    case 'nombre':
      return `<td class="num">${nombre(v)}</td>`;
    case 'monnaie':
      return `<td class="num">${nombre(v)}</td>`;
    case 'pourcent':
      return `<td><div class="mini-jauge">
                <span class="piste"><i style="width:${Math.min(v || 0, 100)}%"></i></span>
                <b>${pourcent(v)}</b></div></td>`;
    case 'statut': {
      const cl = v === 'Valide' ? 'valide' : v === 'Non Valide' ? 'non' : 'cours';
      const lbl = v === 'Valide' ? 'Validé' : v === 'Non Valide' ? 'Non validé' : v;
      return `<td><span class="pastille ${cl}">${echapper(lbl)}</span></td>`;
    }
    default:
      return `<td>${echapper(v)}</td>`;
  }
}

function dessinerEntetes() {
  const cols = COLONNES.filter(c => !(c.cle in FIXES));
  const actions = etat.droits.edit || etat.droits.delete;
  document.getElementById('entetes').innerHTML =
    cols.map(c => {
      const actif = etat.tri === c.cle;
      const fleche = actif ? (etat.sens === 'asc' ? '↑' : '↓') : '↕';
      return `<th class="${c.tri ? 'triable' : ''} ${actif ? 'actif' : ''}" data-tri="${c.cle}">
                ${echapper(c.label)}<span class="fleche">${fleche}</span></th>`;
    }).join('') + (actions ? '<th style="text-align:right">Actions</th>' : '');
}

function dessiner(d) {
  const cols = COLONNES.filter(c => !(c.cle in FIXES));
  const actions = etat.droits.edit || etat.droits.delete;
  const corps = document.getElementById('corps');

  if (!d.lignes.length) {
    corps.innerHTML = `<tr><td colspan="${cols.length + 1}"><div class="vide">
      <b>Aucune ligne ne correspond</b>Modifiez la recherche ou réinitialisez les filtres.</div></td></tr>`;
    document.getElementById('pied').innerHTML = '';
  } else {
    corps.innerHTML = d.lignes.map(l => `<tr data-id="${l.id}">
      ${cols.map(c => cellule(c, l)).join('')}
      ${actions ? `<td style="text-align:right;white-space:nowrap">
        ${etat.droits.edit ? `<button class="btn mini" data-modifier="${l.id}">Modifier</button>` : ''}
        ${etat.droits.delete ? `<button class="btn mini btn-danger" data-supprimer="${l.id}">Supprimer</button>` : ''}
      </td>` : ''}</tr>`).join('');

    /* Pied de tableau : totaux de la selection courante */
    const totaux = d.totaux || {};
    if (Object.keys(totaux).length) {
      document.getElementById('pied').innerHTML = '<tr>' + cols.map((c, i) => {
        if (c.cle in totaux) return `<td class="num">${nombre(totaux[c.cle], 0)}</td>`;
        return i === 0 ? `<td>Total (${nombre(d.total, 0)} lignes)</td>` : '<td></td>';
      }).join('') + (actions ? '<td></td>' : '') + '</tr>';
    }
  }

  const debut = d.total ? (d.page - 1) * d.taille + 1 : 0;
  const fin = Math.min(d.page * d.taille, d.total);
  document.getElementById('info-pagination').textContent =
    `${nombre(debut, 0)}–${nombre(fin, 0)} sur ${nombre(d.total, 0)} lignes`;
  document.getElementById('compteur').textContent = `${nombre(d.total, 0)} lignes`;
  dessinerPages(d);
}

function dessinerPages(d) {
  const zone = document.getElementById('pages');
  const boutons = [];
  const ajouter = (lbl, page, actif = false, off = false) =>
    boutons.push(`<button class="btn mini ${actif ? 'btn-vert' : ''}" data-page="${page}" ${off ? 'disabled' : ''}>${lbl}</button>`);

  ajouter('‹', d.page - 1, false, d.page <= 1);
  const debut = Math.max(1, d.page - 2);
  const fin = Math.min(d.pages, debut + 4);
  for (let p = debut; p <= fin; p++) ajouter(p, p, p === d.page);
  ajouter('›', d.page + 1, false, d.page >= d.pages);
  zone.innerHTML = boutons.join('');
}

/* --------------------------------------------------------- Chargement */
async function charger() {
  try {
    const d = await api(`/api/data/${CLE}?` + parametres().toString());
    etat.droits = d.droits;
    dessinerEntetes();
    dessiner(d);
  } catch (e) {
    document.getElementById('corps').innerHTML =
      `<tr><td colspan="9"><div class="vide"><b>Chargement impossible</b>${echapper(e.message)}</div></td></tr>`;
  }
}

/* ------------------------------------------------------------ Ecoutes */
let minuteur;
document.getElementById('q').addEventListener('input', e => {
  clearTimeout(minuteur);
  minuteur = setTimeout(() => { etat.q = e.target.value.trim(); etat.page = 1; charger(); }, 280);
});

document.getElementById('taille').addEventListener('change', e => {
  etat.taille = parseInt(e.target.value, 10); etat.page = 1; charger();
});

document.getElementById('filtres').addEventListener('change', e => {
  if (e.target.dataset.filtre) {
    etat.filtres[e.target.dataset.filtre] = e.target.value;
  } else if (e.target.id === 'date_min' || e.target.id === 'date_max') {
    etat[e.target.id] = e.target.value;
  }
  etat.page = 1;
  charger();
});

document.getElementById('btn-reset').addEventListener('click', () => {
  etat.q = ''; etat.filtres = {}; etat.date_min = ''; etat.date_max = ''; etat.page = 1;
  document.getElementById('q').value = '';
  document.querySelectorAll('#filtres select, #filtres input').forEach(el => { el.value = ''; });
  charger();
});

document.getElementById('entetes').addEventListener('click', e => {
  const th = e.target.closest('th[data-tri]');
  if (!th || !th.classList.contains('triable')) return;
  const cle = th.dataset.tri;
  etat.sens = etat.tri === cle && etat.sens === 'asc' ? 'desc' : 'asc';
  etat.tri = cle;
  charger();
});

document.getElementById('pages').addEventListener('click', e => {
  const b = e.target.closest('button[data-page]');
  if (b && !b.disabled) { etat.page = parseInt(b.dataset.page, 10); charger(); }
});

document.querySelectorAll('[data-export]').forEach(b => b.addEventListener('click', () => {
  window.location = `/api/export/${CLE}.${b.dataset.export}?` + parametres().toString();
}));

/* --------------------------------------------------------------- CRUD */
function afficherChamps() {
  document.querySelectorAll('#m-form [data-champ]').forEach(l => { l.style.display = ''; });
}

document.getElementById('btn-ajouter')?.addEventListener('click', () => {
  idEnCours = null;
  document.getElementById('m-titre').textContent = 'Ajouter une ligne';
  document.getElementById('m-form').reset();
  document.getElementById('m-erreurs').innerHTML = '';
  if (FIXES.type_dalle) {
    const s = document.querySelector('#m-form [name=type_dalle]');
    if (s) s.value = FIXES.type_dalle;
  }
  afficherChamps();
  ouvrirModale('m-edition');
});

document.getElementById('corps').addEventListener('click', async e => {
  const bModifier = e.target.closest('[data-modifier]');
  const bSupprimer = e.target.closest('[data-supprimer]');

  if (bModifier) {
    const tr = bModifier.closest('tr');
    idEnCours = parseInt(bModifier.dataset.modifier, 10);
    document.getElementById('m-titre').textContent = 'Modifier la ligne';
    document.getElementById('m-erreurs').innerHTML = '';
    afficherChamps();
    /* On pre-remplit depuis les cellules affichees */
    const cols = COLONNES.filter(c => !(c.cle in FIXES));
    cols.forEach((c, i) => {
      const champ = document.querySelector(`#m-form [name="${c.cle}"]`);
      if (!champ) return;
      const brut = tr.children[i].innerText.trim().replace(/\s/g, '').replace(',', '.');
      champ.value = c.type === 'nombre' ? brut : tr.children[i].innerText.trim();
    });
    ouvrirModale('m-edition');
  }

  if (bSupprimer) {
    if (!confirmerSuppression('Supprimer définitivement cette ligne ?')) return;
    try {
      await api(`/api/data/${CLE}/${bSupprimer.dataset.supprimer}`, { method: 'DELETE' });
      notifier('Ligne supprimée.');
      charger();
    } catch (err) { notifier(err.message, 'erreur'); }
  }
});

document.getElementById('m-valider')?.addEventListener('click', async () => {
  const form = document.getElementById('m-form');
  const donnees = {};
  new FormData(form).forEach((v, k) => { donnees[k] = v; });
  if (FIXES.type_dalle) donnees.type_dalle = FIXES.type_dalle;

  const zoneErreurs = document.getElementById('m-erreurs');
  zoneErreurs.innerHTML = '';

  /* Validation avant sauvegarde : on previent l'utilisateur des incoherences. */
  const tot = parseFloat(donnees.surface_totale ?? 'NaN');
  const coul = parseFloat(donnees.surface_coulee ?? 'NaN');
  if (!isNaN(tot) && !isNaN(coul) && coul > tot) {
    if (!window.confirm('La surface coulée dépasse la surface totale.\nEnregistrer quand même ?')) return;
  }

  try {
    if (idEnCours) {
      await api(`/api/data/${CLE}/${idEnCours}`, { method: 'PUT', body: JSON.stringify(donnees) });
      notifier('Modification enregistrée.');
    } else {
      await api(`/api/data/${CLE}`, { method: 'POST', body: JSON.stringify(donnees) });
      notifier('Ligne ajoutée.');
    }
    fermerModale('m-edition');
    charger();
  } catch (err) {
    zoneErreurs.innerHTML = `<div class="alerte erreur">${echapper(err.message)}</div>`;
  }
});

charger();
