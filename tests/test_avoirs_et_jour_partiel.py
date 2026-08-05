"""
Deux derniers défauts de l'audit : les avoirs dans la ventilation TVA, et le jour partiel
dans la moyenne par jour de semaine.

`_negate_refund` négativait le CA, les lignes d'articles et les paiements — mais PAS le bloc
`taxes`. Vendus le renvoie positif sur un avoir exactement comme sur une vente ; vérifié sur
l'avoir 362109040 du café : {'total': '10.50', 'base': '9.29', 'amount': '1.21', 'rate': 13}.
`tva_breakdown` les additionnait donc au lieu de les soustraire.

Ce champ n'est plus rendu par le dashboard, mais il reste servi par l'API — et c'est celui
qu'on relit pour une déclaration.
"""
import sys
from datetime import date
sys.path.insert(0, ".")

import app
import vendus


def _doc(gross, net, rate=13, refund=False):
    d = {
        "type": "NC" if refund else "FT",
        "amount_gross": gross, "amount_net": net,
        "taxes": [{"total": str(gross), "base": str(net),
                   "amount": str(round(gross - net, 2)), "rate": rate}],
        "items": [], "payments": [],
    }
    return vendus._negate_refund(d) if refund else d


# ── 1 · Les avoirs se soustraient de la ventilation TVA ──────────────────────

def test_un_avoir_annule_la_vente_dans_la_ventilation_tva():
    """
    Une vente de 100 € TTC et son avoir le même jour : CA nul, TVA nulle. Avant, la
    ventilation affichait 200 € de total et 23 € de TVA collectée — le double, pas zéro.
    """
    docs = [_doc(100.0, 88.50), _doc(100.0, 88.50, refund=True)]
    out = vendus.tva_breakdown(docs)
    t = out["totals"] if isinstance(out, dict) and "totals" in out else out[1]
    assert t["total"] == 0.0, t
    assert t["tva"] == 0.0, t
    assert t["base"] == 0.0, t


def test_le_bloc_taxes_d_un_avoir_est_bien_negative():
    """Au niveau du document : les trois montants passent en négatif, comme le CA."""
    d = _doc(10.50, 9.29, refund=True)
    t = d["taxes"][0]
    assert (t["total"], t["base"], t["amount"]) == (-10.50, -9.29, -1.21)


def test_une_vente_seule_reste_intacte():
    """Garde-fou de non-régression : rien ne doit bouger sur une vente ordinaire."""
    d = _doc(13.00, 11.50)
    # Comparé en valeur : Vendus renvoie des chaînes, et leur mise en forme exacte n'est pas
    # le sujet — ce qui compte est que le signe et le montant soient inchangés.
    assert float(d["taxes"][0]["total"]) == 13.00
    out = vendus.tva_breakdown([d])
    t = out["totals"] if isinstance(out, dict) and "totals" in out else out[1]
    assert t["total"] == 13.00 and t["tva"] == 1.50


# ── 2 · La moyenne par jour de semaine ignore la journée en cours ────────────

def _rows(day_ca):
    return [{"day": d, "ca_ttc": ca, "nb": nb} for d, (ca, nb) in day_ca.items()]


def test_la_journee_en_cours_ne_tire_pas_la_moyenne_du_jour_de_semaine():
    """
    Deux lundis pleins à 400 €, plus le lundi en cours à 80 €. La moyenne du lundi doit rester
    400 € — sinon elle affiche 293 € le matin et remonte toute seule dans la journée.
    """
    rows = _rows({"2026-07-06": (400.0, 40), "2026-07-13": (400.0, 40),
                  "2026-07-20": (80.0, 8)})
    out = app._weekday_averages(rows, today_iso="2026-07-20")
    lundi = next(x for x in out if x["day"] == "Monday")
    assert lundi["avg_ca"] == 400.0, lundi
    assert lundi["n_days"] == 2, "la journée en cours ne compte pas comme un lundi observé"


def test_un_jour_sans_ticket_n_est_pas_une_journee_a_zero():
    """Absent des données ≠ nul. L'inclure ferait chuter la moyenne d'un jour de fermeture."""
    rows = _rows({"2026-07-06": (400.0, 40), "2026-07-13": (0.0, 0)})
    lundi = next(x for x in app._weekday_averages(rows, "2026-07-20") if x["day"] == "Monday")
    assert lundi["n_days"] == 1 and lundi["avg_ca"] == 400.0


def test_sans_aucun_jour_plein_il_n_y_a_pas_de_classement():
    """`None`, pas une liste vide : l'écran doit pouvoir distinguer « rien » de « zéro »."""
    assert app._weekday_averages([], "2026-07-20") is None
    assert app._weekday_averages(_rows({"2026-07-20": (80.0, 8)}), "2026-07-20") is None


def test_le_classement_est_bien_ordonne_par_ca_moyen():
    rows = _rows({"2026-07-06": (200.0, 20), "2026-07-11": (500.0, 50)})
    out = app._weekday_averages(rows, "2026-07-20")
    assert [x["day"] for x in out] == ["Saturday", "Monday"]
