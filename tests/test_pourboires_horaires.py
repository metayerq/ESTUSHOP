"""
LES POURBOIRES PAR TRANCHE HORAIRE.

⚠️ LA QUESTION N'EST PAS COMPTABLE, ELLE EST SOCIALE. « Combien de pourboires après 18 h » sert
à répartir entre les personnes qui étaient là. Un chiffre faux se paie en confiance dans
l'équipe — ce qui prend plus longtemps à réparer qu'une écriture.
"""

from datetime import date

import pytest

import app as flask_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app._rm, "enabled", lambda: True)
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def r(heure, tip, refund=False):
    return {"ts": "x", "heure": heure, "amount": 500, "tip": tip, "refund": refund}


def poser(monkeypatch, par_jour):
    monkeypatch.setattr(flask_app._rm, "fetch_day_rows",
                        lambda d: par_jour.get(d.isoformat(), []))


def test_la_part_apres_une_heure_est_separee_du_total(client, monkeypatch):
    poser(monkeypatch, {"2026-09-18": [r("11:30", 100), r("18:00", 200), r("21:15", 300)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after=18:00").get_json()
    assert d["total_cents"] == 600
    assert d["total_apres_cents"] == 500


def test_lheure_pivot_est_incluse(client, monkeypatch):
    """« Après 18 h » comprend le ticket de 18:00 pile — c'est le service du soir."""
    poser(monkeypatch, {"2026-09-18": [r("18:00", 200)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after=18:00").get_json()
    assert d["total_apres_cents"] == 200


def test_un_pourboire_rembourse_nen_est_pas_un(client, monkeypatch):
    poser(monkeypatch, {"2026-09-18": [r("19:00", 200), r("19:30", 300, refund=True)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after=18:00").get_json()
    assert d["total_cents"] == 200


def test_sans_heure_on_ne_fabrique_pas_de_part(client, monkeypatch):
    """
    ⚠️ `null` PLUTÔT QUE 0. « Pas demandé » et « zéro pourboire après 18 h » mènent à deux
    lectures opposées, et l'une des deux ferait croire qu'on a travaillé pour rien.
    """
    poser(monkeypatch, {"2026-09-18": [r("19:00", 200)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18").get_json()
    assert d["total_cents"] == 200
    assert d["total_apres_cents"] is None
    assert d["jours"][0]["pourboires_apres_cents"] is None


def test_plusieurs_jours_sont_detailles_et_totalises(client, monkeypatch):
    poser(monkeypatch, {"2026-09-17": [r("19:00", 150)], "2026-09-18": [r("20:00", 250)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-17&to=2026-09-18&after=18:00").get_json()
    assert [j["day"] for j in d["jours"]] == ["2026-09-17", "2026-09-18"]
    assert d["total_apres_cents"] == 400
    assert d["total_apres_euros"] == 4.0


def test_le_nombre_de_tickets_accompagne_le_montant(client, monkeypatch):
    """Quinze pourboires à 1 € et un à 15 € ne se répartissent pas de la même façon."""
    poser(monkeypatch, {"2026-09-18": [r("19:00", 100), r("20:00", 200), r("11:00", 50)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after=18:00").get_json()
    assert d["transactions_avec_pourboire"] == 3
    assert d["transactions_apres"] == 2


def test_un_paiement_sans_pourboire_nest_pas_compte(client, monkeypatch):
    poser(monkeypatch, {"2026-09-18": [r("19:00", 0), r("19:30", 100)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18").get_json()
    assert d["transactions_avec_pourboire"] == 1


def test_la_plage_est_plafonnee(client, monkeypatch):
    """
    ⚠️ CHAQUE JOUR COÛTE UNE VINGTAINE D'APPELS À REVOLUT. Sur un mois, la fonction est tuée à
    60 secondes — au milieu, sans dire où. Refuser est plus honnête.
    """
    poser(monkeypatch, {})
    r_ = client.get("/api/reconciliation/pourboires?from=2026-09-01&to=2026-09-30")
    assert r_.status_code == 400


@pytest.mark.parametrize("heure", ["18h", "25:00 ou pas", "midi"])
def test_une_heure_illisible_est_refusee(client, monkeypatch, heure):
    poser(monkeypatch, {})
    assert client.get(f"/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after={heure}").status_code == 400


def test_une_heure_a_un_chiffre_est_acceptee(client, monkeypatch):
    """« 9:30 » est ce qu'on tape naturellement ; le refuser serait pédant."""
    poser(monkeypatch, {"2026-09-18": [r("10:00", 100)]})
    d = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18&after=9:30").get_json()
    assert d["total_apres_cents"] == 100


def test_une_panne_revolut_nomme_le_jour(client, monkeypatch):
    """Sur une plage de sept jours, savoir LEQUEL a échoué évite de tout relancer."""
    def casse(d):
        raise TimeoutError("trop long")

    monkeypatch.setattr(flask_app._rm, "fetch_day_rows", casse)
    r_ = client.get("/api/reconciliation/pourboires?from=2026-09-18&to=2026-09-18")
    assert r_.status_code == 502
    assert "2026-09-18" in r_.get_json()["error"]


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_y_accede(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    assert flask_app.app.test_client().get(
        "/api/reconciliation/pourboires").status_code in (401, 403)
