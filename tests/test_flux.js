// Le trajet — la cascade du dashboard. Sans dépendance : node tests/test_flux.js
//
// La fonction est lue DANS static/dashboard.js, pas recopiée.
//
// Les cas partent des chiffres réels du lundi 3 août 2026 : 191,70 € encaissés, TVA 13 %,
// marge mesurée 79,7 %, charges 67,81 € + 129,27 €, EBITDA −61,87 €.

const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'dashboard.js'), 'utf8');
const m = src.match(/function fluxSteps\(eco\) \{[\s\S]*?\n\}/);
if (!m) {
  console.error('✗ fluxSteps introuvable dans static/dashboard.js — renommée ou supprimée ?');
  process.exit(1);
}
const fluxSteps = new Function(`${m[0]}; return fluxSteps;`)();

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

const JOUR = {
  ca_ttc: 191.70, ca_ht: 169.65,
  marge_brute_ht: 135.21, marge_is_estimated: false, cogs_coverage_pct: 100,
  cout_fixe_periode: 67.81, cout_perso_periode: 129.27,
  ebitda_ht: -61.87,
};

// ── La cascade doit retomber exactement sur l'EBITDA du serveur ──────────────
{
  const f = fluxSteps(JOUR);
  check('le trajet est traçable sur une journée normale', f.ok === true, f.reason);
  const dernier = f.steps[f.steps.length - 1].after;
  check('le dernier palier est l’EBITDA, pas une somme recalculée',
    Math.abs(dernier - JOUR.ebitda_ht) < 0.005, `palier = ${dernier}`);
  check('cinq postes : CA, TVA, matière, charges, personnel', f.steps.length === 5);
}

// ── La matière n'est PAS cogs_ht ─────────────────────────────────────────────
{
  // Couverture 60 % : cogs_ht ne mesure que 60 % des ventes, mais le taux mesuré est appliqué
  // à tout le CA. Soustraire cogs_ht ferait atterrir la cascade à côté de l'EBITDA.
  const partiel = { ...JOUR, cogs_ht: 20.66, marge_is_estimated: true, cogs_coverage_pct: 60 };
  const f = fluxSteps(partiel);
  const mat = f.steps.find(s => s.key === 'cogs');
  check('la matière vaut ca_ht − marge_brute_ht, pas cogs_ht',
    Math.abs(mat.amount - 34.44) < 0.005, `matière = ${mat.amount}`);
  check('une matière extrapolée est marquée comme telle', mat.estimated === true);
  check('la couverture est remontée pour pouvoir être citée', f.coverage === 60);
}

// ── Un poste manquant n'est jamais dessiné à zéro ────────────────────────────
{
  const sansMarge = { ...JOUR, marge_brute_ht: null };
  check('sans marge mesurable, aucun trajet — et la raison est nommée',
    fluxSteps(sansMarge).ok === false && fluxSteps(sansMarge).reason === 'no-margin');

  const sansCharges = { ...JOUR, cout_fixe_periode: 0, cout_perso_periode: 0,
                        cout_fixe_jour: null, cout_perso_jour: null };
  check('sans charges connues, aucun trajet',
    fluxSteps(sansCharges).reason === 'no-costs');

  check('sans vente, aucun trajet', fluxSteps({ ...JOUR, ca_ttc: 0 }).reason === 'no-sales');
  check('un payload absent ne casse rien', fluxSteps(undefined).ok === false);
}

// ── Le garde-fou : si les postes ne recomposent pas l'EBITDA, on ne dessine pas ──
{
  // EBITDA du serveur incohérent avec les postes (un coût existe qu'on ne modélise pas).
  // Dessiner quand même produirait une cascade qui rate sa cible sans le dire.
  const boiteux = { ...JOUR, ebitda_ht: -20.00 };
  const f = fluxSteps(boiteux);
  check('un écart entre la cascade et l’EBITDA bloque le tracé',
    f.ok === false && f.reason === 'mismatch', `reason = ${f.reason}`);
  check('l’écart est chiffré pour être diagnosticable',
    Math.abs(f.drift - (-41.87)) < 0.005, `drift = ${f.drift}`);
}

// ── Géométrie ────────────────────────────────────────────────────────────────
{
  const f = fluxSteps(JOUR);
  const span = 191.70 - (-61.87);
  check('la première barre part de la gauche', f.steps[0].left === 0);
  check('la première barre occupe la part du CA dans l’amplitude',
    Math.abs(f.steps[0].width - (191.70 / span) * 100) < 0.01);
  check('chaque poste démarre là où le précédent s’arrête',
    f.steps.slice(1).every((s, i) =>
      Math.abs(s.left - ((191.70 - f.steps[i].after) / span) * 100) < 0.01));
  check('le zéro est positionné pour ancrer un EBITDA négatif',
    Math.abs(f.zeroPct - (191.70 / span) * 100) < 0.01);
  check('aucune largeur négative', f.steps.every(s => s.width >= 0));
}

// ── Une période bénéficiaire ─────────────────────────────────────────────────
{
  const bon = { ...JOUR, ca_ttc: 500.00, ca_ht: 442.48,
                marge_brute_ht: 352.66, ebitda_ht: 155.58 };
  const f = fluxSteps(bon);
  check('un EBITDA positif est traçable aussi',
    f.ok === true && f.ebitda > 0, f.reason);
  check('le zéro est au bord droit quand rien n’est négatif',
    Math.abs(f.zeroPct - 100) < 0.01, `zeroPct = ${f.zeroPct}`);
}

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
