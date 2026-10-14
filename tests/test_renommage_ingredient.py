# -*- coding: utf-8 -*-
"""
RENOMMER UN INGRÉDIENT — ET LA FAÇON DONT ÇA DÉTRUISAIT LE CAFÉ.

⚠️ CETTE ROUTE A PERDU DES DONNÉES EN RÉPONDANT « ok ». La nouvelle ligne emportait l'`id` de
l'ancienne ; l'index unique la refusait ; l'échec n'était pas regardé ; l'ancienne ligne était
supprimée quand même. Résultat : zéro ingrédient, un « ✓ Renamed » à l'écran, et chaque recette
qui l'employait réduite à « unknown ingredient » — COGS en baisse, sans un mot.

⚠️ CE QUI EST GARDÉ ICI N'EST PAS « LA ROUTE RÉPOND ». C'est : ce qui reste en base quand une
étape échoue. La bonne issue d'un renommage raté est DEUX ingrédients, pas zéro — l'un est
visible et se répare à la main, l'autre se découvre en lisant une marge fausse.

Le nom est la clé partout : recettes, préparations, historique des prix. D'où la cascade.
"""
import pytest

import app as flask_app

ANCIEN = "Guji"
NOUVEAU = "Guji Natural"

# Une ligne telle que Supabase la rend : les champs métier ET les colonnes de la ligne.
LIGNE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "price": 24.5, "unit_ref": "kg", "category": "Coffee",
    "note": "", "supplier": "Olisipo",
    "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-10-01T08:00:00Z",
}


class Faux:
    """Une base en mémoire qui retient ce qu'on lui a demandé d'écrire."""

    def __init__(self, creation_passe=True, relisible=True, recettes=None, preps=None):
        self.ingredients = {ANCIEN: dict(LIGNE)}
        self.creation_passe = creation_passe
        self.relisible = relisible
        self.recettes = recettes or {}
        self.preps = preps or {}
        self.recettes_sauvees = []
        self.preps_sauvees = []
        self.supprimes = []
        self.patchs = []
        self.ecrit = None

    def charger(self):
        return {n: dict(d) for n, d in self.ingredients.items()}

    def sauver_ingredient(self, nom, data):
        self.ecrit = dict(data)
        if not self.creation_passe:
            return False
        self.ingredients[nom] = dict(data)
        return True

    def get(self, table, params=None):
        if table == "ingredients" and params and params.get("name") == f"eq.{NOUVEAU}":
            return [{"name": NOUVEAU}] if self.relisible and NOUVEAU in self.ingredients else []
        return []

    def sauver_recette(self, titre, ings, notes, waste=0):
        self.recettes_sauvees.append((titre, [dict(i) for i in ings]))
        return self.recettes[titre].get("_sauve", True)

    def sauver_prep(self, nom, ings, qty, unit, notes, cat=""):
        self.preps_sauvees.append((nom, [dict(i) for i in ings]))
        return self.preps[nom].get("_sauve", True), None

    def patch(self, table, filtre, data, dire_combien=False):
        self.patchs.append((table, filtre, data))
        return True, 2

    def supprimer(self, table, col, val):
        self.supprimes.append((table, col, val))
        self.ingredients.pop(val, None)
        return True


@pytest.fixture
def base(monkeypatch):
    def monter(**kw):
        b = Faux(**kw)
        monkeypatch.setattr(flask_app, "_load_ingredients", b.charger)
        monkeypatch.setattr(flask_app, "_save_ingredient", b.sauver_ingredient)
        monkeypatch.setattr(flask_app, "_supa_get", b.get)
        monkeypatch.setattr(flask_app, "_load_recipes", lambda: b.recettes)
        monkeypatch.setattr(flask_app, "_load_preparations", lambda: b.preps)
        monkeypatch.setattr(flask_app, "_save_recipe", b.sauver_recette)
        monkeypatch.setattr(flask_app, "_save_preparation", b.sauver_prep)
        monkeypatch.setattr(flask_app, "_supa_patch", b.patch)
        monkeypatch.setattr(flask_app, "_supa_delete", b.supprimer)
        flask_app.app.config["TESTING"] = True
        return b, flask_app.app.test_client()
    return monter


def renommer(c, ancien=ANCIEN, nouveau=NOUVEAU):
    return c.post(f"/api/ingredients/{ancien}/rename", json={"new_name": nouveau})


# ── Ce que la nouvelle ligne emporte ────────────────────────────────────────────────────────

def test_la_nouvelle_ligne_nemporte_pas_lid_de_lancienne(base):
    """⚠️ L'`id` RECOPIÉ EST CE QUI FAISAIT REFUSER LA CRÉATION. `created_at` et `updated_at`
    appartiennent aussi à la ligne, pas à l'ingrédient : les figer mentirait sur son âge."""
    b, c = base()
    assert renommer(c).status_code == 200
    assert "id" not in b.ecrit
    assert "created_at" not in b.ecrit
    assert "updated_at" not in b.ecrit


def test_les_champs_metier_survivent_au_renommage(base):
    """Le prix, l'unité de référence, la catégorie et le fournisseur suivent le nom."""
    b, c = base()
    renommer(c)
    assert b.ecrit["price"] == 24.5
    assert b.ecrit["unit_ref"] == "kg"
    assert b.ecrit["category"] == "Coffee"
    assert b.ecrit["supplier"] == "Olisipo"


# ── Ce qui reste en base quand ça échoue ────────────────────────────────────────────────────

def test_creation_refusee_lancien_ingredient_est_conserve(base):
    """⚠️ LA FAUTE QUI A DÉTRUIT LE CAFÉ. La création échoue, et l'ancienne ligne était
    supprimée quand même — pendant que la route répondait « ok »."""
    b, c = base(creation_passe=False)
    r = renommer(c)
    assert r.status_code == 502
    assert r.get_json()["ok"] is False
    assert b.supprimes == []
    assert ANCIEN in b.ingredients


def test_nouvelle_ligne_non_relisible_lancien_est_conserve(base):
    """⚠️ « L'ÉCRITURE EST PARTIE » N'EST PAS « LA LIGNE EST LÀ ». Seule une relecture autorise
    la suppression de l'original."""
    b, c = base(relisible=False)
    r = renommer(c)
    assert r.status_code == 502
    assert r.get_json()["error"] == "create_unconfirmed"
    assert b.supprimes == []
    assert ANCIEN in b.ingredients


def test_une_recette_qui_ne_se_sauve_pas_arrete_la_suppression(base):
    """⚠️ UNE CASCADE INCOMPLÈTE ARRÊTE TOUT. Supprimer l'ancien nom alors qu'une recette le
    cite encore la laisserait pointer vers un ingrédient inexistant : COGS en baisse, muet."""
    b, c = base(recettes={
        "Flat White": {"ingredients": [{"name": ANCIEN, "qty": 18, "unit": "g"}],
                       "notes": "", "waste_pct": 0, "_sauve": False},
    })
    r = renommer(c)
    assert r.status_code == 502
    assert r.get_json()["error"] == "cascade_incomplete"
    assert "recipe:Flat White" in r.get_json()["failed"]
    assert b.supprimes == []
    assert ANCIEN in b.ingredients


# ── La cascade quand tout va bien ───────────────────────────────────────────────────────────

def test_les_recettes_et_preparations_sont_repointees(base):
    b, c = base(
        recettes={"Flat White": {"ingredients": [{"name": ANCIEN, "qty": 18, "unit": "g"}],
                                 "notes": "", "waste_pct": 0},
                  "Cookie": {"ingredients": [{"name": "Farine", "qty": 200, "unit": "g"}],
                             "notes": "", "waste_pct": 0}},
        preps={"Café infusé": {"ingredients": [{"name": ANCIEN, "qty": 60, "unit": "g"}],
                               "yield_qty": 1, "yield_unit": "l"}},
    )
    d = renommer(c).get_json()
    assert (d["recipes"], d["preparations"]) == (1, 1)
    assert b.recettes_sauvees == [("Flat White", [{"name": NOUVEAU, "qty": 18, "unit": "g"}])]
    assert b.preps_sauvees == [("Café infusé", [{"name": NOUVEAU, "qty": 60, "unit": "g"}])]
    assert b.supprimes == [("ingredients", "name", ANCIEN)]


def test_lhistorique_des_prix_suit_et_la_route_dit_combien(base):
    """⚠️ UN PATCH QUI NE TROUVE RIEN RÉPOND 204 COMME UN PATCH RÉUSSI. On demande le compte,
    sinon un historique resté sur l'ancien nom passerait inaperçu."""
    b, c = base()
    d = renommer(c).get_json()
    assert d["moved"]["ingredient_price_history"] == 2
    assert ("ingredient_price_history", {"name": f"eq.{ANCIEN}"},
            {"name": NOUVEAU}) in b.patchs


# ── Les refus ordinaires ────────────────────────────────────────────────────────────────────

def test_un_nom_deja_pris_est_refuse_sans_rien_toucher(base):
    b, c = base()
    b.ingredients["Sidamo"] = dict(LIGNE)
    r = renommer(c, nouveau="Sidamo")
    assert r.status_code == 409
    assert b.supprimes == []
    assert b.ecrit is None


def test_un_ingredient_inconnu_rend_404(base):
    b, c = base()
    assert renommer(c, ancien="Fantome").status_code == 404
    assert b.supprimes == []


def test_le_meme_nom_ne_fait_rien(base):
    b, c = base()
    r = renommer(c, nouveau=ANCIEN)
    assert r.status_code == 200
    assert b.ecrit is None
    assert b.supprimes == []


def test_un_nom_vide_est_refuse(base):
    b, c = base()
    r = c.post(f"/api/ingredients/{ANCIEN}/rename", json={"new_name": "   "})
    assert r.status_code == 400
    assert b.ecrit is None


# ── Le prix absent, qui bloquait le renommage et effaçait des coûts ──────────────────────────

@pytest.fixture
def poste(monkeypatch):
    """La route de création/mise à jour d'un ingrédient, avec ce qu'elle écrit vraiment."""
    ecrits = []
    monkeypatch.setattr(flask_app, "_save_ingredient",
                        lambda nom, data: (ecrits.append((nom, dict(data))), True)[1])
    flask_app.app.config["TESTING"] = True
    return ecrits, flask_app.app.test_client()


def test_sans_prix_la_route_ne_touche_pas_au_prix(poste):
    """⚠️ ABSENT VEUT DIRE INCHANGÉ, PAS ZÉRO. Écrire 0 annule le COGS de chaque recette qui
    emploie l'ingrédient — une marge qui grimpe toute seule, sans un mot."""
    ecrits, c = poste
    r = c.post("/api/ingredients", json={"name": ANCIEN, "unit_ref": "kg"})
    assert r.status_code == 200
    assert "price" not in ecrits[0][1]


def test_un_prix_null_ne_fait_pas_tomber_la_route(poste):
    """⚠️ `float(None)` LEVAIT UNE TypeError — un 500 juste après un renommage réussi, donc un
    écran qui annonce le succès pendant que les autres champs sont perdus."""
    ecrits, c = poste
    r = c.post("/api/ingredients", json={"name": ANCIEN, "price": None, "unit_ref": "kg"})
    assert r.status_code == 200
    assert "price" not in ecrits[0][1]


def test_un_prix_fourni_est_bien_ecrit(poste):
    ecrits, c = poste
    c.post("/api/ingredients", json={"name": ANCIEN, "price": 24.5, "unit_ref": "kg"})
    assert ecrits[0][1]["price"] == 24.5


def test_un_prix_a_zero_reste_un_prix_a_zero(poste):
    """Zéro EST une valeur : la facture d'un échantillon gratuit, par exemple."""
    ecrits, c = poste
    c.post("/api/ingredients", json={"name": ANCIEN, "price": 0, "unit_ref": "kg"})
    assert ecrits[0][1]["price"] == 0


# ── L'écran : le second verrou qui empêchait de renommer ─────────────────────────────────────

def test_lecran_ne_reclame_pas_de_prix_pour_un_renommage():
    """⚠️ DEUX VERROUS POUR LA MÊME PANNE. Le serveur détruisait l'ingrédient ; l'écran, lui,
    refusait d'essayer dès que le prix était vide — en affichant « Name and price required »,
    qui envoie chercher le problème ailleurs. Le garde doit laisser passer un renommage."""
    with open("templates/cogs.html", encoding="utf-8") as f:
        html = f.read()
    assert "if (!isRename && isNaN(price))" in html
    # Et l'ancien garde inconditionnel ne doit pas revenir.
    assert "if (!name || isNaN(price))" not in html
