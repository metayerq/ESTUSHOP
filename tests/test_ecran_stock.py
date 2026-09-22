"""
L'ÉCRAN STOCK — la répartition, et ce qui demande un geste.

⚠️ CET ÉCRAN N'AVAIT AUCUN TEST. Il pilote la seule question qu'on lui pose — « qu'est-ce qu'il
faut commander ? » — et rien ne gardait ni le compte, ni la répartition, ni l'état.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _gabarit():
    return open(os.path.join(RACINE, "templates", "stock.html"), encoding="utf-8").read()


def _js():
    g = _gabarit()
    return g[g.rindex("<script>") + 8:g.rindex("</script>")]


def _fonction(nom):
    js = _js()
    i = js.index(f"function {nom}(")
    return js[i:js.index("\n}", i) + 2]


def _rendre(articles, onglet="all"):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    js = _js()
    i = js.index("const CAT_ORDER")
    consts = js[i:js.index("];", i) + 2]
    socle = """
const ids = {};
function faire(id) {
  const o = { id, _t: '', innerHTML: '', attrs: {}, style: {}, value: '',
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; } };
  Object.defineProperty(o, 'textContent', { get() { return this._t; },
                                            set(v) { this._t = String(v); } });
  return o;
}
const document = { getElementById: id => ids[id] || (ids[id] = faire(id)) };
const IS_ADMIN = true;
""" + consts + f"\nlet tab = {json.dumps(onglet)};\n"
    prog = (socle + _fonction("needsOrder") + _fonction("render")
            + f"let items = {json.dumps(articles)};\nrender();\n"
            + """console.log(JSON.stringify({
                 total: ids['s-total'].textContent, cats: ids['s-cats'].textContent,
                 ok: ids['s-ok'].textContent, low: ids['s-low'].textContent,
                 out: ids['s-out'].textContent,
                 parts: ['part-ok','part-low','part-out'].map(k => ids[k].style.width),
                 order: ids['s-order'].textContent, sub: ids['s-order-sub'].textContent,
                 etat: ids['i-order'].attrs['data-etat'] || null,
                 liste: ids['list'].innerHTML,
               }));""")
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def A(nom, statut="ok", alerte=False, cat="Épicerie"):
    return {"id": nom, "name": nom, "category": cat, "status": statut,
            "alert": alerte, "notes": "", "active": True}


# ── La répartition ───────────────────────────────────────────────────────────────────────────

def test_les_trois_parts_font_le_tout():
    """
    ⚠️ ELLES N'EN FAISAIENT QUE TROIS QUARTS. Le compte « ok » excluait les articles signalés à
    la main : trois parts totalisant 75 %, et un quart de barre vide sans que rien ne dise à
    quoi il correspondait. Un article signalé reste AU NIVEAU OK — ce qui est signalé se lit
    dans « à commander », qui existe pour ça.

    ⚠️ UNE BARRE QUI NE BOUCLE PAS EST PIRE QU'UNE ABSENCE DE BARRE : elle promet une
    répartition, et on cherche ce qui manque au lieu de lire ce qui est là.
    """
    r = _rendre([A("a"), A("b", "low"), A("c", "out"), A("d", "ok", alerte=True)])
    parts = [float(p.rstrip("%")) for p in r["parts"]]
    assert abs(sum(parts) - 100) < 0.05, r["parts"]
    assert [r["ok"], r["low"], r["out"]] == ["2", "1", "1"]


def test_sans_article_la_barre_ne_ment_pas():
    """Zéro article divisé par zéro ne vaut pas « tout va bien »."""
    r = _rendre([])
    assert r["parts"] == ["0%", "0%", "0%"]
    assert r["etat"] is None, "une liste vide se dit saine"


# ── Ce qui demande un geste ──────────────────────────────────────────────────────────────────

def test_un_article_signale_a_la_main_compte_a_commander_meme_sil_est_ok():
    """C'est tout l'intérêt du drapeau : anticiper avant que le niveau ne tombe."""
    r = _rendre([A("a"), A("b", "ok", alerte=True)])
    assert r["order"] == "1"
    assert r["ok"] == "2", "le drapeau a changé le NIVEAU de l'article"


@pytest.mark.parametrize("articles,etat", [
    ([A("a")], "ok"),
    ([A("a"), A("b", "ok", alerte=True)], "attention"),
    ([A("a"), A("b", "low")], "attention"),
    ([A("a"), A("b", "out")], "alerte"),
])
def test_letat_distingue_manquer_de_bientot_manquer(articles, etat):
    """
    ⚠️ « BAS » ET « ÉPUISÉ » N'APPELLENT PAS LE MÊME GESTE. Bas se commande cette semaine ;
    épuisé veut dire qu'on ne peut plus servir. Les peindre pareil ferait manquer le second au
    milieu des premiers.
    """
    assert _rendre(articles)["etat"] == etat


def test_rien_a_commander_le_dit_plutot_que_dafficher_un_zero_nu():
    r = _rendre([A("a")])
    assert r["order"] == "0" and "rien ne manque" in r["sub"]


# ── La charte ────────────────────────────────────────────────────────────────────────────────

def test_la_page_porte_la_charte():
    g = _gabarit()
    assert 'class="page db"' in g, "la classe qui définit le fond et l'encre est absente"
    assert "/static/dashboard.css?v=" in g, "la feuille de charte n'est pas chargée"


def test_le_niveau_est_un_segmente_de_la_charte():
    """
    ⚠️ LE CONTRÔLE DE NIVEAU SE PEINT SUR `aria-pressed`, comme tous les segmentés du produit.
    Il marquait son choix avec `.active` ; reprendre le composant sans reprendre l'attribut
    aurait donné trois boutons dont aucun ne paraît choisi — sur le geste principal de la page.

    ⚠️ ET LA SPÉCIFICITÉ EST CALCULÉE, PAS ESPÉRÉE. `.db-seg button[aria-pressed="true"]` pèse
    (0,2,1) et peint en accent ; les trois états pèsent (0,3,1) et gagnent donc, où qu'ils
    soient dans la feuille.
    """
    r = _rendre([A("a", "low")])
    assert 'class="db-seg status-seg"' in r["liste"]
    assert 'class="low" aria-pressed="true"' in r["liste"], r["liste"][:300]
    assert "status-btn" not in r["liste"], "l'ancien composant est revenu"
    bloc = _gabarit()
    bloc = bloc[bloc.index("<style>"):bloc.index("</style>")]
    for etat in ("ok", "low", "out"):
        assert f'.status-seg button.{etat}[aria-pressed="true"]' in bloc, etat


def test_les_onglets_ne_sont_plus_une_cinquieme_copie():
    g = _gabarit()
    assert 'class="nav-seg"' in g
    bloc = g[g.index("<style>"):g.index("</style>")]
    for mort in (".view-tabs", ".view-tab", ".tab-badge"):
        assert mort not in bloc, f"{mort} : l'ancien composant est revenu"
    assert "classList.toggle('active'" not in _js(), "le marqueur d'actif est resté sur une classe"


def test_le_niveau_reste_un_etat_et_non_une_categorie():
    """
    ⚠️ ICI LE VERT, L'AMBRE ET LE ROUGE SONT LÉGITIMES, et c'est la seule page du produit où
    les trois le sont ensemble : « épuisé » est un problème, « bas » un avertissement, « OK »
    une bonne nouvelle. Le contrôle qui interdit de peindre une CATÉGORIE en état ne doit pas
    faire perdre celui-là au passage.
    """
    bloc = _gabarit()
    bloc = bloc[bloc.index("<style>"):bloc.index("</style>")]
    for etat, jeton in (("ok", "green"), ("low", "amber"), ("out", "red")):
        regle = bloc[bloc.index(f".status-seg button.{etat}["):]
        regle = regle[:regle.index("}")]
        assert f"--db-{jeton}" in regle, f"{etat} : {regle.strip()}"
