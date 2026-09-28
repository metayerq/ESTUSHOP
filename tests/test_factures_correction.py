# -*- coding: utf-8 -*-
"""
CORRIGER UNE FACTURE SCANNÉE, C'EST ÉCRIRE DANS LES COÛTS.

⚠️ CE FICHIER EXISTE PARCE QUE LE DANGER DE CET ÉCRAN EST INVISIBLE. Rattacher une ligne à un
ingrédient ressemble à poser une étiquette ; en réalité `qty_ref × price_per_ref` devient la
dépense retenue pour cet ingrédient, et cette dépense nourrit le coût de revient. Une conversion
approximative ne se voit nulle part : elle produit un prix d'achat plausible, la marge bouge un
peu, et personne ne sait pourquoi.

Ce qu'on éprouve ici est donc une seule chose : que le calcul REFUSE de deviner.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _references_ligne, _unite_normale


def test_les_unites_imprimees_sur_les_factures_sont_reconnues():
    # ⚠️ LES FACTURES N'ÉCRIVENT PAS « unit » NI « kg ». Elles écrivent « Uni », « KG », « Lt ».
    # La table de conversion, elle, ne connaît que les formes canoniques : sans normalisation,
    # AUCUNE ligne réelle ne se convertissait jamais.
    assert _unite_normale("Uni") == "unit"
    assert _unite_normale("  KG ") == "kg"
    assert _unite_normale("Lt") == "l"
    assert _unite_normale("kg") == "kg"
    # Une unité inconnue reste elle-même : c'est ce qui la fera échouer plus loin, visiblement.
    assert _unite_normale("barquette") == "barquette"


def test_un_kilo_paye_donne_le_prix_au_kilo():
    qty_ref, prix, raison = _references_ligne(1, "KG", "kg", 2870)
    assert raison is None
    assert qty_ref == 1.0
    assert abs(prix - 28.70) < 1e-9


def test_des_grammes_se_ramenent_au_kilo():
    qty_ref, prix, raison = _references_ligne(500, "g", "kg", 1435)
    assert raison is None
    assert abs(qty_ref - 0.5) < 1e-9
    # 14,35 € pour un demi-kilo : 28,70 € le kilo.
    assert abs(prix - 28.70) < 1e-9


def test_le_prix_vient_de_ce_qui_a_ete_paye_pas_du_catalogue():
    """
    ⚠️ C'EST LE POINT DE TOUTE L'OPÉRATION. Scanner les factures sert à apprendre le prix RÉEL.
    Reprendre `ingredients.price` reviendrait à confirmer ce qu'on croyait déjà savoir, et une
    hausse du fournisseur resterait invisible jusqu'au jour où quelqu'un la saisit à la main.
    """
    _, prix, _ = _references_ligne(2, "kg", "kg", 7000)
    assert abs(prix - 35.0) < 1e-9  # et non les 28,70 € du catalogue


def test_une_conversion_inconnue_ne_produit_aucun_chiffre():
    """
    ⚠️ « Uni » FACE À UN INGRÉDIENT AU KILO PEUT VOULOIR DIRE N'IMPORTE QUOI : une pièce de
    200 g comme un sac de 5 kg. Le seul résultat honnête est l'absence de résultat, assortie de
    sa raison. Un chiffre plausible se propagerait jusqu'à la marge sans que personne puisse
    remonter à sa source ; un trou déclaré, lui, se voit à l'écran.
    """
    qty_ref, prix, raison = _references_ligne(2, "Uni", "kg", 900)
    assert qty_ref is None
    assert prix is None
    assert "Uni" in raison and "kg" in raison


def test_une_quantite_nulle_ne_fabrique_pas_un_prix_infini():
    qty_ref, prix, raison = _references_ligne(0, "kg", "kg", 900)
    assert qty_ref == 0
    assert prix is None
    assert raison


def test_une_quantite_illisible_est_refusee_pas_arrondie():
    qty_ref, prix, raison = _references_ligne("deux", "kg", "kg", 900)
    assert (qty_ref, prix) == (None, None)
    assert raison


def test_sans_unite_de_reference_on_ne_calcule_rien():
    # Un ingrédient sans `unit_ref` en base : on ne sait pas dans quoi convertir.
    qty_ref, prix, raison = _references_ligne(1, "kg", None, 900)
    assert (qty_ref, prix) == (None, None)
    assert raison
