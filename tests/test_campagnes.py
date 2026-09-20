"""
CE QUE LES CAMPAGNES ONT COÛTÉ.

⚠️ L'ANALYSE D'EFFET (venues avant/après l'envoi) A ÉTÉ RETIRÉE LE 20/09/2026, à la demande de
Quentin. Ses tests sont partis avec elle. Noté ici pour que la disparition se lise comme une
décision et non comme une couverture qui s'effrite.
"""

import pytest

from campagnes import recap_depense


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


