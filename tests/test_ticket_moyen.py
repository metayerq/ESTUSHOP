# -*- coding: utf-8 -*-
"""
LA VENTE MOYENNE — ET CE QU'ELLE N'EST PAS.

⚠️ LE TICKET MÉLANGEAIT DEUX BASES. Son numérateur était net des avoirs, son dénominateur les
excluait : dix ventes à 5 € et un remboursement de 20 € affichaient 3,00 €, alors qu'aucune
vente de la journée n'avait changé. Le chiffre ne décrivait rien — ni la recette par vente, ni
la vente moyenne.

⚠️ ET LE CA, LUI, RESTE NET. C'est l'argent encaissé : un remboursement le diminue. Deux
questions, deux bases, et `ticket × nb` ne redonne donc plus `ca`. C'est exactement ce qu'on
voulait : la différence entre les deux EST l'avoir.
"""
import pytest

import vendus as V


def vente(ttc=5.0, ht=4.5):
    return {"amount_gross": ttc, "amount_net": ht}


def avoir(ttc=20.0, ht=18.0):
    return {"amount_gross": -ttc, "amount_net": -ht, "_refund": True}


def test_LA_VENTE_MOYENNE_IGNORE_LES_AVOIRS():
    """Le cas exact signalé : un remboursement de test déformait la moyenne des vraies ventes."""
    s = V.calc_stats([vente() for _ in range(10)] + [avoir()])
    assert s["ticket"] == 5.00, "le ticket subit encore le remboursement"
    assert s["nb"] == 10


def test_le_chiffre_daffaires_reste_net_des_avoirs():
    """Un remboursement diminue bien l'encaissement — c'est la seule base où il compte."""
    s = V.calc_stats([vente() for _ in range(10)] + [avoir()])
    assert s["ca"] == 30.00
    assert s["ca_ht"] == 27.00


def test_SANS_AVOIR_LES_DEUX_BASES_COINCIDENT():
    """La règle ne doit pas déplacer les chiffres d'une journée ordinaire."""
    s = V.calc_stats([vente() for _ in range(4)])
    assert s["ca"] == 20.00
    assert s["ticket"] == 5.00
    assert round(s["ticket"] * s["nb"], 2) == s["ca"]


def test_le_ticket_ht_suit_la_meme_regle():
    s = V.calc_stats([vente() for _ in range(10)] + [avoir()])
    assert s["ticket_ht"] == 4.50


def test_une_journee_sans_vente_ne_divise_pas_par_zero():
    """Un seul avoir : aucune vente, donc aucune moyenne — pas une division."""
    s = V.calc_stats([avoir()])
    assert s["nb"] == 0
    assert s["ticket"] == 0.0 and s["ticket_ht"] == 0.0
    assert s["ca"] == -20.00, "l'avoir reste dans l'encaissement"


def test_un_gros_avoir_ne_rend_pas_la_vente_moyenne_negative():
    """
    ⚠️ C'ÉTAIT POSSIBLE AVANT. Un avoir supérieur au total des ventes donnait un ticket moyen
    NÉGATIF — « le client moyen a rapporté −2,50 € » — pendant que dix ventes bien réelles
    figuraient juste à côté.
    """
    s = V.calc_stats([vente() for _ in range(10)] + [avoir(ttc=200.0, ht=180.0)])
    assert s["ticket"] == 5.00
    assert s["ca"] < 0, "l'encaissement, lui, est bien négatif"


def test_plusieurs_avoirs_ne_comptent_toujours_pas_comme_des_ventes():
    s = V.calc_stats([vente() for _ in range(3)] + [avoir(), avoir()])
    assert s["nb"] == 3 and s["ticket"] == 5.00
