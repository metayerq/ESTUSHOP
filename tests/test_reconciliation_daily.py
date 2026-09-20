"""
LA RÉCONCILIATION QUOTIDIENNE — trois sources, trois statuts.

⚠️ UN ÉCRAN QUI MÉLANGE MESURÉ, ESTIMÉ ET INCONNU EST PIRE QU'UN ÉCRAN VIDE. Et les trois modes
de mensonge de cet endpoint sont silencieux : un facteur cent entre deux tables qui n'ont pas la
même unité, un « pas de donnée » affiché comme un zéro, et un moyen de paiement non classé qui
tombe dans « autre » sans que personne ne le sache.
"""

from datetime import date, timedelta

import pytest

import app as flask_app

JOUR = "2026-09-18"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 9, 19))
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def poser(monkeypatch, resume=None, terminal=None, revolut=None):
    monkeypatch.setattr(flask_app, "_fetch_summaries", lambda a, b: resume or [])
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: terminal or [])
    monkeypatch.setattr(flask_app, "_load_revolut_days", lambda: revolut or {})
    monkeypatch.setattr(flask_app, "_get_today_docs_cached", lambda: [])


def un_jour(client, **kw):
    r = client.get(f"/api/reconciliation/daily?from={JOUR}&to={JOUR}")
    return r.get_json()["jours"][0]


# ── L'unité ──────────────────────────────────────────────────────────────────────────────────

def test_les_deux_unites_se_rejoignent_en_centimes(client, monkeypatch):
    """
    ⚠️ `terminal_days` EST EN CENTIMES ENTIERS, `daily_summary` EN EUROS DÉCIMAUX. Chaque table
    garde l'unité de sa source ; la conversion se fait ICI, à un seul endroit. Un facteur cent
    ne lève jamais — il produit des nombres plausibles et faux.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 120.50, "payments": {"Cartão": 100.50}}],
          terminal=[{"day": JOUR, "gross_cents": 10050, "tips_cents": 200, "tx": 9,
                     "refunds_cents": 0}])
    j = un_jour(client)
    assert j["vendus_total_cents"] == 12050
    assert j["terminal_cents"] == 10050
    assert j["vendus"]["carte_cents"] == 10050
    assert j["ecart_cents"] == 0


def test_les_centimes_ne_derivent_pas_a_larrondi(client, monkeypatch):
    """0,1 + 0,2 en euros ne fait pas 0,30000000000000004 centimes."""
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 0.3, "payments": {"Cartão": 0.1, "Dinheiro": 0.2}}],
          terminal=[{"day": JOUR, "gross_cents": 10}])
    j = un_jour(client)
    assert j["vendus"]["carte_cents"] == 10
    assert j["vendus"]["especes_cents"] == 20


# ── Les moyens de paiement ───────────────────────────────────────────────────────────────────

def test_les_accents_et_la_casse_ne_font_pas_deux_moyens(client, monkeypatch):
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 20.0, "payments": {"Cartão": 10.0, "cartao": 10.0}}],
          terminal=[{"day": JOUR, "gross_cents": 2000}])
    assert un_jour(client)["vendus"]["carte_cents"] == 2000


def test_un_titre_inconnu_est_nomme_pas_avale(client, monkeypatch):
    """
    ⚠️ UN MOYEN DE PAIEMENT NON CLASSÉ QUI TOMBERAIT SILENCIEUSEMENT DANS « AUTRE » ferait
    apparaître un écart permanent avec le terminal, et personne ne saurait que la cause est un
    libellé.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 30.0, "payments": {"Cartão": 20.0, "Cheque": 10.0}}],
          terminal=[{"day": JOUR, "gross_cents": 2000}])
    v = un_jour(client)["vendus"]
    assert v["autre_cents"] == 1000
    assert v["titres_inconnus"] == ["Cheque"]


# ── Ce qui manque ────────────────────────────────────────────────────────────────────────────

def test_une_repartition_absente_ne_produit_pas_un_ecart_catastrophique(client, monkeypatch):
    """
    ⚠️ LE PIÈGE LE PLUS DANGEREUX DE CET ÉCRAN. Sans répartition, un écart calculé vaudrait
    exactement le montant encaissé en carte — 412 € de « manquant » sur une journée normale.
    On chercherait un vol là où il n'y a qu'une colonne pas encore reconstruite.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 120.0}],
          terminal=[{"day": JOUR, "gross_cents": 10000}])
    j = un_jour(client)
    assert j["ecart_cents"] is None
    assert j["repartition_absente"] is True


def test_labsence_de_terminal_est_nommee(client, monkeypatch):
    poser(monkeypatch, resume=[{"day": JOUR, "ca_ttc": 120.0, "payments": {"Cartão": 100.0}}])
    j = un_jour(client)
    assert j["terminal_absent"] is True
    assert j["terminal_cents"] == 0


# ── Les frais ────────────────────────────────────────────────────────────────────────────────

def test_les_frais_mesures_lemportent_sur_lestimation(client, monkeypatch):
    """
    ⚠️ LE CHIFFRE MESURÉ DU JOUR DOIT DIFFÉRER DE CE QUE DONNERAIT LE TAUX, sinon le test est
    dégénéré et passe même si le code ignore la mesure. Première version de ce test : un seul
    jour de relevé, donc un taux calibré sur ce jour-là — les deux valeurs coïncidaient, et le
    mutant « frais = brut × taux » survivait.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 100.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": JOUR, "gross_cents": 10000}],
          # Le mois porte 1 000 € de ventes pour 9 € de frais → taux 0,9 %, soit 90 centimes
          # estimés sur ce jour. Le relevé du jour, lui, en mesure 500.
          revolut={JOUR: {"gross": 100.0, "fees": 5.0, "tips": 0, "net": 95.0, "tx": 1},
                   "2026-09-01": {"gross": 900.0, "fees": 4.0, "tips": 0, "net": 896.0,
                                  "tx": 90}})
    j = un_jour(client)
    assert j["frais_cents"] == 500, "les frais mesurés ont été remplacés par l'estimation"
    assert j["frais_mesures"] is True


def test_sans_releve_les_frais_sont_estimes_et_le_disent(client, monkeypatch):
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 100.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": JOUR, "gross_cents": 10000}])
    j = un_jour(client)
    assert j["frais_mesures"] is False
    assert 130 <= j["frais_cents"] <= 150  # ~1,44 %


def test_le_taux_est_calibre_sur_le_dernier_mois_regle(client, monkeypatch):
    """
    ⚠️ UN TAUX EN DUR VIEILLIT SANS QUE RIEN NE LE SIGNALE. Un changement de contrat Revolut
    ferait dériver l'estimation de tous les jours à venir, et l'écart ne se verrait qu'à la
    clôture suivante.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 100.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": JOUR, "gross_cents": 10000}],
          revolut={"2026-08-01": {"gross": 1000.0, "fees": 30.0, "tips": 0, "net": 970.0,
                                  "tx": 100}})
    d = client.get(f"/api/reconciliation/daily?from={JOUR}&to={JOUR}").get_json()
    assert d["taux_frais"] == pytest.approx(0.03)
    assert d["taux_calibre_sur"] == "2026-08"


# ── Le net et les remboursements ─────────────────────────────────────────────────────────────

def test_le_net_suit_lidentite_mesuree_sur_la_banque(client, monkeypatch):
    """
    ⚠️ VENTES + POURBOIRES − FRAIS, vérifié sur juillet 2026 contre le relevé bancaire
    (6 107,55 € reçus, contre 6 003,62 € pour la colonne `Settlement amount` seule). Notre page
    affichait donc les pourboires comme de l'argent non reçu — faux de 99 € sur un mois.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 100.0, "payments": {"Cartão": 100.0}}],
          terminal=[{"day": JOUR, "gross_cents": 10000, "tips_cents": 500}],
          revolut={JOUR: {"gross": 100.0, "fees": 1.44, "tips": 5.0, "net": 98.56, "tx": 1}})
    assert un_jour(client)["net_cents"] == 10000 + 500 - 144


def test_un_remboursement_reduit_lecart_et_le_net(client, monkeypatch):
    """
    Un avoir rendu en carte diminue l'encaissement des deux côtés : Vendus le compte en négatif
    dans sa répartition, le terminal le porte à part. L'écart doit rester nul.
    """
    poser(monkeypatch,
          resume=[{"day": JOUR, "ca_ttc": 60.0, "payments": {"Cartão": 60.0}}],
          terminal=[{"day": JOUR, "gross_cents": 10000, "refunds_cents": 4000}])
    j = un_jour(client)
    assert j["ecart_cents"] == 0
    assert j["remboursements_cents"] == 4000


# ── Le jour courant ──────────────────────────────────────────────────────────────────────────

def test_aujourdhui_vient_du_cache_et_est_marque(client, monkeypatch):
    """
    ⚠️ `daily_summary` NE PORTE JAMAIS AUJOURD'HUI — il n'est pas fini, et l'y écrire le figerait
    à l'heure du premier regard.
    """
    poser(monkeypatch, terminal=[{"day": "2026-09-19", "gross_cents": 5000}])
    monkeypatch.setattr(flask_app, "_get_today_docs_cached",
                        lambda: [{"amount_gross": 50.0, "payments": [{"title": "Cartão",
                                                                      "amount": 50.0}]}])
    d = client.get("/api/reconciliation/daily?from=2026-09-19&to=2026-09-19").get_json()
    j = d["jours"][0]
    assert j["aujourdhui"] is True
    assert j["vendus_total_cents"] == 5000
    assert j["ecart_cents"] == 0


def test_une_borne_future_est_ramenee_a_aujourdhui(client, monkeypatch):
    poser(monkeypatch)
    d = client.get("/api/reconciliation/daily?from=2026-09-18&to=2026-12-31").get_json()
    assert d["to"] == "2026-09-19"
    assert len(d["jours"]) == 2


def test_des_bornes_illisibles_sont_refusees(client, monkeypatch):
    poser(monkeypatch)
    assert client.get("/api/reconciliation/daily?from=hier").status_code == 400
    assert client.get("/api/reconciliation/daily?from=2026-09-20&to=2026-09-18").status_code == 400


@pytest.mark.parametrize("role", [None])
def test_la_route_est_fermee(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    assert flask_app.app.test_client().get("/api/reconciliation/daily").status_code == 401
