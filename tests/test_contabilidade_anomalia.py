# -*- coding: utf-8 -*-
"""
LES VENTES PAR CARTE NE PEUVENT PAS DÉPASSER LES VENTES TOTALES.

⚠️ L'INVARIANT EST ARITHMÉTIQUE, DONC SA VIOLATION DIT TOUJOURS QUELQUE CHOSE. `cartao` est
une PARTIE de `vendas`. Quand il le dépasse, c'est que le terminal a encaissé quelque chose
qui n'est pas une vente du jour.

Les devoluções du terminal expliquaient l'essentiel des dépassements et sont désormais
déduites de `cartao` — mais pas tous. Mesuré sur septembre 2026 APRÈS cette correction : cinq
jours dépassent encore, pour 146,20 €. Le 23/09 est le plus parlant — Revolut n'enregistre
aucun remboursement quand Vendus porte 48,50 € d'avoirs.

Un comptable qui lit ça conclut à des ventes non déclarées, ou s'alarme pour rien. Ces tests
tiennent le fait qu'on le lui dit — et qu'on ne le dit QUE quand il y a lieu.
"""
import pytest
import app as A


@pytest.fixture
def mois(monkeypatch):
    """Construit les mois à partir de deux sources bouchonnées, sans toucher au réseau."""
    def bati(ventes_par_jour, revolut_par_jour):
        monkeypatch.setattr(A, "_fetch_summaries",
                            lambda a, b: [{"day": j, "ca_ttc": v} for j, v in ventes_par_jour.items()])
        monkeypatch.setattr(A, "_get_today_docs_cached", lambda *a, **k: [])
        monkeypatch.setattr(A, "_load_revolut_days", lambda: revolut_par_jour)
        monkeypatch.setattr(A, "_fee_invoices", lambda: {})
        return A._contabilidade_months()
    return bati


def jour(mois_rendus, iso):
    for m in mois_rendus:
        for d in m["days"]:
            if d["day"] == iso:
                return d
    raise AssertionError(f"{iso} absent")


# ── Le cas réel du 23 septembre ──────────────────────────────────────────────────────────────

def test_essais_rembourses_le_jour_est_signale(mois):
    # Le cas réel du 23/09 : aucune devolução côté Revolut, 48,50 € d'avoirs côté Vendus.
    ms = mois({"2026-09-23": 0.0},
              {"2026-09-23": {"gross": 76.50, "tips": 0.0, "fees": 0.82,
                              "net": 75.68, "refunds": 0.0, "tx": 9}})
    d = jour(ms, "2026-09-23")
    assert d["anomalia"] is True
    assert d["excesso"] == 76.50
    assert ms[0]["anomalias"] == 1
    assert ms[0]["excesso"] == 76.50


def test_une_journee_normale_ne_signale_rien(mois):
    # ⚠️ LA PAGE NE PARLE QUE QUAND IL Y A QUELQUE CHOSE À DIRE. Un avertissement permanent
    # cesse d'être lu, et c'est celui du jour qui compte qu'on rate alors.
    ms = mois({"2026-09-26": 351.30},
              {"2026-09-26": {"gross": 351.38, "tips": 4.58, "fees": 5.44, "net": 345.94, "tx": 36}})
    d = jour(ms, "2026-09-26")
    assert d["anomalia"] is False
    assert d["excesso"] == 0.0
    assert ms[0]["anomalias"] == 0


def test_les_gorjetas_ne_declenchent_pas_l_alerte(mois):
    """
    ⚠️ LE PIÈGE LE PLUS FACILE. Un pourboire fait dépasser le TPA au-delà des ventes, ce qui est
    normal : il transite par le terminal sans être de la facturation. C'est pour ça que
    l'invariant porte sur `cartao` — le TPA MOINS les gorjetas — et jamais sur le TPA brut.
    """
    ms = mois({"2026-09-19": 354.70},
              {"2026-09-19": {"gross": 356.68, "tips": 18.78, "fees": 5.0, "net": 351.68, "tx": 36}})
    assert jour(ms, "2026-09-19")["anomalia"] is False


def test_un_centime_d_ecart_ne_declenche_rien(mois):
    # Les arrondis des deux sources ne doivent pas produire une alerte par jour.
    ms = mois({"2026-09-10": 100.00},
              {"2026-09-10": {"gross": 100.01, "tips": 0.0, "fees": 0.0, "net": 100.01, "tx": 1}})
    assert jour(ms, "2026-09-10")["anomalia"] is False


def test_le_depassement_reel_est_chiffre(mois):
    ms = mois({"2026-09-05": 262.70},
              {"2026-09-05": {"gross": 330.99, "tips": 12.09, "fees": 5.0, "net": 325.99, "tx": 23}})
    d = jour(ms, "2026-09-05")
    assert d["anomalia"] is True
    assert d["excesso"] == pytest.approx(56.20, abs=0.01)


def test_plusieurs_jours_se_cumulent_dans_le_mois(mois):
    ms = mois({"2026-09-22": 0.0, "2026-09-23": 0.0, "2026-09-24": 371.60},
              {"2026-09-22": {"gross": 10.00, "tips": 0.0, "fees": 0.2, "net": 9.8, "tx": 5},
               "2026-09-23": {"gross": 76.50, "tips": 0.0, "fees": 0.82, "net": 75.68, "tx": 9},
               "2026-09-24": {"gross": 372.09, "tips": 6.99, "fees": 5.0, "net": 367.09, "tx": 35}})
    assert ms[0]["anomalias"] == 2
    assert ms[0]["excesso"] == pytest.approx(86.50, abs=0.01)
    assert jour(ms, "2026-09-24")["anomalia"] is False


# ── Ce que la page en fait ───────────────────────────────────────────────────────────────────

def test_le_gabarit_porte_le_signalement():
    """
    ⚠️ LE CALCUL NE SERT À RIEN S'IL N'ARRIVE PAS À L'ÉCRAN. Le gabarit est du JavaScript dans
    une chaîne : rien ne le compile, donc rien ne signalerait la disparition de ce bloc.
    """
    src = open("templates/contabilidade.html", encoding="utf-8").read()
    assert "m.anomalias > 0" in src, "la note mensuelle a disparu du gabarit"
    assert "d.anomalia" in src, "la marque du jour a disparu du gabarit"
    assert "não são vendas não declaradas" in src.lower(), \
        "l'explication a disparu — sans elle, le signalement inquiète au lieu d'informer"


def test_une_devolucao_deja_deduite_ne_declenche_pas_l_alerte(mois):
    """
    ⚠️ LA CORRECTION EN AMONT DOIT ÊTRE RESPECTÉE. `cartao` est déjà net des devoluções depuis
    l'import des Refund : recompter le dépassement sur le brut rallumerait une alerte sur
    chaque jour de remboursement, c'est-à-dire précisément les jours qu'on vient d'expliquer.
    """
    ms = mois({"2026-09-22": 0.0},
              {"2026-09-22": {"gross": 10.00, "tips": 0.0, "fees": 0.2,
                              "net": 9.8, "refunds": 10.00, "tx": 5}})
    assert jour(ms, "2026-09-22")["anomalia"] is False
    assert ms[0]["anomalias"] == 0
