const COLORS = ['rgba(55,53,47,1)','rgba(55,53,47,.65)','rgba(55,53,47,.4)','rgba(55,53,47,.25)','rgba(55,53,47,.12)','rgba(55,53,47,.07)'];
const BAR_ACTIVE = 'rgba(55,53,47,0.85)';
const BAR_IDLE   = 'rgba(55,53,47,0.12)';
let chartHourly = null, chartWeek = null;
let chartCurve  = null, chartDaily = null;
let activeProdTab = 'period'; // 'period' | '7d'

// ── Preset actif ──────────────────────────────────────────────────────────────
let currentPreset = 'today';
let customStart = null, customEnd = null;

function setPreset(p) {
  currentPreset = p;
  document.getElementById('custom-range-bar').style.display = 'none';
  document.querySelectorAll('.pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === p);
  });
  loadData();
}

function openCustomRange() {
  const bar = document.getElementById('custom-range-bar');
  bar.style.display = bar.style.display === 'none' ? 'flex' : 'none';
  document.querySelectorAll('.pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === 'custom');
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
  const pct = ((cur - prev) / Math.abs(prev) * 100).toFixed(0);
  const cls = pct >= 0 ? 'delta-up' : 'delta-down';
  return `<span class="${cls}">${pct >= 0 ? '+' : ''}${pct}% ${label}</span>`;
}

function fmtDate(iso) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
}

// ── Chargement (stale-while-revalidate) ──────────────────────────────────────
// Affiche instantanément les dernières données connues (localStorage), puis
// rafraîchit en arrière-plan. force=true (bouton ↻) bypasse les caches serveur.
async function loadData(force = false) {
  const preset = currentPreset;
  const isCustom = preset === 'custom' && customStart && customEnd;
  const cacheKey = 'estu_data_' + preset + (isCustom ? '_' + customStart + '_' + customEnd : '');
  if (!force) {
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) render(JSON.parse(cached));
    } catch(e) {}
  }
  if (window.uiLoadStart) uiLoadStart();
  try {
    const url = isCustom
      ? `/api/data?preset=custom&start_date=${customStart}&end_date=${customEnd}${force ? '&fresh=1' : ''}`
      : '/api/data?preset=' + preset + (force ? '&fresh=1' : '');
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
      + ' (' + new Date(d.from_date+'T12:00:00').toLocaleDateString('en-GB', {day:'numeric',month:'short'})
      + ' → ' + new Date(d.to_date  +'T12:00:00').toLocaleDateString('en-GB', {day:'numeric',month:'short',year:'numeric'})
      + ')';
  }
  document.getElementById('subtitle').textContent = subtitle;

  // Label KPI dynamique
  const kpiLabel = d.is_single_day
    ? (d.is_today ? 'Today' : fmtDate(d.date).replace(/^\w/, c => c.toUpperCase()))
    : d.period_label;
  document.getElementById('kpi-section-label').textContent = kpiLabel;

  // Mis à jour
  const updatedEl = document.getElementById('updated-at');
  if (d.is_today) {
    updatedEl.textContent = 'Updated at ' + d.updated_at;
    updatedEl.style.display = '';
  } else {
    updatedEl.style.display = 'none';
  }

  // Label comparaison
  const compLabel = d.is_single_day ? 'vs yesterday' : 'vs prev. period';

  // ── KPIs ─────────────────────────────────────────────────────────────────
  document.getElementById('kpi-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    document.getElementById('kpi-ca-ht').textContent =
      `${fmt(d.economics.ca_ht)} excl. VAT · VAT ${fmt(d.economics.tva_collectee)}`;
  } else {
    document.getElementById('kpi-ca-ht').textContent = '';
  }
  document.getElementById('kpi-ca-delta').innerHTML     = delta(d.today.ca,     d.yesterday.ca,     compLabel);
  document.getElementById('kpi-nb').textContent         = d.today.nb;
  document.getElementById('kpi-nb-delta').innerHTML     = delta(d.today.nb,     d.yesterday.nb,     compLabel);
  document.getElementById('kpi-ticket').textContent     = fmt(d.today.ticket);
  document.getElementById('kpi-ticket-delta').innerHTML = delta(d.today.ticket, d.yesterday.ticket, compLabel)
    + (d.today.ticket_ht ? `<span style="color:var(--faint)"> · ${fmt(d.today.ticket_ht)} excl. VAT</span>` : '');
  document.getElementById('kpi-median').textContent     = d.median != null ? fmt(d.median) : '—';

  // Seuil transactions — proportionnel aux jours ouvrés de la période
  const openDaysTx = (d.economics && d.economics.open_days) || 1;
  const seuilTarget = d.seuil * (d.is_single_day ? 1 : openDaysTx);
  const pct = Math.min(100, Math.round(d.today.nb / seuilTarget * 100));
  document.getElementById('seuil-bar').style.width = pct + '%';
  document.getElementById('seuil-meta').textContent = d.is_single_day
    ? `Break-even: ${d.seuil} tx/day`
    : `Break-even: ${seuilTarget} tx (${d.seuil}/day × ${openDaysTx} open days)`;


  // ── Économie ──────────────────────────────────────────────────────────────
  // Labels dynamiques selon la période
  const periodSuffix = d.is_single_day ? '(day)' : `· ${d.n_days} days`;
  document.getElementById('eco-label').textContent      = `Economics ${periodSuffix}`;
  document.getElementById('eco-charges-label').textContent = `Costs ${periodSuffix}`;
  document.getElementById('eco-ebitda-label').textContent  = `EBITDA ${periodSuffix}`;
  document.getElementById('eco-seuil-label').textContent   = `Break-even revenue ${periodSuffix}`;
  document.getElementById('eco-marge-label').textContent   = 'Gross margin';

  const eco = d.economics;
  if (eco) {
    // Marge brute — 100% COGS réel, avec taux de couverture
    document.getElementById('eco-marge').textContent = eco.marge_brute_ht != null ? fmt(eco.marge_brute_ht) : '—';
    if (eco.marge_brute_ht != null) {
      const cov = eco.cogs_coverage_pct;
      const covColor = cov >= 90 ? 'var(--green)' : cov >= 60 ? '#b07d00' : 'var(--red)';
      const covStr = cov != null
        ? `<span style="color:${covColor}">COGS coverage ${cov}%</span>`
        : '';
      document.getElementById('eco-marge-pct').innerHTML =
        `${eco.marge_brute_ht_pct}% <span style="color:var(--faint)">· COGS ${fmt(eco.cogs_ht)} · </span>${covStr}`;
    } else {
      document.getElementById('eco-marge-pct').innerHTML =
        '<span style="color:var(--muted)">no COGS set — complete your recipe sheets</span>';
    }

    // Charges — utilise les totaux période et open_days (pas n_days calendaires)
    document.getElementById('eco-charges').textContent = fmt(eco.cout_total_periode ?? eco.cout_total_jour);
    const openDays = eco.open_days || d.n_days;
    const chargesSub = d.is_single_day
      ? `Fixed ${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} · Staff ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)}`
      : `${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} fixed · ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)} staff · <span style="color:var(--faint)">${openDays} open days × ${fmt(eco.cout_jour ?? (eco.cout_total_jour / openDays))}/day</span>`;
    document.getElementById('eco-charges-sub').innerHTML = chargesSub;

    // EBITDA
    const ebitdaEl = document.getElementById('eco-ebitda');
    ebitdaEl.textContent = eco.ebitda_ht != null ? fmt(eco.ebitda_ht) : '—';
    ebitdaEl.style.color = eco.ebitda_ht > 0 ? 'var(--green)' : eco.ebitda_ht < 0 ? 'var(--red)' : 'var(--text)';
    const ebitdaSub = document.getElementById('eco-ebitda-sub');
    if (eco.ebitda_ht != null) {
      ebitdaSub.innerHTML = eco.ebitda_ht > 0
        ? `<span style="color:var(--green)">Profitable ✓</span>`
        : `<span style="color:var(--red)">Loss ${fmt(Math.abs(eco.ebitda_ht))}</span>`;
    }

    // Seuil CA — TTC en principal, calculé sur la marge réelle mesurée
    const seuilSub = document.getElementById('eco-seuil-sub');
    if (eco.seuil_ca_ttc != null) {
      document.getElementById('eco-seuil').textContent = fmt(eco.seuil_ca_ttc);
      const margeNote = eco.seuil_margin_pct != null
        ? ` <span style="color:var(--faint)">· real margin ${eco.seuil_margin_pct}%</span>`
        : '';
      if (eco.manque_seuil > 0) {
        seuilSub.innerHTML = `<span style="color:var(--red)">${fmt(eco.manque_seuil)} short (incl. VAT)</span>` + margeNote;
      } else {
        seuilSub.innerHTML = `<span style="color:var(--green)">Break-even reached ✓</span>` + margeNote;
      }
      document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
    } else {
      document.getElementById('eco-seuil').textContent = '—';
      seuilSub.innerHTML = '<span style="color:var(--muted)">real margin not measurable</span>';
      document.getElementById('eco-seuil-bar').style.width = '0%';
    }
  }

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
    payEl.innerHTML = '<p style="font-size:12px;color:var(--muted);">No movements recorded.</p>';
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
  const MIX_COLORS = {'Drinks':'rgba(55,53,47,1)','Food':'rgba(55,53,47,.55)','Viennoiserie':'rgba(55,53,47,.35)','Retail':'rgba(55,53,47,.18)'};
  if (d.mix && d.mix.length) {
    document.getElementById('mix-bars').innerHTML = d.mix.map(m => {
      const margeStr = m.marge_pct != null
        ? `margin ${marginBadge(m.marge_pct)} · ${fmt(m.marge_eur)}`
        : '<span style="color:var(--faint)">margin unknown</span>';
      return `
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px;">
          <span style="color:var(--text);font-weight:500">${m.label}</span>
          <span style="font-weight:500">${m.pct}% <span style="color:var(--muted);font-weight:400">· ${fmt(m.amount_ttc ?? m.amount)} incl.VAT <span style="color:var(--faint)">(${fmt(m.amount)} excl.VAT)</span></span></span>
        </div>
        <div style="height:4px;background:var(--bar-bg);border-radius:2px;">
          <div style="height:4px;background:${MIX_COLORS[m.label]||'#888'};border-radius:2px;width:${m.pct}%"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:3px;">
          <span>${margeStr}</span>
          ${m.coverage != null && m.coverage < 95 ? `<span style="color:var(--faint)">cov. ${m.coverage}%</span>` : ''}
        </div>
      </div>`;
    }).join('');
  } else {
    document.getElementById('mix-bars').innerHTML =
      '<span style="font-size:12px;color:var(--muted);">No data</span>';
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
    const periodLbl = d.is_single_day ? (d.is_today ? 'today' : 'this day') : d.period_label?.toLowerCase() || 'the period';
    document.getElementById('products-section-label').textContent = `Products sold`;
    // Activer le tab période seulement si on a des items
    document.getElementById('tab-prod-period').style.display = d.has_items ? '' : 'none';
    if (!d.has_items && activeProdTab === 'period') switchProdTab('7d');
  }
  if (d.has_items && d.products) {
    const maxQty = d.products.length ? d.products[0].qty : 1;
    if (!d.products.length) {
      document.getElementById('products-body').innerHTML =
        '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">No products sold.</td></tr>';
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
      '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px;">No data over 7 days.</td></tr>';
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
      '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:24px;">No transactions.</td></tr>';
    return;
  }
  window._txData = d.recent;
  const recCount = document.getElementById('recent-count');
  if (recCount) recCount.textContent = d.is_single_day
    ? `${d.recent.length} transaction${d.recent.length > 1 ? 's' : ''}`
    : `${d.recent.length} latest`;
  const recLabel = document.getElementById('recent-label');
  if (recLabel) recLabel.textContent = d.is_single_day ? "Today's transactions" : 'Recent transactions';
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

// ── Insights visuels ───────────────────────────────────────────────────────
const WD_SHORT = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

function renderInsights(d) {
  const ins  = d.insights;
  const grid = document.getElementById('insights-grid');
  const lbl  = document.getElementById('insights-label');
  if (!ins) { grid.classList.remove('on'); if (lbl) lbl.style.display = 'none'; return; }
  grid.classList.add('on');
  if (lbl) lbl.style.display = '';

  // 1. Jauge du jour vs break-even
  const g = ins.today_gauge || {};
  if (g.seuil) {
    const pct = Math.min(100, Math.round(g.ca / g.seuil * 100));
    const done = g.ca >= g.seuil;
    const barColor = done ? 'var(--green)' : (pct >= 70 ? '#b07d00' : 'var(--red)');
    document.getElementById('ins-gauge').innerHTML = `
      <div class="ins-label">Today vs break-even (live)</div>
      <div class="ins-big">${fmt(g.ca)} <span style="font-size:12px;color:var(--muted);font-weight:400">/ ${fmt(g.seuil)}</span></div>
      <div style="height:8px;background:var(--bar-bg);border-radius:4px;margin-top:10px;overflow:hidden;">
        <div style="width:${pct}%;height:8px;background:${barColor};border-radius:4px;"></div>
      </div>
      <div class="ins-sub">${done
        ? `<span style="color:var(--green)">Break-even reached ✓ · +${fmt(g.ca - g.seuil)}</span>`
        : `${pct}% — ${fmt(g.seuil - g.ca)} to go`}</div>`;
  } else {
    document.getElementById('ins-gauge').innerHTML = `
      <div class="ins-label">Today vs break-even (live)</div>
      <div class="ins-sub">Break-even not measurable yet today.</div>`;
  }

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
        html += `<div class="hm-cell" style="${v ? `background:rgba(55,53,47,${(0.10 + a * 0.75).toFixed(2)});` : ''}" title="${WD_SHORT[wd]} ${h}h · ${fmt(v)}"></div>`;
      }
    }
    html += `</div>`;
    const rush = ins.rush;
    const rushLine = rush
      ? `<strong>${rush.top_share}%</strong> of revenue in the 3 busiest hours (${rush.hours.map(h => h + 'h').join(', ')})`
      : 'darker = more revenue · hours 8–16';
    document.getElementById('ins-heatmap').innerHTML = `
      <div class="ins-label">Rush heatmap — revenue by hour (28 days)</div>
      ${html}
      <div class="ins-sub">${rushLine}</div>`;
  } else {
    document.getElementById('ins-heatmap').innerHTML = `<div class="ins-label">Rush heatmap</div><div class="ins-sub">Not enough data yet.</div>`;
  }

  // 3+4. Mois : cumul EBITDA + projection / calendrier break-even
  const m = ins.month;
  if (m && m.days && m.days.length) {
    const opens = m.days.filter(x => x.open);
    const pts   = opens.map(x => x.cum);
    const allVals = pts.concat([m.proj_end, 0]);
    const lo = Math.min(...allVals), hi = Math.max(...allVals);
    const W = 600, H = 100, span = (hi - lo) || 1;
    const y = v => 8 + (H - 16) * (1 - (v - lo) / span);
    const n = opens.length;
    const x = i => n > 1 ? (i / (n - 1)) * (W * 0.72) : 0;
    const path = pts.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const projPath = `M${x(n - 1).toFixed(1)},${y(pts[n - 1]).toFixed(1)} L${W - 4},${y(m.proj_end).toFixed(1)}`;
    document.getElementById('ins-month').innerHTML = `
      <div class="ins-label">Month EBITDA — cumulative + projection</div>
      <svg class="ins-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <line x1="0" y1="${y(0).toFixed(1)}" x2="${W}" y2="${y(0).toFixed(1)}" stroke="var(--border)" stroke-width="1.5"/>
        <path d="${path}" fill="none" stroke="rgba(55,53,47,.85)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
        <path d="${projPath}" fill="none" stroke="rgba(55,53,47,.4)" stroke-width="2.5" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="ins-sub">
        MTD <strong style="color:${m.cum_now >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.cum_now)}</strong>
        · projected <strong style="color:${m.proj_end >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.proj_end)}</strong> by month end
        ${m.cross_date ? ` · crossed €0 on ${new Date(m.cross_date + 'T12:00:00').toLocaleDateString('en-GB', {day:'numeric', month:'short'})}` : ''}
      </div>`;

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
      cal += `<div class="cal-cell" style="background:${bg};color:${color};" title="${day.date}${day.ebitda != null ? ' · ' + fmt(day.ebitda) : ''}">${dt.getDate()}</div>`;
    }
    const greens = opens.filter(x => x.ebitda >= 0).length;
    document.getElementById('ins-calendar').innerHTML = `
      <div class="ins-label">Break-even calendar</div>
      <div class="cal-grid">${cal}</div>
      <div class="ins-sub">green = above break-even · ${greens}/${opens.length} open days</div>`;
  } else {
    document.getElementById('ins-month').innerHTML = `<div class="ins-label">Month EBITDA</div><div class="ins-sub">Not enough data yet.</div>`;
    document.getElementById('ins-calendar').innerHTML = `<div class="ins-label">Break-even calendar</div><div class="ins-sub">Not enough data yet.</div>`;
  }

  // 5. Prime cost (période sélectionnée)
  const eco = d.economics || {};
  const perso = eco.cout_perso_periode ?? eco.cout_perso_jour;
  if (eco.ca_ht > 0 && eco.cogs_ht != null && perso != null) {
    const prime = (eco.cogs_ht + perso) / eco.ca_ht * 100;
    const pc = Math.min(100, Math.max(0, prime));
    const color = prime <= 67 ? 'var(--green)' : prime <= 75 ? '#b07d00' : 'var(--red)';
    const cogsPct = eco.marge_brute_ht_pct != null ? (100 - eco.marge_brute_ht_pct) : (eco.cogs_ht / eco.ca_ht * 100);
    const labPct  = perso / eco.ca_ht * 100;
    const cCol = cogsPct <= 32 ? 'var(--green)' : cogsPct <= 38 ? '#b07d00' : 'var(--red)';
    const lCol = labPct  <= 32 ? 'var(--green)' : labPct  <= 40 ? '#b07d00' : 'var(--red)';
    document.getElementById('ins-prime').innerHTML = `
      <div class="ins-label">Prime cost — COGS + labour (${d.period_label.toLowerCase()})</div>
      <div class="ins-big" style="color:${color}">${prime.toFixed(1)}%</div>
      <div style="display:flex;height:8px;border-radius:4px;overflow:hidden;margin-top:10px;background:var(--bar-bg);">
        <div style="width:${Math.min(100,cogsPct)}%;background:rgba(55,53,47,.75);"></div>
        <div style="width:${Math.min(100,labPct)}%;background:rgba(55,53,47,.35);"></div>
      </div>
      <div class="ins-sub">
        <span style="color:${cCol}">COGS ${cogsPct.toFixed(0)}%</span> ·
        <span style="color:${lCol}">Labour ${labPct.toFixed(0)}%</span>
        <span style="color:var(--faint)"> — targets 28–32% each · prime &lt;65%</span>
      </div>`;
  } else {
    document.getElementById('ins-prime').innerHTML = `<div class="ins-label">Prime cost</div><div class="ins-sub">Not measurable for this period.</div>`;
  }

  // 5b. Articles par ticket (attach)
  const bk = ins.basket;
  if (bk && bk.items_per_ticket != null) {
    document.getElementById('ins-basket').innerHTML = `
      <div class="ins-label">Items per ticket (${d.period_label.toLowerCase()})</div>
      <div class="ins-big">${bk.items_per_ticket.toFixed(2)}</div>
      <div class="ins-sub">${bk.attach_pct}% of tickets have 2+ items — the cheapest growth lever</div>`;
  } else {
    document.getElementById('ins-basket').innerHTML = `<div class="ins-label">Items per ticket</div><div class="ins-sub">Not enough data yet.</div>`;
  }

  // 7. CA par place assise
  const st = ins.seat;
  if (st && st.per_seat_day != null) {
    document.getElementById('ins-seat').innerHTML = `
      <div class="ins-label">Revenue per seat / open day</div>
      <div class="ins-big">${fmt(st.per_seat_day)}</div>
      <div class="ins-sub">${st.seats} seats (${st.terrace} terrace + ${st.inside} inside) · ${fmt(st.per_seat_period)}/seat over the period</div>`;
  } else {
    document.getElementById('ins-seat').innerHTML = `<div class="ins-label">Revenue per seat</div><div class="ins-sub">Not enough data yet.</div>`;
  }

  // 6. Top movers semaine vs semaine
  const mv = ins.movers || {};
  const rowHtml = (c, up) => `
    <div class="mv-row">
      <span class="mv-name">${c.name}</span>
      <span style="color:${up ? 'var(--green)' : 'var(--red)'};font-weight:500;white-space:nowrap;">
        ${c.pct == null ? 'new' : (up ? '▲ +' : '▼ ') + c.pct + '%'}
        <span style="color:var(--faint);font-weight:400;">· ${fmt(c.cur)}</span>
      </span>
    </div>`;
  const rowsHtml = (mv.up || []).map(c => rowHtml(c, true)).join('')
                 + (mv.down || []).map(c => rowHtml(c, false)).join('');
  document.getElementById('ins-movers').innerHTML = `
    <div class="ins-label">Top movers — last 7 days vs previous 7</div>
    ${rowsHtml || '<div class="ins-sub">Not enough history yet.</div>'}`;
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
        return dt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
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

// ── Toggle tableau produits ────────────────────────────────────────────────
function switchProdTab(tab) {
  activeProdTab = tab;
  document.getElementById('prod-view-period').style.display = tab === 'period' ? '' : 'none';
  document.getElementById('prod-view-7d').style.display     = tab === '7d'     ? '' : 'none';
  document.getElementById('tab-prod-period').classList.toggle('active', tab === 'period');
  document.getElementById('tab-prod-7d').classList.toggle('active',     tab === '7d');
}

// ── Overview / Cashflow ───────────────────────────────────────────────────
let cashflowData = null;   // chargé une seule fois, mis en cache côté client
let chartCashflow = null;

function switchDashView(view) {
  document.getElementById('view-overview').style.display = view === 'overview' ? '' : 'none';
  document.getElementById('view-cashflow').style.display = view === 'cashflow' ? '' : 'none';
  document.getElementById('tab-view-overview').classList.toggle('active', view === 'overview');
  document.getElementById('tab-view-cashflow').classList.toggle('active', view === 'cashflow');
  if (view === 'cashflow' && !cashflowData) loadCashflow();
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

  const totalIn  = months.reduce((s, m) => s + m.revenue, 0);
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
        { type: 'bar', label: 'Cash in',  data: months.map(m => m.revenue),
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
      <td class="amount">${fmt(m.revenue)}</td>
      <td class="amount">${fmt(m[outKey])}</td>
      <td class="amount" style="color:${netVal >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:500;">${fmt(netVal)}</td>
      <td class="amount" style="color:${cumVal >= 0 ? 'var(--green)' : 'var(--red)'};">${fmt(cumVal)}</td>
    </tr>`;
  }).join('');
}

// ── Init ───────────────────────────────────────────────────────────────────
loadData();
setInterval(() => { if (currentPreset === 'today') loadData(); }, 5 * 60 * 1000);
