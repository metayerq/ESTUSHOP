"""
Couverts MESURÉS contre couverts ESTIMÉS.

Le POS demande le nombre de personnes à chaque ouverture de table et l'écrit sur la note du
document (`pax:N` — contrat écrit dans `apps/pos/lib/covers.ts`). Le dashboard, lui, l'estimait
en comptant les boissons : une personne = une boisson, plancher 1, plafond 8.

⚠️ LA MESURE NE COUVRIRA JAMAIS TOUT. Le comptoir n'ouvre pas de table et la caisse principale
n'est pas ce POS : du 15 au 18 août, 10 documents sur 95 venaient du POS. Le total mêle donc les
deux — et c'est précisément pour ça que la part mesurée doit être annonçable.
"""
import sys
sys.path.insert(0, ".")

import app as A
import app  # les tests de fenêtres appellent la vraie fonction, pas un alias


CAFE = "Bica"
LIVRE = "Livro"
CATALOGUE = {CAFE: {"category_id": next(iter(A.DRINK_CAT_IDS))}, LIVRE: {"category_id": 999}}


def _doc(items, notes=None, refund=False):
    return {"items": [{"title": t, "qty": q} for t, q in items],
            "notes": notes, "_refund": refund, "local_time": "2026-08-18 10:00:00"}


# ── Lire la note ────────────────────────────────────────────────────────────

def test_lit_le_compte_reel_de_la_note():
    assert A._covers_from_notes(_doc([], "Mesa 3 · pax:4")) == 4


def test_rend_none_et_jamais_zero():
    """
    ⚠️ Zéro couvert se propagerait comme « une table sans personne » et ferait chuter la moyenne,
    au lieu de laisser l'estimation faire son travail.
    """
    assert A._covers_from_notes(_doc([], None)) is None
    assert A._covers_from_notes(_doc([], "Mesa 3")) is None
    assert A._covers_from_notes(_doc([], "pax:0")) is None


def test_ne_confond_pas_un_mot_qui_ressemble():
    assert A._covers_from_notes(_doc([], "relatorio max:4")) is None


# ── Préférer la mesure ──────────────────────────────────────────────────────

def test_la_mesure_l_emporte_sur_l_estimation():
    """Une table de 4 avec un seul café compterait 1 personne à l'estimation."""
    r = A._summarize_docs_items([_doc([(CAFE, 1)], "Mesa 3 · pax:4")], CATALOGUE)
    assert r["covers"] == 4
    assert r["covers_measured"] == 1
    assert r["covers_estimated"] == 0


def test_l_estimation_reste_pour_les_documents_sans_note():
    r = A._summarize_docs_items([_doc([(CAFE, 2)])], CATALOGUE)
    assert r["covers"] == 2
    assert r["covers_measured"] == 0
    assert r["covers_estimated"] == 1


def test_les_deux_se_mêlent_et_se_comptent():
    """⚠️ C'est le cas RÉEL : une minorité de documents vient du POS."""
    r = A._summarize_docs_items(
        [_doc([(CAFE, 1)], "Mesa 3 · pax:4"), _doc([(CAFE, 2)]), _doc([(LIVRE, 1)])],
        CATALOGUE)
    # 4 mesurés + 2 estimés + 1 (plancher : un livre sans boisson reste une personne)
    assert r["covers"] == 7
    assert r["covers_measured"] == 1
    assert r["covers_estimated"] == 2


def test_ni_plancher_ni_plafond_sur_une_mesure():
    """
    ⚠️ Le plafond à 8 existe pour rattraper une ESTIMATION absurde — 55 boissons ne sont pas
    55 personnes assises. Une table de 12 saisie par un humain, elle, est une table de 12 :
    l'écrêter falsifierait un comptage au motif d'une règle faite pour une devinette.
    """
    r = A._summarize_docs_items([_doc([(CAFE, 30)], "Mesa 3 · pax:12")], CATALOGUE)
    assert r["covers"] == 12
    assert r["covers_capped"] == 0


def test_le_plafond_s_applique_encore_aux_estimations():
    r = A._summarize_docs_items([_doc([(CAFE, 30)])], CATALOGUE)
    assert r["covers"] == A.COVERS_CAP
    assert r["covers_capped"] == 1


def test_un_avoir_n_apporte_aucun_couvert():
    """Une annulation n'est pas une visite — mesurée ou non."""
    r = A._summarize_docs_items([_doc([(CAFE, 1)], "Mesa 3 · pax:4", refund=True)], CATALOGUE)
    assert r["covers"] == 0
    assert r["covers_measured"] == 0


# ── La part mesurée, annonçable ─────────────────────────────────────────────
#
# ⚠️ CES TESTS LISENT LA VRAIE FONCTION. Une première version recopiait le calcul dans le test :
# elle serait restée verte si `/api/tx/windows` avait cessé de le faire. Un test qui ne peut pas
# tomber ne protège rien.

import datetime as _dt


def _jour(day, mesures, estimes):
    return {"day": day, "nb": 10, "ca_ttc": 100.0, "multi_count": 0,
            "covers_measured": mesures, "covers_estimated": estimes}


def _fenetres(rows, depuis, aujourdhui):
    return app._transactions_payload(rows, depuis, aujourdhui)["windows"]


def _jours_ouverts(depuis, n):
    """Suite de jours civils — les jours fermés sont écartés en amont par le cache."""
    return [(depuis + _dt.timedelta(i)).isoformat() for i in range(n)]


def test_la_part_mesuree_sort_de_l_api():
    """
    ⚠️ CE QUI PERMET DE NE PAS MENTIR. Un total à 90 % estimé se lit comme un comptage tant que
    personne ne dit la proportion — le malentendu exact que la remontée du POS devait dissiper.
    """
    depuis = _dt.date(2026, 7, 1)
    jours = _jours_ouverts(depuis, 10)
    rows = [_jour(j, 1, 9) for j in jours]
    w = _fenetres(rows, depuis, _dt.date(2026, 7, 20))
    assert w, "aucune fenêtre produite"
    assert w[0]["covers_measured_pct"] == 10.0


def test_la_part_est_none_tant_que_rien_n_est_classe():
    """« 0 % mesuré » affirmerait qu'on a regardé. On n'a rien regardé."""
    depuis = _dt.date(2026, 7, 1)
    rows = [_jour(j, 0, 0) for j in _jours_ouverts(depuis, 10)]
    w = _fenetres(rows, depuis, _dt.date(2026, 7, 20))
    assert w[0]["covers_measured_pct"] is None


def test_tout_mesure_donne_cent_pour_cent():
    depuis = _dt.date(2026, 7, 1)
    rows = [_jour(j, 4, 0) for j in _jours_ouverts(depuis, 10)]
    w = _fenetres(rows, depuis, _dt.date(2026, 7, 20))
    assert w[0]["covers_measured_pct"] == 100.0
