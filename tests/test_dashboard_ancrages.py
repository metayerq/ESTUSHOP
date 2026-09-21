"""
LE TABLEAU DE BORD ÉCRIT-IL LÀ OÙ QUELQUE CHOSE EXISTE ?

⚠️ `document.getElementById('…').textContent = x` SUR UN IDENTIFIANT ABSENT LÈVE, et le rendu
s'arrête là. Tout ce qui suit dans la fonction n'est jamais écrit : la page reste à moitié
remplie, avec des « — » qui ressemblent à des absences de données. On cherche alors le bogue
dans l'API, qui a parfaitement répondu.

⚠️ C'EST LE RISQUE DE TOUT REMANIEMENT DE CETTE PAGE. `static/dashboard.js` fait 1 575 lignes et
écrit dans une centaine d'ancrages ; en déplacer un seul sans toucher l'autre fichier casse
l'écran en silence. Ce test lie les deux.
"""

import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()


def _gabarit():
    return open(os.path.join(RACINE, "templates", "index.html"), encoding="utf-8").read()


def test_chaque_ancrage_ecrit_par_le_script_existe_dans_la_page():
    js, html = _js(), _gabarit()
    # Les identifiants créés dynamiquement par le script lui-même sont légitimes : on ne
    # retient que ceux qu'il va CHERCHER.
    cherches = set(re.findall(r"getElementById\(\s*'([^']+)'\s*\)", js))
    cherches |= set(re.findall(r'getElementById\(\s*"([^"]+)"\s*\)', js))
    poses = set(re.findall(r'id="([^"]+)"', html))
    poses |= set(re.findall(r"id='([^']+)'", html))
    # Le script en pose lui-même, par innerHTML.
    poses |= set(re.findall(r"id=[\\\"']([a-zA-Z][\w-]*)", js))
    manquants = sorted(i for i in cherches if i not in poses)
    assert not manquants, f"écrits par dashboard.js, absents de index.html : {manquants}"


def test_chaque_fonction_appelee_par_la_page_existe_dans_le_script():
    """
    ⚠️ UN `onclick` QUI POINTE VERS RIEN NE FAIT RIEN, ET NE DIT RIEN. Le bouton s'affiche,
    s'enfonce sous le doigt, et la page ne bouge pas — le pire des états, puisqu'on réessaie.
    """
    js, html = _js(), _gabarit()
    autres = ""
    for f in ("ui.js",):
        autres += open(os.path.join(RACINE, "static", f), encoding="utf-8").read()
    appelees = set(re.findall(r'on(?:click|change|input)="(\w+)\(', html))
    definies = set(re.findall(r"function\s+(\w+)\s*\(", js + autres))
    definies |= set(re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", js + autres))
    # ⚠️ `window.cycleTheme = function ()` EST UNE DÉFINITION AUSSI. `ui.js` expose ainsi ce que
    # tous les gabarits appellent ; ne chercher que `function nom(` l'aurait déclarée manquante
    # et fait échouer un test sur du code sain.
    definies |= set(re.findall(r"window\.(\w+)\s*=\s*(?:async\s*)?function", js + autres))
    manquants = sorted(appelees - definies)
    assert not manquants, f"appelées par index.html, absentes du script : {manquants}"


# ── Les champs lus par l'écran existent-ils dans la charge utile ? ───────────────────────────

def test_les_champs_economiques_lus_par_lecran_existent_dans_la_reponse():
    """
    ⚠️ UN CHAMP MAL NOMMÉ NE LÈVE PAS, IL VAUT `undefined`. `eco.ebitda` au lieu de
    `eco.ebitda_ht` fait silencieusement basculer l'écran dans sa branche « pas calculable » :
    la page affiche « le résultat n'est pas calculable » avec un lien vers COGS, alors que le
    serveur a parfaitement répondu. On va alors saisir des prix d'achat qui existent déjà.

    ⚠️ ET C'EST EXACTEMENT L'ERREUR QUE J'AI ÉCRITE en construisant le bandeau-réponse. Elle
    n'a été vue qu'en relisant `vendus.py` — aucun test ne liait les deux fichiers.
    """
    js = _js()
    python = open(os.path.join(RACINE, "vendus.py"), encoding="utf-8").read()
    i = python.index('"ca_ttc":          round(ca_ttc, 2),')
    bloc = python[i:python.index("}", python.index('"seuil_margin_pct"', i))]
    connus = set(re.findall(r'"([a-z_0-9]+)":', bloc))
    # Ce que l'écran lit sur `economics`, quel que soit le nom de la variable intermédiaire.
    lus = set()
    # ⚠️ PAS `e` : c'est le nom des événements et des exceptions (`e.target`, `e.message`).
    # Les inclure faisait accuser du code sain — et un test qui crie sur du correct finit
    # désactivé, emportant avec lui le cas qu'il devait attraper.
    for var in ("eco", "ecoTop"):
        lus |= set(re.findall(rf"\b{var}\.([a-z_0-9]+)\b", js))
    # Les champs ajoutés côté route, hors du bloc `vendus.py`.
    ailleurs = set(re.findall(r'"economics"\]\["([a-z_0-9]+)"\]',
                              open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()))
    inconnus = sorted(lus - connus - ailleurs)
    assert not inconnus, f"lus par dashboard.js, absents de la charge utile : {inconnus}"


# ── La réponse du haut, exécutée ─────────────────────────────────────────────────────────────
#
# ⚠️ UNE FONCTION QUI N'EST JAMAIS APPELÉE EST INDISCERNABLE D'UNE FONCTION JUSTE. Un mutant qui
# retirait `renderReponse(d)` de la boucle de rendu a survécu à la première batterie : tout
# était testé du bandeau-réponse sauf le fait qu'on le remplisse.

import json
import shutil
import subprocess

import pytest

SOCLE = """
const champs = {};
const document = { getElementById: function(id){
  return champs[id] || (champs[id] = {
    textContent: '', innerHTML: '', attrs: {},
    style: { display: id === 'db-note' ? 'none' : '' },
    // ⚠️ LE BANCAL IMITE LA PAGE, SÉLECTEUR COMPRIS. `etat()` remonte au conteneur par
    // `closest`, et c'est lui qui porte l'attribut. Un `closest` qui répond oui à tout a laissé
    // survivre un mutant : il suffisait de rétrécir la liste des conteneurs à `.kpi-cell` pour
    // que l'état du bandeau soit jeté en silence, sans qu'aucun test ne rougisse. Ici, comme
    // dans la page, `db-*` vit dans une `.tx-answer` et nulle part ailleurs.
    closest: function(sel){ return sel.indexOf('.tx-answer') >= 0 ? this : null; },
    setAttribute: function(k, v){ this.attrs[k] = v; },
    removeAttribute: function(k){ delete this.attrs[k]; },
  });
} };
const fmt = function(v){ return Number(v).toFixed(2) + ' EUR'; };
"""


def _rendre(economics):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    js = _js()
    bloc = ""
    for nom in ("etat", "renderReponse"):
        i = js.index(f"function {nom}(")
        bloc += js[i:js.index("\n}", i) + 2] + "\n"
    prog = SOCLE + bloc + f"""
        renderReponse({json.dumps({"economics": economics})});
        console.log(JSON.stringify({{
          lead: champs['db-lead'].textContent,
          value: champs['db-value'].textContent,
          etat: champs['db-value'].attrs['data-etat'] || null,
          delta: champs['db-delta'].innerHTML,
          sub: champs['db-sub'].innerHTML,
          note: champs['db-note'].innerHTML,
          noteVisible: champs['db-note'].style.display !== 'none',
        }}));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


ECO = {"ebitda_ht": 420.0, "ca_ttc": 3100.0, "seuil_ca_ttc": 2600.0, "open_days": 5,
       "manque_seuil": 0, "marge_is_estimated": False, "cogs_coverage_pct": 100}


def test_la_reponse_est_bien_remplie():
    r = _rendre(ECO)
    assert "couverts" in r["lead"] and "ne sont pas" not in r["lead"]
    assert "420.00" in r["value"]
    assert r["etat"] == "ok"
    assert "3100.00" in r["sub"] and "2600.00" in r["sub"] and "5" in r["sub"]


def test_la_reponse_est_appelee_a_chaque_rendu():
    """⚠️ TOUT ÉTAIT TESTÉ DU BANDEAU SAUF LE FAIT QU'ON LE REMPLISSE."""
    js = _js()
    i = js.index("function renderInsights(")
    assert "renderReponse(d)" in js[i:i + 200], "la réponse n'est pas rendue avec le reste"
    assert "renderInsights(d)" in js, "renderInsights n'est appelée nulle part"


def test_un_resultat_negatif_dit_ce_quil_manque_en_VENTES():
    """
    ⚠️ « IL MANQUE 180 € » DE RÉSULTAT N'INDIQUE AUCUN GESTE. « Il manque 740 € de ventes » se
    compare à une journée. Les deux diffèrent du taux de marge, et c'est le second qu'on vise.
    """
    r = _rendre({**ECO, "ebitda_ht": -180.0, "manque_seuil": 740.0})
    assert "ne sont pas couverts" in r["lead"]
    assert r["etat"] == "alerte"
    assert "740.00" in r["delta"] and "ventes" in r["delta"]


def test_sans_prix_dachat_la_reponse_nomme_le_geste():
    """
    ⚠️ « PAS DE DONNÉE » N'EST PAS « À L'ÉQUILIBRE ». Afficher 0 € rassurerait à tort ; dire
    seulement « non calculable » laisse devant un écran mort sans indiquer quoi faire.
    """
    r = _rendre({"ebitda_ht": None})
    assert r["value"] == "—"
    assert r["etat"] is None, "une case vide porte un état"
    assert r["noteVisible"] and "/cogs" in r["note"]


def test_une_marge_extrapolee_est_annoncee_a_cote_du_chiffre():
    """Sous la couverture COGS complète, le résultat ET le point mort héritent de
    l'extrapolation : le taire ferait lire une mesure là où il y a une projection."""
    r = _rendre({**ECO, "marge_is_estimated": True, "cogs_coverage_pct": 62})
    assert r["noteVisible"] and "62" in r["note"] and "point mort" in r["note"]


def test_une_marge_mesuree_ne_declenche_aucune_reserve():
    """Un avertissement permanent est un avertissement qu'on cesse de lire."""
    assert _rendre(ECO)["noteVisible"] is False
