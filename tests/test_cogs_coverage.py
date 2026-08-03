"""
Le seuil de couverture COGS à 95 % — et le drapeau que personne ne lisait.

La marge brute n'est pas mesurée sur tout le CA. Elle est mesurée sur la part des ventes dont
on connaît le coût d'achat (`covered_ht`), puis appliquée au reste. Tant que la couverture est
quasi totale, l'extrapolation est sans conséquence. En dessous d'un seuil, elle devient une
hypothèse — et le moteur la marque : `marge_is_estimated` (vendus.py:769).

CE QUI A ÉTÉ TROUVÉ EN PORTANT LA RÈGLE DEPUIS MESA : le drapeau était calculé, renvoyé dans
la réponse, et lu par AUCUN écran. Le front décidait de son côté un second palier (vert ≥ 90 %,
ambre ≥ 60 %). À 92 % de couverture, l'écran affichait donc du vert sur un chiffre que le
moteur tenait pour estimé. Les deux seuils sont désormais un seul, celui du moteur.

Mesuré sur les ventes réelles du 27 juillet au 2 août : couverture 100 % (90 des 97 produits
actifs ont un supply_price). Le drapeau est donc à false aujourd'hui — ces tests gardent une
porte, ils ne corrigent pas un chiffre affiché.
"""
import sys
sys.path.insert(0, ".")

import pytest
import vendus


@pytest.fixture(autouse=True)
def _pas_de_reseau(monkeypatch):
    """Les charges viennent de Supabase ; sans elles le calcul de marge tourne quand même."""
    monkeypatch.setattr(vendus, "_supa_get_economics", lambda *a, **k: [])


def _docs(lignes):
    """Un document, une ligne par (titre, qty, net_ht)."""
    net = sum(l[2] for l in lignes)
    return [{
        "type": "FT", "amount_net": net, "amount_gross": net * 1.13,
        "items": [{"title": t, "qty": q, "amounts": {"net_total": n}} for t, q, n in lignes],
    }]


def _eco(lignes, catalog):
    return vendus.daily_economics(_docs(lignes), catalog, n_days=1)


def test_couverture_totale_la_marge_n_est_pas_marquee():
    eco = _eco([("Café", 10, 100.0)], {"Café": {"cost": 3.0}})
    assert eco["cogs_coverage_pct"] == 100.0
    assert eco["marge_is_estimated"] is False


def test_sous_95_la_marge_est_marquee_comme_extrapolee():
    """94 € couverts sur 100 € vendus : le taux vient de 94 %, il est appliqué aux 100 %."""
    eco = _eco([("Café", 10, 94.0), ("Livre", 1, 6.0)], {"Café": {"cost": 30.0}})
    assert eco["cogs_coverage_pct"] == 94.0
    assert eco["marge_is_estimated"] is True


def test_le_seuil_est_inclusif_a_95():
    """
    À 95 % exactement, le moteur NE marque PAS (`< 95`). Le test fixe la borne : la déplacer
    d'un cran change ce que l'écran affirme, et ce genre de glissement passe inaperçu.
    """
    eco = _eco([("Café", 10, 95.0), ("Livre", 1, 5.0)], {"Café": {"cost": 30.0}})
    assert eco["cogs_coverage_pct"] == 95.0
    assert eco["marge_is_estimated"] is False


def test_sans_aucun_cout_connu_la_marge_est_absente_pas_nulle():
    """
    Aucun produit chiffré : on ne sait pas. Un 0 se lirait « aucune marge », c'est-à-dire une
    information — alors qu'il n'y en a aucune. Et un seuil de rentabilité ne peut pas se
    calculer sur un taux qui n'existe pas.
    """
    eco = _eco([("Livre", 1, 100.0)], {})
    assert eco["marge_brute_ht"] is None
    assert eco["seuil_ca_ttc"] is None
    assert eco["marge_is_estimated"] is False, \
        "rien n'est extrapolé quand rien n'est calculé — le drapeau qualifie un chiffre affiché"
