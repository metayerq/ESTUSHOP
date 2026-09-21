"""
CE QUE `config.py` N'A PLUS LE DROIT DE PORTER.

⚠️ UN FICHIER DE CONFIGURATION QU'ON PEUT ÉDITER SANS EFFET EST PIRE QU'UN FICHIER ABSENT : il
donne la sensation d'avoir agi. `config.py` portait quinze postes de charges et deux salaires en
dur — loyer à 700 €, Julie à 1 000 € — que plus personne n'importait. Les modifier ne changeait
ni la marge, ni le point mort, ni l'EBITDA.

⚠️ ET CHACUNE NE SERVAIT QU'À LA SUIVANTE. La chaîne partait de `CHARGES_FIXES` et finissait sur
`SEUIL_CA_JOUR_TTC`, que personne ne lisait : quatorze constantes dont aucune n'atteignait un
écran. C'est ce qui rend ce genre de code si durable — il ne casse jamais.
"""

import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = open(os.path.join(RACINE, "config.py"), encoding="utf-8").read()
APP = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()


def definitions(source):
    """Les noms RÉELLEMENT définis — pas ceux cités dans un commentaire."""
    sans_commentaires = re.sub(r"(?m)^\s*#.*$", "", source)
    return set(re.findall(r"(?m)^([A-Z_][A-Z0-9_]*)\s*=", sans_commentaires))


@pytest.mark.parametrize("mort", [
    "CHARGES_FIXES", "PERSONNEL",
    "TOTAL_CHARGES_FIXES_MOIS", "TOTAL_PERSONNEL_MOIS", "TOTAL_CHARGES_MOIS",
    "COUT_FIXE_JOUR", "COUT_PERSONNEL_JOUR", "COUT_TOTAL_JOUR", "AMORT_JOUR",
    "SEUIL_CA_JOUR", "SEUIL_CA_JOUR_TTC",
    "MARGE_BP_BOISSONS", "MARGE_BP_PATISSERIES", "MARGE_BP_LIVRES",
])
def test_la_copie_morte_des_charges_ne_revient_pas(mort):
    """
    ⚠️ LA VRAIE SOURCE EST SUPABASE : `charges_fixes` et `employees`, éditées sur `/charges`,
    lues par `daily_economics` ET par la caisse Mesa. Remettre une copie ici recréerait un
    second endroit où « changer le loyer » — dont un seul aurait un effet.
    """
    assert mort not in definitions(CONFIG)


def test_le_seuil_de_points_nest_plus_dupplique():
    """
    ⚠️ IL VIT DANS `card_settings.threshold_points`, réglable depuis `/loyalty` avec simulation,
    motif et journal. Deux seuils, c'est un jour où l'écran annonce 50 et la caisse en compte
    un autre — devant le client.
    """
    assert "POINTS_THRESHOLD" not in definitions(APP)


@pytest.mark.parametrize("vivant", [
    "AMORTISSEMENT_MOIS", "JOURS_OUVERTS_MOIS", "MARGE_BP_GLOBALE",
    "TVA_MOYENNE_BLENDED", "OPEN_WEEKDAYS", "SCHEDULE_CUTOVER", "LAUNCH_OPEN_DAYS",
])
def test_ce_qui_sert_encore_est_toujours_la(vivant):
    """
    ⚠️ LE RISQUE SYMÉTRIQUE DU NETTOYAGE. Supprimer une constante encore lue casse le calcul
    sans toujours lever : `AMORTISSEMENT_MOIS` manquant ferait tomber `daily_economics`, mais
    une valeur de repli silencieuse aurait juste faussé l'EBITDA.
    """
    assert vivant in definitions(CONFIG)


def test_le_fichier_dit_ou_sont_passees_les_charges():
    """Un nettoyage muet fait chercher pendant une heure ce qui a été retiré délibérément."""
    assert "charges_fixes" in CONFIG and "employees" in CONFIG
    assert "/charges" in CONFIG
