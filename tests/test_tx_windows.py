"""
L'affluence — compter les gens quand le chiffre d'affaires baisse.

Un CA qui recule ne dit pas s'il y a moins de monde ou si chacun consomme moins : les deux
produisent la même courbe. `/api/transactions/daily` sépare les deux questions — tickets d'un
côté, panier de l'autre — sur des fenêtres de 14 jours calendaires.

CE QUE CES TESTS DÉFENDENT, dans l'ordre où ces défauts se réintroduisent :

 1. La MÉDIANE, pas la moyenne. L'historique porte 80 tickets le 16 juillet et 73 le 29 juin
    contre une médiane de 20 à 30 : sur une fenêtre de 8 jours ouvrés, une moyenne se fait
    dicter le tiers de sa valeur par un seul jour.
 2. Le JOUR EN COURS n'est une référence pour rien. Consulté à 10 h, il porte trois tickets ;
    compté comme une journée, il ferait plonger toute médiane qui le contient, puis remonter
    d'elle-même au fil des heures. Un chiffre qui bouge sans qu'il se passe rien n'en est pas un.
 3. Un jour FERMÉ n'est pas un jour à zéro. Le café ferme mardi et mercredi depuis le 12 juin ;
    matérialiser ces jours à 0 tirerait chaque médiane vers le bas au rythme du calendrier.
 4. Pas de DELTA contre du vide. Comparer à une fenêtre sans jour plein donnerait −100 %, et
    comparer à deux jours pleins donnerait un écart tiré d'un seul jour.

CE QU'ILS NE COUVRENT PAS. Les fonctions testées sont pures : le cache Supabase, l'appel Vendus
du jour et le montage de la route ne sont pas exercés ici (il faudrait la base et une clé API).
Que la route passe bien `today_lisbon()` et le cache `daily_summary` est vérifié en LISANT le
source, comme test_month_series.py et test_timezone_lisbon.py.
"""
import inspect
import sys
from datetime import date

sys.path.insert(0, ".")

import app
from config import count_open_days_raw, SCHEDULE_CUTOVER


OUVERTURE = date(2026, 5, 27)


def _jour(day, nb, ca_ttc=None, multi=0):
    """Une ligne `daily_summary` minimale (le vrai cache en porte davantage)."""
    return {"day": day, "nb": nb,
            "ca_ttc": round(nb * 10.0, 2) if ca_ttc is None else ca_ttc,
            "multi_count": multi}


def _rows(day_nb):
    """{jour_iso: nb} → lignes de cache, panier fixé à 10 € pour ne pas parasiter."""
    return [_jour(d, n) for d, n in day_nb.items()]


def _fenetre(rows, w_from, w_to, today):
    """Statistiques d'une fenêtre, en partant de lignes de cache brutes."""
    return app._tx_window_stats(app._tx_day_records(rows, today), w_from, w_to)


# ── 1. La médiane elle-même ──────────────────────────────────────────────────

def test_la_mediane_prend_la_valeur_centrale_en_effectif_impair():
    assert app._median([20, 22, 80]) == 22
    assert app._median([80, 20, 22]) == 22, "la série n'est pas supposée triée"


def test_la_mediane_moyenne_les_deux_valeurs_centrales_en_effectif_pair():
    assert app._median([20, 22, 24, 80]) == 23


def test_une_serie_vide_ne_vaut_pas_zero_mais_rien():
    """
    « Aucun jour mesuré » et « des jours mesurés à zéro ticket » sont deux constats opposés.
    Un 0 se lirait « personne n'est venu », c'est-à-dire une information.
    """
    assert app._median([]) is None


def test_un_jour_hors_norme_ne_dicte_pas_la_fenetre():
    """
    Le 16 juillet a fait 80 tickets contre une vingtaine les autres jours. La moyenne de la
    fenêtre serait 30 — un niveau qu'aucun jour n'a jamais tenu.
    """
    rows = _rows({"2026-07-24": 20, "2026-07-25": 20, "2026-07-26": 20,
                  "2026-07-27": 20, "2026-07-30": 20, "2026-07-31": 80})
    w = _fenetre(rows, date(2026, 7, 24), date(2026, 8, 6), date(2026, 8, 7))
    assert w["tx_median"] == 20.0
    moyenne = round(sum([20, 20, 20, 20, 20, 80]) / 6, 1)
    assert moyenne == 30.0 and w["tx_median"] != moyenne


# ── 2. Le jour en cours ──────────────────────────────────────────────────────

def test_le_jour_en_cours_est_exclu_de_la_fenetre_meme_si_la_plage_le_contient():
    """
    Les fenêtres s'arrêtent à hier, mais la garde ne doit pas reposer QUE sur les bornes :
    on demande ici explicitement une plage qui va jusqu'à aujourd'hui.
    """
    today = date(2026, 8, 7)
    rows = _rows({"2026-07-24": 20, "2026-07-25": 20, "2026-07-26": 20,
                  "2026-07-27": 20, "2026-07-30": 20, "2026-07-31": 20,
                  "2026-08-07": 3})                      # aujourd'hui, 10 h du matin
    w = _fenetre(rows, date(2026, 7, 24), today, today)
    assert w["full_days"] == 6, "aujourd'hui ne compte pas comme journée mesurée"
    assert w["tx_median"] == 20.0, "3 tickets à 10 h ne sont pas un jour à 3 tickets"


def test_le_jour_en_cours_figure_dans_days_marque_partiel_et_nulle_part_ailleurs():
    today = date(2026, 8, 7)                              # un vendredi
    rows = _rows({"2026-07-24": 20, "2026-07-31": 20, "2026-08-07": 999})
    out = app._transactions_payload(rows, OUVERTURE, today)

    jour = [d for d in out["days"] if d["day"] == "2026-08-07"]
    assert jour and jour[0]["partial"] is True
    assert all(d["partial"] is False for d in out["days"] if d["day"] != "2026-08-07")

    vendredis = [w for w in out["weekday"] if w["weekday"] == 4][0]
    assert vendredis["n"] == 2, "aujourd'hui ne rejoint pas le lot des vendredis"
    assert vendredis["tx_median"] == 20.0


def test_le_contenu_du_jour_en_cours_ne_deplace_aucune_mediane():
    """
    Le même historique, la journée en cours à 3 tickets puis à 300 : tout ce qui est médiane
    doit être IDENTIQUE. Seule la liste `days` a le droit de bouger.
    """
    today = date(2026, 8, 7)
    base = {"2026-07-24": 20, "2026-07-25": 20, "2026-07-26": 20,
            "2026-07-27": 20, "2026-07-30": 20, "2026-07-31": 20}
    matin = app._transactions_payload(_rows({**base, "2026-08-07": 3}), OUVERTURE, today)
    soir  = app._transactions_payload(_rows({**base, "2026-08-07": 300}), OUVERTURE, today)
    assert matin["windows"] == soir["windows"]
    assert matin["weekday"] == soir["weekday"]
    assert matin["headline"] == soir["headline"]
    assert matin["days"] != soir["days"], "le constat du jour, lui, DOIT suivre la réalité"


# ── 3. Les jours fermés ──────────────────────────────────────────────────────

def test_un_jour_sans_ticket_est_absent_et_non_present_a_zero():
    """
    Un mardi fermé n'est pas une journée à 0 tickets. S'il entrait dans la série, la médiane
    d'une fenêtre de 10 jours ouvrés serait tirée vers le bas par 4 jours de fermeture.
    """
    today = date(2026, 8, 7)
    rows = _rows({"2026-07-24": 20, "2026-07-25": 20, "2026-07-26": 20,
                  "2026-07-27": 20, "2026-07-30": 20, "2026-07-31": 20,
                  "2026-07-28": 0, "2026-07-29": 0})      # mardi et mercredi fermés
    out = app._transactions_payload(rows, OUVERTURE, today)
    assert [d["day"] for d in out["days"]] == ["2026-07-24", "2026-07-25", "2026-07-26",
                                               "2026-07-27", "2026-07-30", "2026-07-31"]
    derniere = out["windows"][-1]
    assert derniere["full_days"] == 6
    assert derniere["tx_median"] == 20.0


def test_une_journee_qui_ne_porte_qu_un_avoir_n_est_pas_une_journee_ouverte():
    """
    `nb` exclut déjà les avoirs (_summarize_docs_items) : une ligne de cache à nb = 0 avec un
    CA négatif est un remboursement passé un jour de fermeture, pas une journée de vente.
    """
    recs = app._tx_day_records([_jour("2026-07-28", 0, ca_ttc=-4.50)], date(2026, 8, 7))
    assert recs == []


# ── 4. Les fenêtres ──────────────────────────────────────────────────────────

def test_les_fenetres_sont_calees_sur_hier_et_remontent_jusqu_a_l_ouverture():
    """
    Calage par la FIN : ancrées sur le 27 mai, les bornes seraient figées et la fenêtre courante
    grossirait d'un jour par jour — sa médiane bougerait alors pour deux raisons mêlées.
    """
    wins = app._tx_windows(app._tx_day_records([], date(2026, 8, 7)),
                           OUVERTURE, date(2026, 8, 7))
    assert wins[-1]["to"] == "2026-08-06", "la plus récente se termine HIER"
    assert wins[-1]["from"] == "2026-07-24"
    assert [w["from"] for w in wins] == sorted(w["from"] for w in wins), "du plus ancien au plus récent"
    assert wins[0]["from"] == OUVERTURE.isoformat(), "on ne remonte pas avant l'ouverture"


def test_le_decoupage_ne_depend_pas_des_donnees():
    """Une fenêtre creuse EXISTE, avec None et sa raison — un trou constaté, pas un trou masqué."""
    today = date(2026, 8, 7)
    vides = app._tx_windows(app._tx_day_records([], today), OUVERTURE, today)
    pleines = app._tx_windows(
        app._tx_day_records(_rows({"2026-07-24": 20}), today), OUVERTURE, today)
    assert len(vides) == len(pleines) == 6
    assert [(w["from"], w["to"]) for w in vides] == [(w["from"], w["to"]) for w in pleines]


def test_la_plus_ancienne_fenetre_annonce_sa_troncature():
    """
    72 jours d'histoire ne font pas un multiple de 14. On garde les jours qui dépassent plutôt
    que de les jeter en silence — mais la fenêtre dit qu'elle ne couvre pas deux semaines.
    """
    wins = app._tx_windows(app._tx_day_records([], date(2026, 8, 7)),
                           OUVERTURE, date(2026, 8, 7))
    assert wins[0]["from"] == "2026-05-27" and wins[0]["to"] == "2026-05-28"
    assert "tronquée" in wins[0]["reason"]
    assert all("tronquée" not in (w["reason"] or "") for w in wins[1:])


def test_une_fenetre_sans_jour_plein_ne_rend_aucun_chiffre():
    today = date(2026, 8, 7)
    w = _fenetre([], date(2026, 7, 24), date(2026, 8, 6), today)
    assert w["full_days"] == 0
    assert w["tx_median"] is None and w["ca_median"] is None
    assert w["basket_median"] is None and w["multi_pct"] is None
    assert w["reliable"] is False
    assert "aucun jour plein" in w["reason"]


def test_sous_six_jours_pleins_la_fenetre_n_est_pas_fiable_mais_reste_chiffree():
    """Non fiable ≠ tue. Le chiffre est publié, accompagné de ce qui le fragilise."""
    today = date(2026, 8, 7)
    cinq = _rows({"2026-07-24": 20, "2026-07-25": 22, "2026-07-26": 18,
                  "2026-07-27": 25, "2026-07-30": 20})
    w = _fenetre(cinq, date(2026, 7, 24), date(2026, 8, 6), today)
    assert w["full_days"] == 5 and w["reliable"] is False
    assert w["reason"] == "5 jours pleins seulement"
    assert w["tx_median"] == 20.0, "la médiane existe quand même"

    six = _fenetre(cinq + [_jour("2026-07-31", 20)], date(2026, 7, 24), date(2026, 8, 6), today)
    assert six["full_days"] == 6 and six["reliable"] is True and six["reason"] is None


def test_le_panier_median_n_est_pas_le_quotient_des_deux_medianes():
    """
    Deux médianes ne se divisent pas : leur quotient n'est la médiane de rien. `basket_median`
    est la médiane des paniers moyens JOURNALIERS — la seule mesure que le cache autorise, le
    détail ticket par ticket coûtant un appel Vendus par ticket.
    """
    today = date(2026, 8, 7)
    rows = [_jour("2026-07-24", 10, ca_ttc=200.0), _jour("2026-07-25", 10, ca_ttc=200.0),
            _jour("2026-07-26", 10, ca_ttc=200.0), _jour("2026-07-27", 40, ca_ttc=200.0),
            _jour("2026-07-30", 40, ca_ttc=200.0), _jour("2026-07-31", 40, ca_ttc=200.0)]
    w = _fenetre(rows, date(2026, 7, 24), date(2026, 8, 6), today)
    assert w["tx_median"] == 25.0 and w["ca_median"] == 200.0
    assert w["basket_median"] == 12.5                    # médiane de [20,20,20,5,5,5]
    assert w["basket_median"] != round(w["ca_median"] / w["tx_median"], 2)  # 8.0


def test_le_taux_multi_lignes_est_une_proportion_agregee_pas_une_mediane():
    """
    10 tickets multi-lignes sur 50 tickets = 20 %. La médiane des taux journaliers dirait 50 % :
    elle donnerait le même poids à un jour de 10 tickets qu'à un jour de 30.

    ⚠️ « multi » signifie « au moins DEUX LIGNES distinctes, avoirs exclus » : un ticket
    « 2 cafés » saisi en une ligne qty = 2 compte comme mono-ligne.
    """
    today = date(2026, 8, 7)
    rows = [_jour("2026-07-24", 10, multi=5), _jour("2026-07-25", 10, multi=5),
            _jour("2026-07-26", 30, multi=0)]
    w = _fenetre(rows, date(2026, 7, 24), date(2026, 8, 6), today)
    assert w["multi_pct"] == 20.0


# ── 5. La bascule de calendrier du 12 juin ───────────────────────────────────

def test_une_fenetre_a_cheval_sur_le_12_juin_compte_ce_qui_a_ete_TRAVAILLE():
    """
    Avant le 12 juin, le café ouvrait six jours sur sept (jours confirmés à la main) ; après, il
    ferme mardi ET mercredi. Une fenêtre qui enjambe la bascule contient donc un mercredi ouvert
    (le 10) et un mercredi fermé (le 17). Compter les jours OBSERVÉS est la seule mesure qui ne
    suppose aucun calendrier — et la seule qui survivra au prochain changement d'horaires.
    """
    today = date(2026, 6, 20)                       # la fenêtre pleine est 06-06 → 06-19
    ouverts = ["2026-06-06", "2026-06-07", "2026-06-08", "2026-06-10", "2026-06-11",
               "2026-06-12", "2026-06-13", "2026-06-14", "2026-06-15", "2026-06-18",
               "2026-06-19"]
    assert count_open_days_raw(date(2026, 6, 6), date(2026, 6, 19)) == len(ouverts) == 11
    assert SCHEDULE_CUTOVER == date(2026, 6, 12)

    out = app._transactions_payload(_rows({d: 20 for d in ouverts}), date(2026, 6, 6), today)
    w = out["windows"][-1]
    assert (w["from"], w["to"]) == ("2026-06-06", "2026-06-19")
    assert w["full_days"] == 11 and w["reliable"] is True
    assert "2026-06-16" not in [d["day"] for d in out["days"]], "mardi fermé, pas mardi à zéro"
    assert "2026-06-17" not in [d["day"] for d in out["days"]], "mercredi fermé après bascule"

    mercredis = [x for x in out["weekday"] if x["weekday"] == 2]
    assert mercredis and mercredis[0]["n"] == 1, "seul le mercredi 10 juin, d'avant la bascule"


def test_une_fermeture_exceptionnelle_ne_se_compte_pas_comme_jour_plein():
    """
    Le pendant du test précédent : `full_days` suit les données, pas le calendrier. Un samedi
    fermé pour cause de panne reste absent — sinon la fenêtre se croirait plus fournie qu'elle
    ne l'est, et sa fiabilité serait affirmée sur un jour qui n'a pas eu lieu.
    """
    today = date(2026, 6, 20)
    ouverts = ["2026-06-06", "2026-06-07", "2026-06-08", "2026-06-10", "2026-06-11",
               "2026-06-12", "2026-06-14", "2026-06-15", "2026-06-18", "2026-06-19"]
    w = _fenetre(_rows({d: 20 for d in ouverts}), date(2026, 6, 6), date(2026, 6, 19), today)
    assert count_open_days_raw(date(2026, 6, 6), date(2026, 6, 19)) == 11
    assert w["full_days"] == 10, "le samedi 13 juin n'a pas ouvert : il ne se compte pas"


# ── 6. Le headline : jamais de delta contre du vide ──────────────────────────

def _deux_fenetres(prev_nb, cur_nb):
    """Deux fenêtres pleines et adjacentes : 07-10 → 07-23, puis 07-24 → 08-06."""
    jours_prev = ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-16", "2026-07-17"]
    jours_cur  = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    rows = _rows({**{d: prev_nb for d in jours_prev}, **{d: cur_nb for d in jours_cur}})
    return app._transactions_payload(rows, date(2026, 7, 10), date(2026, 8, 7))


def test_le_delta_compare_les_deux_dernieres_fenetres_fiables():
    out = _deux_fenetres(prev_nb=30, cur_nb=20)
    h = out["headline"]
    assert (h["tx_median"], h["n"], h["from"], h["to"]) == (20.0, 6, "2026-07-24", "2026-08-06")
    assert (h["prev_tx_median"], h["prev_n"], h["prev_from"], h["prev_to"]) \
        == (30.0, 6, "2026-07-10", "2026-07-23")
    assert h["delta_pct"] == -33
    assert h["reason"] is None


def test_une_seule_fenetre_fiable_ne_produit_pas_de_delta():
    """
    La fenêtre précédente est vide. La traiter comme un 0 donnerait −100 % : le récit d'un café
    qui se serait vidé, alors qu'on n'a simplement rien mesuré avant.
    """
    jours_cur = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    out = app._transactions_payload(_rows({d: 20 for d in jours_cur}),
                                    date(2026, 7, 10), date(2026, 8, 7))
    h = out["headline"]
    assert h["tx_median"] == 20.0, "le niveau, lui, est connu"
    assert h["delta_pct"] is None
    assert h["prev_tx_median"] is None and h["prev_n"] == 0
    assert "une seule fenêtre fiable" in h["reason"]


def test_une_fenetre_trop_maigre_ne_sert_pas_de_reference():
    """Deux jours pleins en face : l'écart serait tiré d'un seul jour. Pas de delta."""
    jours_cur = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    rows = _rows({**{"2026-07-16": 30, "2026-07-17": 30}, **{d: 20 for d in jours_cur}})
    h = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 8, 7))["headline"]
    assert h["delta_pct"] is None
    assert h["prev_tx_median"] is None
    assert "une seule fenêtre fiable" in h["reason"]


def test_sans_aucune_fenetre_fiable_le_headline_ne_dit_rien_et_explique():
    h = app._transactions_payload(_rows({"2026-07-24": 20}), OUVERTURE, date(2026, 8, 7))["headline"]
    assert h["tx_median"] is None and h["delta_pct"] is None and h["n"] == 0
    assert "jours pleins" in h["reason"]


def test_les_premiers_jours_n_ont_pas_encore_de_fenetre():
    """Jour de l'ouverture : rien n'est terminé, il n'y a donc rien à découper."""
    out = app._transactions_payload(_rows({"2026-05-27": 12}), OUVERTURE, OUVERTURE)
    assert out["windows"] == []
    assert out["headline"]["delta_pct"] is None and out["headline"]["reason"]
    assert len(out["days"]) == 1 and out["days"][0]["partial"] is True


def test_une_fenetre_recente_ecartee_est_annoncee():
    """
    Si la dernière fenêtre n'est pas fiable, le chiffre du haut de page n'est PAS celui des deux
    dernières semaines. Le taire laisserait décider sur un chiffre daté sans le savoir.
    """
    jours_a = ["2026-06-26", "2026-06-27", "2026-06-28", "2026-06-29", "2026-07-02", "2026-07-03"]
    jours_b = ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-16", "2026-07-17"]
    rows = _rows({**{d: 30 for d in jours_a}, **{d: 20 for d in jours_b},
                  "2026-07-24": 5})                       # dernière fenêtre : 1 jour plein
    h = app._transactions_payload(rows, date(2026, 6, 26), date(2026, 8, 7))["headline"]
    assert (h["from"], h["to"]) == ("2026-07-10", "2026-07-23")
    assert h["delta_pct"] == -33
    assert "la plus récente écartée" in h["reason"]
    assert "1 jour plein seulement" in h["reason"], "la raison de l'écart est reprise telle quelle"


# ── 7. Le contrat de la réponse ──────────────────────────────────────────────

def test_la_forme_de_la_reponse_est_celle_attendue_par_la_page():
    """
    La page est construite en parallèle sur ce contrat : un renommage silencieux casserait un
    écran sans casser un test. Les clés sont donc fixées ici.
    """
    today = date(2026, 8, 7)
    jours = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    out = app._transactions_payload(_rows({d: 20 for d in jours}), OUVERTURE, today)

    assert set(out) == {"from", "to", "days", "windows", "weekday", "headline"}
    assert (out["from"], out["to"]) == ("2026-05-27", "2026-08-07")
    assert set(out["days"][0]) == {"day", "nb", "ca_ttc", "weekday", "partial"}
    assert set(out["windows"][0]) == {"from", "to", "full_days", "tx_median", "ca_median",
                                      "basket_median", "multi_pct", "reliable", "reason"}
    assert set(out["weekday"][0]) == {"weekday", "label", "tx_median", "n"}
    assert set(out["headline"]) == {"tx_median", "n", "from", "to", "prev_tx_median", "prev_n",
                                    "prev_from", "prev_to", "delta_pct", "reason"}
    assert out["days"][0]["weekday"] == date(2026, 7, 24).weekday() == 4


def test_les_libelles_de_jour_ne_dependent_pas_de_la_locale_du_serveur():
    """`strftime("%A")` parlerait la langue du runtime — celle de Vercel n'est pas celle du dev."""
    today = date(2026, 8, 7)
    out = app._transactions_payload(_rows({"2026-07-24": 20, "2026-07-27": 20}), OUVERTURE, today)
    par_wd = {w["weekday"]: w["label"] for w in out["weekday"]}
    assert par_wd == {0: "Monday", 4: "Friday"}


# ── 8. Le montage de la route, lu dans le source ─────────────────────────────

def test_la_route_date_son_aujourd_hui_sur_lisbonne_et_lit_le_cache():
    """
    `date.today()` sur un serveur UTC désigne la veille entre minuit et 1 h locale : la fenêtre
    courante s'arrêterait alors avant-hier, et la journée d'hier disparaîtrait des médianes.
    """
    src = inspect.getsource(app.api_transactions_daily)
    assert "today_lisbon()" in src and "date.today()" not in src
    assert "_ensure_summaries(" in src, "l'historique vient du cache, pas d'appels Vendus"
    assert "_get_today_docs_cached()" in src, "le jour courant est monté en mémoire"
    assert "_upsert_summary" not in src, "on n'écrit JAMAIS le jour courant dans le cache"


def test_la_route_ne_demande_jamais_au_cache_de_figer_aujourd_hui():
    """La garde de `_ensure_summaries` existe ; encore faut-il ne pas la frôler."""
    src = inspect.getsource(app.api_transactions_daily)
    assert "_ensure_summaries(opening, today_real - timedelta(1), catalog)" in src


def test_la_route_repond_avec_le_cache_et_le_jour_courant_monte_en_memoire(monkeypatch):
    """
    Le montage réel, Supabase et Vendus bouchonnés : c'est le seul moyen d'exercer d'ici la
    route entière (le dépôt n'a ni identifiants ni clé API en test).

    Ce qui est vérifié ici et nulle part ailleurs : la borne haute demandée au cache est bien
    HIER. Un `today_real` passé tel quel ferait écrire par `_ensure_summaries` une ligne
    `daily_summary` figée à l'heure de la consultation — et comme on ne reconstruit que les
    jours manquants, elle ne serait plus jamais corrigée. La garde vit dans `_ensure_summaries`,
    mais un appelant qui la frôle mérite un test.
    """
    vu = {}

    def faux_ensure(from_date, to_date, catalog):
        vu["bornes"] = (from_date, to_date)
        return [_jour("2026-07-24", 20), _jour("2026-07-31", 22)]

    monkeypatch.setattr(app, "DASHBOARD_PASSWORD", "")          # pas de login en test
    monkeypatch.setattr(app, "today_lisbon", lambda: date(2026, 8, 7))
    monkeypatch.setattr(app, "get_catalog", lambda: {})
    monkeypatch.setattr(app, "_ensure_summaries", faux_ensure)
    monkeypatch.setattr(app, "_get_today_docs_cached", lambda: [
        {"amount_gross": 12.0, "amount_net": 10.6,
         "items": [{"title": "Café", "qty": 1,
                    "amounts": {"net_total": 10.6, "gross_total": 12.0}}]}])

    rep = app.app.test_client().get("/api/transactions/daily")
    assert rep.status_code == 200
    data = rep.get_json()
    assert data["ok"] is True
    assert vu["bornes"] == (date(2026, 5, 27), date(2026, 8, 6)), "le cache s'arrête à HIER"

    aujourdhui = [d for d in data["days"] if d["day"] == "2026-08-07"]
    assert aujourdhui and aujourdhui[0]["partial"] is True and aujourdhui[0]["nb"] == 1
    assert all(w["to"] <= "2026-08-06" for w in data["windows"])


def test_aucune_projection_ni_tendance_n_est_calculee():
    """
    Une quarantaine de jours ouvrés, un changement de calendrier au milieu, un mois d'août
    touristique : toute pente calculée là-dessus décrirait le bruit. Ce test est là pour que
    l'ajout d'une régression soit un choix explicite, pas un ajout discret.
    """
    for fn in (app._transactions_payload, app._tx_windows, app._tx_headline, app._tx_window_stats):
        src = inspect.getsource(fn)
        for interdit in ("polyfit", "linregress", "slope", "trend", "proj_"):
            assert interdit not in src, f"{fn.__name__} calcule une tendance ({interdit})"
