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


def test_aucune_fonction_du_script_nest_orpheline():
    """
    ⚠️ DU CODE MORT PASSE TOUS LES TESTS. Le tiroir de transaction et son infobulle — deux cents
    lignes — ont survécu à la disparition de la liste qui les ouvrait : plus rien ne les
    appelait, mais leurs ancrages existaient toujours dans le gabarit, donc le contrôle de
    cohérence restait vert. Il vérifiait qu'ils s'accordaient entre eux, pas qu'un chemin y mène.

    ⚠️ ET CE N'EST PAS UNE QUESTION DE PROPRETÉ. Une fonction qu'on croit vivante se maintient,
    se relit, se corrige — et le jour où quelqu'un s'étonne qu'un clic ne fasse rien, il cherche
    dans du code qui n'est plus branché depuis des mois.
    """
    js, html = _js(), _gabarit()
    # ⚠️ LE PREMIER NIVEAU SEULEMENT, ET C'EST VOULU. Une fonction imbriquée est portée par
    # celle qui la contient : si la contenante est appelée, elle l'est aussi, et si elle ne
    # l'est pas, c'est la contenante qui est signalée. Les inclure ferait crier sur des
    # fermetures locales parfaitement branchées — et un test qui crie sur du correct finit
    # désactivé, emportant avec lui le cas qu'il devait attraper (le tiroir, deux cents lignes).
    definies = set(re.findall(r"^(?:async )?function (\w+)\s*\(", js, re.M))
    appelees = set(re.findall(r"\b(\w+)\s*\(", html)) | set(
        re.findall(r"\b(\w+)\s*\(", re.sub(r"^(?:async )?function \w+\s*\(", "", js, flags=re.M)))
    # Une fonction n'est pas appelée par sa propre déclaration.
    orphelines = sorted(
        f for f in definies
        if len(re.findall(rf"\b{f}\s*\(", js)) <= 1 and f not in appelees
    )
    assert not orphelines, f"définies mais jamais appelées : {orphelines}"


# ── Ce qui est replié, et ce qui ne l'est pas ────────────────────────────────────────────────
#
# ⚠️ TOUT CE QUI SE CONSULTE N'A PAS À ÊTRE DÉROULÉ. Le détail par produit, la répartition
# horaire, les tendances : on les ouvre pour répondre à une question précise, une fois par
# semaine — pas chaque matin. Déroulés, ils poussaient la réponse du haut hors de l'écran.

def test_la_reponse_et_la_chaine_ne_sont_jamais_repliees():
    """
    ⚠️ C'EST LA LIGNE DE PARTAGE. Ce qu'on vient lire chaque matin reste sous les yeux ; ce
    qu'on va chercher se replie. Replier la réponse reviendrait à demander un clic pour savoir
    si la journée paie ses coûts.
    """
    html = _gabarit()
    avant = html[:html.index('<details class="repli">')]
    for ancre in ('id="db-value"', 'class="chaine"', 'id="eco-seuil"', 'id="periode-dit"'):
        assert ancre in avant, f"{ancre} est passé derrière un repli"


def test_les_blocs_de_consultation_sont_replies():
    html = _gabarit()
    for titre in ("Quand l'argent entre", "Ce qui s'est vendu", "Le mois en cours", "Tendances"):
        i = html.index(titre)
        # Le titre doit vivre dans un <summary>, donc après le <details> le plus proche.
        assert html.rindex("<details", 0, i) > html.rindex("</details>", 0, i) \
            if "</details>" in html[:i] else True, titre
        assert "<summary>" in html[html.rindex("<details", 0, i):i], titre


def test_aucun_bloc_nest_ouvert_par_defaut():
    """⚠️ UN `open` OUBLIÉ ANNULE LE REPLI SANS QUE RIEN NE LE SIGNALE."""
    html = _gabarit()
    assert not re.search(r'<details class="repli"[^>]*\sopen', html)


def test_chaque_repli_dit_ce_quon_y_trouve():
    """
    ⚠️ SANS RÉSUMÉ, ON OUVRE LES CINQ BLOCS POUR RETROUVER CELUI QU'ON CHERCHE — ce qui est pire
    que tout laisser déroulé.
    """
    html = _gabarit()
    for m in re.finditer(r"<summary>(.*?)</summary>", html, re.S):
        assert 'class="repli-quoi"' in m.group(1), m.group(1)[:60]


def test_les_graphiques_sont_redimensionnes_a_louverture():
    """
    ⚠️ CHART.JS MESURE SON CONTENEUR AU MOMENT DU TRACÉ. Dans un `<details>` fermé il vaut zéro :
    le graphique est dessiné écrasé et le reste à l'ouverture. Rien ne lève, rien n'est rouge —
    on voit un trait au lieu d'une courbe, et on cherche le bogue dans les données.
    """
    js = _js()
    assert "Chart.getChart" in js, "on tient une liste maison au lieu d'interroger Chart.js"
    i = js.index("document.addEventListener('toggle'")
    bloc = js[i:i + 300]
    assert "reveillerGraphiques" in bloc
    # ⚠️ `toggle` NE REMONTE PAS : sans la phase de capture, l'écouteur posé sur le document
    # ne recevrait jamais rien, et la garde serait silencieusement inopérante.
    assert "true" in bloc, "l'écouteur n'est pas à la capture"


def test_un_repli_contient_bien_un_canvas_a_reveiller():
    """Si plus aucun graphique ne vit dans un repli, la garde ci-dessus n'a plus d'objet — et
    c'est le moment de la retirer plutôt que de la laisser rassurer pour rien."""
    html = _gabarit()
    i = html.index('<details class="repli">')
    assert "<canvas" in html[i:], "plus aucun graphique replié : la garde de redimensionnement est morte"


def test_ouvrir_un_bloc_redimensionne_vraiment_ses_graphiques():
    """
    ⚠️ VÉRIFIER LA FORME DU CODE NE VÉRIFIE PAS SON EFFET. Deux mutants ont survécu à la
    première batterie — l'un vidait `reveillerGraphiques`, l'autre coupait son appel — parce que
    mes contrôles cherchaient `Chart.getChart` dans le source au lieu d'exécuter la fonction.
    Un test qui lit du code atteste qu'il est écrit, jamais qu'il marche.
    """
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    js = _js()
    i = js.index("function reveillerGraphiques(")
    fonction = js[i:js.index("\n}", i) + 2]
    # ⚠️ L'ÉCOUTEUR VIT DANS UN `if (typeof document !== 'undefined') { … }` : le découper à la
    # première accolade en colonne 0 rendait un fragment déséquilibré, et node refusait de le
    # lire. On prend le bloc entier, depuis son `if`.
    i = js.index("if (typeof document !== 'undefined') {\n  document.addEventListener('toggle'")
    ecouteur = js[i:js.index("\n}", js.index("}, true);", i)) + 2]
    prog = """
      const redimensionnes = [];
      function faireCanvas(nom){ return { nom: nom }; }
      const dedans = [faireCanvas('haut'), faireCanvas('bas')];
      const Chart = { getChart: function (c) {
        return { resize: function(){ redimensionnes.push(c.nom); } };
      } };
      let ecouteurPose = null;
      const document = { addEventListener: function (type, fn, capture) {
        if (type === 'toggle') ecouteurPose = { fn: fn, capture: capture };
      } };
    """ + fonction + "\n" + ecouteur + """
      const bloc = { tagName: 'DETAILS', open: true,
                     querySelectorAll: function(){ return dedans; } };
      ecouteurPose.fn({ target: bloc });
      const ferme = { tagName: 'DETAILS', open: false,
                      querySelectorAll: function(){ return [faireCanvas('jamais')]; } };
      ecouteurPose.fn({ target: ferme });
      console.log(JSON.stringify({ redimensionnes: redimensionnes,
                                   capture: ecouteurPose.capture === true }));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["redimensionnes"] == ["haut", "bas"], out["redimensionnes"]
    # ⚠️ ET RIEN N'EST TOUCHÉ SUR UN BLOC QUI SE FERME : redimensionner un canvas qu'on vient de
    # masquer le remettrait à zéro, et c'est le défaut qu'on corrige, appliqué à l'envers.
    assert "jamais" not in out["redimensionnes"]
    assert out["capture"] is True, "`toggle` ne remonte pas — sans capture, rien n'arrive"
