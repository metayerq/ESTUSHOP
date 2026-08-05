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


# ── La projection ne doit pas dériver au fil de la journée ────────────────────

def test_la_projection_ne_bouge_pas_quand_la_journee_en_cours_avance():
    """
    Le défaut : `avg7` moyennait les 7 derniers jours ouvrés EN Y INCLUANT aujourd'hui, dont
    l'EBITDA vaut une marge partielle moins les charges d'une journée entière. À 10 h le jour
    pesait fortement négatif, la projection chutait, puis remontait toute seule au fil des
    heures — une prévision qui bouge sans qu'aucun fait nouveau ne survienne.

    Ici le même mois est calculé deux fois : la journée en cours à 40 € puis à 400 €. La
    projection doit être IDENTIQUE — seul le constat (`cum_now`) a le droit de changer.
    """
    base = {"2026-07-02": (400.0, 40), "2026-07-03": (400.0, 40), "2026-07-06": (400.0, 40)}
    today = date(2026, 7, 9)          # jeudi, jour ouvré

    tot = _rows({**base, "2026-07-09": (40.0, 4)})
    fin = _rows({**base, "2026-07-09": (400.0, 40)})
    a = app._month_series(tot, cout_jour=100.0, fallback_rate=0.70, today_real=today)
    b = app._month_series(fin, cout_jour=100.0, fallback_rate=0.70, today_real=today)

    assert a["proj_end"] == b["proj_end"], (
        f"la projection dérive avec l'avancement du jour : {a['proj_end']} vs {b['proj_end']}")
    assert a["cum_now"] != b["cum_now"], "le cumul, lui, DOIT suivre la journée réelle"


def test_la_journee_en_cours_est_projetee_et_non_prise_pour_reference():
    """
    Tous les jours ouvrés écoulés sont renseignés à 400 € de CA — sans quoi les jours ouverts
    au calendrier mais absents des données compteraient à −100 € de charges chacun et
    fausseraient l'attendu (c'est ce qui a piégé la première version de ce test).

    Marge 70 %, charges 100 € → 180 € d'EBITDA par jour plein. Aujourd'hui jeudi 9 juillet
    n'est pas fini : il doit compter parmi les jours RESTANTS, pas parmi les références.
    """
    rows = _rows({"2026-07-02": (400.0, 40), "2026-07-03": (400.0, 40),
                  "2026-07-04": (400.0, 40), "2026-07-05": (400.0, 40),
                  "2026-07-06": (400.0, 40), "2026-07-09": (40.0, 4)})
    s = app._month_series(rows, cout_jour=100.0, fallback_rate=0.70, today_real=date(2026, 7, 9))
    from config import count_open_days_raw
    restants = count_open_days_raw(date(2026, 7, 9), date(2026, 7, 31))
    assert s["proj_end"] == round(5 * 180.0 + 180.0 * restants, 2), s["proj_end"]


def test_sans_aucun_jour_plein_il_n_y_a_pas_de_projection():
    """
    Premier jour du mois, encore en cours : rien pour asseoir une moyenne. `None`, pas 0 —
    un 0 se lirait « le mois finira à l'équilibre », c'est-à-dire une prévision.
    """
    s = app._month_series(_rows({"2026-07-01": (40.0, 4)}), cout_jour=100.0,
                          fallback_rate=0.70, today_real=date(2026, 7, 1))
    assert s["proj_end"] is None
