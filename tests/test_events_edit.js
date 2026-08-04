// Le bouton « Éditer » de /events. Sans dépendance : node tests/test_events_edit.js
//
// LE BUG. `.modal` et `.drawer` portaient tous deux z-index:101. À égalité, c'est l'ordre du
// DOM qui tranche, et le tiroir est déclaré après le modal (l.320 contre l.247) : il passait
// donc par-dessus. Comme le handler « Éditer » ne fermait pas le tiroir, le modal s'ouvrait
// derrière lui. Sur téléphone le tiroir fait 96vw — recouvrement total, et le bouton semblait
// inerte alors qu'il fonctionnait.
//
// Deux invariants sont vérifiés ici, parce que deux choses distinctes cassaient :
//   1. le handler ferme le tiroir AVANT d'ouvrir le modal, et lit l'événement AVANT de fermer
//      (closeDrawer remet selectedId à null) ;
//   2. le modal reste au-dessus du tiroir dans le CSS, pour que le cas ne puisse pas revenir
//      par un autre chemin.
//
// Le handler est EXÉCUTÉ, pas grepé : un test qui cherche « closeDrawer » dans le source
// passerait au vert sur un appel placé après openModal, c'est-à-dire sur le bug lui-même.

const fs = require('fs');
const path = require('path');

const tpl = fs.readFileSync(path.join(__dirname, '..', 'templates', 'events.html'), 'utf8');

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// ── 1 · Le handler ───────────────────────────────────────────────────────────
const m = tpl.match(/\$\('d-edit'\)\.onclick = \(\)=>\{[\s\S]*?\n\};/);
if (!m) {
  console.error("✗ handler de #d-edit introuvable dans templates/events.html");
  process.exit(1);
}

// `selectedId` est une VRAIE liaison mutable dans la portée du handler, pour que le
// closeDrawer simulé puisse la remettre à null comme le fait le vrai. Le passer en paramètre
// le figeait par valeur : la remise à zéro n'avait aucun effet et l'assertion sur l'ordre de
// lecture ne prouvait rien.
function runHandler(events, initialId) {
  const trace = [];
  const src = `
    let selectedId = ${JSON.stringify(initialId)};
    const closeDrawer = () => { trace.push('closeDrawer'); selectedId = null; };
    const openModal  = ev => trace.push('openModal:' + (ev && ev.id));
    let handler = null;
    const $ = () => ({ set onclick(fn) { handler = fn; } });
    ${m[0]}
    if (handler) handler();
  `;
  new Function('events', 'trace', src)(events, trace);
  return trace;
}

{
  const t = runHandler([{ id: 'ev-1', title: 'Pop-up torréfacteur' }], 'ev-1');
  check('le tiroir est fermé avant l’ouverture du modal',
    t[0] === 'closeDrawer' && t[1] === 'openModal:ev-1', `trace = ${JSON.stringify(t)}`);
  // Cette assertion EST la preuve de l'ordre de lecture : si l'événement était cherché après
  // closeDrawer, selectedId vaudrait null, la recherche échouerait et openModal ne serait
  // jamais appelé. Elle tombe donc précisément sur l'inversion.
  check('l’événement est lu avant la remise à zéro de selectedId',
    t.includes('openModal:ev-1'), `trace = ${JSON.stringify(t)}`);
}
{
  const t = runHandler([{ id: 'ev-1' }], 'ev-inconnu');
  check('sans sélection valide, rien n’est fermé ni ouvert',
    t.length === 0, `trace = ${JSON.stringify(t)}`);
}

// ── 2 · L'empilement ─────────────────────────────────────────────────────────
function zIndexOf(selector) {
  const re = new RegExp(`\\n\\.${selector} \\{[^}]*z-index:\\s*(\\d+)`);
  const hit = tpl.match(re);
  return hit ? Number(hit[1]) : null;
}
const zModal = zIndexOf('modal'), zDrawer = zIndexOf('drawer'), zOverlay = zIndexOf('overlay');

check('les z-index sont lisibles dans le template',
  zModal !== null && zDrawer !== null && zOverlay !== null,
  `modal=${zModal} drawer=${zDrawer} overlay=${zOverlay}`);
check('le modal passe au-dessus du tiroir',
  zModal > zDrawer, `modal=${zModal} vs drawer=${zDrawer}`);
check('les deux passent au-dessus du voile',
  zModal > zOverlay && zDrawer > zOverlay,
  `overlay=${zOverlay}`);

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
