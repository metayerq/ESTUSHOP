"""
LA BANDE D'ÉTAT.

⚠️ ELLE S'AFFICHE SUR TOUTES LES PAGES. Une source coûteuse ici et chaque navigation du
backoffice paierait une seconde de plus — jusqu'au jour où on retirerait la bande pour cette
raison. Et un échec partiel ne doit pas vider le reste : une bande à moitié remplie vaut mieux
qu'une bande vide.
"""

from datetime import date

import pytest

import app as flask_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 9, 21))
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def poser(monkeypatch, docs=None, resume=None, terminal=None, comptes=None):
    monkeypatch.setattr(flask_app, "_get_today_docs_cached", lambda: docs or [])
    monkeypatch.setattr(flask_app, "_fetch_summaries", lambda a, b: resume or [])
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: terminal or [])
    monkeypatch.setattr(flask_app, "_fidelidade_reglages", lambda: {"threshold_points": 50})
    monkeypatch.setattr(flask_app, "_fidelidade_donnees",
                        lambda now, r: (comptes or [], None, False))


def test_le_chiffre_du_jour_vient_du_cache(client, monkeypatch):
    poser(monkeypatch, docs=[{"amount_gross": 12.50}, {"amount_gross": 7.00}])
    d = client.get("/api/statut").get_json()
    assert d["ca"] == 19.5
    assert d["tickets"] == 2
    assert "19,50" in d["ca_texte"]


def test_le_ticket_moyen_se_divise_par_les_ventes_pas_les_documents(client, monkeypatch):
    """
    ⚠️ LES AVOIRS SONT DES DOCUMENTS. Les compter au dénominateur ferait baisser le ticket moyen
    un jour de remboursement, alors que rien n'a changé pour les clients qui ont acheté.
    """
    poser(monkeypatch, docs=[{"amount_gross": 20.0}, {"amount_gross": -5.0, "_refund": True}])
    d = client.get("/api/statut").get_json()
    assert d["tickets"] == 1
    assert "15,00" in d["moyen_texte"]


def test_sans_vente_le_chiffre_reste_un_tiret(client, monkeypatch):
    """« Pas encore de vente » et « zéro euro » mènent à deux lectures opposées à 11 h."""
    poser(monkeypatch, docs=[])
    d = client.get("/api/statut").get_json()
    assert d["ca"] == 0
    assert d["moyen_texte"] is None


def test_un_ecart_de_caisse_est_compte(client, monkeypatch):
    poser(monkeypatch,
          resume=[{"day": "2026-09-18", "ca_ttc": 120.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": "2026-09-18", "gross_cents": 12000, "refunds_cents": 0}])
    d = client.get("/api/statut").get_json()
    assert d["ecarts"] == 1


def test_une_journee_fermee_nest_pas_une_anomalie(client, monkeypatch):
    """Mardi et mercredi n'ont ni encaissement ni facture — ce n'est pas un écart."""
    poser(monkeypatch,
          resume=[{"day": "2026-09-16", "ca_ttc": 0.0, "payments": {}}],
          terminal=[{"day": "2026-09-16", "gross_cents": 0}])
    assert client.get("/api/statut").get_json()["ecarts"] == 0


def test_le_vert_et_le_rouge_ne_saffichent_pas_ensemble(client, monkeypatch):
    """
    ⚠️ AFFICHER « CAISSE ✓ VENDREDI » À CÔTÉ DE « 2 À VÉRIFIER » ferait lire le vert et ignorer
    le rouge — exactement l'inverse de ce qu'une bande d'alerte doit produire.
    """
    # Le 18 est sain ; le 19 porte 23,40 € d'écart — le terminal a encaissé moins que le
    # facturé carte.
    poser(monkeypatch,
          resume=[{"day": "2026-09-18", "ca_ttc": 100.0, "payments": {"Cartão": 100.0}},
                  {"day": "2026-09-19", "ca_ttc": 143.4, "payments": {"Cartão": 123.4}}],
          terminal=[{"day": "2026-09-18", "gross_cents": 10000},
                    {"day": "2026-09-19", "gross_cents": 10000}])
    d = client.get("/api/statut").get_json()
    assert d["ecarts"] == 1
    assert d["caisse_ok"] is None


def test_sans_ecart_la_derniere_journee_saine_est_annoncee(client, monkeypatch):
    poser(monkeypatch,
          resume=[{"day": "2026-09-18", "ca_ttc": 100.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": "2026-09-18", "gross_cents": 10000}])
    assert client.get("/api/statut").get_json()["caisse_ok"] == "18/09"


def test_les_boissons_dues_sont_totalisees(client, monkeypatch):
    poser(monkeypatch, comptes=[{"state": {"rewards_due": 2}}, {"state": {"rewards_due": 1}}])
    assert client.get("/api/statut").get_json()["boissons_dues"] == 3


def test_chaque_morceau_echoue_separement(client, monkeypatch):
    """
    ⚠️ SI LA FIDÉLITÉ EST INDISPONIBLE, LE CHIFFRE DU JOUR RESTE AFFICHÉ. Une bande
    partiellement remplie vaut mieux qu'une bande vide, et bien mieux qu'une erreur en travers
    de l'écran de travail.
    """
    poser(monkeypatch, docs=[{"amount_gross": 30.0}])

    def casse(*a, **k):
        raise RuntimeError("Supabase muet")

    monkeypatch.setattr(flask_app, "_fidelidade_donnees", casse)
    monkeypatch.setattr(flask_app, "_fetch_summaries", casse)
    r = client.get("/api/statut")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ca"] == 30.0
    assert d["boissons_dues"] == 0


def test_la_route_est_fermee(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: None)
    flask_app.app.config["TESTING"] = True
    assert flask_app.app.test_client().get("/api/statut").status_code == 401
