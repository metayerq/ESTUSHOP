"""
LE RAPPROCHEMENT TRANSACTION PAR TRANSACTION.

⚠️ UN ÉCART CHIFFRÉ NE SE RÉPARE PAS. « 23,40 € » dit qu'il y a un problème ; « paiement de
9,60 € à 14:32 sans facture Vendus en face » dit lequel. C'est la différence entre un tableau de
bord et un outil.

⚠️ ET CE MODULE PEUT FABRIQUER DE FAUSSES PISTES. Un appariement trop laxiste dit « tout va
bien » les jours chargés ; trop strict, il invente deux anomalies pour une transaction saine. Les
deux coûtent une heure à chercher quelque chose qui n'existe pas.
"""

import pytest

import app as flask_app

_ap = flask_app._apparier


def p(heure, cents):
    return {"ts": f"2026-09-18T{heure}:00Z", "heure": heure, "amount": cents, "tip": 0,
            "refund": False}


def f(heure, cents, numero="FT 1/1"):
    return {"heure": heure, "amount": cents, "numero": numero}


def test_un_paiement_et_sa_facture_sapparient():
    a, po, fo = _ap([p("14:32", 960)], [f("14:33", 960)])
    assert len(a) == 1 and po == [] and fo == []


def test_le_montant_prime_sur_lheure():
    """
    ⚠️ DEUX CAFÉS À 2,50 € À TROIS MINUTES D'INTERVALLE SE RESSEMBLENT. Un montant identique au
    centime est un signal fort ; l'heure ne sert qu'à départager. L'inverse apparierait au
    hasard dès qu'il y a du monde.
    """
    a, po, fo = _ap([p("14:30", 250)], [f("14:29", 960), f("14:40", 250)])
    assert len(a) == 1
    assert fo == [f("14:29", 960)]


def test_chaque_ligne_ne_sert_quune_fois():
    """
    ⚠️ SANS CETTE RÈGLE, un paiement de 2,50 € s'apparierait à TOUTES les factures de 2,50 € de
    la journée — et le rapprochement dirait « tout est bon » précisément les jours chargés.
    """
    a, po, fo = _ap([p("14:00", 250)], [f("14:01", 250), f("14:05", 250)])
    assert len(a) == 1
    assert len(fo) == 1, "une facture a été appariée deux fois"


def test_un_paiement_sans_facture_est_rendu_en_entier():
    """Un nombre ne se corrige pas ; la ligne, si — on l'ouvre dans Vendus."""
    a, po, fo = _ap([p("14:32", 960)], [])
    assert a == [] and fo == []
    assert po[0]["amount"] == 960 and po[0]["heure"] == "14:32"


def test_une_facture_sans_paiement_est_rendue_avec_son_numero():
    a, po, fo = _ap([], [f("14:32", 960, "FT 2026/117")])
    assert fo[0]["numero"] == "FT 2026/117"


def test_la_fenetre_de_temps_est_large():
    """
    ⚠️ LA FACTURE EST ÉMISE APRÈS L'ENCAISSEMENT, parfois plusieurs minutes plus tard quand le
    client commande encore. Trop serré, l'appariement échoue et fabrique DEUX anomalies — un
    paiement orphelin ET une facture orpheline — pour une seule transaction saine.
    """
    a, _, _ = _ap([p("14:00", 960)], [f("14:18", 960)])
    assert len(a) == 1


def test_au_dela_de_la_fenetre_on_napparie_pas():
    """Deux transactions du même montant à deux heures d'écart ne sont pas la même."""
    a, po, fo = _ap([p("09:00", 960)], [f("18:00", 960)])
    assert a == [] and len(po) == 1 and len(fo) == 1


def test_minuit_ne_fait_pas_exploser_la_comparaison():
    """00:05 et 23:55 sont à dix minutes l'un de l'autre dans la vraie vie, mais PAS le même
    jour — et ce module ne traite qu'un jour. L'écart calculé est grand, donc pas d'appariement :
    c'est le comportement sûr."""
    a, po, fo = _ap([p("00:05", 960)], [f("23:55", 960)])
    assert a == []


# ── La route ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app._rm, "enabled", lambda: True)
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def test_les_remboursements_ne_sapparient_pas(client, monkeypatch):
    """
    ⚠️ UN REMBOURSEMENT N'A PAS DE FACTURE DE VENTE EN FACE. Le mêler aux ventes ferait
    apparaître autant de fausses factures orphelines — et on chercherait des encaissements
    perdus qui sont en réalité des avoirs.
    """
    # ⚠️ LE REMBOURSEMENT PORTE LE MÊME MONTANT QUE LA VENTE, exprès. S'il était mêlé aux
    # ventes, il apparaîtrait en PAIEMENT ORPHELIN — la vente a déjà pris la facture. Un
    # remboursement d'un autre montant n'aurait pas révélé le défaut : ma première version du
    # test en utilisait un, et le mutant passait.
    monkeypatch.setattr(flask_app._rm, "fetch_day_rows", lambda d: [
        {"ts": "x", "heure": "14:00", "amount": 960, "tip": 0, "refund": False},
        {"ts": "y", "heure": "14:05", "amount": 960, "tip": 0, "refund": True},
    ])
    monkeypatch.setattr(flask_app, "get_documents", lambda a, b, detailed: [
        {"local_time": "2026-09-18 14:01:00", "number": "FT 1",
         "payments": [{"title": "Cartão", "amount": 9.60}]},
    ])
    d = client.get("/api/reconciliation/day/2026-09-18/detail").get_json()
    assert d["apparies"] == 1
    assert d["factures_seules"] == []
    assert d["paiements_seuls"] == [], "le remboursement compte aussi comme une vente orpheline"
    assert len(d["remboursements"]) == 1


def test_un_paiement_en_especes_nest_pas_une_facture_carte(client, monkeypatch):
    monkeypatch.setattr(flask_app._rm, "fetch_day_rows", lambda d: [])
    monkeypatch.setattr(flask_app, "get_documents", lambda a, b, detailed: [
        {"local_time": "2026-09-18 14:01:00", "number": "FT 1",
         "payments": [{"title": "Dinheiro", "amount": 9.60}]},
    ])
    d = client.get("/api/reconciliation/day/2026-09-18/detail").get_json()
    assert d["factures_seules"] == []


def test_une_panne_revolut_est_nommee(client, monkeypatch):
    """« 502 » tout court enverrait chercher la panne du mauvais côté."""
    def casse(d):
        raise TimeoutError("trop long")

    monkeypatch.setattr(flask_app._rm, "fetch_day_rows", casse)
    r = client.get("/api/reconciliation/day/2026-09-18/detail")
    assert r.status_code == 502
    assert "Revolut" in r.get_json()["error"]


def test_une_panne_vendus_est_nommee_aussi(client, monkeypatch):
    monkeypatch.setattr(flask_app._rm, "fetch_day_rows", lambda d: [])

    def casse(a, b, detailed):
        raise TimeoutError("trop long")

    monkeypatch.setattr(flask_app, "get_documents", casse)
    r = client.get("/api/reconciliation/day/2026-09-18/detail")
    assert r.status_code == 502
    assert "Vendus" in r.get_json()["error"]


def test_un_jour_a_venir_est_refuse(client, monkeypatch):
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: __import__("datetime").date(2026, 9, 18))
    assert client.get("/api/reconciliation/day/2026-12-01/detail").status_code == 400


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_ouvre_le_detail(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/reconciliation/day/2026-09-18/detail")
    assert r.status_code in (401, 403)
