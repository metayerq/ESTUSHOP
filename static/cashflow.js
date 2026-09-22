let chartCashflow = null;
let cashflowData = null;

/* ═══════════════════════════════════════════════════════════════════════════════════════════
   LA TRÉSORERIE — ce qui est vraiment entré et sorti.
   ═══════════════════════════════════════════════════════════════════════════════════════════

   ⚠️ CE CODE VIVAIT DANS `dashboard.js`, DERRIÈRE UN ONGLET. Deux écrans dans un fichier, deux
   jeux de données chargés par la même page, et une vue que personne ne trouvait s'il ne savait
   pas déjà qu'elle existait. La trésorerie ne partage RIEN avec le tableau de bord : ni
   période — elle va toujours depuis l'ouverture — ni source, ni question.

   ⚠️ ET ELLE NE RÉPOND PAS À LA MÊME QUESTION. Le tableau de bord dit « est-ce qu'on couvre nos
   coûts ? », qui est une question de RÉSULTAT ; celle-ci dit « qu'est-ce qu'il reste en
   banque ? », qui est une question d'ENCAISSEMENT. Les mêler sous deux onglets laissait croire
   à deux vues d'une même chose.
   ═══════════════════════════════════════════════════════════════════════════════════════════ */

const fmt = (v) => new Intl.NumberFormat('fr-PT', {
  style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
}).format(v || 0);

/* ⚠️ `BAR_ACTIVE` ÉTAIT UNE VARIABLE DE `dashboard.js`, ET CETTE PAGE NE LE CHARGE PAS.
 * Elle est partie avec le code quand la trésorerie a été détachée ; sa DÉCLARATION est restée
 * derrière, puis a disparu du tableau de bord à son tour. Résultat : `renderCashflow` levait un
 * ReferenceError à la construction du graphique — les quatre chiffres du haut s'affichaient
 * (ils sont calculés avant), le GRAPHIQUE ne se dessinait jamais et le détail mensuel restait
 * sur « Loading… » indéfiniment. Aucune erreur visible, juste un tableau qui ne vient pas.
 *
 * ⚠️ LES COULEURS SE LISENT AU MOMENT DU TRACÉ, comme sur les autres graphiques du produit.
 * Chart.js ne relit pas ses couleurs tout seul : un changement de thème doit redessiner. */
function jeton(nom) {
  return getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
}

async function loadCashflow() {
  document.getElementById('cf-updated').textContent = 'Loading…';
  if (window.uiLoadStart) uiLoadStart();
  try {
    const r = await fetch('/api/cashflow');
    cashflowData = await r.json();
    document.getElementById('cf-updated').textContent =
      `${cashflowData.from_date} → ${cashflowData.to_date}`;
    renderCashflow();
  } catch (e) {
    document.getElementById('cf-updated').textContent = 'Failed to load';
  } finally {
    if (window.uiLoadEnd) uiLoadEnd();
  }
}

async function loadCommissions() {
  try {
    const r = await fetch('/api/commissions');
    const j = await r.json();
    const rows = j.rows || [];
    document.getElementById('com-body').innerHTML = rows.length ? rows.map(c => `
      <tr>
        <td>${c.date}</td>
        <td>${c.label || ''}</td>
        <td class="r">${fmt(c.amount)}</td>
        <td style="text-align:right;"><button onclick="deleteCommission('${c.id}')"
            style="border:none;background:none;color:var(--db-faint);cursor:pointer;font-size:13px;">&#10005;</button></td>
      </tr>`).join('')
      : '<tr><td colspan="4" class="db-empty">Aucune commission saisie.</td></tr>';
  } catch (e) { /* section optionnelle */ }
}

async function addCommission() {
  const day = document.getElementById('com-date').value;
  const label = document.getElementById('com-label').value.trim();
  const amount = parseFloat(document.getElementById('com-amount').value);
  const err = document.getElementById('com-error');
  err.style.display = 'none';
  if (!day || !(amount > 0)) {
    err.textContent = 'Date et montant requis.'; err.style.display = ''; return;
  }
  const r = await fetch('/api/commissions', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({date: day, label, amount})});
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    err.textContent = 'Erreur : ' + (j.error || r.status); err.style.display = ''; return;
  }
  document.getElementById('com-label').value = '';
  document.getElementById('com-amount').value = '';
  // ⚠️ PLUS DE `loadData(true)` ICI : il rechargeait le tableau de bord, qui vivait
  // dans la même page. L'appeler depuis la trésorerie chercherait une fonction
  // absente et ferait tomber l'enregistrement au dernier moment, après l'écriture.
  cashflowData = null; loadCashflow(); loadCommissions();
}

async function deleteCommission(id) {
  await fetch('/api/commissions/' + id, {method: 'DELETE'});
  // ⚠️ PLUS DE `loadData(true)` ICI : il rechargeait le tableau de bord, qui vivait
  // dans la même page. L'appeler depuis la trésorerie chercherait une fonction
  // absente et ferait tomber l'enregistrement au dernier moment, après l'écriture.
  cashflowData = null; loadCashflow(); loadCommissions();
}

function renderCashflow() {
  if (!cashflowData) return;
  const excl = document.getElementById('cf-excl-capex').checked;
  const months = cashflowData.months;
  if (!months.length) {
    document.getElementById('cashflow-body').innerHTML =
      '<tr><td colspan="5" class="db-empty">Aucune donnée pour le moment.</td></tr>';
    return;
  }

  const outKey = excl ? 'expenses_excl_capex' : 'expenses';
  const netKey = excl ? 'net_excl_capex'      : 'net';
  const cumKey = excl ? 'cum_net_excl_capex'  : 'cum_net';

  const totalIn  = months.reduce((s, m) => s + (m.cash_in ?? m.revenue), 0);
  const totalOut = months.reduce((s, m) => s + m[outKey], 0);
  const net      = totalIn - totalOut;
  document.getElementById('cf-total-in').textContent  = fmt(totalIn);
  document.getElementById('cf-total-out').textContent = fmt(totalOut);
  /* ⚠️ L'ÉTAT PASSE DU CHIFFRE À LA CARTE. Le nombre était peint en vert ou en rouge ; sur une
   * rangée où trois voisins portent déjà des montants, une quatrième couleur ne ressort plus.
   * La bande d'accent le dit sans toucher au chiffre, qui reste lisible en encre. */
  document.getElementById('cf-net').textContent = fmt(net);
  document.getElementById('i-net').setAttribute('data-etat', net >= 0 ? 'ok' : 'alerte');

  const sorted = months.slice().sort((a, b) => a[netKey] - b[netKey]);
  const worst = sorted[0], best = sorted[sorted.length - 1];
  const fmtMonth = m => new Date(m + '-01T12:00:00').toLocaleDateString('en-GB', {month:'short', year:'numeric'});
  /* ⚠️ LE MEILLEUR ET LE PIRE NE SONT PAS « BON » ET « MAUVAIS » : ce sont les deux bouts
   * d'une même série. Les peindre en vert et rouge donnait un jugement à un classement — le
   * pire mois d'un bon semestre reste positif. Les pastilles disent « haut » et « bas ». */
  document.getElementById('cf-best').innerHTML =
    `<span class="db-badge plain up">${fmtMonth(best.month)} ${fmt(best[netKey])}</span> ` +
    `<span class="db-badge plain flat">${fmtMonth(worst.month)} ${fmt(worst[netKey])}</span>`;

  // Chart : barres CA / Dépenses + ligne cumul net
  const ctx = document.getElementById('chart-cashflow').getContext('2d');
  const vert   = jeton('--green');
  const rouge  = jeton('--red');
  const accent = jeton('--accent');
  const faint  = jeton('--faint');
  const filet  = jeton('--border');
  if (chartCashflow) chartCashflow.destroy();
  chartCashflow = new Chart(ctx, {
    data: {
      labels: months.map(m => fmtMonth(m.month)),
      datasets: [
        { type: 'bar', label: 'Cash in',  data: months.map(m => m.cash_in ?? m.revenue),
          backgroundColor: vert, borderRadius: 4, borderSkipped: false },
        { type: 'bar', label: 'Cash out', data: months.map(m => m[outKey]),
          backgroundColor: rouge, borderRadius: 4, borderSkipped: false },
        /* ⚠️ LE CUMUL PARTAGE L'AXE DES BARRES, et c'est le point. Il avait le sien
         * (`yAxisID: 'y2'`, à droite) : deux échelles POUR LA MÊME UNITÉ, des euros contre des
         * euros. Le lecteur comparait une hauteur de barre à une hauteur de ligne et en tirait
         * une conclusion que la donnée ne porte pas — le croisement des deux ne voulait
         * strictement rien dire. Sur un seul axe, un cumul qui écrase les barres est une
         * information : il dit que le mois pèse peu devant ce qui s'est accumulé. */
        { type: 'line', label: 'Cumulative net', data: months.map(m => m[cumKey]),
          borderColor: accent, backgroundColor: 'transparent', borderWidth: 2,
          pointRadius: 3, pointBackgroundColor: accent },
      ]
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.raw)}` } }
      },
      scales: {
        y: { ticks: { callback: v => fmt(v), font: { size: 11 }, color: faint },
             grid: { color: filet }, border: { display: false } },
        x: { ticks: { font: { size: 11 }, color: faint },
             grid: { display: false }, border: { display: false } }
      }
    }
  });

  // Détail mensuel
  document.getElementById('cashflow-body').innerHTML = months.map(m => {
    const netVal = m[netKey];
    const cumVal = m[cumKey];
    return `<tr>
      <td>${fmtMonth(m.month)}</td>
      <td class="r">${fmt(m.cash_in ?? m.revenue)}${m.commissions ? ` <span title="dont ${fmt(m.commissions)} de commissions reçues" style="color:var(--accent);font-size:11px;">◆</span>` : ''}</td>
      <td class="r">${fmt(m[outKey])}</td>
      <td class="r"><b>${fmt(netVal)}</b></td>
      <td class="r ${cumVal >= 0 ? 'cum-pos' : 'cum-neg'}">${fmt(cumVal)}</td>
    </tr>`;
  }).join('');
}


/* ⚠️ CHART.JS LIT SES COULEURS UNE FOIS, AU TRACÉ. Sans ceci, un passage en mode sombre laisse
 * le graphique aux couleurs de l'ancien mode — les deux autres pages à graphique le font déjà. */
if (typeof window !== 'undefined' && window.matchMedia) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const redraw = () => { if (cashflowData) renderCashflow(); };
  if (mq.addEventListener) mq.addEventListener('change', redraw);
  else if (mq.addListener) mq.addListener(redraw);
}

loadCashflow();
loadCommissions();
