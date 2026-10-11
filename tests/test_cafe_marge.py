# -*- coding: utf-8 -*-
"""
LA MARGE AU GRAIN RÉELLEMENT SERVI.

⚠️ CE FICHIER GARDE UN CHIFFRE QUI SERT À DÉCIDER D'UN ACHAT. Un grain qui paraît rentable
parce qu'on l'a valorisé au prix d'un autre fait racheter le mauvais lot.
"""
import cafe_marge as cm

INGR = {
    "Guji Ethiopia": {"price": 24.5, "unit": "kg", "category": "Café"},
    "Brasil Santos": {"price": 18.0, "unit": "kg", "category": "cafe"},
    "Lait entier": {"price": 1.1, "unit": "l", "category": "Frais"},
}


def conso(par_produit):
    """Un faux déplieur de recettes : 0,018 kg de café et 0,15 l de lait par unité."""
    def _c(ventes):
        q = {}
        for titre, n in (ventes or {}).items():
            for nom, par_unite in par_produit.get(titre, {}).items():
                q[nom] = q.get(nom, 0.0) + par_unite * float(n)
        return q
    return _c


RECETTES = {
    "Espresso": {"Guji Ethiopia": 0.018},
    "Flat white": {"Guji Ethiopia": 0.018, "Lait entier": 0.15},
    "V60": {"Guji Ethiopia": 0.015},
    "Batch brew": {"Guji Ethiopia": 0.012},
    "Croissant": {},
}


# ── Rattacher une vente à une méthode ───────────────────────────────────────────────────────

def test_les_boissons_espresso_sont_rattachees():
    for t in ("Espresso", "Flat white", "Cappuccino", "Cortado", "Americano"):
        assert cm.methode_du_produit(t) == "espresso", t


def test_le_v60_et_le_batch_ont_leur_methode():
    assert cm.methode_du_produit("V60 Ethiopia") == "v60"
    assert cm.methode_du_produit("Batch brew") == "batch"
    assert cm.methode_du_produit("Café filtre") == "batch"


def test_la_casse_et_les_accents_nempechent_pas_le_rattachement():
    assert cm.methode_du_produit("CAFÉ FILTRE") == "batch"
    assert cm.methode_du_produit("Pour Over") == "v60"


def test_UN_PRODUIT_QUE_RIEN_NE_NOMME_EST_RENDU_A_PART():
    """
    ⚠️ IL N'EST PAS IGNORÉ. Un produit café oublié verrait son grain facturé au prix courant de
    l'ingrédient au lieu de celui du jour — un écart petit, permanent, et invisible.
    """
    _, hors = cm.repartir({"Espresso": 10, "Croissant": 4, "Thé vert": 2})
    assert hors == {"Croissant": 4, "Thé vert": 2}


# ── Le coût du grain ────────────────────────────────────────────────────────────────────────

def test_LE_PRIX_DU_JOUR_REMPLACE_LE_PRIX_COURANT():
    """18 g × 24,50 €/kg le jour, contre le prix de référence de l'ingrédient."""
    au_jour, au_courant, grains = cm.cout_du_grain({"Guji Ethiopia": 0.18}, INGR, 31.0)
    assert au_jour == round(0.18 * 31.0, 4)
    assert au_courant == round(0.18 * 24.5, 4)
    assert grains == {"Guji Ethiopia": 0.18}


def test_SANS_PRIX_DU_JOUR_LE_COUT_EST_INCONNU_PAS_NUL():
    """⚠️ Zéro se lirait « le café n'a rien coûté » — et la marge paraîtrait excellente."""
    au_jour, au_courant, _ = cm.cout_du_grain({"Guji Ethiopia": 0.18}, INGR, None)
    assert au_jour is None
    assert au_courant > 0


def test_seuls_les_ingredients_categorises_cafe_comptent():
    """Le lait d'un flat white n'est pas du café, et ne doit pas être revalorisé au grain."""
    _, _, grains = cm.cout_du_grain({"Guji Ethiopia": 0.18, "Lait entier": 1.5}, INGR, 31.0)
    assert grains == {"Guji Ethiopia": 0.18}


def test_une_consommation_sans_cafe_ne_rend_aucun_cout():
    au_jour, au_courant, grains = cm.cout_du_grain({"Lait entier": 1.5}, INGR, 31.0)
    assert au_jour is None and au_courant == 0.0 and grains == {}


# ── La journée ──────────────────────────────────────────────────────────────────────────────

CHOIX = {
    "espresso": {"ingredient": "Guji Ethiopia", "prix": 31.0},
    "v60": {"ingredient": "Brasil Santos", "prix": 18.0},
}


def test_CHAQUE_METHODE_EST_VALORISEE_A_SON_PROPRE_GRAIN():
    """
    ⚠️ C'EST TOUTE LA RAISON D'ÊTRE DE CET ÉCRAN. Trois grains servis le même jour : les
    valoriser au même prix reviendrait à n'avoir rien demandé au barista.
    """
    r = cm.journee({"Espresso": 100, "V60": 10}, CHOIX, conso(RECETTES), INGR)
    esp = r["methodes"]["espresso"]
    v60 = r["methodes"]["v60"]
    assert esp["cout_au_jour"] == round(100 * 0.018 * 31.0, 4)
    assert v60["cout_au_jour"] == round(10 * 0.015 * 18.0, 4)


def test_LECART_DIT_CE_QUE_LE_GRAIN_DU_JOUR_COUTE_DE_PLUS():
    """C'est le chiffre qui sert à décider d'un achat."""
    r = cm.journee({"Espresso": 100}, CHOIX, conso(RECETTES), INGR)
    esp = r["methodes"]["espresso"]
    assert esp["ecart"] == round(100 * 0.018 * (31.0 - 24.5), 4)
    assert esp["ecart"] > 0


def test_une_methode_sans_choix_du_jour_na_pas_de_cout_au_jour():
    r = cm.journee({"Batch brew": 20}, CHOIX, conso(RECETTES), INGR)
    batch = r["methodes"]["batch"]
    assert batch["grain"] is None
    assert batch["cout_au_jour"] is None
    assert batch["cout_au_prix_courant"] > 0, "le prix de référence reste calculable"


def test_une_methode_sans_vente_ne_coute_rien_et_ne_leve_pas():
    r = cm.journee({"Espresso": 5}, CHOIX, conso(RECETTES), INGR)
    assert r["methodes"]["v60"]["unites"] == 0
    assert r["methodes"]["v60"]["cout_au_jour"] is None


def test_LE_LAIT_DUN_FLAT_WHITE_NE_SUIT_PAS_LE_GRAIN():
    """Il entre dans la recette, pas dans la revalorisation au café du jour."""
    r = cm.journee({"Flat white": 10}, CHOIX, conso(RECETTES), INGR)
    assert r["methodes"]["espresso"]["grammes"] == {"Guji Ethiopia": round(10 * 0.018, 4)}


def test_les_produits_hors_methode_sont_nommes():
    r = cm.journee({"Espresso": 5, "Croissant": 3}, CHOIX, conso(RECETTES), INGR)
    assert r["hors_methode"] == ["Croissant"]


def test_les_produits_rattaches_sont_nommes_pour_pouvoir_les_verifier():
    """⚠️ Un « cortado » tombé dans le mauvais panier déplace une marge sans rien signaler."""
    r = cm.journee({"Espresso": 5, "Flat white": 2}, CHOIX, conso(RECETTES), INGR)
    assert r["methodes"]["espresso"]["produits"] == ["Espresso", "Flat white"]
