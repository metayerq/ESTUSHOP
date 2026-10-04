# -*- coding: utf-8 -*-
"""
LES CHARGES SUR FACTURE — EAU ET ÉLECTRICITÉ.

⚠️ CE FICHIER EXISTE POUR UN DÉFAUT QUE LA FRICTION CACHAIT. Quentin se plaignait de la lourdeur
de saisie ; en lisant le code j'ai trouvé pire. `_date_effet` refuse toute date antérieure à
demain — la règle qui empêche d'augmenter le loyer de juin depuis septembre, et elle est juste.
Mais la facture d'électricité d'octobre arrive le 5 novembre : elle ne pouvait donc s'appliquer
qu'à partir de novembre. OCTOBRE GARDAIT À JAMAIS LE MONTANT DE SEPTEMBRE, et novembre portait
la facture d'octobre. Un décalage systématique, sur toutes les charges mesurées, que rien à
l'écran n'annonçait.

⚠️ UNE FACTURE N'EST PAS UN CHANGEMENT, C'EST UNE OBSERVATION. On ne retire pas la discipline
des lignes datées — une facture en est l'expression la plus pure. On arrête seulement de
demander une date d'effet et un motif dont la réponse est connue d'avance.
"""
from datetime import date

import pytest

import charges as ch


def facture(mois, montant, nom="Électricité", debut=None, fin=None):
    return {"name": nom, "mode": "facture", "mois": mois, "amount": montant,
            "frequency": "monthly", "valid_from": debut or mois, "valid_to": fin,
            "active": True}


LOYER = {"name": "Loyer", "mode": "stable", "mois": None, "amount": 700.0,
         "frequency": "monthly", "valid_from": None, "valid_to": None, "active": True}


# ── Mesuré contre estimé ────────────────────────────────────────────────────────────────────

def test_LE_MOIS_DE_LA_FACTURE_EST_MESURE():
    total, estimees = ch.charges_mensuelles_detail([facture("2026-09-01", 77.10)],
                                                   date(2026, 9, 15))
    assert total == pytest.approx(77.10)
    assert estimees == [], "le mois de la facture n'est pas une estimation"


def test_LE_MOIS_SUIVANT_PORTE_LA_DERNIERE_FACTURE_ET_LE_DIT():
    """
    ⚠️ C'EST LE CŒUR DU MÉCANISME. Clore chaque ligne à la fin de son mois laisserait un TROU :
    la charge disparaîtrait du point mort, qui paraîtrait plus bas qu'il n'est. Un trou est un
    pire mensonge qu'une estimation annoncée.
    """
    total, estimees = ch.charges_mensuelles_detail([facture("2026-09-01", 77.10)],
                                                   date(2026, 10, 15))
    assert total == pytest.approx(77.10)
    assert estimees == ["Électricité"]


def test_une_charge_stable_nest_jamais_estimee():
    """Le loyer ne s'estime pas : il vaut ce qu'il vaut tant qu'il n'a pas changé."""
    _, estimees = ch.charges_mensuelles_detail([LOYER], date(2026, 10, 15))
    assert estimees == []


def test_la_facture_du_mois_chasse_lestimation():
    lignes = [facture("2026-09-01", 77.10, fin="2026-10-01"),
              facture("2026-10-01", 86.40)]
    total, estimees = ch.charges_mensuelles_detail(lignes, date(2026, 10, 15))
    assert total == pytest.approx(86.40)
    assert estimees == []


def test_LES_DEUX_CHARGES_COEXISTENT_SANS_SE_MELANGER():
    lignes = [facture("2026-10-01", 86.40, nom="Électricité"),
              facture("2026-09-01", 31.40, nom="Eau"), LOYER]
    total, estimees = ch.charges_mensuelles_detail(lignes, date(2026, 10, 15))
    assert total == pytest.approx(86.40 + 31.40 + 700.0)
    assert estimees == ["Eau"], "seule l'eau manque ce mois-ci"


def test_une_ligne_abimee_ne_fait_pas_tomber_le_total():
    lignes = [facture("2026-10-01", "illisible"), LOYER]
    total, _ = ch.charges_mensuelles_detail(lignes, date(2026, 10, 15))
    assert total == pytest.approx(700.0)


# ── Où poser une facture ────────────────────────────────────────────────────────────────────

def test_une_facture_couvre_son_mois_pas_le_lendemain():
    """⚠️ LE DÉFAUT D'ORIGINE. Reçue le 5 novembre, elle couvre quand même octobre."""
    debut, fin, _ = ch.bornes_dune_facture([], "Électricité", date(2026, 10, 1))
    assert debut == date(2026, 10, 1)
    assert fin is None, "sans facture suivante, la ligne reste ouverte"


def test_poser_une_facture_cloture_la_precedente():
    lignes = [facture("2026-09-01", 77.10)]
    _, _, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert len(a_cloturer) == 1
    ligne, quand = a_cloturer[0]
    assert ligne["mois"] == "2026-09-01" and quand == date(2026, 10, 1)


def test_UNE_SAISIE_DANS_LE_DESORDRE_SE_PLACE_AU_BON_ENDROIT():
    """
    ⚠️ RATTRAPER DEUX MOIS, OU CORRIGER UN MOIS ANCIEN APRÈS AVOIR SAISI LES SUIVANTS, ne doit
    pas écraser les voisines. On regarde les factures existantes ; on ne suppose jamais qu'on
    est au bout de la série.
    """
    lignes = [facture("2026-09-01", 77.10), facture("2026-11-01", 92.00)]
    debut, fin, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert debut == date(2026, 10, 1)
    assert fin == date(2026, 11, 1), "octobre doit s'arrêter là où novembre commence"
    assert a_cloturer[0][0]["mois"] == "2026-09-01"


def test_une_facture_deja_close_au_bon_endroit_nest_pas_retouchee():
    lignes = [facture("2026-09-01", 77.10, fin="2026-10-01")]
    _, _, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert a_cloturer == []


def test_les_factures_dune_autre_charge_ne_comptent_pas():
    lignes = [facture("2026-09-01", 31.40, nom="Eau")]
    _, fin, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert fin is None and a_cloturer == []


# ── Ce qui manque ───────────────────────────────────────────────────────────────────────────

def test_LE_MOIS_COURANT_NEST_JAMAIS_EN_ATTENTE():
    """
    ⚠️ IL N'EST PAS FINI. Crier sur un mois en cours apprend à ignorer le signal, et c'est
    celui qui compte qu'on rate ensuite.
    """
    lignes = [facture("2026-09-01", 77.10)]
    assert ch.mois_en_attente(lignes, "Électricité", date(2026, 10, 15)) == []


def test_un_mois_clos_sans_facture_est_en_attente():
    lignes = [facture("2026-09-01", 77.10)]
    assert ch.mois_en_attente(lignes, "Électricité", date(2026, 11, 5)) == [date(2026, 10, 1)]


def test_deux_mois_de_retard_sortent_du_plus_ancien_au_plus_recent():
    """La saisie est séquentielle : le risque du rattrapage est d'inverser les montants."""
    lignes = [facture("2026-08-01", 70.00)]
    assert ch.mois_en_attente(lignes, "Électricité", date(2026, 11, 5)) == [
        date(2026, 9, 1), date(2026, 10, 1)]


def test_un_trou_au_milieu_est_signale():
    lignes = [facture("2026-08-01", 70.00), facture("2026-10-01", 86.40)]
    assert ch.mois_en_attente(lignes, "Électricité", date(2026, 11, 5)) == [date(2026, 9, 1)]


def test_sans_aucune_facture_on_ne_reclame_rien():
    """⚠️ ON NE SAIT PAS DEPUIS QUAND CETTE CHARGE EXISTE : réclamer serait inventer un retard."""
    assert ch.mois_en_attente([], "Électricité", date(2026, 11, 5)) == []


def test_UNE_CHARGE_RECONVERTIE_EN_STABLE_NEST_PAS_ESTIMEE():
    """
    ⚠️ LE `mois` PEUT SURVIVRE À LA RECONVERSION. Repasser une charge de « facture » à
    « stable » laisse son dernier mois dans la ligne — rien ne l'efface. C'est le MODE qui
    décide, jamais la présence d'un mois : sinon le loyer se mettrait à s'annoncer estimé.

    Mon premier test utilisait `mois: None` et ne pouvait donc rien attraper.
    """
    reconvertie = {"name": "Électricité", "mode": "stable", "mois": "2026-09-01",
                   "amount": 80.0, "frequency": "monthly", "valid_from": None,
                   "valid_to": None, "active": True}
    assert ch.facture_estimee(reconvertie, date(2026, 10, 15)) is False
    _, estimees = ch.charges_mensuelles_detail([reconvertie], date(2026, 10, 15))
    assert estimees == []


def test_les_factures_dune_autre_charge_ne_decalent_pas_les_bornes():
    """Eau et électricité vivent dans la même table : leurs séries ne doivent pas se croiser."""
    lignes = [facture("2026-11-01", 33.00, nom="Eau"),
              facture("2026-09-01", 77.10, nom="Électricité")]
    debut, fin, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert fin is None, "une facture d'eau de novembre a borné l'électricité d'octobre"
    assert a_cloturer[0][0]["name"] == "Électricité"


# ── Dire « estimé » là où ça compte ─────────────────────────────────────────────────────────
#
# ⚠️ `charges_mensuelles_detail` EXISTAIT DEPUIS LE DÉBUT ET N'ÉTAIT APPELÉE PAR PERSONNE. Elle
# était écrite, commentée, testée — et le point mort continuait de se calculer avec
# `charges_mensuelles`, qui ne dit rien de ce qu'elle estime. Une fonction juste que rien
# n'appelle ne corrige rien ; elle donne seulement l'impression que c'est fait.

def test_un_mois_sans_facture_est_annonce_comme_estime():
    jours = [date(2026, 10, d) for d in (1, 8, 15)]
    assert ch.charges_estimees([facture("2026-09-01", 77.10)], jours) == ["Électricité"]


def test_le_mois_de_la_facture_nest_pas_une_estimation():
    jours = [date(2026, 10, d) for d in (1, 8, 15)]
    assert ch.charges_estimees([facture("2026-10-01", 81.0)], jours) == []


def test_une_charge_stable_nest_jamais_estimee():
    assert ch.charges_estimees([LOYER], [date(2026, 10, 15)]) == []


def test_un_seul_jour_estime_qualifie_toute_la_periode():
    """
    ⚠️ UNE SEMAINE À CHEVAL SUR DEUX MOIS. Septembre a sa facture, octobre pas encore : les
    trois premiers jours sont mesurés, les quatre suivants supposés. Ne retenir que la
    majorité, ou que le dernier jour, laisserait passer la moitié des semaines de l'année.
    """
    lignes = [facture("2026-09-01", 77.10, debut="2026-09-01", fin="2026-10-01"),
              facture("2026-08-01", 71.0, debut="2026-10-01")]
    jours = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 10, 1), date(2026, 10, 2)]
    assert ch.charges_estimees(lignes, jours) == ["Électricité"]


def test_deux_charges_estimees_sont_toutes_les_deux_nommees():
    lignes = [facture("2026-09-01", 77.10, nom="Électricité"),
              facture("2026-08-01", 31.40, nom="Eau"), LOYER]
    assert ch.charges_estimees(lignes, [date(2026, 10, 15)]) == ["Eau", "Électricité"]


def test_sans_jour_il_ny_a_rien_a_estimer():
    """Une période vide ne doit pas inventer une alerte — ni lever."""
    assert ch.charges_estimees([facture("2026-09-01", 77.10)], []) == []
    assert ch.charges_estimees(None, [date(2026, 10, 15)]) == []


def test_une_ligne_deja_close_ne_rend_pas_la_charge_estimee():
    """
    ⚠️ CE CONTRÔLE MANQUAIT ET LA FONCTION PASSAIT QUAND MÊME. Mes deux premiers cas portaient
    le même nom sur les deux lignes : retirer le filtre `applicable` donnait exactement le même
    résultat, donc rien ne gardait la borne de validité. Ici l'ancienne ligne d'« Eau » est
    close depuis septembre et sa facture est vieille ; la ligne en vigueur, elle, porte le mois
    calculé. Sans le filtre, « Eau » serait annoncée estimée alors qu'elle est mesurée.
    """
    lignes = [facture("2026-07-01", 28.0, nom="Eau", debut="2026-07-01", fin="2026-10-01"),
              facture("2026-10-01", 31.40, nom="Eau", debut="2026-10-01")]
    assert ch.charges_estimees(lignes, [date(2026, 10, 15)]) == []


# ── La ligne héritée de la bascule ──────────────────────────────────────────────────────────
#
# ⚠️ CE DÉFAUT EST APPARU LE JOUR OÙ QUENTIN A BASCULÉ SES DEUX CHARGES. Passer « Électricité »
# en mode facture laisse sa ligne existante en place, SANS mois — c'est voulu : on ignore à quel
# mois correspond le montant déjà saisi, et l'inventer serait affirmer une mesure qu'on n'a pas.
# Mais cette ligne est OUVERTE. `bornes_dune_facture` ne regardait que les lignes PORTANT un
# mois pour décider laquelle clôturer : la ligne héritée ne l'était donc jamais, et dès la
# première facture les deux s'appliquaient. L'électricité comptait double dans le point mort.

CONVERTIE = {"name": "Électricité", "mode": "facture", "mois": None, "amount": 77.10,
             "frequency": "monthly", "valid_from": None, "valid_to": None, "active": True}


def test_la_ligne_sans_mois_est_cloturee_par_la_premiere_facture():
    _, _, a_cloturer = ch.bornes_dune_facture([CONVERTIE], "Électricité", date(2026, 9, 1))
    assert a_cloturer == [(CONVERTIE, date(2026, 9, 1))]


def test_la_charge_ne_compte_pas_double_apres_la_premiere_facture():
    """Le contrôle qui compte vraiment : le total, pas la mécanique qui le produit."""
    close = {**CONVERTIE, "valid_to": "2026-09-01", "active": False}
    sept = facture("2026-09-01", 81.40)
    assert ch.charges_mensuelles([close, sept], date(2026, 8, 15)) == 77.10
    assert ch.charges_mensuelles([close, sept], date(2026, 9, 15)) == 81.40
    assert ch.charges_mensuelles([close, sept], date(2026, 10, 2)) == 81.40


def test_rattraper_un_mois_anterieur_recoupe_aussi_la_ligne_heritee():
    """
    ⚠️ ET DANS LE DÉSORDRE. Septembre saisi en premier clôture la ligne héritée au 1er septembre.
    Saisir août ensuite crée une ligne du 1er août au 1er septembre — la ligne héritée, encore
    ouverte sur août, s'y superposerait. Elle doit reculer jusqu'au premier mois mesuré.
    """
    close_sept = {**CONVERTIE, "valid_to": "2026-09-01"}
    lignes = [close_sept, facture("2026-09-01", 81.40)]
    debut, fin, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 8, 1))
    assert (debut, fin) == (date(2026, 8, 1), date(2026, 9, 1))
    assert a_cloturer == [(close_sept, date(2026, 8, 1))]


def test_une_ligne_heritee_deja_recoupee_nest_pas_reclôturee():
    """Clôturer deux fois au même endroit écrirait pour rien, et brouillerait le journal."""
    close = {**CONVERTIE, "valid_to": "2026-09-01"}
    lignes = [close, facture("2026-09-01", 81.40)]
    _, _, a_cloturer = ch.bornes_dune_facture(lignes, "Électricité", date(2026, 10, 1))
    assert a_cloturer == [(lignes[1], date(2026, 10, 1))]


def test_une_ligne_heritee_qui_commence_plus_tard_nest_pas_fermee_avant_son_debut():
    """
    ⚠️ FERMER UNE LIGNE AVANT SA PROPRE OUVERTURE DONNE UN INTERVALLE À L'ENVERS — du 1er
    novembre au 1er octobre. Elle ne disparaîtrait pas pour autant : `applicable` la lirait
    comme une ligne sans fin utile, et le montant reviendrait là où on croyait l'avoir retiré.
    Une ligne héritée ne se recoupe que si elle couvre déjà le mois saisi.
    """
    tardive = {**CONVERTIE, "valid_from": "2026-11-01"}
    _, _, a_cloturer = ch.bornes_dune_facture([tardive], "Électricité", date(2026, 10, 1))
    assert a_cloturer == []
