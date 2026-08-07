// La page /transactions — « l'affluence tient-elle ? ». Sans dépendance : node tests/test_tx_page.js
//
// ⚠️ LES FONCTIONS SONT LUES DANS static/transactions.js, PAS RECOPIÉES. Une copie
// divergerait du code livré sans que rien ne le signale — le faux vert le plus cher
// du dépôt. En contrepartie, ce fichier dépend des NOMS : renommer une fonction fait
// échouer le test bruyamment, au lieu de tester du vide.
//
// Ce qui est vérifié tient en une phrase : la page n'a pas le droit d'inventer un
// chiffre. Pas de zéro pour un jour fermé, pas de delta contre une fenêtre vide,
// pas de médiane sur trois jours vendue comme une journée typique, pas de sommet
// écrêté en silence.

const fs = require('fs');
const path = require('path');

const SRC_PATH = path.join(__dirname, '..', 'static', 'transactions.js');
const TPL_PATH = path.join(__dirname, '..', 'templates', 'transactions.html');
const src = fs.readFileSync(SRC_PATH, 'utf8');
const tpl = fs.readFileSync(TPL_PATH, 'utf8');

const NOMS = [
  'fmtTx', 'fmtEur', 'fmtPct', 'fmtDay', 'fmtRange', 'reasonLabel',
  'headlineModel', 'chartModel', 'windowRows', 'weekdayRows', 'multiLineModel',
];

function extraire(nom) {
  const m = src.match(new RegExp('\\nfunction ' + nom + '\\([\\s\\S]*?\\n\\}'));
  if (!m) {
    console.error(`✗ ${nom} introuvable dans static/transactions.js — renommée ou supprimée ?`);
    process.exit(1);
  }
  return m[0];
}

const M = new Function(
  NOMS.map(extraire).join('\n') + '\nreturn {' + NOMS.join(',') + '};'
)();

const { headlineModel, chartModel, windowRows, weekdayRows, multiLineModel, reasonLabel } = M;

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// Fenêtre type, calquée sur le contrat de /api/transactions/daily.
const W = (from, to, o) => Object.assign({
  from, to, full_days: 14, tx_median: 20.0, ca_median: 187.10,
  basket_median: 10.54, multi_pct: 31.2, reliable: true, reason: null,
}, o || {});

// ══ 1. LE BANDEAU-RÉPONSE ═══════════════════════════════════════════════════

const HL = {
  tx_median: 20.0, n: 8, from: '2026-07-20', to: '2026-08-02',
  prev_tx_median: 30.0, prev_n: 8, prev_from: '2026-07-06', prev_to: '2026-07-19',
  delta_pct: -33, reason: null,
};

{
  const m = headlineModel(HL);
  check('la réponse cite les deux fenêtres AVEC LEUR n',
    m.value === '20' && m.n === 8 && m.prevValue === '30' && m.prevN === 8,
    JSON.stringify([m.value, m.n, m.prevValue, m.prevN]));
  check('une baisse s’écrit avec le signe moins, pas en rouge — la direction est une donnée',
    m.deltaText === '−33 %' && m.deltaDir === 'down', m.deltaText);
  check('une hausse est marquée « up »',
    headlineModel({ ...HL, delta_pct: 12 }).deltaDir === 'up');
}

// ── delta_pct null : la RAISON prend la place du chiffre ─────────────────────
{
  // Le cas qui compte : sans comparaison possible, « 0 % » dirait « ça tient » et
  // « −100 % » dirait « effondrement ». Les deux seraient inventés.
  const m = headlineModel({ ...HL, delta_pct: null, reason: 'prev-unreliable' });
  check('delta_pct null ⇒ aucun pourcentage affiché',
    m.deltaText === null && m.deltaDir === 'none', String(m.deltaText));
  check('delta_pct null ⇒ la raison est écrite en clair',
    typeof m.note === 'string' && m.note.length > 0 && m.note === reasonLabel('prev-unreliable'), m.note);
  const rendu = JSON.stringify(m);
  check('nulle part un « 0 % » ni un « −100 % » fabriqué',
    !/0\s?%/.test(rendu) && !/-?−?100\s?%/.test(rendu), rendu);
  check('la fenêtre courante reste lisible malgré l’absence de delta',
    m.ok === true && m.value === '20' && m.n === 8);
}

{
  // Fenêtre précédente vide : pas de n ⇒ pas de comparaison, même si l'API envoyait
  // un delta par mégarde. On ne compare pas contre du vide.
  const m = headlineModel({ ...HL, prev_tx_median: null, prev_n: 0, delta_pct: -100 });
  check('pas de delta contre une fenêtre vide',
    m.hasPrev === false && m.deltaText === null, m.deltaText);
  check('l’absence de fenêtre précédente est nommée', !!m.note, m.note);
}

{
  const m = headlineModel({ ...HL, delta_pct: 0 });
  check('un 0 % RÉELLEMENT mesuré se dit « flat », pas « — »',
    m.deltaText === 'flat' && m.deltaDir === 'flat', m.deltaText);
}

{
  const m = headlineModel({ tx_median: null, n: 0, reason: 'too-few-days' });
  check('sans médiane, la valeur est « — » et la raison est donnée',
    m.ok === false && m.value === '—' && m.note === reasonLabel('too-few-days'), m.note);
}

// ══ 2. LE GRAPHIQUE ═════════════════════════════════════════════════════════

// 27 mai → 2 juin, MAIS le 31 mai (dimanche, fermé) est ABSENT du payload.
// Le 1er juin est un jour ouvert à 0 ticket : ça, c'est une mesure.
const DAYS = [
  { day: '2026-05-27', nb: 12, ca_ttc: 140.50, weekday: 2, partial: false },
  { day: '2026-05-28', nb: 18, ca_ttc: 190.00, weekday: 3, partial: false },
  { day: '2026-05-29', nb: 73, ca_ttc: 620.00, weekday: 4, partial: false },
  { day: '2026-05-30', nb: 24, ca_ttc: 260.00, weekday: 5, partial: false },
  // 2026-05-31 : FERMÉ — absent, ce n'est pas un zéro
  { day: '2026-06-01', nb:  0, ca_ttc:   0.00, weekday: 0, partial: false },
  { day: '2026-06-02', nb: 80, ca_ttc: 810.00, weekday: 1, partial: true  },
];

{
  const m = chartModel(DAYS, [W('2026-05-27', '2026-06-09', { tx_median: 21.0, full_days: 5 })]);
  check('un jour fermé n’a AUCUNE barre — il n’est pas dessiné à zéro',
    m.bars.every(b => b.day !== '2026-05-31') && m.n === 6, `${m.n} barres`);
  check('un jour OUVERT à 0 ticket garde sa barre — c’est une mesure, pas une absence',
    m.bars.some(b => b.day === '2026-06-01' && b.nb === 0));
  check('les jours dessinés sont exactement ceux du payload',
    m.bars.map(b => b.day).join(',') === DAYS.map(d => d.day).join(','));
}

{
  const m = chartModel(DAYS, []);
  check('le jour partiel est marqué',
    m.partialCount === 1 && m.bars[m.bars.length - 1].partial === true);
  check('un seul jour peut être partiel dans ce payload', m.bars.filter(b => b.partial).length === 1);
}

{
  // Les vraies pointes : 73 le 29 mai, 80 le 2 juin. Écrêter tasserait toute la série
  // pour faire joli, et rien à l'écran ne dirait que le sommet a été coupé.
  const m = chartModel(DAYS, []);
  check('le maximum affiché est le maximum réel', m.yMax === 80, String(m.yMax));
  check('aucune valeur n’est modifiée en chemin',
    m.bars.map(b => b.nb).join(',') === '12,18,73,24,0,80');
  check('l’absence de troncature est déclarée explicitement', m.clipped === false);
}

// ── L'escalier ───────────────────────────────────────────────────────────────
{
  const wins = [
    W('2026-05-27', '2026-06-09', { tx_median: 21.0 }),
    W('2026-06-10', '2026-06-23', { tx_median: 26.0 }),
  ];
  const m = chartModel(DAYS, wins);
  check('chaque jour reçoit la médiane de SA fenêtre — un palier, pas une pente',
    m.steps.every(s => s === 21.0), JSON.stringify(m.steps));

  // Fenêtre non fiable : pas de palier du tout. Un palier fragile se lirait comme
  // les autres, et rien ne le distinguerait.
  const fragile = chartModel(DAYS, [W('2026-05-27', '2026-06-09',
    { reliable: false, reason: 'too-few-days', tx_median: 21.0, full_days: 3 })]);
  check('une fenêtre non fiable ne produit AUCUN palier',
    fragile.steps.every(s => s === null), JSON.stringify(fragile.steps));
  check('un jour hors de toute fenêtre laisse un trou, pas un zéro',
    chartModel(DAYS, [W('2026-07-01', '2026-07-14')]).steps.every(s => s === null));
}

// ── Le source lui-même : ni lissage, ni plafond ──────────────────────────────
// Les commentaires sont retirés d'abord : ils PARLENT de ce qu'on s'interdit
// (« pas de suggestedMax », « aucune régression »), et un test qui les lirait
// échouerait sur sa propre documentation.
const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"])\/\/.*$/gm, '$1');
{
  check('la ligne des médianes est un escalier (stepped), pas une courbe',
    /stepped:\s*'(middle|before|after)'|stepped:\s*true/.test(code));
  check('aucune interpolation entre paliers (spanGaps désactivé)', /spanGaps:\s*false/.test(code));
  check('aucune tension de courbe — une spline lisserait le bruit en tendance',
    !/tension\s*:/.test(code));
  check('aucun plafond d’axe : pas de suggestedMax ni de max sur l’axe y',
    !/suggestedMax/.test(code) && !/\bmax:\s*\d/.test(code));
  check('aucune régression / projection / moyenne mobile dans le code',
    !/\b(linearRegression|movingAverage|rollingMean|forecast|trendline)\b/i.test(code));
}

// ══ 3. LA TABLE DES FENÊTRES ════════════════════════════════════════════════
{
  const rows = windowRows([
    W('2026-06-22', '2026-07-05'),
    W('2026-07-20', '2026-08-02', { full_days: 8, tx_median: 20.0 }),
    W('2026-07-06', '2026-07-19', { tx_median: 30.0 }),
  ]);
  check('les fenêtres sont classées de la plus récente à la plus ancienne',
    rows.map(r => r.to).join(',') === '2026-08-02,2026-07-19,2026-07-05');
  check('médianes et n sont rendus tels quels sur une fenêtre fiable',
    rows[0].tx === '20' && rows[0].ca === '187.10 €' && rows[0].basket === '10.54 €' && rows[0].n === 8,
    JSON.stringify(rows[0]));
}

{
  // Une « médiane » sur 3 jours pleins n'est pas une journée typique. Le n reste —
  // c'est l'information utile — les médianes deviennent « — » avec leur raison.
  const rows = windowRows([W('2026-08-03', '2026-08-16',
    { full_days: 3, reliable: false, reason: 'too-few-days' })]);
  check('une fenêtre non fiable ne publie aucune médiane',
    rows[0].tx === '—' && rows[0].ca === '—' && rows[0].basket === '—' && rows[0].multi === '—',
    JSON.stringify(rows[0]));
  check('elle garde son n — savoir qu’il n’y a que 3 jours est l’information',
    rows[0].n === 3 && rows[0].reliable === false);
  check('et elle porte sa raison', rows[0].note === reasonLabel('too-few-days'), rows[0].note);
}

{
  const rows = windowRows([W('2026-07-20', '2026-08-02', { basket_median: null })]);
  check('un chiffre manquant dans une fenêtre fiable est « — », jamais 0',
    rows[0].basket === '—' && rows[0].tx === '20');
  check('et il est accompagné d’une raison', !!rows[0].note, rows[0].note);
}

// ══ 4. JOURS DE SEMAINE ET MULTI-LIGNES ═════════════════════════════════════
{
  const rows = weekdayRows([
    { weekday: 0, label: 'Monday', tx_median: 22.0, n: 8 },
    { weekday: 5, label: 'Saturday', tx_median: 41.0, n: 9 },
    { weekday: 6, label: 'Sunday', tx_median: null, n: 0 },
  ]);
  check('les sept jours sont toujours listés, du lundi au dimanche',
    rows.length === 7 && rows[0].label === 'Monday' && rows[6].label === 'Sunday');
  check('un jour jamais ouvert est « — » avec sa raison, pas 0 tickets',
    rows[6].tx === '—' && rows[6].n === 0 && /never open/.test(rows[6].note || ''), rows[6].note);
  check('un jour absent du payload est « — » lui aussi',
    rows[1].tx === '—' && rows[1].n === 0);
  check('le n de chaque jour est remonté', rows[0].n === 8 && rows[5].n === 9);
}

{
  const m = multiLineModel([
    W('2026-07-06', '2026-07-19', { multi_pct: 28.4 }),
    W('2026-07-20', '2026-08-02', { multi_pct: 31.2, full_days: 8 }),
  ]);
  check('la part multi-lignes est lue sur la DERNIÈRE fenêtre fiable',
    m.ok === true && m.text === '31.2 %' && m.n === 8, JSON.stringify(m));

  const seulementFragile = multiLineModel([W('2026-08-03', '2026-08-16',
    { full_days: 2, reliable: false, reason: 'too-few-days', multi_pct: 50.0 })]);
  check('aucune fenêtre fiable ⇒ « — » avec la raison',
    seulementFragile.ok === false && seulementFragile.text === '—'
    && seulementFragile.note === reasonLabel('too-few-days'), seulementFragile.note);
}

// ══ 5. UN PAYLOAD VIDE NE CASSE RIEN ════════════════════════════════════════
{
  // Premier jour d'ouverture, API en panne, cache pas encore construit : la page
  // doit rester lisible et n'afficher que des « — ».
  let boom = null;
  let out = {};
  try {
    out = {
      hl: headlineModel(undefined),
      hl2: headlineModel({}),
      ch: chartModel(undefined, undefined),
      ch2: chartModel([], []),
      win: windowRows(undefined),
      wd: weekdayRows(undefined),
      ml: multiLineModel(undefined),
    };
  } catch (e) { boom = e; }
  check('aucune fonction ne lève sur un payload absent', boom === null, boom && boom.message);
  check('le bandeau vide affiche « — » et sa raison',
    out.hl && out.hl.value === '—' && !!out.hl.note);
  check('le graphique vide n’a aucune barre', out.ch && out.ch.n === 0 && out.ch.bars.length === 0);
  check('les tables vides sont vides, pas remplies de zéros',
    out.win.length === 0 && out.wd.length === 7 && out.wd.every(r => r.tx === '—'));
  check('la part multi-lignes vide est « — » avec une raison',
    out.ml.text === '—' && !!out.ml.note);
  check('un code de raison inconnu est affiché tel quel plutôt qu’avalé',
    reasonLabel('code-inedit-de-lapi') === 'code-inedit-de-lapi');
  check('aucune raison pour un code absent', reasonLabel(null) === null);
}

// ══ 6. LE TEMPLATE : L'ENCART EST FIXE, PAS DÉCORATIF ═══════════════════════
// Il ne dépend d'aucune donnée : il doit rester à l'écran même quand tout va bien.
// Le tester ici évite qu'il disparaisse dans un nettoyage de template.
{
  check('l’encart « What this page cannot tell you » est dans le template',
    /What this page cannot tell you/.test(tpl));
  check('Regulars : la preuve chiffrée de l’anonymat est citée',
    /fiscal_id/.test(tpl) && /59 of 60/.test(tpl) && /---------/.test(tpl));
  check('Hours : l’absence d’heure dans le cache journalier est dite',
    /Hours/.test(tpl) && /not (in the daily cache|stored)/i.test(tpl));
  check('Holiday effect : aucun août de référence avant 2027',
    /Holiday effect/.test(tpl) && /2027/.test(tpl));
  check('l’identité est NOMMÉE, pas expliquée causalement',
    /revenue = tickets × basket/.test(tpl) && /identity/i.test(tpl));
  check('le graphique annonce le jour partiel',
    /partial\b[^<]*excluded from medians/i.test(tpl) || /partial — excluded from medians/.test(src));

  // Identité Flux : rien n'est un solde sur cette page, donc aucun rouge.
  const styles = tpl.slice(tpl.indexOf('.tx-section {'), tpl.indexOf('</style>'));
  check('aucune couleur en dur dans le style de la page (tokens uniquement)',
    !/#[0-9a-fA-F]{3,8}\b/.test(styles) && !/rgba?\(/.test(styles), (styles.match(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/) || [])[0]);
  check('aucun rouge : rien ici n’est un solde',
    !/var\(--red\)/.test(styles) && !/var\(--flux-neg\)/.test(styles));
  check('une baisse d’affluence n’est pas peinte en rouge',
    /\.tx-delta-down\s*\{[^}]*var\(--muted\)/.test(styles));
}

// ══ 7. LE CÂBLAGE : le source complet tourne contre le VRAI template ════════
// Ni navigateur ni identifiants Supabase ici : le fichier entier est exécuté avec
// un DOM minuscule dont les identifiants sont LUS DANS templates/transactions.html.
// Un id renommé d'un côté seulement fait planter le test au lieu de laisser une
// moitié de page vide en production — c'est la seule chose qui remplace l'œil.
{
  const idsTpl = new Set((tpl.match(/id="([a-z0-9-]+)"/g) || []).map(s => s.slice(4, -1)));
  // \b devant `el(` : sans lui, la fin de `reasonLabel('no-data')` passerait pour un id.
  const idsJs  = new Set((src.match(/\bel\('([a-z0-9-]+)'\)/g) || []).map(s => s.slice(4, -2)));
  const orphelins = [...idsJs].filter(i => !idsTpl.has(i));
  check('chaque id écrit par le script existe dans le template',
    orphelins.length === 0, orphelins.join(', '));

  function faireDom() {
    const els = {};
    idsTpl.forEach(id => {
      els[id] = { id, textContent: '', innerHTML: '', className: '', style: {},
                  getContext: () => ctx2d() };
    });
    return els;
  }
  function ctx2d() {
    return { strokeStyle: '', lineWidth: 0, beginPath() {}, moveTo() {}, lineTo() {},
             stroke() {}, createPattern: () => ({ pattern: true }) };
  }

  let dernierChart = null;
  function lancer(payload, opts) {
    const els = faireDom();
    const doc = {
      getElementById: id => (id in els ? els[id] : null),
      createElement: () => ({ width: 0, height: 0, getContext: () => ctx2d() }),
      documentElement: {},
    };
    const win = { matchMedia: () => ({ addEventListener() {}, addListener() {} }) };
    const chartStub = function (c, cfg) { this.config = cfg; dernierChart = cfg; };
    chartStub.prototype.destroy = function () {};
    const fetchStub = (opts && opts.reject)
      ? () => Promise.reject(new Error('network'))
      : () => Promise.resolve({ json: () => Promise.resolve(payload) });
    const f = new Function('window', 'document', 'getComputedStyle', 'Chart', 'fetch',
      src + '\nreturn { loadTx: loadTx };');
    const api = f(win, doc, () => ({ getPropertyValue: () => '#000' }), chartStub, fetchStub);
    return api.loadTx().then(() => els);
  }

  const PAYLOAD = {
    ok: true, from: '2026-05-27', to: '2026-06-02',
    days: DAYS,
    windows: [W('2026-05-27', '2026-06-09', { tx_median: 21.0, full_days: 5 })],
    weekday: [{ weekday: 0, label: 'Monday', tx_median: 22.0, n: 8 }],
    headline: HL,
  };

  const fini = lancer(PAYLOAD).then(els => {
    check('la réponse est écrite dans le bandeau', els['hl-value'].textContent === '20',
      els['hl-value'].textContent);
    check('le n de chaque fenêtre atterrit à l’écran',
      /8 full open days/.test(els['hl-n'].textContent) && /8 full days/.test(els['hl-prev'].innerHTML),
      els['hl-n'].textContent);
    check('le graphique reçoit une barre par jour ouvert, pas une par jour du calendrier',
      dernierChart.data.datasets[0].data.length === DAYS.length);
    check('la deuxième série est bien un escalier',
      dernierChart.data.datasets[1].stepped === 'middle' && dernierChart.data.datasets[1].spanGaps === false);
    check('l’axe y ne fixe aucun plafond — la pointe à 80 passe en entier',
      dernierChart.options.scales.y.max === undefined && dernierChart.options.scales.y.beginAtZero === true);
    check('le pied du graphique nomme le jour partiel',
      /partial — excluded from medians/.test(els['tx-chart-foot'].innerHTML),
      els['tx-chart-foot'].innerHTML);
    check('le pied dit que les jours fermés n’ont pas de barre',
      /not zero-ticket days/.test(els['tx-chart-foot'].innerHTML));
    check('la table des fenêtres est remplie', /187\.10/.test(els['tx-win-body'].innerHTML));
    check('les sept jours de semaine sont rendus',
      (els['tx-wd-body'].innerHTML.match(/<tr>/g) || []).length === 7);
    return lancer({ ok: true, days: [], windows: [], weekday: [], headline: null });
  }).then(els => {
    check('un payload vide laisse la page lisible, tout à « — »',
      els['hl-value'].textContent === '—' && els['tx-multi-val'].textContent === '—');
    check('un payload vide affiche la raison sous le bandeau', !!els['hl-note'].textContent);
    check('sans jour, le graphique dit qu’il n’y a rien à tracer',
      els['tx-chart-empty'].textContent.length > 0 && els['tx-chart-box'].style.display === 'none');
    return lancer(null, { reject: true });
  }).then(els => {
    check('une panne réseau est annoncée, pas déguisée en zéro',
      els['tx-error'].style.display === '' && /not loaded \(not zero\)/.test(els['tx-error'].textContent),
      els['tx-error'].textContent);
    check('et les chiffres restent « — »', els['hl-value'].textContent === '—');
  });

  fini.then(() => {
    console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
    process.exit(failures ? 1 : 0);
  }).catch(e => {
    console.error('  ✗ le câblage a levé — ' + (e && e.stack || e));
    console.log(`\n${failures + 1} échec(s) sur ${ran + 1}`);
    process.exit(1);
  });
}
