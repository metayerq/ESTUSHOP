// L'ouverture d'un événement sur /events. Sans dépendance : node tests/test_events_edit.js
//
// ── L'HISTOIRE DE CE FICHIER, PARCE QU'ELLE EXPLIQUE CE QU'IL GARDE MAINTENANT ──────────────
//
// PREMIER BUG. `.modal` et `.drawer` portaient tous deux z-index:101. À égalité, c'est l'ordre du
// DOM qui tranche, et le tiroir était déclaré après le modal : il passait donc par-dessus. Le
// handler « Éditer » ne fermant pas le tiroir, le modal s'ouvrait derrière lui. Sur téléphone le
// tiroir fait 96vw — recouvrement total, et le bouton semblait inerte alors qu'il fonctionnait.
// Ce fichier vérifiait alors deux choses : que le handler ferme le tiroir AVANT d'ouvrir le modal,
// et que le modal reste au-dessus du tiroir.
//
// SECOND BUG, LE 23/09/2026. Le même empilement en a produit un autre, et pire. Cliquer un
// événement ouvrait le tiroir ; « Éditer » le fermait puis ouvrait la fenêtre. Entre les deux, le
// voile restait posé avec `pointer-events:auto`, et `overlayMaybeOff()` ne l'éteignait QUE si ni le
// tiroir ni la fenêtre ne portaient leur classe. Un échec quelconque entre ces deux instants
// laissait donc la page entière inerte — sans erreur, sans message, sans rien. Le propriétaire l'a
// décrit exactement comme « ça se bloque juste ».
//
// LA CORRECTION N'EST PAS UN TROISIÈME RUSTINE SUR L'EMPILEMENT : c'est la suppression du tiroir.
// Une seule couche ne peut pas se recouvrir elle-même, et un voile qu'on éteint sans condition ne
// peut pas rester posé. Ce fichier garde désormais CETTE absence — parce qu'une couche supprimée
// est une couche qui peut revenir, et que le prochain à toucher cette page ne saura pas ce que ces
// deux bugs ont coûté.

const fs = require('fs');
const path = require('path');

const tpl = fs.readFileSync(path.join(__dirname, '..', 'templates', 'events.html'), 'utf8');
// ⚠️ LES COMMENTAIRES SONT ÉCARTÉS AVANT TOUTE RECHERCHE. Celui qu'on vient de lire parle du
// tiroir, cite `.drawer` et `overlayMaybeOff` : un détecteur qui lit le source brut trouve sa
// propre explication et passe au vert sur le bug qu'il traque. Ça s'est produit huit fois dans ce
// produit en une soirée.
const src = tpl
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^[ \t]*\/\/.*$/gm, ' ');

let failures = 0, ran = 0;
function check(nom, cond, detail) {
  ran++;
  if (cond) console.log(`  ✓ ${nom}`);
  else { console.error(`  ✗ ${nom}${detail ? ' — ' + detail : ''}`); failures++; }
}

// ── 1 · Il n'y a plus qu'une couche ──────────────────────────────────────────
check('aucun élément #drawer', !/id="drawer"/.test(src));
check('aucune règle CSS .drawer', !/\.drawer\s*\{/.test(src));
check('aucun appel à closeDrawer', !/closeDrawer\s*\(/.test(src));
// ⚠️ « MAYBE » ÉTAIT LE PIÈGE : un voile éteint sous condition est un voile qui peut rester posé.
check('le voile s’éteint sans condition',
  !/overlayMaybeOff/.test(src) && /function overlayOff\(\)\{[^}]*remove\('show'\)/.test(src),
  'overlayMaybeOff est revenu');

// ── 2 · Cliquer un événement ouvre DIRECTEMENT l'édition ─────────────────────
//
// Le handler est EXÉCUTÉ, pas grepé : un test qui cherche « openModal » dans le source passerait
// au vert sur un appel placé derrière une condition qui ne se réalise jamais.
const m = src.match(/function openDrawer\(id\)\{[\s\S]*?\n\}/);
if (!m) {
  console.error('✗ openDrawer introuvable dans templates/events.html');
  process.exit(1);
}
function runOuverture(events, id) {
  const trace = [];
  const code = `
    const openModal = ev => trace.push('openModal:' + (ev && ev.id));
    const signalerPanne = msg => trace.push('panne');
    ${m[0]}
    openDrawer(${JSON.stringify(id)});
  `;
  new Function('events', 'trace', code)(events, trace);
  return trace;
}
{
  const t = runOuverture([{ id: 'ev-1', title: 'Pop-up torréfacteur' }], 'ev-1');
  check('un clic sur l’événement ouvre l’édition, sans étape intermédiaire',
    t.length === 1 && t[0] === 'openModal:ev-1', `trace = ${JSON.stringify(t)}`);
}
{
  // ⚠️ UN ÉVÉNEMENT INTROUVABLE NE SE TAIT PAS. Le `return` muet d'avant laissait un clic sans
  // effet — indistinguable d'une page bloquée, ce qui est précisément la confusion à ne plus créer.
  const t = runOuverture([{ id: 'ev-1' }], 'ev-inconnu');
  check('un événement introuvable est SIGNALÉ, pas ignoré',
    t.length === 1 && t[0] === 'panne', `trace = ${JSON.stringify(t)}`);
}

// ── 3 · Le suivi vit dans la fenêtre, et seulement sur un événement existant ──
check('les tâches et les notes sont dans la fenêtre',
  /id="m-suivi"/.test(src) && src.indexOf('id="m-suivi"') < src.indexOf('class="modal-actions"'),
  'le bloc de suivi est sorti de la fenêtre');
// ⚠️ Une zone de saisie qui perd ce qu'on y met est pire qu'une zone absente : avant
// l'enregistrement, une tâche n'a aucun identifiant auquel se rattacher.
check('le suivi est masqué à la création',
  /\$\('m-suivi'\)\.style\.display = isEdit \? 'block' : 'none'/.test(src));

// ── 4 · L'empilement restant reste sain ──────────────────────────────────────
function zIndexOf(selector) {
  const hit = src.match(new RegExp(`\\n\\.${selector} \\{[^}]*z-index:\\s*(\\d+)`));
  return hit ? Number(hit[1]) : null;
}
const zModal = zIndexOf('modal'), zOverlay = zIndexOf('overlay');
check('les z-index sont lisibles', zModal !== null && zOverlay !== null,
  `modal=${zModal} overlay=${zOverlay}`);
check('la fenêtre passe au-dessus du voile', zModal > zOverlay,
  `modal=${zModal} vs overlay=${zOverlay}`);

// ── 5 · Les actions restent atteignables ─────────────────────────────────────
// ⚠️ La fenêtre porte désormais le formulaire ET le suivi, dans `max-height: 90vh; overflow: auto`.
// Sans `sticky`, « Enregistrer » descend hors du champ de vision dès que les tâches s'allongent.
check('le bloc d’actions est collé au bas de la fenêtre',
  /class="modal-actions"[^>]*position:sticky/.test(src));

console.log(failures ? `\n${failures} échec(s) sur ${ran}` : `\n${ran} assertions vertes`);
process.exit(failures ? 1 : 0);
