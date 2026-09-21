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
        <td class="amount">${fmt(c.amount)}</td>
        <td style="text-align:right;"><button onclick="deleteCommission('${c.id}')"
            style="border:none;background:none;color:var(--faint);cursor:pointer;font-size:13px;">✕</button></td>
      </tr>`).join('')
      : '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:16px;">Aucune commission saisie.</td></tr>';
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
      '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">No data yet.</td></tr>';
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
  const netEl = document.getElementById('cf-net');
  netEl.textContent = fmt(net);
  netEl.style.color = net >= 0 ? 'var(--green)' : 'var(--red)';

  const sorted = months.slice().sort((a, b) => a[netKey] - b[netKey]);
  const worst = sorted[0], best = sorted[sorted.length - 1];
  const fmtMonth = m => new Date(m + '-01T12:00:00').toLocaleDateString('en-GB', {month:'short', year:'numeric'});
  document.getElementById('cf-best').innerHTML =
    `<span style="color:var(--green)">${fmtMonth(best.month)} ${fmt(best[netKey])}</span> · ` +
    `<span style="color:var(--red)">${fmtMonth(worst.month)} ${fmt(worst[netKey])}</span>`;

  // Chart : barres CA / Dépenses + ligne cumul net
  const ctx = document.getElementById('chart-cashflow').getContext('2d');
  if (chartCashflow) chartCashflow.destroy();
  chartCashflow = new Chart(ctx, {
    data: {
      labels: months.map(m => fmtMonth(m.month)),
      datasets: [
        { type: 'bar', label: 'Cash in',  data: months.map(m => m.cash_in ?? m.revenue),
          backgroundColor: 'rgba(68,131,97,.75)', borderRadius: 3, yAxisID: 'y' },
        { type: 'bar', label: 'Cash out', data: months.map(m => m[outKey]),
          backgroundColor: 'rgba(196,85,77,.7)', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Cumulative net', data: months.map(m => m[cumKey]),
          borderColor: BAR_ACTIVE, backgroundColor: 'transparent', borderWidth: 2,
          pointRadius: 4, pointBackgroundColor: BAR_ACTIVE, yAxisID: 'y2' },
      ]
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.raw)}` } }
      },
      scales: {
        y:  { ticks:{callback:v=>v+' €',font:{size:11},color:'rgba(120,119,111,1)'}, grid:{color:'rgba(55,53,47,0.06)'}, border:{display:false} },
        y2: { position:'right', ticks:{callback:v=>v+' €',font:{size:10},color:'#bbb'}, grid:{display:false}, border:{display:false} },
        x:  { ticks:{font:{size:11},color:'rgba(120,119,111,1)'}, grid:{display:false}, border:{display:false} }
      }
    }
  });

  // Détail mensuel
  document.getElementById('cashflow-body').innerHTML = months.map(m => {
    const netVal = m[netKey];
    const cumVal = m[cumKey];
    return `<tr>
      <td>${fmtMonth(m.month)}</td>
      <td class="amount">${fmt(m.cash_in ?? m.revenue)}${m.commissions ? ` <span data-tip="dont ${fmt(m.commissions)} de commissions reçues" style="color:#7c4dbe;font-size:11px;">◆</span>` : ''}</td>
      <td class="amount">${fmt(m[outKey])}</td>
      <td class="amount" style="color:${netVal >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:500;">${fmt(netVal)}</td>
      <td class="amount" style="color:${cumVal >= 0 ? 'var(--green)' : 'var(--red)'};">${fmt(cumVal)}</td>
    </tr>`;
  }).join('');
}


loadCashflow();
loadCommissions();
