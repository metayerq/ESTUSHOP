"""
LE MONTANT D'UN PAIEMENT INCLUT-IL LE POURBOIRE ?

⚠️ LA QUESTION QUI DÉCIDE DE CHAQUE CHIFFRE DE LA RÉCONCILIATION. Selon la réponse, « encaissé
carte » vaut `amount` ou `amount − tip` — et l'écart avec Vendus change de signe. Se tromper ne
lèverait rien : l'écran afficherait des nombres plausibles et faux tous les jours.
"""

import pytest

import app as flask_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def _poser(monkeypatch, visites_cents, releve):
    monkeypatch.setattr(flask_app, "_supa_all",
                        lambda t, p: ([{"amount": c} for c in visites_cents], False))
    monkeypatch.setattr(flask_app, "_load_revolut_days", lambda: {"2026-07-01": releve})


def test_amount_qui_colle_au_brut_exclut_le_pourboire(client, monkeypatch):
    # Relevé : 1 000 € de ventes, 80 € de pourboires. L'API dit 1 000 € → elle exclut.
    _poser(monkeypatch, [100_000], {"gross": 1000, "tips": 80, "fees": 12, "net": 1068, "tx": 1})
    d = client.get("/api/revolut/pourboires?month=2026-07").get_json()
    assert "EXCLUT" in d["verdict"]


def test_amount_qui_colle_au_brut_plus_pourboires_les_inclut(client, monkeypatch):
    _poser(monkeypatch, [108_000], {"gross": 1000, "tips": 80, "fees": 12, "net": 1068, "tx": 1})
    d = client.get("/api/revolut/pourboires?month=2026-07").get_json()
    assert "INCLUT" in d["verdict"]


def test_un_mois_sans_pourboire_ne_tranche_pas(client, monkeypatch):
    """
    ⚠️ LE PIÈGE LE PLUS DANGEREUX. Sans pourboires, les deux hypothèses donnent le MÊME nombre :
    la comparaison « réussit » et confirme celle qu'on regardait. Répondre « indécidable » est la
    seule réponse honnête, et c'est celle qu'un test doit exiger.
    """
    _poser(monkeypatch, [100_000], {"gross": 1000, "tips": 0, "fees": 12, "net": 988, "tx": 1})
    d = client.get("/api/revolut/pourboires?month=2026-07").get_json()
    assert "indécidable" in d["verdict"]


def test_des_totaux_incoherents_ne_tranchent_pas(client, monkeypatch):
    _poser(monkeypatch, [5_000], {"gross": 1000, "tips": 80, "fees": 12, "net": 1068, "tx": 1})
    d = client.get("/api/revolut/pourboires?month=2026-07").get_json()
    assert "indécidable" in d["verdict"]


def test_lecart_de_comptage_se_lit_avant_les_montants(client, monkeypatch):
    """
    ⚠️ SI LES DEUX SOURCES N'ONT PAS LE MÊME NOMBRE DE TRANSACTIONS, la comparaison des totaux
    ne veut rien dire. `card_visits` écarte les paiements sans derniers chiffres et ignore les
    remboursements : l'écart de comptage est la première chose à regarder.
    """
    _poser(monkeypatch, [100_000, 2_000],
           {"gross": 1000, "tips": 80, "fees": 12, "net": 1068, "tx": 5})
    d = client.get("/api/revolut/pourboires?month=2026-07").get_json()
    assert d["ecart_transactions"] == -3


def test_un_mois_sans_releve_le_dit(client, monkeypatch):
    monkeypatch.setattr(flask_app, "_supa_all", lambda t, p: ([], False))
    monkeypatch.setattr(flask_app, "_load_revolut_days", lambda: {})
    r = client.get("/api/revolut/pourboires?month=2026-07")
    assert r.status_code == 404
    assert "settlement" in r.get_json()["error"]


def test_le_mois_est_valide(client):
    assert client.get("/api/revolut/pourboires?month=juillet").status_code == 400
    assert client.get("/api/revolut/pourboires").status_code == 400


def test_aucun_montant_individuel_ne_traverse(client, monkeypatch):
    """Ce sont les chiffres du café, pas ceux de ses clients."""
    import json
    _poser(monkeypatch, [1_234, 98_766],
           {"gross": 1000, "tips": 80, "fees": 12, "net": 1068, "tx": 2})
    brut = json.dumps(client.get("/api/revolut/pourboires?month=2026-07").get_json())
    # ⚠️ EN EUROS ET EN CENTIMES. La première version de ce test ne cherchait que la forme
    # « 12.34 » : une fuite qui recopie les lignes brutes rend « 1234 », et passait.
    for fuite in ("12.34", "987.66", "1234", "98766"):
        assert fuite not in brut, f"un montant individuel traverse : {fuite}"


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_y_accede(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/revolut/pourboires?month=2026-07")
    assert r.status_code in (401, 403)
