"""
LA RÉPONSE DE LA PAGE FIDÉLITÉ — « le programme prend-il ? »

⚠️ LA SÉRIE EST CUMULATIVE, ET C'EST LE PIÈGE CENTRAL. Chaque semaine porte le taux de
rattachement sur TOUS les revenants depuis le début, pas sur la cohorte de la semaine. Un écart
s'y lit donc en POINTS : passer de 30 % à 33 %, c'est +3 points. L'écrire « +10 % » serait vrai
arithmétiquement et faux de sens — personne ne lit un taux de rattachement comme une variation
relative.
"""

import pytest

from programme import conversion_headline


def sem(start, returning, linked):
    return {"start": start, "returning": returning, "linked": linked,
            "rate_pct": round(linked * 100.0 / returning, 1) if returning else None,
            "new_links": 0, "new_customers": 0}


SERIE = [
    sem("2026-07-06", 10, 2),    # 20,0 %
    sem("2026-07-13", 14, 4),    # 28,6 %
    sem("2026-07-20", 18, 6),    # 33,3 %
    sem("2026-07-27", 22, 8),    # 36,4 %
    sem("2026-08-03", 26, 11),   # 42,3 %
    sem("2026-08-10", 28, 12),   # semaine EN COURS, tronquée
]


# ── La semaine en cours ──────────────────────────────────────────────────────────────────────

def test_la_semaine_en_cours_ne_porte_jamais_la_reponse():
    """
    ⚠️ ELLE EST TRONQUÉE PAR CONSTRUCTION. La lire comme les autres ferait annoncer un recul
    tous les lundis matin, puis une reprise tous les dimanches soir — un cycle hebdomadaire
    entièrement fabriqué par le découpage.
    """
    h = conversion_headline(SERIE)
    assert h["week"] == "2026-08-03"
    assert h["rate_pct"] == 42.3


def test_une_seule_semaine_en_cours_ne_repond_a_rien():
    h = conversion_headline([sem("2026-08-10", 28, 12)])
    assert h["ok"] is False and h["reason"] == "no-complete-week"
    assert h["rate_pct"] is None


# ── L'écart ──────────────────────────────────────────────────────────────────────────────────

def test_lecart_se_compte_en_points_pas_en_pourcentage():
    """20,0 % → 42,3 % fait +22,3 POINTS. En relatif ce serait +111 %, ce qui ne veut rien dire
    pour un taux de rattachement."""
    h = conversion_headline(SERIE)
    assert h["delta_pts"] == 22.3
    assert h["prev"] == 20.0


def test_les_deux_bouts_sont_nommes_avec_leur_n():
    """
    ⚠️ UN ÉCART SANS SES DEUX BORNES EST UN NOMBRE QUI FLOTTE. Ici le dénominateur grossit à
    chaque semaine : comparer 42 % sur 26 personnes à 20 % sur 10 n'a pas le même poids que sur
    des effectifs égaux, et le lecteur doit pouvoir en juger.
    """
    h = conversion_headline(SERIE)
    assert (h["week"], h["n"]) == ("2026-08-03", 26)
    assert (h["prev_week"], h["prev_n"]) == ("2026-07-06", 10)
    assert h["weeks_between"] == 4


def test_sans_assez_de_recul_on_ne_compare_pas():
    """
    ⚠️ COMPARER CONTRE LA PREMIÈRE SEMAINE DU PROGRAMME OPPOSERAIT UN RÉGIME À UN DÉMARRAGE.
    Mieux vaut dire qu'on ne sait pas encore.
    """
    h = conversion_headline(SERIE[:3])
    assert h["ok"] is True and h["rate_pct"] == 28.6
    assert h["delta_pts"] is None and h["reason"] == "not-enough-weeks"


def test_le_recul_est_exactement_de_quatre_semaines_mesurees():
    h = conversion_headline(SERIE[:5] + [sem("2026-08-10", 28, 12)], recul=2)
    assert h["prev_week"] == "2026-07-20"


# ── Ce qui n'est pas mesuré ──────────────────────────────────────────────────────────────────

def test_une_semaine_sans_revenant_est_sautee_pas_comptee_a_zero():
    """
    ⚠️ UN TAUX ABSENT N'EST PAS UN TAUX DE ZÉRO. Une semaine sans personne de revenu n'a rien
    mesuré ; la compter pour zéro fabriquerait un effondrement au démarrage du programme — au
    moment précis où l'on regarde si l'idée prend.
    """
    serie = [sem("2026-06-29", 0, 0)] + SERIE
    assert serie[0]["rate_pct"] is None
    h = conversion_headline(serie)
    assert h["prev_week"] == "2026-07-06", "la semaine vide a servi de référence"


@pytest.mark.parametrize("lignes", [None, [], [{}], [{"rate_pct": None}]])
def test_une_serie_vide_ou_abimee_ne_leve_pas(lignes):
    h = conversion_headline(lignes)
    assert h["ok"] is False and h["rate_pct"] is None


def test_la_reponse_voyage_avec_la_serie():
    """L'écran ne doit pas avoir à la recalculer : une seule définition, côté serveur."""
    from datetime import datetime, timezone
    out = __import__("programme").conversion_series([], [], [], datetime(2026, 8, 12,
                                                    tzinfo=timezone.utc))
    assert "headline" in out
