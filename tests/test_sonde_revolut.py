"""
LA SONDE QUI DÉCIDE DE LA RÉCONCILIATION.

⚠️ ELLE EST FAITE POUR ÊTRE RECOPIÉE DANS UNE CONVERSATION. C'est son usage prévu : constater ce
que l'API donne, et le montrer. Elle doit donc être sûre à recopier — un montant, un numéro de
carte ou un nom de porteur qui traverserait ici finirait dans un historique que personne ne
purge.
"""

import pytest

import app as flask_app
import revolut_merchant as rm

PAIEMENT = {
    "id": "pay_1",
    "state": "completed",
    "amount": 960,
    "payment_method": {"card_last_four": "4242", "application_name": "Visa",
                       "card_holder_name": "ANA SILVA"},
}
COMMANDE = {"id": "6ab0086e-aaaa", "state": "completed", "amount": 960,
            "email": "ana@exemple.pt"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(rm, "_key", lambda: "cle-de-test")
    monkeypatch.setattr(rm, "_session", lambda: None)

    def faux_get(s, url, params=None, tries=6):
        if url.endswith("/orders"):
            return {"orders": [COMMANDE]}
        if url.endswith("/payments"):
            return [PAIEMENT]
        return None

    monkeypatch.setattr(rm, "_get", faux_get)


def test_elle_rend_les_noms_de_champs(api):
    d = rm.schema_recent()
    c = d["commandes"][0]
    assert "amount" in c["champs_commande"]
    assert "amount" in c["paiements"][0]["champs_paiement"]
    assert "card_last_four" in c["paiements"][0]["champs_moyen"]


def test_elle_ne_rend_aucune_valeur_sensible(api):
    """
    ⚠️ LE TEST QUI COMPTE. Les quatre derniers chiffres, le nom du porteur, l'e-mail du client,
    le montant : rien de tout cela n'a de raison de traverser une sonde de schéma.
    """
    import json
    brut = json.dumps(rm.schema_recent())
    for fuite in ("4242", "ANA SILVA", "ana@exemple.pt", "960"):
        assert fuite not in brut, f"la sonde laisse passer une valeur : {fuite}"


def test_lidentifiant_est_tronque(api):
    assert rm.schema_recent()["commandes"][0]["id"] == "6ab0086e"


def test_la_limite_est_bornee(api, monkeypatch):
    """Sans borne, une faute de frappe dans l'URL lancerait des centaines d'appels à Revolut."""
    vus = []

    def compte(s, url, params=None, tries=6):
        vus.append(params)
        return {"orders": []} if url.endswith("/orders") else []

    monkeypatch.setattr(rm, "_get", compte)
    rm.schema_recent(9999)
    assert vus[0]["limit"] == 10
    rm.schema_recent(0)
    assert vus[1]["limit"] == 1


def test_une_enveloppe_inattendue_ne_fait_pas_tomber_la_sonde(monkeypatch):
    """
    ⚠️ J'AI DÉJÀ SUPPOSÉ UN TABLEAU NU ET REVOLUT A RENDU AUTRE CHOSE — la page est tombée sur
    « .filter is not a function ». Une sonde qui tombe ne dit rien ; elle doit décrire ce
    qu'elle n'a pas su lire.
    """
    monkeypatch.setattr(rm, "_key", lambda: "k")
    monkeypatch.setattr(rm, "_session", lambda: None)
    monkeypatch.setattr(rm, "_get", lambda *a, **k: "bonjour")
    d = rm.schema_recent()
    assert d["commandes"] == []


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_ouvre_la_sonde(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/revolut/schema")
    assert r.status_code in (401, 403)


def test_sans_cle_elle_le_dit_au_lieu_de_tomber(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app._rm, "enabled", lambda: False)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/revolut/schema")
    assert r.status_code == 500
    assert "REVOLUT_MERCHANT_KEY" in r.get_json()["error"]
