"""
LE TABLEAU DE BORD, EXÉCUTÉ.

⚠️ `perDayEl is not defined` EST PARTI EN PRODUCTION. La variable avait été supprimée avec la
carte qui la portait, et une ligne l'utilisait encore. `node --check` l'accepte : une variable
non déclarée n'est une erreur qu'à L'EXÉCUTION, et seulement quand la branche est prise. Il
fallait une période d'un seul jour pour la traverser.

⚠️ ET LE RENDU S'ARRÊTE À LA PREMIÈRE EXCEPTION. Tout ce qui suit dans la fonction n'est jamais
écrit : la page reste vide, avec des « — » qui ressemblent à une absence de données. On cherche
alors le bogue dans l'API, qui a parfaitement répondu.

⚠️ LES CONTRÔLES DE COHÉRENCE NE VOIENT PAS ÇA. Ils lient les identifiants du gabarit à ceux du
script — pas les variables du script entre elles. Seule l'exécution le fait.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()


def _gabarit():
    return open(os.path.join(RACINE, "templates", "index.html"), encoding="utf-8").read()


def _ids():
    """Tous les ancrages du gabarit — le faux DOM ne connaît qu'eux, comme le navigateur."""
    return sorted(set(re.findall(r'id="([^"]+)"', _gabarit())))


# ⚠️ UNE CHARGE UTILE RÉALISTE, PAS UN OBJET VIDE. Un `{}` prend toutes les branches de repli et
# ne traverse aucune des lignes qui plantent. Ce jeu-ci ressemble à cinq services ordinaires.
def payload(**kw):
    base = {
        "preset": "services5", "period_label": "5 derniers services",
        "from_date": "2026-09-18", "to_date": "2026-09-24",
        "n_days": 7, "is_single_day": False, "is_today": False, "has_items": True,
        "date": "2026-09-24", "updated_at": "14:07",
        "periode": {"jours_ouverts": 5, "jours_calendaires": 7, "en_cours": False},
        "comp_label": "vs les 5 services précédents",
        "comp_is_sofar": False, "seuil": 30,
        "today": {"ca": 2074.0, "ca_ht": 1835.0, "ca_gross": 2074.0, "nb": 216,
                  "ticket": 9.59, "popup_chef": 0},
        "yesterday": {"ca": 1899.0, "ca_ht": 1680.0, "nb": 220, "ticket": 8.63},
        "median": 8.40,
        "daily": [{"date": "2026-09-18", "ca_ttc": 380, "ca_ht": 336, "nb": 40},
                  {"date": "2026-09-19", "ca_ttc": 420, "ca_ht": 372, "nb": 44},
                  {"date": "2026-09-20", "ca_ttc": 455, "ca_ht": 403, "nb": 47},
                  {"date": "2026-09-21", "ca_ttc": 399, "ca_ht": 353, "nb": 42},
                  {"date": "2026-09-24", "ca_ttc": 420, "ca_ht": 371, "nb": 43}],
        "daily_comp": [{"date": "2026-09-11", "ca_ttc": 350, "ca_ht": 310, "nb": 38},
                       {"date": "2026-09-12", "ca_ttc": 400, "ca_ht": 354, "nb": 42}],
        "payments": {"labels": ["Carte"], "values": [2074.0]},
        "tva": [{"rate": 13, "base": 1835.0, "tva": 239.0, "total": 2074.0}],
        "week": [{"date": "2026-09-18", "ca": 380, "nb": 40},
                 {"date": "2026-09-24", "ca": 420, "nb": 43}],
        "today_lastweek": None,
        "wow": None,
        "weekdays": [{"day": 5, "avg_ca": 455.0, "n_days": 4},
                     {"day": 3, "avg_ca": 420.0, "n_days": 5},
                     {"day": 0, "avg_ca": 399.0, "n_days": 5}],
        "mix": [], "recent": [], "products": [], "rush": [], "hourly": None,
        "basket": {"tx_per_open_day": 43, "tx_basis_days": 5, "tx_basis_reason": None},
        "upsell": {"rate": 31.2},
        "insights": {"basket": {"items_per_ticket": 1.42, "attach_pct": 31.2},
                     "month": None, "heatmap": None, "seat": None},
        "economics": {
            "ca_ttc": 2074.0, "ca_ht": 1835.0, "cogs_ht": 446.0,
            "marge_brute_ht": 1389.0, "marge_brute_ht_pct": 75.7,
            "marge_is_estimated": False, "cogs_coverage_pct": 96,
            "open_days": 5, "cout_fixe_periode": 317.0, "cout_perso_periode": 660.0,
            "cout_total_periode": 977.0, "cout_jour": 195.4,
            "ebitda_ht": 412.0, "seuil_ca_ttc": 1430.0, "seuil_ca_ttc_jour": 286.0,
            "manque_seuil": 0, "pct_seuil": 145, "seuil_margin_pct": 75.7,
            "excludes_today": False, "today_toggleable": False,
            "periode": {"jours_ouverts": 5, "jours_calendaires": 7, "en_cours": False},
        },
    }
    base.update(kw)
    return base


SOCLE = """
  const ids = __IDS__;
  const champs = {};
  const erreurs = [];
  function faux(id) {
    return {
      id, textContent: '', innerHTML: '', value: '', checked: false,
      className: '', dataset: {}, attrs: {}, style: {},
      classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
      setAttribute(k, v){ this.attrs[k] = v; },
      getAttribute(k){ return this.attrs[k]; },
      removeAttribute(k){ delete this.attrs[k]; },
      closest(){ return this; },
      appendChild(){}, insertAdjacentHTML(pos, h){ this.innerHTML += h; },
      querySelectorAll(){ return []; },
      getContext(){ return ctx2d(); },
      getBoundingClientRect(){ return { width: 0, height: 0 }; },
      addEventListener(){},
    };
  }
  ids.forEach(id => { champs[id] = faux(id); });
  function ctx2d() {
    return { createLinearGradient: () => ({ addColorStop(){} }),
             canvas: { width: 600, height: 200 } };
  }
  class Chart {
    constructor(ctx, cfg) { this.cfg = cfg; }
    destroy() {}
    static getChart() { return null; }
  }
  const document = {
    documentElement: {}, body: { appendChild(){} },
    /* ⚠️ `getElementById` REND `null` SUR UN ID INCONNU, comme le navigateur : un ancrage
       inventé côté script lève ici au lieu de ne rien afficher. */
    getElementById: (id) => (Object.prototype.hasOwnProperty.call(champs, id) ? champs[id] : null),
    createElement: () => faux('tmp'),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener(){},
  };
  const window = { matchMedia: null, uiLoadStart: null, uiLoadEnd: null,
                   innerWidth: 1200, innerHeight: 900 };
  const getComputedStyle = () => ({ getPropertyValue: () => '#123456' });
  const localStorage = { getItem: () => null, setItem(){} };
  const fetch = () => new Promise(() => {});
"""


def _executer(charges):
    """
    Monte le script sur un faux DOM et lui passe chaque charge utile.

    ⚠️ ON ÉCRIT UN FICHIER, ON N'ENCAPSULE PAS DANS `new Function`. La première version
    injectait les 1 200 lignes dans un littéral gabarit : il fallait échapper les accents
    graves et les `${`, et la moindre erreur produisait un programme que node n'arrivait plus à
    terminer. Un harnais qui se bloque ne dit rien de la page qu'il devait éprouver.

    ⚠️ ET L'APPEL D'INITIALISATION EST RETIRÉ. `loadData()` en fin de fichier partirait chercher
    l'API : ici on appelle le rendu nous-mêmes, avec une charge utile choisie.
    """
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    # ⚠️ L'AMORÇAGE EST RETIRÉ, `setInterval` COMPRIS. `loadData()` partirait chercher l'API,
    # et le rafraîchissement toutes les cinq minutes GARDE LE PROCESSUS EN VIE : node ne rendait
    # jamais la main, et le harnais se bloquait au lieu de dire ce qu'il avait trouvé.
    src = _js()
    src = re.sub(r"^loadData\(\);$", "", src, flags=re.M)
    src = re.sub(r"^setInterval\(.*$", "", src, flags=re.M)
    prog = (SOCLE.replace("__IDS__", json.dumps(_ids()))
            + src + """
  const charges = __CHARGES__;
  for (const d of charges) {
    try { render(d); } catch (e) { erreurs.push('render: ' + e.message); }
    try { renderInsights(d); } catch (e) { erreurs.push('insights: ' + e.message); }
  }
  console.log(JSON.stringify({
    erreurs,
    ca: champs['db-ca'].textContent,
    res: champs['db-res'].textContent,
    seuil: champs['db-seuil'].textContent,
    tickets: champs['kpi-nb'].textContent,
    tva: champs['db-tva'].textContent,
    jour: champs['db-wd-v'].textContent,
    couv: champs['db-couv'].textContent,
  }));
""".replace("__CHARGES__", json.dumps(charges)))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(prog)
        chemin = f.name
    try:
        r = subprocess.run(["node", chemin], capture_output=True, text=True, timeout=25)
    finally:
        os.unlink(chemin)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


def test_le_rendu_passe_sur_une_periode_multi_jours():
    """C'est le cas courant : cinq services, une comparaison, une économie complète."""
    r = _executer([payload()])
    assert r["erreurs"] == [], r["erreurs"]


def test_le_rendu_passe_sur_un_jour_unique():
    """
    ⚠️ C'EST LA BRANCHE QUI A PLANTÉ EN PRODUCTION. `perDayEl is not defined` ne se déclenchait
    que sur une période d'un seul jour — la branche `else` d'un `if (!is_single_day …)`.
    """
    r = _executer([payload(is_single_day=True, is_today=True, preset="today",
                           period_label="Aujourd'hui",
                           daily=[{"date": "2026-09-24", "ca_ttc": 420, "ca_ht": 371, "nb": 43}])])
    assert r["erreurs"] == [], r["erreurs"]


def test_le_rendu_passe_sans_economie():
    """Sans prix d'achat, la moitié des cartes n'a rien à écrire — et rien ne doit lever."""
    p = payload()
    p["economics"] = {"ca_ttc": 2074.0, "ca_ht": 1835.0, "open_days": 5,
                      "ebitda_ht": None, "cogs_coverage_pct": None,
                      "excludes_today": False, "today_toggleable": False}
    r = _executer([p])
    assert r["erreurs"] == [], r["erreurs"]
    assert r["res"] == "—" and r["couv"] == "—"


def test_le_rendu_passe_sur_une_charge_utile_creuse():
    """
    ⚠️ UN ENDPOINT QUI RÉPOND À MOITIÉ NE DOIT PAS VIDER LA PAGE. Le rendu s'arrête à la
    première exception : tout ce qui suit n'est jamais écrit.
    """
    p = payload(daily=[], daily_comp=[], weekdays=None, week=[], insights={},
                basket={}, median=None)
    r = _executer([p])
    assert r["erreurs"] == [], r["erreurs"]


def test_les_chiffres_sont_bien_ecrits():
    """
    ⚠️ « AUCUNE ERREUR » N'EST PAS « LA PAGE EST REMPLIE ». Un rendu qui ne lève pas et n'écrit
    rien laisse exactement le même écran qu'un rendu qui plante — des tirets partout.
    """
    r = _executer([payload()])
    assert r["ca"] and r["ca"] != "—", "l'encaissé n'est pas écrit"
    assert "412" in r["res"], r["res"]
    assert "1" in r["seuil"] and r["seuil"] != "—", r["seuil"]
    assert str(r["tickets"]) == "216", r["tickets"]
    assert r["tva"] != "—", "la TVA n'est pas écrite"
    assert r["jour"] == "samedi", r["jour"]
    assert r["couv"] == "96 %", r["couv"]
