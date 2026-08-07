/* ═══════════════════════════════════════════════════════════════════════════════
   /transactions — « l'affluence tient-elle ? »

   Le CA baisse (quartier résidentiel, mois d'août). La question du propriétaire
   n'est pas « combien j'encaisse » mais « est-ce que les gens viennent encore ».
   La page répond à ÇA en premier, et le reste est du contexte.

   Trois règles tenues d'un bout à l'autre :

   1. AUCUN ZÉRO FABRIQUÉ. Les jours fermés sont absents de `days` — ce ne sont pas
      des journées à zéro ticket. Les dessiner à zéro écraserait la médiane et
      inventerait une chute qui n'a pas eu lieu.
   2. AUCUNE TENDANCE. Pas de régression, pas de moyenne mobile, pas de projection.
      ~40 jours ouvrés dont des pointes à 3-4× la médiane : une pente serait le
      dessin du bruit, avec l'autorité d'une droite. On trace des MÉDIANES DE
      FENÊTRE EN ESCALIER, qui assument leur discrétisation — chaque palier dit
      « voilà la journée typique de ces 14 jours », rien de plus.
   3. UN CHIFFRE NON CALCULABLE S'ÉCRIT « — » AVEC SA RAISON. Jamais 0, jamais un
      delta contre une fenêtre vide, jamais un −100 % qui n'est qu'une absence.

   Les fonctions de modèle (headlineModel, chartModel, windowRows, weekdayRows,
   multiLineModel, reasonLabel, fmt*) sont PURES : elles ne touchent pas au DOM.
   tests/test_tx_page.js les lit dans CE fichier et les exécute.
   ═══════════════════════════════════════════════════════════════════════════════ */

let chartTx = null;      // instance Chart.js, détruite avant chaque re-rendu
let lastPayload = null;  // dernier payload servi, pour re-dessiner au changement de thème

// ── Format ────────────────────────────────────────────────────────────────────
// Un null n'est pas un zéro : il devient « — », et l'appelant lui colle une raison.

function fmtTx(v) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  return (Math.round(v * 10) / 10).toString();
}

function fmtEur(v) {
  if (v == null || typeof v !== 'number' || !isFinite(v)) return '—';
  return v.toFixed(2) + ' €';
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

function fmtRange(from, to) {
  if (!from || !to) return '';
  return fmtDay(from) + ' – ' + fmtDay(to);
}

// ── Raisons ───────────────────────────────────────────────────────────────────
// L'API envoie un CODE. On l'écrit en clair quand on le connaît, et on affiche le
// code brut sinon : un code inconnu reste plus honnête qu'un « — » muet, et il
// signale que l'API a appris un cas que la page ignore encore.

// ⚠️ LE SERVEUR ÉMET DES CODES, PAS DE LA PROSE — et c'est ici que vit la formulation.
// Première intégration : l'endpoint renvoyait « 2 jours pleins seulement » en toutes lettres,
// qui s'affichait tel quel dans une page anglaise, faute de correspondance dans cette table.
// Le contrat que j'avais écrit donnait l'exemple en français : la faute est au contrat, pas
// aux deux implémentations qui l'ont suivi chacune raisonnablement.
// Plusieurs causes peuvent se cumuler : elles arrivent jointes par « + ».
function reasonLabel(code) {
  if (!code) return null;
  if (String(code).includes('+')) {
    return String(code).split('+').map(reasonLabel).filter(Boolean).join(' · ');
  }
  const MAP = {
    'truncated':            'window truncated — start of history',
    'no-reliable-window':   'no 14-day window reaches 6 full open days yet',
    'latest-window-skipped':'most recent window skipped — too thin',
    'windows-skipped':      'thin windows in between were skipped',
    'no-data':          'no day recorded yet',
    'no-days':          'no open day in this range',
    'too-few-days':     'fewer than 6 full open days — too thin for a median',
    'insufficient':     'fewer than 6 full open days — too thin for a median',
    'no-prev-window':   'no earlier full window to compare against',
    'no-previous':      'no earlier full window to compare against',
    'prev-unreliable':  'the earlier window is too thin to compare against',
    'prev-zero':        'the earlier window had no ticket — a ratio would be meaningless',
    'partial-window':   'this window is still running',
    'multi-not-measured':'multi-line share not recorded for every day in this window',
  };
  return MAP[code] || String(code);
}

// ── 1. Bandeau-réponse ────────────────────────────────────────────────────────
// Tickets/jour ouvré de la dernière fenêtre fiable, contre la précédente, CHACUNE
// AVEC SON n : « 20 sur 8 jours » et « 30 sur 8 jours » ne pèsent pas pareil que
// « 20 sur 8 » contre « 30 sur 2 », et le lecteur doit pouvoir en juger lui-même.
//
// delta_pct null ⇒ on écrit la raison. Ni « 0 % » (qui dirait « stable » alors
// qu'on ne sait pas), ni « −100 % » (qui dirait « effondrement » alors qu'il n'y
// a rien en face).

function headlineModel(h) {
  const out = {
    ok: false,
    value: '—', n: null, range: '',
    hasPrev: false, prevValue: '—', prevN: null, prevRange: '',
    deltaText: null, deltaDir: 'none',
    note: null, reason: null,
  };
  if (!h || typeof h !== 'object') {
    out.reason = 'no-data';
    out.note = reasonLabel('no-data');
    return out;
  }
  out.reason = h.reason || null;
  out.n = (typeof h.n === 'number') ? h.n : null;
  out.range = fmtRange(h.from, h.to);

  if (typeof h.tx_median !== 'number' || !isFinite(h.tx_median)) {
    out.note = reasonLabel(h.reason || 'no-data');
    return out;
  }
  out.ok = true;
  out.value = fmtTx(h.tx_median);

  // La fenêtre précédente n'existe qu'avec un n : un « n » absent ou nul, c'est
  // une fenêtre vide, et on ne compare pas contre du vide.
  const prevOk = (typeof h.prev_tx_median === 'number' && isFinite(h.prev_tx_median))
              && (typeof h.prev_n === 'number' && h.prev_n > 0);
  if (!prevOk) {
    out.note = reasonLabel(h.reason || 'no-prev-window');
    return out;
  }
  out.hasPrev = true;
  out.prevValue = fmtTx(h.prev_tx_median);
  out.prevN = h.prev_n;
  out.prevRange = fmtRange(h.prev_from, h.prev_to);

  if (typeof h.delta_pct !== 'number' || !isFinite(h.delta_pct)) {
    out.note = reasonLabel(h.reason || 'no-prev-window');
    return out;
  }
  const p = Math.round(h.delta_pct);
  if (p === 0) {
    out.deltaText = 'flat';
    out.deltaDir = 'flat';
  } else {
    out.deltaText = (p > 0 ? '+' : '−') + Math.abs(p) + ' %';
    out.deltaDir = p > 0 ? 'up' : 'down';
  }
  return out;
}

// ── 2. Graphique principal ────────────────────────────────────────────────────
// Une barre par jour PRÉSENT dans le payload. Un jour fermé n'a pas de barre : il
// n'a pas d'existence sur cet axe. Un jour ouvert à 0 ticket, lui, en a une — c'est
// une mesure, pas une absence.
//
// L'escalier : chaque jour reçoit la médiane de la fenêtre qui le contient. Une
// fenêtre non fiable ne donne PAS de palier (null ⇒ trou dans la ligne) plutôt
// qu'un palier fragile qu'on ne distinguerait plus des autres.
//
// yMax = le maximum réel. Les 80 tickets du 16 juillet et les 73 du 29 juin
// s'affichent en entier. Les écrêter tasserait tout le reste de la série pour
// faire joli, et rien à l'écran ne dirait que le sommet a été coupé.

function chartModel(days, windows) {
  const src = Array.isArray(days) ? days : [];
  const wins = Array.isArray(windows) ? windows : [];
  const bars = [];
  for (let i = 0; i < src.length; i++) {
    const d = src[i];
    if (!d || typeof d.day !== 'string') continue;
    if (typeof d.nb !== 'number' || !isFinite(d.nb)) continue;   // pas de nb ⇒ pas de barre
    bars.push({
      day: d.day,
      nb: d.nb,
      partial: d.partial === true,
      label: fmtDay(d.day),
      ca_ttc: (typeof d.ca_ttc === 'number') ? d.ca_ttc : null,
    });
  }
  // Escalier : recherche de la fenêtre contenant le jour. Les fenêtres se
  // chevauchent potentiellement ; la plus récente qui contient le jour gagne.
  const steps = bars.map(function (b) {
    let best = null;
    for (let j = 0; j < wins.length; j++) {
      const w = wins[j];
      if (!w || !w.from || !w.to) continue;
      if (b.day < w.from || b.day > w.to) continue;
      if (w.reliable === false) continue;                        // pas de palier fragile
      if (typeof w.tx_median !== 'number' || !isFinite(w.tx_median)) continue;
      if (!best || w.to > best.to) best = w;
    }
    return best ? best.tx_median : null;
  });
  const yMax = bars.reduce(function (m, b) { return b.nb > m ? b.nb : m; }, 0);
  return {
    bars: bars,
    steps: steps,
    yMax: yMax,          // valeur réelle, jamais plafonnée
    clipped: false,      // aucune troncature : si ça changeait, il faudrait l'écrire à l'écran
    partialCount: bars.filter(function (b) { return b.partial; }).length,
    n: bars.length,
  };
}

// ── 3. Fenêtres de 14 jours ───────────────────────────────────────────────────
// Une fenêtre non fiable garde son n (l'information utile : « il n'y a que 3 jours
// pleins ici ») mais perd ses médianes. Publier une « médiane » de 3 jours à côté
// de médianes de 14 la ferait lire comme une journée typique — elle n'en est pas
// une, et rien dans le nombre lui-même ne le dirait.

function windowRows(windows) {
  const src = Array.isArray(windows) ? windows.slice() : [];
  src.sort(function (a, b) { return String((b && b.to) || '').localeCompare(String((a && a.to) || '')); });
  return src.map(function (w) {
    const ok = w && w.reliable !== false;
    let note = (w && w.reason) ? reasonLabel(w.reason) : null;
    if (!ok && !note) note = reasonLabel('too-few-days');
    const row = {
      from: (w && w.from) || null,
      to: (w && w.to) || null,
      range: w ? fmtRange(w.from, w.to) : '',
      n: (w && typeof w.full_days === 'number') ? w.full_days : null,
      reliable: !!ok,
      tx: ok ? fmtTx(w && w.tx_median) : '—',
      ca: ok ? fmtEur(w && w.ca_median) : '—',
      basket: ok ? fmtEur(w && w.basket_median) : '—',
      multi: ok ? fmtPct(w && w.multi_pct) : '—',
      note: note,
    };
    if (ok && !note && (row.tx === '—' || row.ca === '—' || row.basket === '—')) {
      note = 'not computable from the daily cache';
      row.note = note;
    }
    return row;
  });
}

// ── 4a. Médiane par jour de semaine ───────────────────────────────────────────
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
  return NOMS.map(function (nom, idx) {
    const w = par[idx];
    const n = (w && typeof w.n === 'number') ? w.n : 0;
    const has = !!w && n > 0 && typeof w.tx_median === 'number' && isFinite(w.tx_median);
    return {
      weekday: idx,
      label: (w && w.label) || nom,
      n: n,
      tx: has ? fmtTx(w.tx_median) : '—',
      value: has ? w.tx_median : null,
      note: has ? null : (n === 0 ? 'never open on this day yet' : 'no median for this day'),
    };
  });
}

// ── 4b. Part des tickets multi-lignes ─────────────────────────────────────────
// Lue sur la dernière fenêtre FIABLE. Pas de moyenne de toutes les fenêtres : elles
// se chevauchent, la moyenne compterait plusieurs fois les mêmes jours.

function multiLineModel(windows) {
  const src = Array.isArray(windows) ? windows.slice() : [];
  src.sort(function (a, b) { return String((b && b.to) || '').localeCompare(String((a && a.to) || '')); });
  for (let i = 0; i < src.length; i++) {
    const w = src[i];
    if (!w || w.reliable === false) continue;
    if (typeof w.multi_pct !== 'number' || !isFinite(w.multi_pct)) continue;
    return { ok: true, pct: w.multi_pct, text: fmtPct(w.multi_pct), n: (typeof w.full_days === 'number' ? w.full_days : null), range: fmtRange(w.from, w.to), note: null };
  }
  const first = src.length ? src[0] : null;
  return {
    ok: false, pct: null, text: '—', n: null, range: '',
    note: reasonLabel((first && first.reason) || 'no-data'),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// RENDU (DOM) — au-dessous, plus rien n'est pur.
// ═══════════════════════════════════════════════════════════════════════════════

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
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
  g.moveTo(2, 8);  g.lineTo(8, 2);
  g.stroke();
  const p = g.createPattern(c, 'repeat');
  return p || color;   // navigateur sans createPattern : couleur pleine plutôt que rien
}

function el(id) { return document.getElementById(id); }

function renderHeadline(h) {
  const m = headlineModel(h);
  el('hl-value').textContent = m.value;
  el('hl-n').textContent = m.ok
    ? 'median of ' + (m.n == null ? '?' : m.n) + ' full open days' + (m.range ? ' · ' + m.range : '')
    : '';

  const prev = el('hl-prev');
  if (m.hasPrev) {
    prev.innerHTML = 'previous window <b>' + m.prevValue + '</b> tx/open day'
      + ' <span class="tx-dim">· ' + (m.prevN == null ? '?' : m.prevN) + ' full days'
      + (m.prevRange ? ' · ' + m.prevRange : '') + '</span>';
  } else {
    prev.textContent = '';
  }

  const chip = el('hl-delta');
  if (m.deltaText) {
    chip.textContent = (m.deltaDir === 'up' ? '▲ ' : m.deltaDir === 'down' ? '▼ ' : '= ') + m.deltaText;
    chip.className = 'tx-delta tx-delta-' + m.deltaDir;
    chip.style.display = '';
  } else {
    chip.style.display = 'none';
  }
  // La raison remplace le chiffre absent — elle n'est pas une note de bas de page.
  el('hl-note').textContent = m.note ? 'no comparison — ' + m.note : '';
  el('hl-note').style.display = m.note ? '' : 'none';
}

function renderChart(days, windows) {
  const m = chartModel(days, windows);
  const box = el('tx-chart-box');
  const empty = el('tx-chart-empty');
  if (!m.n) {
    box.style.display = 'none';
    empty.style.display = '';
    empty.textContent = 'No open day recorded yet — nothing to plot.';
    el('tx-chart-foot').textContent = '';
    return;
  }
  box.style.display = '';
  empty.style.display = 'none';

  const bar    = cssVar('--flux-leave');
  const median = cssVar('--green');
  const faint  = cssVar('--faint');
  const border = cssVar('--border');
  const hatch  = hatchPattern(faint);

  const ctx = el('chart-tx').getContext('2d');
  if (chartTx) chartTx.destroy();
  chartTx = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: m.bars.map(function (b) { return b.label; }),
      datasets: [
        {
          type: 'bar',
          label: 'tickets',
          data: m.bars.map(function (b) { return b.nb; }),
          backgroundColor: m.bars.map(function (b) { return b.partial ? hatch : bar; }),
          borderColor: m.bars.map(function (b) { return b.partial ? faint : bar; }),
          borderWidth: m.bars.map(function (b) { return b.partial ? 1 : 0; }),
          borderRadius: 2, borderSkipped: false, order: 2,
        },
        {
          type: 'line',
          label: '14-day median',
          data: m.steps,
          stepped: 'middle',       // escalier : un palier par fenêtre, pas une courbe
          spanGaps: false,         // fenêtre non fiable ⇒ trou visible, pas d'interpolation
          borderColor: median, borderWidth: 2,
          pointRadius: 0, fill: false, order: 1,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (c) {
              const b = m.bars[c.dataIndex];
              if (c.datasetIndex === 1) {
                return c.raw == null ? ' no reliable median here' : ' 14-day median: ' + fmtTx(c.raw) + ' tx/open day';
              }
              return ' ' + b.nb + ' tickets'
                + (b.ca_ttc != null ? ' · ' + fmtEur(b.ca_ttc) : '')
                + (b.partial ? ' · partial — excluded from medians' : '');
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,      // pas de suggestedMax : les pointes réelles passent en entier
          ticks: { font: { size: 11 }, color: faint, precision: 0 },
          grid: { color: border }, border: { display: false },
        },
        x: {
          ticks: { font: { size: 10 }, color: faint, maxTicksLimit: 18, autoSkip: true },
          grid: { display: false }, border: { display: false },
        },
      },
    },
  });

  const part = m.bars.filter(function (b) { return b.partial; });
  el('tx-chart-foot').innerHTML =
    m.n + ' open days plotted · closed days have no bar (they are not zero-ticket days)'
    + (part.length ? ' · hatched = ' + part.map(function (b) { return b.label; }).join(', ')
        + ' <b>partial — excluded from medians</b>' : '')
    + ' · peak ' + m.yMax + ' tickets, shown in full (no scale clipping)';
}

function renderWindows(windows) {
  const rows = windowRows(windows);
  const tb = el('tx-win-body');
  if (!rows.length) {
    tb.innerHTML = '<tr><td colspan="5" class="tx-empty">No 14-day window computed yet.</td></tr>';
    return;
  }
  tb.innerHTML = rows.map(function (r) {
    return '<tr class="' + (r.reliable ? '' : 'tx-row-thin') + '">'
      + '<td class="tx-mono">' + r.range + '</td>'
      + '<td class="tx-num">' + r.tx + '</td>'
      + '<td class="tx-num">' + r.ca + '</td>'
      + '<td class="tx-num">' + r.basket + '</td>'
      + '<td class="tx-num tx-dim">' + (r.n == null ? '—' : r.n) + '</td>'
      + '</tr>'
      + (r.note ? '<tr class="tx-note-row"><td colspan="5">' + r.range + ' — ' + r.note + '</td></tr>' : '');
  }).join('');
}

function renderWeekday(weekday) {
  const rows = weekdayRows(weekday);
  const max = rows.reduce(function (m, r) { return r.value != null && r.value > m ? r.value : m; }, 0);
  el('tx-wd-body').innerHTML = rows.map(function (r) {
    const w = (r.value != null && max > 0) ? Math.round(r.value / max * 100) : 0;
    return '<tr>'
      + '<td>' + r.label + '</td>'
      + '<td class="tx-num">' + r.tx + '</td>'
      + '<td class="tx-bar-cell"><span class="tx-bar" style="width:' + w + '%"></span></td>'
      + '<td class="tx-num tx-dim">' + r.n + '</td>'
      + '<td class="tx-dim">' + (r.note || '') + '</td>'
      + '</tr>';
  }).join('');
}

function renderMulti(windows) {
  const m = multiLineModel(windows);
  el('tx-multi-val').textContent = m.text;
  el('tx-multi-sub').textContent = m.ok
    ? 'of tickets have more than one line · last reliable window' + (m.range ? ' (' + m.range + ')' : '')
      + (m.n != null ? ' · ' + m.n + ' full days' : '')
    : (m.note ? 'not computable — ' + m.note : 'not computable');
}

function renderAll(d) {
  lastPayload = d || {};
  renderHeadline(lastPayload.headline);
  renderChart(lastPayload.days, lastPayload.windows);
  renderWindows(lastPayload.windows);
  renderWeekday(lastPayload.weekday);
  renderMulti(lastPayload.windows);
  const scope = el('tx-scope');
  if (scope) {
    scope.textContent = (lastPayload.from && lastPayload.to)
      ? lastPayload.from + ' → ' + lastPayload.to : '';
  }
}

async function loadTx() {
  const err = el('tx-error');
  err.style.display = 'none';
  if (window.uiLoadStart) window.uiLoadStart();
  try {
    const r = await fetch('/api/transactions/daily');
    const d = await r.json();
    if (!d || d.ok === false) {
      err.textContent = 'The daily cache did not answer' + (d && d.error ? ' — ' + d.error : '') + '.';
      err.style.display = '';
      renderAll({});                     // la page reste lisible, tout est à « — »
      return;
    }
    renderAll(d);
  } catch (e) {
    err.textContent = 'Network error — figures below are not loaded (not zero).';
    err.style.display = '';
    renderAll({});
  } finally {
    if (window.uiLoadEnd) window.uiLoadEnd();
  }
}

// Le graphique lit ses couleurs dans les tokens au moment du tracé : un changement
// de thème système doit le repeindre, sinon il reste aux couleurs de l'ancien mode.
if (window.matchMedia) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const redraw = function () { if (lastPayload) renderChart(lastPayload.days, lastPayload.windows); };
  if (mq.addEventListener) mq.addEventListener('change', redraw);
  else if (mq.addListener) mq.addListener(redraw);
}

loadTx();
