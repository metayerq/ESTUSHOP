// Le RENDU du trajet, pas seulement sa règle. node tests/test_flux_render.js
//
// POURQUOI CE FICHIER EXISTE. Plusieurs livraisons de cette session se sont terminées par « le
// rendu JS n'est pas testé » : la logique était vérifiée, le HTML produit ne l'était pas. Or
// c'est là que tombent les pannes réelles — une variable hors de portée, une clé de payload qui
// n'existe pas, un `undefined` imprimé dans la page.
//
// Il n'y a pas de DOM ici et installer jsdom serait disproportionné. On fournit donc le strict
// minimum dont renderFlux a besoin : un `document.getElementById` qui rend un objet capable de
// recevoir `innerHTML`. Cela suffit à exécuter le vrai code de rendu et à lire ce qu'il écrit.

const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'dashboard.js'), 'utf8');

function grab(re, nom) {
  const m = src.match(re);
  if (!m) { console.error(`✗ ${nom} introuvable dans static/dashboard.js`); process.exit(1); }
  return m[0];
}
const fmtSrc   = grab(/const fmt = n => new Intl\.NumberFormat[\s\S]*?\}\)\.format\(n\);/, 'fmt');
const stepsSrc = grab(/function fluxSteps\(eco\) \{[\s\S]*?\n\}/, 'fluxSteps');
const rendSrc  = grab(/function renderFlux\(d\) \{[\s\S]*?\n\}/, 'renderFlux');

/* DOM minimal : un seul nœud, celui que renderFlux cherche. */
function makeEnv() {
  const el = { innerHTML: '' };
  const document = { getElementById: id => (id === 'flux' ? el : null) };
  const run = new Function('document', `${fmtSrc}\n${stepsSrc}\n${rendSrc}\nreturn renderFlux;`)(document);
  return { el, renderFlux: run };
}

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

const JOUR = {
  economics: {
    ca_ttc: 191.70, ca_ht: 169.65,
    marge_brute_ht: 135.21, marge_is_estimated: false, cogs_coverage_pct: 100,
    cout_fixe_periode: 67.81, cout_perso_periode: 129.27, ebitda_ht: -61.87,
  },
  period_label: 'Today',
};

// ── Le rendu s'exécute et écrit quelque chose ────────────────────────────────
{
  const { el, renderFlux } = makeEnv();
  renderFlux(JOUR);
  const h = el.innerHTML;
  check('le rendu produit du HTML', h.length > 200, `${h.length} caractères`);
  check('aucun "undefined" imprimé dans la page', !h.includes('undefined'),
    (h.match(/.{0,40}undefined.{0,40}/) || [''])[0]);
  check('aucun "NaN" imprimé dans la page', !h.includes('NaN'),
    (h.match(/.{0,40}NaN.{0,40}/) || [''])[0]);
  // [" ] et pas seulement "flux-row" : sinon le conteneur `flux-rows` est compté lui aussi.
  check('les six lignes sont présentes (5 postes + total)',
    (h.match(/class="flux-row[" ]/g) || []).length === 6,
    `${(h.match(/class="flux-row[" ]/g) || []).length} ligne(s)`);
  check('les montants sont formatés en euros', h.includes('€'));
  check('le libellé de période est repris', h.includes('Today'));
  check('l’EBITDA négatif porte la classe rouge', h.includes('flux-amount neg'));
  check('aucune largeur ou position NaN dans les styles',
    !/(?:left|width):\s*NaN/.test(h));
}

// ── L'état extrapolé se voit ─────────────────────────────────────────────────
{
  const { el, renderFlux } = makeEnv();
  renderFlux({ ...JOUR, economics: { ...JOUR.economics,
    marge_is_estimated: true, cogs_coverage_pct: 62 } });
  const h = el.innerHTML;
  check('la matière extrapolée porte la hachure', h.includes('is-estimated'));
  check('la réserve cite le taux de couverture réel', h.includes('62%'));
  check('la légende gagne l’entrée « extrapolé »', h.includes('extrapolé'));
}
{
  const { el, renderFlux } = makeEnv();
  renderFlux(JOUR);
  check('rien n’est marqué extrapolé quand tout est mesuré',
    !el.innerHTML.includes('is-estimated'));
}

// ── Les cas sans trajet disent pourquoi, et ne montrent aucun zéro ───────────
{
  const { el, renderFlux } = makeEnv();
  renderFlux({ economics: { ...JOUR.economics, marge_brute_ht: null }, period_label: 'Today' });
  const h = el.innerHTML;
  check('sans marge, la raison est écrite en clair', h.includes('fiches recettes'));
  check('…et aucune barre n’est dessinée', !h.includes('flux-seg'));
  check('…et aucun montant à 0,00 € n’apparaît', !h.includes('€0.00') && !h.includes('0,00 €'));
}
{
  const { el, renderFlux } = makeEnv();
  renderFlux({});                                   // payload vide : premier chargement
  check('un payload vide affiche un message, pas une erreur',
    el.innerHTML.includes('Pas de trajet'));
}

// ── Une période bénéficiaire ─────────────────────────────────────────────────
{
  const { el, renderFlux } = makeEnv();
  renderFlux({ economics: { ca_ttc: 500, ca_ht: 442.48, marge_brute_ht: 352.66,
    cout_fixe_periode: 67.81, cout_perso_periode: 129.27, ebitda_ht: 155.58 },
    period_label: 'This week' });
  const h = el.innerHTML;
  check('un EBITDA positif n’est pas rouge', !h.includes('flux-amount neg'));
  check('la phrase annonce ce que la période dégage', h.includes('dégage'));
}

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
