"""
LA SONDE DES LIBELLÉS DE PAIEMENT.

⚠️ ELLE EXISTE PARCE QUE « FACTURÉ CARTE = 0 » A TROIS CAUSES POSSIBLES, et qu'elles appellent
trois corrections différentes : Vendus ne rend pas le champ, le cache a été rempli avant le
correctif, ou le libellé n'est pas dans la liste des moyens carte. Les trois produisent le même
zéro à l'écran.

J'ai supposé deux fois avant de la construire. Les deux fois, je me suis trompé.
"""

import pytest

import app as flask_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def poser(monkeypatch, docs=None, cache=None):
    monkeypatch.setattr(flask_app, "get_documents", lambda a, b, detailed: docs or [])
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [{"day": "2026-09-18", "ca_ttc": 520.0,
                                       "payments": cache}] if cache is not None else [])


def test_elle_distingue_les_trois_etapes(client, monkeypatch):
    poser(monkeypatch,
          docs=[{"payments": [{"title": "Cartão", "amount": 9.6}]}],
          cache={"Cartão": 9.6})
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["vendus_live"]["titres"] == {"Cartão": 9.6}
    assert d["cache_daily_summary"]["present"] is True
    assert d["classement"]["live"]["carte"] == ["Cartão"]


def test_un_champ_absent_chez_vendus_se_voit(client, monkeypatch):
    """
    ⚠️ LA PREMIÈRE CAUSE. Si `documents_avec_paiements` vaut 0 alors que `documents` en compte
    trente, c'est Vendus qui ne rend rien — et aucun correctif de cache n'y changera quoi que
    ce soit.
    """
    poser(monkeypatch, docs=[{"amount_gross": 12.0}, {"amount_gross": 8.0}], cache={})
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["vendus_live"]["documents"] == 2
    assert d["vendus_live"]["documents_avec_paiements"] == 0


def test_un_libelle_inconnu_est_range_dans_autre(client, monkeypatch):
    """
    ⚠️ LA TROISIÈME CAUSE, ET LA PLUS SOURNOISE. Vendus rend le champ, le cache l'a — mais le
    libellé n'est pas dans ma liste. « Facturé carte » reste à zéro sans que rien ne manque.
    """
    # ⚠️ « Visa/Mastercard » ÉTAIT L'EXEMPLE DE LA PREMIÈRE VERSION — il est désormais reconnu.
    # Un test qui garde un exemple périmé cesse de tester ce qu'il dit tester.
    poser(monkeypatch,
          docs=[{"payments": [{"title": "Vale de refeição", "amount": 9.6}]}],
          cache={"Vale de refeição": 9.6})
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["classement"]["live"]["autre"] == ["Vale de refeição"]
    assert d["classement"]["live"]["carte"] == []


def test_les_accents_et_la_casse_ne_trompent_pas_le_classement(client, monkeypatch):
    poser(monkeypatch, docs=[{"payments": [{"title": "CARTAO", "amount": 9.6}]}], cache={})
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["classement"]["live"]["carte"] == ["CARTAO"]


def test_elle_annonce_ce_quelle_connait(client, monkeypatch):
    """Pour qu'on voie immédiatement ce qu'il manque à la liste, sans lire le code."""
    poser(monkeypatch)
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    # ⚠️ DES MOTS, PAS DES LIBELLÉS : afficher les libellés entiers ferait croire qu'il faut
    # les énumérer un par un.
    assert "cartao" in d["mots_reconnus"]["carte"]
    assert "dinheiro" in d["mots_reconnus"]["especes"]


def test_une_panne_vendus_est_nommee_et_ne_cache_pas_le_reste(client, monkeypatch):
    """Le cache reste lisible même si Vendus ne répond pas — c'est justement la comparaison."""
    def casse(a, b, detailed):
        raise TimeoutError("trop long")

    monkeypatch.setattr(flask_app, "get_documents", casse)
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [{"day": "2026-09-18", "ca_ttc": 520.0,
                                       "payments": {"Cartão": 412.3}}])
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["vendus_live"]["erreur"]
    assert d["cache_daily_summary"]["payments"] == {"Cartão": 412.3}


def test_un_cache_absent_nest_pas_un_cache_vide(client, monkeypatch):
    """
    ⚠️ « PAS DE LIGNE » ET « LIGNE AVEC UNE RÉPARTITION VIDE » APPELLENT DEUX GESTES DIFFÉRENTS :
    reconstruire, ou corriger les libellés.
    """
    poser(monkeypatch, docs=[], cache=None)
    d = client.get("/api/vendus/paiements?day=2026-09-18").get_json()
    assert d["cache_daily_summary"]["present"] is False


def test_le_jour_est_valide(client):
    assert client.get("/api/vendus/paiements?day=hier").status_code == 400


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_y_accede(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/vendus/paiements?day=2026-09-18")
    assert r.status_code in (401, 403)
