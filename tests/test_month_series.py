"""
La série du mois — et l'indépendance qu'elle revendique.

Aucun test n'existait dans ce dépôt. Celui-ci part du défaut trouvé en portant la même logique
dans Mesa : le bloc « insights visuels (indépendants du preset sélectionné) » recevait un
`fallback_rate` dérivé de l'économie de la PÉRIODE SÉLECTIONNÉE. Changer le filtre au-dessus
déplaçait donc le cumul et la projection du mois — des chiffres qui ne parlent que du mois.

⚠️ CE QUE CE FICHIER COUVRE, ET CE QU'IL NE COUVRE PAS.
`_month_series` a le droit d'utiliser le taux qu'on lui donne : c'est son contrat. Le défaut
était dans le CHOIX de ce taux, en amont. C'est donc `_month_fallback_rate` qui est testé ici.
Que le site d'appel passe bien cette fonction-là est vérifié en lisant app.py, pas par un test :
l'exercer demanderait la route entière et donc la base. Si quelqu'un y recâble un taux de
période, ces tests resteront verts.
"""
import inspect
import sys
from datetime import date
sys.path.insert(0, ".")

import app
from config import MARGE_BP_GLOBALE


def _rows(day_ca, covered=0.0, cogs=0.0):
    """Résumés journaliers minimaux : {jour: (ca_ht, nb)}."""
    return [
        {"day": d, "ca_ht": ca, "ca_ttc": ca * 1.13, "nb": nb,
         "covered_ht": covered, "cogs_ht": cogs, "products": {}}
        for d, (ca, nb) in day_ca.items()
    ]


def test_le_taux_du_mois_ne_voit_que_le_mois():
    """
    L'invariant qui manquait : le taux ne se calcule qu'à partir des lignes du mois.

    Il est vérifié ici par la SIGNATURE — la fonction n'a aucun moyen d'accéder à la période
    sélectionnée, même par accident. Un test de valeurs se contenterait de décrire le calcul ;
    celui-ci ferme la porte par laquelle le bug était entré.
    """
    params = list(inspect.signature(app._month_fallback_rate).parameters)
    assert params == ["rows_month"], (
        f"_month_fallback_rate prend {params} — tout paramètre supplémentaire rouvre la porte "
        "à un taux venu d'ailleurs que du mois"
    )


def test_le_taux_est_mesure_quand_les_lignes_sont_chiffrees():
    """200 € couverts, 60 € de COGS → 70 % de marge mesurée."""
    rows = _rows({"2026-07-02": (200.0, 20)}, covered=200.0, cogs=60.0)
    assert app._month_fallback_rate(rows) == 0.70


def test_sans_couverture_on_retombe_sur_l_hypothese_du_bp_pas_sur_zero():
    """
    Aucune ligne chiffrée : on ne sait pas, on assume. Un 0 se lirait « marge nulle »,
    c'est-à-dire une information, alors qu'il n'y en a aucune.
    """
    rows = _rows({"2026-07-02": (200.0, 20)})   # covered_ht = 0
    assert app._month_fallback_rate(rows) == MARGE_BP_GLOBALE
    assert app._month_fallback_rate([]) == MARGE_BP_GLOBALE


def test_les_jours_fermes_ne_comptent_pas_comme_des_jours_a_zero():
    """Un jour fermé n'a pas d'EBITDA : `None`, pas 0. Un 0 se lirait « a couvert ses charges »."""
    rows = _rows({"2026-07-02": (200.0, 20)})
    s = app._month_series(rows, cout_jour=100.0, fallback_rate=0.70, today_real=date(2026, 7, 8))
    fermes = [d for d in s["days"] if not d["open"]]
    assert fermes, "juillet 2026 contient des mardis/mercredis fermés"
    assert all(d["ebitda"] is None for d in fermes)


def test_le_jour_de_bascule_n_est_nomme_que_s_il_y_a_eu_bascule():
    """`cross_date` : un mois ouvert en bénéfice n'a rien franchi."""
    rows = _rows({"2026-07-02": (5000.0, 200)})
    s = app._month_series(rows, cout_jour=100.0, fallback_rate=0.70, today_real=date(2026, 7, 2))
    assert s["cum_now"] > 0
    assert s["cross_date"] is None
