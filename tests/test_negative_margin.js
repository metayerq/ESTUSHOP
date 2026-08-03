// L'alerte « vendu sous son coût » — sans dépendance : node tests/test_negative_margin.js
//
// Comme test_usage_ranking.js, la fonction est lue DANS le template livré, pas recopiée.
//
// Les chiffres des cas viennent du catalogue Vendus réel d'Estudantina (3 août 2026), parce
// qu'une règle d'alerte se juge sur ce qu'elle dit des vraies données, pas sur des cas ronds.

const fs = require('fs');
const path = require('path');

const tpl = fs.readFileSync(
  path.join(__dirname, '..', 'templates', 'cogs.html'), 'utf8');

const m = tpl.match(/function negativeMarginProducts\(products\) \{[\s\S]*?\n\}/);
if (!m) {
  console.error('✗ negativeMarginProducts introuvable dans templates/cogs.html');
  process.exit(1);
}
const negativeMarginProducts = new Function(`${m[0]}; return negativeMarginProducts;`)();

let failures = 0, ran = 0;
function check(nom, condition, detail) {
  ran++;
  if (condition) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// Catalogue réel, 3 août 2026.
const CATALOGUE = [
  { title: 'FAZENDA SANTA MARTHA', price_ht: 9.76,  price_ttc: 12.00, supply_price: 12.10, has_recipe: false },
  { title: 'LA COLINA',            price_ht: 12.85, price_ttc: 15.80, supply_price: 15.80, has_recipe: false },
  { title: 'MOUNT ELGON',          price_ht: 12.36, price_ttc: 15.20, supply_price: 15.20, has_recipe: false },
  { title: 'TIMANA DECAF',         price_ht: 12.44, price_ttc: 15.30, supply_price: 15.30, has_recipe: false },
  { title: 'EL TAMBO',             price_ht: 11.54, price_ttc: 14.20, supply_price: 9.81,  has_recipe: false },
  { title: 'Cappuccino',           price_ht: 2.65,  price_ttc: 3.00,  supply_price: 0,     has_recipe: true, recipe_total: 0.42 },
];

{
  const bad = negativeMarginProducts(CATALOGUE);
  check('les quatre produits sous leur coût sont trouvés, et eux seuls',
    bad.length === 4, `${bad.length} trouvé(s) : ${bad.map(b => b.title).join(', ')}`);
  check('un produit à marge faible mais positive reste hors alerte',
    !bad.some(b => b.title === 'EL TAMBO'));
  check('classé par la perte en euros, pas en pourcentage',
    bad[0].title === 'LA COLINA', `tête de liste : ${bad[0].title}`);
  check('la perte par unité est la différence HT',
    Math.abs(bad[0].loss - 2.95) < 0.005, `perte = ${bad[0].loss}`);
}

// ── La distinction qui évite d'accuser un fournisseur à tort ─────────────────
{
  const bad = negativeMarginProducts(CATALOGUE);
  const suspects = bad.filter(b => b.costLooksLikeSalePrice).map(b => b.title);
  check('un coût égal au prix de vente TTC est signalé comme tel',
    suspects.length === 3 && !suspects.includes('FAZENDA SANTA MARTHA'),
    `signalés : ${suspects.join(', ')}`);
  check('un vrai prix fournisseur n’est pas confondu avec une faute de frappe',
    bad.find(b => b.title === 'FAZENDA SANTA MARTHA').costLooksLikeSalePrice === false);
}

// ── Un coût inconnu n'est pas une perte ──────────────────────────────────────
{
  const sansCout = [{ title: 'Livre', price_ht: 23.58, price_ttc: 25.00, supply_price: 0, has_recipe: false }];
  check('sans prix d’achat ni recette, aucun avis n’est rendu',
    negativeMarginProducts(sansCout).length === 0);

  const sansPrix = [{ title: 'Offert', price_ht: 0, price_ttc: 0, supply_price: 3.20, has_recipe: false }];
  check('un produit sans prix de vente n’est pas une perte à afficher ici',
    negativeMarginProducts(sansPrix).length === 0);
}

// ── Quand une recette existe, c'est elle qui fait foi ────────────────────────
{
  // supply_price traîne à 0,10 € mais la recette dit 4,00 € : c'est la recette qui compte,
  // sinon un coût d'achat résiduel masquerait une perte réelle.
  const p = [{ title: 'Brunch', price_ht: 3.00, price_ttc: 3.39,
               supply_price: 0.10, has_recipe: true, recipe_total: 4.00 }];
  const bad = negativeMarginProducts(p);
  check('le coût recette prime sur le prix d’achat', bad.length === 1 && bad[0].fromRecipe === true);
  check('la perte est calculée sur la recette', Math.abs(bad[0].loss - 1.00) < 0.005);
}

// ── Robustesse ───────────────────────────────────────────────────────────────
{
  check('un catalogue vide ou absent ne casse rien',
    negativeMarginProducts([]).length === 0 && negativeMarginProducts(undefined).length === 0);
  check('une marge exactement nulle n’est pas une perte',
    negativeMarginProducts([{ title: 'Pile', price_ht: 5, price_ttc: 5.65, supply_price: 5, has_recipe: false }]).length === 0);
}

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
