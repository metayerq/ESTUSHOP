"""
« HABITUÉ » ET « À RISQUE » : TROIS IMPLÉMENTATIONS, UNE SEULE RÈGLE.

⚠️ LA MÊME RÈGLE EST ÉCRITE TROIS FOIS DANS CETTE MAISON. `_at_risk` la calcule pour la page
`/clientes`, `programme.py` pour le backoffice fidélité, et `lib/loyalty.ts` pour le bandeau de
la caisse. Toutes les trois disent aujourd'hui : habitué à partir de 4 passages, alerte au-delà
de `max(7 jours, 3 × intervalle médian)`.

Rien ne les oblige à continuer. Et une divergence ne casserait rien : la page « clients »
annoncerait douze habitués perdus, le backoffice en listerait neuf, et il faudrait un après-midi
pour comprendre lequel a raison — si tant est que quelqu'un remarque l'écart.

Ce fichier ne fusionne pas les trois : il les fait répondre aux mêmes questions. Le jour où l'une
change, ce test tombe, et le changement devient une décision au lieu d'un accident.

(Le troisième côté, TypeScript, est tenu par `mesa/apps/pos/lib/loyalty.vectors.json`, dont
l'empreinte est vérifiée dans les deux dépôts.)
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("VENDUS_API_KEY", "x")
import app as A  # noqa: E402
from programme import REGULAR_AFTER_VISITS, build_accounts  # noqa: E402

AUJOURD_HUI = "2026-09-19"
MAINTENANT = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _rows(jours, fp="fp1", cents=1000):
    """Le format que lit `_at_risk` : une ligne par visite, avec son jour."""
    return [{"fp": fp, "day": j, "ts": f"{j}T10:00:00+00:00", "amount": cents} for j in jours]


def _cote_fidelite(jours, fp="fp1", cents=1000):
    """Le même client, vu par le backoffice fidélité."""
    comptes = build_accounts(
        [{"fp": fp, "ts": f"{j}T10:00:00+00:00", "amount_cents": cents} for j in jours],
        [], [], [], 50, MAINTENANT,
    )
    return comptes[0]


CAS = [
    ("hebdomadaire, absent 32 jours",
     ["2026-07-21", "2026-07-28", "2026-08-04", "2026-08-18"], True, True),
    ("hebdomadaire, absent 11 jours — dans son rythme",
     ["2026-08-11", "2026-08-18", "2026-08-25", "2026-09-08"], True, False),
    ("quotidien, absent 5 jours — le café ferme deux jours",
     ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-14"], True, False),
    ("quotidien, absent 9 jours — au-delà du plancher de 7",
     ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"], True, True),
    ("trois passages seulement — pas encore une habitude",
     ["2026-06-01", "2026-06-08", "2026-06-15"], False, False),
    ("pile à son rythme, 21 jours pour un seuil de 21",
     ["2026-07-14", "2026-07-21", "2026-07-28", "2026-08-29"], True, False),
]


@pytest.mark.parametrize("nom,jours,habitue,a_risque", [pytest.param(*c, id=c[0]) for c in CAS])
def test_les_deux_moteurs_disent_la_meme_chose(nom, jours, habitue, a_risque):
    clientes = A._at_risk(_rows(jours), AUJOURD_HUI)
    fidelite = _cote_fidelite(jours)

    assert (clientes["regulars"] == 1) is habitue, f"/clientes : habitué ? ({nom})"
    assert fidelite["regular"] is habitue, f"backoffice : habitué ? ({nom})"

    assert (clientes["count"] == 1) is a_risque, f"/clientes : à risque ? ({nom})"
    assert fidelite["at_risk"] is a_risque, f"backoffice : à risque ? ({nom})"


def test_le_nombre_de_passages_qui_fait_un_habitue_est_le_meme():
    """
    Quatre des deux côtés. ⚠️ Le passer à cinq ici et pas là ferait diverger deux écrans qui
    prétendent compter les mêmes personnes.
    """
    assert REGULAR_AFTER_VISITS == 4
    jours = ["2026-09-01", "2026-09-08", "2026-09-15"]           # 3 passages
    assert A._at_risk(_rows(jours), AUJOURD_HUI)["regulars"] == 0
    assert _cote_fidelite(jours)["regular"] is False
    jours.append("2026-09-16")                                    # le quatrième
    assert A._at_risk(_rows(jours), AUJOURD_HUI)["regulars"] == 1
    assert _cote_fidelite(jours)["regular"] is True


def test_la_regle_affichee_a_l_ecran_est_celle_qui_est_calculee():
    """
    ⚠️ `/clientes` ÉCRIT SA RÈGLE EN TOUTES LETTRES SOUS LE CHIFFRE. Une phrase qui ne suit pas
    le code est pire qu'aucune phrase : elle fait croire qu'on a vérifié.
    """
    assert A._at_risk([], AUJOURD_HUI)["rule"] == "absent > max(7 j, 3 × intervalle médian)"


def test_la_seule_divergence_connue_est_nommee():
    """
    ⚠️ QUATRE PASSAGES LE MÊME JOUR NE FONT AUCUN INTERVALLE. `_at_risk` suppose alors sept
    jours — donc un seuil de 21 — et peut déclarer la personne perdue. Le backoffice répond
    qu'il n'y a pas de rythme à constater, et se tait.

    Les deux se défendent ; ce qui ne se défend pas, c'est de ne pas savoir que l'écart existe.
    Il est sans conséquence pratique — quelqu'un qui paie quatre fois dans la même journée et ne
    revient jamais n'est pas un habitué perdu — et ce test existe pour qu'on le retrouve le jour
    où l'un des deux chiffres surprendra.
    """
    jours = ["2026-06-01"] * 4
    assert A._at_risk(_rows(jours), AUJOURD_HUI)["count"] == 1
    fidelite = _cote_fidelite(jours)
    assert fidelite["absence_threshold_days"] is None
    assert fidelite["at_risk"] is False
