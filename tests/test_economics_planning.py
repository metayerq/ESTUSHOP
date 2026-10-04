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


# ══ LES COMMISSIONS ═════════════════════════════════════════════════════════════════════════
#
# ⚠️ ELLES ÉTAIENT AJOUTÉES APRÈS COUP, et le point mort ne les voyait pas. L'écran annonçait
# « +297,39 € de résultat — coûts couverts » en vert, à côté de « 635,70 € de ventes
# manquantes », et une marge brute de 200 %. Trois chiffres sur le même écran, tous faux
# ensemble. Aucun test ne les gardait.

CHARGES_LOURDES = {"name": "Loyer", "amount": 6000.0, "frequency": "monthly",
                   "valid_from": None, "valid_to": None, "active": True}


@pytest.fixture
def maigre(monkeypatch):
    """Trois journées à 200 € TTC, 6 000 € de loyer : le point mort est hors d'atteinte."""
    etat = {"charges_fixes": [CHARGES_LOURDES], "employees": [], "shifts": []}
    monkeypatch.setattr(V, "_supa_get_economics", lambda t, p=None: list(etat.get(t, [])))
    return etat


def _trois_jours(com=0.0):
    docs = [{"local_time": f"2026-10-{j:02d} 12:00:00", "amount_gross": 200.0,
             "amount_net": 180.0, "items": []} for j in (1, 2, 3)]
    return V.daily_economics(docs, {}, from_date=date(2026, 10, 1), to_date=date(2026, 10, 3),
                             cogs_agg=(160.0, 540.0, 540.0), marge_hors_ventes=com)


def test_UNE_COMMISSION_BAISSE_LE_POINT_MORT(maigre):
    """Chaque euro de commission est un euro de charges que les ventes n'ont plus à couvrir."""
    sans, avec = _trois_jours(0.0), _trois_jours(700.0)
    assert avec["seuil_ca_ttc"] < sans["seuil_ca_ttc"]
    # 700 € de marge sans coût, au taux mesuré : le seuil baisse de 700/taux, converti en TTC.
    baisse = sans["seuil_ca_ttc"] - avec["seuil_ca_ttc"]
    attendu = 700.0 / (sans["seuil_margin_pct"] / 100) * (1 + sans["seuil_tva_pct"] / 100)
    assert baisse == pytest.approx(attendu, rel=0.02)


def test_LE_RESULTAT_ET_LE_POINT_MORT_NE_SE_CONTREDISENT_PLUS(maigre):
    """
    ⚠️ LE DÉFAUT EXACT SIGNALÉ. Un résultat positif et un manque de ventes non nul ne peuvent
    pas coexister : si les coûts sont couverts, il ne manque rien.
    """
    for com in (0.0, 300.0, 700.0, 5000.0):
        e = _trois_jours(com)
        if e["ebitda_ht"] is not None and e["ebitda_ht"] >= 0:
            assert e["manque_seuil"] == 0, (
                f"commission {com} : résultat {e['ebitda_ht']} mais "
                f"{e['manque_seuil']} € de ventes « manquantes »")


def test_LA_MARGE_BRUTE_NE_DEPASSE_JAMAIS_CENT_POUR_CENT(maigre):
    """Un ratio dont le numérateur contient un revenu que le dénominateur ignore."""
    for com in (0.0, 700.0, 5000.0):
        pct = _trois_jours(com)["marge_brute_ht_pct"]
        assert pct is None or pct <= 100, f"commission {com} → marge brute {pct} %"


def test_la_commission_apparait_a_part_et_dans_le_total(maigre):
    e = _trois_jours(700.0)
    assert e["marge_hors_ventes_ht"] == 700.0
    assert e["marge_totale_ht"] == pytest.approx(e["marge_brute_ht"] + 700.0, abs=0.01)


def test_LE_RESULTAT_INCLUT_LA_COMMISSION(maigre):
    """
    ⚠️ MON PREMIER TEST NE MORDAIT PAS ICI. Il n'exigeait la cohérence que lorsque l'EBITDA
    était POSITIF : retirer la commission du résultat le rendait négatif, et l'assertion était
    simplement sautée. Un test qui s'abstient dès que le code casse ne garde rien.
    """
    sans, avec = _trois_jours(0.0), _trois_jours(700.0)
    assert avec["ebitda_ht"] - sans["ebitda_ht"] == pytest.approx(700.0, abs=0.01)


def test_une_commission_superieure_aux_charges_ne_rend_pas_le_seuil_negatif(maigre):
    """« La journée est déjà payée » se dit 0 €, pas −1 200 € : un seuil négatif serait une cible."""
    e = _trois_jours(50000.0)
    assert e["seuil_ca_ttc"] == 0
    assert e["pct_seuil"] == 100, "un seuil nul est atteint, pas inatteignable"


def test_la_commission_se_repartit_sur_les_journees(maigre):
    """
    ⚠️ CELUI-CI AUSSI ÉTAIT CREUX. Il vérifiait que les trois journées ont le même seuil — ce
    qui reste vrai si on ne répartit RIEN du tout. Il faut exiger que la série baisse, et de
    la bonne part.
    """
    sans = _trois_jours(0.0)["seuil_ca_ttc_par_jour"]
    avec = _trois_jours(300.0)["seuil_ca_ttc_par_jour"]
    assert set(sans) == set(avec) and len(avec) == 3

    # Un revenu de période imputé à un seul jour ferait plonger son seuil et fausser les autres.
    assert len(set(round(v, 2) for v in avec.values())) == 1, "les trois journées ont divergé"
    for j in avec:
        assert avec[j] < sans[j], f"{j} : le seuil n'a pas bougé"
    # La somme des baisses journalières vaut la baisse de la période.
    baisse_jours = sum(sans[j] - avec[j] for j in avec)
    baisse_total = _trois_jours(0.0)["seuil_ca_ttc"] - _trois_jours(300.0)["seuil_ca_ttc"]
    assert baisse_jours == pytest.approx(baisse_total, rel=0.01)


# ── « On ne sait pas » n'est pas « zéro » ────────────────────────────────────────────────────

def test_SANS_SEUIL_CALCULABLE_LE_TAUX_D_ATTEINTE_EST_INCONNU(maigre):
    """
    ⚠️ `pct_seuil = 0` DESSINAIT UNE BARRE VIDE, qui se lit « tu n'as rien atteint » — une
    affirmation, là où il n'y a pas de mesure. C'est la règle que `manque_seuil` respectait
    déjà deux lignes plus haut en valant `None`.
    """
    docs = [{"local_time": "2026-10-01 12:00:00", "amount_gross": 200.0,
             "amount_net": 180.0, "items": []}]
    e = V.daily_economics(docs, {}, from_date=date(2026, 10, 1), to_date=date(2026, 10, 1),
                          cogs_agg=(0.0, 0.0, 0.0))      # aucun coût mesuré → pas de taux
    assert e["seuil_ca_ttc"] is None
    assert e["manque_seuil"] is None
    assert e["pct_seuil"] is None, "0 % affirme un échec jamais mesuré"


# ══ LA BASE DE LA MARGE ═════════════════════════════════════════════════════════════════════
#
# ⚠️ LE TAUX ÉTAIT MESURÉ SUR LES LIGNES ET APPLIQUÉ AU CA DU DOCUMENT. Une remise globale
# baisse le second sans toucher au premier : la marchandise a bien été consommée. Sur 100 € de
# lignes à 30 € de coût, une remise de 25 % annonçait 52,50 € de marge là où il en reste
# 45,00 — 7,50 € inventés, et un point mort d'autant trop bas.


def _avec_remise(ca_ht, items_ht, cogs_ht, couvert=None):
    """`ca_ht` est l'encaissé ; `items_ht` la somme des lignes. L'écart est la remise."""
    docs = [{"local_time": "2026-10-01 12:00:00", "amount_gross": round(ca_ht * 1.13, 2),
             "amount_net": ca_ht, "items": []}]
    return V.daily_economics(docs, {}, from_date=date(2026, 10, 1), to_date=date(2026, 10, 1),
                             cogs_agg=(cogs_ht, couvert if couvert is not None else items_ht,
                                       items_ht))


def test_SANS_REMISE_LA_REGLE_NE_DEPLACE_RIEN(maigre):
    """La correction ne doit pas bouger les chiffres d'une journée ordinaire."""
    e = _avec_remise(ca_ht=100.0, items_ht=100.0, cogs_ht=30.0)
    assert e["marge_brute_ht"] == pytest.approx(70.0, abs=0.01)
    assert e["marge_brute_ht_pct"] == pytest.approx(70.0, abs=0.1)


def test_UNE_REMISE_GLOBALE_NE_REND_PAS_LA_MARCHANDISE(maigre):
    """Ce qui est vendu 75 € et a coûté 30 € laisse 45 €, pas 52,50 €."""
    e = _avec_remise(ca_ht=75.0, items_ht=100.0, cogs_ht=30.0)
    assert e["marge_brute_ht"] == pytest.approx(45.0, abs=0.01)
    assert e["marge_brute_ht_pct"] == pytest.approx(60.0, abs=0.1)


def test_le_cout_sextrapole_depuis_la_part_couverte(maigre):
    """
    Le coût est mesuré sur la moitié des lignes seulement : on l'extrapole aux lignes, puis on
    le retire de l'encaissé. 100 € de lignes, 50 € couvertes à 15 € de coût → 30 € pour tout.
    """
    e = _avec_remise(ca_ht=100.0, items_ht=100.0, cogs_ht=15.0, couvert=50.0)
    assert e["marge_brute_ht"] == pytest.approx(70.0, abs=0.01)
    assert e["cogs_coverage_pct"] == pytest.approx(50.0, abs=0.1)


def test_UNE_REMISE_FAIT_MONTER_LE_POINT_MORT(maigre):
    """
    ⚠️ C'EST LA CONSÉQUENCE QUI COMPTE. Une marge surévaluée donne un point mort trop bas : on
    croit la journée payée alors qu'elle ne l'est pas. Le sens de l'erreur est le pire des deux.
    """
    sans = _avec_remise(ca_ht=100.0, items_ht=100.0, cogs_ht=30.0)
    avec = _avec_remise(ca_ht=75.0,  items_ht=100.0, cogs_ht=30.0)
    assert avec["seuil_ca_ttc"] > sans["seuil_ca_ttc"]


# ══ LE TOTAL DE PÉRIODE ═════════════════════════════════════════════════════════════════════

def test_LE_TOTAL_EST_LA_SOMME_DE_SES_JOURS(base):
    """
    ⚠️ IL ÉTAIT RECONSTRUIT À PARTIR D'UNE MOYENNE : `cout_jour × open_days`. Tant que les deux
    comptes coïncident, les deux chemins donnent le même nombre — et mon premier test ne
    distinguait donc rien. Ils divergent quand l'appelant IMPOSE un nombre de jours observés
    supérieur aux journées réellement trouvées : le total cesse alors d'être la somme des jours
    qu'il prétend additionner.

    ⚠️ ET IL FAUT DU PERSONNEL pour que la part salariale compte : sans salarié, retirer le
    personnel du total ne change rien et le contrôle passe sans rien garder.
    """
    import charges as ch
    from config import count_open_days_raw

    docs = [{"local_time": f"2026-10-{j:02d} 12:00:00", "amount_gross": 200.0,
             "amount_net": 180.0, "items": []} for j in (1, 2, 3)]
    # La fenêtre du 1er au 7 octobre compte 5 journées de service ; on en impose 9.
    e = V.daily_economics(docs, {}, from_date=date(2026, 10, 1), to_date=date(2026, 10, 7),
                          cogs_agg=(160.0, 540.0, 540.0), open_days_override=9)

    ouvert = lambda j: count_open_days_raw(j, j) == 1
    jours = ch.jours_ouverts_entre(date(2026, 10, 1), date(2026, 10, 7), ouvert)
    assert len(jours) < 9, "ce test suppose que le nombre imposé dépasse les journées trouvées"

    f, p, _ = ch.cout_periode_planning([LOYER], [BARISTA, ANA], [], jours, ouvert,
                                       V.PLANNING_CUTOVER if hasattr(V, "PLANNING_CUTOVER")
                                       else date(2026, 10, 1))
    assert e["cout_total_periode"] == pytest.approx(round(f + p, 2), abs=0.02), (
        "le total n'est pas la somme de ses journées")
    assert e["cout_perso_periode"] > 0, "sans personnel, ce contrôle ne garde rien"
    assert e["cout_total_periode"] == pytest.approx(
        e["cout_fixe_periode"] + e["cout_perso_periode"], abs=0.01)
