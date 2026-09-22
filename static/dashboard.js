/**
 * L'ÉTAT D'UN INDICATEUR, PORTÉ PAR SA BANDE D'ACCENT.
 *
 * ⚠️ `null` RETIRE L'ATTRIBUT PLUTÔT QUE DE POSER UNE VALEUR NEUTRE. Un indicateur sans donnée
 * n'est pas « bon » : la bande reprend la couleur de la bordure, et l'œil ne s'y arrête pas.
 */
/**
 * Pose l'état d'un indicateur sur le CONTENEUR qui le porte.
 *
 * ⚠️ LE CHIFFRE RESTE EN ENCRE, C'EST LA BANDE QUI PORTE L'ÉTAT. Un nombre coloré est plus
 * difficile à lire qu'un nombre noir, et sur douze indicateurs colorés plus rien ne ressort.
 *
 * ⚠️ LA LISTE DES CONTENEURS DOIT SUIVRE LES FORMES DE LA PAGE. Elle ne connaissait que
 * `.kpi-cell` : appelée depuis le bandeau-réponse, qui est une `.tx-answer`, elle ne trouvait
 * rien et ne faisait RIEN — l'état était calculé puis jeté en silence. Le pire cas : la
 * fonction a l'air appelée, la couleur n'apparaît jamais, et on cherche le bogue dans le CSS.
 */
function etat(el, valeur){
  var cel = el && el.closest ? el.closest('.kpi-cell, .tx-answer, .maillon') : null;
  if (!cel) return;
  if (valeur) cel.setAttribute('data-etat', valeur);
  else cel.removeAttribute('data-etat');
}

/**
 * Pose un repère de cible sur une barre de progression.
 *
 * ⚠️ LE REPÈRE EST DANS LA BARRE, PAS À CÔTÉ. Une légende « cible 65 % » sous le graphique
 * oblige à convertir mentalement une largeur en pourcentage — c'est exactement le calcul qu'un
 * repère évite.
 */
function marquerSeuil(barre, pct, libelle){
  if (!barre || !barre.parentElement) return;
  var enveloppe = barre.parentElement;
  enveloppe.classList.add('seuil-wrap');
  var vieux = enveloppe.querySelector('.seuil-marque');
  if (vieux) vieux.remove();
  var m = document.createElement('div');
  m.className = 'seuil-marque';
  m.style.left = Math.max(0, Math.min(100, pct)) + '%';
  if (libelle) m.title = libelle;
  enveloppe.appendChild(m);
}

const COLORS = ['#2554C7','rgba(37,84,199,.7)','rgba(37,84,199,.5)','rgba(37,84,199,.35)','rgba(37,84,199,.2)','rgba(37,84,199,.12)'];
const BAR_ACTIVE = '#2554C7';
const BAR_IDLE   = 'rgba(37,84,199,.12)';
let chartHourly = null, chartWeek = null;
let chartCurve  = null, chartDaily = null;

// ── Preset actif ──────────────────────────────────────────────────────────────
let currentPreset = 'today';
let customStart = null, customEnd = null;

function setPreset(p) {
  currentPreset = p;
  document.getElementById('custom-range-bar').style.display = 'none';
  /* ⚠️ LE SEGMENTÉ SE MARQUE PAR `aria-pressed`, PAS PAR UNE CLASSE. L'ancienne bascule visait
   * `.pill`, qui n'existe plus : le bouton cliqué restait gris, la page se rechargeait, et rien
   * ne disait quelle période était active. */
  document.querySelectorAll('#period-pills button[data-preset]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(btn.dataset.preset === p));
  });
  loadData();
}

function openCustomRange() {
  const bar = document.getElementById('custom-range-bar');
  bar.style.display = bar.style.display === 'none' ? 'flex' : 'none';
  document.querySelectorAll('#period-pills button[data-preset]').forEach(btn => {
    btn.setAttribute('aria-pressed', String(btn.dataset.preset === 'custom'));
  });
  if (!document.getElementById('custom-start').value) {
    const today = new Date().toISOString().slice(0, 10);
    document.getElementById('custom-start').value = today;
    document.getElementById('custom-end').value = today;
  }
}

function applyCustomRange() {
  const start = document.getElementById('custom-start').value;
  const end = document.getElementById('custom-end').value;
  if (!start || !end) return;
  customStart = start;
  customEnd = end;
  currentPreset = 'custom';
  loadData();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function marginBadge(pct) {
  const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? '#b07d00' : 'var(--red)';
  return `<span style="color:${color};font-weight:500">${pct}%</span>`;
}

const fmt = n => new Intl.NumberFormat('en-IE', {
  style: 'currency', currency: 'EUR', minimumFractionDigits: 2
}).format(n);

function delta(cur, prev, label) {
  label = label || 'vs prev. period';
  if (prev == null || prev === 0) return '';
  const pct = Math.round((cur - prev) / Math.abs(prev) * 100);
  const up = pct >= 0;
  // Pastille Mesa (flèche + %) suivie du libellé en gris.
  return `<span class="${up ? 'delta-up' : 'delta-down'}">${up ? '▲ +' : '▼ '}${pct}%</span>`
       + `<span style="color:var(--muted);margin-left:8px;font-size:11.5px;">${label}</span>`;
}

// Pastille seule (flèche + %), sans libellé — pour le strip Today.

// "Sat 18 Jul"

// Strip "Today" : snapshot du jour + delta vs jour ouvré précédent.

function fmtDate(iso) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
}

// ── Chargement (stale-while-revalidate) ──────────────────────────────────────
// Affiche instantanément les dernières données connues (localStorage), puis
// rafraîchit en arrière-plan. force=true (bouton ↻) bypasse les caches serveur.
// Journée en cours dans l'économie de la période. Par défaut NON : elle
// n'apporte qu'une recette partielle mais une journée entière de charges.
let inclToday = false;
try { inclToday = localStorage.getItem('estu_incl_today') === '1'; } catch (e) {}

function toggleInclToday() {
  inclToday = document.getElementById('incl-today').checked;
  try { localStorage.setItem('estu_incl_today', inclToday ? '1' : '0'); } catch (e) {}
  loadData(true);
}

async function loadData(force = false) {
  const preset = currentPreset;
  const isCustom = preset === 'custom' && customStart && customEnd;
  // La clé de cache porte le choix : sans lui, basculer le bouton réaffichait
  // les chiffres de l'autre périmètre le temps d'un aller-retour.
  const cacheKey = 'estu_data_' + preset + (inclToday ? '_incl' : '')
                 + (isCustom ? '_' + customStart + '_' + customEnd : '');
  if (!force) {
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) render(JSON.parse(cached));
    } catch(e) {}
  }
  if (window.uiLoadStart) uiLoadStart();
  try {
    const incl = inclToday ? '&incl_today=1' : '';
    const url = isCustom
      ? `/api/data?preset=custom&start_date=${customStart}&end_date=${customEnd}${incl}${force ? '&fresh=1' : ''}`
      : '/api/data?preset=' + preset + incl + (force ? '&fresh=1' : '');
    const r = await fetch(url);
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    if (preset !== currentPreset) return;   // l'utilisateur a changé de vue entre-temps
    render(d);
    try { localStorage.setItem(cacheKey, JSON.stringify(d)); } catch(e) {}
    document.getElementById('error-banner').style.display = 'none';
  } catch(e) {
    document.getElementById('error-msg').textContent = e.message;
    document.getElementById('error-banner').style.display = 'block';
  } finally {
    if (window.uiLoadEnd) uiLoadEnd();
  }
}

// ── Clients récurrents (empreintes de cartes, voir revolut_merchant.py) ──────
// Chargé à part : petite table Supabase, inutile d'alourdir /api/data.
let _retReq = 0;

// Reconstruction : 10 jours par appel (timeout serverless), de l'ouverture à
// aujourd'hui. Admin seulement — un 403 arrête tout et le dit.

// ── Rendu principal ───────────────────────────────────────────────────────────
/**
 * LA RÉPONSE DU HAUT : « est-ce qu'on couvre nos coûts ? »
 *
 * ⚠️ LA PAGE OUVRAIT SUR HUIT CELLULES DE MÊME POIDS, en deux grilles décrivant la même
 * période. Aucune ne répondait à la question qu'on se pose en ouvrant un tableau de bord de
 * café : est-ce que la journée paie ce qu'elle coûte ? On la reconstituait de tête, chaque
 * matin, à partir du résultat et du point mort lus dans deux coins différents.
 *
 * ⚠️ LE VERDICT NOIR QUI VIVAIT ICI NE S'AFFICHAIT QUE SUR « AUJOURD'HUI ». Les six autres
 * périodes n'avaient pas de réponse du tout — et « ce mois-ci » est précisément celle qu'on
 * regarde pour décider quelque chose.
 *
 * ⚠️ ET « PAS DE DONNÉE » N'EST PAS « À L'ÉQUILIBRE ». Sans prix d'achat, le résultat n'est pas
 * calculable : la réponse le dit et nomme le geste, au lieu d'afficher un zéro rassurant.
 */
/* ═══════════════════════════════════════════════════════════════════════════════════════════
   LA COURBE — et la comparaison en pointillés.
   ═══════════════════════════════════════════════════════════════════════════════════════════

   ⚠️ « −9 % » DIT DE COMBIEN ; LA COURBE DIT QUAND. Un samedi creux et cinq jours identiques
   donnent le même pourcentage et appellent deux gestes opposés. La série précédente est tracée
   en pointillés par-dessus, alignée sur le même axe.

   ⚠️ ET LE POINT MORT EST UNE LIGNE, PAS UNE CARTE. Tracé à `seuil_ca_ttc_jour`, il dit d'un
   coup d'œil quels services ont payé leur journée — ce qu'aucun pourcentage ne montre.
   ═══════════════════════════════════════════════════════════════════════════════════════════ */
let chartMini = {};

function jetons() {
  const c = getComputedStyle(document.querySelector('.db') || document.documentElement);
  const v = (n) => (c.getPropertyValue(n) || '').trim();
  return {
    iris: v('--db-iris') || '#635BFF',
    slate: v('--db-slate') || '#A3ACBA',
    line: v('--db-line-soft') || '#EDF1F6',
    faint: v('--db-faint') || '#8792A2',
    ink: v('--db-ink') || '#1A1F36',
    card: v('--db-card') || '#FFFFFF',
    green: v('--db-green') || '#067647',
  };
}

/** Un dégradé vertical sous la courbe, comme Stripe. */
function voile(ctx, couleur, h) {
  const g = ctx.createLinearGradient(0, 0, 0, h || 200);
  g.addColorStop(0, couleur + '38');
  g.addColorStop(1, couleur + '00');
  return g;
}

function renderCourbe(d) {
  const cv = document.getElementById('chart-daily');
  if (!cv || typeof Chart === 'undefined') return;
  const j = jetons();
  const jours = (d.daily || []);
  const comp = (d.daily_comp || []);

  /* ⚠️ LA COMPARAISON EST ALIGNÉE SUR LE RANG, PAS SUR LA DATE. Les deux fenêtres n'ont pas les
   * mêmes quantièmes — c'est tout l'intérêt d'une comparaison à nombre de services égal. On
   * superpose donc le 1er service au 1er, le 2e au 2e. Les aligner par date ferait glisser la
   * courbe d'un cran à chaque jour fermé. */
  const n = Math.max(jours.length, comp.length);
  const labels = [];
  for (let i = 0; i < n; i++) {
    const x = jours[i];
    labels.push(x ? new Date(x.date + 'T12:00:00')
      .toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric' }) : '');
  }
  const serie = [], precedente = [];
  for (let i = 0; i < n; i++) {
    serie.push(jours[i] ? jours[i].ca_ttc : null);
    precedente.push(comp[i] ? comp[i].ca_ttc : null);
  }

  const seuilJour = d.economics && d.economics.seuil_ca_ttc_jour;
  const jeux = [
    {
      label: 'Encaissé', data: serie, borderColor: j.iris, borderWidth: 2.5,
      pointRadius: 0, pointHoverRadius: 4, tension: .25, fill: true,
      backgroundColor: (c) => voile(c.chart.ctx, j.iris, c.chart.height),
      spanGaps: false, order: 1,
    },
  ];
  if (precedente.some((v) => v != null)) {
    jeux.push({
      label: 'Période précédente', data: precedente, borderColor: j.slate, borderWidth: 2,
      borderDash: [5, 5], pointRadius: 0, pointHoverRadius: 3, tension: .25, fill: false,
      spanGaps: false, order: 2,
    });
  }
  if (seuilJour > 0) {
    jeux.push({
      label: 'Point mort / service', data: new Array(n).fill(seuilJour),
      borderColor: j.ink, borderWidth: 1.5, borderDash: [2, 5], pointRadius: 0,
      pointHoverRadius: 0, fill: false, order: 3,
    });
  }

  if (chartDaily) chartDaily.destroy();
  chartDaily = new Chart(cv.getContext('2d'), {
    type: 'line',
    data: { labels, datasets: jeux },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: j.ink, padding: 10, displayColors: true, boxWidth: 8, boxHeight: 8,
          callbacks: {
            /* ⚠️ UN TROU N'EST PAS UN ZÉRO. Un jour fermé n'a pas de point ; l'infobulle doit
             * le dire plutôt que d'afficher 0 €, qui se lirait « ouvert, personne n'est venu ». */
            label: (c) => c.raw == null
              ? ` ${c.dataset.label} : non mesuré`
              : ` ${c.dataset.label} : ${fmt(c.raw)}`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true, border: { display: false },
          grid: { color: j.line },
          ticks: { font: { size: 11 }, color: j.faint, maxTicksLimit: 5,
                   callback: (v) => fmt(v) },
        },
        x: {
          grid: { display: false }, border: { display: false },
          ticks: { font: { size: 11 }, color: j.faint, maxRotation: 0, autoSkipPadding: 18 },
        },
      },
    },
  });
}

/** Une mini-courbe, sans axes : la forme suffit, le chiffre est au-dessus. */
function miniCourbe(id, valeurs, couleur) {
  const cv = document.getElementById(id);
  if (!cv || typeof Chart === 'undefined') return;
  const mesures = (valeurs || []).filter((v) => v != null);
  if (chartMini[id]) { chartMini[id].destroy(); chartMini[id] = null; }
  /* ⚠️ MOINS DE DEUX POINTS NE FAIT PAS UNE COURBE. Un seul point tracé donne une ligne plate
   * qui se lit « stable » — alors qu'on n'a rien mesuré du tout. */
  if (mesures.length < 2) { cv.style.display = 'none'; return; }
  cv.style.display = '';
  chartMini[id] = new Chart(cv.getContext('2d'), {
    type: 'line',
    data: { labels: valeurs.map(() => ''), datasets: [{
      data: valeurs, borderColor: couleur, borderWidth: 2, pointRadius: 0,
      tension: .3, fill: true,
      backgroundColor: (c) => voile(c.chart.ctx, couleur, 60), spanGaps: false,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false, beginAtZero: false } },
    },
  });
}

function renderMinis(d) {
  const j = jetons();
  const jours = d.daily || [];
  miniCourbe('mini-tickets', jours.map((x) => x.nb), j.iris);
  miniCourbe('mini-ticket', jours.map((x) => (x.nb ? x.ca_ttc / x.nb : null)), j.green);
  /* ⚠️ LA MARGE N'EXISTE PAS JOUR PAR JOUR DANS CETTE CHARGE UTILE. Tracer le CA HT à sa place
   * donnerait une courbe crédible et fausse — on dessinerait des ventes en croyant lire une
   * marge. La carte garde son chiffre et se passe de courbe. */
  miniCourbe('mini-marge', [], j.iris);
}

/**
 * LES QUATRE MESURES QU'AUCUNE AUTRE CARTE NE PORTE.
 *
 * ⚠️ « OÙ VA L'ARGENT » DÉCOMPOSAIT CE QUE LES DEUX SEUILS RÉSUMENT DÉJÀ : la part de
 * marchandise et de personnel EST le prime cost, et le reste est le résultat, affiché en tête.
 * Une décomposition qui n'ajoute rien à ce qu'on vient de lire fait douter des deux.
 *
 * ⚠️ CHACUNE DE CES QUATRE DIT « — » PLUTÔT QU'UN ZÉRO quand elle n'est pas mesurée. « Aucune
 * donnée » et « zéro » mènent à des décisions opposées, et sur une carte de trois lignes rien
 * ne les distingue si l'on écrit 0.
 */
function renderQuatre(d) {
  const E = (id) => document.getElementById(id);
  const eco = d.economics || {};

  /* Par jour de semaine — le jour qui porte le chiffre, et l'écart au plus faible. */
  const wd = d.weekdays;
  if (Array.isArray(wd) && wd.length) {
    const JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];
    const tri = wd.slice().sort((a, b) => a.day - b.day);
    const max = Math.max(...tri.map((x) => x.avg_ca));
    const fort = wd[0];
    E('db-wd-v').textContent = JOURS[fort.day] || '—';
    E('db-wd').innerHTML = tri.map((x) => {
      const h = max > 0 ? Math.max(3, Math.round(x.avg_ca / max * 26)) : 3;
      const on = x.day === fort.day;
      return `<span title="${JOURS[x.day]} · ${fmt(x.avg_ca)} en moyenne" style="display:inline-block;`
        + `width:11px;height:${h}px;margin-right:3px;border-radius:2px;vertical-align:bottom;`
        + `background:var(--db-${on ? 'iris' : 'line'})"></span>`;
    }).join('');
    E('db-wd-sub').innerHTML = `<span>${fmt(fort.avg_ca)} en moyenne · ${fort.n_days} jours</span>`;
  } else {
    E('db-wd-v').textContent = '—';
    E('db-wd').innerHTML = '';
    E('db-wd-sub').innerHTML = '<span>pas encore assez de jours pleins</span>';
  }

  /* TVA collectée — ce qui est encaissé et qui n'appartient pas au café. */
  if (d.today && d.today.ca != null && d.today.ca_ht != null) {
    const tva = d.today.ca - d.today.ca_ht;
    E('db-tva').textContent = fmt(tva);
    E('db-tva-sub').innerHTML =
      `<span>${(d.today.ca ? tva / d.today.ca * 100 : 0).toFixed(1)} % de l’encaissé</span>`;
  } else {
    E('db-tva').textContent = '—';
    E('db-tva-sub').innerHTML = '';
  }

  /* Articles par ticket — la vente additionnelle, qui ne se lit nulle part ailleurs. */
  const bk = d.insights && d.insights.basket;
  if (bk && bk.items_per_ticket != null) {
    E('db-panier').textContent = bk.items_per_ticket.toFixed(2).replace('.', ',');
    E('db-panier-sub').innerHTML = bk.attach_pct != null
      ? `<span>${bk.attach_pct} % des tickets portent 2 articles ou plus</span>` : '';
  } else {
    E('db-panier').textContent = '—';
    E('db-panier-sub').innerHTML = '<span>pas encore assez de données</span>';
  }

  /* Couverture des coûts — la seule des quatre qui appelle un geste. */
  const cov = eco.cogs_coverage_pct;
  if (cov != null) {
    E('db-couv').textContent = cov + ' %';
    E('db-couv-bar').style.width = Math.min(100, cov) + '%';
    /* ⚠️ SOUS 100 %, LA MARGE EST EXTRAPOLÉE — donc le résultat et le point mort aussi. La
     * carte renvoie vers l'écran qui répare, plutôt que de constater. */
    E('db-couv-sub').innerHTML = cov >= 99
      ? '<span class="db-badge up">tous les coûts connus</span>'
      : `<span class="db-badge warn">marge extrapolée</span><span class="db-link">Compléter →</span>`;
  } else {
    E('db-couv').textContent = '—';
    E('db-couv-bar').style.width = '0%';
    E('db-couv-sub').innerHTML = '<span class="db-link">Ouvrir COGS →</span>';
  }
}

function renderReponse(d) {
  const eco = d.economics || {};
  const E = (id) => document.getElementById(id);
  const note = E('db-note');
  const jours = eco.open_days != null ? eco.open_days : null;

  /* ⚠️ LE MÊME COMPTE QUE LA LIGNE DE PÉRIODE. `open_days` vient de `daily_economics`, qui
   * reçoit la fenêtre RÉELLEMENT calculée : les deux sont d'accord par construction. Les
   * laisser diverger ferait lire « 412 € sur 5 services » à côté de « 4 services ». */
  E('db-res-l').textContent = 'Résultat'
    + (d.is_single_day ? '' : (jours ? ` · ${jours} service${jours > 1 ? 's' : ''}` : ''));

  /* ⚠️ LE POINT MORT EST DIT EN EUROS, PAS EN POURCENTAGE. « 145 % » ne se compare à rien
   * qu'on connaisse ; « 1 430 € » se compare à une journée de caisse. */
  if (eco.seuil_ca_ttc != null) {
    E('db-seuil').textContent = fmt(eco.seuil_ca_ttc);
    E('db-seuil-sub').innerHTML = eco.manque_seuil > 0
      ? `<span class="db-badge warn">${fmt(eco.manque_seuil)} manquants</span>`
      : `<span class="db-badge up">dépassé</span>`;
  } else {
    E('db-seuil').textContent = '—';
    E('db-seuil-sub').textContent = '';
  }

  if (eco.ebitda_ht == null) {
    /* ⚠️ « PAS DE DONNÉE » N'EST PAS « À L'ÉQUILIBRE ». Afficher 0 € rassurerait à tort ; dire
     * seulement « non calculable » laisse devant un écran mort sans indiquer le geste. */
    E('db-res').textContent = '—';
    E('db-res').style.color = '';
    E('db-res-sub').innerHTML = '';
    note.innerHTML = 'Le résultat se calcule à partir de la marge, donc des prix d’achat. '
      + '<a href="/cogs" class="db-link">Ouvrir COGS &amp; recettes →</a>';
    note.style.display = '';
    return;
  }

  const couvre = eco.ebitda_ht >= 0;
  E('db-res').textContent = fmt(eco.ebitda_ht);
  E('db-res').style.color = couvre ? 'var(--db-green)' : 'var(--db-red)';

  /* ⚠️ LE MANQUE EST DIT EN EUROS DE VENTES, PAS EN RÉSULTAT. « Il manque 180 € » de résultat
   * n'indique aucun geste ; « il manque 740 € de ventes » se compare à une journée. Les deux
   * diffèrent du taux de marge, et c'est le second qu'on peut viser. */
  E('db-res-sub').innerHTML = couvre
    ? '<span class="db-badge up">coûts couverts</span>'
    : `<span class="db-badge down">${fmt(eco.manque_seuil || 0)} de ventes manquantes</span>`;

  /* ⚠️ CE QUI EST ESTIMÉ SE DIT À CÔTÉ DU CHIFFRE. Sous la couverture complète des coûts, la
   * marge est extrapolée — donc le résultat ET le point mort le sont aussi. Le taire ferait
   * lire un résultat mesuré là où il y a une projection. */
  if (eco.marge_is_estimated === true) {
    note.innerHTML = `Marge extrapolée sur <b>${eco.cogs_coverage_pct} %</b> des ventes — `
      + 'le résultat et le point mort en héritent.';
    note.style.display = '';
  } else {
    note.style.display = 'none';
  }
}

function render(d) {
  window._lastData = d;
  /* ⚠️ « RETURNING CUSTOMERS » A DEUX PAGES À LUI : `/clientes` analyse les empreintes de
   * cartes du terminal, `/loyalty` suit le rattachement au programme. Les tuiles d'ici ne
   * faisaient que renvoyer vers la première.
   */
  // Bandeau warnings — sources de données en échec
  const warnBanner = document.getElementById('warn-banner');
  if (d.warnings && d.warnings.length) {
    document.getElementById('warn-msg').textContent = d.warnings.join(' · ');
    warnBanner.style.display = '';
  } else {
    warnBanner.style.display = 'none';
  }

  // Sous-titre
  let subtitle = 'Alcântara';
  if (d.is_single_day) {
    subtitle += ' — ' + fmtDate(d.date);
  } else {
    subtitle += ' — ' + d.period_label
      + ' (' + new Date(d.from_date+'T12:00:00').toLocaleDateString('fr-FR', {day:'numeric',month:'short'})
      + ' → ' + new Date(d.to_date  +'T12:00:00').toLocaleDateString('fr-FR', {day:'numeric',month:'short',year:'numeric'})
      + ')';
  }
  document.getElementById('subtitle').textContent = subtitle;

  // Le titre de page porte la période choisie.
  document.getElementById('db-titre').textContent = d.is_single_day
    ? (d.is_today ? 'Aujourd’hui' : fmtDate(d.date).replace(/^\w/, c => c.toUpperCase()))
    : d.period_label;

  // Mis à jour
  const updatedEl = document.getElementById('updated-at');
  if (d.is_today) {
    updatedEl.textContent = 'Updated at ' + d.updated_at;
    updatedEl.style.display = '';
  } else {
    updatedEl.style.display = 'none';
  }

  // Label comparaison — en vue "aujourd'hui live", comparaison à la même heure
  // du dernier jour ouvré (sinon la métrique est faussée avant la fermeture).
  const compLabel = d.comp_label || (d.is_single_day ? 'vs le service précédent' : 'vs période précédente');

  // Bouton « journée en cours » : visible seulement là où il change quelque chose
  const inclBar = document.getElementById('incl-today-bar');
  if (inclBar) {
    const can = !!(d.economics && d.economics.today_toggleable);
    inclBar.style.display = can ? 'flex' : 'none';
    if (can) {
      document.getElementById('incl-today').checked = inclToday;
      document.getElementById('incl-today-hint').textContent = inclToday
        ? '— charges d\u2019une journée entière face à une recette partielle'
        : '';
    }
  }

  // ── Les trois chiffres du bandeau ────────────────────────────────────────
  document.getElementById('db-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    // Le brut reste écrit : c'est lui qui coïncide avec Vendus, la trésorerie
    // et la page comptable. Le net est ce que le café gagne réellement.
    // ⚠️ MÊME PÉRIMÈTRE QUE LE GRAND CHIFFRE. `economics` s'arrête à hier ;
    // reprendre son ca_ht ici affichait un HT + TVA qui ne recomposait pas le
    // total affiché juste au-dessus. Les stats couvrent la période entière.
    const chef = d.today.popup_chef;
    document.getElementById('db-ca-sub').innerHTML =
      `<span>${fmt(d.today.ca_ht)} HT · TVA ${fmt(d.today.ca - d.today.ca_ht)}</span>`
      + (chef ? `<span class="db-badge iris">${fmt(chef)} reversé au chef</span>` : '');
  } else {
    document.getElementById('db-ca-sub').textContent = '';
  }
  // Deltas "vs yesterday" seulement en jour unique. En multi-jours, le strip
  // Today porte la comparaison ; le bloc période reste descriptif (comme Mesa).
  // Deltas vs période de comparaison — sur TOUTES les périodes (le backend
  // aligne la fenêtre : même jour / mêmes jours de semaine / même quantième).
  // delta() renvoie '' si la période de comparaison est vide (ex. since opening).
  /* ⚠️ L'ÉCART DU CHIFFRE D'AFFAIRES REJOINT LE BANDEAU, ET LA DÉCOMPOSITION « trafic ×
   * panier » DISPARAÎT. Elle expliquait POURQUOI le chiffre bougeait — utile, et déjà porté
   * par les deux cartes Tickets et Ticket moyen, qui montrent chacune sa propre courbe. Deux
   * façons de dire la même chose, dont une en pourcentages imbriqués.
   */
  const caDelta = delta(d.today.ca, d.yesterday.ca, compLabel);
  const caSub = document.getElementById('db-ca-sub');
  if (caDelta) caSub.insertAdjacentHTML('afterbegin', caDelta);

  const openDays = d.economics?.open_days || 0;
  const nbPerDayEl = document.getElementById('kpi-nb-perday');
  if (!d.is_single_day && openDays > 1) {
    const tx = d.basket && d.basket.tx_per_open_day;
    nbPerDayEl.innerHTML = tx != null
      ? `<strong style="color:var(--text)">${tx}</strong>`
        + `<span style="color:var(--faint);font-size:11px;"> tickets / jour ouvert`
        + ` · ${d.basket.tx_basis_days} j pleins</span>`
      : `<span style="color:var(--muted)">—</span>`
        + `<span style="color:var(--faint);font-size:11px;"> tickets / jour ouvert`
        + ` · ${(d.basket && d.basket.tx_basis_reason) || 'indisponible'}</span>`;
  } else {
    /* ⚠️ `perDayEl` A ÉTÉ SUPPRIMÉ AVEC LA CARTE QUI LE PORTAIT, et cette ligne est restée.
     * `node --check` l'accepte — une variable non définie n'est une erreur qu'à L'EXÉCUTION,
     * et seulement quand la branche est prise : il fallait une période d'un seul jour pour la
     * traverser. Le rendu s'arrêtait là, et la page restait vide. */
    nbPerDayEl.innerHTML = '';
  }

  document.getElementById('kpi-nb').textContent         = d.today.nb;
  document.getElementById('kpi-nb-delta').innerHTML     = delta(d.today.nb, d.yesterday.nb, compLabel)
    || `<span style="color:var(--muted)">tickets (refunds deducted)</span>`;
  document.getElementById('kpi-ticket').textContent     = fmt(d.today.ticket);
  // Delta et médiane sur DEUX lignes distinctes → la médiane reste toujours
  // visible, y compris sur TODAY où le libellé de delta est long.
  document.getElementById('kpi-ticket-delta').innerHTML = delta(d.today.ticket, d.yesterday.ticket, compLabel);
  document.getElementById('kpi-ticket-median').innerHTML =
    d.median != null ? `median ${fmt(d.median)}` : '';

  const ecoTop = d.economics;

  // ── Économie ──────────────────────────────────────────────────────────────
  // Labels dynamiques selon la période
  // Suffixe = jours réellement OUVERTS (les coûts sont calculés dessus), pas les
  // jours calendaires — sinon "Since opening · 55 days" alors qu'on a ouvert 42j.
  const openN = (d.economics && d.economics.open_days) || null;
  const periodSuffix = d.is_single_day ? '(jour)'
    : (openN ? `· ${openN} services` : `· ${d.n_days} jours`)
      + (d.economics && d.economics.excludes_today ? ' · hors journée en cours' : '');
  document.getElementById('eco-prime-label').textContent   = `Prime cost ${periodSuffix}`;
  document.getElementById('eco-seuil-label').textContent   = `Point mort ${periodSuffix}`;
  document.getElementById('eco-marge-label').textContent   = 'Marge brute';

  const eco = d.economics;
  // Bloc économie isolé dans une fonction immédiate : le cas « aucun jour ouvré »
  // sort par un `return`, qui ne doit interrompre QUE cette zone — pas le rendu des
  // produits et des transactions qui suit.
  if (eco) (() => {
    // Marge brute — 100% COGS réel, avec taux de couverture
    document.getElementById('eco-marge').textContent = eco.marge_brute_ht != null ? fmt(eco.marge_brute_ht) : '—';
    if (eco.marge_brute_ht != null) {
      // ⚠️ LE SEUIL EST CELUI DU MOTEUR, PAS UN SECOND SEUIL ÉCRIT ICI.
      //
      // Le JS re-décidait son propre palier (vert ≥ 90, ambre ≥ 60). Le moteur, lui, marque
      // la marge comme extrapolée en dessous de 95 (vendus.py:769). Entre les deux, à 92 % de
      // couverture, l'écran affichait du VERT sur un chiffre que le moteur tenait pour estimé.
      // `marge_is_estimated` était calculé, renvoyé, et lu par personne.
      const cov = eco.cogs_coverage_pct;
      const est = eco.marge_is_estimated === true;
      const covColor = est ? (cov != null && cov >= 60 ? '#b07d00' : 'var(--red)') : 'var(--green)';
      // Sous le seuil, la marge n'est plus mesurée : elle est mesurée sur une PARTIE des ventes
      // puis appliquée au reste. Le dire, plutôt que d'afficher un pourcentage de couverture que
      // le lecteur doit interpréter lui-même.
      const covStr = cov == null ? ''
        : est ? `<span style="color:${covColor}">mesurée sur ${cov} % des ventes, appliquée au reste</span>`
              : `<span style="color:${covColor}">couverture des coûts ${cov} %</span>`;
      document.getElementById('eco-marge-pct').innerHTML =
        `${eco.marge_brute_ht_pct}%${est ? ' <span style="color:#b07d00">est.</span>' : ''}` +
        ` <span style="color:var(--faint)">· marchandise ${fmt(eco.cogs_ht)} · </span>${covStr}`;
      /* ⚠️ L'ÉTAT DE LA MARGE, C'EST SA COUVERTURE — pas sa valeur. Une marge de 75 % mesurée
         sur 96 % des ventes et la même mesurée sur 55 % ne sont pas la même information, et
         c'est la seconde qui appelle un geste. La bande le dit sans une ligne de texte de
         plus. */
      etat(document.getElementById('eco-marge'), !est ? 'ok'
           : (cov != null && cov >= 60) ? 'attention' : 'alerte');
    } else {
      /* ⚠️ UNE CASE VIDE DIT CE QUI LA REMPLIRA, avec le lien pour y aller. « No COGS set »
         laisse devant un écran mort. */
      etat(document.getElementById('eco-marge'), null);
      document.getElementById('eco-marge-pct').innerHTML =
        '<span style="color:var(--muted)">Aucun prix d\'achat renseigné. ' +
        '<a href="/cogs" style="color:var(--accent)">Ouvrir COGS &amp; recettes →</a></span>';
    }

    // Charges — utilise les totaux période et open_days (pas n_days calendaires)
    // ⚠️ `?? cout_total_jour` REFERAIT LE BUG. Le serveur renvoie désormais `null` quand la
    // période ne contient aucun jour ouvré — un mardi-mercredi, café fermé. Le repli sur le
    // coût JOURNALIER y réafficherait les ~197 € que la correction serveur venait justement
    // de retirer. Sans jour ouvré, il n'y a rien à imputer : on le dit.
    /* ⚠️ LA CARTE « CHARGES » A ÉTÉ RETIRÉE : la répartition montre déjà le personnel et les
     * charges fixes, chacun avec sa part. Un total à côté de ses deux composantes fait chercher
     * ce qu'il ajoute — et il n'ajoute rien.
     */
    // Prime cost — COGS + labour, sur la période (déplacé des cartes Insights)
    const primePerso = eco.cout_perso_periode ?? eco.cout_perso_jour;
    const primeEl = document.getElementById('eco-prime');
    const primeSub = document.getElementById('eco-prime-sub');
    const primeBar = document.getElementById('eco-prime-bar');
    // ⚠️ LE TITRE ET SON SOUS-TEXTE PARLAIENT DE DEUX COGS DIFFÉRENTS.
    //
    // Le chiffre utilisait `cogs_ht`, mesuré sur la seule part des ventes dont le coût est
    // connu ; le sous-texte affichait `100 − marge_brute_ht_pct`, le taux extrapolé à tout le
    // CA. À 60 % de couverture, le titre annonçait 48 % en vert pendant que sa propre ligne du
    // dessous additionnait 30 + 30 = 60 %, au-delà de la cible. Le prime cost était sous-estimé
    // exactement du déficit de couverture, et jamais marqué comme estimé.
    //
    // On prend maintenant la matière extrapolée des deux côtés — la même que la cascade Flux :
    // ca_ht − marge_brute_ht. Les deux lignes disent enfin le même nombre.
    const primeMatiere = (eco.marge_brute_ht != null) ? (eco.ca_ht - eco.marge_brute_ht) : null;
    if (eco.ca_ht > 0 && primeMatiere != null && primePerso != null) {
      const prime   = (primeMatiere + primePerso) / eco.ca_ht * 100;
      const cogsPct = primeMatiere / eco.ca_ht * 100;
      const labPct  = primePerso / eco.ca_ht * 100;
      const est     = eco.marge_is_estimated === true;
      primeEl.textContent = prime.toFixed(1) + '%';
      /* ⚠️ LE CHIFFRE RESTE EN ENCRE ; C'EST LA BANDE QUI PORTE L'ÉTAT. Un nombre coloré est
         plus difficile à lire qu'un nombre noir, et sur douze indicateurs colorés plus rien ne
         ressort. */
      primeEl.style.color = '';
      etat(primeEl, prime <= 65 ? 'ok' : prime <= 75 ? 'attention' : 'alerte');
      primeSub.innerHTML = `Marchandise ${cogsPct.toFixed(0)}% · Personnel ${labPct.toFixed(0)}%`
        + (est ? ` <span style="color:var(--amber)">· matière extrapolée sur ${eco.cogs_coverage_pct}% des ventes</span>` : '')
        + ` <span style="color:var(--faint)">· cible &lt;65 %</span>`;
      primeBar.innerHTML =
        `<div style="width:${Math.min(100,cogsPct)}%;background:var(--flux-leave);"></div>` +
        `<div style="width:${Math.min(100,labPct)}%;background:var(--flux-tax);"></div>`;
      /* ⚠️ LE REPÈRE DE CIBLE, À 65 %. Une barre sans repère dit « c'est trop » ; avec le
         repère, elle dit « de deux points ». La barre est graduée sur 100 % du CA : la cible
         s'y place donc à 65 % de sa largeur. */
      marquerSeuil(primeBar, 65, 'cible 65 %');
    } else {
      /* ⚠️ UN TIRET, PAS UN ZÉRO — et une phrase qui dit ce qui le remplira. « Not
         measurable » laisse devant un écran mort sans indiquer le geste. */
      primeEl.textContent = '—'; primeEl.style.color = '';
      etat(primeEl, null);
      primeSub.innerHTML = '<span style="color:var(--muted)">Il manque les prix d\'achat. ' +
        '<a href="/cogs" style="color:var(--accent)">Ouvrir COGS &amp; recettes →</a></span>';
      primeBar.innerHTML = '';
    }

    // Seuil CA — TTC en principal, calculé sur la marge réelle mesurée
    const seuilSub = document.getElementById('eco-seuil-sub');
    if (eco.seuil_ca_ttc != null) {
      document.getElementById('eco-seuil').textContent = fmt(eco.seuil_ca_ttc);
      // Le seuil vaut charges ÷ marge réelle (vendus.py:745) : il repose sur le MÊME taux que
      // la marge brute. Sous le seuil de couverture, l'appeler « real margin » le fait passer
      // pour mesuré alors qu'il est extrapolé — et le seuil se déplace avec lui.
      const seuilEst = eco.marge_is_estimated === true;
      const margeNote = eco.seuil_margin_pct == null ? ''
        : seuilEst
          ? ` <span style="color:#b07d00">· sur une marge extrapolée de ${eco.seuil_margin_pct} %</span>`
          : ` <span style="color:var(--faint)">· marge réelle ${eco.seuil_margin_pct} %</span>`;
      if (eco.manque_seuil > 0) {
        seuilSub.innerHTML = `<span style="color:var(--red)">${fmt(eco.manque_seuil)} manquants (TTC)</span>` + margeNote;
      } else {
        seuilSub.innerHTML = `<span style="color:var(--green)">Point mort atteint${seuilEst ? '' : ' ✓'}</span>` + margeNote;
      }
      document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
    } else {
      document.getElementById('eco-seuil').textContent = '—';
      etat(document.getElementById('eco-seuil'), null);
      seuilSub.innerHTML = '<span style="color:var(--muted)">Le point mort se calcule ' +
        'charges ÷ marge réelle. <a href="/cogs" style="color:var(--accent)">Ouvrir COGS →</a></span>';
      document.getElementById('eco-seuil-bar').style.width = '0%';
    }

    // Point mort moyen par jour ouvré + évolution vs période de comparaison.
    // Couleurs INVERSÉES : un point mort qui BAISSE est une bonne nouvelle (vert).
    const avgEl = document.getElementById('eco-seuil-avg');
    const perDay = eco.seuil_ca_ttc_jour, prevDay = eco.seuil_jour_prev;
    if (perDay != null) {
      let evo = '';
      if (prevDay != null && prevDay > 0) {
        const pct = Math.round((perDay - prevDay) / prevDay * 100);
        if (pct !== 0) {
          const down = pct < 0;                       // point mort en baisse = mieux
          const col = down ? 'var(--green)' : 'var(--red)';
          evo = ` <span style="color:${col};font-weight:500">${down ? '▼ ' : '▲ +'}${pct}%</span>`
              + `<span style="color:var(--faint);font-size:11px;"> ${compLabel || 'vs prev.'}</span>`;
        } else {
          evo = ` <span style="color:var(--muted)">= stable</span>`;
        }
      }
      avgEl.innerHTML = `<span style="color:var(--muted)">moy. ${fmt(perDay)}/jour ouvert</span>${evo}`;
    } else {
      avgEl.innerHTML = '';
    }
  })();

  // ── Insights visuels ──────────────────────────────────────────────────────
  try { renderInsights(d); } catch(e) { console.error('insights', e); }

  // ── Sparkline 7 derniers jours (toujours) ────────────────────────────────
  const peakIdx = d.week.reduce((mi, v, i, a) => v.ca > a[mi].ca ? i : mi, 0);
  const wCtx = document.getElementById('chart-week').getContext('2d');
  if (chartWeek) chartWeek.destroy();
  chartWeek = new Chart(wCtx, {
    type: 'bar',
    data: {
      labels: d.week.map(w => w.label),
      datasets: [{
        data: d.week.map(w => w.ca),
        backgroundColor: d.week.map((_, i) => i === peakIdx && d.week[peakIdx].ca > 0 ? BAR_ACTIVE : BAR_IDLE),
        borderRadius: 3,
        borderSkipped: false,
      }]
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => fmt(ctx.raw) + ' · ' + d.week[ctx.dataIndex].nb + ' tickets' } }
      },
      scales: {
        y: { display: false, beginAtZero: true },
        x: { ticks: { font: { size: 11 }, color: 'rgba(120,119,111,1)' }, grid: { display: false }, border: { display: false } }
      }
    }
  });
  document.getElementById('week-labels').innerHTML = d.week.map((w, i) =>
    `<span style="${i === peakIdx && w.ca > 0 ? 'color:var(--text);font-weight:600' : ''}">${fmt(w.ca)}</span>`
  ).join('');

  /* ⚠️ LE GRAPHIQUE PRINCIPAL EST DESSINÉ PAR `renderCourbe`, appelée depuis `renderOverview`.
   * L'ancien aiguillage — barres horaires sur un jour, courbe sur plusieurs — a disparu avec le
   * bloc « Par heure » : une seule forme désormais, le cumul ou la série selon la période, et la
   * comparaison en pointillés par-dessus.
   */

  /* ⚠️ LA RÉPARTITION DES PAIEMENTS EST PARTIE VERS `/reconciliation`. Celle d'ici venait de
   * ce que Vendus DÉCLARE ; celle de là-bas est MESURÉE sur le terminal Revolut, ligne à
   * ligne, avec l'écart entre les deux. Garder les deux, c'était offrir le choix entre une
   * mesure et une déclaration — et celui qui choisit mal ne le saura jamais.
   */

  /* ⚠️ LES PICS D'ACTIVITÉ RÉSUMAIENT LE GRAPHIQUE SITUÉ JUSTE EN DESSOUS. Trois pastilles
   * au-dessus d'une courbe qui dit la même chose, en mieux : on lisait deux fois, puis on
   * cessait de lire les deux.
   */

  // ── Produits (toggle période / 7j) ───────────────────────────────────────
  const topSection = document.getElementById('top-products-section');
  if (topSection) {
    topSection.style.display = '';
    const periodLbl = d.is_single_day ? (d.is_today ? 'aujourd’hui' : 'ce jour') : (d.period_label?.toLowerCase() || 'la période');
    document.getElementById('products-section-label').textContent = `Ce qui s'est vendu — ${periodLbl}`;
  }
  if (!d.has_items) {
    document.getElementById('products-body').innerHTML =
      '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">Le d&eacute;tail par article n&rsquo;existe pas sur cette p&eacute;riode.</td></tr>';
  } else if (d.products) {
    const maxQty = d.products.length ? d.products[0].qty : 1;
    const cntEl = document.getElementById('products-count');
    if (cntEl) cntEl.textContent = d.products.length ? `· ${d.products.length}` : '';
    if (!d.products.length) {
      document.getElementById('products-body').innerHTML =
        '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">Aucun produit vendu.</td></tr>';
    } else {
      window._prodData = d.products;
      document.getElementById('products-body').innerHTML = d.products.map((p, i) => {
        const barW = Math.round(p.qty / maxQty * 100);
        const rank = i === 0 ? ' style="font-weight:600"' : '';
        const marginHtml = p.margin_pct != null ? marginBadge(p.margin_pct) : '<span style="color:var(--muted)">—</span>';
        const popupBadge = p.popup
          ? ` <span style="font-size:10px;font-weight:600;color:#7c4dbe;background:rgba(124,77,190,.12);border-radius:9px;padding:1px 7px;vertical-align:1px;">popup ${p.commission_pct}%</span>`
          : '';
        return `<tr style="cursor:pointer;" onclick="openProductPopup(${i})">
          <td${rank}>${p.name}${popupBadge}</td>
          <td class="amount">${p.qty}</td>
          <td class="amount" style="color:var(--muted)">${fmt(p.avg)}</td>
          <td class="amount">${fmt(p.revenue)}</td>
          <td class="amount">${marginHtml}</td>
          <td style="padding-right:16px;vertical-align:middle;">
            <div style="height:3px;background:var(--bar-bg);border-radius:2px;">
              <div style="height:3px;background:var(--bar);border-radius:2px;width:${barW}%"></div>
            </div>
          </td>
        </tr>`;
      }).join('');
    }
  }

  // ── Transactions récentes ────────────────────────────────────────────────
  if (!d.recent || !d.recent.length) {
    document.getElementById('recent-body').innerHTML =
      '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:24px;">Aucune commande.</td></tr>';
    return;
  }
  window._txData = d.recent;
  const recCount = document.getElementById('recent-count');
  if (recCount) recCount.textContent = d.is_single_day
    ? `${d.recent.length} commande${d.recent.length > 1 ? 's' : ''}`
    : `${d.recent.length} dernières`;
  const recLabel = document.getElementById('recent-label');
  if (recLabel) recLabel.textContent = d.is_single_day ? 'Commandes du jour' : 'Commandes';
  document.getElementById('recent-body').innerHTML = d.recent.map((t, i) => `
    <tr style="cursor:pointer;" onclick="openDrawer(${i})"
        onmouseenter="showTxTooltip(event, ${i})" onmousemove="moveTxTooltip(event)" onmouseleave="hideTxTooltip()">
      <td class="time">${t.time}</td>
      <td class="num">${t.number}</td>
      <td><span class="badge">${t.type}</span></td>
      <td class="amount">${fmt(t.amount)}</td>
    </tr>`).join('');
}

// ── Tooltip survol transaction ───────────────────────────────────────────────

// ── Insights visuels ───────────────────────────────────────────────────────
const WD_SHORT = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

/**
 * CE QUE LA PÉRIODE CONTIENT — en services, pas en jours de calendrier.
 *
 * ⚠️ « LA SEMAINE DERNIÈRE » EST AMBIGUË. Sept jours calendaires, ou cinq de service ? Les deux
 * réponses existent et donnent des chiffres différents ; tant que l'écran ne dit pas laquelle
 * il applique, on lit un total sans savoir sur quoi il porte.
 *
 * ⚠️ ET LA COMPARAISON PEUT ÊTRE BANCALE SANS QUE RIEN NE LE DISE. « Semaine en cours » un
 * jeudi contient DEUX services ; « semaine dernière » en contient cinq. Passer de l'une à
 * l'autre fait lire un effondrement de 60 % qui n'est qu'un décalage de calendrier — on le
 * signale là où le choix vient d'être fait.
 */
function renderPeriode(d) {
  const zone = document.getElementById('periode-dit');
  /* ⚠️ ON DÉCRIT LA FENÊTRE DU CALCUL, PAS CELLE QU'ON A DEMANDÉE. Quand la journée en cours
   * est retirée de l'économie — une recette partielle face à des charges entières bascule
   * l'EBITDA dans le rouge sans raison — le résultat porte sur une fenêtre plus courte. Un
   * jeudi, « Semaine en cours » annonçait 2 services et calculait sur 1 : le chiffre était
   * juste, sa légende doublait sa base. */
  const eco = d && d.economics;
  const p = (eco && eco.periode) || (d && d.periode);
  if (!p) { zone.innerHTML = ''; return; }
  const bouts = [];
  const n = p.jours_ouverts;
  bouts.push(`<b>${n}</b> service${n > 1 ? 's' : ''} sur ${p.jours_calendaires} jour`
             + (p.jours_calendaires > 1 ? 's' : ''));
  if (eco && eco.excludes_today) {
    bouts.push('<span class="att">journée en cours exclue du calcul</span>');
  } else if (p.en_cours) {
    bouts.push('<span class="att">période en cours, pas terminée</span>');
  }
  if (d.comp_label) bouts.push(d.comp_label);
  else bouts.push('<span class="att">pas de période comparable</span>');
  zone.innerHTML = bouts.join(' · ');
}

function renderInsights(d) {
  renderReponse(d);
  renderPeriode(d);
  renderCourbe(d);
  renderMinis(d);
  renderQuatre(d);
  const ins = d.insights;
  const monthZone    = document.getElementById('month-zone');
  const patternsZone = document.getElementById('patterns-zone');
  if (!ins) {
    monthZone.style.display = 'none'; patternsZone.style.display = 'none';
    return;
  }

  /* ⚠️ LE BANDEAU NOIR « VERDICT DU JOUR » EST PARTI. Il répondait à la même question que le
   * bandeau-réponse du haut — « est-ce qu'on couvre nos coûts ? » — mais UNIQUEMENT sur la
   * période « aujourd'hui ». Les six autres n'avaient pas de réponse du tout, et « ce mois-ci »
   * est précisément celle qu'on regarde pour décider quelque chose.
   *
   * ⚠️ ET DEUX RÉPONSES À LA MÊME QUESTION, C'EST UNE DE TROP. Le jour où elles divergeraient —
   * un arrondi, une période incluse d'un côté et pas de l'autre — on ne saurait pas laquelle
   * croire, et on cesserait de croire les deux.
   */

  // Zone 2 "This month" : masquée quand la période EST le mois en cours (doublon).
  const showMonthZone = currentPreset !== 'month' && ins.month && ins.month.days && ins.month.days.length;
  monthZone.style.display = showMonthZone ? '' : 'none';
  if (showMonthZone) {
    document.getElementById('month-zone-label').textContent =
      new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  }

  // Zone 3 "Patterns" : toujours affichée (fenêtres fixes), sous-blocs gérés plus bas.
  patternsZone.style.display = '';
  // Sparkline 7j masquée quand la période = week/lastweek (doublon du graphe principal).
  document.getElementById('last7-block').style.display =
    (currentPreset === 'week' || currentPreset === 'lastweek') ? 'none' : '';

  // 2. Heatmap heure × jour (28 derniers jours)
  const hm = ins.heatmap;
  if (hm && hm.cells && hm.cells.length) {
    const byKey = {};
    for (const c of hm.cells) byKey[c.d + '_' + c.h] = c.v;
    const daysWithData = [...new Set(hm.cells.map(c => c.d))].sort();
    let html = `<div class="hm-grid" style="grid-template-columns:34px repeat(${hm.hours.length},1fr);">`;
    html += `<div></div>` + hm.hours.map(h => `<div class="hm-lbl">${h}</div>`).join('');
    for (const wd of daysWithData) {
      html += `<div class="hm-lbl">${WD_SHORT[wd]}</div>`;
      for (const h of hm.hours) {
        const v = byKey[wd + '_' + h] || 0;
        const a = hm.max ? (v / hm.max) : 0;
        html += `<div class="hm-cell" style="${v ? `background:rgba(37,84,199,${(0.10 + a * 0.75).toFixed(2)});` : ''}" data-tip="${WD_SHORT[wd]} ${h}h · ${fmt(v)}"></div>`;
      }
    }
    html += `</div>`;
    const rush = ins.rush;
    const rushLine = rush
      ? `<strong>${rush.top_share}%</strong> de l'encaissé sur les 3 heures les plus chargées (${rush.hours.map(h => h + 'h').join(', ')})`
      : 'plus foncé = plus encaissé · heures 8–16';
    document.getElementById('ins-heatmap').innerHTML = `
      <div class="ins-label">Carte des pics — encaissé par heure (28 jours)</div>
      ${html}
      <div class="ins-sub">${rushLine}</div>`;
  } else {
    document.getElementById('ins-heatmap').innerHTML = `<div class="ins-label">Rush heatmap</div><div class="ins-sub">Pas encore assez de données.</div>`;
  }

  // 3+4. Mois : cumul EBITDA + projection / calendrier break-even
  const m = ins.month;
  if (m && m.days && m.days.length) {
    const opens = m.days.filter(x => x.open);
    const pts   = opens.map(x => x.cum);
    // ⚠️ `proj_end` peut valoir null : aucun jour PLEIN dans le mois, donc rien pour asseoir
    // une moyenne. fmt(null) rendrait « €0.00 projected d'ici la fin du mois » — une prévision
    // fabriquée, exactement ce que le serveur refuse désormais d'affirmer.
    const hasProj = m.proj_end != null;
    const allVals = pts.concat(hasProj ? [m.proj_end, 0] : [0]);
    const lo = Math.min(...allVals), hi = Math.max(...allVals);
    const W = 600, H = 100, span = (hi - lo) || 1;
    const y = v => 8 + (H - 16) * (1 - (v - lo) / span);
    const n = opens.length;
    const x = i => n > 1 ? (i / (n - 1)) * (W * 0.72) : 0;
    const path = pts.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const projPath = hasProj
      ? `M${x(n - 1).toFixed(1)},${y(pts[n - 1]).toFixed(1)} L${W - 4},${y(m.proj_end).toFixed(1)}`
      : '';
    document.getElementById('ins-month').innerHTML = `
      <div class="ins-label">Month EBITDA — cumulative + projection</div>
      <svg class="ins-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <line x1="0" y1="${y(0).toFixed(1)}" x2="${W}" y2="${y(0).toFixed(1)}" stroke="var(--border)" stroke-width="1.5"/>
        <path d="${path}" fill="none" stroke="var(--flux-keep)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
        ${hasProj ? `<path d="${projPath}" fill="none" stroke="var(--flux-leave)" stroke-width="2.5" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>` : ''}
      </svg>
      <div class="ins-sub">
        MTD <strong style="color:${m.cum_now >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.cum_now)}</strong>
        · ${hasProj
            ? `projected <strong style="color:${m.proj_end >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.proj_end)}</strong> d'ici la fin du mois`
            : `<span style="color:var(--muted)">pas encore de jour plein ce mois-ci — aucune projection</span>`}
        ${m.cross_date ? ` · crossed €0 on ${new Date(m.cross_date + 'T12:00:00').toLocaleDateString('fr-FR', {day:'numeric', month:'short'})}` : ''}
      </div>
      ${m.proj_ca_end != null ? `
      <div class="ins-sub" style="margin-top:4px;">
        Revenue: MTD <strong>${fmt(m.ca_mtd)}</strong>
        · projected <strong>${fmt(m.proj_ca_end)}</strong> d'ici la fin du mois
        ${m.seuil_ca_month != null ? ` vs <strong>${fmt(m.seuil_ca_month)}</strong> needed to break even
          → <strong style="color:${m.proj_ca_end >= m.seuil_ca_month ? 'var(--green)' : 'var(--red)'}">${(m.proj_ca_end >= m.seuil_ca_month ? '+' : '') + fmt(m.proj_ca_end - m.seuil_ca_month)}</strong>` : ''}
      </div>` : ''}`;

    const first = new Date(m.days[0].date + 'T12:00:00');
    const lead  = (first.getDay() + 6) % 7;
    let cal = WD_SHORT.map(w => `<div class="hm-lbl">${w[0]}</div>`).join('');
    for (let i = 0; i < lead; i++) cal += `<div></div>`;
    for (const day of m.days) {
      const dt = new Date(day.date + 'T12:00:00');
      let bg = 'var(--bg-page)', color = 'var(--faint)';
      if (day.open && day.ebitda != null) {
        bg = day.ebitda >= 0 ? 'rgba(80,161,116,.28)' : 'rgba(196,85,77,.24)';
        color = 'var(--text)';
      }
      cal += `<div class="cal-cell" style="background:${bg};color:${color};" data-tip="${new Date(day.date+'T12:00:00').toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'})}${day.ebitda != null ? ' · EBITDA ' + fmt(day.ebitda) : ' · fermé'}">${dt.getDate()}</div>`;
    }
    const greens = opens.filter(x => x.ebitda >= 0).length;
    document.getElementById('ins-calendar').innerHTML = `
      <div class="ins-label">Calendrier du point mort</div>
      <div class="cal-grid">${cal}</div>
      <div class="ins-sub">vert = au-dessus du point mort · ${greens}/${opens.length} services</div>`;
  } else {
    document.getElementById('ins-month').innerHTML = `<div class="ins-label">Month EBITDA</div><div class="ins-sub">Pas encore assez de données.</div>`;
    document.getElementById('ins-calendar').innerHTML = `<div class="ins-label">Calendrier du point mort</div><div class="ins-sub">Pas encore assez de données.</div>`;
  }

  /* ⚠️ « ARTICLES PAR TICKET » ET « ENCAISSÉ PAR PLACE » SONT PARTIS avec les cartes qui les
   * portaient. Les deux étaient justes et se lisaient une fois : l'un mesure la vente
   * additionnelle, l'autre le rendement de la salle. Aucun n'a jamais changé une décision — et
   * ils occupaient la ligne située juste sous le résultat.
   */
}

// ── Tooltip instantanée partagée ([data-tip]) ───────────────────────────────
// Remplace les title natifs : affichage immédiat au survol, suit la souris,
// délégation → fonctionne sur tout contenu re-rendu sans réattacher.
(function () {
  const tip = document.createElement('div');
  tip.id = 'hover-tip';
  document.body.appendChild(tip);

  function place(e) {
    const pad = 12;
    let x = e.clientX + pad, y = e.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width  > window.innerWidth  - 8) x = e.clientX - r.width  - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    tip.style.left = x + 'px';
    tip.style.top  = y + 'px';
  }

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('[data-tip]');
    if (!el) return;
    tip.textContent = el.dataset.tip;
    tip.style.display = 'block';
    place(e);
  });
  document.addEventListener('mousemove', e => {
    if (tip.style.display === 'block' && e.target.closest('[data-tip]')) place(e);
  });
  document.addEventListener('mouseout', e => {
    if (e.target.closest('[data-tip]') && !(e.relatedTarget && e.relatedTarget.closest('[data-tip]'))) {
      tip.style.display = 'none';
    }
  });
})();

// ── Init ───────────────────────────────────────────────────────────────────
loadData();
setInterval(() => { if (currentPreset === 'today') loadData(); }, 5 * 60 * 1000);


// ── Produits popup (chef partenaire) ─────────────────────────────────────────
// La commission sur le TTC est la marge brute : côté serveur, le coût du
// produit devient net × (1 − commission), donc la marge % affichée = le taux.
let _popupProd = null;

function openProductPopup(i) {
  const p = (window._prodData || [])[i];
  if (!p) return;
  _popupProd = p;
  document.getElementById('popup-prod-name').textContent = p.name;
  document.getElementById('popup-prod-meta').textContent =
    `${p.qty} vendus · ${fmt(p.revenue)}` + (p.margin_pct != null ? ` · marge ${p.margin_pct} %` : '');
  const check = document.getElementById('popup-check');
  check.checked = !!p.popup;
  const sel = document.getElementById('popup-pct-select');
  const custom = document.getElementById('popup-pct-custom');
  const pct = p.commission_pct;
  if (pct != null && ['10','15','20'].includes(String(pct))) {
    sel.value = String(pct); custom.style.display = 'none';
  } else if (pct != null) {
    sel.value = 'custom'; custom.style.display = ''; custom.value = pct;
  } else {
    sel.value = '20'; custom.style.display = 'none'; custom.value = '';
  }
  document.getElementById('popup-error').style.display = 'none';
  popupCheckChanged();
  document.getElementById('popup-overlay').style.display = '';
  document.getElementById('popup-modal').style.display = '';
}
function closeProductPopup() {
  document.getElementById('popup-overlay').style.display = 'none';
  document.getElementById('popup-modal').style.display = 'none';
  _popupProd = null;
}
function popupCheckChanged() {
  document.getElementById('popup-pct-row').style.display =
    document.getElementById('popup-check').checked ? '' : 'none';
}
function popupPctChanged() {
  const isCustom = document.getElementById('popup-pct-select').value === 'custom';
  const custom = document.getElementById('popup-pct-custom');
  custom.style.display = isCustom ? '' : 'none';
  if (isCustom) custom.focus();
}
async function saveProductPopup() {
  if (!_popupProd) return;
  const popup = document.getElementById('popup-check').checked;
  let pct = document.getElementById('popup-pct-select').value;
  if (pct === 'custom') pct = document.getElementById('popup-pct-custom').value;
  const errEl = document.getElementById('popup-error');
  if (popup && !(parseFloat(pct) >= 0 && parseFloat(pct) < 100)) {
    errEl.textContent = 'Commission invalide — entre 0 et 100 %.';
    errEl.style.display = ''; return;
  }
  const btn = document.getElementById('popup-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const r = await fetch('/api/popup-flag', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: _popupProd.name, popup, commission_pct: parseFloat(pct)})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.status);
    closeProductPopup();
    loadData(true);   // recharge : badge, marge, COGS et EBITDA reflètent le flag
  } catch (e) {
    errEl.textContent = 'Erreur : ' + e.message;
    errEl.style.display = '';
  } finally {
    btn.disabled = false; btn.textContent = 'Enregistrer';
  }
}

/* ── La commande qu'on vient de cliquer ───────────────────────────────────────
 * ⚠️ REVENU AVEC LA LISTE. Ces fonctions avaient été retirées parce que plus rien ne les
 * appelait — c'était juste à ce moment-là, et faux dès que la liste est revenue. Le contrôle
 * « aucune fonction orpheline » les aurait signalées dans les deux sens.
 */
function showTxTooltip(e, idx) {
  const t = window._txData[idx];
  if (!t) return;
  const tip = document.getElementById('tx-tooltip');
  const itemsHtml = (t.items && t.items.length)
    ? t.items.map(it => `
        <div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0;">
          <span>${it.qty > 1 ? `<span style="color:var(--muted)">${it.qty}×</span> ` : ''}${it.name}</span>
          <span style="color:var(--muted);white-space:nowrap;">${fmt(it.total)}</span>
        </div>`).join('')
    : '<div style="color:var(--muted);">Detail unavailable</div>';
  const payHtml = (t.payments && t.payments.length)
    ? `<div style="border-top:1px solid var(--border);margin-top:6px;padding-top:6px;color:var(--muted);">${t.payments.map(p => p.label).join(' · ')}</div>`
    : '';
  tip.innerHTML = `
    <div style="font-weight:600;margin-bottom:6px;">${t.number} · ${t.time}</div>
    ${itemsHtml}
    <div style="display:flex;justify-content:space-between;border-top:1px solid var(--border);margin-top:6px;padding-top:6px;font-weight:600;">
      <span>Total</span><span>${fmt(t.amount)}</span>
    </div>${payHtml}`;
  tip.style.display = 'block';
  moveTxTooltip(e);
}

function moveTxTooltip(e) {
  const tip = document.getElementById('tx-tooltip');
  if (tip.style.display === 'none') return;
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > window.innerWidth)  x = e.clientX - w - pad;
  if (y + h > window.innerHeight) y = e.clientY - h - pad;
  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}

function hideTxTooltip() {
  document.getElementById('tx-tooltip').style.display = 'none';
}

function openDrawer(idx) {
  const t = window._txData[idx];
  document.getElementById('drawer-number').textContent = t.number;
  document.getElementById('drawer-meta').textContent   = t.time + ' · ' + t.client;
  document.getElementById('drawer-items').innerHTML = t.items.length
    ? t.items.map(item => `
        <tr>
          <td class="dt-name">${item.name}</td>
          <td class="dt-qty">${item.qty > 1 ? item.qty + ' ×' : ''} ${fmt(item.unit)}</td>
          <td class="dt-amt">${fmt(item.total)}</td>
        </tr>`).join('')
    : '<tr><td colspan="3" style="color:var(--muted);font-size:12px;padding:8px 0;">Detail unavailable</td></tr>';
  document.getElementById('drawer-payments').innerHTML = t.payments.map(p => `
    <div class="drawer-pay-row">
      <span>${p.label}</span>
      <span>${fmt(p.amount)}</span>
    </div>`).join('');
  document.getElementById('drawer-total').innerHTML = `<span>Total</span><span>${fmt(t.amount)}</span>`;
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
