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
