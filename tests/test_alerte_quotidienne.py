# -*- coding: utf-8 -*-
"""
L'ALERTE NE PARLE QUE QUAND IL Y A QUELQUE CHOSE À DIRE.

⚠️ C'EST SA SEULE QUALITÉ, ET LA PLUS FRAGILE. Un rapport qui annonce tous les soirs que tout
va bien cesse d'être lu au bout d'une semaine — et c'est celui du jour qui compte qu'on rate
alors. Mesuré sur septembre 2026 : sans seuil, l'alerte partirait cinq fois dans le mois dont
trois pour quelques euros d'essais de terminal un mardi. Avec le seuil, deux fois, méritées.

⚠️ ET ELLE NE REFAIT PAS LE RAPPROCHEMENT. Les ventes par carte sont une PARTIE des ventes :
`cartao` ne peut pas dépasser `vendas`. De l'arithmétique sur deux totaux, pas un appariement —
sinon on aurait deux vérités concurrentes, celle du POS et celle-ci.
"""
import pytest
import app as A


@pytest.fixture(autouse=True)
def sans_reseau(monkeypatch):
    monkeypatch.setattr(A, "_get_today_docs_cached", lambda *a, **k: [])
    monkeypatch.setattr(A, "_fee_invoices", lambda: {})
    monkeypatch.delenv("CRON_SECRET", raising=False)


def _poser(monkeypatch, ventes, revolut):
    monkeypatch.setattr(A, "_fetch_summaries",
                        lambda a, b: [{"day": j, "ca_ttc": v} for j, v in ventes.items()])
    monkeypatch.setattr(A, "_load_revolut_days", lambda: revolut)


JOUR = "2026-09-23"
REV = {"gross": 76.50, "tips": 0.0, "fees": 0.82, "net": 75.68, "refunds": 0.0, "tx": 9}


# ── Quand elle parle ────────────────────────────────────────────────────────────────────────

def test_le_cas_reel_du_23_septembre(monkeypatch):
    _poser(monkeypatch, {JOUR: 0.0}, {JOUR: REV})
    texte = A._alerte_du_jour(JOUR)
    assert texte is not None
    assert "76.50" in texte and "0.00" in texte
    assert "23/09" in texte


def test_une_journee_normale_ne_dit_rien(monkeypatch):
    _poser(monkeypatch, {"2026-09-26": 351.30},
           {"2026-09-26": {"gross": 351.38, "tips": 4.58, "fees": 5.44, "net": 345.94,
                           "refunds": 0.0, "tx": 36}})
    assert A._alerte_du_jour("2026-09-26") is None


def test_sous_le_seuil_on_se_tait(monkeypatch):
    # ⚠️ Trois des cinq dépassements de septembre étaient des essais à quelques euros. Les
    # signaler apprendrait à ignorer les deux qui comptaient.
    _poser(monkeypatch, {JOUR: 0.0},
           {JOUR: {"gross": 6.00, "tips": 0.0, "fees": 0.0, "net": 6.0, "refunds": 0.0, "tx": 3}})
    assert A._alerte_du_jour(JOUR) is None


def test_les_gorjetas_ne_declenchent_rien(monkeypatch):
    # Un pourboire fait légitimement dépasser le TPA : il transite sans être de la faturação.
    _poser(monkeypatch, {JOUR: 300.00},
           {JOUR: {"gross": 330.00, "tips": 30.00, "fees": 5.0, "net": 325.0,
                   "refunds": 0.0, "tx": 30}})
    assert A._alerte_du_jour(JOUR) is None


def test_les_devolucoes_deja_deduites_ne_declenchent_rien(monkeypatch):
    # ⚠️ La correction en amont doit être respectée : `cartao` est déjà net des remboursements.
    _poser(monkeypatch, {JOUR: 0.0},
           {JOUR: {"gross": 76.50, "tips": 0.0, "fees": 0.82, "net": 75.68,
                   "refunds": 76.50, "tx": 9}})
    assert A._alerte_du_jour(JOUR) is None


def test_un_jour_inconnu_ne_dit_rien(monkeypatch):
    _poser(monkeypatch, {JOUR: 0.0}, {JOUR: REV})
    assert A._alerte_du_jour("2026-01-01") is None


# ── La route ────────────────────────────────────────────────────────────────────────────────

def test_la_route_envoie_et_marque(monkeypatch):
    _poser(monkeypatch, {JOUR: 0.0}, {JOUR: REV})
    envois, marques = [], []
    monkeypatch.setattr(A, "_envoyer_alerte", lambda t: (envois.append(t), (True, "ok"))[1])
    monkeypatch.setattr(A, "_alerte_deja_envoyee",
                        lambda d, marquer=False: (marques.append(d), False)[1] if marquer else False)
    r = A.app.test_client().get(f"/api/cron/alerte?day={JOUR}")
    assert r.status_code == 200 and r.get_json()["envoye"] is True
    assert len(envois) == 1 and marques == [JOUR]


def test_une_alerte_ne_part_pas_deux_fois(monkeypatch):
    # ⚠️ Le cron peut être rejoué. Recevoir deux fois le même avertissement apprend à l'ignorer.
    _poser(monkeypatch, {JOUR: 0.0}, {JOUR: REV})
    envois = []
    monkeypatch.setattr(A, "_envoyer_alerte", lambda t: (envois.append(t), (True, "ok"))[1])
    monkeypatch.setattr(A, "_alerte_deja_envoyee", lambda d, marquer=False: not marquer)
    assert A.app.test_client().get(f"/api/cron/alerte?day={JOUR}").get_json()["alerte"] is False
    assert envois == []


def test_un_echec_d_envoi_ne_marque_pas_la_journee(monkeypatch):
    # Sinon l'alerte serait perdue pour toujours : le cron suivant la croirait déjà partie.
    _poser(monkeypatch, {JOUR: 0.0}, {JOUR: REV})
    marques = []
    monkeypatch.setattr(A, "_envoyer_alerte", lambda t: (False, "caisse http 500"))
    monkeypatch.setattr(A, "_alerte_deja_envoyee",
                        lambda d, marquer=False: (marques.append(d), False)[1] if marquer else False)
    r = A.app.test_client().get(f"/api/cron/alerte?day={JOUR}")
    assert r.get_json()["envoye"] is False
    assert marques == [], "une alerte non partie a été marquée comme envoyée"


def test_la_route_est_fermee_sans_le_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cr3t")
    assert A.app.test_client().get("/api/cron/alerte").status_code == 401
    _poser(monkeypatch, {}, {})
    assert A.app.test_client().get("/api/cron/alerte?key=s3cr3t").status_code == 200
