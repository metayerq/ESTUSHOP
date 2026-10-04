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


# ══ UNE FACTURE COUVRE UNE PÉRIODE, PAS UN MOIS ═════════════════════════════════════════════
#
# ⚠️ L'HYPOTHÈSE S'EST CASSÉE SUR LA PREMIÈRE VRAIE FACTURE D'EAU. L'EPAL facture par période de
# 60 jours : du 21/07/2026 au 18/09/2026, 176,14 €. À cheval sur TROIS mois civils. Saisie comme
# un montant mensuel — ce que le modèle « une facture = un mois » en faisait — l'eau pesait
# 176,14 €/mois au lieu de 89,36 €, soit 86,78 € de trop chaque mois dans le point mort.
#
# Les factures d'électricité portent une période elles aussi : ce n'est pas un cas particulier
# de l'eau, c'est la forme normale d'une facture de fluide.

EPAL = {"name": "Eau", "mode": "facture", "mois": "2026-09-01", "amount": 176.14,
        "frequency": "monthly", "periode_debut": "2026-07-21", "periode_fin": "2026-09-18",
        "valid_from": "2026-07-21", "valid_to": None, "active": True}


def test_le_taux_journalier_vient_de_la_periode():
    assert round(ch.taux_jour(EPAL), 4) == round(176.14 / 60, 4)


def test_une_ligne_sans_periode_garde_son_equivalent_mensuel():
    """Les charges stables et les lignes d'avant la migration ne bougent pas d'un centime."""
    assert ch.taux_jour(LOYER) is None
    assert ch.part_mensuelle(LOYER, date(2026, 9, 15)) == 700.0


def test_chaque_mois_porte_les_jours_quil_a_consommes():
    """
    ⚠️ C'EST TOUT L'OBJET. Juillet n'a que 11 jours couverts, août les 31, septembre 18 — et la
    somme des trois fait la facture. Imputer 176,14 € à un seul des trois mois serait faux dans
    les trois.
    """
    close = {**EPAL, "valid_to": "2026-09-19"}
    j = round(ch.part_mensuelle(close, date(2026, 7, 15)), 2)
    a = round(ch.part_mensuelle(close, date(2026, 8, 15)), 2)
    s = round(ch.part_mensuelle(close, date(2026, 9, 15)), 2)
    assert (j, a, s) == (32.29, 91.01, 52.84)
    assert round(j + a + s, 2) == 176.14, "la somme des trois mois doit faire la facture"


def test_la_derniere_facture_prolonge_son_taux_sur_les_jours_suivants():
    """
    ⚠️ C'EST L'ESTIMATION, ET ELLE SORT DE LA MÊME RÈGLE. La ligne reste ouverte : octobre entier
    est « en vigueur », donc 31 jours au taux de la dernière facture. Pas de second calcul à
    tenir d'accord avec le premier.
    """
    assert round(ch.part_mensuelle(EPAL, date(2026, 10, 15)), 2) == round(176.14 / 60 * 31, 2)


def test_le_mois_qui_precede_la_periode_ne_porte_rien():
    """La ligne n'est pas encore en vigueur : zéro jour couvert, pas un prorata inventé."""
    assert ch.part_mensuelle(EPAL, date(2026, 6, 15)) == 0.0


def test_le_total_mensuel_additionne_les_deux_regimes():
    close = {**EPAL, "valid_to": "2026-09-19"}
    assert round(ch.charges_mensuelles([LOYER, close], date(2026, 8, 15)), 2) == round(700 + 91.01, 2)


def test_une_periode_a_lenvers_est_ignoree_pas_negative():
    """Une saisie inversée doit retomber sur l'ancien comportement, jamais produire un crédit."""
    tordue = {**EPAL, "periode_debut": "2026-09-18", "periode_fin": "2026-07-21"}
    assert ch.taux_jour(tordue) is None
    assert ch.part_mensuelle(tordue, date(2026, 8, 15)) == 176.14


def test_une_facture_dun_seul_jour_ne_divise_pas_par_zero():
    court = {**EPAL, "periode_debut": "2026-08-10", "periode_fin": "2026-08-10", "amount": 5.0}
    assert ch.taux_jour(court) == 5.0


def test_estime_se_dit_au_jour_pres_quand_la_periode_est_connue():
    """
    ⚠️ UNE FACTURE DE 60 JOURS FINIT LE 18, PAS LE 30. Le 15 septembre est encore mesuré, le
    19 ne l'est plus — raisonner par mois aurait déclaré septembre entier mesuré, alors que ses
    douze derniers jours sont une prolongation.
    """
    assert ch.facture_estimee(EPAL, date(2026, 9, 15)) is False
    assert ch.facture_estimee(EPAL, date(2026, 9, 18)) is False
    assert ch.facture_estimee(EPAL, date(2026, 9, 19)) is True
    assert ch.facture_estimee(EPAL, date(2026, 10, 2)) is True


def test_sans_periode_le_raisonnement_par_mois_reste():
    """Les lignes d'avant la migration gardent leur règle : rien ne change sous elles."""
    assert ch.facture_estimee(facture("2026-09-01", 77.10), date(2026, 9, 20)) is False
    assert ch.facture_estimee(facture("2026-09-01", 77.10), date(2026, 10, 2)) is True


def test_deux_factures_dune_periode_se_suivent_sans_trou_ni_recouvrement():
    """
    ⚠️ LA FACTURE SUIVANTE BORNE LA PRÉCÉDENTE, AU JOUR. L'EPAL enchaîne : 21/07→18/09, puis
    19/09→… La première doit s'arrêter exactement là où la seconde commence, sinon les deux
    taux s'additionnent sur les jours partagés, ou aucun ne couvre les jours du trou.
    """
    debut, fin, a_cloturer = ch.bornes_dune_facture(
        [EPAL], "Eau", date(2026, 9, 19))
    assert (debut, fin) == (date(2026, 9, 19), None)
    assert a_cloturer == [(EPAL, date(2026, 9, 19))]


def test_rattraper_une_periode_anterieure_la_place_entre_ses_voisines():
    precedente = {**EPAL, "periode_debut": "2026-05-22", "periode_fin": "2026-07-20",
                  "valid_from": "2026-05-22", "valid_to": "2026-07-21", "amount": 160.0}
    _, fin, a_cloturer = ch.bornes_dune_facture(
        [precedente, EPAL], "Eau", date(2026, 3, 23))
    assert fin == date(2026, 5, 22), "elle doit s'arrêter où la suivante commence"
    assert a_cloturer == [], "aucune ligne n'était en vigueur ce jour-là"


def test_resaisir_la_meme_periode_ne_se_cloture_pas_elle_meme():
    """Sans ce garde-fou, corriger une facture la fermerait sur son propre premier jour."""
    _, _, a_cloturer = ch.bornes_dune_facture([EPAL], "Eau", date(2026, 7, 21))
    assert a_cloturer == []


def test_une_ligne_sans_bornes_mais_avec_periode_commence_a_sa_periode():
    """Posée hors de la route (import, correction à la main), elle garde un début lisible."""
    sans_bornes = {k: v for k, v in EPAL.items() if k != "valid_from"}
    assert ch.debut_dune_ligne(sans_bornes) == date(2026, 7, 21)


def test_a_defaut_de_tout_le_mois_sert_de_debut():
    """Les lignes d'avant la migration n'ont ni période ni bornes : leur mois les situe."""
    assert ch.debut_dune_ligne({"name": "x", "mode": "facture", "mois": "2026-09-01"}) \
        == date(2026, 9, 1)


# ── Jusqu'à quand sait-on ───────────────────────────────────────────────────────────────────

def test_la_couverture_sarrete_au_dernier_jour_facture():
    c = ch.couverture([EPAL], "Eau", date(2026, 10, 4))
    assert c["jusqua"] == date(2026, 9, 18)
    assert c["jours"] == 16, "16 jours extrapolés depuis la fin de la facture"
    assert c["debut_suivant"] == date(2026, 9, 19), "le lendemain, pour ne pas laisser de trou"


def test_une_facture_sans_periode_est_lue_comme_couvrant_son_mois():
    """Les lignes d'avant la migration prétendaient couvrir leur mois : on les prend au mot."""
    c = ch.couverture([facture("2026-09-01", 77.10)], "Électricité", date(2026, 10, 4))
    assert c["jusqua"] == date(2026, 9, 30) and c["jours"] == 4


def test_sans_aucune_facture_il_ny_a_rien_a_extrapoler():
    c = ch.couverture([], "Eau", date(2026, 10, 4))
    assert c == {"jusqua": None, "jours": 0, "debut_suivant": None}


def test_une_facture_qui_couvre_aujourdhui_ne_compte_aucun_jour_estime():
    c = ch.couverture([EPAL], "Eau", date(2026, 9, 10))
    assert c["jours"] == 0, "le jour calculé est dans la période : rien n'est extrapolé"


def test_cest_la_facture_la_plus_recente_qui_fixe_la_couverture():
    vieille = {**EPAL, "periode_debut": "2026-05-22", "periode_fin": "2026-07-20"}
    c = ch.couverture([vieille, EPAL], "Eau", date(2026, 10, 4))
    assert c["jusqua"] == date(2026, 9, 18)


def test_la_couverture_de_leau_ignore_les_factures_delectricite():
    """
    ⚠️ LES DEUX CHARGES VIVENT DANS LA MÊME TABLE. Sans le filtre, une facture d'électricité
    plus récente ferait croire l'eau à jour — et l'écran cesserait de réclamer celle qui manque.
    """
    elec = {**EPAL, "name": "Électricité", "periode_debut": "2026-09-19",
            "periode_fin": "2026-10-03"}
    c = ch.couverture([EPAL, elec], "Eau", date(2026, 10, 4))
    assert c["jusqua"] == date(2026, 9, 18) and c["jours"] == 16
