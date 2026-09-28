"""
LA VARIANCE — L'ÉCART ENTRE CE QUI A ÉTÉ CONSOMMÉ ET CE QUI AURAIT DÛ L'ÊTRE.

⚠️ CE MODULE DOIT RESTER LE MIROIR DE `calc_recipe_cogs`. Si les deux divergent, le COGS et la
variance diront deux choses différentes de la même recette, et rien ne permettra de trancher.
"""

import pytest

from variance import quantites_recette, consommation_theorique, variance


INGR = {
    "Farinha T55": {"price": 0.736, "unit_ref": "kg"},
    "Leite":       {"price": 0.89,  "unit_ref": "l"},
    "Ovos":        {"price": 0.16,  "unit_ref": "unit"},
}


def test_une_recette_simple_se_convertit_dans_l_unite_de_reference():
    q, avert = quantites_recette(
        [{"name": "Farinha T55", "qty": 500, "unit": "g"}], INGR)
    assert q == {"Farinha T55": 0.5}       # 500 g = 0,5 kg
    assert avert == []


def test_les_millilitres_deviennent_des_litres():
    q, _ = quantites_recette([{"name": "Leite", "qty": 250, "unit": "ml"}], INGR)
    assert q["Leite"] == pytest.approx(0.25)


def test_une_conversion_inconnue_remonte_au_lieu_de_disparaitre():
    """
    ⚠️ UNE LIGNE IGNORÉE EN SILENCE SOUS-ESTIME LE THÉORIQUE, donc GONFLE la variance : elle
    accuse la cuisine d'un gaspillage qui n'existe pas.
    """
    q, avert = quantites_recette(
        [{"name": "Farinha T55", "qty": 2, "unit": "cuillère"}], INGR)
    assert q == {}
    assert any("conversion" in a for a in avert)


def test_un_ingredient_inconnu_remonte_aussi():
    q, avert = quantites_recette([{"name": "Zzz", "qty": 1, "unit": "g"}], INGR)
    assert q == {}
    assert any("ni ingrédient ni préparation" in a for a in avert)


def test_une_preparation_applique_son_rendement():
    """
    ⚠️ LE FACTEUR 1000 QUI A DÉJÀ PIÉGÉ LE MOTEUR DE COÛT. Une ligne de 200 ml d'une préparation
    qui rend 1 l vaut 0,2 lot — pas 200.
    """
    prep = {"Calda": {"ingredients": [{"name": "Leite", "qty": 1, "unit": "l"}],
                      "yield_qty": 1, "yield_unit": "l"}}
    q, avert = quantites_recette([{"name": "Calda", "qty": 200, "unit": "ml"}], INGR, prep)
    assert q["Leite"] == pytest.approx(0.2)


def test_la_consommation_theorique_multiplie_par_les_ventes():
    recipes = {"Croissant": {"ingredients": [{"name": "Farinha T55", "qty": 100, "unit": "g"}]}}
    conso, sans, _ = consommation_theorique({"Croissant": 30}, recipes, INGR)
    assert conso["Farinha T55"] == pytest.approx(3.0)      # 30 × 100 g = 3 kg
    assert sans == []


def test_les_produits_sans_recette_sont_rendus_a_part():
    """
    ⚠️ LES IGNORER FERAIT PASSER LEUR CONSOMMATION POUR DU GASPILLAGE. Il faut pouvoir dire
    « la variance ne couvre qu'une partie des ventes » plutôt qu'accuser à tort.
    """
    conso, sans, _ = consommation_theorique({"Café": 100}, {}, INGR)
    assert conso == {}
    assert sans == ["Café"]


def test_la_variance_est_reelle_moins_theorique():
    v = variance({"Farinha T55": 3.6}, {"Farinha T55": 3.0})
    assert v[0]["ecart"] == pytest.approx(0.6)
    assert v[0]["ecart_pct"] == pytest.approx(20.0)


def test_un_ingredient_sans_theorique_garde_son_ecart_sans_pourcentage():
    """Diviser par zéro donnerait un infini ; l'écart brut reste lisible."""
    v = variance({"Ovos": 12}, {})
    assert v[0]["ecart"] == 12
    assert v[0]["ecart_pct"] is None


def test_on_ne_compare_que_ce_qui_a_ete_compte():
    """
    ⚠️ UN INGRÉDIENT THÉORIQUEMENT CONSOMMÉ MAIS ABSENT DES COMPTAGES n'a pas de réel à lui
    opposer ; l'afficher ferait croire à un stock qui se remplit tout seul.
    """
    v = variance({"Leite": 2.0}, {"Leite": 1.5, "Farinha T55": 40})
    assert [x["ingredient"] for x in v] == ["Leite"]


def test_le_classement_met_les_plus_gros_ecarts_en_tete():
    v = variance({"A": 10, "B": 1.2}, {"A": 9.9, "B": 0.2})
    assert [x["ingredient"] for x in v] == ["B", "A"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# VALORISER — parce qu'un pourcentage sur deux jours ment par construction.
# ══════════════════════════════════════════════════════════════════════════════════════════

from variance import valoriser, marge_reelle

LIB = {
    "Café":    {"price": 18.0, "unit_ref": "kg"},   # 18 €/kg
    "Lait":    {"price": 0.90, "unit_ref": "l"},    # 0,90 €/l
    "Persil":  {"price": 4.0,  "unit_ref": "kg"},
    "Sel":     {"price": None, "unit_ref": "kg"},   # prix inconnu
}


def _ligne(nom, reelle, theorique):
    ecart = reelle - theorique
    return {"ingredient": nom, "reelle": reelle, "theorique": theorique,
            "ecart": round(ecart, 4),
            "ecart_pct": round(ecart / theorique * 100, 1) if theorique else None}


def test_le_cout_de_l_ecart_est_la_quantite_fois_le_prix():
    lignes, totaux = valoriser([_ligne("Café", 5.5, 5.0)], {"Café": 5.0}, LIB)
    assert lignes[0]["cout_ecart"] == 9.0          # 0,5 kg × 18 €
    assert lignes[0]["cout_theorique"] == 90.0     # 5 kg × 18 €
    assert totaux["cout_ecart"] == 9.0


def test_le_classement_passe_en_euros_pas_en_quantite():
    """
    ⚠️ LE DÉFAUT QUE ÇA FERME. Trié en quantité, le persil (+0,1 kg = 40 centimes) passait
    AVANT le café (+0,05 kg = 90 centimes) dès que la quantité était plus grande — et pire,
    on comparait des kilos à des litres et à des unités, qui n'ont aucun rapport entre eux.
    """
    lignes, _ = valoriser(
        [_ligne("Persil", 1.1, 1.0), _ligne("Café", 5.05, 5.0)],
        {"Persil": 1.0, "Café": 5.0}, LIB)
    assert [l["ingredient"] for l in lignes] == ["Café", "Persil"]
    assert lignes[0]["cout_ecart"] == 0.9
    assert lignes[1]["cout_ecart"] == 0.4


def test_un_prix_inconnu_ne_vaut_pas_zero():
    """« Gratuit » et « on ne sait pas » sont deux faits opposés."""
    lignes, totaux = valoriser([_ligne("Sel", 2.0, 1.0)], {"Sel": 1.0}, LIB)
    assert lignes[0]["cout_ecart"] is None
    assert totaux["cout_ecart"] == 0.0
    assert totaux["sans_prix"] == ["Sel"]


def test_la_couverture_dit_quelle_part_du_cogs_a_ete_mesuree():
    """
    ⚠️ LE CHIFFRE SANS LEQUEL LE COGS RÉEL EST UN MENSONGE. On ne compte pas tout : l'écart
    n'existe que sur ce qui a été compté DEUX fois. Le COGS réel est donc un plancher, et la
    couverture dit de combien.
    """
    # Théorique : 90 € de café + 9 € de lait = 99 €. Seul le café a été compté.
    _, totaux = valoriser([_ligne("Café", 5.5, 5.0)], {"Café": 5.0, "Lait": 10.0}, LIB)
    assert totaux["cogs_theorique"] == 99.0
    assert totaux["cogs_theorique_couvert"] == 90.0
    assert totaux["couverture_pct"] == 90.9
    # Le réel s'appuie sur le théorique ENTIER, augmenté du seul écart mesuré.
    assert totaux["cogs_reel"] == 108.0


def test_la_marge_reelle_se_compare_a_la_theorique():
    _, totaux = valoriser([_ligne("Café", 5.5, 5.0)], {"Café": 5.0}, LIB)
    m = marge_reelle(300.0, totaux)
    assert m["marge_theorique_pct"] == 70.0   # (300 − 90) / 300
    assert m["marge_reelle_pct"] == 67.0      # (300 − 99) / 300
    assert m["perte_pct_ca"] == 3.0           # 9 € sur 300 €


def test_sans_chiffre_d_affaires_on_n_invente_pas_de_marge():
    _, totaux = valoriser([_ligne("Café", 5.5, 5.0)], {"Café": 5.0}, LIB)
    for ca in (0, None, -5):
        m = marge_reelle(ca, totaux)
        assert m["marge_reelle_pct"] is None


def test_un_ecart_negatif_ameliore_le_cogs_reel():
    """Consommer MOINS que les recettes : le signe doit traverser jusqu'aux euros."""
    _, totaux = valoriser([_ligne("Café", 4.5, 5.0)], {"Café": 5.0}, LIB)
    assert totaux["cout_ecart"] == -9.0
    assert totaux["cogs_reel"] == 81.0
