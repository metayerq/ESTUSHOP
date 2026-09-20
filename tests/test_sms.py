"""
LE COMPTAGE DES SEGMENTS, REJOUÉ SUR LES VECTEURS DE LA CAISSE.

⚠️ DEUX IMPLÉMENTATIONS DE LA MÊME RÈGLE, ET LA DIVERGENCE SE PAIE. L'écran de composition
compte pendant qu'on tape ; la caisse compte au moment d'envoyer. Si les deux ne tombent pas
d'accord, le patron valide « 1 segment » et reçoit une facture double — sur toute la liste, et
seulement à cause d'un caractère rare qui n'apparaissait dans aucun essai.

C'est la situation exacte qui avait produit deux barèmes de points incompatibles. Même remède :
les vecteurs sont produits par l'implémentation TypeScript, qui fait foi, et rejoués ici.
"""

import json
import os

import pytest

from sms import (
    CAMPAGNE_PREFIXE,
    CAMPAGNE_SORTIE,
    campagne_apercu,
    is_gsm7,
    sms_cost,
)

VECTEURS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors",
                        "loyalty_state.json")


def _vecteurs():
    with open(VECTEURS, encoding="utf-8") as f:
        return json.load(f)


def _cas():
    return [pytest.param(c, id=(c["texte"][:18] or "vide")) for c in _vecteurs()["smsCost"]]


@pytest.mark.parametrize("cas", _cas())
def test_le_cout_est_celui_de_la_caisse(cas):
    """
    ⚠️ SI CE TEST TOMBE, NE CORRIGE PAS LE VECTEUR : regarde laquelle des deux implémentations a
    bougé. Un comptage modifié d'un seul côté est exactement la panne qu'on rend impossible ici.
    """
    obtenu = sms_cost(cas["texte"])
    assert obtenu["gsm7"] == cas["gsm7"]
    assert obtenu["length"] == cas["length"]
    assert obtenu["segments"] == cas["segments"]


def test_le_piege_portugais_de_la_cedille():
    """
    ⚠️ « Ç » MAJUSCULE EST DANS L'ALPHABET, « ç » MINUSCULE NON. C'est le piège le plus coûteux
    du portugais : « começar », « serviço », « obrigação » font basculer le message ENTIER en
    UCS-2, et la limite tombe de 160 à 70 caractères.
    """
    assert is_gsm7("COMEÇAR")
    assert not is_gsm7("começar")
    assert not is_gsm7("pão")
    assert not is_gsm7("ó")
    # Ceux-là passent, et ce sont les plus utiles.
    assert is_gsm7("José à Lisboa, ò è ù ì ñ ü")


def test_la_bascule_de_segment_est_exacte():
    """160 tiennent en un segment ; 161 en coûtent DEUX, pas un et demi."""
    assert sms_cost("a" * 160)["segments"] == 1
    assert sms_cost("a" * 161)["segments"] == 2
    assert sms_cost("a" * 306)["segments"] == 2
    assert sms_cost("a" * 307)["segments"] == 3


def test_le_caractere_etendu_compte_double():
    """« € », « { », « } » s'écrivent sur deux septets — 80 euros font 160 caractères."""
    assert sms_cost("€")["length"] == 2
    assert sms_cost("€" * 80)["segments"] == 1
    assert sms_cost("€" * 81)["segments"] == 2


# ── L'enveloppe ──────────────────────────────────────────────────────────────────────────────

def test_lenveloppe_est_celle_de_la_caisse():
    """
    ⚠️ LE PRÉFIXE ET LA MENTION DE SORTIE SONT POSÉS PAR MESA, PAS ICI. Les recopier sert à
    compter juste ; s'ils divergeaient, le budget affiché serait faux de quelques caractères —
    assez pour faire basculer un message au second segment après validation.
    """
    # ⚠️ LES DEUX DÉPÔTS SONT VOISINS EN LOCAL, SÉPARÉS EN PRODUCTION. Ce test ne peut donc
    # s'exécuter que sur un poste qui a les deux — il se tait ailleurs plutôt que de rougir pour
    # une raison qui n'a rien à voir avec le code. La garantie qui ne se tait JAMAIS est
    # l'empreinte des vecteurs, vérifiée juste au-dessus.
    racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    chemin = os.path.join(racine, "mesa", "apps", "pos", "lib", "sms.ts")
    if not os.path.exists(chemin):
        pytest.skip("dépôt Mesa absent — vérifié en local et à la revue")
    with open(chemin, encoding="utf-8") as f:
        src = f.read()
    assert f'CAMPAGNE_PREFIXE = "{CAMPAGNE_PREFIXE}"' in src
    assert f'CAMPAGNE_SORTIE = "{CAMPAGNE_SORTIE}"' in src


def test_le_budget_nest_pas_cent_soixante():
    """
    ⚠️ ANNONCER 160 LAISSERAIT ÉCRIRE SOIXANTE CARACTÈRES DE TROP. L'enveloppe — nom du café,
    lien de la page client, mention de sortie — mange une bonne moitié du budget avant le
    premier mot.
    """
    budget = campagne_apercu("")["budget"]
    assert 40 < budget < 120


def test_le_budget_est_exact_au_caractere():
    budget = campagne_apercu("")["budget"]
    assert campagne_apercu("a" * budget)["segments"] == 1
    assert campagne_apercu("a" * (budget + 1))["segments"] == 2


def test_les_espaces_de_saisie_ne_sont_pas_factures():
    """Un retour à la ligne oublié en fin de zone de texte est un caractère payant."""
    assert campagne_apercu("  Amanha   temos  pao \n") == campagne_apercu("Amanha temos pao")


def test_lapercu_porte_toujours_la_sortie():
    a = campagne_apercu("Amanha temos pao quente")
    assert a["message"].startswith(CAMPAGNE_PREFIXE)
    assert a["message"].endswith(CAMPAGNE_SORTIE)
