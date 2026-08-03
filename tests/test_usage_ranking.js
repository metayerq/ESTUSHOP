// L'ordre des écarts de consommation — premier test JavaScript de ce dépôt.
//
// Il n'y a pas d'outillage front ici, et en installer un pour une fonction serait
// disproportionné. Ce fichier n'a donc AUCUNE dépendance : `node tests/test_usage_ranking.js`.
//
// ⚠️ IL LIT LA FONCTION DANS LE TEMPLATE RÉEL, pas une copie. Une copie divergerait du code
// livré sans que rien ne le signale — et c'est exactement le genre de faux vert qui donne
// l'impression d'être couvert. En contrepartie, il dépend du nom `rankUsageRows` : si la
// fonction est renommée, le test échoue bruyamment au lieu de tester du vide.

const fs = require('fs');
const path = require('path');

const tpl = fs.readFileSync(
  path.join(__dirname, '..', 'templates', 'cogs.html'), 'utf8');

const m = tpl.match(/function rankUsageRows\(rows, bought, cap\) \{[\s\S]*?\n\}/);
if (!m) {
  console.error('✗ rankUsageRows introuvable dans templates/cogs.html — renommée ou supprimée ?');
  process.exit(1);
}
const rankUsageRows = new Function(`${m[0]}; return rankUsageRows;`)();

let failures = 0, ran = 0;
function check(nom, condition, detail) {
  ran++;
  if (condition) { console.log(`  ✓ ${nom}`); }
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// Coût unitaire 1 €/unité partout, pour que l'écart en euros se lise directement.
const ing = (name, qty, cost) => ({ name, qty, cost, unit_ref: 'kg' });

// ── Le classement se fait en euros, pas en pourcentage ───────────────────────
{
  // Lait : 100 consommés, 112 achetés → +12 %, mais 12 € d'écart.
  // Cannelle : 1 consommé, 3 achetés → +200 %, et 2 € d'écart.
  const rows   = [ing('Lait', 100, 100), ing('Cannelle', 1, 1)];
  const bought = { 'Lait': { qty: 112 }, 'Cannelle': { qty: 3 } };
  const r = rankUsageRows(rows, bought, 10);
  check('un gros % sur un ingrédient bon marché ne passe pas devant',
    r.reconciled[0].name === 'Lait',
    `tête de liste : ${r.reconciled[0].name}`);
}

// ── Un écart négatif compte autant qu'un positif ─────────────────────────────
{
  // Acheter beaucoup moins que ce que les ventes expliquent est un signal aussi fort
  // qu'en acheter trop : il manque des factures, ou on puise dans un stock non compté.
  const rows   = [ing('Café', 100, 100), ing('Sucre', 10, 10)];
  const bought = { 'Café': { qty: 40 }, 'Sucre': { qty: 12 } };
  const r = rankUsageRows(rows, bought, 10);
  check('un écart négatif est classé sur sa taille, pas ignoré',
    r.reconciled[0].name === 'Café',
    `tête de liste : ${r.reconciled[0].name}`);
}

// ── Les lignes sans achat ne se mêlent jamais au classement ──────────────────
{
  const rows = [ing('Farine', 50, 50), ing('Lait', 100, 100), ing('Sel', 2, 2)];
  const bought = { 'Lait': { qty: 101 } };   // seul le lait a un achat saisi
  const r = rankUsageRows(rows, bought, 10);
  check('seules les lignes réconciliables sont classées',
    r.reconciled.length === 1 && r.reconciled[0].name === 'Lait');
  check('les autres sont mises à part, pas comptées à −100 %',
    r.unlogged.length === 2 && r.unlogged.every(x => x.name !== 'Lait'));
  check("un écart d'1 € ne disparaît pas derrière des lignes sans achat",
    r.reconciled[0].name === 'Lait');
}

// ── Le plafond dit ce qu'il cache ────────────────────────────────────────────
{
  const rows = Array.from({ length: 53 }, (_, i) => ing(`Ing${i}`, 10, 10));
  const r = rankUsageRows(rows, {}, 10);
  check('hidden compte exactement les lignes tronquées',
    r.hidden === 43, `hidden = ${r.hidden}`);
  check('rien à annoncer quand rien n’est caché',
    rankUsageRows(rows.slice(0, 4), {}, 10).hidden === 0);
}

// ── Un ingrédient consommé à zéro n'est pas réconciliable ────────────────────
{
  // qty = 0 : le pourcentage d'écart serait une division par zéro. La ligne n'a pas sa
  // place dans un classement d'écarts, même si un achat existe.
  const rows   = [ing('Vanille', 0, 0)];
  const bought = { 'Vanille': { qty: 5 } };
  const r = rankUsageRows(rows, bought, 10);
  check('consommation nulle → non classée, pas un écart infini',
    r.reconciled.length === 0 && r.unlogged.length === 1);
}

// ── Robustesse ───────────────────────────────────────────────────────────────
{
  const r = rankUsageRows(undefined, {}, 10);
  check('une période sans consommation ne casse pas le tri',
    r.reconciled.length === 0 && r.unlogged.length === 0 && r.hidden === 0);
}

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
