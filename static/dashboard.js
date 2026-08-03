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
  const pct = Math.round((cur - prev) / Math.abs(prev) * 100);
  const up = pct >= 0;
  // Pastille Mesa (flèche + %) suivie du libellé en gris.
  return `<span class="${up ? 'delta-up' : 'delta-down'}">${up ? '▲ +' : '▼ '}${pct}%</span>`
       + `<span style="color:var(--muted);margin-left:8px;font-size:11.5px;">${label}</span>`;
}

// Pastille seule (flèche + %), sans libellé — pour le strip Today.
function deltaBadge(cur, prev) {
  if (prev == null || prev === 0) return '';
  const pct = Math.round((cur - prev) / Math.abs(prev) * 100);
  const up = pct >= 0;
  return `<span class="${up ? 'delta-up' : 'delta-down'}">${up ? '▲ +' : '▼ '}${pct}%</span>`;
}

// "Sat 18 Jul"
function dayShort(iso) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

// Strip "Today" : snapshot du jour + delta vs jour ouvré précédent.
function renderTodayStrip(d) {
  const strip = document.getElementById('today-strip');
  const todayIso = new Date().toISOString().slice(0, 10);
  const includesToday = !d.is_single_day && d.to_date === todayIso && Array.isArray(d.week);
  if (!includesToday) { strip.style.display = 'none'; return; }

  const wk = d.week;
  const today = wk[wk.length - 1];                     // dernier point = aujourd'hui
  // Comparaison au MÊME JOUR DE LA SEMAINE précédente (samedi vs samedi), à
  // heure égale — pas au jour précédent, qui n'a pas la même saisonnalité.
  const prev = d.today_lastweek
    || [...wk.slice(0, -1)].reverse().find(x => x.nb > 0)   // repli si indisponible
    || null;
  const tTicket = today.nb ? today.ca / today.nb : 0;
  const pTicket = prev && prev.nb ? prev.ca / prev.nb : 0;
  const vs = prev ? `vs ${dayShort(prev.date)}${d.today_lastweek ? ' same time' : ''} · ` : '';

  document.getElementById('ts-ca').textContent      = fmt(today.ca);
  document.getElementById('ts-ca-badge').innerHTML  = prev ? deltaBadge(today.ca, prev.ca) : '';
  document.getElementById('ts-ca-sub').textContent  = prev ? vs + fmt(prev.ca) : '';
  document.getElementById('ts-nb').textContent      = today.nb;
  document.getElementById('ts-nb-badge').innerHTML  = prev ? deltaBadge(today.nb, prev.nb) : '';
  document.getElementById('ts-nb-sub').textContent  = prev ? vs + prev.nb : '';
  document.getElementById('ts-ticket').textContent  = fmt(tTicket);
  document.getElementById('ts-ticket-badge').innerHTML = (prev && prev.nb && today.nb) ? deltaBadge(tTicket, pTicket) : '';
  document.getElementById('ts-ticket-sub').textContent = (prev && prev.nb) ? vs + fmt(pTicket) : '';
  strip.style.display = '';
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
// ══ LE TRAJET ══════════════════════════════════ testé : tests/test_flux.js ══
//
// L'écran n'énonce pas un résultat, il le montre se construire : ce qui entre, ce qui sort,
// ce qui reste. Chaque poste part du niveau atteint par le précédent — la cascade rend le
// décalage visible là où quatre KPI côte à côte le laissaient à reconstituer de tête.
//
// ⚠️ LA MATIÈRE N'EST PAS `cogs_ht`. `cogs_ht` est le coût mesuré sur la seule part des ventes
// dont on connaît le prix d'achat. Ce qui est réellement retranché du CA HT pour arriver à la
// marge brute, c'est `ca_ht − marge_brute_ht` : le taux mesuré, appliqué à tout le CA. Les deux
// coïncident quand la couverture est de 100 % et divergent sinon — soustraire `cogs_ht` ferait
// atterrir la cascade ailleurs que sur l'EBITDA affiché juste à côté.
//
// La cascade est donc construite pour tomber SUR `ebitda_ht` par construction, et non sur une
// somme recalculée qui pourrait dériver du chiffre du serveur.
//
// ⚠️ ET ELLE NE S'AFFICHE PAS À MOITIÉ. Sans marge mesurable ou sans charges connues, il n'y a
// pas de trajet : on dit lequel manque. Une cascade avec un segment à zéro se lirait « ce poste
// ne coûte rien ».

function fluxSteps(eco) {
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
  const e = eco || {};
  const caTtc = num(e.ca_ttc), caHt = num(e.ca_ht);
  const marge = num(e.marge_brute_ht), ebitda = num(e.ebitda_ht);
  const fixe  = num(e.cout_fixe_periode)  ?? num(e.cout_fixe_jour);
  const perso = num(e.cout_perso_periode) ?? num(e.cout_perso_jour);

  if (!caTtc || caTtc <= 0)  return { ok: false, reason: 'no-sales' };
  if (caHt === null)         return { ok: false, reason: 'no-net' };
  if (marge === null)        return { ok: false, reason: 'no-margin' };
  if (fixe === null || perso === null || (fixe + perso) <= 0)
                             return { ok: false, reason: 'no-costs' };
  if (ebitda === null)       return { ok: false, reason: 'no-ebitda' };

  const est = e.marge_is_estimated === true;
  const steps = [
    { key: 'revenue',  label: 'CA TTC',      amount: caTtc,        after: caTtc, kind: 'in'  },
    { key: 'vat',      label: '− TVA',       amount: caTtc - caHt, after: caHt,  kind: 'tax' },
    { key: 'cogs',     label: '− matière',   amount: caHt - marge, after: marge, kind: 'out', estimated: est },
    { key: 'fixed',    label: '− charges',   amount: fixe,         after: marge - fixe,        kind: 'out' },
    { key: 'staff',    label: '− personnel', amount: perso,        after: marge - fixe - perso, kind: 'out' },
  ];

  // Le dernier palier DOIT être l'EBITDA du serveur. S'il ne l'est pas, un poste manque au
  // modèle : mieux vaut ne rien dessiner que dessiner une cascade qui ment d'un écart muet.
  if (Math.abs(steps[steps.length - 1].after - ebitda) > 0.02)
    return { ok: false, reason: 'mismatch', drift: steps[steps.length - 1].after - ebitda };

  const top = caTtc, bottom = Math.min(0, ebitda), span = (top - bottom) || 1;
  const pct = v => (v / span) * 100;
  const laid = steps.map((s, i) => {
    const from = i === 0 ? 0 : steps[i - 1].after;
    const to   = s.after;
    return { ...s,
      left:  i === 0 ? 0 : pct(top - from),
      width: i === 0 ? pct(s.amount) : pct(from - to) };
  });

  return { ok: true, steps: laid, ebitda, estimated: est,
           zeroPct: pct(top), coverage: num(e.cogs_coverage_pct) };
}

function renderFlux(d) {
  const el = document.getElementById('flux');
  if (!el) return;
  const f = fluxSteps(d && d.economics);
  const scope = d && d.period_label ? d.period_label : '';

  if (!f.ok) {
    const why = {
      'no-sales':  'aucune vente sur la période.',
      'no-net':    'le CA hors taxes est indisponible.',
      'no-margin': 'le coût matière n’est pas mesurable — complète les fiches recettes.',
      'no-costs':  'les charges sont indisponibles — vérifie l’onglet Costs.',
      'no-ebitda': 'le résultat n’est pas calculable.',
      'mismatch':  'les postes ne se recomposent pas en EBITDA — un coût manque au modèle.',
    }[f.reason] || 'données insuffisantes.';
    el.innerHTML = `<div class="flux-head"><span class="flux-title">Le trajet</span>
        <span class="flux-scope">${scope}</span></div>
      <div class="flux-empty">Pas de trajet à tracer : ${why}</div>`;
    return;
  }

  const colour = { in: 'var(--flux-keep)', tax: 'var(--flux-tax)', out: 'var(--flux-leave)' };
  const rows = f.steps.map(s => `
    <div class="flux-row">
      <span class="flux-label">${s.label}</span>
      <span class="flux-track">
        <span class="flux-seg${s.estimated ? ' is-estimated' : ''}"
              style="left:${s.left}%;width:${s.width}%;background:${colour[s.kind]}"></span>
      </span>
      <span class="flux-amount${s.kind === 'in' ? '' : ' dim'}">${s.kind === 'in' ? '' : '−'}${fmt(s.amount)}</span>
    </div>`).join('');

  const neg = f.ebitda < 0;
  const ebW = Math.abs((f.ebitda / (f.steps[0].amount - Math.min(0, f.ebitda))) * 100);
  const ebLeft = neg ? f.zeroPct : f.zeroPct - ebW;
  const total = `
    <div class="flux-row is-total">
      <span class="flux-label">= EBITDA</span>
      <span class="flux-track"><span class="flux-zero" style="left:${f.zeroPct}%"></span>
        <span class="flux-seg" style="left:${ebLeft}%;width:${ebW}%;
              background:${neg ? 'var(--flux-neg)' : 'var(--flux-keep)'}"></span></span>
      <span class="flux-amount${neg ? ' neg' : ''}">${fmt(f.ebitda)}</span>
    </div>`;

  // La lecture, écrite. Le graphique montre le décalage ; la phrase nomme le poste qui pèse.
  const matiere = f.steps.find(s => s.key === 'cogs');
  const charges = f.steps.filter(s => s.kind === 'out' && s.key !== 'cogs')
                         .reduce((a, s) => a + s.amount, 0);
  const verdict = neg
    ? `Il manque <b>${fmt(-f.ebitda)}</b> pour couvrir la période.`
    : `La période dégage <b>${fmt(f.ebitda)}</b>.`;
  const poids = matiere.amount < charges
    ? `La matière pèse <b>${fmt(matiere.amount)}</b>, les charges <b>${fmt(charges)}</b>.`
    : `La matière pèse <b>${fmt(matiere.amount)}</b>, plus que les <b>${fmt(charges)}</b> de charges.`;
  const reserve = f.estimated
    ? ` <span class="est">La matière est extrapolée : le coût n’est connu que sur ${f.coverage}% des ventes.</span>`
    : '';

  el.innerHTML = `
    <div class="flux-head"><span class="flux-title">Le trajet</span>
      <span class="flux-scope">${scope}</span></div>
    <div class="flux-rows">${rows}${total}</div>
    <div class="flux-note">${poids} ${verdict}${reserve}</div>
    <div class="flux-legend">
      <span><i style="background:var(--flux-keep)"></i>ce qui reste</span>
      <span><i style="background:var(--flux-leave)"></i>ce qui sort</span>
      <span><i style="background:var(--flux-tax)"></i>TVA</span>
      ${f.estimated ? '<span><i class="flux-seg is-estimated" style="background:var(--flux-leave)"></i>extrapolé</span>' : ''}
    </div>`;
}

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

  // Label comparaison — en vue "aujourd'hui live", comparaison à la même heure
  // du dernier jour ouvré (sinon la métrique est faussée avant la fermeture).
  const compLabel = d.comp_label || (d.is_single_day ? 'vs yesterday' : 'vs prev. period');

  // ── KPIs ─────────────────────────────────────────────────────────────────
  document.getElementById('kpi-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    document.getElementById('kpi-ca-ht').textContent =
      `${fmt(d.economics.ca_ht)} excl. VAT · VAT ${fmt(d.economics.tva_collectee)}`;
  } else {
    document.getElementById('kpi-ca-ht').textContent = '';
  }
  // Deltas "vs yesterday" seulement en jour unique. En multi-jours, le strip
  // Today porte la comparaison ; le bloc période reste descriptif (comme Mesa).
  // Deltas vs période de comparaison — sur TOUTES les périodes (le backend
  // aligne la fenêtre : même jour / mêmes jours de semaine / même quantième).
  // delta() renvoie '' si la période de comparaison est vide (ex. since opening).
  const caDelta = delta(d.today.ca, d.yesterday.ca, compLabel);
  document.getElementById('kpi-ca-delta').innerHTML     = caDelta;

  // Décomposition de la croissance : CA = trafic (tx) × panier (ticket moyen).
  // Répond à "POURQUOI ça bouge" — plus de clients, ou panier plus gros ?
  const driversEl = document.getElementById('kpi-ca-drivers');
  const prevNb = d.yesterday.nb, prevTicket = d.yesterday.ticket;
  if (caDelta && prevNb > 0 && prevTicket > 0) {
    const gNb = Math.round((d.today.nb     - prevNb)     / prevNb     * 100);
    const gTk = Math.round((d.today.ticket - prevTicket) / prevTicket * 100);
    const part = (g, label) => {
      const col = g > 0 ? 'var(--green)' : g < 0 ? 'var(--red)' : 'var(--muted)';
      return `<span style="color:var(--muted)">${label}</span> <span style="color:${col};font-weight:500">${g >= 0 ? '+' : ''}${g}%</span>`;
    };
    driversEl.innerHTML =
      `<span style="color:var(--faint)">=</span> ${part(gNb, 'traffic')}` +
      `<span style="color:var(--faint)"> × </span>${part(gTk, 'basket')}`;
  } else {
    driversEl.innerHTML = '';
  }
  // Moyenne par jour ouvert — seulement en multi-jours (sur un jour unique, la
  // moyenne EST le total). Le CA/jour est confronté au point mort/jour : c'est
  // la lecture qui dit d'un coup d'œil si la période tient la route.
  const openDays  = d.economics?.open_days || 0;
  const perDayEl  = document.getElementById('kpi-ca-perday');
  const nbPerDayEl = document.getElementById('kpi-nb-perday');
  if (!d.is_single_day && openDays > 1) {
    const caDay    = d.today.ca / openDays;
    const seuilDay = d.economics?.seuil_ca_ttc_jour;
    let verdict = '';
    if (seuilDay > 0) {
      const above = caDay >= seuilDay;
      const gap   = Math.round(Math.abs(caDay - seuilDay));
      verdict = ` <span style="color:${above ? 'var(--green)' : 'var(--red)'};font-weight:500">`
              + `${above ? '▲' : '▼'} ${fmt(gap)}</span>`
              + `<span style="color:var(--faint);font-size:11px;"> vs break-even</span>`;
    }
    perDayEl.innerHTML = `<strong style="color:var(--text)">${fmt(caDay)}</strong>`
      + `<span style="color:var(--faint);font-size:11px;"> / open day</span>${verdict}`;
    nbPerDayEl.innerHTML = `<strong style="color:var(--text)">${Math.round(d.today.nb / openDays)}</strong>`
      + `<span style="color:var(--faint);font-size:11px;"> tickets / open day</span>`;
  } else {
    perDayEl.innerHTML = '';
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

  // EBITDA en rangée d'or — le chiffre qui répond à "est-ce que je gagne de l'argent ?"
  const ebitdaEl  = document.getElementById('kpi-ebitda');
  const ebitdaSub = document.getElementById('kpi-ebitda-sub');
  const ecoTop = d.economics;
  const ebitdaOpenN = ecoTop && ecoTop.open_days;
  document.getElementById('kpi-ebitda-label').textContent =
    'Est. EBITDA' + (d.is_single_day ? '' : (ebitdaOpenN ? ` · ${ebitdaOpenN} open days` : ` · ${d.n_days} days`));
  if (ecoTop && ecoTop.ebitda_ht != null) {
    ebitdaEl.textContent = fmt(ecoTop.ebitda_ht);
    ebitdaEl.style.color = ecoTop.ebitda_ht > 0 ? 'var(--green)' : ecoTop.ebitda_ht < 0 ? 'var(--red)' : 'var(--text)';
    // L'EBITDA descend de la marge brute, donc du taux mesuré sur la partie couverte du CA.
    // Si ce taux est extrapolé, « Profitable ✓ » affirme plus que ce qu'on sait — la coche
    // se lit comme un fait vérifié. Le verdict est alors donné au conditionnel.
    const ebitdaEst = ecoTop.marge_is_estimated === true;
    ebitdaSub.innerHTML = (ecoTop.ebitda_ht >= 0
      ? `<span style="color:var(--green)">Profitable${ebitdaEst ? '' : ' ✓'}</span>`
      : `<span style="color:var(--red)">Loss</span>`)
      + (ebitdaEst ? ` <span style="color:#b07d00">on an extrapolated margin</span>` : '');
  } else {
    ebitdaEl.textContent = '—'; ebitdaEl.style.color = 'var(--text)';
    ebitdaSub.innerHTML = '<span style="color:var(--muted)">not measurable</span>';
  }

  // ── Strip "Today" (période multi-jours incluant aujourd'hui) ──────────────
  // Mesa affiche toujours un snapshot du jour au-dessus de la période. Dérivé
  // de d.week (7 derniers jours) : dernier point = aujourd'hui, jour ouvré
  // précédent = dernier point antérieur avec des ventes.
  renderTodayStrip(d);
  renderFlux(d);

  // (Barre "Break-even N tx/day" supprimée : constante BP statique, redondante
  //  et parfois contradictoire avec le seuil CA réel affiché dans Economics.)


  // ── Économie ──────────────────────────────────────────────────────────────
  // Labels dynamiques selon la période
  // Suffixe = jours réellement OUVERTS (les coûts sont calculés dessus), pas les
  // jours calendaires — sinon "Since opening · 55 days" alors qu'on a ouvert 42j.
  const openN = (d.economics && d.economics.open_days) || null;
  const periodSuffix = d.is_single_day ? '(day)'
    : (openN ? `· ${openN} open days` : `· ${d.n_days} days`);
  document.getElementById('eco-label').textContent      = `Economics ${periodSuffix}`;
  document.getElementById('eco-charges-label').textContent = `Costs ${periodSuffix}`;
  document.getElementById('eco-prime-label').textContent   = `Prime cost ${periodSuffix}`;
  document.getElementById('eco-seuil-label').textContent   = `Break-even revenue ${periodSuffix}`;
  document.getElementById('eco-marge-label').textContent   = 'Gross margin';

  const eco = d.economics;
  if (eco) {
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
        : est ? `<span style="color:${covColor}">measured on ${cov}% of sales, applied to the rest</span>`
              : `<span style="color:${covColor}">COGS coverage ${cov}%</span>`;
      document.getElementById('eco-marge-pct').innerHTML =
        `${eco.marge_brute_ht_pct}%${est ? ' <span style="color:#b07d00">est.</span>' : ''}` +
        ` <span style="color:var(--faint)">· COGS ${fmt(eco.cogs_ht)} · </span>${covStr}`;
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

    // Prime cost — COGS + labour, sur la période (déplacé des cartes Insights)
    const primePerso = eco.cout_perso_periode ?? eco.cout_perso_jour;
    const primeEl = document.getElementById('eco-prime');
    const primeSub = document.getElementById('eco-prime-sub');
    const primeBar = document.getElementById('eco-prime-bar');
    if (eco.ca_ht > 0 && eco.cogs_ht != null && primePerso != null) {
      const prime = (eco.cogs_ht + primePerso) / eco.ca_ht * 100;
      const cogsPct = eco.marge_brute_ht_pct != null ? (100 - eco.marge_brute_ht_pct) : (eco.cogs_ht / eco.ca_ht * 100);
      const labPct  = primePerso / eco.ca_ht * 100;
      primeEl.textContent = prime.toFixed(1) + '%';
      primeEl.style.color = prime <= 67 ? 'var(--green)' : prime <= 75 ? '#b07d00' : 'var(--red)';
      primeSub.innerHTML = `COGS ${cogsPct.toFixed(0)}% · Labour ${labPct.toFixed(0)}% <span style="color:var(--faint)">· target &lt;65%</span>`;
      primeBar.innerHTML =
        `<div style="width:${Math.min(100,cogsPct)}%;background:#2554C7;"></div>` +
        `<div style="width:${Math.min(100,labPct)}%;background:rgba(37,84,199,.35);"></div>`;
    } else {
      primeEl.textContent = '—'; primeEl.style.color = 'var(--text)';
      primeSub.innerHTML = '<span style="color:var(--muted)">not measurable</span>';
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
          ? ` <span style="color:#b07d00">· on an extrapolated ${eco.seuil_margin_pct}% margin</span>`
          : ` <span style="color:var(--faint)">· real margin ${eco.seuil_margin_pct}%</span>`;
      if (eco.manque_seuil > 0) {
        seuilSub.innerHTML = `<span style="color:var(--red)">${fmt(eco.manque_seuil)} short (incl. VAT)</span>` + margeNote;
      } else {
        seuilSub.innerHTML = `<span style="color:var(--green)">Break-even reached${seuilEst ? '' : ' ✓'}</span>` + margeNote;
      }
      document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
    } else {
      document.getElementById('eco-seuil').textContent = '—';
      seuilSub.innerHTML = '<span style="color:var(--muted)">real margin not measurable</span>';
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
      avgEl.innerHTML = `<span style="color:var(--muted)">avg ${fmt(perDay)}/open day</span>${evo}`;
    } else {
      avgEl.innerHTML = '';
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
  const hourlyBars  = document.getElementById('hourly-bars');
  const hourlySub   = document.getElementById('hourly-sub');
  const dailyCanvas = document.getElementById('chart-daily');
  const timeLabel   = document.getElementById('time-chart-label');

  if (d.is_single_day && d.hourly) {
    hourlyBars.style.display = '';
    dailyCanvas.style.display = 'none';
    timeLabel.textContent = 'Revenue by hour';
    // Libellé court de la référence : "vs last Sat same time" → "last Sat"
    const prevLbl = (d.comp_label || '').replace(/^vs\s+/, '').replace(/\s+same time$/, '');
    renderHourlyBars(d.hourly, d.hourly_prev, prevLbl);
  } else if (d.daily && d.daily.length) {
    hourlyBars.style.display = 'none';
    hourlySub.textContent = '';
    dailyCanvas.style.display = '';
    timeLabel.textContent = 'Revenue by day';
    hideHourlySwitch();
    renderDailyChart(d.daily);
  } else {
    hourlyBars.style.display = 'none';
    hourlySub.textContent = '';
    dailyCanvas.style.display = 'none';
    hideHourlySwitch();
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
  const MIX_COLORS = {'Drinks':'#2554C7','Food':'#2554C7','Viennoiserie':'#2554C7','Retail':'#2554C7'};
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
    // Référence semaine passée : rééchantillonnée sur les heures d'aujourd'hui
    // (chaque journée a ses propres horaires de transaction) → courbe en escalier.
    const cPrev = d.curve_prev;
    let prevSeries = null;
    if (cPrev && cPrev.length > 1) {
      let j = 0, last = 0;
      prevSeries = d.curve.map(p => {
        while (j < cPrev.length && cPrev[j].time <= p.time) { last = cPrev[j].ca_cum; j++; }
        return last;
      });
    }
    const prevLblCurve = (d.comp_label || '').replace(/^vs\s+/, '').replace(/\s+same time$/, '') || 'last week';

    chartCurve = new Chart(cCtx, {
      type: 'line',
      data: {
        labels: d.curve.map(p => p.time),
        datasets: [{
          label: 'Today',
          data: d.curve.map(p => p.ca_cum),
          borderColor: BAR_ACTIVE,
          backgroundColor: 'rgba(37,84,199,0.06)',
          borderWidth: 2, fill: true, tension: 0.3,
          pointRadius: d.curve.map((_, i) => i === 0 ? 0 : 4),
          pointBackgroundColor: BAR_ACTIVE, pointBorderColor: '#fff', pointBorderWidth: 2,
        }].concat(prevSeries ? [{
          label: prevLblCurve,
          data: prevSeries,
          borderColor: 'rgba(120,119,111,0.55)',
          borderWidth: 1.5, borderDash: [5, 4],
          fill: false, tension: 0.3, pointRadius: 0,
        }] : [])
      },
      options: {
        plugins: {
          legend: prevSeries ? {
            display: true, position: 'top', align: 'end',
            labels: { boxWidth: 18, boxHeight: 2, font: { size: 11 },
                      color: 'rgba(120,119,111,1)', usePointStyle: false }
          } : { display: false },
          tooltip: {
            callbacks: {
              title: ctx => ctx[0].label,
              label: ctx => {
                if (ctx.datasetIndex === 1) return ` ${prevLblCurve} : ${fmt(ctx.raw)}`;
                const pt = d.curve[ctx.dataIndex];
                const lines = [` Cumul : ${fmt(ctx.raw)}`];
                if (pt.ca_tx) lines.push(` + ${fmt(pt.ca_tx)}  (${pt.nb})`);
                if (prevSeries) {
                  const diff = ctx.raw - prevSeries[ctx.dataIndex];
                  lines.push(` ${diff >= 0 ? '+' : ''}${fmt(diff)} vs ${prevLblCurve}`);
                }
                return lines;
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
    const periodLbl = d.is_single_day ? (d.is_today ? 'today' : 'this day') : (d.period_label?.toLowerCase() || 'the period');
    document.getElementById('products-section-label').textContent = `Products sold — ${periodLbl}`;
  }
  if (!d.has_items) {
    document.getElementById('products-body').innerHTML =
      '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">Item detail not available for this period.</td></tr>';
  } else if (d.products) {
    const maxQty = d.products.length ? d.products[0].qty : 1;
    const cntEl = document.getElementById('products-count');
    if (cntEl) cntEl.textContent = d.products.length ? `· ${d.products.length}` : '';
    if (!d.products.length) {
      document.getElementById('products-body').innerHTML =
        '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">No products sold.</td></tr>';
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
  const ins = d.insights;
  const monthZone    = document.getElementById('month-zone');
  const patternsZone = document.getElementById('patterns-zone');
  const verdictEl = document.getElementById('verdict-banner');
  if (!ins) {
    monthZone.style.display = 'none'; patternsZone.style.display = 'none';
    verdictEl.style.display = 'none';
    return;
  }

  // ── Verdict du jour : la journée en une phrase (vue Today uniquement) ──────
  const v = ins.verdict;
  if (d.is_today && v && v.nb > 0) {
    const dayLabel = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' });
    let parts = [`<strong>${fmt(v.ca)}</strong> · ${v.nb} tickets`];
    if (v.pct_of_typical != null) {
      const good = v.pct_of_typical >= 100;
      parts.push(`<span style="color:${good ? '#7ee2a8' : '#ffd27a'}">${v.pct_of_typical}%</span> of a typical ${v.weekday} (${fmt(v.typical_ca)} median, full day)`);
    }
    if (v.seuil != null) {
      parts.push(v.seuil_time
        ? `<span style="color:#7ee2a8">break-even reached at ${v.seuil_time}</span>`
        : `<span style="color:#ffd27a">${fmt(Math.max(0, v.seuil - v.ca))} to break-even</span>`);
    }
    verdictEl.innerHTML = `✦ ${dayLabel} — ` + parts.join(' · ');
    verdictEl.style.display = '';
  } else {
    verdictEl.style.display = 'none';
  }


  // Zone 2 "This month" : masquée quand la période EST le mois en cours (doublon).
  const showMonthZone = currentPreset !== 'month' && ins.month && ins.month.days && ins.month.days.length;
  monthZone.style.display = showMonthZone ? '' : 'none';
  if (showMonthZone) {
    document.getElementById('month-zone-label').textContent =
      new Date().toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
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
        <path d="${path}" fill="none" stroke="#2554C7" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
        <path d="${projPath}" fill="none" stroke="rgba(37,84,199,.45)" stroke-width="2.5" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="ins-sub">
        MTD <strong style="color:${m.cum_now >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.cum_now)}</strong>
        · projected <strong style="color:${m.proj_end >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.proj_end)}</strong> by month end
        ${m.cross_date ? ` · crossed €0 on ${new Date(m.cross_date + 'T12:00:00').toLocaleDateString('en-GB', {day:'numeric', month:'short'})}` : ''}
      </div>
      ${m.proj_ca_end != null ? `
      <div class="ins-sub" style="margin-top:4px;">
        Revenue: MTD <strong>${fmt(m.ca_mtd)}</strong>
        · projected <strong>${fmt(m.proj_ca_end)}</strong> by month end
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
      cal += `<div class="cal-cell" style="background:${bg};color:${color};" data-tip="${new Date(day.date+'T12:00:00').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})}${day.ebitda != null ? ' · EBITDA ' + fmt(day.ebitda) : ' · closed'}">${dt.getDate()}</div>`;
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

  // Articles par ticket (attach)
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
}

// ── Graphe horaire : deux vues exclusives ───────────────────────────────────
// 'abs'   → CA par heure (vue par défaut, inchangée)
// 'delta' → écart par heure vs le même jour la semaine passée, autour de zéro.
// Une seule information à la fois : rien n'est superposé aux barres.
let _hourlyMode = 'abs';
let _hourlyData = null;

function hideHourlySwitch() {
  const sw = document.getElementById('hourly-switch');
  if (sw) sw.style.display = 'none';
  _hourlyData = null;
}

function setHourlyMode(mode) {
  _hourlyMode = mode;
  document.getElementById('hsw-abs').classList.toggle('active', mode === 'abs');
  document.getElementById('hsw-delta').classList.toggle('active', mode === 'delta');
  if (_hourlyData) renderHourlyBars(_hourlyData.h, _hourlyData.prev, _hourlyData.prevLabel);
}

// Vue "écarts" : barres vertes vers le haut (mieux que la semaine passée),
// rouges vers le bas, de part et d'autre d'une ligne de zéro.
function renderHourlyDelta(hours, vals, prevByHour, prevLabel, h) {
  const diffs = hours.map((hr, i) => (vals[i] || 0) - (prevByHour[hr] || 0));
  const maxAbs = Math.max(...diffs.map(Math.abs), 0) || 1;
  const ref = prevLabel || 'last week';

  document.getElementById('hourly-bars').innerHTML =
    `<div class="dbar-row"><div class="dbar-zero"></div>` + hours.map((hr, i) => {
      const dv  = diffs[i];
      const now = vals[i] || 0, pv = prevByHour[hr] || 0;
      const px  = Math.round(Math.abs(dv) / maxAbs * 58);
      const pct = pv > 0 ? Math.round(dv / pv * 100) : null;
      const tip = (now || pv)
        ? `${hr}h · ${fmt(now)} vs ${fmt(pv)} — ${dv >= 0 ? '+' : ''}${fmt(dv)}`
          + (pct !== null ? ` (${dv >= 0 ? '+' : ''}${pct}%)` : '')
        : `${hr}h · no sales`;
      const bar = px > 0
        ? `<div class="dfill ${dv >= 0 ? 'pos' : 'neg'}" style="height:${Math.max(px, 3)}px;"></div>`
        : '';
      return `<div class="dbar" data-tip="${tip}">
        <div class="up-half">${dv > 0 ? bar : ''}</div>
        <div class="down-half">${dv < 0 ? bar : ''}</div>
        <span class="dhr">${hr}</span>
      </div>`;
    }).join('') + `</div>`;

  // Sous-titre : les créneaux qui expliquent le plus l'écart
  const ranked = hours.map((hr, i) => ({ hr, d: diffs[i] })).filter(x => Math.abs(x.d) > 0.5);
  const best  = ranked.filter(x => x.d > 0).sort((a, b) => b.d - a.d).slice(0, 2);
  const worst = ranked.filter(x => x.d < 0).sort((a, b) => a.d - b.d).slice(0, 2);
  const totalDiff = diffs.reduce((s, v) => s + v, 0);
  const line = (label, arr, col) => arr.length
    ? ` · <span style="color:var(--faint)">${label}</span> `
      + arr.map(x => `<span style="color:${col};font-weight:500">${x.hr}h ${x.d >= 0 ? '+' : ''}${fmt(x.d)}</span>`).join(' ')
    : '';
  document.getElementById('hourly-sub').innerHTML =
    `<span style="color:var(--faint)">vs ${ref}:</span> `
    + `<b style="color:${totalDiff >= 0 ? 'var(--green)' : 'var(--red)'}">${totalDiff >= 0 ? '+' : ''}${fmt(totalDiff)}</b>`
    + line('gained', best, 'var(--green)')
    + line('lost', worst, 'var(--red)');
}

// hourly.labels = ["7h","8h",…] · values/nb/avg_ticket/avg_gap alignés.
function renderHourlyBars(h, prev, prevLabel) {
  // Mémorise les données pour pouvoir basculer entre les deux vues sans
  // recharger (la bascule ne fait que re-rendre).
  _hourlyData = { h, prev, prevLabel };

  const hours = h.labels.map(l => parseInt(l, 10));
  const vals  = h.values;
  // Comparaison "même jour la semaine passée" : jamais superposée aux barres.
  // Elle vit dans le sous-titre, les tooltips, et la vue "vs last week".
  const prevByHour = {};
  if (prev && Array.isArray(prev.labels)) {
    prev.labels.forEach((l, i) => { prevByHour[parseInt(l, 10)] = prev.values[i] || 0; });
  }
  const hasPrev = Object.values(prevByHour).some(v => v > 0);

  // Bascule visible seulement s'il y a une référence à comparer
  const sw = document.getElementById('hourly-switch');
  if (sw) sw.style.display = hasPrev ? '' : 'none';
  if (!hasPrev) _hourlyMode = 'abs';

  if (_hourlyMode === 'delta' && hasPrev) {
    renderHourlyDelta(hours, vals, prevByHour, prevLabel, h);
    return;
  }

  const maxV = Math.max(...vals, 0) || 1;
  const peakIdx = vals.reduce((mi, v, i, a) => v > a[mi] ? i : mi, 0);
  const peakHour = hours[peakIdx];

  // Heures creuses : entre la première et la dernière heure active, < 5% du pic.
  const active = hours.filter((_, i) => vals[i] > 0);
  const first = active[0], last = active[active.length - 1];
  const dead = active.length >= 2
    ? hours.filter((hr, i) => hr > first && hr < last && vals[i] < maxV * 0.05)
    : [];
  const deadSet = new Set(dead);

  document.getElementById('hourly-bars').innerHTML =
    `<div class="hbar-row">` + hours.map((hr, i) => {
      const isPeak = i === peakIdx && vals[i] > 0;
      const hpx = Math.round(vals[i] / maxV * 118);
      const pv  = prevByHour[hr] || 0;
      let tip = `${hr}h · ${fmt(vals[i])} · ${h.nb[i]} tx`;
      if (hasPrev && (pv > 0 || vals[i] > 0)) {
        const diff = vals[i] - pv;
        const pct  = pv > 0 ? Math.round(diff / pv * 100) : null;
        tip += ` — ${prevLabel || 'last week'}: ${fmt(pv)}`
             + (pct !== null ? ` (${diff >= 0 ? '+' : ''}${pct}%)` : '');
      }
      return `<div class="hbar" data-tip="${tip}">
        <div class="fill ${isPeak ? 'peak' : 'norm'}" style="height:${hpx}px;${vals[i] > 0 ? 'min-height:3px;' : 'border:none;'}"></div>
        <span class="hr ${deadSet.has(hr) ? 'dead' : ''}">${hr}</span>
      </div>`;
    }).join('') + `</div>`;

  // Sous-titre : pic du jour + total vs référence + légende du repère
  const totalNow  = vals.reduce((s, v) => s + v, 0);
  const totalPrev = hasPrev ? Object.values(prevByHour).reduce((s, v) => s + v, 0) : 0;
  let cmp = '';
  if (hasPrev && totalPrev > 0) {
    const pct = Math.round((totalNow - totalPrev) / totalPrev * 100);
    const up  = pct >= 0;
    cmp = ` · <span style="color:${up ? 'var(--green)' : 'var(--red)'};font-weight:500">${up ? '▲ +' : '▼ '}${pct}%</span>`
        + ` <span style="color:var(--faint)">vs ${prevLabel || 'last week'}</span>`;
  }
  document.getElementById('hourly-sub').innerHTML =
    `Peak at <b style="color:var(--text)">${peakHour}h</b> · ${fmt(maxV === 1 && vals[peakIdx] === 0 ? 0 : vals[peakIdx])}`
    + (dead.length ? ` · dead hours: <b style="color:var(--text)">${dead.map(x => x + 'h').join(', ')}</b>` : '')
    + cmp;
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
