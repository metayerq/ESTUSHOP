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
    for nom in ("renderReponse",):
        i = js.index(f"function {nom}(")
        bloc += js[i:js.index("\n}", i) + 2] + "\n"
    prog = SOCLE + bloc + f"""
        renderReponse({json.dumps({"economics": economics})});
        console.log(JSON.stringify({{
          lead: champs['db-res-l'].textContent,
          value: champs['db-res'].textContent,
          couleur: champs['db-res'].style.color || null,
          delta: champs['db-res-sub'].innerHTML,
          seuil: champs['db-seuil'].textContent,
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
    """
    ⚠️ LE LIBELLÉ PORTE LE NOMBRE DE SERVICES, PAS LE VERDICT. Celui-ci est passé dans la
    pastille : une phrase qui répète la couleur d'à côté occupe une ligne pour rien.
    """
    r = _rendre(ECO)
    assert "5 services" in r["lead"]
    assert "420.00" in r["value"]
    assert "couverts" in r["delta"]
    assert "2600.00" in r["seuil"], "le point mort est dit en euros, pas en pourcentage"


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
    assert "740.00" in r["delta"] and "ventes" in r["delta"]
    assert "db-badge down" in r["delta"], "un manque n'est pas peint comme une réussite"


def test_sans_prix_dachat_la_reponse_nomme_le_geste():
    """
    ⚠️ « PAS DE DONNÉE » N'EST PAS « À L'ÉQUILIBRE ». Afficher 0 € rassurerait à tort ; dire
    seulement « non calculable » laisse devant un écran mort sans indiquer quoi faire.
    """
    r = _rendre({"ebitda_ht": None})
    assert r["value"] == "—"
    assert r["delta"] == "", "une case vide porte une pastille"
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


# ── L'ordre de lecture ───────────────────────────────────────────────────────────────────────
#
# ⚠️ LES CINQ BLOCS REPLIÉS ONT ÉTÉ DÉPLIÉS, À LA DEMANDE. Ce que le repli protégeait — la
# réponse du haut visible sans défiler — tient désormais à l'ORDRE seul : ce qu'on vient lire
# chaque matin d'abord, ce qu'on va chercher ensuite. Un test sur des `<details>` disparus
# aurait continué de passer au vert en ne vérifiant rien.

def test_la_reponse_vient_avant_tout_le_reste():
    """
    ⚠️ C'EST LA LIGNE DE PARTAGE, ET ELLE SURVIT AU DÉPLIAGE. La question, le résultat, la
    chaîne et le point mort se lisent sans défiler ; le détail par produit, les tendances et le
    mois en cours viennent après. Les intervertir remettrait un tableau de quarante lignes
    devant le chiffre qu'on ouvre la page pour voir.
    """
    html = _gabarit()
    # ⚠️ LA CHAÎNE A LAISSÉ PLACE À LA COURBE. Les ancrages changent ; la règle ne bouge pas —
    # ce qu'on vient lire chaque matin d'abord, ce qu'on va chercher ensuite.
    ordre = ['id="db-ca"', 'id="db-res"', 'id="eco-seuil"',
             'id="recent-body"', 'id="products-body"', 'id="month-zone"', 'id="patterns-zone"']
    positions = [html.index(a) for a in ordre]
    assert positions == sorted(positions), \
        "l'ordre de lecture est rompu : " + str(list(zip(ordre, positions)))


def test_la_periode_est_annoncee_avant_le_premier_chiffre():
    """Un total sans sa période est un nombre qui flotte."""
    html = _gabarit()
    assert html.index('id="periode-dit"') < html.index('id="db-ca"')


# ⚠️ LES TESTS DE LA GARDE DE REDIMENSIONNEMENT SONT PARTIS AVEC ELLE. Ils éprouvaient un
# comportement réel — Chart.js dessine dans un canvas de taille nulle quand le bloc est replié,
# et le graphique sort écrasé — mais plus aucun graphique de cette page n'est replié. Les
# garder aurait entretenu la croyance qu'une protection veille, alors qu'elle n'a plus de cible.
# Le code et ses tests sont au commit « Cinq blocs du tableau de bord se replient ».


# ── Cliquer une commande ouvre son détail ────────────────────────────────────────────────────

def test_la_liste_memorise_ses_lignes_pour_le_tiroir():
    """
    ⚠️ SANS `window._txData`, CLIQUER UNE COMMANDE N'OUVRE RIEN. La ligne se surligne au
    survol, le curseur devient une main, et rien ne se passe — le pire des états, puisqu'on
    réessaie. Un mutant qui supprimait cette ligne a survécu à une batterie : tout était testé
    de la liste sauf ce qui la rend cliquable.
    """
    js = _js()
    i = js.index("// ── Transactions récentes")
    bloc = js[i:i + 1200]
    assert "window._txData = d.recent" in bloc, "la liste ne mémorise plus ses lignes"
    assert "openDrawer(" in bloc, "les lignes ne sont plus cliquables"


def test_ouvrir_une_commande_remplit_le_tiroir():
    """⚠️ ET ON L'EXÉCUTE. Vérifier qu'une affectation est écrite n'atteste pas que le tiroir
    sache s'en servir."""
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    js = _js()
    i = js.index("function openDrawer(")
    fonction = js[i:js.index("\n}", i) + 2]
    prog = """
      const champs = {};
      const document = { getElementById: function (id) {
        return champs[id] || (champs[id] = {
          textContent: '', innerHTML: '',
          classList: { classes: [], add: function (c) { this.classes.push(c); } },
        });
      } };
      const window = { _txData: [{
        number: 'FT 2026/418', time: '14:03', client: 'Consommateur final', amount: 12.5,
        items: [{ name: 'Café', qty: 2, total: 3.0 }],
        payments: [{ method: 'Cartão de Crédito', amount: 12.5 }],
      }] };
      const fmt = function (v) { return Number(v).toFixed(2) + ' EUR'; };
    """ + fonction + """
      openDrawer(0);
      console.log(JSON.stringify({
        numero: champs['drawer-number'].textContent,
        items: champs['drawer-items'].innerHTML,
        total: champs['drawer-total'].innerHTML,
        ouvert: champs['drawer'].classList.classes,
      }));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["numero"] == "FT 2026/418"
    assert "Café" in out["items"]
    assert "12.50" in out["total"]
    assert "open" in out["ouvert"], "le tiroir ne s'ouvre pas"


# ── La feuille du tableau de bord ────────────────────────────────────────────────────────────

def test_qui_charge_la_charte_en_porte_la_classe():
    """
    ⚠️ CE CONTRÔLE A EXIGÉ DEUX CHOSES CONTRAIRES, L'UNE APRÈS L'AUTRE, ET LES DEUX ÉTAIENT
    JUSTES EN LEUR TEMPS. D'abord « une seule page charge cette feuille » — vrai tant qu'elle
    DÉCLARAIT des couleurs. Puis « les jetons restent sous `.db` » — vrai tant qu'on croyait le
    scope gratuit.

    ⚠️ IL NE L'ÉTAIT PAS. Modales, tiroirs et voiles se posent PAR-DESSUS la page, donc hors de
    `.page` dans le DOM — et hors de portée d'un jeton scopé. Chacun de leurs `var(--db-*)` se
    résolvait dans le vide : fond transparent, aucune ombre. On voyait la page à travers le
    texte d'une modale, sur toute la plateforme, et rien ne le signalait.

    ⚠️ CE QUI RESTE VRAI : la feuille ne déclare AUCUNE couleur. C'est ça qui autorise à la
    charger partout, et c'est ça qu'il faut garder.
    """
    css = open(os.path.join(RACINE, "static", "dashboard.css"), encoding="utf-8").read()
    assert css.count(":root {") >= 1, "les jetons ne sont plus accessibles hors de .page"
    # ⚠️ ET ELLE NE DÉCLARE PLUS AUCUNE COULEUR. C'est ce qui autorise une deuxième page à la
    # charger : le jour où une valeur littérale y revient, elle redevient une palette parallèle.
    import re
    couleurs = [c for c in re.findall(r"#[0-9a-fA-F]{6}\b", re.sub(r"/\*.*?\*/", " ", css, flags=re.S))]
    assert not couleurs, f"la charte redéclare des couleurs : {couleurs}"

    import glob
    porteuses = []
    for chemin in sorted(glob.glob(os.path.join(RACINE, "templates", "*.html"))):
        html = open(chemin, encoding="utf-8").read()
        if "dashboard.css" not in html:
            continue
        porteuses.append(os.path.basename(chemin))
        assert "/static/dashboard.css?v=" in html, f"{chemin} : feuille chargée sans version"
        assert 'class="page db"' in html, (
            f"{chemin} charge la charte sans porter `db` — son fond et son encre manqueront")
    assert porteuses == [
                         # ⚠️ AJOUTÉE LE 28/09 : l'archive des factures scannées. `/faturas`
                         # envoie déposer une photo ; rien ne permettait de RELIRE ce que le
                         # scan en avait compris — donc une ligne rattachée au mauvais
                         # ingrédient passait jusqu'à la marge sans qu'aucun écran la montre.
                         "arquivo_faturas.html",
                         "cashflow.html", "charges.html", "cogs.html", "expenses.html",
                         "fidelidade.html", "index.html", "inventario.html",
                         # ⚠️ AJOUTÉE LE 27/09 : la page qui répond à « combien je gagne
                         # vraiment ». Le chiffre vivait dans un onglet de /cogs, derrière
                         # deux inventaires clos qui n'avaient jamais eu lieu.
                         "marge.html",
                         "reconciliation.html", "stock.html", "transactions.html"], porteuses


def _courbe(payload):
    """
    Exécute `renderCourbe` sur un faux Chart et rend la configuration produite.

    ⚠️ LIRE LE CODE N'ATTESTE PAS DE CE QU'IL DESSINE. Quatre mutants ont survécu à une
    batterie parce que mes contrôles cherchaient « borderDash » dans le source : il y en a deux,
    en retirer un laissait l'autre, et le test restait vert pendant que la comparaison devenait
    une ligne pleine.
    """
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    js = _js()
    bloc = ""
    for nom in ("jetons", "voile", "renderCourbe"):
        i = js.index(f"function {nom}(")
        bloc += js[i:js.index("\n}", i) + 2] + "\n"
    prog = """
      let config = null;
      class Chart {
        constructor(ctx, cfg) { config = cfg; }
        destroy() {}
      }
      let chartDaily = null;
      const faux = { getContext: () => ({ createLinearGradient: () => ({ addColorStop(){} }) }) };
      const document = {
        getElementById: (id) => (id === 'chart-daily' ? faux : null),
        querySelector: () => null, documentElement: {},
      };
      const getComputedStyle = () => ({ getPropertyValue: () => '#000000' });
      const fmt = (v) => Number(v).toFixed(2);
    """ + bloc + f"""
      renderCourbe({json.dumps(payload)});
      console.log(JSON.stringify({{
        jeux: config.data.datasets.map(j => ({{
          label: j.label, data: j.data, dash: j.borderDash || null, spanGaps: j.spanGaps,
        }})),
        labels: config.data.labels,
      }}));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


JOURS = [{"date": "2026-09-18", "ca_ttc": 380, "nb": 40},
         {"date": "2026-09-19", "ca_ttc": 420, "nb": 44},
         {"date": "2026-09-21", "ca_ttc": 455, "nb": 47}]
COMP = [{"date": "2026-09-11", "ca_ttc": 350, "nb": 38},
        {"date": "2026-09-12", "ca_ttc": 400, "nb": 42},
        {"date": "2026-09-14", "ca_ttc": 410, "nb": 43}]
PAYLOAD = {"daily": JOURS, "daily_comp": COMP,
           "economics": {"seuil_ca_ttc_jour": 287.0}}


def test_la_comparaison_est_tracee_en_pointilles():
    """⚠️ « −9 % » DIT DE COMBIEN ; LA COURBE DIT QUAND l'écart s'est creusé."""
    r = _courbe(PAYLOAD)
    comp = [j for j in r["jeux"] if j["data"] == [350, 400, 410]]
    assert comp, "la série de comparaison n'est pas tracée"
    assert comp[0]["dash"], "la comparaison n'est pas en pointillés"


def test_le_point_mort_est_une_ligne_sur_la_courbe():
    """
    ⚠️ IL MONTRE QUELS SERVICES ONT PAYÉ LEUR JOURNÉE. Un pourcentage de couverture donne le
    total et cache la dispersion : trois jours au-dessus et deux très en dessous se lisent
    comme cinq jours moyens.
    """
    r = _courbe(PAYLOAD)
    seuil = [j for j in r["jeux"] if j["data"] == [287.0, 287.0, 287.0]]
    assert seuil, "le point mort n'est pas tracé"
    assert seuil[0]["dash"], "le point mort n'est pas en tirets"


def test_sans_point_mort_connu_aucune_ligne_nest_inventee():
    r = _courbe({"daily": JOURS, "daily_comp": [], "economics": {}})
    assert len(r["jeux"]) == 1, "une ligne est tracée sans seuil connu"


def test_un_jour_ferme_nest_pas_relie_au_suivant():
    """
    ⚠️ RELIER DEUX JOURS SÉPARÉS PAR UNE FERMETURE DESSINE UNE PENTE QUI N'A PAS EU LIEU. Le
    café ferme mardi et mercredi : la courbe traverserait le creux comme s'il avait été mesuré.
    """
    r = _courbe(PAYLOAD)
    """
    ⚠️ CE CONTRÔLE COMPTAIT LES SÉRIES, ET LE COMPTE A CHANGÉ LE 04/10/2026. Il affirmait que
    la ligne du point mort « est une constante, sans trou » et exigeait donc exactement deux
    porteurs. Depuis le planning, le point mort suit le coût du jour : il a des trous comme les
    autres — les jours fermés — et il doit porter la même garde.

    On n'exempte donc pas la troisième série : on remplace le COMPTE par l'INVARIANT. Toute
    série qui contient un trou doit porter `spanGaps: false`. C'est plus fort qu'un nombre, et
    ça ne se périme pas au prochain jeu de données.
    """
    assert len(r["jeux"]) >= 3, "les trois séries ne sont pas tracées"
    for serie in r["jeux"]:
        assert serie.get("spanGaps") is False, (
            f"« {serie['label']} » relierait les deux bords d'un trou : "
            "une pente qui n'a pas eu lieu")

    # ⚠️ ET SUR UN JEU QUI A VRAIMENT UN TROU. Le jeu ci-dessus exprime la fermeture par une
    # date ABSENTE, pas par un `null` : il ne prouve donc pas que la garde sert. Ici la
    # comparaison est plus courte que la période, ce qui crée un vrai trou en fin de série.
    court = {"daily": JOURS, "daily_comp": COMP[:1],
             "economics": {"seuil_ca_ttc_jour": 287.0,
                           "seuil_ca_ttc_par_jour": {"2026-09-18": 280.0,
                                                     "2026-09-21": 310.0}}}
    r2 = _courbe(court)
    trous = [j for j in r2["jeux"] if any(v is None for v in j["data"])]
    assert len(trous) >= 2, "ce jeu devrait porter des trous — comparaison courte, seuil partiel"
    for serie in trous:
        assert serie.get("spanGaps") is False, f"« {serie['label']} » comblerait son trou"


def test_LE_POINT_MORT_S_ALIGNE_SUR_LA_DATE_PAS_SUR_LE_RANG():
    """
    ⚠️ LA COMPARAISON S'ALIGNE SUR LE RANG — c'est voulu, les deux fenêtres n'ont pas les mêmes
    quantièmes. LE POINT MORT, LUI, APPARTIENT À UNE DATE : l'aligner sur le rang le décale
    d'un cran à chaque jour fermé, et il irait annoncer à un lundi le seuil d'un samedi à deux
    extras. Les deux séries se ressemblent, et la règle est l'inverse.
    """
    r = _courbe({"daily": JOURS, "daily_comp": [],
                 "economics": {"seuil_ca_ttc_jour": 287.0,
                               "seuil_ca_ttc_par_jour": {"2026-09-18": 280.0,
                                                         "2026-09-21": 310.0}}})
    seuil = [j for j in r["jeux"] if "mort" in j["label"]][0]
    # JOURS = 18, 19, 21 ; le seuil n'est connu que pour le 18 et le 21.
    assert seuil["data"] == [280.0, None, 310.0], (
        "le seuil est aligné sur le rang : il annonce au 19 le chiffre du 21")


def test_les_deux_series_sont_alignees_sur_le_rang_pas_sur_la_date():
    """
    ⚠️ LES DEUX FENÊTRES N'ONT PAS LES MÊMES QUANTIÈMES — c'est tout l'intérêt d'une
    comparaison à nombre de services égal. Les aligner par date ferait glisser la courbe d'un
    cran à chaque jour fermé.
    """
    r = _courbe(PAYLOAD)
    assert len(r["labels"]) == 3
    for j in r["jeux"]:
        assert len(j["data"]) == 3


def test_le_serveur_sert_bien_la_serie_de_comparaison():
    """⚠️ SANS ELLE, LA COURBE EN POINTILLÉS DISPARAÎT SANS ERREUR : le jeu de données est
    simplement absent, et la page perd sa comparaison en silence."""
    src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    assert '"daily_comp":    daily_breakdown(docs_comp),' in src


def test_une_mini_courbe_refuse_de_tracer_un_seul_point():
    """
    ⚠️ UN POINT UNIQUE DONNE UNE LIGNE PLATE, qui se lit « stable » — alors qu'on n'a rien
    mesuré. C'est la même faute que d'afficher 0 pour une absence.
    """
    js = _js()
    i = js.index("function miniCourbe(")
    bloc = js[i:js.index("\nfunction renderMinis(", i)]
    assert "mesures.length < 2" in bloc
    assert "display = 'none'" in bloc


def test_les_quatre_cartes_disent_moins_plutot_que_zero():
    """
    ⚠️ « AUCUNE DONNÉE » ET « ZÉRO » MÈNENT À DES DÉCISIONS OPPOSÉES, et sur une carte de trois
    lignes rien ne les distingue si l'on écrit 0. Les quatre écrivent « — » et disent pourquoi.
    """
    js = _js()
    i = js.index("function renderQuatre(")
    bloc = js[i:js.index("\nfunction renderReponse(", i)]
    assert bloc.count("= '—'") >= 4, "une carte affiche un zéro à la place d'une absence"
    # ⚠️ ET LA COUVERTURE RENVOIE VERS L'ÉCRAN QUI RÉPARE, plutôt que de constater : sous
    # 100 %, la marge est extrapolée, donc le résultat et le point mort aussi. Le lien porte
    # la carte ENTIÈRE, dans le gabarit — un renvoi en fin de phrase se rate au doigt.
    assert "extrapolée" in bloc
    html = _gabarit()
    i = html.index('id="db-couv"')
    assert 'href="/cogs"' in html[max(0, i - 400):i], "la carte n'est pas cliquable"


def test_les_quatre_cartes_ne_repetent_rien_de_la_page():
    """
    ⚠️ « OÙ VA L'ARGENT » DÉCOMPOSAIT CE QUE LES DEUX SEUILS RÉSUMENT DÉJÀ : marchandise plus
    personnel EST le prime cost, et le reste est le résultat, affiché en tête. Une décomposition
    qui n'ajoute rien à ce qu'on vient de lire fait douter des deux.
    """
    js = _js()
    i = js.index("function renderQuatre(")
    bloc = js[i:js.index("\nfunction renderReponse(", i)]
    for deja_ailleurs in ("cout_perso_periode", "cout_fixe_periode", "ebitda_ht", "marge_brute_ht"):
        assert deja_ailleurs not in bloc, f"{deja_ailleurs} est déjà affiché ailleurs"


def test_le_selecteur_marque_la_periode_active():
    """
    ⚠️ UN BOUTON QUI NE S'ENFONCE PAS EST UN BOUTON QU'ON RECLIQUE. L'ancienne bascule visait
    `.pill`, qui n'existe plus depuis le passage au segmenté : la page se rechargeait bien, mais
    rien ne disait quelle période était affichée — et le chiffre du haut, lui, avait changé.

    ⚠️ ET C'EST `aria-pressed`, PAS UNE CLASSE. Le style s'y accroche, et un lecteur d'écran
    l'annonce ; une classe ne fait ni l'un ni l'autre.
    """
    js = _js()
    i = js.index("function setPreset(")
    bloc = js[i:js.index("\n}", i)]
    # ⚠️ SANS LES COMMENTAIRES. L'explication au-dessus de la ligne contient « aria-pressed » :
    # un mutant qui remettait `classList.toggle` à l'écran survivait, puisque le mot restait
    # dans le fichier. Chercher dans le commentaire revient à vérifier qu'on a eu l'intention.
    code = re.sub(r"/\*.*?\*/", " ", bloc, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    assert "aria-pressed" in code, "le segmenté n'est pas marqué"
    assert "#period-pills button[data-preset]" in code, "la bascule ne vise pas le segmenté"
    css = open(os.path.join(RACINE, "static", "dashboard.css"), encoding="utf-8").read()
    assert '.db-seg button[aria-pressed="true"]' in css, "l'état sélectionné n'est pas peint"
    # ⚠️ ET LE GABARIT EN POSE UN SEUL À VRAI AU CHARGEMENT : deux boutons enfoncés diraient
    # deux périodes, un seul chiffre étant affiché.
    html = _gabarit()
    i = html.index('id="period-pills"')
    barre = html[i:html.index("</div>", i)]
    assert barre.count('aria-pressed="true"') == 1, barre.count('aria-pressed="true"')

def _vise_une_cellule(selecteur):
    """Le sélecteur STYLE-t-il une cellule, ou seulement quelque chose qui vit dedans ?"""
    import re
    dernier = re.split(r"[\s>+~]+", selecteur.strip())[-1]
    # On retire classes, id, pseudo-classes et attributs : reste le nom d'élément, s'il y en a.
    element = re.split(r"[.#:\[]", dernier)[0].strip().lower()
    return element in ("th", "td", "tr", "thead", "tbody")


def test_aucune_cellule_de_tableau_ne_sort_du_contexte_tabulaire():
    """
    ⚠️ CE CONTRÔLE EXISTE PARCE QUE `display:flex` SUR UN `<th>` A DÉTRUIT UNE RANGÉE ENTIÈRE.
    Le libellé « Qté en stock » et sa pastille ⓘ débordaient de leur colonne ; la boîte flex
    semblait le correctif évident — elle enferme ses enfants et sait passer à la ligne.

    Sauf qu'un `display:flex` SORT l'élément du contexte de formatage tabulaire : ce n'est plus
    une cellule. Mesuré dans le navigateur, les cinq en-têtes numériques se sont empilés sur la
    même boîte (903→1039 px) pendant que les cellules du corps restaient à leur place — la
    rangée d'en-tête entièrement désalignée du tableau qu'elle coiffe.

    ⚠️ ET RIEN NE LE DIT. Le HTML reste valide, le CSS aussi, la page se charge sans un
    avertissement. C'est en MESURANT les rectangles qu'on le voit — jamais en relisant la règle,
    qui a l'air parfaitement raisonnable.

    `display:grid` a exactement le même effet, et `inline-flex` aussi.
    """
    import glob
    import re

    FAUTIFS = ("flex", "inline-flex", "grid", "inline-grid", "block", "inline-block")
    coupables = []
    for chemin in sorted(glob.glob(os.path.join(RACINE, "templates", "*.html"))):
        html = open(chemin, encoding="utf-8").read()
        for style in re.findall(r"<style[^>]*>(.*?)</style>", html, re.S):
            # On enlève les commentaires : une règle citée en exemple n'est pas une règle.
            style = re.sub(r"/\*.*?\*/", " ", style, flags=re.S)
            """
            ⚠️ LES BLOCS `@media (max-width: …)` SONT EXEMPTÉS, ET C'EST RAISONNÉ. Ce contrôle
            existe parce qu'une cellule sortie du contexte tabulaire cesse de s'aligner sur sa
            colonne — silencieusement. Sous une largeur donnée, il n'y a PLUS de colonnes :
            transformer les rangées en cartes est la seule façon de rendre un tableau de six
            colonnes utilisable sur un iPad, et le désalignement est alors l'intention.

            Ce qui reste interdit est l'essentiel : la même déclaration hors média, c'est-à-dire
            sur l'écran large où les colonnes existent — la panne du 28/09/2026, où cinq en-têtes
            se sont empilés sur la même case pendant que le corps du tableau restait en place.
            """
            style = re.sub(r"@media[^{]*max-width[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", " ",
                           style, flags=re.S)
            for bloc in re.finditer(r"([^{}]+)\{([^{}]*)\}", style):
                selecteur, corps = bloc.group(1), bloc.group(2)
                # ⚠️ SEUL LE DERNIER ÉLÉMENT DU SÉLECTEUR EST CELUI QU'ON STYLE. La première
                # version cherchait « th » n'importe où et accusait `.db thead th button`,
                # qui vise un BOUTON dans un en-tête — parfaitement légitime. Un garde qui
                # crie au loup sur du code correct finit désactivé, et ne garde plus rien.
                if not any(_vise_une_cellule(part) for part in selecteur.split(",")):
                    continue
                m = re.search(r"display\s*:\s*([a-z-]+)", corps)
                if m and m.group(1) in FAUTIFS:
                    coupables.append(
                        f"{os.path.basename(chemin)} : `{selecteur.strip()[:60]}` "
                        f"pose display:{m.group(1)}")
    assert not coupables, (
        "une cellule de tableau quitte le contexte tabulaire — la colonne se désaligne "
        "silencieusement :\n  " + "\n  ".join(coupables))
