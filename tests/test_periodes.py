"""
LES PÉRIODES D'UN CAFÉ OUVERT CINQ JOURS SUR SEPT.

⚠️ « HIER » N'EST PAS UN JOUR D'OUVERTURE. Le café ouvre lundi, jeudi, vendredi, samedi,
dimanche. Chaque jeudi, « hier » tombait sur un mercredi fermé : la page s'affichait vide, avec
des zéros, et rien ne disait que le café n'avait pas ouvert. Un écran vide se lit « on n'a rien
vendu », jamais « on n'était pas là ».
"""

from datetime import date, timedelta

import pytest

import periodes as P

# Septembre 2026 : le 21 est un lundi, le 22 mardi (fermé), le 23 mercredi (fermé),
# le 24 jeudi, le 25 vendredi, le 26 samedi, le 27 dimanche.
LUNDI, MARDI, MERCREDI, JEUDI = (date(2026, 9, d) for d in (21, 22, 23, 24))


def test_le_cafe_ferme_bien_mardi_et_mercredi():
    """Le socle de tout ce qui suit — s'il change, tout le reste doit être relu."""
    assert P.est_ouvert(LUNDI) and P.est_ouvert(JEUDI)
    assert not P.est_ouvert(MARDI) and not P.est_ouvert(MERCREDI)


# ── « Hier » ─────────────────────────────────────────────────────────────────────────────────

def test_le_jeudi_hier_est_lundi_pas_mercredi():
    """
    ⚠️ C'EST LE BOGUE, ET IL REVENAIT CHAQUE JEUDI. « Yesterday » ouvrait sur un mercredi fermé :
    zéro euro, zéro ticket, et aucune phrase pour dire que le café n'avait pas ouvert.
    """
    assert P.dernier_jour_ouvert(JEUDI) == LUNDI


def test_le_lundi_hier_est_dimanche():
    assert P.dernier_jour_ouvert(LUNDI) == date(2026, 9, 20)


def test_sans_jour_ouvert_en_amont_on_ne_devine_pas():
    """⚠️ MIEUX VAUT `None` QU'UNE DATE INVENTÉE : l'appelant doit pouvoir dire « pas encore »."""
    assert P.dernier_jour_ouvert(date(2026, 5, 27), limite=3) is None


# ── La fenêtre de cinq services ──────────────────────────────────────────────────────────────

def test_cinq_services_enjambent_les_jours_fermes():
    """
    ⚠️ « SEPT DERNIERS JOURS » N'EST PAS UNE SEMAINE DE SERVICE. Selon où tombe la fenêtre, elle
    contient quatre ou cinq ouvertures — et le total change sans que rien n'ait bougé au café.
    """
    j = P.derniers_jours_ouverts(JEUDI, 5)
    assert [d.day for d in j] == [18, 19, 20, 21, 24]
    assert all(P.est_ouvert(d) for d in j)


def test_la_fenetre_est_rendue_du_plus_ancien_au_plus_recent():
    j = P.derniers_jours_ouverts(JEUDI, 3)
    assert j == sorted(j)


def test_la_borne_haute_est_incluse():
    assert P.derniers_jours_ouverts(JEUDI, 1) == [JEUDI]


def test_un_jour_ferme_nest_jamais_la_borne_haute():
    """Demander « les 2 derniers services » un mercredi rend lundi et dimanche."""
    assert P.derniers_jours_ouverts(MERCREDI, 2) == [date(2026, 9, 20), LUNDI]


def test_on_nen_invente_pas_quand_lhistorique_manque():
    assert len(P.derniers_jours_ouverts(date(2026, 5, 28), 10, limite=5)) < 10


# ── La fenêtre de comparaison ────────────────────────────────────────────────────────────────

def test_la_reference_a_le_meme_nombre_de_services():
    """
    ⚠️ RECULER DE SEPT JOURS N'ÉQUILIBRE RIEN QUAND LE CALENDRIER BOUGE. Un férié, une fermeture
    exceptionnelle, et l'on oppose quatre services à cinq — puis on conclut sur l'écart.
    """
    debut, fin, n = P.fenetre_precedente(LUNDI, JEUDI)
    assert n == 2, "lundi + jeudi = deux services"
    from config import count_open_days_raw
    assert count_open_days_raw(debut, fin) == 2


def test_la_reference_sarrete_la_veille_de_la_periode():
    debut, fin, _ = P.fenetre_precedente(LUNDI, JEUDI)
    assert fin < LUNDI


def test_sans_assez_dhistorique_il_ny_a_pas_de_reference():
    """
    ⚠️ UNE RÉFÉRENCE AMPUTÉE FERAIT CONCLURE À UNE PROGRESSION QUI N'EST QU'UN MANQUE DE PASSÉ.
    Mieux vaut dire qu'on ne compare pas.
    """
    debut, fin, n = P.fenetre_precedente(date(2026, 5, 27), date(2026, 5, 31), limite=2)
    assert debut is None and fin is None


def test_une_periode_sans_aucun_service_na_pas_de_reference():
    debut, fin, n = P.fenetre_precedente(MARDI, MERCREDI)
    assert debut is None and n == 0


# ── Ce que la période annonce ────────────────────────────────────────────────────────────────

def test_la_periode_dit_ses_services_et_ses_jours():
    """
    ⚠️ « LA SEMAINE DERNIÈRE » EST AMBIGUË : sept jours calendaires, ou cinq de service ? Les
    deux réponses existent et donnent des chiffres différents. Tant que l'écran ne dit pas
    laquelle il applique, on lit un total sans savoir sur quoi il porte.
    """
    d = P.decrire(date(2026, 9, 14), date(2026, 9, 20), JEUDI)
    assert d["jours_calendaires"] == 7
    assert d["jours_ouverts"] == 5
    assert d["en_cours"] is False


def test_une_periode_qui_contient_aujourdhui_est_dite_en_cours():
    """
    ⚠️ UNE PÉRIODE QUI N'EST PAS FINIE COMPARÉE À UNE PÉRIODE CLOSE fait lire un recul tous les
    matins et une reprise tous les soirs — un cycle fabriqué par l'heure à laquelle on regarde.
    """
    assert P.decrire(LUNDI, JEUDI, JEUDI)["en_cours"] is True
    assert P.decrire(date(2026, 9, 14), date(2026, 9, 20), JEUDI)["en_cours"] is False


def test_cette_semaine_un_jeudi_ne_contient_que_deux_services():
    """C'est le piège que l'écran doit annoncer : deux services contre cinq la semaine passée."""
    assert P.decrire(LUNDI, JEUDI, JEUDI)["jours_ouverts"] == 2
    assert P.decrire(date(2026, 9, 14), date(2026, 9, 20), JEUDI)["jours_ouverts"] == 5


# ── Les périodes vues de la route ────────────────────────────────────────────────────────────

import app as flask_app


def test_le_dernier_service_remplace_la_veille_calendaire():
    """⚠️ CHAQUE JEUDI, « HIER » OUVRAIT SUR UN MERCREDI FERMÉ : zéro euro, zéro ticket, et pas
    un mot pour dire que le café n'avait pas ouvert."""
    debut, fin = flask_app.PRESET_RANGES["yesterday"](JEUDI)
    assert debut == fin == LUNDI


def test_cinq_services_est_une_semaine_de_travail_pas_sept_jours():
    debut, fin = flask_app.PRESET_RANGES["services5"](JEUDI)
    from config import count_open_days_raw
    assert count_open_days_raw(debut, fin) == 5
    assert (fin - debut).days == 6, "la fenêtre enjambe les jours fermés"


@pytest.mark.parametrize("preset", ["today", "yesterday", "services5", "week", "lastweek",
                                    "month", "all"])
def test_chaque_periode_a_un_libelle_en_francais(preset):
    """La page est lue par Quentin ; « Last week » et « Semaine dernière » ne se mélangent pas
    sur le même écran."""
    assert preset in flask_app.PRESET_LABELS
    assert flask_app.PRESET_LABELS[preset].lower() != preset


def test_toutes_les_pastilles_de_lecran_existent_cote_serveur():
    """
    ⚠️ UNE PASTILLE SANS PRESET RENVOIE LA PÉRIODE PAR DÉFAUT, SANS RIEN DIRE. Le bouton
    s'enfonce, la page se recharge, et les chiffres sont ceux d'une autre période.
    """
    import os
    import re
    g = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "index.html"), encoding="utf-8").read()
    pastilles = set(re.findall(r'data-preset="(\w+)"', g)) - {"custom"}
    assert pastilles <= set(flask_app.PRESET_RANGES), pastilles - set(flask_app.PRESET_RANGES)
    # ⚠️ ET L'INVERSE : un preset servi mais absent de l'écran est du code mort qu'on croit
    # utilisé — il survivrait à une refonte sans que personne ne le voie disparaître.
    assert set(flask_app.PRESET_RANGES) - {"custom"} <= pastilles


# ── À quoi chaque période se compare ─────────────────────────────────────────────────────────
#
# ⚠️ CETTE RÈGLE VIVAIT EN LIGNE DANS LA ROUTE, au milieu du chargement des documents. Quatre
# mutants ont survécu à une batterie parce que rien ne pouvait l'exercer sans monter toute la
# requête. Une règle qu'on ne peut pas éprouver seule finit par n'être éprouvée par personne.

def _comp(preset, debut, fin, aujourd_hui=JEUDI):
    from config import count_open_days_raw
    is_single = debut == fin
    n = (fin - debut).days + 1
    return flask_app._comparaison(preset, debut, fin, aujourd_hui, is_single, n)


def test_une_fenetre_se_compare_a_meme_nombre_de_services():
    """
    ⚠️ RECULER DE SEPT JOURS N'ÉQUILIBRE RIEN QUAND LE CALENDRIER BOUGE. « Semaine en cours » un
    jeudi contient deux services ; sept jours plus tôt en contient cinq. On conclurait sur un
    écart de 60 % qui n'est qu'un décalage de calendrier.
    """
    from config import count_open_days_raw
    cf, ct, _, libelle = _comp("week", LUNDI, JEUDI)
    assert count_open_days_raw(cf, ct) == count_open_days_raw(LUNDI, JEUDI) == 2
    assert "2 services" in libelle
    assert ct < LUNDI, "la référence empiète sur la période"


def test_les_cinq_services_se_comparent_aux_cinq_precedents():
    from config import count_open_days_raw
    debut, fin = flask_app.PRESET_RANGES["services5"](JEUDI)
    cf, ct, _, libelle = _comp("services5", debut, fin)
    assert count_open_days_raw(cf, ct) == 5 and "5 services" in libelle


def test_un_jour_se_compare_au_meme_jour_de_semaine():
    """⚠️ UN SAMEDI ET UN LUNDI N'ONT NI LA MÊME CLIENTÈLE NI LE MÊME VOLUME. Les opposer ferait
    lire une chute de moitié chaque lundi matin."""
    cf, ct, _, libelle = _comp("yesterday", LUNDI, LUNDI)
    assert cf == ct == LUNDI - timedelta(7)
    assert cf.weekday() == LUNDI.weekday()


def test_aujourdhui_se_compare_a_la_meme_heure():
    """
    ⚠️ SANS ÇA, ON OPPOSE UNE MATINÉE À UNE JOURNÉE ENTIÈRE. À 11 h, le café serait en chute de
    70 % tous les jours — et la chute disparaîtrait au fil de l'après-midi.
    """
    cf, ct, meme_heure, libelle = _comp("today", JEUDI, JEUDI)
    assert meme_heure is True and "même heure" in libelle


def test_le_mois_recule_de_quatre_semaines_pas_dun_mois():
    """Reculer d'un mois calendaire décale les jours de semaine, et le café n'ouvre pas tous les
    jours : on opposerait sam/dim/lun à mer/jeu/ven/sam/dim."""
    cf, ct, _, _ = _comp("month", date(2026, 9, 1), date(2026, 9, 24))
    assert (date(2026, 9, 1) - cf).days == 28
    assert cf.weekday() == date(2026, 9, 1).weekday()


def test_sans_reference_comparable_on_ne_compare_pas():
    """
    ⚠️ UNE RÉFÉRENCE AMPUTÉE FERAIT CONCLURE À UNE PROGRESSION QUI N'EST QU'UN MANQUE DE PASSÉ.
    Au tout début de l'historique, il n'y a rien derrière : l'écran doit le dire.
    """
    debut = date(2026, 5, 27)
    cf, ct, _, libelle = _comp("week", debut, debut + timedelta(3), debut + timedelta(3))
    assert cf is None and libelle is None


def test_la_charge_utile_annonce_la_periode():
    """
    ⚠️ LE CONSOMMATEUR DE CETTE CLÉ EST L'ÉCRAN. Sans elle, la ligne « n services sur m jours »
    reste vide et l'ambiguïté revient, sans que rien ne signale sa disparition.
    """
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app.py"), encoding="utf-8").read()
    assert '"periode":       _per.decrire(from_date, to_date, today_real),' in src
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "dashboard.js"), encoding="utf-8").read()
    assert "d.periode" in js, "l'écran ne lit pas la période annoncée"
    i = js.index("function renderInsights(")
    assert "renderPeriode(d)" in js[i:i + 260], "la ligne de période n'est jamais rendue"
    # ⚠️ ET ELLE SIGNALE UNE PÉRIODE INACHEVÉE : une période en cours comparée à une période
    # close fait lire un recul tous les matins et une reprise tous les soirs.
    j = js.index("function renderPeriode(")
    assert "en_cours" in js[j:js.index("\n}", j)]
