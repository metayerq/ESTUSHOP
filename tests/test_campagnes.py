"""
MESURER L'EFFET D'UNE CAMPAGNE — SANS PRÉTENDRE LE DÉMONTRER.

⚠️ CE MODULE PEUT MENTIR DE DEUX FAÇONS, ET AUCUNE NE LÈVE. Il peut compter deux fois quelqu'un
qui a deux cartes, doublant l'efficacité apparente. Et il peut comparer une fenêtre incomplète à
une fenêtre pleine, faisant passer une campagne d'hier pour un échec. Les deux se lisent comme
des chiffres parfaitement normaux.
"""

from datetime import datetime, timedelta, timezone

import pytest

from campagnes import (
    FENETRE_JOURS,
    complete,
    effet_campagne,
    recap_depense,
    visites_par_telephone,
)

ENVOI = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
TEL = "+351912345678"
AUTRE = "+351922222222"


def v(fp, jours, cents=500):
    """Un passage, décalé de `jours` par rapport à l'envoi."""
    return {"fp": fp, "ts": (ENVOI + timedelta(days=jours)).isoformat(), "amount": cents}


CAMPAGNE = {"slug": "abc", "sent_at": ENVOI.isoformat(), "cout_centimes": 200}


def _effet(visites, liens, destinataires=(TEL,)):
    return effet_campagne(CAMPAGNE, list(destinataires), visites_par_telephone(visites, liens))


# ── Regrouper par personne ───────────────────────────────────────────────────────────────────

def test_deux_cartes_du_meme_client_ne_font_quune_personne():
    """
    ⚠️ COMPTER PAR CARTE DOUBLERAIT L'EFFICACITÉ APPARENTE. Quelqu'un qui paie tantôt avec sa
    carte physique, tantôt avec son Apple Pay, compterait pour deux clients revenus.
    """
    liens = [{"fp": "aaaa", "phone": TEL}, {"fp": "bbbb", "phone": TEL}]
    e = _effet([v("aaaa", 1), v("bbbb", 2)], liens)
    assert e["venus_apres"] == 1
    assert e["apres"]["visites"] == 2
    assert e["apres"]["jours"] == 2


def test_deux_tickets_le_meme_jour_sont_une_venue():
    """Le café et le gâteau payés séparément le même matin ne font pas deux visites."""
    liens = [{"fp": "aaaa", "phone": TEL}]
    e = _effet([v("aaaa", 1), v("aaaa", 1)], liens)
    assert e["apres"]["visites"] == 2
    assert e["apres"]["jours"] == 1


def test_une_carte_sans_numero_est_ignoree():
    e = _effet([v("zzzz", 1)], [{"fp": "aaaa", "phone": TEL}])
    assert e["apres"]["visites"] == 0


# ── La comparaison avant / après ─────────────────────────────────────────────────────────────

def test_la_comparaison_porte_sur_les_memes_personnes():
    """
    ⚠️ « 30 % SONT VENUS DANS LA SEMAINE » NE PROUVE RIEN : ce sont des habitués. Le seul
    chiffre honnête compare les mêmes gens, la même durée, juste avant l'envoi.
    """
    liens = [{"fp": "aaaa", "phone": TEL}]
    e = _effet([v("aaaa", -3), v("aaaa", 2), v("aaaa", 4)], liens)
    assert e["avant"]["visites"] == 1
    assert e["apres"]["visites"] == 2
    assert e["venus_avant"] == 1
    assert e["venus_apres"] == 1


def test_ceux_quon_reveille_sont_comptes_a_part():
    """
    ⚠️ LE SEUL GROUPE OÙ L'EFFET D'UN MESSAGE EST PLAUSIBLE. Un habitué qui vient chaque semaine
    serait venu sans nous ; celui qui n'était pas venu depuis et qui revient, peut-être pas.
    """
    liens = [{"fp": "aaaa", "phone": TEL}, {"fp": "bbbb", "phone": AUTRE}]
    # TEL venait déjà ; AUTRE était absent et revient.
    e = _effet([v("aaaa", -2), v("aaaa", 2), v("bbbb", 3)], liens, (TEL, AUTRE))
    assert e["venus_avant"] == 1
    assert e["venus_apres"] == 2
    assert e["reveilles"] == 1


def test_linstant_de_lenvoi_appartient_a_lapres():
    """Quelqu'un qui paie dans la minute qui suit le SMS est un « après », pas un « avant »."""
    liens = [{"fp": "aaaa", "phone": TEL}]
    e = _effet([{"fp": "aaaa", "ts": ENVOI.isoformat(), "amount": 500}], liens)
    assert e["apres"]["visites"] == 1
    assert e["avant"]["visites"] == 0


def test_la_fenetre_est_symetrique():
    """
    ⚠️ SEPT JOURS EXACTEMENT DE CHAQUE CÔTÉ. Le café ferme mardi et mercredi : une fenêtre plus
    courte comparerait un week-end à deux jours de fermeture, et la campagne aurait l'air d'un
    triomphe ou d'un échec selon le jour du clic.
    """
    liens = [{"fp": "aaaa", "phone": TEL}]
    # Aux deux bornes exactes : -7 est dedans (borne basse incluse), +7 est dehors.
    e = _effet([v("aaaa", -FENETRE_JOURS), v("aaaa", FENETRE_JOURS)], liens)
    assert e["avant"]["visites"] == 1
    assert e["apres"]["visites"] == 0


def test_le_delta_en_euros_est_la_difference():
    liens = [{"fp": "aaaa", "phone": TEL}]
    e = _effet([v("aaaa", -1, 300), v("aaaa", 1, 1000)], liens)
    assert e["delta_cents"] == 700


def test_une_campagne_sans_destinataire_ne_rend_rien():
    assert _effet([], [], ()) is None


# ── La fenêtre incomplète ────────────────────────────────────────────────────────────────────

def test_une_campagne_dhier_est_signalee_incomplete():
    """
    ⚠️ SANS CE DRAPEAU, TOUTE CAMPAGNE RÉCENTE PARAÎT RATÉE. On la lit le lendemain, on voit
    deux venues au lieu de douze, et on conclut sur un message qui n'a pas eu le temps d'agir.
    """
    e = _effet([], [{"fp": "aaaa", "phone": TEL}])
    c = complete(e, ENVOI + timedelta(days=1))
    assert c["complete"] is False
    assert c["jours_restants"] >= 6


def test_une_campagne_ancienne_est_complete():
    e = _effet([], [{"fp": "aaaa", "phone": TEL}])
    assert complete(e, ENVOI + timedelta(days=FENETRE_JOURS))["complete"] is True


# ── Le récapitulatif de dépense ──────────────────────────────────────────────────────────────

def _c(mois, jour, recipients, segments, cout):
    return {"sent_at": f"2026-{mois:02d}-{jour:02d}T10:00:00+00:00", "recipients": recipients,
            "segments": segments, "cout_centimes": cout}


def test_la_depense_est_groupee_par_mois_du_plus_recent():
    r = recap_depense([_c(9, 3, 10, 10, 50), _c(9, 20, 20, 40, 200), _c(8, 15, 5, 5, 25)])
    assert [m["mois"] for m in r["mois"]] == ["2026-09", "2026-08"]
    assert r["mois"][0]["campagnes"] == 2
    assert r["mois"][0]["cents"] == 250
    assert r["total_cents"] == 275


def test_le_cout_par_message_revele_les_segments():
    """
    ⚠️ C'EST LE CHIFFRE QUI SE COMPARE D'UNE CAMPAGNE À L'AUTRE. Un texte qui passe à deux
    segments double cette ligne sans que le nombre de destinataires bouge — c'est la seule
    façon de voir qu'un « ã » oublié coûte de l'argent.
    """
    r = recap_depense([_c(9, 3, 10, 20, 100)])
    assert r["cents_par_message"] == 10.0


def test_un_recap_vide_ne_divise_pas_par_zero():
    r = recap_depense([])
    assert r["total_cents"] == 0 and r["cents_par_message"] == 0


def test_une_date_illisible_nest_pas_comptee():
    r = recap_depense([{"sent_at": None, "recipients": 9, "cout_centimes": 99}])
    assert r["total_cents"] == 0


def test_une_horloge_illisible_ne_dit_pas_que_cest_fini():
    """⚠️ « Je ne sais pas » et « c'est fini » mènent à deux lectures opposées du même écran."""
    e = _effet([], [{"fp": "aaaa", "phone": TEL}])
    assert complete(e, None)["complete"] is False
