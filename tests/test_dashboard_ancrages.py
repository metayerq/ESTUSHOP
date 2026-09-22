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

def test_les_jetons_du_tableau_de_bord_ne_debordent_pas_sur_les_autres_pages():
    """
    ⚠️ POSER CES JETONS SUR `:root` REPEINDRAIT QUINZE ÉCRANS D'UN COUP. Affluence, Fidélité,
    Charges, Réconciliation n'ont pas été relus dans ce langage : une refonte silencieuse se
    découvre en production, sur la page qu'on ouvre le moins.
    """
    css = open(os.path.join(RACINE, "static", "dashboard.css"), encoding="utf-8").read()
    assert ":root {" not in css, "les jetons sont posés globalement"
    assert css.count(".db {") >= 1
    html = _gabarit()
    assert 'class="page db"' in html, "la page ne porte pas le préfixe qui active les jetons"
    assert "/static/dashboard.css?v=" in html, "la feuille n'est pas chargée, ou sans version"
    # ⚠️ ET ELLE N'EST CHARGÉE QUE LÀ. Une autre page qui l'inclurait hériterait de jetons
    # pensés pour celle-ci, sans en porter la structure.
    import glob
    for chemin in glob.glob(os.path.join(RACINE, "templates", "*.html")):
        if os.path.basename(chemin) == "index.html":
            continue
        assert "dashboard.css" not in open(chemin, encoding="utf-8").read(), chemin


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
    # ⚠️ LA LIGNE DU POINT MORT N'A PAS DE `spanGaps` : c'est une constante, sans trou. Exiger
    # la clé partout ferait échouer le test sur un jeu de données qui n'a pas le problème.
    porteurs = [j for j in r["jeux"] if "spanGaps" in j and j["spanGaps"] is not None]
    assert len(porteurs) == 2, "les deux séries mesurées ne portent pas la garde"
    assert all(j["spanGaps"] is False for j in porteurs)


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


def test_la_repartition_se_tait_sans_marge():
    """
    ⚠️ SANS MARGE, LA RÉPARTITION N'EN EST PAS UNE : il manquerait le plus gros poste, et les
    parts affichées sembleraient tout couvrir.
    """
    js = _js()
    i = js.index("function renderRepartition(")
    bloc = js[i:js.index("\nfunction renderReponse(", i)]
    assert "ebitda_ht == null" in bloc and "/cogs" in bloc
