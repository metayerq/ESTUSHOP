// Prime cost — le titre et son sous-texte parlaient de deux COGS différents.
// Sans dépendance : node tests/test_prime_cost.js
//
// LE BUG. Le chiffre utilisait `cogs_ht`, mesuré sur la seule part des ventes dont le coût
// d'achat est connu. Le sous-texte, lui, affichait `100 − marge_brute_ht_pct`, le taux
// extrapolé à tout le CA. À 60 % de couverture, le titre annonçait 48 % en VERT pendant que sa
// propre ligne du dessous additionnait 30 + 30 = 60 %, au-delà de la cible. Le prime cost était
// sous-estimé exactement du déficit de couverture, et jamais marqué comme estimé — alors que la
// marge brute, elle, l'était depuis le portage du seuil de couverture.
//
// Le bloc de rendu est EXÉCUTÉ avec un DOM minimal, pas grepé : c'est la cohérence entre le
// nombre affiché et sa ligne d'explication qui est en cause, et elle ne se lit pas dans le source.

const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'dashboard.js'), 'utf8');

// L'extraction part des déclarations d'éléments : le bloc de calcul s'en sert, les isoler
// seuls donnerait un ReferenceError plutôt qu'un test.
const m = src.match(/    const primeEl = document\.getElementById\('eco-prime'\);[\s\S]*?\n    \} else \{/);
if (!m) {
  console.error('✗ bloc prime cost introuvable dans static/dashboard.js');
  process.exit(1);
}
// On coupe avant le `} else {` pour ne garder que la branche calculante.
const bloc = m[0].replace(/\n    \} else \{$/, '\n    }');

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

function rendre(eco, primePerso) {
  const els = {
    'eco-prime':     { textContent: '', style: {} },
    'eco-prime-sub': { innerHTML: '' },
    'eco-prime-bar': { innerHTML: '' },
  };
  const document = { getElementById: id => els[id] };
  const fmt = n => '€' + Number(n).toFixed(2);
  new Function('document', 'eco', 'primePerso', 'fmt', bloc)(document, eco, primePerso, fmt);
  return {
    valeur: parseFloat(els['eco-prime'].textContent),
    sous:   els['eco-prime-sub'].innerHTML,
    couleur: els['eco-prime'].style.color,
  };
}

// Couverture 60 % : coût connu sur 600 € de CA, 180 € de COGS mesuré → taux matière 30 %,
// extrapolé aux 1000 € de CA → 300 € de matière. Personnel 300 €.
const PARTIEL = {
  ca_ht: 1000, cogs_ht: 180, marge_brute_ht: 700,
  marge_brute_ht_pct: 70, marge_is_estimated: true, cogs_coverage_pct: 60,
};

{
  const r = rendre(PARTIEL, 300);
  check('le prime cost est calculé sur la matière extrapolée',
    Math.abs(r.valeur - 60.0) < 0.05, `affiché ${r.valeur}% (48 % = l'ancien bug)`);
  check('l’ancien calcul donnait 48 %, soit 12 points de moins',
    Math.abs(r.valeur - ((PARTIEL.cogs_ht + 300) / PARTIEL.ca_ht * 100)) > 11,
    'le chiffre n’a pas bougé par rapport au calcul fautif');
  check('le sous-texte annonce la même matière que le titre',
    /COGS 30%/.test(r.sous), r.sous);
  check('le titre et son sous-texte se recomposent',
    Math.abs(r.valeur - 60.0) < 0.05 && /COGS 30% · Labour 30%/.test(r.sous), r.sous);
  check('l’extrapolation est annoncée avec son taux de couverture',
    /extrapolée sur 60% des ventes/.test(r.sous), r.sous);
}

// Couverture totale : rien n'est extrapolé, rien ne doit être marqué.
{
  const complet = { ca_ht: 1000, cogs_ht: 300, marge_brute_ht: 700,
                    marge_brute_ht_pct: 70, marge_is_estimated: false, cogs_coverage_pct: 100 };
  const r = rendre(complet, 300);
  check('à 100 % de couverture le chiffre est inchangé', Math.abs(r.valeur - 60.0) < 0.05);
  check('…et rien n’est marqué extrapolé', !/extrapolée/.test(r.sous), r.sous);
}

// Le cas qui change vraiment le verdict à l'écran : matière 350 + personnel 350 = 70 %,
// au-delà du seuil vert de 67 %. L'ancien calcul (cogs_ht 210 + 350 = 56 %) l'affichait en
// vert — un prime cost au-dessus de la cible qui se donnait pour sain.
{
  const bascule = { ca_ht: 1000, cogs_ht: 210, marge_brute_ht: 650,
                    marge_brute_ht_pct: 65, marge_is_estimated: true, cogs_coverage_pct: 60 };
  const r = rendre(bascule, 350);
  check('un prime cost réellement au-dessus du seuil n’est plus affiché en vert',
    Math.abs(r.valeur - 70.0) < 0.05 && r.couleur !== 'var(--green)',
    `${r.valeur}% / ${r.couleur}`);
}

// Un prime cost sain reste vert.
{
  const sain = { ca_ht: 1000, cogs_ht: 250, marge_brute_ht: 750,
                 marge_brute_ht_pct: 75, marge_is_estimated: false, cogs_coverage_pct: 100 };
  const r = rendre(sain, 300);
  check('55 % reste sous la cible et s’affiche en vert',
    Math.abs(r.valeur - 55.0) < 0.05 && r.couleur === 'var(--green)',
    `${r.valeur}% / ${r.couleur}`);
}

// Aucune couleur codée en dur hors des tokens Flux.
{
  const r = rendre(PARTIEL, 300);
  check('les barres utilisent les tokens, pas le bleu Mesa',
    !/#2554C7/.test(r.sous), 'bleu blueprint résiduel');
}

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
