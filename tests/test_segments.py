"""
DÉCOUPER LA JOURNÉE — le service de jour, le service du soir.

⚠️ UN ÉVÉNEMENT DU SOIR FAUSSE LA COMPARAISON DES JOURS. Un concert un vendredi ajoute quarante
tickets à ce vendredi-là ; la médiane du vendredi monte, et l'on conclut que le vendredi se
tient mieux que le jeudi. C'est l'événement qu'on mesure, pas le café.
"""

import pytest

import segments as S


def jour(iso, heures, **kw):
    base = {"day": iso, "nb": sum(heures.values()) if heures else 0, "ca_ttc": 300.0,
            "covers": 40, "covers_capped": 0, "covers_measured": 2, "covers_estimated": 8,
            "multi_count": 9, "hours": heures, "weekday": 0, "partial": False}
    base.update(kw)
    return base


# ── Les bornes ───────────────────────────────────────────────────────────────────────────────

def test_le_soir_du_filtre_est_celui_du_graphique():
    """
    ⚠️ DEUX DÉFINITIONS DU « SOIR » QUI DÉRIVENT, ET LE BLOC DU GRAPHIQUE CESSE DE CORRESPONDRE
    AU FILTRE QUI PRÉTEND L'EXCLURE. On exclurait 19h-23h en croyant exclure 20h-23h, et le
    chiffre de la page ne serait plus celui qu'elle dessine.
    """
    import app
    bloc = [b for b in app._tx_hourly.__doc__.split("\n") if "BLOCS" in b] or [""]
    src = open("app.py", encoding="utf-8").read()
    i = src.index('BLOCS = (("morning"')
    ligne = src[i:src.index("\n", i)]
    assert f'"evening", {S.SOIR_DEBUT}, {S.SOIR_FIN}' in ligne, ligne


@pytest.mark.parametrize("heure,jour_,soir", [
    (18, True, False),
    (19, False, True),      # la borne basse du soir est INCLUSE
    (23, False, True),      # la borne haute aussi
    (7, True, False),
])
def test_chaque_heure_tombe_dans_un_seul_camp(heure, jour_, soir):
    assert S._dans_segment(heure, "day") is jour_
    assert S._dans_segment(heure, "evening") is soir
    assert S._dans_segment(heure, "all") is True


# ── Ce qui est écarté, et pourquoi ───────────────────────────────────────────────────────────

def test_un_jour_sans_mesure_horaire_est_ecarte_pas_compte_a_zero():
    """
    ⚠️ UN JOUR SANS `hours` N'EST PAS UN JOUR SANS SOIRÉE. Les lignes écrites avant l'existence
    du champ n'ont pas « zéro ticket le soir », elles n'ont pas la mesure. Les compter à zéro
    ferait chuter toutes les médianes du soir — et d'autant plus que l'historique est ancien,
    ce qui ressemblerait exactement à une tendance.
    """
    gardes, ecartes = S.appliquer([jour("2026-09-18", None)], "evening")
    assert gardes == []
    assert ecartes == 1


def test_une_soiree_vide_est_une_mesure_pas_une_absence():
    """Ce soir-là, personne n'est venu — c'est une information, et elle doit compter."""
    gardes, ecartes = S.appliquer([jour("2026-09-18", {"9": 10})], "evening")
    assert len(gardes) == 1 and gardes[0]["nb"] == 0
    assert ecartes == 0


def test_un_dict_horaire_abime_nabat_pas_le_calcul():
    g, _ = S.appliquer([jour("2026-09-18", {"9": 10, "midi": 5, "99": 3, "20": 4})], "day")
    assert g[0]["nb"] == 10


# ── Ce que le filtre n'a pas le droit de recopier ────────────────────────────────────────────

@pytest.mark.parametrize("segment", ["day", "evening"])
def test_le_ca_de_la_journee_ne_suit_pas_un_compte_filtre(segment):
    """
    ⚠️ LE CACHE STOCKE LE CA PAR JOUR, PAS PAR HEURE. Laisser 300 € à côté de 10 tickets de
    matinée donnerait un panier de 30 € au lieu de 10 — faux d'un facteur trois, et rien à
    l'écran ne le dirait. Ce qui ne peut pas être découpé se tait.
    """
    g, _ = S.appliquer([jour("2026-09-18", {"9": 10, "20": 20})], segment)
    assert g[0]["ca_ttc"] is None
    assert g[0]["covers"] is None
    assert g[0]["multi_count"] is None


def test_sans_filtre_rien_nest_touche():
    """Le mode « journée entière » doit rendre exactement ce que le cache contient."""
    src = [jour("2026-09-18", {"9": 10, "20": 20})]
    g, e = S.appliquer(src, "all")
    assert g == src and e == 0


def test_le_total_des_deux_segments_fait_la_journee():
    """
    ⚠️ SI LA SOMME NE RETOMBE PAS SUR LE TOTAL, UNE HEURE EST DANS LES DEUX CAMPS OU DANS AUCUN.
    C'est le seul contrôle qui attrape une borne mal posée sans qu'on ait à la relire.
    """
    heures = {str(h): h for h in range(7, 24)}
    d, _ = S.appliquer([jour("2026-09-18", heures)], "day")
    s, _ = S.appliquer([jour("2026-09-18", heures)], "evening")
    assert d[0]["nb"] + s[0]["nb"] == sum(heures.values())


# ── Le segment demandé ───────────────────────────────────────────────────────────────────────

def test_le_defaut_exclut_le_soir():
    """
    ⚠️ C'EST L'USAGE COURANT DE LA PAGE QUI COMMANDE LE DÉFAUT. Comparer des jours entre eux est
    ce qu'on vient y faire ; les soirées d'événement sont l'exception qui la fausse. Un défaut
    qui inclut tout donnerait raison à l'exception.
    """
    assert S.SEGMENT_DEFAUT == "day"
    assert S.normaliser(None) == "day"


@pytest.mark.parametrize("brut", ["", "matin", "DAY", "'; drop table", None, 7])
def test_un_segment_inconnu_retombe_sur_le_defaut(brut):
    assert S.normaliser(brut) == "day"


@pytest.mark.parametrize("segment", ["day", "evening", "all"])
def test_les_trois_segments_sont_acceptes(segment):
    assert S.normaliser(segment) == segment


def test_la_mesure_horaire_ne_survit_pas_au_filtre():
    """
    ⚠️ `hours` EST UNE MESURE DE LA JOURNÉE ENTIÈRE. La laisser sur un jour filtré ferait
    dessiner la répartition horaire complète à partir de jours qui prétendent ne contenir que
    le matin — et c'est ce graphique qui JUSTIFIE le filtre appliqué juste au-dessus.
    """
    g, _ = S.appliquer([jour("2026-09-18", {"9": 10, "20": 20})], "day")
    assert g[0]["hours"] is None
