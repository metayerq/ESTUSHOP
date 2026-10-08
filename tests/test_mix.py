# -*- coding: utf-8 -*-
"""
CE QU'UN PRODUIT RAPPORTE PAR JOUR DE SEMAINE.

⚠️ CE FICHIER GARDE UNE DÉCISION, PAS UN AFFICHAGE. Quentin se demande s'il garde le brunch en
semaine. Un chiffre faux ici lui fait supprimer un produit rentable, ou garder une cuisine qui
lui coûte deux salaires pour rien.
"""
from datetime import date

import mix


def doc(jour, *articles):
    """Un document Vendus détaillé. `articles` : (titre, qty, ht)."""
    return {"date": f"{jour} 10:30:00",
            "items": [{"title": t, "qty": q, "amounts": {"net_total": ht}}
                      for t, q, ht in articles]}


# Septembre 2026 : le 7 est un lundi.
LUNDIS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]
SAMEDIS = ["2026-09-05", "2026-09-12"]


def test_un_produit_est_agrege_par_jour_de_semaine():
    docs = [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0)),
            doc(SAMEDIS[0], ("Sourdough toast", 9, 45.0))]
    r = mix.par_jour_de_semaine(docs, ["sourdough"])
    assert r["par_jour"][0]["produits"]["sourdough"]["qty"] == 2
    assert r["par_jour"][5]["produits"]["sourdough"]["qty"] == 9


def test_LA_MOYENNE_SE_DIVISE_PAR_LES_JOURS_OUVERTS_PAS_PAR_LES_JOURS_VENDUS():
    """
    ⚠️ C'EST LE CŒUR DE LA DÉCISION. Un sourdough vendu deux lundis sur quatre fait une moyenne
    du lundi de la MOITIÉ de ce qu'il fait quand il part. Diviser par deux donnerait la
    performance d'un bon lundi — qui n'est pas la question posée : on décide d'ouvrir la cuisine
    TOUS les lundis, pas seulement ceux où ça se vend.
    """
    docs = [doc(j, ("Café", 1, 2.0)) for j in LUNDIS]          # quatre lundis ouverts
    docs += [doc(LUNDIS[0], ("Sourdough toast", 4, 20.0)),
             doc(LUNDIS[1], ("Sourdough toast", 4, 20.0))]      # vendu deux lundis sur quatre
    r = mix.par_jour_de_semaine(docs, ["sourdough"])
    ligne = r["par_jour"][0]["produits"]["sourdough"]
    assert ligne["qty"] == 8 and ligne["jours_vendu"] == 2
    assert r["par_jour"][0]["jours_ouverts"] == 4
    assert ligne["qty_par_jour"] == 2.0, "la moyenne a été calculée sur les jours de vente"
    assert ligne["rev_ht_par_jour"] == 10.0


def test_UN_JOUR_OUVERT_SANS_LE_PRODUIT_TIRE_LA_MOYENNE_VERS_LE_BAS():
    """Et c'est exactement l'information qu'on vient chercher."""
    docs = [doc(j, ("Café", 1, 2.0)) for j in LUNDIS]
    docs += [doc(LUNDIS[0], ("Sourdough toast", 4, 20.0))]
    assert r_(docs)["qty_par_jour"] == 1.0


def r_(docs, terme="sourdough", wd=0):
    return mix.par_jour_de_semaine(docs, [terme])["par_jour"][wd]["produits"][terme]


def test_UN_JOUR_OU_LE_CAFE_NA_JAMAIS_OUVERT_REND_NONE_PAS_ZERO():
    """
    ⚠️ « 0 € le mardi » SE LIRAIT « ÇA NE SE VEND PAS LE MARDI » — alors que le café est fermé.
    C'est la confusion qui ferait supprimer un produit sur une absence de données.
    """
    docs = [doc(j, ("Sourdough toast", 3, 15.0)) for j in LUNDIS]
    r = mix.par_jour_de_semaine(docs, ["sourdough"])
    assert r["par_jour"][1]["jours_ouverts"] == 0
    assert r["par_jour"][1]["produits"]["sourdough"]["qty_par_jour"] is None


def test_LES_TITRES_TROUVES_SONT_RENDUS():
    """
    ⚠️ UNE RECHERCHE QUI NE TROUVE RIEN REND DES ZÉROS, ET DES ZÉROS SE LISENT « ça ne se vend
    pas » — la réponse exactement inverse de la vérité. On doit pouvoir vérifier d'un coup d'œil
    ce que la recherche a attrapé.
    """
    docs = [doc(LUNDIS[0], ("Bowl granola maison", 2, 12.0), ("Granola à emporter", 1, 6.0))]
    r = mix.par_jour_de_semaine(docs, ["granola"])
    assert r["correspondances"]["granola"] == ["Bowl granola maison", "Granola à emporter"]


def test_une_recherche_sans_resultat_le_dit_par_une_liste_vide():
    docs = [doc(LUNDIS[0], ("Café", 1, 2.0))]
    r = mix.par_jour_de_semaine(docs, ["sourdough"])
    assert r["correspondances"]["sourdough"] == []
    assert r["par_jour"][0]["produits"]["sourdough"]["qty"] == 0


def test_la_recherche_ignore_la_casse_et_les_accents():
    docs = [doc(LUNDIS[0], ("CRÈME brûlée", 1, 6.0))]
    r = mix.par_jour_de_semaine(docs, ["creme"])
    assert r["correspondances"]["creme"] == ["CRÈME brûlée"]


def test_deux_termes_se_comptent_separement():
    docs = [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0), ("Bowl granola", 3, 18.0))]
    r = mix.par_jour_de_semaine(docs, ["sourdough", "granola"])
    assert r["par_jour"][0]["produits"]["sourdough"]["rev_ht"] == 10.0
    assert r["par_jour"][0]["produits"]["granola"]["rev_ht"] == 18.0


def test_un_document_sans_date_lisible_ne_fait_rien_tomber():
    docs = [{"date": None, "items": [{"title": "Sourdough", "qty": 1, "amounts": {}}]},
            doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))]
    assert r_(docs)["qty"] == 2


def test_un_article_abime_ne_fait_pas_tomber_le_calcul():
    docs = [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0)),
            {"date": LUNDIS[1], "items": [{"title": "Sourdough", "qty": "n/a"}]}]
    assert r_(docs)["qty"] == 2


def test_LES_QUANTITES_SONT_GARDEES_PAR_TITRE():
    """
    ⚠️ UN TERME PEUT ATTRAPER DEUX ARTICLES AUX RECETTES DIFFÉRENTES. « granola » trouve le bol
    à 180 g et le sachet à emporter à 60 g : appliquer un coût de revient à la somme des deux
    serait faux de tout l'écart entre eux. Le coût se calcule titre par titre.
    """
    docs = [doc(LUNDIS[0], ("Bowl granola", 3, 18.0), ("Granola à emporter", 5, 15.0))]
    ligne = mix.par_jour_de_semaine(docs, ["granola"])["par_jour"][0]["produits"]["granola"]
    assert ligne["par_titre"] == {"Bowl granola": 3.0, "Granola à emporter": 5.0}
    assert ligne["qty"] == 8.0, "le total reste la somme des deux"


def test_un_jour_sans_vente_na_aucun_titre():
    docs = [doc(j, ("Café", 1, 2.0)) for j in LUNDIS]
    assert r_(docs)["par_titre"] == {}
