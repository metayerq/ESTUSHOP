"""
TOUTE TABLE CRÉÉE DOIT DIRE CE QU'ELLE FAIT DE RLS.

⚠️ L'OUBLI NE SE VOIT PAS AU DÉPLOIEMENT, IL SE VOIT UN JOUR PLUS TARD, AU PIRE MOMENT. Supabase
active la sécurité au niveau ligne par défaut. Sans politique, la LECTURE ne renvoie pas
d'erreur : elle renvoie zéro ligne. L'application en conclut « pas encore configuré », sert ses
valeurs par défaut, affiche des champs parfaitement actifs — et c'est seulement à
l'enregistrement que ça casse, avec un message que personne ne relie aux réglages.

C'est arrivé le 19/09/2026 sur `card_settings` : la table existait, la page semblait
fonctionner, et « new row violates row-level security policy » est tombé au moment de valider.

Ce test ne choisit pas à la place de l'auteur — il exige seulement que le choix soit ÉCRIT.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DOSSIER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")

# `create table [if not exists] [public.]nom`
CREATION = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_][a-z0-9_]*)",
                      re.I)


def _migrations():
    return sorted(f for f in os.listdir(DOSSIER) if f.endswith(".sql"))


# ⚠️ DEUX FICHIERS ANTÉRIEURS À CETTE RÈGLE, ET ON NE LES RÉÉCRIT PAS. Une migration est le
# compte rendu de ce qui a été exécuté : la modifier après coup fait mentir l'archive. Leur état
# RLS a été réglé à la main ou par un défaut Supabase plus ancien, et il est vérifié par le fait
# que ces tables FONCTIONNENT en production depuis des mois.
#
# Cette liste ne doit pas grandir. Le test juste en dessous s'en assure.
ANTERIEURES = {
    # Lue par tout le tableau de bord depuis août : si RLS la bloquait, aucun chiffre ne
    # s'afficherait. La preuve est dans l'usage quotidien.
    "20260810_create_daily_summary.sql": "daily_summary tourne en production depuis août 2026",
    # Les tables de l'ancien programme « neuf boissons », supprimé le 19/09/2026. Plus aucun
    # code ne les lit ; leur état RLS n'a plus d'effet sur quoi que ce soit.
    "20260819_loyalty.sql": "loyalty_members / loyalty_events — programme retiré, tables mortes",
}


def test_la_liste_des_exceptions_ne_grandit_pas():
    """
    ⚠️ UNE LISTE D'EXCEPTIONS QUI S'ALLONGE EST UNE RÈGLE QUI S'ÉTEINT. Ajouter un fichier ici
    doit demander de toucher ce test — donc d'y réfléchir — plutôt que de faire taire un échec.
    """
    assert set(ANTERIEURES) == {
        "20260810_create_daily_summary.sql",
        "20260819_loyalty.sql",
    }
    for fichier in ANTERIEURES:
        assert os.path.exists(os.path.join(DOSSIER, fichier)), (
            f"{fichier} n'existe plus — retirer aussi son exception")


@pytest.mark.parametrize("fichier", _migrations())
def test_chaque_table_creee_tranche_sur_rls(fichier):
    if fichier in ANTERIEURES:
        pytest.skip(ANTERIEURES[fichier])

    chemin = os.path.join(DOSSIER, fichier)
    with open(chemin, encoding="utf-8") as f:
        sql = f.read()

    tables = CREATION.findall(sql)
    if not tables:
        return

    muettes = []
    for t in tables:
        # Soit on désactive RLS, soit on l'assume avec au moins une politique. Les deux se
        # défendent ; ne rien dire ne se défend pas.
        desactive = re.search(rf"alter\s+table\s+(?:public\.)?{t}\s+disable\s+row\s+level\s+security",
                              sql, re.I)
        politique = re.search(rf"create\s+policy[^;]*\bon\s+(?:public\.)?{t}\b", sql, re.I)
        if not desactive and not politique:
            muettes.append(t)

    assert not muettes, (
        f"{fichier} crée {muettes} sans rien dire de RLS. Sous Supabase, la lecture renverra "
        "zéro ligne SANS ERREUR et l'écriture échouera plus tard : ajouter "
        f"`alter table public.{muettes[0]} disable row level security;` — ou une politique "
        "explicite si l'accès doit être restreint."
    )


def test_le_dossier_de_migrations_est_bien_lu():
    """Un test qui ne parcourt aucun fichier passe toujours — et ne protège rien."""
    assert len(_migrations()) >= 10
