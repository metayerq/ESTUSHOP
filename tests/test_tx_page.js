// La page /transactions — « l'affluence tient-elle ? ». Sans dépendance : node tests/test_tx_page.js
//
// ⚠️ LES FONCTIONS SONT LUES DANS static/transactions.js, PAS RECOPIÉES. Une copie
// divergerait du code livré sans que rien ne le signale — le faux vert le plus cher
// du dépôt. En contrepartie, ce fichier dépend des NOMS : renommer une fonction fait
// échouer le test bruyamment, au lieu de tester du vide.
//
// CE QUI EST VÉRIFIÉ tient en une phrase : la page n'a pas le droit d'inventer un
// chiffre. Pas de zéro pour une absence, pas d'écart contre une fenêtre vide ou
// fragile, pas de médiane de trois jours vendue comme une journée typique, pas de
// répartition horaire dessinée quand elle n'est pas mesurable, pas de sommet écrêté
// en silence, pas de tendance nulle part.
//
// Les données sont les VRAIES : cinq fenêtres de 7 jours entre le 3 juillet et le
// 6 août 2026. C'est le récit que la page doit porter — la fréquentation tient
// (26-28 tickets, 33-35 personnes estimées par jour) pendant que le CA par personne
// s'érode de 7,18 € à 6,45 €.

const fs = require('fs');
const path = require('path');

const SRC_PATH = path.join(__dirname, '..', 'static', 'transactions.js');
const TPL_PATH = path.join(__dirname, '..', 'templates', 'transactions.html');
const src = fs.readFileSync(SRC_PATH, 'utf8');
const tpl = fs.readFileSync(TPL_PATH, 'utf8');

const NOMS = [
  'fmtTx', 'fmtEur', 'fmtPct', 'fmtDay', 'fmtLongDay', 'fmtRange', 'fmtHour',
  'reasonLabel', 'joinReasons', 'deltaModel', 'reliableWindows', 'pickWindows',
  'cappedModel', 'answerModel', 'kpiSpecs', 'kpiModels', 'sparkline', 'sparkSvg',
  'dailyModel', 'windowStep', 'spendModel', 'hourlyModel', 'windowRows',
  'weekdayRows', 'multiLineModel', 'scopeModel',
];

function extraire(nom) {
  const m = src.match(new RegExp('\\nfunction ' + nom + '\\([\\s\\S]*?\\n\\}'));
  if (!m) {
    console.error(`✗ ${nom} introuvable dans static/transactions.js — renommée ou supprimée ?`);
    process.exit(1);
  }
  return m[0];
}

// Le seuil « holding » est une CONSTANTE de jugement, pas une mesure. Il est extrait
// comme le reste : s'il disparaissait du source, answerModel lèverait un
// ReferenceError ici plutôt que de tomber silencieusement sur autre chose.
const CONST = src.match(/\nconst HOLD_PCT = \d+;/);
if (!CONST) {
  console.error('✗ HOLD_PCT introuvable dans static/transactions.js — le seuil « holding » a disparu.');
  process.exit(1);
}

const M = new Function(
  CONST[0] + '\n' + NOMS.map(extraire).join('\n') + '\nreturn {' + NOMS.join(',') + '};'
)();

const {
  fmtTx, fmtEur, fmtPct, reasonLabel, joinReasons, deltaModel, reliableWindows,
  pickWindows, cappedModel, answerModel, kpiModels, sparkline, sparkSvg,
  dailyModel, spendModel, hourlyModel, windowRows, weekdayRows, multiLineModel,
  scopeModel,
} = M;

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// ══ LE PAYLOAD RÉEL ═════════════════════════════════════════════════════════
// Cinq fenêtres de 7 jours. `ca_median` retombe sur tx_median × basket_median,
// comme sur les données servies (26 × 10,29 = 268,0).

const W = (from, to, o) => Object.assign({
  from, to, full_days: 5,
  tx_median: null, ca_median: null, basket_median: null,
  covers_median: null, ca_per_cover: null, covers_capped: 0,
  multi_pct: null, reliable: true, reason: null,
}, o || {});

const WINDOWS = [
  W('2026-07-03', '2026-07-09', { full_days: 5, tx_median: 25.0, ca_median: 270.00, basket_median: 10.80, covers_median: 34.0,  ca_per_cover: 7.18, multi_pct: 30.1 }),
  W('2026-07-10', '2026-07-16', { full_days: 5, tx_median: 37.0, ca_median: 354.83, basket_median: 9.59,  covers_median: 55.0,  ca_per_cover: 7.51, multi_pct: 29.4 }),
  W('2026-07-17', '2026-07-23', { full_days: 6, tx_median: 26.0, ca_median: 278.46, basket_median: 10.71, covers_median: 33.5,  ca_per_cover: 6.68, multi_pct: 30.8 }),
  W('2026-07-24', '2026-07-30', { full_days: 5, tx_median: 28.0, ca_median: 285.60, basket_median: 10.20, covers_median: 35.0,  ca_per_cover: 6.27, multi_pct: 31.9 }),
  W('2026-07-31', '2026-08-06', { full_days: 5, tx_median: 26.0, ca_median: 268.00, basket_median: 10.29, covers_median: 33.0,  ca_per_cover: 6.45, multi_pct: 31.2 }),
];

const HEADLINE = {
  tx_median: 26.0, n: 5, from: '2026-07-31', to: '2026-08-06',
  prev_tx_median: 28.0, prev_n: 5, prev_from: '2026-07-24', prev_to: '2026-07-30',
  delta_pct: -7, reason: null,
};

const DAY = (day, nb, ca, covers, weekday, partial) => ({
  day, nb, ca_ttc: ca, covers, weekday, partial: partial === true,
});

const DAYS = [
  DAY('2026-07-03', 25, 254.25, 34, 4),
  DAY('2026-07-06', 22, 231.00, 30, 0),
  DAY('2026-07-09', 27, 289.00, 36, 3),
  DAY('2026-07-13', 37, 354.83, 55, 0),
  DAY('2026-07-20', 26, 278.46, 33, 0),
  DAY('2026-07-27', 28, 285.60, 35, 0),
  DAY('2026-08-03', 26, 268.00, 33, 0),
  DAY('2026-08-06', 31, 310.00, 40, 3),
  DAY('2026-08-07', 9,   88.40, 12, 4, true),   // aujourd'hui — partiel
];

const HOURLY = {
  days_measured: 37, reason: null,
  by_hour: [
    { hour: 9,  tickets: 160, pct: 12.5, per_day: 4.3 },
    { hour: 11, tickets: 166, pct: 13.0, per_day: 4.5 },
    { hour: 14, tickets: 80,  pct: 6.2,  per_day: 2.2 },
    { hour: 20, tickets: 104, pct: 8.1,  per_day: 2.8 },
  ],
  blocks: [
    { block: 'morning',   from_hour: 5,  to_hour: 12, tickets: 645, pct: 50.4, per_day: 17.4 },
    { block: 'afternoon', from_hour: 13, to_hour: 18, tickets: 317, pct: 24.8, per_day: 8.6 },
    { block: 'evening',   from_hour: 19, to_hour: 23, tickets: 317, pct: 24.8, per_day: 8.6 },
  ],
};

const PAYLOAD = {
  ok: true,
  analysis_start: '2026-07-01', opening_day: '2026-05-27',
  from: '2026-07-01', to: '2026-08-07',
  days: DAYS, windows: WINDOWS, hourly: HOURLY,
  weekday: [
    { weekday: 0, label: 'Monday',   tx_median: 22.0, n: 8 },
    { weekday: 3, label: 'Thursday', tx_median: 29.0, n: 6 },
    { weekday: 4, label: 'Friday',   tx_median: 25.0, n: 5 },
  ],
  headline: HEADLINE,
};

// ══ 1. LE RÉCIT — l'affluence tient, la dépense par personne recule ═════════
console.log('\n— le récit de la page');
{
  const m = answerModel(PAYLOAD);
  check('la réponse est « l’affluence tient »',
    m.verdict === 'holding' && /holding/i.test(m.lead), m.verdict + ' / ' + m.lead);
  check('elle cite les deux fenêtres AVEC LEUR n',
    m.value === '26' && m.n === 5 && m.prevValue === '28' && m.prevN === 5,
    JSON.stringify([m.value, m.n, m.prevValue, m.prevN]));
  check('l’écart d’affluence vient du serveur, il n’est pas recalculé',
    m.delta.ok === true && m.delta.pct === -7 && m.delta.text === '−7 %', JSON.stringify(m.delta));
  check('une baisse n’est pas « rouge » : la direction est une donnée, pas une alarme',
    m.delta.dir === 'down');
  check('le seuil du verdict est PUBLIÉ, parce que c’est un jugement',
    m.threshold === 10);

  // La vraie information de la page.
  check('l’érosion du CA/personne est portée par le bandeau',
    m.erosion.ok === true && m.erosion.first === '€7.18' && m.erosion.last === '€6.45',
    JSON.stringify([m.erosion.first, m.erosion.last]));
  check('l’érosion vaut −10 % entre deux fenêtres NOMMÉES et datées',
    m.erosion.delta.pct === -10
    && /3 Jul/.test(m.erosion.firstRange) && /6 Aug/.test(m.erosion.lastRange),
    JSON.stringify([m.erosion.delta.pct, m.erosion.firstRange, m.erosion.lastRange]));
  check('les deux bouts portent leur n — 5 jours contre 5 jours',
    m.erosion.firstN === 5 && m.erosion.lastN === 5);
  check('les fenêtres intermédiaires sont comptées, pas escamotées',
    m.erosion.windows === 5, String(m.erosion.windows));
}

// ══ 2. delta_pct null ⇒ LA RAISON, JAMAIS « 0 % » ═══════════════════════════
console.log('\n— un écart qu’on ne peut pas calculer ne vaut pas zéro');
{
  // Le cas qui compte : sans comparaison possible, « 0 % » dirait « ça tient » et
  // « −100 % » dirait « effondrement ». Les deux seraient inventés.
  const p = { ...PAYLOAD, headline: { ...HEADLINE, delta_pct: null, reason: 'prev-unreliable' } };
  const m = answerModel(p);
  check('delta_pct null ⇒ aucun pourcentage affiché',
    m.delta.ok === false && m.delta.text === null && m.delta.dir === 'none',
    JSON.stringify(m.delta));
  check('delta_pct null ⇒ jamais la chaîne « 0 % » dans la pastille d’affluence',
    JSON.stringify(m.delta).indexOf('0 %') === -1
    && JSON.stringify(m.delta).indexOf('flat') === -1, JSON.stringify(m.delta));
  check('delta_pct null ⇒ la raison est écrite en clair',
    m.note === 'the earlier window is too thin to compare against', m.note);
  check('delta_pct null ⇒ le verdict devient « inconnu », pas « ça tient »',
    m.verdict === 'unknown' && /cannot be compared/i.test(m.lead), m.lead);
}
{
  // prev_n à zéro : il y a un nombre en face, mais il ne porte aucun jour.
  const p = { ...PAYLOAD, headline: { ...HEADLINE, prev_n: 0, delta_pct: -7 } };
  const m = answerModel(p);
  check('une fenêtre précédente à n=0 n’est pas une référence',
    m.delta.ok === false && m.prevValue === '—', JSON.stringify([m.delta.ok, m.prevValue]));
}
{
  const d = deltaModel(26, null);
  check('deltaModel sans référence ⇒ raison, pas de valeur',
    d.ok === false && d.pct === null && d.reason === 'no-prev-window', JSON.stringify(d));
  const z = deltaModel(26, 0);
  check('deltaModel contre zéro ⇒ « prev-zero », pas +∞',
    z.ok === false && z.reason === 'prev-zero', JSON.stringify(z));
  const n = deltaModel(null, 28);
  check('deltaModel sans mesure courante ⇒ « not-measured », pas −100 %',
    n.ok === false && n.reason === 'not-measured', JSON.stringify(n));
  const f = deltaModel(26, 26);
  check('un écart réellement nul s’écrit « flat », pas « 0 % »',
    f.ok === true && f.text === 'flat' && f.dir === 'flat', JSON.stringify(f));
}

// ══ 3. covers_median null ⇒ « — » + LA RAISON ═══════════════════════════════
console.log('\n— une personne non estimée n’est pas zéro personne');
{
  const wins = WINDOWS.map((w, i) =>
    i === 4 ? { ...w, covers_median: null, ca_per_cover: null } : w);
  const m = kpiModels({ ...PAYLOAD, windows: wins });
  const covers = m.find(k => k.key === 'covers');
  const spend = m.find(k => k.key === 'spend');
  check('covers_median null ⇒ la cellule affiche « — », jamais 0',
    covers.value === '—', covers.value);
  check('covers_median null ⇒ aucun écart n’est publié',
    covers.delta.ok === false && covers.delta.text === null, JSON.stringify(covers.delta));
  check('covers_median null ⇒ la RAISON accompagne le tiret',
    covers.note === 'not measured — the API did not report this figure', covers.note);
  check('ca_per_cover null ⇒ même traitement sur le CA par personne',
    spend.value === '—' && spend.delta.ok === false && !!spend.note,
    JSON.stringify([spend.value, spend.note]));
  check('la sparkline ne compte que les fenêtres RÉELLEMENT mesurées',
    covers.seriesMeasured === 4 && covers.windows === 5,
    JSON.stringify([covers.seriesMeasured, covers.windows]));

  const rows = windowRows(wins);
  check('la table écrit « — » pour la fenêtre sans personnes estimées',
    rows[0].covers === '—' && rows[0].spend === '—',
    JSON.stringify([rows[0].covers, rows[0].spend]));
}
{
  // Un endpoint qui ne connaît PAS `covers` du tout : la page dégrade, elle ne casse pas.
  const nus = WINDOWS.map(w => {
    const c = { ...w };
    delete c.covers_median; delete c.ca_per_cover; delete c.covers_capped;
    return c;
  });
  const jours = DAYS.map(d => { const c = { ...d }; delete c.covers; return c; });
  const p = { ...PAYLOAD, windows: nus, days: jours };
  const m = kpiModels(p);
  check('sans le champ `covers`, la cellule reste à « — » avec sa raison',
    m[1].value === '—' && m[1].note === 'not measured — the API did not report this figure',
    JSON.stringify([m[1].value, m[1].note]));
  const s = spendModel(jours, nus);
  check('sans personnes estimées, le cadre du bas ne se dessine PAS',
    s.ok === false && s.reason === 'no-covers', JSON.stringify([s.ok, s.reason]));
  check('et le refus de dessiner porte une phrase lisible',
    reasonLabel(s.reason) === 'people were not estimated over this window');
  const a = answerModel(p);
  check('le bandeau ne prétend pas mesurer une érosion qu’il n’a pas',
    a.erosion.ok === false && a.erosion.last === '—', JSON.stringify(a.erosion.last));
  check('mais il répond quand même sur l’affluence, qui est mesurée',
    a.ok === true && a.verdict === 'holding');
}

// ══ 4. covers_capped ⇒ LA TRONCATURE ANNONCE CE QU'ELLE CACHE ═══════════════
console.log('\n— un plafond atteint se déclare');
{
  const wins = WINDOWS.map((w, i) => i === 4 ? { ...w, covers_capped: 3 } : w);
  const c = cappedModel(wins);
  check('covers_capped non nul est repéré',
    c.any === true && c.total === 3 && c.windows === 1, JSON.stringify(c));
  check('et il dit dans quel SENS il déforme : personnes sous-comptées, €/personne sur-estimé',
    /under-counted/.test(c.text) && /over-stated/.test(c.text), c.text);

  const rows = windowRows(wins);
  const ligne = rows.find(r => r.to === '2026-08-06');
  check('la fenêtre concernée porte la note dans la table',
    ligne.capped === 3 && /8-person ceiling reached 3×/.test(ligne.note), ligne.note);

  const ok = cappedModel(WINDOWS);
  check('à zéro, rien n’est annoncé — on ne crie pas sur une borne jamais touchée',
    ok.any === false && ok.text === null, JSON.stringify(ok));
  const rows0 = windowRows(WINDOWS);
  check('et aucune ligne ne porte de note de plafond',
    rows0.every(r => !r.note || !/ceiling/.test(r.note)));
}

// ══ 5. hourly.reason ⇒ UN MESSAGE, PAS UN GRAPHIQUE ════════════════════════
console.log('\n— une répartition horaire non mesurable ne se dessine pas');
{
  const m = hourlyModel(HOURLY);
  check('avec 37 jours mesurés, la répartition se dessine',
    m.ok === true && m.bars.length === 4, JSON.stringify([m.ok, m.bars.length]));
  // 9h porte 160 tickets, plus que le pic du soir (20h, 104). « Les deux heures les
  // plus chargées » sortirait donc 11h et 9h — deux heures du MÊME bloc — et
  // laisserait la clientèle du soir sans marque. Le sommet de chaque bloc, lui,
  // montre bien les deux clientèles.
  check('le sommet de chaque bloc est marqué : 11h le matin, 14h l’après-midi, 20h le soir',
    m.peaks.join(',') === '11,14,20', m.peaks.join(','));
  check('la règle est énoncée dans le modèle, pas seulement appliquée',
    /busiest hour inside each block/.test(m.peakRule), m.peakRule);
  check('9h (160 tickets) n’est PAS marqué, alors qu’il dépasse le pic du soir',
    m.bars.find(b => b.hour === 9).peak === false
    && m.bars.find(b => b.hour === 20).peak === true);
  check('un sommet par bloc, ni plus ni moins',
    m.bars.filter(b => b.peak).length === 3);
  check('les trois blocs sont repris tels quels : 50,4 % le matin',
    m.blocks[0].pctText === '50.4 %' && m.blocks[0].width === 50,
    JSON.stringify([m.blocks[0].pctText, m.blocks[0].width]));
  check('days_measured est remonté pour être affiché', m.daysMeasured === 37);
}
{
  // Une répartition sur 3 jours ressemble EXACTEMENT à une répartition sur 30.
  // Rien dans les barres ne dirait laquelle on regarde : on n'en dessine aucune.
  const h = { days_measured: 3, reason: 'too-few-measured-days', by_hour: [], blocks: [] };
  const m = hourlyModel(h);
  check('hourly.reason non nul ⇒ ok=false, aucune barre',
    m.ok === false && m.bars.length === 0 && m.blocks.length === 0,
    JSON.stringify([m.ok, m.bars.length, m.blocks.length]));
  check('hourly.reason non nul ⇒ un message en clair remplace le graphique',
    m.note === 'too few days carry a recorded ticket time', m.note);
  check('et days_measured reste affiché, pour qu’on sache sur quoi porte le refus',
    m.daysMeasured === 3);
}
{
  // Le piège inverse : une raison posée alors que les barres SONT là. On ne dessine
  // toujours pas — c'est le serveur qui sait, pas la page.
  const m = hourlyModel({ ...HOURLY, reason: 'too-few-measured-days' });
  check('des barres présentes ne rachètent pas une raison posée',
    m.ok === false && m.bars.length === 0, JSON.stringify([m.ok, m.bars.length]));
}
{
  check('hourly absent ⇒ refus de dessiner, avec sa raison',
    hourlyModel(null).ok === false
    && hourlyModel(null).note === 'not measured — the API did not report this figure');
  check('hourly vide ⇒ pas de barres inventées',
    hourlyModel({ days_measured: 9, reason: null, by_hour: [], blocks: [] }).ok === false);
}

// ══ 6. LE JOUR PARTIEL EST MARQUÉ ═══════════════════════════════════════════
console.log('\n— aujourd’hui n’est pas une journée');
{
  const m = dailyModel(DAYS, WINDOWS);
  check('le jour partiel a bien une barre — c’est une mesure, pas une absence',
    m.n === 9, String(m.n));
  const auj = m.bars[m.bars.length - 1];
  check('et il est MARQUÉ partiel', auj.day === '2026-08-07' && auj.partial === true,
    JSON.stringify([auj.day, auj.partial]));
  check('il est nommé dans la liste destinée au pied du graphique',
    m.partialDays.length === 1 && /7 Aug/.test(m.partialDays[0]), JSON.stringify(m.partialDays));
  check('les autres jours ne sont pas marqués',
    m.bars.filter(b => b.partial).length === 1);
  check('le sommet réel est publié sans écrêtage',
    m.yMax === 37 && m.clipped === false, JSON.stringify([m.yMax, m.clipped]));
  check('les jours fermés n’existent pas — pas de barre à zéro entre le 3 et le 6 juillet',
    m.tickets.every(v => v > 0) && m.n === DAYS.length);
}
{
  // Le palier d'une fenêtre non fiable ne se dessine pas : il serait indiscernable
  // des autres une fois tracé.
  const wins = WINDOWS.map((w, i) =>
    i === 4 ? { ...w, reliable: false, full_days: 2, reason: 'too-few-days' } : w);
  const m = dailyModel(DAYS, wins);
  const i = m.bars.findIndex(b => b.day === '2026-08-03');
  check('une fenêtre non fiable ne produit AUCUN palier — un trou, pas une valeur',
    m.steps[i] === null, String(m.steps[i]));
  const j = m.bars.findIndex(b => b.day === '2026-07-27');
  check('les paliers des fenêtres fiables restent en place',
    m.steps[j] === 28.0, String(m.steps[j]));
}

// ══ 7. PAYLOAD VIDE — LA PAGE NE CASSE PAS ═════════════════════════════════
console.log('\n— rien reçu : « — » partout, aucune exception');
{
  const VIDES = [undefined, null, {}, { ok: true }, { days: [], windows: [], weekday: [] }];
  let boum = null;
  VIDES.forEach((v, i) => {
    try {
      answerModel(v); kpiModels(v); scopeModel(v); cappedModel(v && v.windows);
      dailyModel(v && v.days, v && v.windows); spendModel(v && v.days, v && v.windows);
      hourlyModel(v && v.hourly); windowRows(v && v.windows);
      weekdayRows(v && v.weekday); multiLineModel(v && v.windows);
      pickWindows(v); reliableWindows(v && v.windows);
    } catch (e) { boum = `payload #${i} : ${e.message}`; }
  });
  check('aucun modèle ne lève sur un payload vide, absent ou tronqué', boum === null, boum);

  const a = answerModel({});
  check('sans donnée, le bandeau dit qu’il ne sait pas — il n’affiche pas 0',
    a.ok === false && a.value === '—' && a.verdict === 'unknown',
    JSON.stringify([a.value, a.verdict]));
  check('et il nomme la cause',
    a.note === 'no 7-day window has enough full open days yet', a.note);

  const k = kpiModels({});
  check('les quatre cellules existent quand même, toutes à « — »',
    k.length === 4 && k.every(c => c.value === '—'), JSON.stringify(k.map(c => c.value)));
  check('aucune cellule ne publie d’écart',
    k.every(c => c.delta.ok === false && !!c.note));
  check('aucune sparkline n’est dessinée sur du vide',
    k.every(c => sparkSvg(c.series, 92, 26) === ''));

  const d = dailyModel([], []);
  check('aucun jour ⇒ aucune barre, et yMax n’est pas un maximum inventé',
    d.n === 0 && d.bars.length === 0 && d.yMax === 0);
  check('la table des fenêtres est vide, pas remplie de zéros', windowRows([]).length === 0);
  check('les 7 jours de semaine existent, ceux jamais ouverts à « — »',
    weekdayRows([]).length === 7 && weekdayRows([]).every(r => r.tx === '—' && r.n === 0));
}

// ══ 8. FENÊTRES FRAGILES : n CONSERVÉ, MÉDIANES RETIRÉES ═══════════════════
console.log('\n— une médiane de trois jours n’est pas une journée typique');
{
  const wins = WINDOWS.concat([
    W('2026-08-07', '2026-08-13', {
      full_days: 1, tx_median: 9.0, ca_median: 88.40, basket_median: 9.82,
      covers_median: 12.0, ca_per_cover: 7.37, reliable: false, reason: 'truncated+too-few-days',
    }),
  ]);
  const rows = windowRows(wins);
  const fragile = rows[0];
  check('la fenêtre fragile garde son n — c’est l’information utile',
    fragile.n === 1 && fragile.reliable === false, JSON.stringify([fragile.n, fragile.reliable]));
  check('mais elle perd TOUTES ses médianes',
    fragile.tx === '—' && fragile.ca === '—' && fragile.basket === '—'
    && fragile.covers === '—' && fragile.spend === '—');
  check('et les raisons cumulées sont dépliées, jointes par « · »',
    fragile.note === 'window truncated — start of the analysis period · '
      + 'too few full open days in this window for a median', fragile.note);
  check('elle n’entre dans aucune sparkline ni aucun écart',
    reliableWindows(wins).length === 5);
  check('la table est triée du plus récent au plus ancien',
    rows[0].to === '2026-08-13' && rows[rows.length - 1].to === '2026-07-09');
}
{
  // Le repli quand le headline est muet : on prend la dernière fenêtre FIABLE,
  // jamais la dernière fenêtre tout court.
  const wins = WINDOWS.concat([
    W('2026-08-07', '2026-08-13', { full_days: 1, tx_median: 9.0, reliable: false, reason: 'too-few-days' }),
  ]);
  const p = pickWindows({ windows: wins, headline: {} });
  check('sans headline, la fenêtre courante est la dernière FIABLE',
    p.cur.to === '2026-08-06', p.cur && p.cur.to);
  check('et la précédente est celle d’avant, fiable elle aussi',
    p.prev.to === '2026-07-30', p.prev && p.prev.to);
}
{
  const p = pickWindows({ windows: [WINDOWS[4]], headline: HEADLINE });
  check('une seule fenêtre ⇒ pas de précédente, et la raison le dit',
    p.prev === null && /no-prev-window/.test(p.reason || ''), JSON.stringify([p.prev, p.reason]));
}
{
  // Le serveur ne DEVRAIT jamais désigner une fenêtre fragile comme référence — son
  // headline ne retient que des fenêtres fiables. La page s'en défend quand même,
  // parce qu'un contrat qui change sous une page est exactement ce qui est déjà
  // arrivé ici. Une défense non testée est du code mort : on la met à l'épreuve.
  const wins = WINDOWS.map((w, i) =>
    i === 3 ? { ...w, reliable: false, full_days: 2, reason: 'too-few-days' } : w);
  const p = pickWindows({ windows: wins, headline: HEADLINE });
  check('une fenêtre de référence fragile est REFUSÉE, même désignée par le serveur',
    p.prev === null && /prev-unreliable/.test(p.reason || ''),
    JSON.stringify([p.prev && p.prev.to, p.reason]));
  check('la fenêtre courante, elle, reste celle du serveur',
    p.cur.to === '2026-08-06', p.cur && p.cur.to);

  const k = kpiModels({ ...PAYLOAD, windows: wins });
  check('aucune des quatre cellules ne publie d’écart contre une fenêtre fragile',
    k.every(c => c.delta.ok === false && c.prevValue === '—'),
    JSON.stringify(k.map(c => [c.key, c.delta.ok, c.prevValue])));
  check('et chacune dit pourquoi',
    k.every(c => /too thin to compare against/.test(c.note || '')),
    JSON.stringify(k.map(c => c.note)));
}

// ══ 9. LES QUATRE KPI DÉCRIVENT LA MÊME PAIRE DE FENÊTRES ══════════════════
console.log('\n— quatre chiffres, deux fenêtres, une seule période');
{
  const k = kpiModels(PAYLOAD);
  check('les quatre cellules pointent la même fenêtre courante',
    k.every(c => c.range === k[0].range) && /31 Jul/.test(k[0].range), k[0].range);
  check('et la même fenêtre de référence',
    k.every(c => c.prevRange === k[0].prevRange) && /24 Jul/.test(k[0].prevRange), k[0].prevRange);
  check('tickets : 26, −7 % contre 28',
    k[0].value === '26' && k[0].delta.pct === -7, JSON.stringify([k[0].value, k[0].delta.pct]));
  check('personnes estimées : 33, −6 % contre 35',
    k[1].value === '33' && k[1].delta.pct === -6, JSON.stringify([k[1].value, k[1].delta.pct]));
  check('CA par personne : 6,45 €, +3 % contre 6,27 €',
    k[2].value === '€6.45' && k[2].delta.pct === 3, JSON.stringify([k[2].value, k[2].delta.pct]));
  check('panier : 10,29 €',
    k[3].value === '€10.29', k[3].value);
  check('le libellé des personnes ne dit JAMAIS « customers »',
    k.every(c => !/customer/i.test(c.label + ' ' + c.hint)),
    k.map(c => c.label).join(' | '));
  check('et il annonce que c’est une ESTIMATION, avec sa règle et son sens',
    /Estimated, not counted/.test(k[1].hint) && /ceiling 8/.test(k[1].hint)
    && /Runs high/.test(k[1].hint), k[1].hint);
  check('le CA/personne prévient qu’il ne se retrouve pas en divisant deux colonnes',
    /not revenue\/day/.test(k[2].hint), k[2].hint);
}

// ══ 10. SPARKLINE — pas de tendance, pas d'interpolation, pas de plancher ══
console.log('\n— la sparkline est une liste de paliers, pas une pente');
{
  const s = sparkline([25, 37, 26, 28, 26], 92, 26);
  check('cinq points mesurés ⇒ une seule polyligne',
    s.ok === true && s.segments.length === 1 && s.segments[0].length === 5,
    JSON.stringify([s.segments.length, s.segments[0] && s.segments[0].length]));
  check('les bornes sont les vraies valeurs, pas 0 et un arrondi supérieur',
    s.min === 25 && s.max === 37, JSON.stringify([s.min, s.max]));
  check('le maximum est en haut, le minimum en bas',
    s.segments[0][1].y < s.segments[0][0].y);
}
{
  const s = sparkline([25, null, 26, 28, 26], 92, 26);
  check('un trou COUPE la ligne — on n’interpole pas par-dessus une absence',
    s.segments.length === 2 && s.gaps === 1,
    JSON.stringify([s.segments.length, s.gaps]));
  check('le point resté seul est isolé pour être tracé quand même',
    s.isolated.length === 1 && s.isolated[0].x === 3, JSON.stringify(s.isolated));
  const svg = sparkSvg([25, null, 26, 28, 26], 92, 26);
  check('le SVG trace une polyligne pour le groupe restant',
    (svg.match(/<polyline/g) || []).length === 1, svg);
  // Une mesure qui n'a pas de voisine ne DISPARAÎT pas du dessin : elle se voit,
  // en creux, et l'absence de trait dit qu'aucune ligne ne la rejoint.
  check('et un cercle creux pour la mesure restée seule',
    /circle[^>]*fill="none"/.test(svg), svg);
}
{
  const s = sparkline([26, 26, 26], 92, 26);
  check('une série plate se dessine au MILIEU, pas collée au plancher',
    s.flat === true && s.segments[0].every(p => p.y === 13),
    JSON.stringify(s.segments[0]));
}
{
  check('un seul point mesuré ne fait pas une ligne',
    sparkline([26], 92, 26).ok === false && sparkSvg([26], 92, 26) === '');
  check('une série vide non plus',
    sparkline([], 92, 26).ok === false && sparkline([null, null], 92, 26).ok === false);
}

// ══ 11. LE PÉRIMÈTRE — JUIN EST EXCLU, ET ÇA SE VOIT ═══════════════════════
console.log('\n— l’exclusion de juin est annoncée, pas cachée');
{
  const m = scopeModel(PAYLOAD);
  check('l’analyse démarre au 1er juillet', m.analysisStart === '2026-07-01');
  check('l’ouverture du 27 mai est retenue', m.openingDay === '2026-05-27');
  check('l’exclusion est DÉTECTÉE et bornée à la veille du démarrage',
    m.excludes === true && m.excludedFrom === '2026-05-27' && m.excludedTo === '2026-06-30',
    JSON.stringify([m.excludes, m.excludedFrom, m.excludedTo]));
  check('elle est écrite en toutes lettres',
    /27 May 2026/.test(m.excludedText) && /30 Jun 2026/.test(m.excludedText), m.excludedText);
}
{
  // Un endpoint qui ne dit pas où commence l'analyse : on ne l'invente pas, on
  // retombe sur `from` ET on prévient que c'est un repli.
  const p = { ...PAYLOAD }; delete p.analysis_start;
  const m = scopeModel(p);
  check('sans analysis_start, on retombe sur `from` — et on le DIT',
    m.analysisStart === '2026-07-01' && /did not report analysis_start/.test(m.note || ''),
    m.note);
}
{
  const p = { ...PAYLOAD, opening_day: '2026-07-01' };
  check('ouverture le jour du démarrage ⇒ rien n’est exclu, on n’invente pas de trou',
    scopeModel(p).excludes === false);
}

// ══ 12. JOURS DE SEMAINE ET MULTI-LIGNES ═══════════════════════════════════
console.log('\n— le n vit à côté de chaque médiane');
{
  const r = weekdayRows(PAYLOAD.weekday);
  check('les 7 jours sont là, dans l’ordre lundi → dimanche',
    r.length === 7 && r[0].label === 'Monday' && r[6].label === 'Sunday');
  check('un jour jamais ouvert vaut « — », pas 0',
    r[1].tx === '—' && r[1].n === 0 && r[1].note === 'never open on this day yet',
    JSON.stringify([r[1].tx, r[1].n]));
  check('la barre du plus fort jour occupe 100 %, les autres en proportion',
    r[3].width === 100 && r[0].width === Math.round(22 / 29 * 100),
    JSON.stringify([r[3].width, r[0].width]));
  check('un jour sans mesure n’a pas de barre', r[1].width === 0);
}
{
  const m = multiLineModel(WINDOWS);
  check('la part multi-lignes est lue sur la DERNIÈRE fenêtre fiable, pas moyennée',
    m.ok === true && m.text === '31.2 %' && m.n === 5, JSON.stringify([m.text, m.n]));
  const sans = WINDOWS.map(w => ({ ...w, multi_pct: null }));
  check('non mesurée ⇒ « — » et sa raison, jamais 0,0 %',
    multiLineModel(sans).text === '—'
    && /multi-line share not recorded/.test(multiLineModel(sans).note || ''),
    multiLineModel(sans).note);
}

// ══ 13. FORMAT ET RAISONS ══════════════════════════════════════════════════
console.log('\n— un null s’écrit « — », jamais 0');
{
  check('fmtTx(null) === « — »', fmtTx(null) === '—' && fmtTx(undefined) === '—');
  check('fmtEur(null) === « — »', fmtEur(null) === '—' && fmtEur(0) === '€0.00');
  check('fmtPct(null) === « — »', fmtPct(null) === '—' && fmtPct(0) === '0.0 %');
  check('un NaN ou un Infinity n’est pas un chiffre non plus',
    fmtTx(NaN) === '—' && fmtEur(Infinity) === '—');
  check('zéro RESTE zéro : c’est une mesure, pas une absence',
    fmtTx(0) === '0');
}
{
  check('un code inconnu s’affiche brut plutôt que de disparaître',
    reasonLabel('quelque-chose-de-neuf') === 'quelque-chose-de-neuf');
  check('les codes cumulés par « + » sont tous dépliés',
    reasonLabel('truncated+no-prev-window')
      === 'window truncated — start of the analysis period · '
        + 'no earlier reliable window to compare against');
  check('aucun code n’est laissé sans phrase parmi ceux du contrat',
    ['truncated', 'no-days', 'too-few-days', 'no-reliable-window', 'latest-window-skipped',
     'windows-skipped', 'no-prev-window', 'prev-zero'].every(c => reasonLabel(c) !== c));
  check('joinReasons cumule sans doublon',
    joinReasons('truncated', 'truncated+no-days') === 'truncated+no-days',
    joinReasons('truncated', 'truncated+no-days'));
  check('joinReasons de deux riens vaut rien', joinReasons(null, null) === null);
}

// ══ 14. UNE RÉSERVE QUI VAUT MÊME QUAND LE CHIFFRE EXISTE ══════════════════
console.log('\n— une fenêtre sautée change le sens du chiffre affiché');
{
  const m = answerModel({ ...PAYLOAD, headline: { ...HEADLINE, reason: 'latest-window-skipped' } });
  check('l’écart reste calculable, mais la réserve est portée séparément',
    m.delta.ok === true
    && m.caveat === 'the most recent window was skipped — too few open days',
    JSON.stringify([m.delta.ok, m.caveat]));
  check('sans réserve, il n’y a pas de réserve affichée',
    answerModel(PAYLOAD).caveat === null);
}

// ══ 15. LE GABARIT — ce qui doit rester à l'écran ══════════════════════════
console.log('\n— le gabarit');
{
  const IDS = [
    'tx-scope-band', 'hl-lead', 'hl-value', 'hl-delta', 'hl-n', 'hl-prev', 'hl-erosion',
    'hl-rule', 'hl-caveat', 'hl-note', 'tx-kpis', 'tx-chart-grid', 'chart-footfall',
    'tx-frame-spend', 'chart-spend', 'tx-spend-box', 'tx-spend-empty', 'tx-chart-empty',
    'tx-chart-foot', 'tx-hours-meta', 'tx-blocks', 'tx-hours-box', 'tx-hours-bars',
    'tx-hours-empty', 'tx-hours-foot', 'tx-win-body', 'tx-wd-body', 'tx-multi-val',
    'tx-multi-sub', 'tx-error', 'tx-scope',
  ];
  const manquants = IDS.filter(id => tpl.indexOf('id="' + id + '"') === -1);
  check('tous les points d’ancrage du rendu existent dans le gabarit',
    manquants.length === 0, manquants.join(', '));

  // L'encart FIXE : il reste même quand tout va bien. Sans lui, ces questions se
  // répondraient par un chiffre inventé.
  check('l’encart « What this page cannot tell you » est là',
    /What this page cannot tell you/.test(tpl));
  check('il porte les regulars et la preuve chiffrée du NIF vide',
    /Regulars/.test(tpl) && /59 of 60/.test(tpl) && /fiscal_id/.test(tpl));
  check('il porte l’estimation des personnes, sa règle et son SENS',
    /1 drink = 1 person/.test(tpl) && /ceiling 8/.test(tpl) && /upper bound/.test(tpl));
  check('il porte l’exclusion de juin, avec les 55 boissons',
    /June is excluded/.test(tpl) && /55 drinks/.test(tpl) && /27 May 2026/.test(tpl));
  check('il porte l’absence d’août de référence',
    /Holiday effect/.test(tpl) && /2027/.test(tpl));
  check('il dit pourquoi il n’y a AUCUNE tendance',
    /No trend, on purpose/.test(tpl) && /regression/i.test(tpl));
  check('le mot « customers » n’est jamais employé pour les personnes estimées',
    !/\d+\s*customers/i.test(tpl));
}
{
  // Le style de la page (hors bloc de nav, partagé par tous les gabarits) ne doit
  // porter QUE des tokens : une couleur en dur ne serait juste que dans un thème.
  const bloc = tpl.slice(tpl.indexOf('/* ══ /transactions'), tpl.indexOf('</style>'));
  check('le bloc de style ne contient aucune couleur en dur',
    !/#[0-9a-fA-F]{3,8}\b/.test(bloc) && !/rgba?\(/.test(bloc),
    (bloc.match(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g) || []).join(' '));
  check('AUCUN ROUGE : rien ici n’est un solde',
    !/--red|--flux-neg|delta-down/.test(bloc));
  check('le source ne peint rien en dur non plus',
    !/#[0-9a-fA-F]{6}\b/.test(src), (src.match(/#[0-9a-fA-F]{6}\b/g) || []).join(' '));
  check('le source ne lit que des tokens connus',
    (src.match(/cssVar\('([^']+)'\)/g) || [])
      .every(c => /--(bg|bg-card|text|border|muted|faint|green|amber|mono|flux-keep|flux-leave|flux-tax)\b/.test(c)),
    (src.match(/cssVar\('([^']+)'\)/g) || []).join(' '));
}
{
  // La garde qui compte le plus : rien sur cette page n'a le droit de lisser,
  // d'ajuster ou de projeter. Un `stepped` retiré transformerait chaque palier en
  // pente, et personne ne le verrait dans une revue de diff.
  check('les deux séries de fenêtre sont des ESCALIERS, jamais des courbes',
    (src.match(/stepped: 'middle'/g) || []).length === 3,
    String((src.match(/stepped: 'middle'/g) || []).length));
  check('aucun trou n’est comblé par interpolation',
    (src.match(/spanGaps: false/g) || []).length === 4
    && !/spanGaps: true/.test(src));
  check('aucune tension de courbe n’est introduite', !/tension:/.test(src));
  check('aucun axe n’est plafonné en douce',
    !/suggestedMax|max:\s*\d/.test(src));
  check('les deux cadres ne partagent PAS d’axe Y — pas de double axe',
    !/yAxisID|position: 'right'/.test(src));
}

// ══ 16. LE RENDU LUI-MÊME, EXÉCUTÉ ════════════════════════════════════════
// Les tests ci-dessus ne voient que les modèles. Or la moitié des façons de mentir
// vit dans le rendu : un id qui n'existe plus, une raison calculée puis jamais
// écrite, un « — » remplacé par un 0 au moment de la concaténation. Personne ne
// verra jamais cette page dans un navigateur pendant qu'elle est écrite : le
// fichier entier est donc EXÉCUTÉ ici, sur un DOM minimal, et on relit ce qui a
// été posé dans les éléments.
//
// getElementById ne connaît QUE les id présents dans le gabarit et renvoie null
// pour les autres : un id inventé côté JS lève ici au lieu de ne rien afficher.
console.log('\n— le rendu, exécuté sur un DOM minimal');

function faireDom() {
  const ids = {};
  (tpl.match(/id="([^"]+)"/g) || []).forEach(function (m) {
    const id = m.slice(4, -1);
    ids[id] = {
      id, textContent: '', innerHTML: '', className: '', style: {},
      getContext: () => ctx2d(),
    };
  });
  function ctx2d() {
    return {
      strokeStyle: '', lineWidth: 0,
      beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
      createPattern: () => ({ pattern: true }),
      canvas: { width: 600, height: 200 },
    };
  }
  const charts = [];
  function Chart(ctx, cfg) { this.cfg = cfg; this.destroy = function () {}; charts.push(cfg); }
  const document = {
    documentElement: {},
    getElementById: (id) => (Object.prototype.hasOwnProperty.call(ids, id) ? ids[id] : null),
    createElement: () => ({ width: 0, height: 0, getContext: ctx2d }),
    addEventListener() {},
  };
  const win = { matchMedia: null, uiLoadStart: null, uiLoadEnd: null };
  const getComputedStyle = () => ({ getPropertyValue: (n) => 'var' + n });
  const fetch = () => new Promise(() => {});   // inerte : on appelle renderAll nous-mêmes
  const api = new Function(
    'document', 'window', 'getComputedStyle', 'Chart', 'fetch',
    src + '\nreturn { renderAll: renderAll, renderCharts: renderCharts };'
  )(document, win, getComputedStyle, Chart, fetch);
  return { ids, charts, api };
}

{
  let boum = null;
  const dom = faireDom();
  try { dom.api.renderAll(PAYLOAD); } catch (e) { boum = e.message; }
  check('le rendu complet passe sur le payload réel, sans id manquant', boum === null, boum);

  const t = (id) => (dom.ids[id] ? (dom.ids[id].innerHTML || dom.ids[id].textContent) : '@ABSENT');
  check('le bandeau du haut annonce l’exclusion, avec ses deux bornes',
    /Analysis starts 1 Jul 2026/.test(t('tx-scope-band'))
    && /27 May 2026/.test(t('tx-scope-band')) && /30 Jun 2026/.test(t('tx-scope-band')),
    t('tx-scope-band'));
  check('la réponse est écrite : « Footfall is holding. » avec 26',
    /Footfall is holding\./.test(t('hl-lead')) && t('hl-value') === '26',
    t('hl-lead') + ' / ' + t('hl-value'));
  check('la pastille d’écart est posée, sans classe rouge',
    /−7 %/.test(t('hl-delta')) && !/delta-down|--red/.test(t('hl-delta')), t('hl-delta'));
  check('l’érosion du CA/personne est bien écrite dans le bandeau',
    /€6\.45/.test(t('hl-erosion')) && /€7\.18/.test(t('hl-erosion'))
    && /no trend is fitted/.test(t('hl-erosion')), t('hl-erosion'));
  check('le seuil du verdict est affiché à l’écran, pas seulement dans le modèle',
    /&plusmn;10/.test(t('hl-rule')), t('hl-rule'));
  check('les quatre cellules KPI sont posées, avec leurs sparklines',
    (t('tx-kpis').match(/kpi-cell/g) || []).length === 4
    && (t('tx-kpis').match(/<svg/g) || []).length === 4, t('tx-kpis').slice(0, 120));
  // Le tooltip partagé [data-tip] vit dans static/dashboard.js, que cette page ne
  // charge pas : une réserve rangée là n'existerait nulle part.
  check('les réserves sont du TEXTE VISIBLE, pas un survol qui n’existe pas ici',
    (t('tx-kpis').match(/tx-kpi-hint/g) || []).length === 4
    && /ceiling 8/.test(t('tx-kpis')) && !/data-tip/.test(t('tx-kpis')),
    t('tx-kpis').slice(0, 200));
  check('l’axe tronqué du bas s’annonce sous le graphique',
    /does not start at zero/.test(t('tx-chart-foot')), t('tx-chart-foot'));
  check('le pied de graphique dit que les jours fermés ne sont pas des zéros',
    /they are not zero-ticket days/.test(t('tx-chart-foot')));
  check('il dit aussi que les deux cadres NE PARTAGENT PAS d’axe Y',
    /neither shares a y-axis/.test(t('tx-chart-foot')), t('tx-chart-foot'));
  check('le jour partiel est nommé en clair sous le graphique',
    /7 Aug/.test(t('tx-chart-foot')) && /partial/.test(t('tx-chart-foot')));
  check('les trois blocs horaires sont rendus avec leurs barres',
    (t('tx-blocks').match(/progress-fill/g) || []).length === 3
    && /50\.4 %/.test(t('tx-blocks')), t('tx-blocks').slice(0, 100));
  check('la table des fenêtres porte les cinq lignes',
    (t('tx-win-body').match(/<tr class="">/g) || []).length === 5,
    String((t('tx-win-body').match(/<tr/g) || []).length));
  check('et le CA/personne de la dernière fenêtre y figure', /€6\.45/.test(t('tx-win-body')));
  check('les sept jours de semaine sont rendus',
    (t('tx-wd-body').match(/<tr>/g) || []).length === 7);

  // Deux graphiques, deux configurations : aucune ne doit porter deux axes Y.
  check('deux graphiques sont construits, pas un seul à deux axes',
    dom.charts.length === 2, String(dom.charts.length));
  check('chaque graphique n’a qu’UN axe Y',
    dom.charts.every(c => Object.keys(c.options.scales).filter(k => k[0] === 'y').length === 1),
    JSON.stringify(dom.charts.map(c => Object.keys(c.options.scales))));
  check('les deux partagent exactement les mêmes étiquettes de dates',
    dom.charts[0].data.labels.join('|') === dom.charts[1].data.labels.join('|'));
  check('et la même largeur d’axe imposée, sans quoi ils ne s’alignent pas',
    dom.charts.every(c => typeof c.options.scales.y.afterFit === 'function'));
  check('aucune animation ne masque un re-rendu',
    dom.charts.every(c => c.options.animation === false));
}
{
  // Payload vide : la page doit rester lisible et ne poser AUCUN zéro.
  let boum = null;
  const dom = faireDom();
  try { dom.api.renderAll({}); } catch (e) { boum = e.message; }
  check('le rendu passe aussi sur un payload vide', boum === null, boum);
  const t = (id) => (dom.ids[id] ? (dom.ids[id].innerHTML || dom.ids[id].textContent) : '@ABSENT');
  check('la valeur du bandeau reste « — »', t('hl-value') === '—', t('hl-value'));
  check('aucune pastille d’écart n’est posée', t('hl-delta') === '', t('hl-delta'));
  check('la raison est écrite à la place du chiffre, et l’élément est visible',
    /no 7-day window/.test(t('hl-note')) && dom.ids['hl-note'].style.display === '',
    t('hl-note'));
  check('les quatre cellules restent à « — », chacune avec sa raison',
    (t('tx-kpis').match(/>—</g) || []).length === 4
    && (t('tx-kpis').match(/tx-kpi-reason/g) || []).length >= 4, t('tx-kpis').slice(0, 200));
  check('aucun graphique n’est construit sur du vide', dom.charts.length === 0);
  check('les deux cadres sont masqués ensemble, pas un seul',
    dom.ids['tx-chart-grid'].style.display === 'none'
    && dom.ids['tx-frame-spend'].style.display === 'none');
  check('la répartition horaire affiche son refus, pas des barres',
    /not drawn/.test(t('tx-hours-empty')) && dom.ids['tx-hours-box'].style.display === 'none',
    t('tx-hours-empty'));
  check('et elle dit que le nombre de jours mesurés n’est pas connu',
    /not reported/.test(t('tx-hours-meta')), t('tx-hours-meta'));
}
{
  // Le cas le plus dangereux du lot : hourly.reason posé. Rien ne doit être dessiné.
  const dom = faireDom();
  dom.api.renderAll({ ...PAYLOAD, hourly: { days_measured: 3, reason: 'too-few-measured-days', by_hour: HOURLY.by_hour, blocks: HOURLY.blocks } });
  const t = (id) => (dom.ids[id] ? (dom.ids[id].innerHTML || dom.ids[id].textContent) : '@ABSENT');
  check('hourly.reason ⇒ les barres sont MASQUÉES et les blocs effacés',
    dom.ids['tx-hours-box'].style.display === 'none' && t('tx-blocks') === '',
    t('tx-blocks').slice(0, 80));
  check('hourly.reason ⇒ le message explique pourquoi',
    /too few days carry a recorded ticket time/.test(t('tx-hours-empty')), t('tx-hours-empty'));
  check('hourly.reason ⇒ days_measured reste affiché : on sait sur quoi porte le refus',
    /3 full open days/.test(t('tx-hours-meta')), t('tx-hours-meta'));
}
{
  // covers_capped à l'écran, pas seulement dans le modèle.
  const dom = faireDom();
  const wins = WINDOWS.map((w, i) => (i === 4 ? { ...w, covers_capped: 3 } : w));
  dom.api.renderAll({ ...PAYLOAD, windows: wins });
  const t = (id) => (dom.ids[id] ? (dom.ids[id].innerHTML || dom.ids[id].textContent) : '@ABSENT');
  check('le plafond atteint est écrit sous les cellules concernées',
    (t('tx-kpis').match(/8-person ceiling/g) || []).length === 2, t('tx-kpis').slice(0, 80));
  check('il est écrit dans la table des fenêtres',
    /8-person ceiling reached 3×/.test(t('tx-win-body')));
  check('et sous le graphique, où le chiffre est lu',
    /8-person ceiling/.test(t('tx-chart-foot')), t('tx-chart-foot'));
}
{
  // Sans personnes estimées, le cadre du bas ne se dessine pas — il s'explique.
  const dom = faireDom();
  const nus = WINDOWS.map(w => { const c = { ...w }; delete c.covers_median; delete c.ca_per_cover; return c; });
  const jours = DAYS.map(d => { const c = { ...d }; delete c.covers; return c; });
  dom.api.renderAll({ ...PAYLOAD, windows: nus, days: jours });
  const t = (id) => (dom.ids[id] ? (dom.ids[id].innerHTML || dom.ids[id].textContent) : '@ABSENT');
  check('le cadre du bas est masqué et remplacé par sa raison',
    dom.ids['tx-spend-box'].style.display === 'none'
    && /people were not estimated/.test(t('tx-spend-empty')), t('tx-spend-empty'));
  check('le cadre du haut, lui, reste dessiné : l’affluence est mesurée',
    dom.ids['tx-chart-grid'].style.display === '' && dom.charts.length === 1,
    String(dom.charts.length));
  check('la légende du cadre absent est masquée avec lui — pas de marques sans tracé',
    dom.ids['tx-spend-legend'].style.display === 'none');
  check('et le pied ne parle plus de « deux cadres » quand il n’y en a qu’un',
    !/both frames/.test(t('tx-chart-foot')), t('tx-chart-foot'));
}

// ══════════════════════════════════════════════════════════════════════════
console.log(`\n${ran - failures}/${ran} vérifications passées`);
if (failures) {
  console.error(`${failures} échec(s)`);
  process.exit(1);
}
