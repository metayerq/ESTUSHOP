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


# ⚠️ LA CHAÎNE A LAISSÉ PLACE À LA COURBE. Ses deux tests — « un seul maillon en avant » et
# « l'addition tombe juste » — n'ont plus d'objet : il n'y a plus de maillons, et la répartition
# est une barre empilée dont les parts somment à 100 % par construction.
#
# ⚠️ CE QU'ILS PROTÉGEAIENT SURVIT AILLEURS. La hiérarchie est tenue par `test_la_reponse_vient
# _avant_tout_le_reste` ; la justesse de la répartition, par le fait qu'elle est calculée à
# partir d'un seul total (`ca_ttc`) plutôt que recomposée à la main.

def test_la_repartition_se_calcule_sur_un_seul_total():
    """
    ⚠️ CINQ PARTS CALCULÉES SUR CINQ DÉNOMINATEURS NE FONT PAS 100 %. La barre empilée promet
    une décomposition ; si les parts ne somment pas au tout, la promesse se casse à l'œil — une
    bande blanche apparaît au bout, ou la dernière déborde.
    """
    i = DASH.index("function renderRepartition(")
    bloc = DASH[i:DASH.index("\nfunction ", i + 10)]
    assert bloc.count("/ ttc * 100") == 2, "les parts ne viennent pas toutes du même total"
    assert "const ttc = eco.ca_ttc;" in bloc


def test_la_bande_detat_suit_les_conteneurs_que_la_fonction_connait():
    """
    ⚠️ `etat()` NE CONNAISSAIT QUE `.kpi-cell`. Appelée depuis le bandeau-réponse, elle ne
    trouvait aucun conteneur et ne faisait RIEN : l'état était calculé puis jeté en silence. La
    fonction a été élargie — la mise en forme doit suivre, sans quoi l'attribut serait posé sans
    que rien ne l'affiche, ce qui est le même défaut à l'envers.
    """
    i = DASH.index("var cel = el && el.closest ? el.closest(")
    selecteurs = re.findall(r"closest\('([^']+)'\)", DASH[i:i + 200])[0]
    for sel in [s.strip() for s in selecteurs.split(",")]:
        assert f'{sel}[data-etat="alerte"]::before' in CSS, f"{sel} n'a pas de bande d'état"
