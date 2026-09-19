"""
LE SUIVI DE CONVERSION — est-ce que demander le numéro au comptoir marche ?

Quentin commence à demander les numéros la semaine du 21 septembre 2026. Ce qu'il veut voir
n'est pas un taux, c'est une COURBE : est-ce que ça monte, et quelle semaine a été bonne.

⚠️ CE QUI REND CE CALCUL PIÉGEUX, C'EST QUE LE DÉNOMINATEUR BOUGE. Chaque semaine amène de
nouveaux clients revenus, qui n'ont pas encore eu l'occasion de donner leur numéro. Calculer le
taux des semaines passées avec le dénominateur d'AUJOURD'HUI écraserait les débuts et ferait
croire à une progression qui n'a pas eu lieu — ou, pire, à une stagnation.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from programme import conversion_series  # noqa: E402

LISBONNE = ZoneInfo("Europe/Lisbon")
# Un samedi. La semaine en cours a commencé le lundi 14.
MAINTENANT = datetime(2026, 9, 19, 12, 0, tzinfo=LISBONNE)


def v(fp, jour):
    return {"fp": fp, "ts": f"2026-{jour}T10:00:00+00:00"}


def lien(fp, tel, jour):
    return {"fp": fp, "phone": tel, "linked_at": f"2026-{jour}T10:00:00+00:00"}


def client(tel, jour):
    return {"phone": tel, "consent_at": f"2026-{jour}T10:00:00+00:00", "opted_out_at": None}


def serie(visits=(), links=(), customers=(), weeks=4):
    return conversion_series(list(visits), list(links), list(customers), MAINTENANT, weeks)


def test_la_courbe_couvre_les_semaines_demandees():
    d = serie(weeks=4)
    assert [s["start"] for s in d["weeks"]] == ["2026-08-24", "2026-08-31", "2026-09-07", "2026-09-14"]


def test_seules_les_cartes_qui_reviennent_entrent_au_denominateur():
    """
    ⚠️ UN TOURISTE VENU UNE FOIS N'AVAIT AUCUNE RAISON DE DONNER SON NUMÉRO. Au dénominateur, il
    ferait baisser le taux chaque fois qu'un inconnu entre : la courbe mesurerait la
    fréquentation au lieu de l'effort fait au comptoir.
    """
    d = serie(visits=[
        v("revient", "09-01"), v("revient", "09-08"),
        v("passant", "09-02"),
    ])
    assert d["weeks"][-1]["returning"] == 1


def test_une_carte_devient_revenue_a_son_DEUXIEME_passage_pas_avant():
    """La semaine du premier passage, elle ne compte pas encore ; celle du second, oui."""
    d = serie(visits=[v("c", "09-02"), v("c", "09-10")])
    par_semaine = {s["start"]: s["returning"] for s in d["weeks"]}
    assert par_semaine["2026-08-31"] == 0   # premier passage seulement
    assert par_semaine["2026-09-07"] == 1   # le second est tombé cette semaine-là


def test_le_taux_passe_est_calcule_avec_le_denominateur_DE_L_EPOQUE():
    """
    ⚠️ LE CŒUR DU SUIVI. Fin août : une carte revenue, rattachée → 100 %. Mi-septembre : trois
    revenues, toujours une seule rattachée → 33 %. Si on recalculait tout avec le dénominateur
    d'aujourd'hui, la première semaine afficherait 33 % elle aussi, et la courbe raconterait une
    stagnation là où il y a eu un vrai recul du taux.
    """
    d = serie(visits=[
        v("a", "08-20"), v("a", "08-25"),
        v("b", "09-08"), v("b", "09-09"),
        v("c", "09-10"), v("c", "09-11"),
    ], links=[lien("a", "+351911", "08-26")], customers=[client("+351911", "08-26")])
    par_semaine = {s["start"]: s for s in d["weeks"]}
    assert par_semaine["2026-08-24"]["rate_pct"] == 100.0
    assert par_semaine["2026-09-07"]["rate_pct"] == 33.3
    assert par_semaine["2026-09-14"]["returning"] == 3


def test_un_rattachement_futur_ne_remonte_pas_dans_le_passe():
    """Rattacher quelqu'un aujourd'hui ne doit pas repeindre les semaines d'avant en vert."""
    d = serie(visits=[v("a", "08-20"), v("a", "08-25")],
              links=[lien("a", "+351911", "09-17")], customers=[client("+351911", "09-17")])
    par_semaine = {s["start"]: s for s in d["weeks"]}
    assert par_semaine["2026-08-24"]["linked"] == 0
    assert par_semaine["2026-08-24"]["rate_pct"] == 0.0
    assert par_semaine["2026-09-14"]["linked"] == 1


def test_sans_personne_de_revenu_le_taux_est_absent_et_non_nul():
    d = serie(visits=[v("passant", "09-02")])
    assert d["weeks"][-1]["rate_pct"] is None


def test_les_nouveaux_inscrits_se_comptent_en_PERSONNES():
    """
    ⚠️ DEUX CARTES SUR LE MÊME NUMÉRO, C'EST UN CLIENT CONVAINCU, PAS DEUX. Compter les liens
    ferait paraître la semaine deux fois meilleure qu'elle ne l'a été — et c'est le chiffre
    qu'on regardera pour décider si la façon de demander fonctionne.
    """
    d = serie(links=[lien("carte1", "+351911", "09-15"), lien("carte2", "+351911", "09-16")],
              customers=[client("+351911", "09-15")])
    derniere = d["weeks"][-1]
    assert derniere["new_customers"] == 1
    assert derniere["new_links"] == 2
    assert d["this_week_customers"] == 1
    assert d["this_week_links"] == 2


def test_un_rattachement_sans_date_est_dit_et_non_range_au_debut():
    """
    ⚠️ LE RANGER D'OFFICE À LA PREMIÈRE SEMAINE GONFLERAIT LES DÉBUTS et ferait croire à un
    départ en fanfare. On préfère un chiffre à part, visible, qu'une courbe jolie et fausse.
    """
    d = serie(visits=[v("a", "08-20"), v("a", "08-25")],
              links=[{"fp": "a", "phone": "+351911", "linked_at": None}],
              customers=[{"phone": "+351911", "consent_at": None, "opted_out_at": None}])
    assert d["undated_links"] == 1
    assert all(s["linked"] == 0 for s in d["weeks"])


def test_un_lien_sans_date_retombe_sur_la_date_du_consentement():
    """Le numéro a bien été donné un jour connu : l'information existe, elle est juste ailleurs."""
    d = serie(visits=[v("a", "08-20"), v("a", "08-25")],
              links=[{"fp": "a", "phone": "+351911", "linked_at": None}],
              customers=[client("+351911", "08-26")])
    assert d["undated_links"] == 0
    assert {s["start"]: s["linked"] for s in d["weeks"]}["2026-08-24"] == 1


def test_les_desabonnes_sont_comptes_a_part():
    d = serie(customers=[{"phone": "+351911", "consent_at": "2026-09-15T10:00:00+00:00",
                          "opted_out_at": "2026-09-16T10:00:00+00:00"}])
    assert d["customers_total"] == 1
    assert d["opted_out"] == 1


def test_la_semaine_en_cours_s_arrete_a_maintenant():
    """
    ⚠️ ELLE N'EST PAS FINIE. Une semaine tronquée à l'instant présent se compare mal aux
    précédentes — mais la compter jusqu'à dimanche prochain donnerait un `new_customers` figé
    qui semble s'être arrêté. On coupe à maintenant, et l'écran dit que la semaine court.
    """
    d = serie(links=[lien("a", "+351911", "09-19")], customers=[client("+351911", "09-19")])
    assert d["weeks"][-1]["new_customers"] == 1
    d2 = serie(links=[lien("a", "+351911", "09-20")], customers=[client("+351911", "09-20")])
    assert d2["weeks"][-1]["new_customers"] == 0


def test_un_programme_vide_ne_divise_par_rien():
    d = serie()
    assert d["customers_total"] == 0
    assert d["this_week_customers"] == 0
    assert all(s["rate_pct"] is None for s in d["weeks"])


def test_une_carte_vue_deux_fois_garde_sa_PREMIERE_date_de_rattachement():
    """
    ⚠️ CE N'EST PAS UN CAS THÉORIQUE. `fp` est bien clé primaire dans `card_links`, mais la
    lecture se fait PAR PAGES (`_supa_all`, `offset`) : si une ligne est insérée entre deux
    pages, tout décale et une ligne peut être lue deux fois. Garder la date la plus TARDIVE
    reculerait le rattachement de quelqu'un sur la courbe — et ferait disparaître une conversion
    de la semaine où elle a réellement eu lieu.
    """
    d = serie(
        visits=[v("a", "08-20"), v("a", "08-25")],
        links=[lien("a", "+351911", "08-26"), lien("a", "+351911", "09-16")],
        customers=[client("+351911", "08-26")],
    )
    par_semaine = {s["start"]: s for s in d["weeks"]}
    assert par_semaine["2026-08-24"]["linked"] == 1, "le rattachement d'août a été repoussé"
    assert par_semaine["2026-08-24"]["new_links"] == 1
    # Et il n'est compté qu'UNE fois, pas une par doublon.
    assert sum(s["new_links"] for s in d["weeks"]) == 1
