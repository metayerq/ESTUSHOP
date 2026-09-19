"""
LA NORMALISATION DES NUMÉROS, VÉRIFIÉE CONTRE CELLE DU COMPTOIR.

⚠️ `phone` EST LA CLÉ PRIMAIRE DE `card_customers`. Si Mesa range « 0912345678 » en
`+351912345678` et qu'ESTUSHOP le range en `+3510912345678`, la même personne obtient DEUX
comptes : deux soldes, dont un invisible, et un client qui ne comprendra jamais où sont passés
ses points. Ce n'est pas une divergence cosmétique, c'est une clé qui se dédouble.

Les vecteurs sont produits par l'implémentation TypeScript, dans le même fichier figé que le
barème — donc protégés par la même empreinte.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phone import mask_phone, normalise_phone  # noqa: E402

VECTEURS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors", "loyalty_state.json")

with open(VECTEURS, encoding="utf-8") as f:
    CAS = json.load(f)["phones"]


def test_le_jeu_couvre_les_formes_reelles_et_les_refus():
    """Un jeu qui ne contiendrait que des numéros valides ne protégerait que la moitié du chemin."""
    assert len(CAS) >= 15
    assert sum(1 for c in CAS if c["ok"]) >= 8
    assert sum(1 for c in CAS if not c["ok"]) >= 5


@pytest.mark.parametrize("cas", [pytest.param(c, id=repr(c["brut"])) for c in CAS])
def test_le_numero_est_range_comme_au_comptoir(cas):
    ok, valeur = normalise_phone(cas["brut"])
    assert ok is cas["ok"], f"{cas['brut']!r} : accepté d'un côté, refusé de l'autre"
    assert valeur == (cas["e164"] if cas["ok"] else cas["reason"])


def test_le_masque_ne_laisse_que_quatre_chiffres():
    assert mask_phone("+351912345678") == "••• 5678"
    assert mask_phone(None) == "•••"
    assert mask_phone("12") == "•••"
