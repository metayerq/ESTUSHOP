"""
LE CALCUL DES POINTS, VÉRIFIÉ CONTRE CELUI DE LA CAISSE.

⚠️ CE FICHIER EST LE SEUL LIEN ENTRE DEUX IMPLÉMENTATIONS DU MÊME BARÈME. Le solde est calculé
en TypeScript au comptoir (Mesa) et en Python ici. Rien dans le langage, les types ou les revues
ne garantit qu'ils tombent d'accord : une divergence produirait deux chiffres différents pour la
même personne, et on ne s'en apercevrait qu'en la regardant dans les yeux.

Les vecteurs sont produits par l'implémentation TypeScript — celle qui tourne en production et
qui fait foi — puis rejoués ici. Le fichier est une COPIE OCTET POUR OCTET de
`mesa/apps/pos/lib/loyalty.vectors.json`, et son empreinte est vérifiée des deux côtés : changer
le barème oblige à toucher les deux dépôts, délibérément, ou l'un des deux vire au rouge.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from points import (  # noqa: E402
    EXPIRY_WARNING_DAYS,
    POINTS_PER_EURO,
    absence_threshold_days,
    expires_at,
    loyalty_state,
    parse_ts,
    to_iso,
)

VECTEURS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors", "loyalty_state.json")

# ⚠️ L'EMPREINTE EST ÉCRITE DES DEUX CÔTÉS. Mesa la vérifie aussi, sur le fichier d'origine.
# Régénérer les vecteurs casse les deux suites : c'est le seul moyen qu'une modification du
# barème ne puisse pas passer d'un seul côté sans que personne ne le remarque.
EMPREINTE = "1500e12303cc79d7a81d37c02dc3038a9d6aec9136335e42d87ed2d55c12a7d2"


def _vecteurs():
    with open(VECTEURS, "rb") as f:
        brut = f.read()
    return brut, json.loads(brut.decode("utf-8"))


def _dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _visites(v):
    return [{"ts": x["ts"], "amount_cents": x["amountCents"]} for x in v]


def _recompenses(r):
    return [{"ts": x["ts"], "points_spent": x["pointsSpent"]} for x in r]


# Ce que le vecteur TypeScript appelle, et le nom qu'on lui donne ici.
CHAMPS = {
    "spentCents": "spent_cents",
    "earnedPoints": "earned_points",
    "spentPoints": "spent_points",
    "expiredPoints": "expired_points",
    "balancePoints": "balance_points",
    "rewardsDue": "rewards_due",
    "pointsToNext": "points_to_next",
    "expiringSoonPoints": "expiring_soon_points",
    "nextExpiry": "next_expiry",
    "visits": "visits",
    "lastSeen": "last_seen",
}


def test_le_fichier_de_vecteurs_est_celui_de_mesa():
    """
    ⚠️ SI CE TEST TOMBE, NE CHANGE PAS L'EMPREINTE : VA VOIR CE QUI A BOUGÉ. Un vecteur modifié
    d'un seul côté, c'est exactement la panne qu'on cherche à rendre impossible.
    """
    brut, _ = _vecteurs()
    assert hashlib.sha256(brut).hexdigest() == EMPREINTE, (
        "les vecteurs ne sont plus ceux de Mesa — recopier "
        "mesa/apps/pos/lib/loyalty.vectors.json et mettre à jour l'empreinte DES DEUX CÔTÉS"
    )


def test_les_constantes_sont_les_memes():
    _, v = _vecteurs()
    assert POINTS_PER_EURO == v["pointsPerEuro"]
    assert EXPIRY_WARNING_DAYS == v["expiryWarningDays"]


def _cas_etats():
    _, v = _vecteurs()
    return [pytest.param(s, id=s["name"]) for s in v["states"]]


@pytest.mark.parametrize("cas", _cas_etats())
def test_le_solde_est_identique_a_celui_de_la_caisse(cas):
    obtenu = loyalty_state(
        _visites(cas["visits"]),
        _recompenses(cas["rewards"]),
        cas["thresholdPoints"],
        _dt(cas["now"]),
        cas["expiryMonths"],
    )
    attendu = cas["expected"]
    ecarts = {
        js: (attendu[js], obtenu[py])
        for js, py in CHAMPS.items()
        if attendu[js] != obtenu[py]
    }
    assert not ecarts, f"{cas['why']}\nDivergence avec Mesa : {ecarts}"


def _cas_absence():
    _, v = _vecteurs()
    return [pytest.param(a, id=a["name"]) for a in v["absence"]]


@pytest.mark.parametrize("cas", _cas_absence())
def test_le_seuil_d_absence_est_identique(cas):
    assert absence_threshold_days(cas["days"]) == cas["expected"], cas["why"]


def _cas_expiration():
    _, v = _vecteurs()
    return [pytest.param(e, id=f"{e['at'][:10]}+{e['months']}m") for e in v["expiry"]]


@pytest.mark.parametrize("cas", _cas_expiration())
def test_l_arithmetique_des_mois_est_identique(cas):
    assert to_iso(expires_at(_dt(cas["at"]), cas["months"])) == cas["expected"]


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Ce que les vecteurs ne couvrent pas : les entrées que la base peut produire et que
# l'implémentation TypeScript ne voit jamais, parce que Mesa lit déjà des lignes normalisées.
# ─────────────────────────────────────────────────────────────────────────────────────────────

def test_postgres_rend_ses_dates_avec_un_decalage_et_non_un_Z():
    """
    ⚠️ SUPABASE NE RENVOIE PAS LE FORMAT DE JAVASCRIPT. Un `timestamptz` sort en
    `2026-09-01T10:00:00+00:00`, pas en `...Z`. Les deux doivent désigner le même instant, sinon
    le backoffice et la caisse ne feraient pas expirer les points le même jour.
    """
    assert parse_ts("2026-09-01T10:00:00+00:00") == parse_ts("2026-09-01T10:00:00Z")
    assert parse_ts("2026-09-01T11:00:00+01:00") == parse_ts("2026-09-01T10:00:00Z")
    assert parse_ts("2026-09-01T10:00:00.123456+00:00") is not None


def test_une_date_illisible_ne_fait_pas_tomber_la_page():
    for brut in (None, "", "   ", "pas une date", 42, [], {}):
        assert parse_ts(brut) is None


def test_un_client_sans_rien_ne_casse_pas():
    etat = loyalty_state([], [], 50, _dt("2026-09-19T12:00:00Z"))
    assert etat["balance_points"] == 0
    assert etat["rewards_due"] == 0
    assert etat["next_expiry"] is None
    assert etat["last_seen"] is None


def test_le_montant_arrive_parfois_en_chaine():
    """
    ⚠️ POSTGREST REND CE QUE LA COLONNE CONTIENT, ET UNE COLONNE `numeric` SORT EN CHAÎNE.
    Une chaîne n'est pas un montant : la compter vaudrait mieux que la refuser, mais la
    convertir en silence masquerait une colonne au mauvais type. On l'ignore, et le test dit
    pourquoi — si un jour `amount` devient `numeric`, ce test est le premier à le signaler.
    """
    etat = loyalty_state(
        [{"ts": "2026-09-01T10:00:00Z", "amount_cents": "5000"}], [], 50, _dt("2026-09-19T12:00:00Z")
    )
    assert etat["balance_points"] == 0


def test_un_booleen_n_est_pas_un_montant():
    """`True` vaut 1 en Python — sans garde, une colonne booléenne offrirait un centime."""
    etat = loyalty_state(
        [{"ts": "2026-09-01T10:00:00Z", "amount_cents": True}], [], 50, _dt("2026-09-19T12:00:00Z")
    )
    assert etat["spent_cents"] == 0


def test_l_horloge_locale_n_entre_jamais_dans_le_calcul():
    """
    ⚠️ `now` EST UN PARAMÈTRE. Si un jour quelqu'un remplace ça par `datetime.now()`, ce test
    ne le verra pas — mais la signature, si : elle exige l'instant, elle ne le devine pas.
    """
    tot = loyalty_state(
        [{"ts": "2025-10-01T10:00:00Z", "amount_cents": 6000}], [], 50, _dt("2026-09-30T12:00:00Z")
    )
    tard = loyalty_state(
        [{"ts": "2025-10-01T10:00:00Z", "amount_cents": 6000}], [], 50, _dt("2026-10-02T12:00:00Z")
    )
    assert tot["balance_points"] == 60
    assert tard["balance_points"] == 0
    assert tard["expired_points"] == 60
