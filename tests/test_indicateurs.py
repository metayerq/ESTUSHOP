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

def test_les_quatre_cartes_portent_chacune_une_seule_mesure():
    """
    ⚠️ LA BARRE EMPILÉE « OÙ VA L'ARGENT » A ÉTÉ RETIRÉE : elle décomposait ce que le prime cost
    et le résultat disent déjà. Ce qui la remplace n'a pas de somme à faire tomber juste — chaque
    carte porte UNE mesure, avec sa propre absence.
    """
    i = DASH.index("function renderQuatre(")
    bloc = DASH[i:DASH.index("\nfunction ", i + 10)]
    for ancre in ("db-wd-v", "db-tva", "db-panier", "db-couv"):
        assert f"E('{ancre}')" in bloc, ancre


# ⚠️ `etat()` EST PARTIE, ET SON TEST AVEC ELLE. La fonction visait `.kpi-cell`, `.tx-answer`
# et `.maillon` — trois classes qu'aucune page ne porte plus. Cinq appels calculaient un état
# puis ne faisaient rien : exactement le défaut que son propre commentaire décrivait.
#
# ⚠️ CE QU'ELLE PORTAIT SURVIT DANS `.db-badge`. La charte le dit : la pastille porte l'état, le
# chiffre reste en encre — et la pastille est posée à côté de chaque valeur.
