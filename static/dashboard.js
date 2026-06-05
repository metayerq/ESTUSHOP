const COLORS = ['rgba(55,53,47,1)','rgba(55,53,47,.65)','rgba(55,53,47,.4)','rgba(55,53,47,.25)','rgba(55,53,47,.12)','rgba(55,53,47,.07)'];
const BAR_ACTIVE = 'rgba(55,53,47,0.85)';
const BAR_IDLE   = 'rgba(55,53,47,0.12)';
let chartHourly = null, chartPayments = null, chartWeek = null, chartCurve = null;

function marginBadge(pct) {
  const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? '#b07d00' : 'var(--red)';
  return `<span style="color:${color};font-weight:500">${pct}%</span>`;
}

const fmt = n => new Intl.NumberFormat('fr-FR', {
  style: 'currency', currency: 'EUR', minimumFractionDigits: 2
}).format(n);

function delta(today, yesterday) {
  if (!yesterday) return '';
  const pct = ((today - yesterday) / yesterday * 100).toFixed(0);
  const cls = pct >= 0 ? 'delta-up' : 'delta-down';
  return `<span class="${cls}">${pct >= 0 ? '+' : ''}${pct}% vs hier</span>`;
}

function getSelectedDate() {
  return document.getElementById('date-picker').value;
}

function goToday() {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('date-picker').value = today;
  loadData();
}

async function loadData() {
  const date = getSelectedDate();
  try {
    const r = await fetch('/api/data' + (date ? '?date=' + date : ''));
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    render(d);
    document.getElementById('error-banner').style.display = 'none';
  } catch(e) {
    document.getElementById('error-msg').textContent = e.message;
    document.getElementById('error-banner').style.display = 'block';
  }
}

function render(d) {
  const dateStr = new Date(d.date + 'T12:00:00').toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
  document.getElementById('subtitle').textContent = 'Alcântara — ' + dateStr;
  const updatedEl = document.getElementById('updated-at');
  if (d.is_today) {
    updatedEl.textContent = 'Mis à jour à ' + d.updated_at;
    updatedEl.style.display = '';
  } else {
    updatedEl.style.display = 'none';
  }

  document.getElementById('kpi-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    document.getElementById('kpi-ca-ht').textContent =
      `${fmt(d.economics.ca_ht)} HT · TVA ${fmt(d.economics.tva_collectee)}`;
  }
  document.getElementById('kpi-ca-delta').innerHTML     = delta(d.today.ca, d.yesterday.ca);
  document.getElementById('kpi-nb').textContent         = d.today.nb;
  document.getElementById('kpi-nb-delta').innerHTML     = delta(d.today.nb, d.yesterday.nb);
  document.getElementById('kpi-ticket').textContent     = fmt(d.today.ticket);
  document.getElementById('kpi-ticket-delta').innerHTML = delta(d.today.ticket, d.yesterday.ticket)
    + (d.today.ticket_ht ? `<span style="color:var(--faint)"> · ${fmt(d.today.ticket_ht)} HT</span>` : '');
  document.getElementById('kpi-balance').textContent    = fmt(d.balance);

  // Tempo service
  const tempoCell = document.getElementById('kpi-tempo-cell');
  if (d.tempo && d.tempo.avg_gap_min != null) {
    tempoCell.style.display = '';
    const gap = d.tempo.avg_gap_min;
    document.getElementById('kpi-tempo').textContent = gap < 1
      ? `${Math.round(gap * 60)}s/tx`
      : `${gap}min/tx`;
    document.getElementById('kpi-tempo-sub').textContent =
      `${d.tempo.tx_per_hour} tx/h · pic ${d.tempo.busiest}`;
  } else {
    tempoCell.style.display = 'none';
  }

  const pct = Math.min(100, Math.round(d.today.nb / d.seuil * 100));
  document.getElementById('seuil-bar').style.width = pct + '%';

  // Sparkline semaine
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
        tooltip: { callbacks: { label: ctx => fmt(ctx.raw) + ' · ' + d.week[ctx.dataIndex].nb + ' tx' } }
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

  // Chart horaire — barres CA + ligne ticket moyen
  const maxHourVal = Math.max(...d.hourly.values);
  const hCtx = document.getElementById('chart-hourly').getContext('2d');
  if (chartHourly) chartHourly.destroy();
  chartHourly = new Chart(hCtx, {
    type: 'bar',
    data: {
      labels: d.hourly.labels,
      datasets: [
        {
          type: 'bar',
          label: 'CA',
          data: d.hourly.values,
          backgroundColor: d.hourly.values.map(v => v > 0 && v === maxHourVal ? BAR_ACTIVE : BAR_IDLE),
          borderRadius: 2,
          borderSkipped: false,
          yAxisID: 'y',
        },
        {
          type: 'line',
          label: 'Ticket moy.',
          data: d.hourly.avg_ticket,
          borderColor: BAR_ACTIVE,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          borderDash: [4, 3],
          pointRadius: d.hourly.avg_ticket.map(v => v != null ? 3 : 0),
          pointBackgroundColor: BAR_ACTIVE,
          spanGaps: false,
          yAxisID: 'y2',
        }
      ]
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.datasetIndex === 0) {
                const nb  = d.hourly.nb[ctx.dataIndex];
                const gap = d.hourly.avg_gap[ctx.dataIndex];
                const gapStr = gap != null ? ` · ${gap}min/tx` : '';
                return ` CA: ${fmt(ctx.raw)}  (${nb} tx${gapStr})`;
              }
              return ctx.raw != null ? ` Ticket moy: ${fmt(ctx.raw)}` : null;
            }
          }
        }
      },
      scales: {
        y: {
          ticks: { callback: v => v + ' €', font: { size: 11 }, color: 'rgba(120,119,111,1)' },
          grid: { color: 'rgba(55,53,47,0.06)' }, border: { display: false },
        },
        y2: {
          position: 'right',
          ticks: { callback: v => v + ' €', font: { size: 10 }, color: '#bbb' },
          grid: { display: false }, border: { display: false },
        },
        x: {
          ticks: { font: { size: 11 }, color: 'rgba(120,119,111,1)' },
          grid: { display: false }, border: { display: false }
        }
      }
    }
  });

  // Chart paiements
  const pCtx = document.getElementById('chart-payments').getContext('2d');
  if (chartPayments) chartPayments.destroy();
  const noData = !d.payments.labels.length;
  if (noData) {
    document.getElementById('payment-legend').innerHTML =
      '<p style="font-size:12px;color:var(--muted);">Aucun mouvement enregistré.</p>';
  } else {
    chartPayments = new Chart(pCtx, {
      type: 'doughnut',
      data: {
        labels: d.payments.labels,
        datasets: [{
          data: d.payments.values,
          backgroundColor: COLORS.slice(0, d.payments.labels.length),
          borderWidth: 3, borderColor: '#fff'
        }]
      },
      options: {
        cutout: '68%',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ' ' + ctx.label + ': ' + fmt(ctx.raw) } }
        }
      }
    });
    const total = d.payments.values.reduce((a, b) => a + b, 0);
    document.getElementById('payment-legend').innerHTML = d.payments.labels.map((l, i) => {
      const p = total > 0 ? Math.round(d.payments.values[i] / total * 100) : 0;
      return `<div class="pay-row">
        <span class="pay-name"><span class="pay-dot" style="background:${COLORS[i]}"></span>${l}</span>
        <span class="pay-val">${fmt(d.payments.values[i])} · ${p}%</span>
      </div>`;
    }).join('');
  }

  // Économie du jour
  const eco = d.economics;
  if (eco) {
    // Marge brute HT
    document.getElementById('eco-marge').textContent = eco.marge_brute_ht != null ? fmt(eco.marge_brute_ht) : '—';
    document.getElementById('eco-marge-pct').innerHTML = eco.marge_brute_ht_pct != null
      ? `${eco.marge_brute_ht_pct}% <span style="color:var(--faint)">HT · COGS ${fmt(eco.cogs_ht)}</span>`
      : '<span style="color:var(--muted)">coûts partiels catalogue</span>';

    // Charges HT/jour
    document.getElementById('eco-charges').textContent = fmt(eco.cout_total_jour);
    document.getElementById('eco-charges-sub').innerHTML =
      `Fixe ${fmt(eco.cout_fixe_jour)} · Perso ${fmt(eco.cout_perso_jour)} <span style="color:var(--faint)">HT</span>`;

    // EBITDA HT
    const ebitdaEl = document.getElementById('eco-ebitda');
    ebitdaEl.textContent = eco.ebitda_ht != null ? fmt(eco.ebitda_ht) : '—';
    ebitdaEl.style.color = eco.ebitda_ht > 0 ? 'var(--green)' : eco.ebitda_ht < 0 ? 'var(--red)' : 'var(--text)';
    const ebitdaSub = document.getElementById('eco-ebitda-sub');
    if (eco.ebitda_ht != null) {
      ebitdaSub.innerHTML = eco.ebitda_ht > 0
        ? `<span style="color:var(--green)">Journée rentable ✓</span>`
        : `<span style="color:var(--red)">Déficit ${fmt(Math.abs(eco.ebitda_ht))}</span>`;
    }

    // Seuil CA HT + ligne TVA
    document.getElementById('eco-seuil').textContent = fmt(eco.seuil_ca_ht);
    const seuilSub = document.getElementById('eco-seuil-sub');
    if (eco.manque_seuil > 0) {
      seuilSub.innerHTML = `<span style="color:var(--red)">Il manque ${fmt(eco.manque_seuil)} HT</span>`;
    } else {
      seuilSub.innerHTML = `<span style="color:var(--green)">Seuil dépassé ✓</span>`;
    }
    document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
  }

  // Performance commerciale
  // Ticket médian
  if (d.median != null) {
    document.getElementById('kpi-median').textContent = fmt(d.median);
    const diff = d.today.ticket ? Math.round((d.median - d.today.ticket) / d.today.ticket * 100) : 0;
    document.getElementById('kpi-median-vs').textContent = fmt(d.today.ticket) + (diff !== 0 ? ` (${diff > 0 ? '+' : ''}${diff}%)` : '');
  }

  // Upsell
  if (d.upsell && d.upsell.total) {
    document.getElementById('kpi-upsell').textContent = d.upsell.rate + '%';
    document.getElementById('kpi-upsell-sub').textContent =
      `${d.upsell.multi} tickets multi · ${d.upsell.single} seul`;
  }

  // Mix boissons/food
  const MIX_COLORS = {'Boissons':'rgba(55,53,47,1)','Food':'rgba(55,53,47,.55)','Extras':'rgba(55,53,47,.3)','Autre':'rgba(55,53,47,.15)'};
  if (d.mix && d.mix.length) {
    const total = d.mix.reduce((a,b) => a + b.amount, 0);
    document.getElementById('mix-bars').innerHTML = d.mix.map(m => `
      <div style="margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
          <span style="color:var(--muted)">${m.label}</span>
          <span style="font-weight:500">${m.pct}% · ${fmt(m.amount)}</span>
        </div>
        <div style="height:4px;background:var(--bar-bg);border-radius:2px;">
          <div style="height:4px;background:${MIX_COLORS[m.label]||'#888'};border-radius:2px;width:${m.pct}%"></div>
        </div>
      </div>`).join('');
  }

  // Tendance WoW
  if (d.wow) {
    document.getElementById('kpi-wow-ca').textContent = fmt(d.wow.cur_ca);
    document.getElementById('kpi-wow-ca-delta').innerHTML = d.wow.growth_ca != null
      ? `<span class="${d.wow.growth_ca >= 0 ? 'delta-up' : 'delta-down'}">${d.wow.growth_ca >= 0 ? '+' : ''}${d.wow.growth_ca}% vs sem. préc.</span>`
      : '<span style="color:var(--muted)">pas de comparatif</span>';
    document.getElementById('kpi-wow-nb').textContent = d.wow.cur_nb;
    document.getElementById('kpi-wow-nb-delta').innerHTML = d.wow.growth_nb != null
      ? `<span class="${d.wow.growth_nb >= 0 ? 'delta-up' : 'delta-down'}">${d.wow.growth_nb >= 0 ? '+' : ''}${d.wow.growth_nb}% vs sem. préc.</span>`
      : '<span style="color:var(--muted)">pas de comparatif</span>';
  }

  // Meilleur jour de la semaine
  if (d.weekdays && d.weekdays.length) {
    const best = d.weekdays[0];
    document.getElementById('kpi-best-day').textContent = best.day;
    document.getElementById('kpi-best-day-sub').textContent =
      `moy. ${fmt(best.avg_ca)} · ${best.n_days}j de données`;
  }

  // Courbe cumulative
  const curveSection = document.getElementById('curve-section');
  if (d.curve && d.curve.length > 1) {
    curveSection.style.display = '';
    const cCtx = document.getElementById('chart-curve').getContext('2d');
    if (chartCurve) chartCurve.destroy();
    chartCurve = new Chart(cCtx, {
      type: 'line',
      data: {
        labels: d.curve.map(p => p.time),
        datasets: [{
          data: d.curve.map(p => p.ca_cum),
          borderColor: BAR_ACTIVE,
          backgroundColor: 'rgba(55,53,47,0.06)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: d.curve.map((p, i) => i === 0 ? 0 : 4),
          pointBackgroundColor: BAR_ACTIVE,
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
        }]
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: ctx => ctx[0].label,
              label: ctx => {
                const pt = d.curve[ctx.dataIndex];
                return [
                  ` Cumul : ${fmt(ctx.raw)}`,
                  pt.ca_tx ? ` + ${fmt(pt.ca_tx)}  (${pt.nb})` : '',
                ].filter(Boolean);
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: v => v + ' €', font: { size: 11 }, color: 'rgba(120,119,111,1)' },
            grid: { color: 'rgba(55,53,47,0.06)' }, border: { display: false },
          },
          x: {
            ticks: { font: { size: 11 }, color: 'rgba(120,119,111,1)', maxTicksLimit: 12 },
            grid: { display: false }, border: { display: false },
          }
        }
      }
    });
  } else {
    curveSection.style.display = 'none';
  }

  // Rush detector
  const rushSection = document.getElementById('rush-section');
  if (d.rush && d.rush.length) {
    rushSection.style.display = '';
    document.getElementById('rush-list').innerHTML = d.rush.map(r =>
      `<span class="rush-badge">⚡ ${r.start}–${r.end} · ${r.count} tx</span>`
    ).join('');
  } else {
    rushSection.style.display = 'none';
  }

  // Top produits
  const maxQty = d.products.length ? d.products[0].qty : 1;
  if (!d.products.length) {
    document.getElementById('products-body').innerHTML =
      '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">Aucun produit vendu aujourd\'hui.</td></tr>';
  } else {
    document.getElementById('products-body').innerHTML = d.products.map((p, i) => {
      const barW = Math.round(p.qty / maxQty * 100);
      const rank = i === 0 ? ' style="font-weight:600"' : '';
      const marginHtml = p.margin_pct != null ? marginBadge(p.margin_pct) : '<span style="color:var(--muted)">—</span>';
      return `<tr>
        <td${rank}>${p.name}</td>
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

  // CA moyen 7j par produit
  if (!d.products_7d || !d.products_7d.length) {
    document.getElementById('products7d-body').innerHTML =
      '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">Aucune donnée sur 7 jours.</td></tr>';
  } else {
    const maxRev7 = d.products_7d[0].revenue;
    document.getElementById('products7d-body').innerHTML = d.products_7d.map((p, i) => {
      const bar = Math.round(p.revenue / maxRev7 * 100);
      const marginHtml = p.margin_pct != null ? marginBadge(p.margin_pct) : '<span style="color:var(--muted)">—</span>';
      return `<tr>
        <td style="${i===0?'font-weight:600':''}">${p.name}</td>
        <td class="amount" style="color:var(--muted)">${p.days_sold}j</td>
        <td class="amount" style="color:var(--muted)">${p.qty}</td>
        <td class="amount">${fmt(p.revenue)}</td>
        <td class="amount">${marginHtml}</td>
        <td style="padding-right:16px;vertical-align:middle;min-width:100px;">
          <div style="height:3px;background:var(--bar-bg);border-radius:2px;">
            <div style="height:3px;background:var(--bar);border-radius:2px;width:${bar}%"></div>
          </div>
          <span style="font-size:11px;color:var(--muted)">${fmt(p.avg_day)}/j</span>
        </td>
      </tr>`;
    }).join('');
  }

  // Ventilation TVA
  const tvaSection = document.getElementById('tva-section');
  if (d.tva && d.tva.rows.length) {
    tvaSection.style.display = '';
    document.getElementById('tva-body').innerHTML = d.tva.rows.map(r => `
      <tr>
        <td><span class="badge">${r.rate}%</span></td>
        <td class="amount">${fmt(r.base)}</td>
        <td class="amount">${fmt(r.tva)}</td>
        <td class="amount">${fmt(r.total)}</td>
      </tr>`).join('');
    document.getElementById('tva-foot').innerHTML = `
      <tr>
        <td>Total</td>
        <td class="amount">${fmt(d.tva.totals.base)}</td>
        <td class="amount">${fmt(d.tva.totals.tva)}</td>
        <td class="amount">${fmt(d.tva.totals.total)}</td>
      </tr>`;
  } else {
    tvaSection.style.display = 'none';
  }

  // Produits non vendus
  const unsoldSection = document.getElementById('unsold-section');
  if (d.unsold && d.unsold.length) {
    unsoldSection.style.display = '';
    document.getElementById('unsold-list').innerHTML =
      d.unsold.map(p => `<span class="unsold-tag">${p.name}</span>`).join('');
  } else {
    unsoldSection.style.display = 'none';
  }

  // Tableau transactions — cliquable
  if (!d.recent || !d.recent.length) {
    document.getElementById('recent-body').innerHTML =
      '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:24px;">Aucune transaction aujourd\'hui.</td></tr>';
    return;
  }
  window._txData = d.recent;
  document.getElementById('recent-body').innerHTML = d.recent.map((t, i) => `
    <tr style="cursor:pointer;" onclick="openDrawer(${i})">
      <td class="time">${t.time}</td>
      <td class="num">${t.number}</td>
      <td><span class="badge">${t.type}</span></td>
      <td class="amount">${fmt(t.amount)}</td>
    </tr>`).join('');
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
    : '<tr><td colspan="3" style="color:var(--muted);font-size:12px;padding:8px 0;">Détail non disponible</td></tr>';

  document.getElementById('drawer-payments').innerHTML = t.payments.map(p => `
    <div class="drawer-pay-row">
      <span>${p.label}</span>
      <span>${fmt(p.amount)}</span>
    </div>`).join('');

  document.getElementById('drawer-total').innerHTML =
    `<span>Total</span><span>${fmt(t.amount)}</span>`;

  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

// Initialiser le picker à aujourd'hui
document.getElementById('date-picker').value = new Date().toISOString().slice(0, 10);
loadData();
// Auto-refresh seulement si on est sur aujourd'hui
setInterval(() => { if (getSelectedDate() === new Date().toISOString().slice(0, 10)) loadData(); }, 5 * 60 * 1000);
