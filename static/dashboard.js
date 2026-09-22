/**
 * L'ÉTAT D'UN INDICATEUR, PORTÉ PAR SA BANDE D'ACCENT.
 *
 * ⚠️ `null` RETIRE L'ATTRIBUT PLUTÔT QUE DE POSER UNE VALEUR NEUTRE. Un indicateur sans donnée
 * n'est pas « bon » : la bande reprend la couleur de la bordure, et l'œil ne s'y arrête pas.
 */
/**
 * Pose l'état d'un indicateur sur le CONTENEUR qui le porte.
 *
 * ⚠️ LE CHIFFRE RESTE EN ENCRE, C'EST LA BANDE QUI PORTE L'ÉTAT. Un nombre coloré est plus
 * difficile à lire qu'un nombre noir, et sur douze indicateurs colorés plus rien ne ressort.
 *
 * ⚠️ LA LISTE DES CONTENEURS DOIT SUIVRE LES FORMES DE LA PAGE. Elle ne connaissait que
 * `.kpi-cell` : appelée depuis le bandeau-réponse, qui est une `.tx-answer`, elle ne trouvait
 * rien et ne faisait RIEN — l'état était calculé puis jeté en silence. Le pire cas : la
 * fonction a l'air appelée, la couleur n'apparaît jamais, et on cherche le bogue dans le CSS.
 */
function etat(el, valeur){
  var cel = el && el.closest ? el.closest('.kpi-cell, .tx-answer, .maillon') : null;
  if (!cel) return;
  if (valeur) cel.setAttribute('data-etat', valeur);
  else cel.removeAttribute('data-etat');
}

/**
 * Pose un repère de cible sur une barre de progression.
 *
 * ⚠️ LE REPÈRE EST DANS LA BARRE, PAS À CÔTÉ. Une légende « cible 65 % » sous le graphique
 * oblige à convertir mentalement une largeur en pourcentage — c'est exactement le calcul qu'un
 * repère évite.
 */
function marquerSeuil(barre, pct, libelle){
  if (!barre || !barre.parentElement) return;
  var enveloppe = barre.parentElement;
  enveloppe.classList.add('seuil-wrap');
  var vieux = enveloppe.querySelector('.seuil-marque');
  if (vieux) vieux.remove();
  var m = document.createElement('div');
  m.className = 'seuil-marque';
  m.style.left = Math.max(0, Math.min(100, pct)) + '%';
  if (libelle) m.title = libelle;
  enveloppe.appendChild(m);
}

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
  return new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
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
  return new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
}

// ── Chargement (stale-while-revalidate) ──────────────────────────────────────
// Affiche instantanément les dernières données connues (localStorage), puis
// rafraîchit en arrière-plan. force=true (bouton ↻) bypasse les caches serveur.
// Journée en cours dans l'économie de la période. Par défaut NON : elle
// n'apporte qu'une recette partielle mais une journée entière de charges.
let inclToday = false;
try { inclToday = localStorage.getItem('estu_incl_today') === '1'; } catch (e) {}

function toggleInclToday() {
  inclToday = document.getElementById('incl-today').checked;
  try { localStorage.setItem('estu_incl_today', inclToday ? '1' : '0'); } catch (e) {}
  loadData(true);
}

async function loadData(force = false) {
  const preset = currentPreset;
  const isCustom = preset === 'custom' && customStart && customEnd;
  // La clé de cache porte le choix : sans lui, basculer le bouton réaffichait
  // les chiffres de l'autre périmètre le temps d'un aller-retour.
  const cacheKey = 'estu_data_' + preset + (inclToday ? '_incl' : '')
                 + (isCustom ? '_' + customStart + '_' + customEnd : '');
  if (!force) {
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) render(JSON.parse(cached));
    } catch(e) {}
  }
  if (window.uiLoadStart) uiLoadStart();
  try {
    const incl = inclToday ? '&incl_today=1' : '';
    const url = isCustom
      ? `/api/data?preset=custom&start_date=${customStart}&end_date=${customEnd}${incl}${force ? '&fresh=1' : ''}`
      : '/api/data?preset=' + preset + incl + (force ? '&fresh=1' : '');
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

// ── Clients récurrents (empreintes de cartes, voir revolut_merchant.py) ──────
// Chargé à part : petite table Supabase, inutile d'alourdir /api/data.
let _retReq = 0;

// Reconstruction : 10 jours par appel (timeout serverless), de l'ouverture à
// aujourd'hui. Admin seulement — un 403 arrête tout et le dit.

// ── Rendu principal ───────────────────────────────────────────────────────────
/**
 * LA RÉPONSE DU HAUT : « est-ce qu'on couvre nos coûts ? »
 *
 * ⚠️ LA PAGE OUVRAIT SUR HUIT CELLULES DE MÊME POIDS, en deux grilles décrivant la même
 * période. Aucune ne répondait à la question qu'on se pose en ouvrant un tableau de bord de
 * café : est-ce que la journée paie ce qu'elle coûte ? On la reconstituait de tête, chaque
 * matin, à partir du résultat et du point mort lus dans deux coins différents.
 *
 * ⚠️ LE VERDICT NOIR QUI VIVAIT ICI NE S'AFFICHAIT QUE SUR « AUJOURD'HUI ». Les six autres
 * périodes n'avaient pas de réponse du tout — et « ce mois-ci » est précisément celle qu'on
 * regarde pour décider quelque chose.
 *
 * ⚠️ ET « PAS DE DONNÉE » N'EST PAS « À L'ÉQUILIBRE ». Sans prix d'achat, le résultat n'est pas
 * calculable : la réponse le dit et nomme le geste, au lieu d'afficher un zéro rassurant.
 */
function renderReponse(d) {
  const eco = d.economics || {};
  const E = (id) => document.getElementById(id);
  const note = E('db-note');
  const jours = eco.open_days != null ? eco.open_days : null;

  if (eco.ebitda_ht == null) {
    E('db-lead').textContent = 'Le résultat n’est pas calculable sur cette période.';
    E('db-value').textContent = '—';
    E('db-delta').innerHTML = '';
    E('db-sub').innerHTML = '';
    E('db-rule').innerHTML = '';
    note.innerHTML = 'Il manque les prix d’achat pour connaître la marge. '
      + '<a href="/cogs">Ouvrir COGS &amp; recettes →</a>';
    note.style.display = '';
    etat(E('db-value'), null);
    return;
  }

  const couvre = eco.ebitda_ht >= 0;
  E('db-value').textContent = fmt(eco.ebitda_ht);
  etat(E('db-value'), couvre ? 'ok' : 'alerte');
  E('db-lead').textContent = couvre
    ? 'Les coûts sont couverts.'
    : 'Les coûts ne sont pas couverts.';

  /* ⚠️ LE MANQUE EST DIT EN EUROS DE CHIFFRE D'AFFAIRES, PAS EN RÉSULTAT. « Il manque 180 € »
     de résultat n'indique aucun geste ; « il manque 740 € de ventes » se compare à une
     journée. Les deux diffèrent du taux de marge, et c'est le second qu'on peut viser. */
  const manque = eco.manque_seuil;
  E('db-delta').innerHTML = couvre
    ? '<span class="tx-chip tx-chip-up">au-dessus du point mort</span>'
    : (manque > 0
        ? `<span class="tx-chip tx-chip-down">${fmt(manque)} de ventes manquantes</span>`
        : '');

  const bouts = [];
  if (eco.ca_ttc != null) bouts.push(`<b>${fmt(eco.ca_ttc)}</b> encaissés`);
  if (eco.seuil_ca_ttc != null) bouts.push(`point mort <b>${fmt(eco.seuil_ca_ttc)}</b>`);
  /* ⚠️ LE MÊME COMPTE QUE LA LIGNE DE PÉRIODE. `open_days` vient de `daily_economics`, qui
   * reçoit la fenêtre RÉELLEMENT calculée : les deux sont donc d'accord par construction. Les
   * laisser diverger ferait lire « 420 € sur 5 services » à côté de « 4 services ». */
  if (jours) bouts.push(`<b>${jours}</b> service${jours > 1 ? 's' : ''}`);
  E('db-sub').innerHTML = bouts.join(' · ');

  /* ⚠️ CE QUI EST ESTIMÉ SE DIT À CÔTÉ DU CHIFFRE. Sous la couverture COGS complète, la marge
     est extrapolée — donc le résultat ET le point mort le sont aussi. Le taire ferait lire un
     résultat mesuré là où il y a une projection. */
  if (eco.marge_is_estimated === true) {
    note.innerHTML = `Marge extrapolée sur <b>${eco.cogs_coverage_pct}%</b> des ventes — `
      + 'le résultat et le point mort en héritent.';
    note.style.display = '';
  } else {
    note.style.display = 'none';
  }

  E('db-rule').innerHTML = 'Résultat = marge brute &minus; charges fixes et salaires, '
    + 'répartis sur les jours <b>réellement ouverts</b>.';
}

/* ⚠️ LA GARDE DE REDIMENSIONNEMENT EST PARTIE AVEC LES BLOCS REPLIÉS. Chart.js mesure son
 * conteneur au moment du tracé : dans un `<details>` fermé il vaut zéro, et le graphique sort
 * écrasé à l'ouverture. Le problème était réel ; il n'a plus d'objet ici, puisque plus aucun
 * graphique de cette page n'est replié.
 *
 * ⚠️ ET UNE PROTECTION SANS CIBLE EST PIRE QU'ABSENTE : on la maintient, on la relit, on la
 * croit active — et le jour où un graphique replié réapparaît ailleurs, personne ne pense à
 * vérifier qu'elle le couvre. Si le pli revient, ce code est dans l'historique, au commit
 * « Cinq blocs du tableau de bord se replient ».
 */

function render(d) {
  window._lastData = d;
  /* ⚠️ « RETURNING CUSTOMERS » A DEUX PAGES À LUI : `/clientes` analyse les empreintes de
   * cartes du terminal, `/loyalty` suit le rattachement au programme. Les tuiles d'ici ne
   * faisaient que renvoyer vers la première.
   */
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
    ? (d.is_today ? 'Aujourd’hui' : fmtDate(d.date).replace(/^\w/, c => c.toUpperCase()))
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
  const compLabel = d.comp_label || (d.is_single_day ? 'vs le service précédent' : 'vs période précédente');

  // Bouton « journée en cours » : visible seulement là où il change quelque chose
  const inclBar = document.getElementById('incl-today-bar');
  if (inclBar) {
    const can = !!(d.economics && d.economics.today_toggleable);
    inclBar.style.display = can ? 'flex' : 'none';
    if (can) {
      document.getElementById('incl-today').checked = inclToday;
      document.getElementById('incl-today-hint').textContent = inclToday
        ? '— charges d\u2019une journée entière face à une recette partielle'
        : '';
    }
  }

  // ── KPIs ─────────────────────────────────────────────────────────────────
  document.getElementById('kpi-ca').textContent = fmt(d.today.ca);
  if (d.economics) {
    // Le brut reste écrit : c'est lui qui coïncide avec Vendus, la trésorerie
    // et la page comptable. Le net est ce que le café gagne réellement.
    // ⚠️ MÊME PÉRIMÈTRE QUE LE GRAND CHIFFRE. `economics` s'arrête à hier ;
    // reprendre son ca_ht ici affichait un HT + TVA qui ne recomposait pas le
    // total affiché juste au-dessus. Les stats couvrent la période entière.
    const chef = d.today.popup_chef;
    document.getElementById('kpi-ca-ht').innerHTML =
      `${fmt(d.today.ca_ht)} HT · TVA ${fmt(d.today.ca - d.today.ca_ht)}`
      + (chef ? `<br><span style="color:#7c4dbe;">${fmt(d.today.ca_gross)} facturé · ${fmt(chef)} reversé au chef</span>` : '');
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
    // Confronté au point mort, donc calculé sur la MÊME base que lui : quand
    // l'économie exclut le jour courant, sa recette sort aussi du numérateur —
    // sinon on divisait 4 jours de recette par 3 jours de charges.
    const caBase   = d.economics?.excludes_today && d.economics?.ca_ttc != null
                     ? d.economics.ca_ttc : d.today.ca;
    const caDay    = caBase / openDays;
    const seuilDay = d.economics?.seuil_ca_ttc_jour;
    let verdict = '';
    if (seuilDay > 0) {
      const above = caDay >= seuilDay;
      const gap   = Math.round(Math.abs(caDay - seuilDay));
      verdict = ` <span style="color:${above ? 'var(--green)' : 'var(--red)'};font-weight:500">`
              + `${above ? '▲' : '▼'} ${fmt(gap)}</span>`
              + `<span style="color:var(--faint);font-size:11px;"> vs le point mort</span>`;
    }
    perDayEl.innerHTML = `<strong style="color:var(--text)">${fmt(caDay)}</strong>`
      + `<span style="color:var(--faint);font-size:11px;"> / jour ouvert</span>${verdict}`;
    // ⚠️ Calculé par le serveur (_tx_per_open_day), plus ici. La division faite à cet endroit
    // comptait la journée EN COURS des deux côtés : un vendredi matin, trois tickets face à un
    // jour ouvré entier faisaient chuter la moyenne d'un tiers, qui remontait ensuite toute
    // seule au fil des heures. Le serveur ne retient que les jours pleins et sait répondre
    // « on ne sait pas » quand il n'y en a aucun — un 0 se lirait « aucune transaction ».
    const tx = d.basket && d.basket.tx_per_open_day;
    nbPerDayEl.innerHTML = tx != null
      ? `<strong style="color:var(--text)">${tx}</strong>`
        + `<span style="color:var(--faint);font-size:11px;"> tickets / jour ouvert`
        + ` · ${d.basket.tx_basis_days} j pleins</span>`
      : `<span style="color:var(--muted)">—</span>`
        + `<span style="color:var(--faint);font-size:11px;"> tickets / jour ouvert`
        + ` · ${(d.basket && d.basket.tx_basis_reason) || 'indisponible'}</span>`;
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
    'Résultat' + (d.is_single_day ? '' : (ebitdaOpenN ? ` · ${ebitdaOpenN} services` : ` · ${d.n_days} jours`))
    + (ecoTop && ecoTop.excludes_today ? ' · hors journée en cours' : '');
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
      + (ebitdaEst ? ` <span style="color:#b07d00">sur une marge extrapolée</span>` : '');
  } else {
    /* ⚠️ UNE CASE VIDE NOMME LE GESTE. L'EBITDA se calcule à partir de la marge, qui se
       calcule à partir des prix d'achat : dire « pas mesurable » sans dire pourquoi laisse
       chercher la panne au mauvais endroit. */
    ebitdaEl.textContent = '—'; ebitdaEl.style.color = '';
    etat(ebitdaEl, null);
    ebitdaSub.innerHTML = '<span style="color:var(--muted)">Se calcule à partir de la marge. ' +
      '<a href="/cogs" style="color:var(--accent)">Ouvrir COGS &amp; recettes →</a></span>';
  }

  // ── Strip "Today" (période multi-jours incluant aujourd'hui) ──────────────
  // Mesa affiche toujours un snapshot du jour au-dessus de la période. Dérivé
  // de d.week (7 derniers jours) : dernier point = aujourd'hui, jour ouvré
  // précédent = dernier point antérieur avec des ventes.
  renderTodayStrip(d);

  // (Barre "Break-even N tx/day" supprimée : constante BP statique, redondante
  //  et parfois contradictoire avec le seuil CA réel affiché dans Economics.)


  // ── Économie ──────────────────────────────────────────────────────────────
  // Labels dynamiques selon la période
  // Suffixe = jours réellement OUVERTS (les coûts sont calculés dessus), pas les
  // jours calendaires — sinon "Since opening · 55 days" alors qu'on a ouvert 42j.
  const openN = (d.economics && d.economics.open_days) || null;
  const periodSuffix = d.is_single_day ? '(jour)'
    : (openN ? `· ${openN} services` : `· ${d.n_days} jours`)
      + (d.economics && d.economics.excludes_today ? ' · hors journée en cours' : '');
  document.getElementById('eco-label').textContent      = `Economics ${periodSuffix}`;
  document.getElementById('eco-charges-label').textContent = `Charges ${periodSuffix}`;
  document.getElementById('eco-prime-label').textContent   = `Prime cost ${periodSuffix}`;
  document.getElementById('eco-seuil-label').textContent   = `Point mort ${periodSuffix}`;
  document.getElementById('eco-marge-label').textContent   = 'Marge brute';

  const eco = d.economics;
  // Bloc économie isolé dans une fonction immédiate : le cas « aucun jour ouvré »
  // sort par un `return`, qui ne doit interrompre QUE cette zone — pas le rendu des
  // produits et des transactions qui suit.
  if (eco) (() => {
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
        : est ? `<span style="color:${covColor}">mesurée sur ${cov} % des ventes, appliquée au reste</span>`
              : `<span style="color:${covColor}">couverture des coûts ${cov} %</span>`;
      document.getElementById('eco-marge-pct').innerHTML =
        `${eco.marge_brute_ht_pct}%${est ? ' <span style="color:#b07d00">est.</span>' : ''}` +
        ` <span style="color:var(--faint)">· marchandise ${fmt(eco.cogs_ht)} · </span>${covStr}`;
      /* ⚠️ L'ÉTAT DE LA MARGE, C'EST SA COUVERTURE — pas sa valeur. Une marge de 75 % mesurée
         sur 96 % des ventes et la même mesurée sur 55 % ne sont pas la même information, et
         c'est la seconde qui appelle un geste. La bande le dit sans une ligne de texte de
         plus. */
      etat(document.getElementById('eco-marge'), !est ? 'ok'
           : (cov != null && cov >= 60) ? 'attention' : 'alerte');
    } else {
      /* ⚠️ UNE CASE VIDE DIT CE QUI LA REMPLIRA, avec le lien pour y aller. « No COGS set »
         laisse devant un écran mort. */
      etat(document.getElementById('eco-marge'), null);
      document.getElementById('eco-marge-pct').innerHTML =
        '<span style="color:var(--muted)">Aucun prix d\'achat renseigné. ' +
        '<a href="/cogs" style="color:var(--accent)">Ouvrir COGS &amp; recettes →</a></span>';
    }

    // Charges — utilise les totaux période et open_days (pas n_days calendaires)
    // ⚠️ `?? cout_total_jour` REFERAIT LE BUG. Le serveur renvoie désormais `null` quand la
    // période ne contient aucun jour ouvré — un mardi-mercredi, café fermé. Le repli sur le
    // coût JOURNALIER y réafficherait les ~197 € que la correction serveur venait justement
    // de retirer. Sans jour ouvré, il n'y a rien à imputer : on le dit.
    const chargesEl = document.getElementById('eco-charges');
    if (eco.open_days === 0) {
      chargesEl.textContent = '—';
      document.getElementById('eco-charges-sub').innerHTML =
        '<span style="color:var(--muted)">aucun jour d\'ouverture sur la période</span>';
      document.getElementById('eco-prime').textContent = '—';
      etat(document.getElementById('eco-prime'), null);
      document.getElementById('eco-prime-sub').innerHTML =
        '<span style="color:var(--muted)">Aucun jour d\'ouverture sur la période.</span>';
      document.getElementById('eco-prime-bar').innerHTML = '';
      document.getElementById('eco-seuil').textContent = '—';
      document.getElementById('eco-seuil-sub').innerHTML =
        '<span style="color:var(--muted)">pas de point mort sans jour ouvré</span>';
      return;
    }
    chargesEl.textContent = fmt(eco.cout_total_periode ?? eco.cout_total_jour);
    const openDays = eco.open_days || d.n_days;
    const chargesSub = d.is_single_day
      ? `Fixes ${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} · Personnel ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)}`
      : `${fmt(eco.cout_fixe_periode ?? eco.cout_fixe_jour)} de fixes · ${fmt(eco.cout_perso_periode ?? eco.cout_perso_jour)} de personnel · <span style="color:var(--faint)">${openDays} services × ${fmt(eco.cout_jour ?? (eco.cout_total_jour / openDays))}/jour</span>`;
    document.getElementById('eco-charges-sub').innerHTML = chargesSub;

    // Prime cost — COGS + labour, sur la période (déplacé des cartes Insights)
    const primePerso = eco.cout_perso_periode ?? eco.cout_perso_jour;
    const primeEl = document.getElementById('eco-prime');
    const primeSub = document.getElementById('eco-prime-sub');
    const primeBar = document.getElementById('eco-prime-bar');
    // ⚠️ LE TITRE ET SON SOUS-TEXTE PARLAIENT DE DEUX COGS DIFFÉRENTS.
    //
    // Le chiffre utilisait `cogs_ht`, mesuré sur la seule part des ventes dont le coût est
    // connu ; le sous-texte affichait `100 − marge_brute_ht_pct`, le taux extrapolé à tout le
    // CA. À 60 % de couverture, le titre annonçait 48 % en vert pendant que sa propre ligne du
    // dessous additionnait 30 + 30 = 60 %, au-delà de la cible. Le prime cost était sous-estimé
    // exactement du déficit de couverture, et jamais marqué comme estimé.
    //
    // On prend maintenant la matière extrapolée des deux côtés — la même que la cascade Flux :
    // ca_ht − marge_brute_ht. Les deux lignes disent enfin le même nombre.
    const primeMatiere = (eco.marge_brute_ht != null) ? (eco.ca_ht - eco.marge_brute_ht) : null;
    if (eco.ca_ht > 0 && primeMatiere != null && primePerso != null) {
      const prime   = (primeMatiere + primePerso) / eco.ca_ht * 100;
      const cogsPct = primeMatiere / eco.ca_ht * 100;
      const labPct  = primePerso / eco.ca_ht * 100;
      const est     = eco.marge_is_estimated === true;
      primeEl.textContent = prime.toFixed(1) + '%';
      /* ⚠️ LE CHIFFRE RESTE EN ENCRE ; C'EST LA BANDE QUI PORTE L'ÉTAT. Un nombre coloré est
         plus difficile à lire qu'un nombre noir, et sur douze indicateurs colorés plus rien ne
         ressort. */
      primeEl.style.color = '';
      etat(primeEl, prime <= 65 ? 'ok' : prime <= 75 ? 'attention' : 'alerte');
      primeSub.innerHTML = `Marchandise ${cogsPct.toFixed(0)}% · Personnel ${labPct.toFixed(0)}%`
        + (est ? ` <span style="color:var(--amber)">· matière extrapolée sur ${eco.cogs_coverage_pct}% des ventes</span>` : '')
        + ` <span style="color:var(--faint)">· cible &lt;65 %</span>`;
      primeBar.innerHTML =
        `<div style="width:${Math.min(100,cogsPct)}%;background:var(--flux-leave);"></div>` +
        `<div style="width:${Math.min(100,labPct)}%;background:var(--flux-tax);"></div>`;
      /* ⚠️ LE REPÈRE DE CIBLE, À 65 %. Une barre sans repère dit « c'est trop » ; avec le
         repère, elle dit « de deux points ». La barre est graduée sur 100 % du CA : la cible
         s'y place donc à 65 % de sa largeur. */
      marquerSeuil(primeBar, 65, 'cible 65 %');
    } else {
      /* ⚠️ UN TIRET, PAS UN ZÉRO — et une phrase qui dit ce qui le remplira. « Not
         measurable » laisse devant un écran mort sans indiquer le geste. */
      primeEl.textContent = '—'; primeEl.style.color = '';
      etat(primeEl, null);
      primeSub.innerHTML = '<span style="color:var(--muted)">Il manque les prix d\'achat. ' +
        '<a href="/cogs" style="color:var(--accent)">Ouvrir COGS &amp; recettes →</a></span>';
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
          ? ` <span style="color:#b07d00">· sur une marge extrapolée de ${eco.seuil_margin_pct} %</span>`
          : ` <span style="color:var(--faint)">· marge réelle ${eco.seuil_margin_pct} %</span>`;
      if (eco.manque_seuil > 0) {
        seuilSub.innerHTML = `<span style="color:var(--red)">${fmt(eco.manque_seuil)} manquants (TTC)</span>` + margeNote;
      } else {
        seuilSub.innerHTML = `<span style="color:var(--green)">Point mort atteint${seuilEst ? '' : ' ✓'}</span>` + margeNote;
      }
      document.getElementById('eco-seuil-bar').style.width = Math.min(100, eco.pct_seuil) + '%';
    } else {
      document.getElementById('eco-seuil').textContent = '—';
      etat(document.getElementById('eco-seuil'), null);
      seuilSub.innerHTML = '<span style="color:var(--muted)">Le point mort se calcule ' +
        'charges ÷ marge réelle. <a href="/cogs" style="color:var(--accent)">Ouvrir COGS →</a></span>';
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
      avgEl.innerHTML = `<span style="color:var(--muted)">moy. ${fmt(perDay)}/jour ouvert</span>${evo}`;
    } else {
      avgEl.innerHTML = '';
    }
  })();

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
        tooltip: { callbacks: { label: ctx => fmt(ctx.raw) + ' · ' + d.week[ctx.dataIndex].nb + ' tickets' } }
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
    timeLabel.textContent = 'Par heure';
    // Libellé court de la référence : "vs last Sat same time" → "last Sat"
    const prevLbl = (d.comp_label || '').replace(/^vs\s+/, '').replace(/\s+same time$/, '');
    renderHourlyBars(d.hourly, d.hourly_prev, prevLbl);
  } else if (d.daily && d.daily.length) {
    hourlyBars.style.display = 'none';
    hourlySub.textContent = '';
    dailyCanvas.style.display = '';
    timeLabel.textContent = 'Par jour';
    hideHourlySwitch();
    renderDailyChart(d.daily);
  } else {
    hourlyBars.style.display = 'none';
    hourlySub.textContent = '';
    dailyCanvas.style.display = 'none';
    hideHourlySwitch();
  }

  /* ⚠️ LA RÉPARTITION DES PAIEMENTS EST PARTIE VERS `/reconciliation`. Celle d'ici venait de
   * ce que Vendus DÉCLARE ; celle de là-bas est MESURÉE sur le terminal Revolut, ligne à
   * ligne, avec l'écart entre les deux. Garder les deux, c'était offrir le choix entre une
   * mesure et une déclaration — et celui qui choisit mal ne le saura jamais.
   */

  /* ⚠️ LES PICS D'ACTIVITÉ RÉSUMAIENT LE GRAPHIQUE SITUÉ JUSTE EN DESSOUS. Trois pastilles
   * au-dessus d'une courbe qui dit la même chose, en mieux : on lisait deux fois, puis on
   * cessait de lire les deux.
   */

  // ── Produits (toggle période / 7j) ───────────────────────────────────────
  const topSection = document.getElementById('top-products-section');
  if (topSection) {
    topSection.style.display = '';
    const periodLbl = d.is_single_day ? (d.is_today ? 'aujourd’hui' : 'ce jour') : (d.period_label?.toLowerCase() || 'la période');
    document.getElementById('products-section-label').textContent = `Ce qui s'est vendu — ${periodLbl}`;
  }
  if (!d.has_items) {
    document.getElementById('products-body').innerHTML =
      '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">Le d&eacute;tail par article n&rsquo;existe pas sur cette p&eacute;riode.</td></tr>';
  } else if (d.products) {
    const maxQty = d.products.length ? d.products[0].qty : 1;
    const cntEl = document.getElementById('products-count');
    if (cntEl) cntEl.textContent = d.products.length ? `· ${d.products.length}` : '';
    if (!d.products.length) {
      document.getElementById('products-body').innerHTML =
        '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px;">Aucun produit vendu.</td></tr>';
    } else {
      window._prodData = d.products;
      document.getElementById('products-body').innerHTML = d.products.map((p, i) => {
        const barW = Math.round(p.qty / maxQty * 100);
        const rank = i === 0 ? ' style="font-weight:600"' : '';
        const marginHtml = p.margin_pct != null ? marginBadge(p.margin_pct) : '<span style="color:var(--muted)">—</span>';
        const popupBadge = p.popup
          ? ` <span style="font-size:10px;font-weight:600;color:#7c4dbe;background:rgba(124,77,190,.12);border-radius:9px;padding:1px 7px;vertical-align:1px;">popup ${p.commission_pct}%</span>`
          : '';
        return `<tr style="cursor:pointer;" onclick="openProductPopup(${i})">
          <td${rank}>${p.name}${popupBadge}</td>
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
      '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:24px;">Aucune commande.</td></tr>';
    return;
  }
  window._txData = d.recent;
  const recCount = document.getElementById('recent-count');
  if (recCount) recCount.textContent = d.is_single_day
    ? `${d.recent.length} commande${d.recent.length > 1 ? 's' : ''}`
    : `${d.recent.length} dernières`;
  const recLabel = document.getElementById('recent-label');
  if (recLabel) recLabel.textContent = d.is_single_day ? 'Commandes du jour' : 'Commandes';
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

// ── Insights visuels ───────────────────────────────────────────────────────
const WD_SHORT = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

/**
 * CE QUE LA PÉRIODE CONTIENT — en services, pas en jours de calendrier.
 *
 * ⚠️ « LA SEMAINE DERNIÈRE » EST AMBIGUË. Sept jours calendaires, ou cinq de service ? Les deux
 * réponses existent et donnent des chiffres différents ; tant que l'écran ne dit pas laquelle
 * il applique, on lit un total sans savoir sur quoi il porte.
 *
 * ⚠️ ET LA COMPARAISON PEUT ÊTRE BANCALE SANS QUE RIEN NE LE DISE. « Semaine en cours » un
 * jeudi contient DEUX services ; « semaine dernière » en contient cinq. Passer de l'une à
 * l'autre fait lire un effondrement de 60 % qui n'est qu'un décalage de calendrier — on le
 * signale là où le choix vient d'être fait.
 */
function renderPeriode(d) {
  const zone = document.getElementById('periode-dit');
  /* ⚠️ ON DÉCRIT LA FENÊTRE DU CALCUL, PAS CELLE QU'ON A DEMANDÉE. Quand la journée en cours
   * est retirée de l'économie — une recette partielle face à des charges entières bascule
   * l'EBITDA dans le rouge sans raison — le résultat porte sur une fenêtre plus courte. Un
   * jeudi, « Semaine en cours » annonçait 2 services et calculait sur 1 : le chiffre était
   * juste, sa légende doublait sa base. */
  const eco = d && d.economics;
  const p = (eco && eco.periode) || (d && d.periode);
  if (!p) { zone.innerHTML = ''; return; }
  const bouts = [];
  const n = p.jours_ouverts;
  bouts.push(`<b>${n}</b> service${n > 1 ? 's' : ''} sur ${p.jours_calendaires} jour`
             + (p.jours_calendaires > 1 ? 's' : ''));
  if (eco && eco.excludes_today) {
    bouts.push('<span class="att">journée en cours exclue du calcul</span>');
  } else if (p.en_cours) {
    bouts.push('<span class="att">période en cours, pas terminée</span>');
  }
  if (d.comp_label) bouts.push(d.comp_label);
  else bouts.push('<span class="att">pas de période comparable</span>');
  zone.innerHTML = bouts.join(' · ');
}

function renderInsights(d) {
  renderReponse(d);
  renderPeriode(d);
  const ins = d.insights;
  const monthZone    = document.getElementById('month-zone');
  const patternsZone = document.getElementById('patterns-zone');
  if (!ins) {
    monthZone.style.display = 'none'; patternsZone.style.display = 'none';
    return;
  }

  /* ⚠️ LE BANDEAU NOIR « VERDICT DU JOUR » EST PARTI. Il répondait à la même question que le
   * bandeau-réponse du haut — « est-ce qu'on couvre nos coûts ? » — mais UNIQUEMENT sur la
   * période « aujourd'hui ». Les six autres n'avaient pas de réponse du tout, et « ce mois-ci »
   * est précisément celle qu'on regarde pour décider quelque chose.
   *
   * ⚠️ ET DEUX RÉPONSES À LA MÊME QUESTION, C'EST UNE DE TROP. Le jour où elles divergeraient —
   * un arrondi, une période incluse d'un côté et pas de l'autre — on ne saurait pas laquelle
   * croire, et on cesserait de croire les deux.
   */

  // Zone 2 "This month" : masquée quand la période EST le mois en cours (doublon).
  const showMonthZone = currentPreset !== 'month' && ins.month && ins.month.days && ins.month.days.length;
  monthZone.style.display = showMonthZone ? '' : 'none';
  if (showMonthZone) {
    document.getElementById('month-zone-label').textContent =
      new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
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
      ? `<strong>${rush.top_share}%</strong> de l'encaissé sur les 3 heures les plus chargées (${rush.hours.map(h => h + 'h').join(', ')})`
      : 'plus foncé = plus encaissé · heures 8–16';
    document.getElementById('ins-heatmap').innerHTML = `
      <div class="ins-label">Carte des pics — encaissé par heure (28 jours)</div>
      ${html}
      <div class="ins-sub">${rushLine}</div>`;
  } else {
    document.getElementById('ins-heatmap').innerHTML = `<div class="ins-label">Rush heatmap</div><div class="ins-sub">Pas encore assez de données.</div>`;
  }

  // 3+4. Mois : cumul EBITDA + projection / calendrier break-even
  const m = ins.month;
  if (m && m.days && m.days.length) {
    const opens = m.days.filter(x => x.open);
    const pts   = opens.map(x => x.cum);
    // ⚠️ `proj_end` peut valoir null : aucun jour PLEIN dans le mois, donc rien pour asseoir
    // une moyenne. fmt(null) rendrait « €0.00 projected d'ici la fin du mois » — une prévision
    // fabriquée, exactement ce que le serveur refuse désormais d'affirmer.
    const hasProj = m.proj_end != null;
    const allVals = pts.concat(hasProj ? [m.proj_end, 0] : [0]);
    const lo = Math.min(...allVals), hi = Math.max(...allVals);
    const W = 600, H = 100, span = (hi - lo) || 1;
    const y = v => 8 + (H - 16) * (1 - (v - lo) / span);
    const n = opens.length;
    const x = i => n > 1 ? (i / (n - 1)) * (W * 0.72) : 0;
    const path = pts.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const projPath = hasProj
      ? `M${x(n - 1).toFixed(1)},${y(pts[n - 1]).toFixed(1)} L${W - 4},${y(m.proj_end).toFixed(1)}`
      : '';
    document.getElementById('ins-month').innerHTML = `
      <div class="ins-label">Month EBITDA — cumulative + projection</div>
      <svg class="ins-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <line x1="0" y1="${y(0).toFixed(1)}" x2="${W}" y2="${y(0).toFixed(1)}" stroke="var(--border)" stroke-width="1.5"/>
        <path d="${path}" fill="none" stroke="var(--flux-keep)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
        ${hasProj ? `<path d="${projPath}" fill="none" stroke="var(--flux-leave)" stroke-width="2.5" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>` : ''}
      </svg>
      <div class="ins-sub">
        MTD <strong style="color:${m.cum_now >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.cum_now)}</strong>
        · ${hasProj
            ? `projected <strong style="color:${m.proj_end >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(m.proj_end)}</strong> d'ici la fin du mois`
            : `<span style="color:var(--muted)">pas encore de jour plein ce mois-ci — aucune projection</span>`}
        ${m.cross_date ? ` · crossed €0 on ${new Date(m.cross_date + 'T12:00:00').toLocaleDateString('fr-FR', {day:'numeric', month:'short'})}` : ''}
      </div>
      ${m.proj_ca_end != null ? `
      <div class="ins-sub" style="margin-top:4px;">
        Revenue: MTD <strong>${fmt(m.ca_mtd)}</strong>
        · projected <strong>${fmt(m.proj_ca_end)}</strong> d'ici la fin du mois
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
      cal += `<div class="cal-cell" style="background:${bg};color:${color};" data-tip="${new Date(day.date+'T12:00:00').toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'})}${day.ebitda != null ? ' · EBITDA ' + fmt(day.ebitda) : ' · fermé'}">${dt.getDate()}</div>`;
    }
    const greens = opens.filter(x => x.ebitda >= 0).length;
    document.getElementById('ins-calendar').innerHTML = `
      <div class="ins-label">Calendrier du point mort</div>
      <div class="cal-grid">${cal}</div>
      <div class="ins-sub">vert = au-dessus du point mort · ${greens}/${opens.length} services</div>`;
  } else {
    document.getElementById('ins-month').innerHTML = `<div class="ins-label">Month EBITDA</div><div class="ins-sub">Pas encore assez de données.</div>`;
    document.getElementById('ins-calendar').innerHTML = `<div class="ins-label">Calendrier du point mort</div><div class="ins-sub">Pas encore assez de données.</div>`;
  }

  // Articles par ticket (attach)
  const bk = ins.basket;
  if (bk && bk.items_per_ticket != null) {
    document.getElementById('ins-basket').innerHTML = `
      <div class="ins-label">Articles par ticket (${d.period_label.toLowerCase()})</div>
      <div class="ins-big">${bk.items_per_ticket.toFixed(2)}</div>
      <div class="ins-sub">${bk.attach_pct} % des tickets portent 2 articles ou plus — le levier le moins cher</div>`;
  } else {
    document.getElementById('ins-basket').innerHTML = `<div class="ins-label">Articles par ticket</div><div class="ins-sub">Pas encore assez de données.</div>`;
  }

  // 7. CA par place assise
  const st = ins.seat;
  if (st && st.per_seat_day != null) {
    document.getElementById('ins-seat').innerHTML = `
      <div class="ins-label">Encaissé par place / open day</div>
      <div class="ins-big">${fmt(st.per_seat_day)}</div>
      <div class="ins-sub">${st.seats} places (${st.terrace} en terrasse + ${st.inside} en salle) · ${fmt(st.per_seat_period)}/place sur la période</div>`;
  } else {
    document.getElementById('ins-seat').innerHTML = `<div class="ins-label">Encaissé par place</div><div class="ins-sub">Pas encore assez de données.</div>`;
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
  const ref = prevLabel || 'semaine passée';

  document.getElementById('hourly-bars').innerHTML =
    `<div class="dbar-row"><div class="dbar-zero"></div>` + hours.map((hr, i) => {
      const dv  = diffs[i];
      const now = vals[i] || 0, pv = prevByHour[hr] || 0;
      const px  = Math.round(Math.abs(dv) / maxAbs * 58);
      const pct = pv > 0 ? Math.round(dv / pv * 100) : null;
      const tip = (now || pv)
        ? `${hr}h · ${fmt(now)} vs ${fmt(pv)} — ${dv >= 0 ? '+' : ''}${fmt(dv)}`
          + (pct !== null ? ` (${dv >= 0 ? '+' : ''}${pct}%)` : '')
        : `${hr}h · aucune vente`;
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
        tip += ` — ${prevLabel || 'semaine passée'}: ${fmt(pv)}`
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
        + ` <span style="color:var(--faint)">vs ${prevLabel || 'semaine passée'}</span>`;
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



// ── Overview / Cashflow ───────────────────────────────────────────────────
let cashflowData = null;   // chargé une seule fois, mis en cache côté client
let chartCashflow = null;



// ── Commissions reçues : liste + saisie (vue Cashflow) ──────────────────────


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


// ── Produits popup (chef partenaire) ─────────────────────────────────────────
// La commission sur le TTC est la marge brute : côté serveur, le coût du
// produit devient net × (1 − commission), donc la marge % affichée = le taux.
let _popupProd = null;

function openProductPopup(i) {
  const p = (window._prodData || [])[i];
  if (!p) return;
  _popupProd = p;
  document.getElementById('popup-prod-name').textContent = p.name;
  document.getElementById('popup-prod-meta').textContent =
    `${p.qty} vendus · ${fmt(p.revenue)}` + (p.margin_pct != null ? ` · marge ${p.margin_pct} %` : '');
  const check = document.getElementById('popup-check');
  check.checked = !!p.popup;
  const sel = document.getElementById('popup-pct-select');
  const custom = document.getElementById('popup-pct-custom');
  const pct = p.commission_pct;
  if (pct != null && ['10','15','20'].includes(String(pct))) {
    sel.value = String(pct); custom.style.display = 'none';
  } else if (pct != null) {
    sel.value = 'custom'; custom.style.display = ''; custom.value = pct;
  } else {
    sel.value = '20'; custom.style.display = 'none'; custom.value = '';
  }
  document.getElementById('popup-error').style.display = 'none';
  popupCheckChanged();
  document.getElementById('popup-overlay').style.display = '';
  document.getElementById('popup-modal').style.display = '';
}
function closeProductPopup() {
  document.getElementById('popup-overlay').style.display = 'none';
  document.getElementById('popup-modal').style.display = 'none';
  _popupProd = null;
}
function popupCheckChanged() {
  document.getElementById('popup-pct-row').style.display =
    document.getElementById('popup-check').checked ? '' : 'none';
}
function popupPctChanged() {
  const isCustom = document.getElementById('popup-pct-select').value === 'custom';
  const custom = document.getElementById('popup-pct-custom');
  custom.style.display = isCustom ? '' : 'none';
  if (isCustom) custom.focus();
}
async function saveProductPopup() {
  if (!_popupProd) return;
  const popup = document.getElementById('popup-check').checked;
  let pct = document.getElementById('popup-pct-select').value;
  if (pct === 'custom') pct = document.getElementById('popup-pct-custom').value;
  const errEl = document.getElementById('popup-error');
  if (popup && !(parseFloat(pct) >= 0 && parseFloat(pct) < 100)) {
    errEl.textContent = 'Commission invalide — entre 0 et 100 %.';
    errEl.style.display = ''; return;
  }
  const btn = document.getElementById('popup-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const r = await fetch('/api/popup-flag', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: _popupProd.name, popup, commission_pct: parseFloat(pct)})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.status);
    closeProductPopup();
    loadData(true);   // recharge : badge, marge, COGS et EBITDA reflètent le flag
  } catch (e) {
    errEl.textContent = 'Erreur : ' + e.message;
    errEl.style.display = '';
  } finally {
    btn.disabled = false; btn.textContent = 'Enregistrer';
  }
}

/* ── La commande qu'on vient de cliquer ───────────────────────────────────────
 * ⚠️ REVENU AVEC LA LISTE. Ces fonctions avaient été retirées parce que plus rien ne les
 * appelait — c'était juste à ce moment-là, et faux dès que la liste est revenue. Le contrôle
 * « aucune fonction orpheline » les aurait signalées dans les deux sens.
 */
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
