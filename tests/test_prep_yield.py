"""
La quantité d'une ligne de recette et le rendement d'une préparation ne sont pas dans la même
unité — et personne ne convertissait.

Une recette qui consomme « 200 ml » d'un sirop dont la préparation rend « 1 l » divisait 200
par 1 : 200 batches au lieu de 0,2. Facteur 1000, sur le COÛT affiché.

Trois endroits divisaient par un rendement, tous les trois sans conversion : le moteur de coût
(calc_recipe_cogs), la consommation théorique (/api/inventory/usage) et l'aperçu d'impact prix
côté client. Ils étaient donc cohérents entre eux — et faux ensemble, ce qui est la raison pour
laquelle rien ne le signalait.

UNIT_CONVERSIONS ne pouvait pas servir : elle ne ramène une ligne que vers l'unité de RÉFÉRENCE
d'un ingrédient (kg / l / unit). Elle ne connaît ni ml→ml, ni g→g, et ne dit rien de « combien
de 1 l valent 200 ml ». D'où _UNIT_BASE, qui raisonne en dimensions.
"""
import sys
sys.path.insert(0, ".")

import app


# ── Le facteur lui-même ───────────────────────────────────────────────────────

def test_meme_unite_facteur_neutre():
    assert app.prep_yield_factor("ml", "ml") == (1.0, None)
    assert app.prep_yield_factor("portion", "portion") == (1.0, None)


def test_le_cas_qui_coutait_un_facteur_mille():
    f, warn = app.prep_yield_factor("ml", "l")
    assert f == 0.001 and warn is None


def test_conversion_de_masse_dans_les_deux_sens():
    assert app.prep_yield_factor("g", "kg")[0] == 0.001
    assert app.prep_yield_factor("kg", "g")[0] == 1000.0


def test_unite_et_portion_comptent_pareil():
    """Une préparation qui rend « 10 portions », consommée « à l'unité » : 1 pour 1."""
    assert app.prep_yield_factor("unit", "portion") == (1.0, None)


def test_deux_unites_inconnues_ne_sont_pas_de_meme_dimension():
    """
    Le piège exact rencontré dans Mesa : la comparaison de dimensions trouvait
    `undefined == undefined`, concluait « même dimension », et produisait des NaN qui se sont
    affichés comme coûts sur des recettes réelles. Ici, deux inconnues ne se comparent pas.
    """
    f, warn = app.prep_yield_factor("bidule", "machin")
    assert f == 1.0
    assert warn is not None


def test_dimensions_incompatibles_ne_sont_pas_devinees():
    """
    « portion » face à « ml » : on ne sait pas. Le comportement historique (facteur 1) est
    CONSERVÉ — corriger au jugé ferait bouger des coûts que personne n'a demandé à voir bouger —
    mais il est signalé, sans quoi le nombre passerait pour exact.
    """
    f, warn = app.prep_yield_factor("ml", "portion")
    assert f == 1.0
    assert warn and "inconnue" in warn


# ── Le coût qui en découle ────────────────────────────────────────────────────

_INGR = {"Sucre": {"unit_ref": "kg", "price": 2.0}}          # 2 €/kg
_PREP = {"Sirop": {"ingredients": [{"name": "Sucre", "qty": 500, "unit": "g"}],
                   "yield_qty": 1, "yield_unit": "l"}}        # 1 l coûte 1,00 €


def test_le_cout_d_une_prep_suit_l_unite_de_la_ligne():
    """200 ml d'un sirop à 1,00 €/l valent 0,20 € — pas 200 €."""
    total, bd = app.calc_recipe_cogs(
        [{"name": "Sirop", "qty": 200, "unit": "ml"}], _INGR, prep_lib=_PREP)
    assert total == 0.2, f"200 ml de sirop facturés {total} €"
    assert bd[0]["yield_factor"] == 0.001
    assert "warning" not in bd[0]


def test_une_ligne_dans_l_unite_du_rendement_est_inchangee():
    """Garde-fou de non-régression : le cas déjà correct doit le rester au centime."""
    total, _ = app.calc_recipe_cogs(
        [{"name": "Sirop", "qty": 2, "unit": "l"}], _INGR, prep_lib=_PREP)
    assert total == 2.0


def test_le_chemin_par_lequel_l_ecart_arrive_vraiment():
    """
    L'éditeur FORCE l'unité d'une ligne « préparation » à celle du rendement (ing-unit-fixed,
    pas de menu déroulant) : dans le cours normal des choses les deux coïncident et le défaut
    ne se déclenche pas. Il est LATENT, pas actif.

    Il devient atteignable ici : la préparation passe d'un rendement en litres à un rendement
    en millilitres. Les lignes de recette DÉJÀ enregistrées gardent « l » en base — rien ne les
    réécrit. Sans conversion, chacune coûterait 1000 fois son prix, sans un mot à l'écran.
    """
    prep_ml = {"Sirop": {"ingredients": [{"name": "Sucre", "qty": 500, "unit": "g"}],
                         "yield_qty": 1000, "yield_unit": "ml"}}   # même batch, autre libellé
    ligne_ancienne = [{"name": "Sirop", "qty": 0.2, "unit": "l"}]  # 200 ml, unité d'avant

    total, bd = app.calc_recipe_cogs(ligne_ancienne, _INGR, prep_lib=prep_ml)
    assert total == 0.2, f"la ligne héritée coûte {total} € au lieu de 0,20 €"
    assert bd[0]["yield_factor"] == 1000.0


def test_une_unite_non_convertible_est_signalee_dans_le_breakdown():
    total, bd = app.calc_recipe_cogs(
        [{"name": "Sirop", "qty": 3, "unit": "portion"}], _INGR, prep_lib=_PREP)
    assert total == 3.0, "comportement historique conservé"
    assert bd[0].get("warning"), "…mais visible"
