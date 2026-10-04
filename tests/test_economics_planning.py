# -*- coding: utf-8 -*-
"""
LE POINT MORT, JOUR PAR JOUR — DE BOUT EN BOUT.

⚠️ CE FICHIER COMBLE UN TROU QUE J'AI DÉCOUVERT EN CHANGEANT LE DIVISEUR. `charges.py` est
couvert pièce par pièce, mais `daily_economics` — qui assemble tout et alimente le dashboard,
la comptabilité et la caisse — n'était testé nulle part de bout en bout. J'ai remplacé la
constante `JOURS_OUVERTS_MOIS` par le vrai calendrier et les 1809 tests sont restés verts.

⚠️ ET LA LIGNE DU GRAPHE EST LE PIÈGE. Tant que le coût était le même tous les jours, une
moyenne suffisait. Elle ne suffit plus : tracer la moyenne au-dessus d'un samedi à deux extras
et d'un lundi en solo ferait croire que le lundi a manqué sa journée alors qu'il l'a payée.
"""
from datetime import date

import pytest

import vendus as V
from config import count_open_days_raw


BARISTA = {"person_id": "p-bar", "name": "Marco", "type": "full_time",
           "gross_monthly": 1200.0, "meal_card_daily": 10.20, "tsu_exempt": False,
           "valid_from": "2026-05-01", "valid_to": None, "active": True}
ANA = {"person_id": "p-ana", "name": "Ana", "type": "extra", "gross_monthly": 0,
       "hourly_rate": 12.0, "valid_from": "2026-05-01", "valid_to": None, "active": True}
LOYER = {"name": "Loyer", "amount": 700.0, "frequency": "monthly",
         "valid_from": None, "valid_to": None, "active": True}


def docs(jours):
    """Un document par jour, montants ronds — ce test porte sur les coûts, pas sur le CA."""
    return [{"local_time": f"{j} 12:00:00", "amount_gross": 1130.0, "amount_net": 1000.0,
             "items": []} for j in jours]


@pytest.fixture
def base(monkeypatch):
    """Les tables, pilotables test par test."""
    etat = {"charges_fixes": [LOYER], "employees": [BARISTA, ANA], "shifts": []}
    monkeypatch.setattr(V, "_supa_get_economics",
                        lambda t, p=None: list(etat.get(t, [])))
    return etat


def eco(d0, d1, **kw):
    """`cogs_agg` fixe une marge mesurée de 70 % : sans elle, pas de point mort calculable."""
    jours = [d0.isoformat()]
    return V.daily_economics(docs(jours), {}, from_date=d0, to_date=d1,
                             cogs_agg=(300.0, 1000.0, 1000.0), **kw)


# ── La série par jour ───────────────────────────────────────────────────────────────────────

def test_LE_POINT_MORT_EST_RENDU_JOUR_PAR_JOUR(base):
    d = eco(date(2026, 10, 5), date(2026, 10, 11))
    serie = d["seuil_ca_ttc_par_jour"]
    assert serie, "sans série, la ligne du graphe reste horizontale sur un coût qui ne l'est plus"
    # Lundi, jeudi, vendredi, samedi, dimanche : mardi et mercredi sont fermés.
    assert set(serie) == {"2026-10-05", "2026-10-08", "2026-10-09",
                          "2026-10-10", "2026-10-11"}


def test_UN_JOUR_AVEC_UN_EXTRA_A_UN_POINT_MORT_PLUS_HAUT(base):
    """Le cœur de la demande : le planning doit se répercuter sur le seuil du jour."""
    sans = eco(date(2026, 10, 5), date(2026, 10, 11))["seuil_ca_ttc_par_jour"]
    base["shifts"] = [{"person_id": "p-ana", "day": "2026-10-10",
                       "start_time": "09:00", "end_time": "17:00"}]
    avec = eco(date(2026, 10, 5), date(2026, 10, 11))["seuil_ca_ttc_par_jour"]

    assert avec["2026-10-10"] > sans["2026-10-10"], "le samedi devrait coûter plus cher"
    assert avec["2026-10-09"] == pytest.approx(sans["2026-10-09"]), (
        "le vendredi n'a aucun service en plus : son seuil ne doit pas bouger")


def test_les_jours_fermes_nont_pas_de_point_mort(base):
    """Mardi et mercredi : rien n'ouvre, il n'y a pas de journée à payer."""
    serie = eco(date(2026, 10, 5), date(2026, 10, 11))["seuil_ca_ttc_par_jour"]
    assert "2026-10-06" not in serie and "2026-10-07" not in serie


def test_la_moyenne_reste_rendue_pour_les_ecrans_qui_la_lisent(base):
    """`seuil_ca_ttc_jour` alimente encore plusieurs cartes : le retirer les viderait."""
    d = eco(date(2026, 10, 5), date(2026, 10, 11))
    assert d["seuil_ca_ttc_jour"] is not None


# ── Le diviseur ─────────────────────────────────────────────────────────────────────────────

def test_LE_DIVISEUR_EST_CELUI_DU_MOIS_PAS_LA_CONSTANTE(base):
    """
    ⚠️ 21,25 ÉTAIT UNE SAISIE DU BUSINESS PLAN. Octobre a 23 services et février 20 : la même
    paie répartie sur 23 jours coûte 8 % de moins par jour que sur 21,25.
    """
    from config import JOURS_OUVERTS_MOIS
    import charges as ch

    # ⚠️ `cout_perso_jour` PORTE EN FAIT LE TOTAL DE LA PÉRIODE — un nom hérité, gardé pour
    # `dashboard.js`. Sur une période d'UN jour les deux coïncident, d'où la fenêtre serrée.
    d = eco(date(2026, 10, 5), date(2026, 10, 5))
    attendu = round(ch.cout_employe_mensuel(BARISTA) / 23, 2)      # octobre 2026 : 23 services
    faux    = round(ch.cout_employe_mensuel(BARISTA) / JOURS_OUVERTS_MOIS, 2)
    assert d["cout_perso_jour"] == pytest.approx(attendu, abs=0.01)
    assert abs(d["cout_perso_jour"] - faux) > 0.5, (
        "le diviseur du business plan donnerait un coût sensiblement différent : "
        "si les deux se valent, le changement n'a pas pris")


def test_fevrier_coute_plus_cher_par_jour_quoctobre(base):
    """20 services contre 23 : la même paie, répartie sur moins de journées."""
    oct_ = eco(date(2026, 10, 5), date(2026, 10, 5))["cout_perso_jour"]
    fev  = eco(date(2027, 2, 1),  date(2027, 2, 1))["cout_perso_jour"]
    assert fev > oct_


# ── La promesse de la bascule ───────────────────────────────────────────────────────────────

def test_AVANT_LA_BASCULE_LE_COUT_DES_EXTRAS_NE_DISPARAIT_PAS(base):
    """
    ⚠️ SEPTEMBRE N'A AUCUN SHIFT. Sans la borne, son coût de personnel chuterait du montant des
    extras APRÈS avoir été lu, et le point mort d'un mois clos deviendrait faux.
    """
    extra_au_forfait = dict(ANA, gross_monthly=400.0)
    base["employees"] = [BARISTA, extra_au_forfait]
    import charges as ch

    sept = eco(date(2026, 9, 4), date(2026, 9, 4))
    n = ch.jours_ouverts_du_mois(date(2026, 9, 4),
                                 lambda j: count_open_days_raw(j, j) == 1)
    assert n == 20, "septembre 2026 compte 20 services — mesuré, pas supposé"
    attendu = (ch.cout_employe_mensuel(BARISTA)
               + ch.cout_employe_mensuel(extra_au_forfait)) / n
    assert sept["cout_perso_jour"] == pytest.approx(round(attendu, 2), abs=0.01)


def test_apres_la_bascule_le_forfait_de_lextra_ne_compte_plus(base):
    """Sinon il serait payé deux fois : son forfait lissé ET ses heures."""
    import charges as ch
    base["employees"] = [BARISTA, dict(ANA, gross_monthly=400.0)]
    oct_ = eco(date(2026, 10, 5), date(2026, 10, 5))
    assert oct_["cout_perso_jour"] == pytest.approx(
        round(ch.cout_employe_mensuel(BARISTA) / 23, 2), abs=0.01)


# ── Ce qui ne doit pas tomber ───────────────────────────────────────────────────────────────

def test_une_base_injoignable_ne_fait_pas_tomber_le_dashboard(base, monkeypatch):
    def casse(t, p=None):
        raise RuntimeError("supabase muet")
    monkeypatch.setattr(V, "_supa_get_economics", casse)
    d = eco(date(2026, 10, 5), date(2026, 10, 11))
    assert d["charges_source"] == "indisponible"
    assert d["seuil_ca_ttc_par_jour"] == {}


def test_sans_marge_mesurable_aucun_seuil_nest_invente(base):
    """Pas de COGS couvert → pas de taux de marge → pas de point mort, ni moyen ni par jour."""
    d = V.daily_economics(docs(["2026-10-05"]), {}, from_date=date(2026, 10, 5),
                          to_date=date(2026, 10, 11), cogs_agg=(0.0, 0.0, 0.0))
    assert d["seuil_ca_ttc_jour"] is None
    assert d["seuil_ca_ttc_par_jour"] == {}


def test_LE_CHEMIN_SANS_BORNES_UTILISE_AUSSI_LE_VRAI_DIVISEUR(base, monkeypatch):
    """
    ⚠️ CETTE BRANCHE EXISTE POUR LES APPELS HISTORIQUES, et elle était restée sur la constante.
    Mes premiers tests passaient tous des dates : remettre `JOURS_OUVERTS_MOIS` ici ne faisait
    rougir personne. Trouvé par mutation.
    """
    import config
    import charges as ch
    monkeypatch.setattr(config, "today_lisbon", lambda: date(2026, 10, 15))

    d = V.daily_economics(docs(["2026-10-15"]), {}, cogs_agg=(300.0, 1000.0, 1000.0))
    attendu = round(ch.cout_employe_mensuel(BARISTA) / 23, 2)     # octobre : 23 services
    assert d["cout_perso_jour"] == pytest.approx(attendu, abs=0.01)


def test_sans_bornes_aucune_serie_par_jour_nest_inventee(base, monkeypatch):
    """On ne sait pas quels jours la période couvre : rendre une série serait l'inventer."""
    import config
    monkeypatch.setattr(config, "today_lisbon", lambda: date(2026, 10, 15))
    d = V.daily_economics(docs(["2026-10-15"]), {}, cogs_agg=(300.0, 1000.0, 1000.0))
    assert d["seuil_ca_ttc_par_jour"] == {}
