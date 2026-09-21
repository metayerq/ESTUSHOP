"""
LE LANGAGE VISUEL DES INDICATEURS.

⚠️ DOUZE CHIFFRES DE TAILLE IDENTIQUE NE DISENT PAS LEQUEL REGARDER. Et un nombre coloré est
plus difficile à lire qu'un nombre en encre — sur douze indicateurs colorés, plus rien ne
ressort. La bande d'accent porte l'état, le chiffre reste lisible, et seuls ceux qui décident
quelque chose passent en vedette.

⚠️ AUCUNE DE CES RÈGLES NE LÈVE SI ON LA CASSE. L'écran reste « fonctionnel » : il se lit
simplement moins bien, et on finit par ne plus l'ouvrir.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


CSS = lire("static/style.css")
DASH = lire("static/dashboard.js")
COGS = lire("templates/cogs.html")


# ── La bande d'accent ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etat", ["ok", "attention", "alerte"])
def test_chaque_etat_a_sa_bande(etat):
    assert f'.kpi-cell[data-etat="{etat}"]::before' in CSS


def test_le_chiffre_nest_plus_colore():
    """
    ⚠️ LA RÉGRESSION À EMPÊCHER. Le prime cost peignait sa propre valeur en vert, ambre ou
    rouge ; avec la bande, la couleur du texte devient redondante et nuit à la lecture.
    """
    i = DASH.index("primeEl.textContent = prime.toFixed(1)")
    bloc = DASH[i:i + 600]
    assert "primeEl.style.color = ''" in bloc
    assert "prime <= 67 ? 'var(--green)'" not in bloc


def test_les_deux_indicateurs_qui_decident_sont_en_vedette():
    """
    La marge et le prime cost décident d'un geste ; le reste est du contexte. ⚠️ ET PAS PLUS DE
    DEUX : si tout est en vedette, plus rien ne l'est.
    """
    index = lire("templates/index.html")
    assert index.count("kpi-cell vedette") == 2
    assert ".kpi-cell.vedette .kpi-value" in CSS


def test_un_indicateur_sans_donnee_na_pas_detat():
    """
    ⚠️ « PAS DE DONNÉE » N'EST PAS « BON ». Poser une valeur neutre allumerait une bande verte
    sur une case vide.
    """
    i = DASH.index("function etat(el, valeur)")
    bloc = DASH[i:i + 400]
    assert "removeAttribute('data-etat')" in bloc


# ── Le repère de seuil ───────────────────────────────────────────────────────────────────────

def test_le_prime_cost_porte_son_repere_de_cible():
    """
    ⚠️ VOIR DE COMBIEN ON DÉPASSE VAUT MIEUX QUE SAVOIR QU'ON DÉPASSE. Une barre sans repère
    dit « c'est trop » ; avec le repère, elle dit « de deux points ».
    """
    assert "marquerSeuil(primeBar, 65" in DASH
    assert ".seuil-marque" in CSS


def test_le_repere_est_dans_la_barre_pas_a_cote():
    """Une légende sous le graphique oblige à convertir une largeur en pourcentage — c'est
    exactement le calcul que le repère évite."""
    i = DASH.index("function marquerSeuil")
    bloc = DASH[i:i + 700]
    assert "m.style.left" in bloc
    assert "appendChild(m)" in bloc


def test_le_repere_ne_sort_pas_de_la_barre():
    """Un seuil à 140 % placerait le trait hors du cadre, sans rien dire."""
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    # ⚠️ ON APPELLE LA VRAIE FONCTION, avec un DOM simulé. La première version de ce test
    # recopiait le bornage dans le programme node et vérifiait donc sa propre copie : le mutant
    # qui retirait le `Math.min` passait tranquillement.
    i = DASH.index("function marquerSeuil")
    fn = DASH[i:DASH.index("\n}", i) + 2]
    prog = fn + """
    function faireBarre(){
      var env = { classList: { add: function(){} }, enfants: [],
                  querySelector: function(){ return null; },
                  appendChild: function(x){ this.enfants.push(x); } };
      return { parentElement: env, env: env };
    }
    global.document = { createElement: function(){ return { style: {}, className: '' }; } };
    var pos = [-10, 0, 65, 100, 140].map(function(p){
      var b = faireBarre();
      marquerSeuil(b, p, 'x');
      return b.env.enfants[0].style.left;
    });
    console.log(JSON.stringify(pos));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["0%", "0%", "65%", "100%", "100%"]


# ── Les états vides ──────────────────────────────────────────────────────────────────────────

def test_une_case_vide_dit_ce_qui_la_remplira():
    """
    ⚠️ « NOT MEASURABLE » LAISSE DEVANT UN ÉCRAN MORT. Une case vide doit nommer le geste, et
    porter le lien qui y mène.
    """
    for morceau in ("Il manque les prix d", "Aucun prix d"):
        assert morceau in DASH, f"état vide sans consigne : {morceau}"
    assert DASH.count('href="/cogs"') >= 2


def test_les_anciens_libelles_morts_ont_disparu():
    assert "not measurable" not in DASH
    assert "no COGS set" not in DASH


# ── COGS parle la même langue ────────────────────────────────────────────────────────────────

def test_cogs_met_la_couverture_en_tete_et_en_vedette():
    """
    ⚠️ UNE MARGE MOYENNE DE 75 % SUR 96 % DU CATALOGUE ET LA MÊME SUR 55 % NE SONT PAS LA MÊME
    INFORMATION — et c'est la seconde qui appelle un geste. L'afficher à côté de la marge, à la
    même taille, laissait le lecteur décider lequel des deux compte.
    """
    assert 'id="s-couv"' in COGS
    assert 'id="i-couv"' in COGS and "sum-item vedette" in COGS
    assert COGS.index('id="i-couv"') < COGS.index('id="s-avg"')


def test_cogs_emploie_la_meme_grammaire_que_le_dashboard():
    """⚠️ DEUX GRAMMAIRES VISUELLES DANS UN MÊME OUTIL obligent à réapprendre à chaque page."""
    for etat in ("ok", "attention", "alerte"):
        assert f'.sum-item[data-etat="{etat}"]::before' in COGS


def test_une_marge_negative_alerte_meme_sans_ouvrir_la_liste():
    """Une perte à chaque vente doit trouver le lecteur."""
    i = COGS.index("marquerEtat('i-min'")
    assert "< 0 ? 'alerte'" in COGS[i:i + 200]
