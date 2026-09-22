"""
L'ÉCRAN TRÉSORERIE — et la variable qui n'est jamais partie avec son code.

⚠️ CETTE PAGE ÉTAIT CASSÉE EN PRODUCTION, SANS QUE RIEN NE LE DISE. `renderCashflow()` levait
un `ReferenceError` à la construction du graphique : `BAR_ACTIVE` était une variable de
`dashboard.js`, emportée avec le code quand la trésorerie a été détachée, mais sa DÉCLARATION
est restée derrière — puis a disparu du tableau de bord à son tour.

⚠️ ET LE MODE DE PANNE EST LE PIRE QU'ON PUISSE AVOIR : les quatre chiffres du haut
s'affichaient (ils sont calculés AVANT la ligne fautive), le graphique ne se dessinait jamais,
et le détail mensuel restait sur « Loading… » indéfiniment. Une page à moitié remplie se lit
comme une page qui charge lentement, pas comme une page en erreur — on attend, puis on ferme.

⚠️ AUCUN TEST N'EXISTAIT ICI. C'est la seule raison pour laquelle ça a pu durer : le fichier
était relu, le bug n'est pas dans une ligne, il est dans une ligne ABSENTE d'un autre fichier.
Ce que ces contrôles font, c'est EXÉCUTER le rendu — la seule chose qui distingue « le code a
l'air juste » de « le code marche ».
"""
import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(RACINE, "static", "cashflow.js"), encoding="utf-8").read()


def _code_seul(src):
    """
    ⚠️ LE CODE SANS SES COMMENTAIRES NI SES CHAÎNES. C'est la quatrième fois de cette refonte
    qu'un détecteur reconnaît sa propre explication : le commentaire qui dit pourquoi
    `yAxisID: 'y2'` a été retiré contient `yAxisID`. Et les chaînes comptent autant — une
    entité HTML `&#10005;` ressemble à une couleur, un `'2026-07-01T12:00'` à une constante.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    # Les commentaires de fin de ligne aussi — mais pas le `//` d'une URL.
    src = re.sub(r"(?<!:)//.*$", " ", src, flags=re.M)
    src = re.sub(r"`(?:[^`\\]|\\.)*`", " '' ", src)
    src = re.sub(r"'(?:[^'\\\n]|\\.)*'", " '' ", src)
    src = re.sub(r'"(?:[^"\\\n]|\\.)*"', ' "" ', src)
    return src


def _gabarit():
    return open(os.path.join(RACINE, "templates", "cashflow.html"), encoding="utf-8").read()


MOIS = [
    {"month": "2026-05", "cash_in": 2400, "expenses": 9000, "expenses_excl_capex": 1200,
     "net": -6600, "net_excl_capex": 1200, "cum_net": -6600, "cum_net_excl_capex": 1200,
     "commissions": 0},
    {"month": "2026-06", "cash_in": 9000, "expenses": 7000, "expenses_excl_capex": 5000,
     "net": 2000, "net_excl_capex": 4000, "cum_net": -4600, "cum_net_excl_capex": 5200,
     "commissions": 0},
    {"month": "2026-07", "cash_in": 10000, "expenses": 8000, "expenses_excl_capex": 6000,
     "net": 2000, "net_excl_capex": 4000, "cum_net": -2600, "cum_net_excl_capex": 9200,
     "commissions": 120},
]


def _rendre(mois=None, excl=False):
    """Exécute `renderCashflow` pour de vrai, sur un DOM minimal."""
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    prog = """
const ids = {};
function faire(id) {
  const o = { id, _t: '', innerHTML: '', style: {}, checked: %s, value: '', attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    getContext: () => ({ canvas: {} }) };
  Object.defineProperty(o, 'textContent', { get() { return this._t; },
                                            set(v) { this._t = String(v); } });
  return o;
}
const document = { documentElement: {}, getElementById: id => ids[id] || (ids[id] = faire(id)) };
function Chart(ctx, cfg) { this.destroy = () => {}; Chart.last = cfg; }
const getComputedStyle = () => ({ getPropertyValue: n => 'JETON' + n });
const window = {};
const fetch = () => new Promise(() => {});
""" % ("true" if excl else "false")
    src = _js().replace("\nloadCashflow();\nloadCommissions();\n", "\n")
    prog += src + f"\ncashflowData = {json.dumps({'months': mois if mois is not None else MOIS})};\n"
    prog += """
let boum = null;
try { renderCashflow(); } catch (e) { boum = e.constructor.name + ': ' + e.message; }
console.log(JSON.stringify({
  boum,
  totalIn: ids['cf-total-in'] ? ids['cf-total-in'].textContent : null,
  net: ids['cf-net'] ? ids['cf-net'].textContent : null,
  etatNet: ids['i-net'] ? (ids['i-net'].attrs['data-etat'] || null) : '@ABSENT',
  best: ids['cf-best'] ? ids['cf-best'].innerHTML : null,
  corps: ids['cashflow-body'] ? ids['cashflow-body'].innerHTML : '@JAMAIS-TOUCHÉ',
  chart: typeof Chart.last === 'undefined' ? null : {
    axes: Object.keys(Chart.last.options.scales),
    series: Chart.last.data.datasets.map(d => ({
      label: d.label, type: d.type, couleur: d.backgroundColor || d.borderColor,
      axe: d.yAxisID || null })),
  },
}));"""
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── La panne ─────────────────────────────────────────────────────────────────────────────────

def test_le_rendu_va_jusquau_bout():
    """
    ⚠️ LE CONTRÔLE QUI AURAIT ÉVITÉ TOUT ÇA. Il ne vérifie rien de subtil : il appelle la
    fonction. Un `ReferenceError` sur une variable qui n'existe pas ne se voit dans aucune
    relecture du fichier fautif — la ligne manquante est ailleurs.
    """
    r = _rendre()
    assert r["boum"] is None, r["boum"]


def test_le_detail_mensuel_se_remplit_vraiment():
    """
    ⚠️ IL RESTAIT SUR « Loading… » DEPUIS LA SÉPARATION DES DEUX ÉCRANS. Le remplissage se
    trouve APRÈS la construction du graphique : tout ce qui suivait la ligne fautive ne
    s'exécutait jamais.
    """
    r = _rendre()
    assert r["corps"] != "@JAMAIS-TOUCHÉ", "la table n'a même pas été atteinte"
    assert len(re.findall(r"<tr>", r["corps"])) == 3, r["corps"][:200]


def test_aucune_variable_libre_dans_les_scripts_de_page():
    """
    ⚠️ `BAR_ACTIVE` A LA FORME D'UNE CONSTANTE DE MODULE, et c'est ce qui le rendait invisible :
    en majuscules, il ressemble à quelque chose de fourni par ailleurs. Ce contrôle vérifie que
    chaque nom de cette forme est bien DÉCLARÉ dans le fichier qui l'emploie.

    ⚠️ IL NE REMPLACE PAS L'EXÉCUTION, il l'accompagne. Une variable en minuscules passerait
    entre les mailles ; celle-là, non — et c'est celle qui vient de coûter une page.
    """
    connus = {"JSON", "URL"}          # globales du navigateur, jamais déclarées
    for nom in sorted(os.listdir(os.path.join(RACINE, "static"))):
        if not nom.endswith(".js"):
            continue
        src = _code_seul(open(os.path.join(RACINE, "static", nom), encoding="utf-8").read())
        declares = set(re.findall(r"(?:const|let|var|function)\s+([A-Z][A-Z0-9_]{2,})", src))
        # ⚠️ UNE DÉCLARATION PEUT EN PORTER PLUSIEURS : `var KEY = 'x', ORDER = [...]`. Ne lire
        # que le premier nom fait passer les suivants pour des variables libres — et un
        # contrôle qui crie au loup sur du code juste finit par ne plus être lu.
        declares |= set(re.findall(r",\s*([A-Z][A-Z0-9_]{2,})\s*=", src))
        # Une propriété (`x.FOO`) ou une clé d'objet (`FOO:`) n'est pas une variable libre.
        src = re.sub(r"\.\s*[A-Z][A-Z0-9_]{2,}", " ", src)
        src = re.sub(r"\b[A-Z][A-Z0-9_]{2,}\s*:", " ", src)
        # ⚠️ EN POSITION DE CODE, PAS DANS UNE PHRASE. `COGS et EBITDA` dans un commentaire ou
        # `MTD <strong>` dans un gabarit de chaîne ont la forme d'une constante et n'en sont
        # pas. Un identifiant employé est suivi d'un délimiteur JavaScript, jamais d'un mot.
        employes = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\s*(?=[,);.\[\]}=?:+*/&|-]|$)",
                                  src, re.M))
        libres = employes - declares - connus
        assert not libres, f"{nom} : {sorted(libres)} employé(s) sans déclaration"


# ── Le graphique ─────────────────────────────────────────────────────────────────────────────

def test_un_seul_axe_des_ordonnees():
    """
    ⚠️ IL Y EN AVAIT DEUX, POUR LA MÊME UNITÉ. Les barres (flux du mois) sur l'axe de gauche,
    le cumul sur un axe de droite : des euros contre des euros, à deux échelles. On comparait
    une hauteur de barre à une hauteur de ligne, et le point où elles se croisent ne voulait
    strictement rien dire.

    ⚠️ SUR UN SEUL AXE, UN CUMUL QUI ÉCRASE LES BARRES EST UNE INFORMATION : il dit que le mois
    pèse peu devant ce qui s'est accumulé. C'est précisément ce que le second axe cachait.
    """
    r = _rendre()
    assert sorted(r["chart"]["axes"]) == ["x", "y"], r["chart"]["axes"]
    assert all(s["axe"] is None for s in r["chart"]["series"]), r["chart"]["series"]
    assert "yAxisID" not in _code_seul(_js())


def test_le_graphique_lit_ses_couleurs_dans_les_jetons():
    """Six couleurs de l'ancien thème beige étaient écrites en dur — elles n'ont jamais suivi
    le passage en mode sombre, ni le changement de palette."""
    r = _rendre()
    couleurs = [s["couleur"] for s in r["chart"]["series"]]
    assert all(c.startswith("JETON--") or c == "transparent" for c in couleurs), couleurs
    src = _code_seul(_js())
    assert not re.search(r"rgba?\([\d\s,.]+\)", src), re.findall(r"rgba?\([\d\s,.]+\)", src)
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", src), re.findall(r"#[0-9a-fA-F]{3,6}\b", src)


def test_un_changement_de_theme_redessine():
    """Chart.js lit ses couleurs une fois, au tracé : sans écoute, le graphique reste aux
    couleurs de l'ancien mode."""
    assert "prefers-color-scheme: dark" in _js()
    assert "renderCashflow()" in _js()[_js().index("matchMedia"):]


# ── Les états ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("excl,etat", [(False, "alerte"), (True, "ok")])
def test_le_net_porte_son_etat_sur_la_carte(excl, etat):
    """
    ⚠️ LA CASE « NET » EST LA SEULE DES QUATRE À POSER UNE QUESTION. Les trois autres sont des
    constats. Et l'état change avec la case « exclure les investissements » : c'est tout
    l'intérêt de la case — savoir si le trou vient des travaux ou de l'exploitation.
    """
    r = _rendre(excl=excl)
    assert r["etatNet"] == etat, f"excl={excl} → {r['etatNet']}"


def test_le_meilleur_et_le_pire_mois_ne_sont_pas_un_jugement():
    """
    ⚠️ ILS ÉTAIENT PEINTS EN VERT ET EN ROUGE. Ce sont les deux bouts d'une même série : le
    pire mois d'un bon semestre reste positif, et le rouge lui donnait tort. Les pastilles
    disent « haut » et « bas », pas « bien » et « mal ».
    """
    r = _rendre()
    assert "db-badge" in r["best"]
    assert "down" not in r["best"], r["best"]
    assert "var(--red)" not in r["best"] and "var(--green)" not in r["best"], r["best"]


def test_un_cumul_negatif_est_la_seule_alerte_du_tableau():
    """
    ⚠️ LE NET D'UN MOIS VA ET VIENT ; LE CUMUL QUI REPASSE SOUS ZÉRO dit qu'on a dépensé plus
    qu'encaissé DEPUIS L'OUVERTURE. Colorer les deux colonnes mettait au même niveau une
    fluctuation et un état.
    """
    r = _rendre()
    assert r["corps"].count("cum-neg") == 3, r["corps"][:300]
    assert "cum-pos" not in r["corps"]
    r2 = _rendre(excl=True)
    assert r2["corps"].count("cum-pos") == 3 and "cum-neg" not in r2["corps"]


# ── La charte ────────────────────────────────────────────────────────────────────────────────

def test_la_page_porte_la_charte():
    html = _gabarit()
    assert 'class="page db"' in html, "la classe qui définit les jetons `--db-*` est absente"
    assert "/static/dashboard.css?v=" in html, "la feuille de charte n'est pas chargée"


def test_la_garde_robe_du_tableau_de_bord_est_partie():
    """
    ⚠️ 29 RÈGLES, TOUTES MORTES. La page a été détachée du tableau de bord et en a emporté le
    vestiaire entier : onglets de vue, paiements compacts, bande « semaine dernière », cartes
    d'insight, calendrier, carte de chaleur, en-tête collant des produits. Du style mort se lit
    comme du style disponible.
    """
    bloc = _gabarit()
    bloc = bloc[bloc.index("<style>"):bloc.index("</style>")]
    for mort in (".view-tabs", ".view-tab", ".pay-compact", ".wow-strip", ".ins-card",
                 ".ins-label", ".hm-grid", ".cal-grid", ".mv-row", ".zone-head",
                 ".products-scroll"):
        assert mort not in bloc, f"{mort} : le vestiaire est revenu"
