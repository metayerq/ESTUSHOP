# -*- coding: utf-8 -*-
"""
LE POINT MORT LISSÉ — `_cout_mois_jour`.

Le dashboard peut afficher, au choix, le point mort MOYEN du mois : un repère constant, là où
le coût d'un jour précis saute avec les extras. Ce coût moyen doit (1) se diviser par les VRAIS
jours ouverts du mois — pas une constante — et (2) inclure les extras du planning. Deux pièges
qui, muets, rendraient la moyenne fausse d'un mois à l'autre.
"""
from datetime import date

import pytest

import app
import charges as _ch
from config import count_open_days_raw


LOYER = {"name": "Loyer", "amount": 700.0, "frequency": "monthly",
         "valid_from": None, "valid_to": None, "active": True}
BARISTA = {"person_id": "p-bar", "name": "Marco", "type": "full_time",
           "gross_monthly": 1200.0, "meal_card_daily": 10.20, "tsu_exempt": False,
           "valid_from": "2026-05-01", "valid_to": None, "active": True}
ANA = {"person_id": "p-ana", "name": "Ana", "type": "extra", "gross_monthly": 0,
       "hourly_rate": 10.0, "valid_from": "2026-05-01", "valid_to": None, "active": True}
# Ana tous les samedis (jour ouvert), 8 h — après la bascule planning du 01/10.
SAT_RULE = {"id": "r-sat", "person_id": "p-ana", "weekday": 5,
            "start_time": "08:00", "end_time": "16:00",
            "valid_from": "2026-10-01", "valid_to": None}


@pytest.fixture
def base(monkeypatch):
    etat = {"charges_fixes": [LOYER], "employees": [BARISTA, ANA],
            "shifts": [], "shift_rules": []}
    monkeypatch.setattr(app, "_supa_get", lambda t, p=None: list(etat.get(t, [])))
    return etat


def _ouverts_nov():
    eo = lambda j: count_open_days_raw(j, j) == 1
    return _ch.jours_ouverts_entre(date(2026, 11, 1), date(2026, 11, 30), eo)


def test_LISSE_DIVISE_PAR_LES_VRAIS_JOURS_OUVERTS(base):
    ref = date(2026, 11, 15)
    n = len(_ouverts_nov())
    attendu = (_ch.charges_mensuelles([LOYER], ref)
               + _ch.personnel_mensuel([BARISTA, ANA], ref)) / n
    assert app._cout_mois_jour(ref) == pytest.approx(attendu)


def test_LISSE_INCLUT_LES_EXTRAS_DU_PLANNING(base):
    base["shift_rules"] = [SAT_RULE]
    ref = date(2026, 11, 15)
    n = len(_ouverts_nov())
    sans = (_ch.charges_mensuelles([LOYER], ref)
            + _ch.personnel_mensuel([BARISTA, ANA], ref)) / n
    samedis = sum(1 for j in _ouverts_nov() if j.weekday() == 5)
    hausse = samedis * 8 * ANA["hourly_rate"] / n
    assert app._cout_mois_jour(ref) == pytest.approx(sans + hausse)


def test_LISSE_SANS_BASE_REND_NONE(base, monkeypatch):
    # Aucun jour ouvert lisible → pas de moyenne inventée.
    monkeypatch.setattr(app._ch, "jours_ouverts_entre", lambda *a, **k: [])
    assert app._cout_mois_jour(date(2026, 11, 15)) is None


# ── Prep : jours fermés travaillés, et jours « prep seuls » ───────────────────────────────────

import charges as _ch2
from config import PLANNING_CUTOVER

ZOE = {"person_id": "p-zoe", "name": "Zoé", "type": "extra", "gross_monthly": 0,
       "hourly_rate": 10.0, "valid_from": "2026-05-01", "valid_to": None, "active": True}


def _n_ouverts():
    return len(_ouverts_nov())


def test_PREP_UN_JOUR_FERME_EST_COMPTE_ET_REPARTI(base):
    # Mercredi 2026-11-04 est fermé (REGIME_USINE : mar/mer fermés). Zoé y fait les prep, 8 h.
    base["employees"] = [BARISTA, ZOE]
    base["shifts"] = [{"person_id": "p-zoe", "day": "2026-11-04",
                       "start_time": "08:00", "end_time": "16:00",
                       "annule": False, "rule_id": None, "prep": True}]
    ref = date(2026, 11, 15)
    n = _n_ouverts()
    base_cout = (_ch.charges_mensuelles([LOYER], ref)
                 + _ch.personnel_mensuel([BARISTA, ZOE], ref)) / n
    attendu = base_cout + (8 * ZOE["hourly_rate"]) / n     # 80 € étalés sur les jours ouverts
    assert app._cout_mois_jour(ref) == pytest.approx(attendu)


def test_UN_JOUR_PREP_SEUL_EST_FERME_AUX_CLIENTS():
    # Un samedi (ouvert) où seule Zoé fait les prep : plus de jour ouvert aux clients.
    shifts = [{"person_id": "p-zoe", "day": "2026-11-07",
               "start_time": "08:00", "end_time": "16:00",
               "annule": False, "rule_id": None, "prep": True}]
    eo = lambda j: count_open_days_raw(j, j) == 1
    assert _ch2.jour_prep_seul(date(2026, 11, 7), [], shifts) is True
    clients = _ch2.jours_ouverts_clients(date(2026, 11, 1), date(2026, 11, 30), eo, [], shifts)
    assert date(2026, 11, 7) not in clients
    assert len(clients) == len(_ouverts_nov()) - 1


def test_UN_SERVICE_NON_PREP_GARDE_LE_JOUR_OUVERT():
    # Si quelqu'un sert (créneau non-prep) ce samedi, le jour reste ouvert aux clients.
    shifts = [{"person_id": "p-zoe", "day": "2026-11-07",
               "start_time": "08:00", "end_time": "16:00",
               "annule": False, "rule_id": None, "prep": False}]
    assert _ch2.jour_prep_seul(date(2026, 11, 7), [], shifts) is False
