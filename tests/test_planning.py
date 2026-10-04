# -*- coding: utf-8 -*-
"""
LE PLANNING — CE QUE COÛTE UN JOUR, ET CE QU'IL NE DOIT PAS COÛTER.

⚠️ CE FICHIER EXISTE POUR DEUX FAUTES QUI NE SE VOIENT PAS À LA LECTURE.

La première : compter un permanent DEUX fois. Sa paie est lissée, et l'inscrire au planning
ajouterait ses heures par-dessus. Le point mort monterait d'un tiers, et personne ne saurait
dire pourquoi — le planning a l'air juste, la fiche a l'air juste.

La seconde : effacer le passé. Le jour où les extras passent au planning, les mois clos n'ont
aucun shift. Sans date de bascule, le coût du personnel de septembre tomberait d'un coup et son
point mort deviendrait faux APRÈS avoir été lu. C'est exactement ce que les dates de validité
des charges corrigent ; la même discipline s'applique ici.
"""
import datetime
from datetime import date

import pytest

import charges as ch


JOURS = 21.7            # jours ouverts d'un mois type
BASCULE = date(2026, 10, 1)

# ⚠️ LE PERMANENT PORTE UN TAUX HORAIRE, ET CE N'EST PAS UN DÉTAIL DE FIXTURE. Sans lui, le
# test du double comptage passait pour la MAUVAISE raison : ajouter ses heures ne coûtait rien
# puisque le taux valait zéro. Le garde de production avait l'air tenu, il ne l'était pas — il
# aurait cédé le jour où un taux est saisi pour un permanent, ce qui est parfaitement légitime
# (suivre les heures sans changer la paie). Trouvé par mutation, pas par relecture.
BARISTA = {
    "person_id": "p-barista", "name": "Barista", "type": "full_time",
    "gross_monthly": 1200.0, "meal_card_daily": 10.20, "tsu_exempt": False,
    "hourly_rate": 11.0,
    "valid_from": "2026-05-01", "valid_to": None, "active": True,
}
EXTRA = {
    "person_id": "p-ana", "name": "Ana", "type": "extra",
    "gross_monthly": 300.0, "hourly_rate": 12.0,
    "valid_from": "2026-05-01", "valid_to": None, "active": True,
}


def shift(person="p-ana", jour="2026-10-03", debut="09:00", fin="17:00"):
    return {"person_id": person, "day": jour, "start_time": debut, "end_time": fin}


# ── Les heures ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("debut,fin,attendu", [
    ("09:00", "17:00", 8.0),
    ("09:30", "17:00", 7.5),
    ("09:00:00", "12:15:00", 3.25),
    ("18:00", "23:59", 5.983333333333333),
])
def test_les_heures_se_comptent(debut, fin, attendu):
    assert ch.heures(debut, fin) == pytest.approx(attendu)


@pytest.mark.parametrize("debut,fin", [
    ("17:00", "09:00"),     # inversé : une faute de frappe, pas une nuit
    ("09:00", "09:00"),     # durée nulle
    ("", "17:00"),
    (None, "17:00"),
    ("abc", "17:00"),
    ("25:00", "26:00"),     # hors cadran
    ("09:70", "17:00"),
])
def test_une_saisie_illisible_ne_vaut_aucune_heure(debut, fin):
    """
    ⚠️ ZÉRO, PAS UNE DEVINETTE. « 17:00 → 09:00 » traité comme un service de 23 heures
    gonflerait le coût du jour de 276 € sans que rien ne le signale.
    """
    assert ch.heures(debut, fin) == 0.0


# ── La fiche du jour ────────────────────────────────────────────────────────────────────────

def test_une_augmentation_doctobre_ne_change_pas_un_service_de_septembre():
    """⚠️ LE CŒUR DU MODÈLE. Le taux se résout à la date du shift, pas à aujourd'hui."""
    avant = dict(EXTRA, hourly_rate=12.0, valid_from="2026-05-01", valid_to="2026-10-01")
    apres = dict(EXTRA, hourly_rate=15.0, valid_from="2026-10-01", valid_to=None)
    employes = [avant, apres]

    septembre = ch.cout_shift(shift(jour="2026-09-20"), employes)
    octobre   = ch.cout_shift(shift(jour="2026-10-20"), employes)
    assert septembre == pytest.approx(8 * 12.0)
    assert octobre   == pytest.approx(8 * 15.0)


def test_une_personne_a_plusieurs_fiches_et_une_seule_identite():
    avant = dict(EXTRA, hourly_rate=12.0, valid_from="2026-05-01", valid_to="2026-10-01")
    apres = dict(EXTRA, hourly_rate=15.0, valid_from="2026-10-01", valid_to=None)
    f = ch.fiche_du_jour([avant, apres], "p-ana", date(2026, 10, 5))
    assert f["hourly_rate"] == 15.0


def test_un_shift_sans_fiche_applicable_ne_coute_rien():
    """Inventer un taux serait pire que zéro : l'écran le signale, le calcul ne devine pas."""
    assert ch.cout_shift(shift(person="p-inconnu"), [EXTRA]) == 0.0


def test_un_shift_dune_personne_partie_ne_coute_rien():
    partie = dict(EXTRA, valid_to="2026-09-01")
    assert ch.cout_shift(shift(jour="2026-10-03"), [partie]) == 0.0


# ── Le coût d'un jour ───────────────────────────────────────────────────────────────────────

def _jour_coute(employes, shifts, jour):
    return ch.personnel_du_jour(employes, shifts, jour, JOURS, BASCULE)


def test_un_jour_sans_extra_ne_coute_que_le_permanent():
    attendu = ch.cout_employe_mensuel(BARISTA) / JOURS
    assert _jour_coute([BARISTA, EXTRA], [], date(2026, 10, 5)) == pytest.approx(attendu)


def test_un_extra_de_huit_heures_ajoute_ses_heures_au_jour():
    seul = _jour_coute([BARISTA, EXTRA], [], date(2026, 10, 3))
    avec = _jour_coute([BARISTA, EXTRA], [shift(jour="2026-10-03")], date(2026, 10, 3))
    assert avec - seul == pytest.approx(8 * 12.0)


def test_deux_extras_le_meme_jour_sadditionnent():
    bob = dict(EXTRA, person_id="p-bob", name="Bob", hourly_rate=10.0)
    s = [shift(jour="2026-10-03"), shift(person="p-bob", jour="2026-10-03", debut="12:00", fin="18:00")]
    seul = _jour_coute([BARISTA, EXTRA, bob], [], date(2026, 10, 3))
    avec = _jour_coute([BARISTA, EXTRA, bob], s, date(2026, 10, 3))
    assert avec - seul == pytest.approx(8 * 12.0 + 6 * 10.0)


def test_un_shift_dun_autre_jour_ne_compte_pas():
    seul = _jour_coute([BARISTA, EXTRA], [], date(2026, 10, 3))
    avec = _jour_coute([BARISTA, EXTRA], [shift(jour="2026-10-04")], date(2026, 10, 3))
    assert avec == pytest.approx(seul)


def test_LE_PERMANENT_INSCRIT_AU_PLANNING_N_EST_PAS_PAYE_DEUX_FOIS():
    """
    ⚠️ LA FAUTE QUI NE SE VOIT PAS. Sa paie est déjà lissée. Ajouter ses heures parce qu'il
    figure au planning ferait monter le point mort d'un tiers, et le planning comme la fiche
    auraient l'air justes tous les deux.
    """
    sans = _jour_coute([BARISTA, EXTRA], [], date(2026, 10, 3))
    avec = _jour_coute([BARISTA, EXTRA],
                       [shift(person="p-barista", jour="2026-10-03")], date(2026, 10, 3))
    assert avec == pytest.approx(sans)


def test_le_montant_mensuel_dun_extra_ne_compte_plus_apres_la_bascule():
    """Sinon on le paie deux fois : son forfait lissé ET ses heures."""
    avec_extra = _jour_coute([BARISTA, EXTRA], [], date(2026, 10, 5))
    sans_extra = _jour_coute([BARISTA], [], date(2026, 10, 5))
    assert avec_extra == pytest.approx(sans_extra)


# ── La bascule ──────────────────────────────────────────────────────────────────────────────

def test_AVANT_LA_BASCULE_LE_CALCUL_EST_EXACTEMENT_CELUI_DHIER():
    """
    ⚠️ LA PROMESSE DU JOUR DE MISE EN SERVICE. Septembre n'a aucun shift : sans cette borne,
    son coût de personnel chuterait du montant des extras, APRÈS avoir été lu.
    """
    septembre = ch.personnel_du_jour([BARISTA, EXTRA], [], date(2026, 9, 20), JOURS, BASCULE)
    hier = ch.personnel_mensuel([BARISTA, EXTRA], date(2026, 9, 20)) / JOURS
    assert septembre == pytest.approx(hier)


def test_avant_la_bascule_un_shift_ne_coute_rien_de_plus():
    """Un shift saisi pour une date antérieure ne doit pas s'ajouter au forfait déjà compté."""
    sans = ch.personnel_du_jour([BARISTA, EXTRA], [], date(2026, 9, 20), JOURS, BASCULE)
    avec = ch.personnel_du_jour([BARISTA, EXTRA], [shift(jour="2026-09-20")],
                                date(2026, 9, 20), JOURS, BASCULE)
    assert avec == pytest.approx(sans)


def test_sans_bascule_le_comportement_reste_celui_dhier():
    """`bascule=None` : aucune régression possible pour un appelant qui ne la passe pas."""
    a = ch.personnel_du_jour([BARISTA, EXTRA], [shift()], date(2026, 10, 3), JOURS, None)
    b = ch.personnel_mensuel([BARISTA, EXTRA], date(2026, 10, 3)) / JOURS
    assert a == pytest.approx(b)


def test_le_jour_de_la_bascule_est_inclus():
    """La borne est `>=` : le 1er octobre est le premier jour au planning."""
    veille = ch.personnel_du_jour([BARISTA, EXTRA], [shift(jour="2026-09-30")],
                                  date(2026, 9, 30), JOURS, BASCULE)
    jour_j = ch.personnel_du_jour([BARISTA, EXTRA], [shift(jour="2026-10-01")],
                                  date(2026, 10, 1), JOURS, BASCULE)
    assert veille == pytest.approx(ch.cout_employe_mensuel(BARISTA) / JOURS
                                   + ch.cout_employe_mensuel(EXTRA) / JOURS)
    assert jour_j == pytest.approx(ch.cout_employe_mensuel(BARISTA) / JOURS + 8 * 12.0)


# ── Les cas limites qui font tomber un calcul ───────────────────────────────────────────────

def test_aucun_jour_ouvert_ne_divise_pas_par_zero():
    assert ch.personnel_du_jour([BARISTA], [], date(2026, 10, 5), 0, BASCULE) == 0.0


def test_un_taux_absent_vaut_zero_et_ne_fait_pas_tomber_le_jour():
    muet = dict(EXTRA, hourly_rate=None)
    assert _jour_coute([BARISTA, muet], [shift()], date(2026, 10, 3)) == pytest.approx(
        ch.cout_employe_mensuel(BARISTA) / JOURS)


def test_un_shift_sans_date_est_ignore():
    assert ch.cout_shift({"person_id": "p-ana", "start_time": "09:00", "end_time": "17:00"},
                         [EXTRA]) == 0.0


def test_un_taux_illisible_ne_fait_pas_tomber_le_jour():
    casse = dict(EXTRA, hourly_rate="douze")
    assert ch.cout_shift(shift(), [casse]) == 0.0


# ── Le diviseur, et la période ──────────────────────────────────────────────────────────────

OUVERT = lambda j: j.weekday() in {0, 3, 4, 5, 6}    # lun, jeu, ven, sam, dim


def test_le_diviseur_vient_du_calendrier_pas_dune_constante():
    """
    ⚠️ 21,25 ÉTAIT UNE SAISIE, PAS UNE MESURE. Le vrai compte oscille entre 20 et 23 selon le
    mois — ±8 %, sur le diviseur de toute paie lissée et donc de tout le point mort.
    """
    assert ch.jours_ouverts_du_mois(date(2026, 10, 15), OUVERT) == 23
    assert ch.jours_ouverts_du_mois(date(2027, 2, 15), OUVERT) == 20


def test_decembre_ne_deborde_pas_sur_lannee_suivante():
    """Le calcul du dernier jour du mois passe par janvier de l'année d'après."""
    assert ch.jours_ouverts_du_mois(date(2026, 12, 15), OUVERT) == len(
        ch.jours_ouverts_entre(date(2026, 12, 1), date(2026, 12, 31), OUVERT))


def test_fevrier_bissextile_compte_son_29():
    assert ch.jours_ouverts_du_mois(date(2028, 2, 10), OUVERT) == len(
        ch.jours_ouverts_entre(date(2028, 2, 1), date(2028, 2, 29), OUVERT))


def test_CHAQUE_JOUR_PORTE_LE_DIVISEUR_DE_SON_MOIS():
    """
    ⚠️ UNE PÉRIODE QUI ENJAMBE DEUX MOIS N'A PAS UN DIVISEUR UNIQUE. Octobre a 23 services,
    février 20 : diviser tout par une moyenne ferait porter à l'un les charges de l'autre.
    """
    jours = [date(2026, 10, 30), date(2026, 11, 2)]
    _, _, par_jour = ch.cout_periode_planning([], [BARISTA], [], jours, OUVERT, BASCULE)
    oct_, nov = par_jour[date(2026, 10, 30)], par_jour[date(2026, 11, 2)]
    assert oct_["personnel"] != nov["personnel"]
    assert oct_["personnel"] == pytest.approx(
        ch.cout_employe_mensuel(BARISTA) / ch.jours_ouverts_du_mois(date(2026, 10, 1), OUVERT))


def test_le_detail_par_jour_est_rendu_pour_la_courbe():
    """Sans lui, la ligne de point mort resterait horizontale sur un coût qui ne l'est plus."""
    jours = [date(2026, 10, 2), date(2026, 10, 3)]
    s = [shift(jour="2026-10-03")]
    fixes, perso, par_jour = ch.cout_periode_planning([], [BARISTA, EXTRA], s, jours,
                                                      OUVERT, BASCULE)
    assert set(par_jour) == set(jours)
    assert par_jour[date(2026, 10, 3)]["total"] > par_jour[date(2026, 10, 2)]["total"]
    assert perso == pytest.approx(sum(v["personnel"] for v in par_jour.values()))
    assert fixes == pytest.approx(sum(v["fixes"] for v in par_jour.values()))


def test_une_periode_vide_ne_coute_rien_et_ne_tombe_pas():
    assert ch.cout_periode_planning([], [BARISTA], [], [], OUVERT, BASCULE) == (0.0, 0.0, {})


def test_un_mois_sans_aucune_ouverture_ne_divise_pas_par_zero():
    ferme = lambda j: False
    fixes, perso, par_jour = ch.cout_periode_planning(
        [], [BARISTA], [], [date(2026, 10, 2)], ferme, BASCULE)
    assert (fixes, perso, par_jour) == (0.0, 0.0, {})
