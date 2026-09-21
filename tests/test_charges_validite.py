"""
LES CHARGES À UNE DATE DONNÉE.

⚠️ SANS DATE DE VALIDITÉ, CHANGER UN MONTANT RÉÉCRIT LE PASSÉ. Augmenter le loyer en septembre
changeait l'EBITDA de juin, partout, sans que rien ne le signale — et supprimer un poste le
retirait de tout l'historique, rendant trois mois soudain rentables.

⚠️ AUCUNE DE CES ERREURS NE LÈVE. Elles produisent des chiffres plausibles, cohérents entre eux,
et faux.
"""

from datetime import date

import pytest

import charges as C

JUIN = date(2026, 6, 15)
OCTOBRE = date(2026, 10, 15)


def loyer(montant, depuis=None, jusqua=None, freq="monthly"):
    return {"amount": montant, "frequency": freq, "valid_from": depuis, "valid_to": jusqua}


# ── La règle d'applicabilité ─────────────────────────────────────────────────────────────────

def test_une_ligne_sans_bornes_sapplique_partout():
    """
    ⚠️ C'EST LE COMPORTEMENT DES LIGNES D'AVANT LA MIGRATION. NULL n'est jamais zéro : il veut
    dire « pas de borne ». Les traiter autrement aurait fait disparaître toutes les charges
    existantes du jour au lendemain.
    """
    assert C.applicable(loyer(700), JUIN) is True
    assert C.applicable(loyer(700), OCTOBRE) is True


def test_une_ligne_ne_sapplique_pas_avant_son_debut():
    assert C.applicable(loyer(750, depuis="2026-10-01"), JUIN) is False
    assert C.applicable(loyer(750, depuis="2026-10-01"), OCTOBRE) is True


def test_la_borne_haute_est_exclue():
    """
    ⚠️ « VALIDE JUSQU'AU 1er OCTOBRE » VEUT DIRE QUE LE 30 SEPTEMBRE EST LE DERNIER JOUR
    COUVERT. C'est ainsi qu'on clôt une ligne et qu'on en ouvre une autre le même jour sans
    compter le loyer deux fois — l'erreur la plus coûteuse de ce module, et la plus discrète.
    """
    ancien = loyer(700, jusqua="2026-10-01")
    assert C.applicable(ancien, date(2026, 9, 30)) is True
    assert C.applicable(ancien, date(2026, 10, 1)) is False


def test_une_bascule_ne_compte_jamais_deux_fois():
    lignes = [loyer(700, jusqua="2026-10-01"), loyer(750, depuis="2026-10-01")]
    assert C.charges_mensuelles(lignes, date(2026, 9, 30)) == 700
    assert C.charges_mensuelles(lignes, date(2026, 10, 1)) == 750


def test_une_date_illisible_ne_fait_pas_tomber_le_calcul():
    """PostgREST peut rendre une chaîne inattendue ; une ligne abîmée n'est pas une panne."""
    assert C.applicable({"valid_from": "pas-une-date"}, JUIN) is True


# ── Les fréquences ───────────────────────────────────────────────────────────────────────────

def test_les_charges_trimestrielles_et_annuelles_sont_lissees():
    assert C.charges_mensuelles([loyer(300, freq="quarterly")], JUIN) == 100
    assert C.charges_mensuelles([loyer(1200, freq="annual")], JUIN) == 100


def test_une_ligne_au_montant_abime_est_ignoree_pas_fatale():
    lignes = [loyer(700), {"amount": "n/a", "frequency": "monthly"}]
    assert C.charges_mensuelles(lignes, JUIN) == 700


# ── Le personnel ─────────────────────────────────────────────────────────────────────────────

def test_un_extra_est_paye_tel_quel():
    """
    ⚠️ UN EXTRA N'A NI TREIZIÈME MOIS, NI CARTE REPAS. Lui appliquer la formule salariale
    gonflerait son coût de 40 % et fausserait le point mort les mois de gros service —
    précisément ceux où l'on en emploie.
    """
    assert C.cout_employe_mensuel({"gross_monthly": 500, "type": "extra"}) == 500


def test_un_salarie_porte_la_tsu_le_quatorzieme_mois_et_les_repas():
    c = C.cout_employe_mensuel({"gross_monthly": 1000, "meal_card_daily": 10.20})
    attendu = (1000 * 14 * 1.2375 + 10.20 * 242) / 12
    assert c == pytest.approx(attendu)


def test_une_exoneration_de_tsu_est_respectee():
    """Julie est exonérée — premier emploi. L'ignorer surestimerait son coût de 23,75 %."""
    avec = C.cout_employe_mensuel({"gross_monthly": 1000})
    sans = C.cout_employe_mensuel({"gross_monthly": 1000, "tsu_exempt": True})
    assert sans < avec


def test_un_salarie_parti_ne_coute_plus_rien_apres_son_depart():
    lignes = [{"gross_monthly": 1000, "tsu_exempt": True, "valid_to": "2026-10-01"}]
    assert C.personnel_mensuel(lignes, date(2026, 9, 30)) > 0
    assert C.personnel_mensuel(lignes, date(2026, 10, 1)) == 0


# ── Le coût d'une période ────────────────────────────────────────────────────────────────────

def test_une_periode_qui_enjambe_une_hausse_compte_les_deux_montants():
    """
    ⚠️ MULTIPLIER UN TOTAL MENSUEL PAR UN NOMBRE DE JOURS DONNERAIT LE BON ORDRE DE GRANDEUR ET
    LE MAUVAIS CHIFFRE — et l'erreur serait maximale le mois où l'on vient justement voir
    l'effet du changement.
    """
    lignes = [loyer(700, jusqua="2026-10-01"), loyer(1000, depuis="2026-10-01")]
    jours = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    fixes, _ = C.cout_periode(lignes, [], jours, 20)
    # Deux jours à 700/20 = 35, deux jours à 1000/20 = 50.
    assert fixes == pytest.approx(2 * 35 + 2 * 50)


def test_une_periode_sans_jour_ouvert_ne_coute_rien():
    """
    ⚠️ UN MARDI-MERCREDI, LE CAFÉ EST FERMÉ. Imputer une journée de charges à une période sans
    ouverture affichait 197 € de charges et un EBITDA négatif sur des jours où rien n'a eu lieu.
    """
    assert C.cout_periode([loyer(700)], [], [], 20) == (0.0, 0.0)


def test_le_calcul_ne_refait_pas_la_somme_pour_chaque_jour_identique():
    """Sur trois mois, les mêmes bornes reviennent quatre-vingt-dix fois."""
    appels = []

    class Espion(dict):
        def get(self, k, d=None):
            if k == "amount":
                appels.append(1)
            return super().get(k, d)

    lignes = [Espion(loyer(700))]
    jours = [date(2026, 6, 1)] * 50
    C.cout_periode(lignes, [], jours, 20)
    assert len(appels) <= 2, "la somme est recalculée à chaque jour"


def test_les_jours_ouverts_excluent_les_jours_de_fermeture():
    ouvert = lambda j: j.weekday() not in (1, 2)   # mardi, mercredi fermés
    jours = C.jours_ouverts_entre(date(2026, 9, 14), date(2026, 9, 20), ouvert)
    assert len(jours) == 5
    assert date(2026, 9, 15) not in jours


# ── Le cas que le déploiement a failli emporter ──────────────────────────────────────────────
#
# ⚠️ AVANT LES DATES, `active` ÉTAIT LA SEULE FAÇON D'ARRÊTER UN POSTE. `daily_economics`
# filtrait `active=eq.true` ; ce filtre est tombé pour qu'une ligne clôturée compte encore dans
# les mois passés. Mais une charge éteinte à la main, sans bornes, s'est alors remise à coûter —
# un logiciel résilié qui reprend 120 € par mois, sans un mot, sur tous les mois à la fois.
#
# ⚠️ ET C'EST AUSSI CE QUI TIENT LA PROMESSE DU DÉPLOIEMENT. Le jour de la migration, aucune
# ligne n'a de bornes : toutes doivent se comporter exactement comme la veille.

DESACTIVEE = {"name": "Ancien logiciel", "amount": 120.0, "frequency": "monthly",
              "active": False, "valid_from": None, "valid_to": None}


def test_une_charge_eteinte_a_la_main_ne_compte_pas():
    assert C.charges_mensuelles([DESACTIVEE], date(2026, 9, 21)) == 0.0


def test_un_salarie_eteint_a_la_main_ne_compte_pas():
    parti = {"name": "Ana", "gross_monthly": 900, "type": "full_time", "active": False,
             "valid_from": None, "valid_to": None}
    assert C.personnel_mensuel([parti], date(2026, 9, 21)) == 0.0


def test_active_ne_lemporte_que_faute_de_bornes():
    """
    ⚠️ DÈS QU'UNE LIGNE A UNE DATE, C'EST LA DATE QUI COMMANDE. Sinon `active`, que le serveur
    fait basculer au jour dit, se mettrait à contredire la borne qu'il vient lui-même d'écrire :
    une ligne clôturée au 1er novembre cesserait de compter en septembre.
    """
    close_plus_tard = dict(DESACTIVEE, valid_to="2026-11-01")
    assert C.applicable(close_plus_tard, date(2026, 9, 21)) is True
    assert C.applicable(close_plus_tard, date(2026, 11, 1)) is False


def test_une_ligne_sans_champ_active_sapplique():
    """Les vecteurs et les anciennes lignes n'ont pas ce champ — son absence n'est pas un « non »."""
    assert C.applicable({"amount": 100}, date(2026, 9, 21)) is True


def test_active_vrai_ne_force_rien_contre_les_dates():
    """Une ligne active mais pas encore entrée en vigueur ne compte pas."""
    future = {"amount": 100, "active": True, "valid_from": "2026-10-01", "valid_to": None}
    assert C.applicable(future, date(2026, 9, 21)) is False
