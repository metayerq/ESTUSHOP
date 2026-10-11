# -*- coding: utf-8 -*-
"""
LA ROUTE QUI CHIFFRE LE CAFÉ AU GRAIN DU JOUR.

⚠️ ELLE EXISTE PARCE QU'UNE ROUTE QUE RIEN N'APPELLE PLANTE LE JOUR OÙ QUELQU'UN L'OUVRE — et
ce jour-là, c'est au moment de décider d'un achat de grain.
"""
import pytest

import app as flask_app


def doc(jour, *articles):
    return {"date": f"{jour} 10:00:00",
            "items": [{"title": t, "qty": q, "amounts": {"net_total": ht}}
                      for t, q, ht in articles]}


RECETTES = {"Espresso": {"ingredients": [{"name": "Guji", "qty": 18, "unit": "g"}],
                         "waste_pct": 0, "notes": "", "partner": "", "commission_pct": None},
            "V60": {"ingredients": [{"name": "Brasil", "qty": 15, "unit": "g"}],
                    "waste_pct": 0, "notes": "", "partner": "", "commission_pct": None}}
# ⚠️ `unit_ref`, PAS `unit`. C'est la colonne que `quantites_recette` lit pour convertir les
# grammes d'une recette, et celle à laquelle `price` se rapporte. Mon premier bouchon portait
# `unit` : la recette ne se dépliait pas, les coûts sortaient à zéro, et j'ai cru à un défaut
# du calcul. Un bouchon qui ne ressemble pas à la base ment sur ce qu'il éprouve.
INGR = {"Guji": {"price": 24.5, "unit_ref": "kg", "category": "Café"},
        "Brasil": {"price": 18.0, "unit_ref": "kg", "category": "Café"}}


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_load_recipes", lambda: dict(RECETTES))
    monkeypatch.setattr(flask_app, "_load_ingredients", lambda: dict(INGR))
    monkeypatch.setattr(flask_app, "_load_preparations", lambda: [])
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def servir(monkeypatch, docs, choix=()):
    import vendus
    monkeypatch.setattr(vendus, "get_documents_with_items", lambda a, b:
                        [d for d in docs if str(d["date"])[:10] == a])
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p=None: list(choix) if t == "cafe_du_jour" else [])


def appel(c, debut="2026-10-12", fin="2026-10-12"):
    return c.get(f"/api/marge-cafe?debut={debut}&fin={fin}")


CHOIX_GUJI = {"jour": "2026-10-12", "methode": "espresso",
              "ingredient": "Guji", "prix": 31.0}


def test_LA_ROUTE_REPOND_VRAIMENT(admin, monkeypatch):
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 10, 20.0))], [CHOIX_GUJI])
    r = appel(admin)
    assert r.status_code == 200 and r.mimetype == "text/plain"


def test_LE_PRIX_FIGE_EST_EMPLOYE_PAS_LE_PRIX_COURANT(admin, monkeypatch):
    """
    ⚠️ LE CŒUR DE LA FONCTION. Dix espressos à 18 g font 0,18 kg : 5,58 € au grain du jour
    (31 €/kg) contre 4,41 € au prix de référence (24,50 €/kg). Si la route lisait le prix
    courant, les deux colonnes seraient identiques et tout l'écran serait décoratif.
    """
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 10, 20.0))], [CHOIX_GUJI])
    t = appel(admin).get_data(as_text=True)
    ligne = [l for l in t.splitlines() if l.startswith("espresso")][0]
    assert "5.58" in ligne and "4.41" in ligne
    assert "1.17" in ligne, "l'écart n'est pas affiché"


def test_UN_JOUR_SANS_GRAIN_POSE_NEST_PAS_UN_JOUR_A_ZERO(admin, monkeypatch):
    """
    ⚠️ SINON LE TOTAL PARAÎT COMPLET alors qu'il lui manque des journées — et on décide d'un
    achat sur une somme amputée.
    """
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 10, 20.0))], [])
    t = appel(admin).get_data(as_text=True)
    ligne = [l for l in t.splitlines() if l.startswith("espresso")][0]
    assert "?" in ligne, "l'écart est affirmé alors qu'une journée n'a pas de grain"
    assert ligne.rstrip().endswith("1"), "le nombre de jours sans grain n'est pas dit"


def test_chaque_methode_est_valorisee_a_son_propre_grain(admin, monkeypatch):
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 10, 20.0), ("V60", 4, 16.0))],
           [CHOIX_GUJI, {"jour": "2026-10-12", "methode": "v60",
                         "ingredient": "Brasil", "prix": 18.0}])
    t = appel(admin).get_data(as_text=True)
    assert "1.08" in [l for l in t.splitlines() if l.startswith("v60")][0]


def test_LES_PRODUITS_NON_RATTACHES_SONT_NOMMES(admin, monkeypatch):
    """⚠️ S'il y a du café parmi eux, son grain est compté au prix de référence sans le dire."""
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 1, 2.0), ("Croissant", 3, 6.0))],
           [CHOIX_GUJI])
    t = appel(admin).get_data(as_text=True)
    assert "Croissant" in t and "aucun mot ne rattache" in t


def test_une_methode_sans_vente_le_dit(admin, monkeypatch):
    servir(monkeypatch, [doc("2026-10-12", ("Espresso", 1, 2.0))], [CHOIX_GUJI])
    t = appel(admin).get_data(as_text=True)
    assert "aucune vente rattachée" in [l for l in t.splitlines() if l.startswith("batch")][0]


def test_la_route_est_fermee_aux_roles_sans_les_chiffres(admin, monkeypatch):
    servir(monkeypatch, [], [])
    for role in ("investor", "staff", None):
        monkeypatch.setattr(flask_app, "_current_role", lambda r=role: r)
        assert appel(admin).status_code == 403, role


@pytest.mark.parametrize("p", ["", "?debut=2026-10-12", "?debut=x&fin=y"])
def test_une_demande_incomplete_est_refusee(admin, monkeypatch, p):
    servir(monkeypatch, [], [])
    assert admin.get(f"/api/marge-cafe{p}").status_code == 400
