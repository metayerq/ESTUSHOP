// Helpers UI partagés (barre de chargement + skeletons).
// Chargé avant le script de chaque page ; API globale volontairement minuscule.
(function () {
  var bar = null, pending = 0;

  function ensureBar() {
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'loadbar';
      document.body.appendChild(bar);
    }
    return bar;
  }

  // Compteur : plusieurs fetchs concurrents = une seule barre.
  window.uiLoadStart = function () {
    pending++;
    ensureBar().classList.add('on');
  };
  window.uiLoadEnd = function () {
    pending = Math.max(0, pending - 1);
    if (!pending && bar) bar.classList.remove('on');
  };

  // Remplace les cellules "Loading…" initiales par des skeletons animés.
  function skeletonize() {
    document.querySelectorAll('td.empty, .empty').forEach(function (el) {
      if (/^(Loading|Chargement)/.test(el.textContent.trim())) {
        el.innerHTML =
          '<span class="skel" style="width:62%"></span>' +
          '<span class="skel" style="width:44%"></span>' +
          '<span class="skel" style="width:55%"></span>';
      }
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', skeletonize);
  } else {
    skeletonize();
  }
})();

/* ── Thème ─────────────────────────────────────────────────────────────────────
   Flux apporte un mode sombre là où il n'y en avait aucun. Trois états, dans cet
   ordre : `system` (la préférence de l'OS, valeur par défaut), `light`, `dark`.

   ⚠️ APPLIQUÉ TOUT DE SUITE, PAS AU DOMContentLoaded. Attendre laisserait la page
   peindre en clair puis basculer — un flash blanc à chaque navigation, le matin
   comme le soir. ui.js est chargé avant le script de page, donc <html> existe déjà.

   Vit ici et non dans dashboard.js : les neuf écrans partagent style.css, le choix
   doit valoir partout. */
(function () {
  var KEY = 'estu-theme', ORDER = ['system', 'light', 'dark'];

  function read() {
    try { var v = localStorage.getItem(KEY); return ORDER.indexOf(v) >= 0 ? v : 'system'; }
    catch (e) { return 'system'; }   // stockage refusé (navigation privée) → système
  }
  function apply(mode) {
    var el = document.documentElement;
    if (mode === 'system') el.removeAttribute('data-theme');
    else el.setAttribute('data-theme', mode);
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.textContent = mode === 'light' ? '☀' : mode === 'dark' ? '☾' : '◐';
      btn.title = 'Thème : ' + (mode === 'system' ? 'système' : mode === 'light' ? 'clair' : 'sombre');
    }
  }
  window.cycleTheme = function () {
    var next = ORDER[(ORDER.indexOf(read()) + 1) % ORDER.length];
    try { localStorage.setItem(KEY, next); } catch (e) {}
    apply(next);
  };
  apply(read());
  // Le bouton n'existe pas encore au moment du premier apply : on repasse dessus
  // une fois le DOM prêt, pour que son icône reflète l'état réel.
  document.addEventListener('DOMContentLoaded', function () { apply(read()); });
})();
