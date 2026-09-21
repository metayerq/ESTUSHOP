/* ═══════════════════════════════════════════════════════════════════════════════
   /transactions — « l'affluence tient-elle ? »

   SIMPLIFICATION, 21/09/2026. La page défendait sa méthode à chaque étape : 744 mots
   de prose lus sans rien déplier, dont 426 en notes de bas de page, huit sections, une
   table de données brutes et deux graphiques. C'était juste quand les chiffres étaient
   neufs et qu'il fallait prouver qu'ils ne mentaient pas ; ça ne l'est plus quand on
   les lit toutes les semaines. Une page qu'il faut traverser pour trouver son nombre
   est une page qu'on n'ouvre plus.

   ⚠️ ET LA SIMPLIFICATION N'EST PAS UN RACCOURCISSEMENT DES AVERTISSEMENTS. Effacer une
   mise en garde sans effacer le chiffre qu'elle protège rendrait la page plus courte ET
   plus fausse. Ce qui est parti, ce sont les CHIFFRES qui avaient besoin d'un paragraphe
   pour être honnêtes — les quatre cellules KPI, la table des fenêtres, la part
   multi-lignes, et surtout le graphique du CA par personne, qui portait à lui seul la
   moitié des réserves de la page. Les limites qui restent vraies sont TOUJOURS ÉCRITES,
   dans un bloc replié : fermé, on sait qu'il existe et on l'ouvre le jour où un chiffre
   surprend — c'est exactement ce jour-là qu'il sert.

   ⚠️ DEUX CHOSES ONT ÉTÉ RETIRÉES À TORT, PUIS REMISES. La RAISON affichée quand le
   chiffre manque : sans elle un « — » reste sans explication, au moment précis où l'on
   en a besoin. Et le SEUIL DU VERDICT : « tient » est un jugement à ±10 %, pas une
   mesure, et le taire donnerait au mot l'autorité d'un fait.

   ─── LE RÉCIT QUE CETTE PAGE PORTE ──────────────────────────────────────────
   La fréquentation TIENT — 26 à 28 tickets par jour ouvré sur les trois dernières
   fenêtres. Ce qui bouge est ailleurs : le CA PAR PERSONNE s'érode, de 7,18 €
   (3–9 juil.) à 6,45 € (31 juil.–6 août). C'est le signal le plus utile de la page,
   et il tient maintenant en UNE LIGNE sous la réponse — avec sa provenance collée au
   chiffre, parce qu'une provenance qui vit en bas de page est une provenance qu'on
   ne lit pas. Un silence, lui, se lirait comme « compté ».

   ─── TROIS RÈGLES TENUES D'UN BOUT À L'AUTRE ────────────────────────────────
   1. AUCUN ZÉRO FABRIQUÉ. Les jours fermés sont absents de `days` — ce ne sont pas
      des journées à zéro ticket. Un champ `null` veut dire « non mesuré », jamais
      « nul » : il s'écrit « — » ET il traîne sa raison avec lui.
   2. AUCUNE TENDANCE. Pas de régression, pas de moyenne mobile, pas de projection,
      pas de lissage. ~27 jours ouvrés. Ce que la page trace, ce sont des MÉDIANES
      DE FENÊTRE EN ESCALIER : chaque palier dit « voilà la journée typique de ces
      7 jours », rien de plus. Les deux seules comparaisons faites sont des
      comparaisons de POINTS NOMMÉS (telle fenêtre contre telle fenêtre, chacune
      avec son n), pas des pentes.
   3. PAS DE ROUGE. Rien ici n'est un solde. Une affluence qui baisse est une
      mesure, pas une perte. Vert = la mesure mise en avant, gris = le reste.

   ─── PURETÉ ────────────────────────────────────────────────────────────────
   Tout ce qui est au-dessus de la barre « RENDU » est PUR : aucun accès au DOM,
   aucune horloge, aucun fetch. tests/test_tx_page.js lit ces fonctions DANS CE
   FICHIER par regex et les exécute — il n'en recopie aucune.
   ═══════════════════════════════════════════════════════════════════════════════ */

let chartFoot = null;    // le graphique d'affluence — le seul de la page
let lastPayload = null;  // dernier payload servi, pour re-dessiner au changement de thème

// Au-delà de ce seuil, la page cesse de dire « ça tient ». C'est un JUGEMENT, pas
// une mesure — il est donc AFFICHÉ à l'écran à côté du verdict, pour que le lecteur
// puisse le contester. Un seuil caché transformerait une convention en constat.
const HOLD_PCT = 10;

// ── Format ────────────────────────────────────────────────────────────────────
// Un null n'est pas un zéro : il devient « — », et l'appelant lui colle une raison.

function fmtTx(v) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  return (Math.round(v * 10) / 10).toString();
}

function fmtEur(v) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  return '€' + v.toFixed(2);
}

function fmtPct(v) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  return (Math.round(v * 10) / 10).toFixed(1) + ' %';
}

function fmtDay(iso) {
  if (!iso || typeof iso !== 'string') return '';
  const d = new Date(iso + 'T12:00:00');
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function fmtLongDay(iso) {
  if (!iso || typeof iso !== 'string') return '';
  const d = new Date(iso + 'T12:00:00');
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function fmtRange(from, to) {
  if (!from || !to) return '';
  return fmtDay(from) + ' – ' + fmtDay(to);
}

function fmtHour(h) {
  if (typeof h !== 'number' || !isFinite(h)) return '—';
  return (h < 10 ? '0' : '') + Math.round(h) + 'h';
}

// ── Raisons ───────────────────────────────────────────────────────────────────
// L'API envoie un CODE. On l'écrit en clair quand on le connaît, et on affiche le
// code brut sinon : un code inconnu reste plus honnête qu'un « — » muet, et il
// signale que l'API a appris un cas que la page ignore encore.
//
// ⚠️ LE SERVEUR ÉMET DES CODES, PAS DE LA PROSE — et c'est ici que vit la formulation.
// Première intégration : l'endpoint renvoyait « 2 jours pleins seulement » en toutes
// lettres, qui s'affichait tel quel dans une page anglaise, faute de correspondance
// dans cette table. Le contrat que j'avais écrit donnait l'exemple en français : la
// faute est au contrat, pas aux deux implémentations qui l'ont suivi.
//
// Aucun libellé ne cite le SEUIL de jours pleins : il vit côté serveur et peut y
// changer sans que la page le sache. Écrire « moins de 6 jours » ici, c'est publier
// une constante qu'on ne mesure pas.
// Plusieurs causes peuvent se cumuler : elles arrivent jointes par « + ».
function reasonLabel(code) {
  if (!code) return null;
  if (String(code).includes('+')) {
    return String(code).split('+').map(reasonLabel).filter(Boolean).join(' · ');
  }
  const MAP = {
    'truncated':             'window truncated — start of the analysis period',
    'no-days':               'no open day in this window',
    'too-few-days':          'too few full open days in this window for a median',
    'insufficient':          'too few full open days in this window for a median',
    'no-reliable-window':    'no 7-day window has enough full open days yet',
    'latest-window-skipped': 'the most recent window was skipped — too few open days',
    'windows-skipped':       'thin windows in between were skipped, so the two compared windows are not adjacent',
    'no-prev-window':        'no earlier reliable window to compare against',
    'no-previous':           'no earlier reliable window to compare against',
    'prev-unreliable':       'the earlier window is too thin to compare against',
    'prev-zero':             'the earlier window had no ticket — a ratio would be meaningless',
    'partial-window':        'this window is still running',
    'no-data':               'no day recorded yet',
    'not-measured':          'not measured — the API did not report this figure',
    'too-few-measured-days': 'too few days carry a recorded ticket time',
    'multi-not-measured':    'multi-line share not recorded for every day in this window',
    'no-covers':             'people were not estimated over this window',
  };
  return MAP[code] || String(code);
}

// Cumule deux codes sans en perdre un ni le répéter. Le serveur utilise déjà « + » ;
// la page doit pouvoir y ajouter le sien quand elle constate quelque chose de plus.
function joinReasons(a, b) {
  const parts = [];
  [a, b].forEach(function (c) {
    if (!c) return;
    String(c).split('+').forEach(function (x) {
      if (x && parts.indexOf(x) === -1) parts.push(x);
    });
  });
  return parts.length ? parts.join('+') : null;
}

// ── Écart entre deux mesures ──────────────────────────────────────────────────
// Un écart n'existe que si les DEUX termes sont mesurés. Sans terme de référence
// il n'y a pas « 0 % » (qui dirait « stable ») ni « −100 % » (qui dirait
// « effondrement ») : il y a une RAISON.

function deltaModel(cur, prev) {
  const out = { ok: false, pct: null, text: null, dir: 'none', reason: null };
  if (typeof cur !== 'number' || !isFinite(cur)) {
    out.reason = 'not-measured';
    return out;
  }
  if (typeof prev !== 'number' || !isFinite(prev)) {
    out.reason = 'no-prev-window';
    return out;
  }
  if (prev === 0) {
    out.reason = 'prev-zero';
    return out;
  }
  const p = Math.round((cur - prev) / Math.abs(prev) * 100);
  out.ok = true;
  out.pct = p;
  if (p === 0) {
    out.text = 'flat';
    out.dir = 'flat';
  } else {
    out.text = (p > 0 ? '+' : '−') + Math.abs(p) + ' %';
    out.dir = p > 0 ? 'up' : 'down';
  }
  return out;
}

// ── Les fenêtres fiables, de la plus ancienne à la plus récente ───────────────
// Une fenêtre non fiable n'entre dans AUCUNE comparaison ni sparkline : sa médiane
// porte trop peu de jours pleins pour se lire comme une journée typique, et elle
// serait indiscernable des autres une fois dessinée.

function reliableWindows(windows) {
  const src = Array.isArray(windows) ? windows : [];
  const out = [];
  for (let i = 0; i < src.length; i++) {
    const w = src[i];
    if (!w || typeof w !== 'object') continue;
    if (w.reliable === false) continue;
    if (!w.to) continue;
    out.push(w);
  }
  out.sort(function (a, b) { return String(a.to).localeCompare(String(b.to)); });
  return out;
}

// ── La PAIRE de fenêtres dont parle toute la page ─────────────────────────────
// Les quatre cellules KPI et le bandeau décrivent LA MÊME paire de fenêtres. Si
// chaque cellule choisissait la sienne, quatre chiffres côte à côte parleraient de
// quatre périodes différentes sans que rien ne le dise.
//
// L'autorité est le serveur : `headline.from/to` et `headline.prev_from/prev_to`
// désignent les deux fenêtres retenues. On les RETROUVE dans `windows` plutôt que
// de refaire le choix — refaire le choix, c'est risquer d'en faire un autre.

function pickWindows(payload) {
  const p = (payload && typeof payload === 'object') ? payload : {};
  const wins = Array.isArray(p.windows) ? p.windows : [];
  const h = (p.headline && typeof p.headline === 'object') ? p.headline : {};
  const find = function (from, to) {
    if (!from || !to) return null;
    for (let i = 0; i < wins.length; i++) {
      const w = wins[i];
      if (w && w.from === from && w.to === to) return w;
    }
    return null;
  };
  let cur = find(h.from, h.to);
  let prev = find(h.prev_from, h.prev_to);
  let reason = h.reason || null;
  let fromHeadline = !!cur;

  if (!cur) {
    // Repli : le headline est muet ou pointe hors de `windows`. On prend la
    // dernière fenêtre fiable et celle d'avant, et on DIT que c'est un repli.
    const rel = reliableWindows(wins);
    cur = rel.length ? rel[rel.length - 1] : null;
    prev = rel.length > 1 ? rel[rel.length - 2] : null;
    if (!cur) reason = joinReasons(reason, 'no-reliable-window');
  }
  if (cur && !prev) reason = joinReasons(reason, 'no-prev-window');
  if (prev && prev.reliable === false) {
    prev = null;
    reason = joinReasons(reason, 'prev-unreliable');
  }
  return { cur: cur, prev: prev, reason: reason, fromHeadline: fromHeadline };
}

// ── Le plafond des personnes estimées ─────────────────────────────────────────
// `covers_capped` compte les tickets qui ont TOUCHÉ le plafond de 8 personnes. Un
// plafond atteint veut dire que la fenêtre SOUS-COMPTE ses personnes — et donc que
// son CA/personne est SUR-estimé. Ça ne se murmure pas en note de bas de page :
// c'est une borne qui déforme le chiffre affiché juste au-dessus.

// ── D'où viennent les personnes : comptées ou devinées ────────────────────────
// Le POS demande le nombre de personnes à l'ouverture d'une table et l'écrit sur la
// note du document ; le reste — le comptoir, la caisse principale — est ESTIMÉ en
// comptant les boissons. Le total mêle donc les deux.
//
// ⚠️ SANS CETTE PHRASE, UN CHIFFRE À 90 % DEVINÉ SE LIT COMME UN COMPTAGE. C'est
// précisément le malentendu que la remontée du POS était censée dissiper : le taire
// annulerait tout le bénéfice. `null` tant que rien n'est classé — pas « 0 % mesuré »,
// qui affirmerait qu'on a regardé.


function cappedModel(windows) {
  const src = Array.isArray(windows) ? windows : [];
  let total = 0, touched = 0;
  for (let i = 0; i < src.length; i++) {
    const w = src[i];
    if (!w || typeof w.covers_capped !== 'number' || !isFinite(w.covers_capped)) continue;
    if (w.covers_capped > 0) { total += w.covers_capped; touched++; }
  }
  return {
    any: total > 0,
    total: total,
    windows: touched,
    text: total > 0
      ? ('the 8-person ceiling was reached ' + total + '× across ' + touched
         + ' window' + (touched > 1 ? 's' : '')
         + ' — people are under-counted there, so revenue per person is over-stated')
      : null,
  };
}

// ── 1. Bandeau-réponse ────────────────────────────────────────────────────────
// « Is footfall holding? » répondu en une phrase, chiffres à l'appui, avec les n.
//
// Deux clauses, et seulement deux :
//   a) l'affluence — dernière fenêtre fiable contre la précédente, chacune avec son
//      n. « 26 sur 5 jours » et « 28 sur 5 jours » ne pèsent pas pareil que « 26 sur
//      5 » contre « 28 sur 2 », et le lecteur doit pouvoir en juger lui-même.
//   b) l'érosion — le CA/personne de la DERNIÈRE fenêtre fiable contre celui de la
//      PREMIÈRE. Deux points nommés, datés, avec leurs n. Ce n'est pas une pente :
//      rien n'est ajusté, rien n'est extrapolé, et les fenêtres du milieu sont
//      visibles juste en dessous dans la sparkline et le graphique.

function answerModel(payload) {
  const p = (payload && typeof payload === 'object') ? payload : {};
  const h = (p.headline && typeof p.headline === 'object') ? p.headline : {};
  const rel = reliableWindows(p.windows);
  const pick = pickWindows(p);

  const out = {
    ok: false,
    verdict: 'unknown',
    threshold: HOLD_PCT,
    lead: 'Not enough measured windows to answer yet.',
    value: '—', n: null, range: '',
    prevValue: '—', prevN: null, prevRange: '',
    delta: { ok: false, text: null, dir: 'none', reason: null },
    covers: null,
    windowsUsed: rel.length,
    reason: joinReasons(h.reason, pick.reason),
    // Une réserve qui vaut MÊME QUAND LE CHIFFRE EXISTE. « latest-window-skipped »
    // en est le cas type : l'écart se calcule très bien, mais il ne porte pas sur
    // les sept derniers jours — et personne ne doit décider quoi que ce soit sans
    // le savoir. Elle est donc séparée de la note « pas de comparaison ».
    caveat: null,
    note: null,
  };
  out.caveat = reasonLabel(out.reason);

  const tx = (typeof h.tx_median === 'number' && isFinite(h.tx_median))
    ? h.tx_median
    : (pick.cur && typeof pick.cur.tx_median === 'number' ? pick.cur.tx_median : null);

  if (tx == null) {
    out.note = reasonLabel(out.reason || 'no-reliable-window');
    return out;
  }

  out.ok = true;
  out.value = fmtTx(tx);
  out.n = (typeof h.n === 'number') ? h.n
        : (pick.cur && typeof pick.cur.full_days === 'number' ? pick.cur.full_days : null);
  out.range = fmtRange(h.from || (pick.cur && pick.cur.from), h.to || (pick.cur && pick.cur.to));

  // La fenêtre précédente n'existe qu'avec un n : un « n » absent ou nul, c'est une
  // fenêtre vide, et on ne compare pas contre du vide.
  const prevOk = (typeof h.prev_tx_median === 'number' && isFinite(h.prev_tx_median))
              && (typeof h.prev_n === 'number' && h.prev_n > 0);
  if (prevOk) {
    out.prevValue = fmtTx(h.prev_tx_median);
    out.prevN = h.prev_n;
    out.prevRange = fmtRange(h.prev_from, h.prev_to);
    // Le serveur a déjà calculé l'écart ; on ne le recalcule pas pour ne pas
    // publier deux vérités. S'il est absent, il n'y a pas d'écart, pas un zéro.
    if (typeof h.delta_pct === 'number' && isFinite(h.delta_pct)) {
      const q = Math.round(h.delta_pct);
      out.delta = {
        ok: true, pct: q,
        text: q === 0 ? 'flat' : (q > 0 ? '+' : '−') + Math.abs(q) + ' %',
        dir: q === 0 ? 'flat' : (q > 0 ? 'up' : 'down'),
        reason: null,
      };
    } else {
      out.delta = { ok: false, text: null, dir: 'none', reason: h.reason || 'no-prev-window' };
    }
  } else {
    out.delta = { ok: false, text: null, dir: 'none', reason: h.reason || 'no-prev-window' };
  }

  // Personnes estimées de la fenêtre courante — le mot « estimated » n'est jamais
  // omis, et jamais remplacé par « customers ».
  if (pick.cur && typeof pick.cur.covers_median === 'number' && isFinite(pick.cur.covers_median)) {
    out.covers = { value: fmtTx(pick.cur.covers_median), raw: pick.cur.covers_median };
  }

  if (out.delta.ok) {
    if (Math.abs(out.delta.pct) <= HOLD_PCT) {
      out.verdict = 'holding';
      out.lead = 'Footfall is holding.';
    } else if (out.delta.pct > 0) {
      out.verdict = 'up';
      out.lead = 'Footfall is up on the previous window.';
    } else {
      out.verdict = 'down';
      out.lead = 'Footfall is down on the previous window.';
    }
  } else {
    out.verdict = 'unknown';
    out.lead = 'Footfall cannot be compared to an earlier window.';
    out.note = reasonLabel(out.delta.reason || 'no-prev-window');
  }

  return out;
}

// ── 2. Cellules KPI ───────────────────────────────────────────────────────────
// Quatre mesures de la MÊME paire de fenêtres. Chacune : sa valeur, son écart en
// pastille, et une sparkline sur TOUTES les fenêtres fiables — la sparkline
// n'est pas une tendance, c'est la suite des paliers déjà tracés plus bas.
//
// ⚠️ `ca_per_cover` n'est PAS `ca_median / covers_median`. C'est un ratio calculé
// sur la fenêtre entière côté serveur. Diviser deux médianes ne donnerait la médiane
// de rien, et le lecteur qui divise les deux colonnes du tableau ne retombera pas
// sur ce chiffre — la page le lui dit plutôt que de le laisser croire à une erreur.

// ⚠️ LES RÉSERVES SONT ÉCRITES, PAS SURVOLÉES. La première version posait ces
// phrases dans un `data-tip`, comme les cellules du dashboard. Mais le tooltip
// partagé `[data-tip]` est implémenté dans static/dashboard.js, que cette page NE
// CHARGE PAS : les quatre réserves n'auraient existé nulle part, et style.css aurait
// quand même mis un curseur « help » promettant une explication qui ne venait
// jamais. Elles sont donc du texte visible. C'est de toute façon la bonne place :
// « estimé, plafond 8 » n'est pas un détail à découvrir au survol.


// ── Sparkline ─────────────────────────────────────────────────────────────────
// Rendue en SVG pur, sans Chart.js : quatre canvas de 90×26 px pour quatre suites
// de cinq points coûteraient plus cher que la page entière.
//
// Trois refus explicites :
//   · une série de moins de deux points mesurés ne donne pas de ligne (un point
//     n'a pas de direction, et le dessiner en tracerait une),
//   · un trou (fenêtre sans mesure) COUPE la ligne — pas d'interpolation par-dessus
//     une absence,
//   · une série plate se dessine au MILIEU de la boîte, pas collée en bas : min=max
//     n'est pas « zéro », et coller la ligne au plancher le laisserait croire.

function sparkline(values, w, h) {
  const src = Array.isArray(values) ? values : [];
  const width = (typeof w === 'number' && w > 0) ? w : 92;
  const height = (typeof h === 'number' && h > 0) ? h : 26;
  const out = {
    ok: false, w: width, h: height, segments: [], last: null,
    min: null, max: null, n: 0, gaps: 0, flat: false,
  };
  const nums = [];
  for (let i = 0; i < src.length; i++) {
    const v = src[i];
    if (typeof v === 'number' && isFinite(v)) nums.push(v);
    else out.gaps++;
  }
  out.n = nums.length;
  if (nums.length < 2) return out;

  let min = nums[0], max = nums[0];
  for (let i = 1; i < nums.length; i++) {
    if (nums[i] < min) min = nums[i];
    if (nums[i] > max) max = nums[i];
  }
  out.min = min; out.max = max;
  out.flat = (max === min);

  const pad = 3;
  const span = max - min;
  const px = function (i) {
    if (src.length < 2) return width / 2;
    return Math.round((pad + i * (width - 2 * pad) / (src.length - 1)) * 10) / 10;
  };
  const py = function (v) {
    if (span <= 0) return Math.round(height / 2 * 10) / 10;
    return Math.round(((height - pad) - (v - min) / span * (height - 2 * pad)) * 10) / 10;
  };

  let seg = [];
  let last = null;
  for (let i = 0; i < src.length; i++) {
    const v = src[i];
    if (typeof v === 'number' && isFinite(v)) {
      const pt = { x: px(i), y: py(v) };
      seg.push(pt);
      last = pt;
    } else if (seg.length) {
      out.segments.push(seg);
      seg = [];
    }
  }
  if (seg.length) out.segments.push(seg);
  // Un segment d'un seul point n'est pas une ligne — mais c'est une MESURE, et une
  // mesure ne disparaît pas du dessin. Il est isolé ici pour être tracé en point.
  out.isolated = out.segments.filter(function (s) { return s.length === 1; })
                             .map(function (s) { return s[0]; });
  out.last = last;
  out.ok = out.segments.some(function (s) { return s.length >= 2; });
  return out;
}

// Le SVG est construit ici (fonction pure, testable) et non dans le rendu : c'est
// le seul endroit où la géométrie et le balisage doivent rester d'accord.
function sparkSvg(values, w, h) {
  const m = sparkline(values, w, h);
  if (!m.ok) return '';
  const polys = m.segments
    .filter(function (s) { return s.length >= 2; })
    .map(function (s) {
      return '<polyline fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round" points="'
        + s.map(function (pt) { return pt.x + ',' + pt.y; }).join(' ') + '"/>';
    }).join('');
  // Les points isolés (une fenêtre mesurée entre deux fenêtres qui ne le sont pas)
  // sont tracés en creux : ils existent, et on voit qu'aucune ligne ne les rejoint.
  const lone = (m.isolated || []).map(function (pt) {
    return '<circle cx="' + pt.x + '" cy="' + pt.y + '" r="1.8" fill="none" '
      + 'stroke="currentColor" stroke-width="1.2"/>';
  }).join('');
  const dot = m.last
    ? '<circle cx="' + m.last.x + '" cy="' + m.last.y + '" r="2" fill="currentColor"/>'
    : '';
  return '<svg class="tx-spark" viewBox="0 0 ' + m.w + ' ' + m.h + '" width="' + m.w
    + '" height="' + m.h + '" aria-hidden="true" focusable="false">'
    + polys + lone + dot + '</svg>';
}

// ── 3a. Graphique du haut — l'affluence ───────────────────────────────────────
// Une barre par jour PRÉSENT dans le payload. Un jour fermé n'a pas de barre : il
// n'a pas d'existence sur cet axe. Un jour ouvert à 0 ticket, lui, en aurait une —
// c'est une mesure, pas une absence.
//
// L'escalier : chaque jour reçoit la médiane de la fenêtre qui le contient. Une
// fenêtre non fiable ne donne PAS de palier (null ⇒ trou dans la ligne) plutôt
// qu'un palier fragile qu'on ne distinguerait plus des autres.
//
// yMax = le maximum réel. Écrêter tasserait le reste de la série pour faire joli,
// et rien à l'écran ne dirait que le sommet a été coupé.

function dailyModel(days, windows) {
  const src = Array.isArray(days) ? days : [];
  const bars = [];
  for (let i = 0; i < src.length; i++) {
    const d = src[i];
    if (!d || typeof d.day !== 'string') continue;
    if (typeof d.nb !== 'number' || !isFinite(d.nb)) continue;   // pas de nb ⇒ pas de barre
    bars.push({
      day: d.day,
      nb: d.nb,
      covers: (typeof d.covers === 'number' && isFinite(d.covers)) ? d.covers : null,
      ca_ttc: (typeof d.ca_ttc === 'number' && isFinite(d.ca_ttc)) ? d.ca_ttc : null,
      partial: d.partial === true,
      label: fmtDay(d.day),
    });
  }
  bars.sort(function (a, b) { return a.day.localeCompare(b.day); });
  return {
    n: bars.length,
    labels: bars.map(function (b) { return b.label; }),
    bars: bars,
    tickets: bars.map(function (b) { return b.nb; }),
    covers: bars.map(function (b) { return b.covers; }),
    steps: windowStep(bars, windows, 'tx_median'),
    coverSteps: windowStep(bars, windows, 'covers_median'),
    yMax: bars.reduce(function (m, b) { return b.nb > m ? b.nb : m; }, 0),
    clipped: false,          // aucune troncature : si ça changeait, il faudrait l'écrire à l'écran
    partialDays: bars.filter(function (b) { return b.partial; }).map(function (b) { return b.label; }),
  };
}

// Palier de fenêtre pour chaque jour. Les fenêtres peuvent se chevaucher ; la plus
// récente qui contient le jour gagne. Une fenêtre non fiable ne produit rien.
function windowStep(bars, windows, field) {
  const wins = Array.isArray(windows) ? windows : [];
  return bars.map(function (b) {
    let best = null;
    for (let j = 0; j < wins.length; j++) {
      const w = wins[j];
      if (!w || !w.from || !w.to) continue;
      if (b.day < w.from || b.day > w.to) continue;
      if (w.reliable === false) continue;
      const v = w[field];
      if (typeof v !== 'number' || !isFinite(v)) continue;
      if (!best || w.to > best.to) best = w;
    }
    return best ? best[field] : null;
  });
}

// ── 3b. Graphique du bas — le CA par personne estimée ─────────────────────────
// MÊMES étiquettes que le graphique du haut, dans le même ordre : c'est ce qui
// autorise à les lire l'un au-dessus de l'autre. Si la série des personnes n'existe
// pas, le cadre du bas ne se dessine pas — il affiche pourquoi.
//
// Le nuage de points journaliers est là pour que le palier ne se prenne pas pour la
// vérité : on voit la dispersion dont la médiane est tirée.


// ── 4. Répartition horaire ────────────────────────────────────────────────────
// `hourly.reason` non null ⇒ ON NE DESSINE PAS. Une répartition mesurée sur trois
// jours ressemble exactement à une répartition mesurée sur trente, et rien dans les
// barres ne dirait laquelle on regarde. Le message remplace le graphique.
//
// Les pics sont marqués par une règle ÉNONCÉE et affichée : L'HEURE LA PLUS
// CHARGÉE DE CHAQUE BLOC. Pas de détection de « pic » maison qui déciderait toute
// seule de ce qui compte.
//
// ⚠️ La règle naïve « les deux heures les plus chargées » a été essayée et JETÉE :
// sur les données réelles elle sort 11h (166 tickets) et 9h (160), deux heures du
// même bloc du matin, et laisse le pic du soir (20h, 104) sans marque. Elle
// dessinerait donc UNE clientèle là où il y en a deux — exactement le contraire de
// ce que la ventilation par bloc existe pour montrer. Un maximum par bloc ne
// « trouve » rien : il pointe le sommet d'un découpage déjà publié par l'API.

function hourlyModel(hourly) {
  const h = (hourly && typeof hourly === 'object') ? hourly : null;
  const out = {
    ok: false, reason: null, note: null,
    daysMeasured: (h && typeof h.days_measured === 'number') ? h.days_measured : null,
    bars: [], blocks: [], peaks: [], total: 0, maxTickets: 0,
    peakRule: 'the busiest hour inside each block published by the API',
  };
  if (!h) {
    out.reason = 'not-measured';
    out.note = reasonLabel(out.reason);
    return out;
  }
  if (h.reason) {
    out.reason = h.reason;
    out.note = reasonLabel(h.reason);
    return out;
  }
  const src = Array.isArray(h.by_hour) ? h.by_hour : [];
  const rows = [];
  for (let i = 0; i < src.length; i++) {
    const b = src[i];
    if (!b || typeof b.hour !== 'number') continue;
    if (typeof b.tickets !== 'number' || !isFinite(b.tickets)) continue;
    rows.push(b);
  }
  if (!rows.length) {
    out.reason = 'not-measured';
    out.note = reasonLabel(out.reason);
    return out;
  }
  rows.sort(function (a, b) { return a.hour - b.hour; });
  let max = 0, total = 0;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].tickets > max) max = rows[i].tickets;
    total += rows[i].tickets;
  }
  // Le sommet de CHAQUE bloc publié par l'API. Égalité tranchée par l'heure la plus
  // tôt, pour que le résultat ne dépende pas de l'ordre d'arrivée des lignes.
  const blocksSrc = Array.isArray(h.blocks) ? h.blocks : [];
  const peaks = [];
  const bornes = blocksSrc.length
    ? blocksSrc
    : [{ from_hour: 0, to_hour: 23 }];   // sans découpage, un seul sommet : celui de la journée
  for (let i = 0; i < bornes.length; i++) {
    const b = bornes[i];
    if (!b || typeof b.from_hour !== 'number' || typeof b.to_hour !== 'number') continue;
    let top = null;
    for (let j = 0; j < rows.length; j++) {
      const r = rows[j];
      if (r.hour < b.from_hour || r.hour > b.to_hour) continue;
      if (!top || r.tickets > top.tickets) top = r;
    }
    if (top && peaks.indexOf(top.hour) === -1) peaks.push(top.hour);
  }

  out.ok = true;
  out.total = total;
  out.maxTickets = max;
  out.peaks = peaks.slice().sort(function (a, b) { return a - b; });
  out.bars = rows.map(function (r) {
    return {
      hour: r.hour,
      label: fmtHour(r.hour),
      tickets: r.tickets,
      pct: (typeof r.pct === 'number' && isFinite(r.pct)) ? r.pct : null,
      perDay: (typeof r.per_day === 'number' && isFinite(r.per_day)) ? r.per_day : null,
      height: max > 0 ? Math.round(r.tickets / max * 100) : 0,
      peak: peaks.indexOf(r.hour) !== -1,
    };
  });

  const LABELS = { morning: 'Morning', afternoon: 'Afternoon', evening: 'Evening' };
  const blocks = Array.isArray(h.blocks) ? h.blocks : [];
  out.blocks = blocks.map(function (b) {
    const pct = (b && typeof b.pct === 'number' && isFinite(b.pct)) ? b.pct : null;
    return {
      key: (b && b.block) || '',
      label: (b && LABELS[b.block]) || (b && b.block) || '—',
      range: (b && typeof b.from_hour === 'number' && typeof b.to_hour === 'number')
        ? fmtHour(b.from_hour) + '–' + fmtHour(b.to_hour) : '',
      tickets: (b && typeof b.tickets === 'number') ? b.tickets : null,
      pct: pct,
      pctText: fmtPct(pct),
      perDay: (b && typeof b.per_day === 'number' && isFinite(b.per_day)) ? b.per_day : null,
      width: pct == null ? 0 : Math.max(0, Math.min(100, Math.round(pct))),
    };
  });
  return out;
}

// ── 5. Fenêtres de 7 jours ────────────────────────────────────────────────────
// Une fenêtre non fiable garde son n (l'information utile : « il n'y a que 3 jours
// pleins ici ») mais perd ses médianes. Publier une « médiane » de 3 jours à côté
// de médianes de 5 ou 6 la ferait lire comme une journée typique — elle n'en est
// pas une, et rien dans le nombre lui-même ne le dirait.


// ── 6. Médiane par jour de semaine ────────────────────────────────────────────
// n par jour toujours affiché : une médiane sur 2 lundis n'est pas une médiane sur
// 9. Un jour sans mesure s'écrit « — », pas 0 — un mardi jamais ouvert n'est pas
// un mardi à zéro ticket.

function weekdayRows(weekday) {
  const NOMS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const src = Array.isArray(weekday) ? weekday : [];
  const par = {};
  for (let i = 0; i < src.length; i++) {
    const w = src[i];
    if (!w || typeof w.weekday !== 'number') continue;
    par[w.weekday] = w;
  }
  const rows = NOMS.map(function (nom, idx) {
    const w = par[idx];
    const n = (w && typeof w.n === 'number') ? w.n : 0;
    const has = !!w && n > 0 && typeof w.tx_median === 'number' && isFinite(w.tx_median);
    return {
      weekday: idx,
      label: (w && w.label) || nom,
      n: n,
      tx: has ? fmtTx(w.tx_median) : '—',
      value: has ? w.tx_median : null,
      width: 0,
      note: has ? null : (n === 0 ? 'never open on this day yet' : 'no median for this day'),
    };
  });
  let max = 0;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].value != null && rows[i].value > max) max = rows[i].value;
  }
  for (let i = 0; i < rows.length; i++) {
    rows[i].width = (rows[i].value != null && max > 0)
      ? Math.round(rows[i].value / max * 100) : 0;
  }
  return rows;
}

// ── 7. Part des tickets multi-lignes ──────────────────────────────────────────
// Lue sur la dernière fenêtre FIABLE. Pas de moyenne de toutes les fenêtres : elles
// peuvent se chevaucher, et la moyenne compterait plusieurs fois les mêmes jours.


// ── 8. Ce que la page couvre, et ce qu'elle exclut ────────────────────────────
// JUIN EST EXCLU, ET ÇA DOIT SE VOIR. Le café a ouvert le 27 mai ; l'analyse
// démarre le 1er juillet. Entre les deux, il y a le rodage et des commandes de
// groupe montant à 55 boissons — des journées qui écraseraient toutes les médianes
// de la page. L'exclusion est légitime ; la CACHER ne l'est pas. Elle vit donc dans
// un bandeau permanent en haut de page, pas seulement dans l'encart du bas.


// ═══════════════════════════════════════════════════════════════════════════════
// RENDU (DOM) — au-dessous, plus rien n'est pur.
// ═══════════════════════════════════════════════════════════════════════════════

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function el(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Hachures du jour partiel. Pas de couleur en dur : la trame est peinte avec le
// token passé en argument.
function hatchPattern(color) {
  const c = document.createElement('canvas');
  c.width = 6; c.height = 6;
  const g = c.getContext('2d');
  g.strokeStyle = color;
  g.lineWidth = 1.6;
  g.beginPath();
  g.moveTo(-1, 7); g.lineTo(7, -1);
  g.moveTo(2, 8); g.lineTo(8, 2);
  g.stroke();
  const p = g.createPattern(c, 'repeat');
  return p || color;   // navigateur sans createPattern : couleur pleine plutôt que rien
}

// Pastille d'écart. AUCUN ROUGE : une baisse d'affluence est une mesure, pas une
// perte. « up » est vert, tout le reste est neutre — la direction est portée par la
// flèche et le signe, pas par une couleur d'alarme.
function chipHtml(d) {
  if (!d || !d.ok || !d.text) return '';
  const arrow = d.dir === 'up' ? '▲ ' : d.dir === 'down' ? '▼ ' : '= ';
  return '<span class="tx-chip tx-chip-' + d.dir + '">' + arrow + esc(d.text) + '</span>';
}


function renderAnswer(d) {
  const m = answerModel(d);
  el('hl-lead').textContent = m.lead;
  el('hl-value').textContent = m.value;
  el('hl-delta').innerHTML = chipHtml(m.delta);

  // ⚠️ LES DEUX FENÊTRES SONT NOMMÉES ICI, PUISQUE LA LIGNE « fenêtre précédente » A DISPARU.
  // Un écart sans ses deux bornes est un pourcentage qui flotte : on ne sait plus ce qu'il
  // compare, et surtout pas sur combien de jours.
  el('hl-n').innerHTML = m.ok
    ? 'median of <b>' + (m.n == null ? '?' : m.n) + '</b> full open days'
      + (m.range ? ' · ' + esc(m.range) : '')
      + (m.prevValue !== '—'
        ? ' <span class="tx-dim">· against <b>' + esc(m.prevValue) + '</b> over '
          + (m.prevN == null ? '?' : m.prevN) + ' full days'
          + (m.prevRange ? ', ' + esc(m.prevRange) : '') + '</span>'
        : '')
    : '';

  // ⚠️ « TIENT » EST UN JUGEMENT, PAS UNE MESURE. Le seuil doit rester écrit : sans lui, le mot
  // prend l'autorité d'un fait, et avec cinq jours ouverts de chaque côté, une bonne journée
  // suffit à le faire basculer.
  const rule = el('hl-rule');
  rule.innerHTML = m.delta.ok
    ? '&laquo;&nbsp;holding&nbsp;&raquo; = within &plusmn;' + m.threshold
      + '&nbsp;% of the previous window — a convention set on this page, not a measurement.'
    : '';

  const note = el('hl-note');
  const reason = m.note || (m.delta.ok ? null : reasonLabel(m.delta.reason));
  note.textContent = reason ? 'no comparison — ' + reason : '';
  note.style.display = reason ? '' : 'none';

  // La réserve s'affiche même quand l'écart existe. Quand il n'existe pas, la note
  // ci-dessus porte déjà la même raison : on ne l'écrit pas deux fois.
  const caveat = el('hl-caveat');
  const showCaveat = m.caveat && m.delta.ok;
  caveat.textContent = showCaveat ? 'read with care — ' + m.caveat : '';
  caveat.style.display = showCaveat ? '' : 'none';
}


// Les deux graphiques partagent la MÊME largeur d'axe Y, imposée : sans ça, un axe
// en « 80 » et un axe en « €7.50 » ne s'alignent pas, et deux cadres décalés de
// quelques pixels ne se lisent plus l'un au-dessus de l'autre.
const AXIS_W = 54;

function commonScales(faint, border, showX) {
  return {
    y: {
      beginAtZero: true,
      afterFit: function (a) { a.width = AXIS_W; },
      ticks: { font: { size: 11 }, color: faint },
      grid: { color: border }, border: { display: false },
    },
    x: {
      ticks: {
        display: showX, font: { size: 10 }, color: faint,
        maxTicksLimit: 14, autoSkip: true, maxRotation: 0,
      },
      grid: { display: false }, border: { display: false },
    },
  };
}

function renderCharts(d) {
  const payload = d || {};
  const foot = dailyModel(payload.days, payload.windows);

  const empty = el('tx-chart-empty');
  const grid = el('tx-chart-grid');
  if (!foot.n) {
    // ⚠️ AUCUN JOUR OUVRÉ : LE CADRE DISPARAÎT. Le laisser vide à l'écran lui donnerait
    // l'air d'une mesure plate — et une mesure plate est une information, l'absence n'en
    // est pas une.
    grid.style.display = 'none';
    empty.style.display = '';
    empty.textContent = 'No open day in the analysis period — nothing to plot.';
    el('tx-chart-foot').textContent = '';
    if (chartFoot) { chartFoot.destroy(); chartFoot = null; }
    return;
  }
  grid.style.display = '';
  empty.style.display = 'none';

  const gray = cssVar('--flux-tax');
  const green = cssVar('--green');
  const faint = cssVar('--faint');
  const muted = cssVar('--muted');
  const border = cssVar('--border');
  const surface = cssVar('--bg-card');
  const hatch = hatchPattern(faint);

  // ── Haut : affluence ──
  if (chartFoot) chartFoot.destroy();
  chartFoot = new Chart(el('chart-footfall').getContext('2d'), {
    type: 'bar',
    data: {
      labels: foot.labels,
      datasets: [
        {
          type: 'bar', label: 'tickets',
          data: foot.tickets,
          backgroundColor: foot.bars.map(function (b) { return b.partial ? hatch : gray; }),
          borderColor: foot.bars.map(function (b) { return b.partial ? faint : gray; }),
          borderWidth: foot.bars.map(function (b) { return b.partial ? 1 : 0; }),
          borderRadius: 4, borderSkipped: false,
          categoryPercentage: 0.86, barPercentage: 0.9,   // le jour reste un jour, avec de l'air autour
          order: 3,
        },
        {
          type: 'line', label: 'median tickets / open day (7-day window)',
          data: foot.steps,
          stepped: 'middle',    // escalier : un palier par fenêtre, jamais une courbe
          spanGaps: false,      // fenêtre non fiable ⇒ trou visible, pas d'interpolation
          borderColor: green, borderWidth: 2,
          pointRadius: 0, fill: false, order: 1,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function (items) {
              const b = foot.bars[items[0].dataIndex];
              return b ? fmtLongDay(b.day) + (b.partial ? ' — partial day' : '') : '';
            },
            label: function (c) {
              const b = foot.bars[c.dataIndex];
              if (c.datasetIndex === 1) {
                return c.raw == null ? ' no reliable median here'
                  : ' window median: ' + fmtTx(c.raw) + ' tickets / open day';
              }
              return ' ' + b.nb + ' tickets'
                + (b.ca_ttc != null ? ' · ' + fmtEur(b.ca_ttc) : '')
                + (b.partial ? ' · partial — excluded from every median' : '');
            },
          },
        },
      },
      scales: commonScales(faint, border, true),
    },
  });

  // ⚠️ LA NOTE SOUS LE GRAPHIQUE RESTE, ET ELLE EST COURTE. Trois choses qu'aucun axe ne dit :
  // un jour fermé N'EST PAS un jour à zéro ticket, le jour en cours est hachuré parce qu'il est
  // incomplet, et le sommet est montré en entier. Les taire ferait lire des creux qui n'existent
  // pas.
  const capped = cappedModel(payload.windows);
  el('tx-chart-foot').innerHTML =
    foot.n + ' open days plotted · a closed day has no bar — '
    + '<b>it is not a zero-ticket day</b>'
    + (foot.partialDays.length
        ? ' · hatched = ' + esc(foot.partialDays.join(', '))
          + ' <b>partial, excluded from every median</b>'
        : '')
    + ' · peak ' + foot.yMax + ' tickets, shown in full (no scale clipping)'
    + (capped.any ? ' · <b>' + esc(capped.text) + '</b>' : '');
}

function renderHourly(d) {
  const m = hourlyModel(d && d.hourly);
  const box = el('tx-hours-box');
  const msg = el('tx-hours-empty');
  const meta = el('tx-hours-meta');

  meta.textContent = m.daysMeasured == null
    ? 'days measured: not reported'
    : 'measured on ' + m.daysMeasured + ' full open day' + (m.daysMeasured === 1 ? '' : 's');

  if (!m.ok) {
    box.style.display = 'none';
    msg.style.display = '';
    // On ne dessine pas une répartition qu'on ne peut pas qualifier : les barres
    // d'un échantillon de 3 jours sont indiscernables de celles de 30.
    msg.textContent = 'Hourly split not drawn — ' + (m.note || 'not measured') + '.';
    el('tx-blocks').innerHTML = '';
    return;
  }
  box.style.display = '';
  msg.style.display = 'none';

  el('tx-blocks').innerHTML = m.blocks.map(function (b) {
    return '<div class="tx-block">'
      + '<div class="tx-block-head"><span class="tx-block-name">' + esc(b.label) + '</span>'
      + '<span class="tx-mono">' + esc(b.range) + '</span></div>'
      + '<div class="tx-block-val">' + esc(b.pctText) + '</div>'
      + '<div class="progress-track"><div class="progress-fill" style="width:' + b.width + '%"></div></div>'
      + '<div class="tx-block-sub">'
      + (b.perDay == null ? '—' : fmtTx(b.perDay) + ' tickets / open day')
      + (b.tickets == null ? '' : ' · ' + b.tickets + ' tickets total')
      + '</div></div>';
  }).join('');

  el('tx-hours-bars').innerHTML = m.bars.map(function (b) {
    return '<div class="tx-hbar' + (b.peak ? ' is-peak' : '') + '">'
      + '<span class="tx-hbar-val">' + (b.peak ? b.tickets : '') + '</span>'
      + '<span class="tx-hbar-fill" style="height:' + Math.max(b.height, 2) + '%" '
      + 'title="' + esc(b.label + ' · ' + b.tickets + ' tickets · ' + fmtPct(b.pct)
        + ' · ' + fmtTx(b.perDay) + '/open day') + '"></span>'
      + '<span class="tx-hbar-hr">' + esc(b.label) + '</span>'
      + '</div>';
  }).join('');

  el('tx-hours-foot').innerHTML =
    'Highlighted = ' + esc(m.peakRule) + ' (' + m.peaks.map(fmtHour).join(', ')
    + ') — a stated rule, not a detected &laquo;&nbsp;peak&nbsp;&raquo;.'
    + ' Bars are ticket counts summed over the measured days, not revenue.'
    + ' A ticket with no recorded time is not an 00h ticket: those days are excluded entirely.';
}


function renderWeekday(d) {
  const rows = weekdayRows(d && d.weekday);
  el('tx-wd-body').innerHTML = rows.map(function (r) {
    return '<tr>'
      + '<td>' + esc(r.label) + '</td>'
      + '<td class="tx-num">' + esc(r.tx) + '</td>'
      + '<td class="tx-bar-cell"><span class="tx-bar" style="width:' + r.width + '%"></span></td>'
      + '<td class="tx-num tx-dim">' + r.n + '</td>'
      + '<td class="tx-dim">' + esc(r.note || '') + '</td>'
      + '</tr>';
  }).join('');
}


function renderAll(d) {
  lastPayload = d || {};
  renderAnswer(lastPayload);
  renderCharts(lastPayload);
  renderHourly(lastPayload);
  renderWeekday(lastPayload);
}

// ── Le découpage jour / soir ──────────────────────────────────────────────────
//
// ⚠️ UN ÉVÉNEMENT DU SOIR FAUSSE LA COMPARAISON DES JOURS. Un concert un vendredi ajoute
// quarante tickets à ce vendredi-là ; la médiane du vendredi monte, et l'on conclut que le
// vendredi se tient mieux que le jeudi. C'est l'événement qu'on mesure, pas le café.
//
// ⚠️ LE DÉCOUPAGE EST FAIT PAR LE SERVEUR, PAS ICI. Les médianes n'ont qu'UNE définition ; la
// refaire dans le navigateur pour les vues filtrées donnerait deux façons de calculer une
// journée typique, qui divergeraient au premier cas limite.
let segment = 'day';

function majSegment(d) {
  const boutons = document.querySelectorAll('.tx-segment button[data-seg]');
  for (let i = 0; i < boutons.length; i++) {
    boutons[i].setAttribute('aria-pressed', String(boutons[i].dataset.seg === segment));
  }
  // ⚠️ LES JOURS ÉCARTÉS SE DISENT. Les lignes de cache écrites avant la mesure horaire n'ont
  // pas « zéro ticket le soir », elles n'ont pas la mesure : elles sont exclues des médianes
  // filtrées. Un historique à moitié instrumenté qui se tairait se lirait comme un historique
  // complet — et les médianes du soir porteraient sur trois jours sans que personne le sache.
  const note = el('tx-segment-note');
  const perdus = d && d.segment_days_dropped;
  note.innerHTML = perdus
    ? perdus + ' jour(s) sur ' + d.segment_days_total + ' n’ont pas de mesure horaire et sont '
      + '<b>exclus</b> de cette vue — ils ne sont pas comptés à zéro.'
    : '';
}

async function loadTx() {
  const err = el('tx-error');
  err.style.display = 'none';
  if (window.uiLoadStart) window.uiLoadStart();
  try {
    const r = await fetch('/api/transactions/daily?segment=' + encodeURIComponent(segment));
    const d = await r.json();
    if (!d || d.ok === false) {
      err.textContent = 'The daily cache did not answer'
        + (d && d.error ? ' — ' + d.error : '') + '. Nothing below is loaded — and nothing below is zero.';
      err.style.display = '';
      renderAll({});                     // la page reste lisible, tout est à « — »
      majSegment(null);
      return;
    }
    renderAll(d);
    majSegment(d);
  } catch (e) {
    err.textContent = 'Network error — the figures below are not loaded (which is not the same as zero).';
    err.style.display = '';
    renderAll({});
    majSegment(null);
  } finally {
    if (window.uiLoadEnd) window.uiLoadEnd();
  }
}

// Les graphiques lisent leurs couleurs dans les tokens AU MOMENT du tracé : un
// changement de thème système doit les repeindre, sinon ils restent aux couleurs de
// l'ancien mode.
if (typeof window !== 'undefined' && window.matchMedia) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const redraw = function () { if (lastPayload) renderCharts(lastPayload); };
  if (mq.addEventListener) mq.addEventListener('change', redraw);
  else if (mq.addListener) mq.addListener(redraw);
}

if (typeof document !== 'undefined') {
  const barre = document.querySelector('.tx-segment');
  if (barre) {
    barre.addEventListener('click', function (e) {
      const b = e.target.closest ? e.target.closest('button[data-seg]') : null;
      if (!b || b.dataset.seg === segment) return;
      segment = b.dataset.seg;
      majSegment(null);                  // la sélection bouge tout de suite, la donnée suit
      loadTx();
    });
  }
  loadTx();
}
