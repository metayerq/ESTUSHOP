const COLORS = ['rgba(55,53,47,1)','rgba(55,53,47,.65)','rgba(55,53,47,.4)','rgba(55,53,47,.25)','rgba(55,53,47,.12)','rgba(55,53,47,.07)'];
const BAR_ACTIVE = 'rgba(55,53,47,0.85)';
const BAR_IDLE   = 'rgba(55,53,47,0.12)';
let chartHourly = null, chartWeek = null;
let chartCurve  = null, chartDaily = null;
let activeProdTab = 'period'; // 'period' | '7d'

// ── Preset actif ──────────────────────────────────────────────────────────────
let currentPreset = 'today';

function setPreset(p) {
  currentPreset = p;
  document.querySelectorAll('.pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === p);
  });
  loadData();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function marginBadge(pct) {
  const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? '#b07d00' : 'var(--red)';
  return `<span style="color:${color};font-weight:500">${pct}%</span>`;
}

const fmt = n => new Intl.NumberFormat('fr-FR', {
  style: 'currency', currency: 'EUR', minimumFractionDigits: 2
}).format(n);

function delta(cur, prev, label) {
  label = label || 'vs période préc.';
  if (prev == null || prev === 0) return '';
  const pct = ((cur - prev) / Math.abs(prev) * 100).toFixed(0);
  const cls = pct >= 0 ? 'delta-up' : 'delta-down';
  return `<span class="${cls}">${pct >= 0 ? '+' : ''}${pct}% ${label}</span>`;
}

function fmtDate(iso) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
}

// ── Chargement ────────────────────────────────────────────────────────────────
async function loadData() {
  try {
    const r = await fetch('/api/data?preset=' + currentPreset);
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

// ── Rendu principal ───────────────────────────────────────────────────────────
function render(d) {
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

  // Label KPI dynamique
  const kpiLabel = d.is_single_day
    ? (d.is_today ? 'Aujourd\'hui' : fmtDate(d.date).replace(/^\w/, c => c.toUpperCase()))
    : d.period_label;
  document.getElementById('kpi-section-label').textContent = kpiLabel;

  // Mis à jour
  const updatedEl = document.getElementById('updated-at');
  if (d.is_today) {
    updatedEl.textContent = 'Mis à jour à ' + d.updated_at;
    updatedEl.style.display = '';
  } else {
    updatedEl.style.display = 'none';
  }

  // Label comparaison
  const compLabel = d.is_single_day ? 'vs hier' : 'vs période préc.';

  // ── KPIs ─────────────────────────────────────────────────────────────────
  document.getElementById('kpi-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    document.getElementById('kpi-ca-ht').textContent =
      `${fmt(d.economics.ca_ht)} HT · TVA ${fmt(d.economics.tva_collectee)}`;
  } else {
    document.getElementById('kpi-ca-ht').textContent = '';
  }
  document.getElementById('kpi-ca-delta').innerHTML     = delta(d.today.ca,     d.yesterday.ca,     compLabel);
  document.getElementById('kpi-nb').textContent         = d.today.nb;
  document.getElementById('kpi-nb-delta').innerHTML     = delta(d.today.nb,     d.yesterday.nb,     compLabel);
  document.getElementById('kpi-ticket').textContent     = fmt(d.today.ticket);
  document.getElementById('kpi-ticket-delta').innerHTML = delta(d.today.ticket, d.yesterday.ticket, compLabel)
    + (d.today.ticket_ht ? `<span style="color:var(--faint)"> · ${fmt(d.today.ticket_ht)} HT</span>` : '');
  document.getElementById('kpi-balance').textContent    = d.balance != null ? fmt(d.balance) : '—';

  // Seuil transactions — proportionnel aux jours ouvrés de la période
  const openDaysTx = (d.economics && d.economics.open_days) || 1;
  const seuilTarget = d.seuil * (d.is_single_day ? 1 : openDaysTx);
  const pct = Math.min(100, Math.round(d.today.nb / seuilTarget * 100));
  document.getElementById('seuil-bar').style.width = pct + '%';
  document.getElementById('seuil-meta').textContent = d.is_single_day
    ? `Seuil rentabilité : ${d.seuil} tx/j`
    : `Seuil : ${seuilTarget} tx (${d.seuil}/j × ${openDaysTx}j ouvrés)`;

  // Tempo service (jour unique seulement)
  const tempoCell = document.getElementById('kpi-tempo-cell');
  if (d.is_single_day && d.tempo && d.tempo.avg_gap_min != null) {
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

  // ── Économie ──────────────────────────────────────────────────────────────
  // Labels dynamiques selon la période
  const periodSuffix = d.is_single_day ? 'du jour' : `· ${d.n_days} jours`;
  document.getElementById('eco-label').textContent      = `Économie ${periodSuffix}`;
  document.getElementById('eco-charges-label').textContent = `Charges ${periodSuffix}`;
  document.getElementById('eco-ebitda-label').textContent  = `EBITDA ${periodSuffix}`;
  document.getElementById('eco-seuil-label').textContent   = `Seuil CA TTC ${periodSuffix}`;
  document.getElementById('eco-marge-label').textContent   = 'Marge brute';

  const eco = d.economics;
  if (eco) {
    // Marge brute — 100% COGS réel, avec taux de couverture
    document.getElementById('eco-marge').textContent = eco.marge_brute_ht != null ? fmt(eco.marge_brute_ht) : '—';
    if (eco.marge_brute_ht != null) {
      const cov = eco.cogs_coverage_pct;
      const covColor = cov >= 90 ? 'var(--green)' : cov >= 60 ? '#b07d00' : 'var(--red)';
      const covStr = cov != null
        ? `<span style="color:${covColor}">couverture COGS ${cov}%</span>`
        : '';
      document.getElementById('eco-marge-pct').innerHTML =
        `${eco.marge_brute_ht_pct}% <span style="color:var(--faint)">· COGS ${fmt(eco.cogs_ht)} · </span>${covStr}`;
    } else {
      document.getElementById('eco-marge-pct').innerHTML =
        '<span style="color:var(--muted)">aucun COGS renseigné — complétez vos fiches recettes</span>';
    }

    // Charges — utilise les totaux période et open_days (pas n_days calendaires)
    document.getElementById('eco-charges').textContent = fmt(eco.cout_total_periode ?? eco.cout_total_jour);
    const openDays = eco.open_days || d.n_days;
    const chargesSub = d.is_single_day
      ? `Fixe ${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} · Perso ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)}`
      : `${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} fixes · ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)} perso · <span style="color:var(--faint)">${openDays}j ouvrés × ${fmt(eco.cout_jour ?? (eco.cout_total_jour / openDays))}/j</span>`;
    document.getElementById('eco-charges-sub').innerHTML = chargesSub;

    // EBITDA
    const ebitdaEl = document.getElementById('eco-ebitda');
    ebitdaEl.textContent = eco.ebitda_ht != null ? fmt(eco.ebitda_ht) : '—';
    ebitdaEl.style.color = eco.ebitda_ht > 0 ? 'var(--green)' : eco.ebitda_ht < 0 ? 'var(--red)' : 'var(--text)';
    const ebitdaSub = document.getElementById('eco-ebitda-sub');
    if (eco.ebitda_ht != null) {
      ebitdaSub.innerHTML = eco.ebitda_ht > 0
        ? `<span style="color:var(--green)">Rentable ✓</span>`
        : `<span style="color:var(--red)">Déficit ${fmt(Math.abs(eco.ebitda_ht))}</span>`;
    }

    // Seuil CA — TTC en principal, calculé sur la marge réelle mesurée
    const seuilSub = document.getElementById('eco-seuil-sub');
    if (eco.seuil_ca_ttc != null) {
      document.getElementById('eco-seuil').textContent = fmt(eco.seuil_ca_ttc);
      const margeNote = eco.seuil_margin_pct != null
        ? ` <span style="color:var(--faint)">· marge réelle ${eco.seuil_margin_pct}%</span>`
        : '';
      if (eco.manque_seuil > 0) {
        seuilSub.innerHTML = `<span style="color:var(--red)">Il manque ${fmt(eco.manque_seuil)} TTC</span>` + margeNote;
      } else {
        seuilSub.innerHTML = `<span style="color:var(--green)">Seuil dépassé ✓</span>` + margeNote;
      }
      document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
    } else {
      document.getElementById('eco-seuil').textContent = '—';
      seuilSub.innerHTML = '<span style="color:var(--muted)">marge réelle non mesurable</span>';
      document.getElementById('eco-seuil-bar').style.width = '0%';
    }
  }

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

  // ── Graphe temporel : horaire (1j) ou journalier (multi-jours) ───────────
  const hourlyCanvas = document.getElementById('chart-hourly');
  const dailyCanvas  = document.getElementById('chart-daily');
  const timeLabel    = document.getElementById('time-chart-label');

  if (d.is_single_day && d.hourly) {
    hourlyCanvas.style.display = '';
    dailyCanvas.style.display  = 'none';
    timeLabel.textContent = 'CA par heure (€)';
    renderHourlyChart(d);
  } else if (d.daily && d.daily.length) {
    hourlyCanvas.style.display = 'none';
    dailyCanvas.style.display  = '';
    timeLabel.textContent = 'CA par jour (€)';
    renderDailyChart(d.daily);
  } else {
    hourlyCanvas.style.display = 'none';
    dailyCanvas.style.display  = 'none';
  }

  // ── Paiements compacts (remplace le donut) ───────────────────────────────
  const payEl = document.getElementById('payment-compact');
  if (!d.payments.labels.length) {
    payEl.innerHTML = '<p style="font-size:12px;color:var(--muted);">Aucun mouvement enregistré.</p>';
  } else {
    const total = d.payments.values.reduce((a, b) => a + b, 0);
    payEl.innerHTML = d.payments.labels.map((l, i) => {
      const val = d.payments.values[i];
      const pct = total > 0 ? Math.round(val / total * 100) : 0;
      return `<div class="pay-compact-row">
        <span class="pay-label">
          <span class="pay-dot" style="background:${COLORS[i]}"></span>${l}
        </span>
        <span class="pay-nums">${fmt(val)} · ${pct}%</span>
      </div>
      <div class="pay-bar-track">
        <div class="pay-bar-fill" style="width:${pct}%;background:${COLORS[i]}"></div>
      </div>`;
    }).join('');
  }

  // ── Mix produits + rentabilité par groupe ────────────────────────────────
  const MIX_COLORS = {'Boissons':'rgba(55,53,47,1)','Food':'rgba(55,53,47,.55)','Retail':'rgba(55,53,47,.3)'};
  if (d.mix && d.mix.length) {
    document.getElementById('mix-bars').innerHTML = d.mix.map(m => {
      const margeStr = m.marge_pct != null
        ? `marge ${marginBadge(m.marge_pct)} · ${fmt(m.marge_eur)}`
        : '<span style="color:var(--faint)">marge inconnue</span>';
      return `
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px;">
          <span style="color:var(--text);font-weight:500">${m.label}</span>
          <span style="font-weight:500">${m.pct}% <span style="color:var(--muted);font-weight:400">· ${fmt(m.amount)} HT</span></span>
        </div>
        <div style="height:4px;background:var(--bar-bg);border-radius:2px;">
          <div style="height:4px;background:${MIX_COLORS[m.label]||'#888'};border-radius:2px;width:${m.pct}%"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:3px;">
          <span>${margeStr}</span>
          ${m.coverage != null && m.coverage < 95 ? `<span style="color:var(--faint)">couv. ${m.coverage}%</span>` : ''}
        </div>
      </div>`;
    }).join('');
  } else {
    document.getElementById('mix-bars').innerHTML =
      '<span style="font-size:12px;color:var(--muted);">Aucune donnée</span>';
  }

  // Distribution tickets et TVA retirés du flux principal

  // ── WoW strip (sous sparkline) ────────────────────────────────────────────
  const wowStrip = document.getElementById('wow-strip');
  if (d.wow) {
    wowStrip.style.display = 'flex';
    document.getElementById('kpi-wow-ca').textContent = fmt(d.wow.cur_ca);
    document.getElementById('kpi-wow-ca-delta').innerHTML = d.wow.growth_ca != null
      ? `<span class="${d.wow.growth_ca >= 0 ? 'delta-up' : 'delta-down'}">${d.wow.growth_ca >= 0 ? '+' : ''}${d.wow.growth_ca}%</span>`
      : '';
    document.getElementById('kpi-wow-nb').textContent = d.wow.cur_nb;
    document.getElementById('kpi-wow-nb-delta').innerHTML = d.wow.growth_nb != null
      ? `<span class="${d.wow.growth_nb >= 0 ? 'delta-up' : 'delta-down'}">${d.wow.growth_nb >= 0 ? '+' : ''}${d.wow.growth_nb}%</span>`
      : '';
  } else {
    wowStrip.style.display = 'none';
  }
  if (d.weekdays && d.weekdays.length) {
    const best = d.weekdays[0];
    document.getElementById('kpi-best-day').textContent = best.day;
    document.getElementById('kpi-best-day-sub').textContent =
      `moy. ${fmt(best.avg_ca)}`;
  }

  // ── Courbe cumulative (jour unique) ───────────────────────────────────────
  const curveSection = document.getElementById('curve-section');
  if (d.is_single_day && d.curve && d.curve.length > 1) {
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
          borderWidth: 2, fill: true, tension: 0.3,
          pointRadius: d.curve.map((_, i) => i === 0 ? 0 : 4),
          pointBackgroundColor: BAR_ACTIVE, pointBorderColor: '#fff', pointBorderWidth: 2,
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
                return [` Cumul : ${fmt(ctx.raw)}`, pt.ca_tx ? ` + ${fmt(pt.ca_tx)}  (${pt.nb})` : ''].filter(Boolean);
              }
            }
          }
        },
        scales: {
          y: { beginAtZero: true, ticks:{callback:v=>v+' €',font:{size:11},color:'rgba(120,119,111,1)'}, grid:{color:'rgba(55,53,47,0.06)'}, border:{display:false} },
          x: { ticks:{font:{size:11},color:'rgba(120,119,111,1)',maxTicksLimit:12}, grid:{display:false}, border:{display:false} }
        }
      }
    });
  } else {
    curveSection.style.display = 'none';
  }

  // ── Rush detector (jour unique) ────────────────────────────────────────────
  const rushSection = document.getElementById('rush-section');
  if (d.is_single_day && d.rush && d.rush.length) {
    rushSection.style.display = '';
    document.getElementById('rush-list').innerHTML = d.rush.map(r =>
      `<span class="rush-badge">⚡ ${r.start}–${r.end} · ${r.count} tx</span>`
    ).join('');
  } else {
    rushSection.style.display = 'none';
  }

  // ── Produits (toggle période / 7j) ───────────────────────────────────────
  const topSection = document.getElementById('top-products-section');
  if (topSection) {
    topSection.style.display = '';
    // Mettre à jour le label selon la période active
    const periodLbl = d.is_single_day ? (d.is_today ? 'aujourd\'hui' : 'cette journée') : d.period_label?.toLowerCase() || 'la période';
    document.getElementById('products-section-label').textContent = `Produits vendus`;
    // Activer le tab période seulement si on a des items
    document.getElementById('tab-prod-period').style.display = d.has_items ? '' : 'none';
    if (!d.has_items && activeProdTab === 'period') switchProdTab('7d');
  }
  if (d.has_items && d.products) {
    const maxQty = d.products.length ? d.products[0].qty : 1;
    if (!d.products.length) {
      document.getElementById('products-body').innerHTML =
        '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">Aucun produit vendu.</td></tr>';
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
  }

  // ── CA moyen 7j par produit ───────────────────────────────────────────────
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


  // ── Produits non vendus (jour unique) ────────────────────────────────────
  const unsoldSection = document.getElementById('unsold-section');
  if (d.is_single_day && d.unsold && d.unsold.length) {
    unsoldSection.style.display = '';
    document.getElementById('unsold-list').innerHTML =
      d.unsold.map(p => `<span class="unsold-tag">${p.name}</span>`).join('');
  } else {
    unsoldSection.style.display = 'none';
  }

  // ── Transactions récentes ────────────────────────────────────────────────
  if (!d.recent || !d.recent.length) {
    document.getElementById('recent-body').innerHTML =
      '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:24px;">Aucune transaction.</td></tr>';
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

// ── Graphe horaire ─────────────────────────────────────────────────────────
function renderHourlyChart(d) {
  const maxHourVal = Math.max(...d.hourly.values);
  const hCtx = document.getElementById('chart-hourly').getContext('2d');
  if (chartHourly) chartHourly.destroy();
  chartHourly = new Chart(hCtx, {
    type: 'bar',
    data: {
      labels: d.hourly.labels,
      datasets: [
        {
          type: 'bar', label: 'CA',
          data: d.hourly.values,
          backgroundColor: d.hourly.values.map(v => v > 0 && v === maxHourVal ? BAR_ACTIVE : BAR_IDLE),
          borderRadius: 2, borderSkipped: false, yAxisID: 'y',
        },
        {
          type: 'line', label: 'Ticket moy.',
          data: d.hourly.avg_ticket,
          borderColor: BAR_ACTIVE, backgroundColor: 'transparent',
          borderWidth: 1.5, borderDash: [4, 3],
          pointRadius: d.hourly.avg_ticket.map(v => v != null ? 3 : 0),
          pointBackgroundColor: BAR_ACTIVE,
          spanGaps: false, yAxisID: 'y2',
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
                return ` CA: ${fmt(ctx.raw)}  (${nb} tx${gap != null ? ' · ' + gap + 'min/tx' : ''})`;
              }
              return ctx.raw != null ? ` Ticket moy: ${fmt(ctx.raw)}` : null;
            }
          }
        }
      },
      scales: {
        y:  { ticks:{callback:v=>v+' €',font:{size:11},color:'rgba(120,119,111,1)'}, grid:{color:'rgba(55,53,47,0.06)'}, border:{display:false} },
        y2: { position:'right', ticks:{callback:v=>v+' €',font:{size:10},color:'#bbb'}, grid:{display:false}, border:{display:false} },
        x:  { ticks:{font:{size:11},color:'rgba(120,119,111,1)'}, grid:{display:false}, border:{display:false} }
      }
    }
  });
}

// ── Graphe journalier (multi-jours) ───────────────────────────────────────
function renderDailyChart(daily) {
  const maxVal = Math.max(...daily.map(d => d.ca_ttc)) || 1;
  const dCtx = document.getElementById('chart-daily').getContext('2d');
  if (chartDaily) chartDaily.destroy();
  chartDaily = new Chart(dCtx, {
    type: 'bar',
    data: {
      labels: daily.map(d => {
        const dt = new Date(d.date + 'T12:00:00');
        return dt.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
      }),
      datasets: [{
        data: daily.map(d => d.ca_ttc),
        backgroundColor: daily.map(d => d.ca_ttc === maxVal ? BAR_ACTIVE : BAR_IDLE),
        borderRadius: 3, borderSkipped: false,
      }]
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const day = daily[ctx.dataIndex];
              return ` ${fmt(ctx.raw)} · ${day.nb} tx`;
            }
          }
        }
      },
      scales: {
        y: { beginAtZero: true, ticks:{callback:v=>v+' €',font:{size:11},color:'rgba(120,119,111,1)'}, grid:{color:'rgba(55,53,47,0.06)'}, border:{display:false} },
        x: { ticks:{font:{size:11},color:'rgba(120,119,111,1)',maxTicksLimit:16}, grid:{display:false}, border:{display:false} }
      }
    }
  });
}

// ── Drawer ticket ──────────────────────────────────────────────────────────
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
  document.getElementById('drawer-total').innerHTML = `<span>Total</span><span>${fmt(t.amount)}</span>`;
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

// ── Toggle tableau produits ────────────────────────────────────────────────
function switchProdTab(tab) {
  activeProdTab = tab;
  document.getElementById('prod-view-period').style.display = tab === 'period' ? '' : 'none';
  document.getElementById('prod-view-7d').style.display     = tab === '7d'     ? '' : 'none';
  document.getElementById('tab-prod-period').classList.toggle('active', tab === 'period');
  document.getElementById('tab-prod-7d').classList.toggle('active',     tab === '7d');
}

// ── Init ───────────────────────────────────────────────────────────────────
loadData();
setInterval(() => { if (currentPreset === 'today') loadData(); }, 5 * 60 * 1000);
