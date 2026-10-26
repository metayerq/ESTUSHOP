"""
LES JOURS ET HORAIRES D'OUVERTURE, RÉGLABLES ET DATÉS.

⚠️ LE CAFÉ OUVRE LE MARDI À PARTIR DU 27/10/2026. Les jours d'ouverture étaient écrits dans
`config.py` : le planning refusait tout service un mardi (« fermé »), et les charges du mois se
divisaient par des mois de cinq jours par semaine. Les changer dans le code aurait rouvert, d'un
coup, tous les mardis depuis juin.
"""

from datetime import date

import pytest

import app as flask_app
import calendrier as cal
import charges as ch
import config

MARDI_AVANT = date(2026, 10, 20)
MARDI_OUVERT = date(2026, 10, 27)
MERCREDI = date(2026, 10, 28)

MARDI_DES_LE_27 = {"regimes": [{
    "depuis": "2026-10-27",
    "jours": {str(wd): {"ouvre": "08:30", "ferme": "18:00"} for wd in (0, 1, 3, 4, 5, 6)},
}]}


@pytest.fixture
def regimes():
    """Branche un calendrier le temps d'un test, puis rend la source d'avant."""
    avant = config._SOURCE_CALENDRIER
    flask_app._CAL_CACHE["v"] = None

    def brancher(valeur):
        r = cal.construire(valeur, config.REGIME_USINE)
        config.brancher_calendrier(lambda: r)
        return r
    yield brancher
    config.brancher_calendrier(avant)
    flask_app._CAL_CACHE["v"] = None


# ── Le calcul ────────────────────────────────────────────────────────────────────────────────

def test_sans_reglage_le_calendrier_est_celui_dhier(regimes):
    regimes(None)
    assert config.count_open_days_raw(MARDI_OUVERT, MERCREDI) == 0
    assert config.count_open_days_raw(date(2026, 10, 26), date(2026, 10, 26)) == 1


def test_le_mardi_ouvre_a_partir_de_sa_date_et_pas_avant(regimes):
    """⚠️ LE CŒUR DE L'AFFAIRE : le mardi 20 reste fermé, le mardi 27 ouvre."""
    regimes(MARDI_DES_LE_27)
    assert config.count_open_days_raw(MARDI_OUVERT, MARDI_OUVERT) == 1
    assert config.count_open_days_raw(MARDI_AVANT, MARDI_AVANT) == 0
    assert config.count_open_days_raw(MERCREDI, MERCREDI) == 0


def test_un_premier_regime_ne_remonte_pas_dans_le_passe():
    """
    ⚠️ LE PIÈGE DE LA PREMIÈRE VALEUR. Enregistré seul, « mardi ouvert dès le 27/10 » serait le
    seul régime connu ; sans le régime d'origine remis en tête, juillet aurait ses mardis.
    """
    r = cal.valider(MARDI_DES_LE_27, config.REGIME_USINE)
    assert [x["depuis"] for x in r] == [config.SCHEDULE_CUTOVER, MARDI_OUVERT]
    assert not cal.ouvert_selon(date(2026, 7, 7), r)


def test_le_diviseur_des_charges_suit_le_calendrier(regimes):
    """
    Octobre 2026 comptait 23 jours ouverts ; avec le mardi 27, il en compte 24. Le loyer du mois
    se répartit sur 24 journées : chacune en porte moins, le mois en porte autant.
    """
    est_ouvert = lambda j: config.count_open_days_raw(j, j) == 1
    regimes(None)
    assert ch.jours_ouverts_du_mois(date(2026, 10, 15), est_ouvert) == 23
    regimes(MARDI_DES_LE_27)
    assert ch.jours_ouverts_du_mois(date(2026, 10, 15), est_ouvert) == 24
    assert ch.jours_ouverts_du_mois(date(2026, 9, 15), est_ouvert) == 20, "septembre a bougé"
    # Novembre : 22 jours sur l'ancien calendrier, et quatre mardis de plus.
    assert ch.jours_ouverts_du_mois(date(2026, 11, 15), est_ouvert) == 26


def test_un_mardi_ouvert_avec_tickets_nest_pas_compte_deux_fois(regimes):
    """
    ⚠️ `_tx_per_open_day` AJOUTAIT UN JOUR pour chaque journée à tickets hors `OPEN_WEEKDAYS` —
    un mardi d'événement privé. Une fois le mardi au calendrier, il était compté par le
    calendrier ET par cette rallonge.
    """
    regimes(MARDI_DES_LE_27)
    rows = [{"day": "2026-10-27", "nb": 40}]
    r = flask_app._tx_per_open_day(rows, MARDI_OUVERT, MARDI_OUVERT, date(2026, 10, 29))
    assert r["tx_basis_days"] == 1 and r["tx_per_open_day"] == 40.0


# ── La validation ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("abime", [
    {"regimes": [{"depuis": "2026-10-27", "jours": {"1": {"ouvre": "18:00", "ferme": "08:30"}}}]},
    {"regimes": [{"depuis": "2026-10-27", "jours": {"1": {"ouvre": "8h30", "ferme": None}}}]},
    {"regimes": [{"depuis": "2026-10-27", "jours": {"7": {}}}]},
    {"regimes": [{"depuis": "2026-05-01", "jours": {"1": {}}}]},
    {"regimes": [{"depuis": "2026-10-27", "jours": {}}, {"depuis": "2026-10-27", "jours": {}}]},
    {"regimes": "mardi"},
])
def test_une_valeur_abimee_est_refusee_et_ne_sapplique_pas_a_moitie(abime):
    with pytest.raises(cal.CalendrierInvalide):
        cal.valider(abime, config.REGIME_USINE)
    assert cal.construire(abime, config.REGIME_USINE) == [config.REGIME_USINE]


def test_une_heure_inconnue_nest_pas_inventee():
    """« Ouvert le mardi, heures pas encore fixées » est un état légitime : pas de 08:00 inventé."""
    r = cal.valider({"regimes": [{"depuis": "2026-10-27", "jours": {"1": {}}}]}, config.REGIME_USINE)
    assert cal.horaires_du(MARDI_OUVERT, r) == {"ouvre": None, "ferme": None}


# ── L'écran et l'API ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def base(monkeypatch, regimes):
    """Une base en mémoire pour `reglages`, un admin, et le 26/10/2026."""
    lignes = {}
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_identite", lambda: ("admin", "quentin"))
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 10, 26))
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a, **k: None)

    def get(table, params=None):
        assert table == "reglages"
        return [lignes["calendrier"]] if "calendrier" in lignes else []

    def upsert(table, data, on_conflict=None):
        lignes[data["cle"]] = data
        return True, None
    monkeypatch.setattr(flask_app, "_supa_get", get)
    monkeypatch.setattr(flask_app, "_supa_upsert", upsert)
    config.brancher_calendrier(flask_app._calendrier_courant)
    flask_app.app.config["TESTING"] = True
    return lignes


def test_enregistrer_le_mardi_rouvre_le_planning(base):
    c = flask_app.app.test_client()
    r = c.put("/api/parametres/calendrier", json=MARDI_DES_LE_27)
    assert r.status_code == 200 and r.get_json()["ok"]
    assert config.count_open_days_raw(MARDI_OUVERT, MARDI_OUVERT) == 1
    lu = c.get("/api/parametres/calendrier").get_json()
    assert [x["depuis"] for x in lu["regimes"]] == ["2026-06-12", "2026-10-27"]
    assert lu["regimes"][1]["jours"]["1"] == {"ouvre": "08:30", "ferme": "18:00"}


def test_un_mois_clos_ne_change_pas_douverture(base):
    """
    ⚠️ SEPTEMBRE EST CLOS LE 26 OCTOBRE. Ouvrir ses mardis redivise son loyer et son point mort,
    des chiffres déjà lus. Le mois en cours, lui, reste modifiable.
    """
    c = flask_app.app.test_client()
    sept = {"regimes": [{"depuis": "2026-09-01", "jours": MARDI_DES_LE_27["regimes"][0]["jours"]}]}
    r = c.put("/api/parametres/calendrier", json=sept)
    assert r.status_code == 409 and "2026-09-01" in r.get_json()["error"]
    assert "calendrier" not in base, "le refus a quand même écrit"
    octobre = {"regimes": [{"depuis": "2026-10-20", "jours": MARDI_DES_LE_27["regimes"][0]["jours"]}]}
    assert c.put("/api/parametres/calendrier", json=octobre).status_code == 200


def test_les_heures_dun_mois_clos_restent_modifiables(base):
    """Les heures ne divisent rien : les renseigner pour juin ne touche à aucun chiffre."""
    jours = {str(wd): {"ouvre": "08:30", "ferme": "18:00"} for wd in sorted(config.OPEN_WEEKDAYS)}
    r = flask_app.app.test_client().put("/api/parametres/calendrier",
                                        json={"regimes": [{"depuis": "2026-06-12", "jours": jours}]})
    assert r.status_code == 200


def test_un_calendrier_illisible_est_refuse_sans_ecrire(base):
    r = flask_app.app.test_client().put("/api/parametres/calendrier", json={"regimes": "mardi"})
    assert r.status_code == 400 and "calendrier" not in base


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_regle_le_calendrier(base, monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    c = flask_app.app.test_client()
    assert c.put("/api/parametres/calendrier", json=MARDI_DES_LE_27).status_code in (401, 403)
    assert c.get("/api/parametres/calendrier").status_code in (401, 403)
    assert "calendrier" not in base


def test_une_base_injoignable_garde_le_dernier_calendrier_lu(base, monkeypatch):
    """
    ⚠️ UN HOQUET NE REFERME PAS LE MARDI. Retomber sur le régime du code pendant trente secondes
    redivise les charges d'octobre sans que rien n'ait bougé.
    """
    c = flask_app.app.test_client()
    c.put("/api/parametres/calendrier", json=MARDI_DES_LE_27)
    assert config.count_open_days_raw(MARDI_OUVERT, MARDI_OUVERT) == 1

    def panne(table, params=None):
        raise ConnectionError("Supabase injoignable")
    monkeypatch.setattr(flask_app, "_supa_get", panne)
    flask_app._CAL_CACHE["t"] = 0.0           # le cache a expiré
    assert config.count_open_days_raw(MARDI_OUVERT, MARDI_OUVERT) == 1


def test_le_planning_recoit_les_heures_des_jours_ouverts(base, monkeypatch):
    flask_app.app.test_client().put("/api/parametres/calendrier", json=MARDI_DES_LE_27)
    vrai_get = flask_app._supa_get

    def get(table, params=None):
        return vrai_get(table, params) if table == "reglages" else []
    monkeypatch.setattr(flask_app, "_supa_get", get)
    d = flask_app.app.test_client().get(
        "/api/shifts?from=2026-10-26&to=2026-11-01").get_json()
    assert "2026-10-27" in d["couts"], "le mardi reste fermé au planning"
    assert d["horaires"]["2026-10-27"] == {"ouvre": "08:30", "ferme": "18:00"}
    assert "2026-10-28" not in d["couts"]
