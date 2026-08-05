"""
Tickets par jour ouvré — et le jour partiel qu'il ne faut compter d'aucun côté.

Le dashboard affichait déjà « tickets / open day », mais divisait un total INCLUANT la journée
en cours par un nombre de jours ouvrés l'incluant aussi. Consulté un vendredi matin sur « cette
semaine », le dénominateur comptait une journée entière face à trois tickets : la moyenne
chutait d'environ un tiers puis remontait toute seule au fil des heures. Un chiffre qui bouge
sans que rien ne se passe n'est pas une moyenne.

Le café ouvre lundi, jeudi, vendredi, samedi, dimanche (config.OPEN_WEEKDAYS).
"""
import sys
from datetime import date
sys.path.insert(0, ".")

import app


def _rows(day_nb):
    return [{"day": d, "nb": n} for d, n in day_nb.items()]


def test_le_jour_en_cours_ne_compte_ni_au_numerateur_ni_au_denominateur():
    """
    Vendredi matin, 3 tickets au compteur. Les jours pleins sont lundi (40) et jeudi (30) —
    mardi et mercredi sont fermés. La moyenne doit être 35, pas (40+30+3)/3 = 24,3.
    """
    rows = _rows({"2026-08-03": 40, "2026-08-06": 30, "2026-08-07": 3})
    out = app._tx_per_open_day(rows, date(2026, 8, 3), date(2026, 8, 7), date(2026, 8, 7))
    assert out["tx_per_open_day"] == 35.0, out
    assert out["tx_basis_days"] == 2


def test_les_jours_fermes_ne_diluent_pas_la_moyenne():
    """Mardi et mercredi sont fermés : ils ne doivent jamais entrer au dénominateur."""
    rows = _rows({"2026-08-03": 40})                      # lundi seul
    out = app._tx_per_open_day(rows, date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 6))
    assert out["tx_basis_days"] == 1, "mar 4 et mer 5 sont fermés"
    assert out["tx_per_open_day"] == 40.0


def test_une_periode_reduite_au_jour_courant_ne_rend_pas_zero():
    """
    Preset « Today » : il n'existe aucun jour plein. La réponse est « on ne sait pas » —
    un 0 se lirait « aucune transaction en moyenne », c'est-à-dire une information.
    """
    out = app._tx_per_open_day(_rows({"2026-08-07": 3}),
                               date(2026, 8, 7), date(2026, 8, 7), date(2026, 8, 7))
    assert out["tx_per_open_day"] is None
    assert out["tx_basis_reason"]


def test_une_periode_entierement_fermee_ne_rend_pas_zero_non_plus():
    """Mardi → mercredi : aucun jour ouvré. Pas de moyenne, et la raison est dite."""
    out = app._tx_per_open_day([], date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6))
    assert out["tx_per_open_day"] is None
    assert "aucun jour ouvré" in out["tx_basis_reason"]


def test_un_jour_travaille_hors_calendrier_entre_au_denominateur():
    """
    Un mardi d'événement privé porte des tickets. Le compter au numérateur sans le compter
    au dénominateur gonflerait la moyenne d'un jour de travail fantôme.
    """
    rows = _rows({"2026-08-03": 40, "2026-08-04": 20})     # lundi + mardi (fermé au calendrier)
    out = app._tx_per_open_day(rows, date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 6))
    assert out["tx_basis_days"] == 2, "le mardi travaillé doit compter"
    assert out["tx_per_open_day"] == 30.0


def test_un_jour_ferme_sans_ticket_reste_hors_du_denominateur():
    """Contrepartie du test précédent : `nb` à zéro n'ouvre pas la journée."""
    rows = _rows({"2026-08-03": 40, "2026-08-04": 0})
    out = app._tx_per_open_day(rows, date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 6))
    assert out["tx_basis_days"] == 1
    assert out["tx_per_open_day"] == 40.0
