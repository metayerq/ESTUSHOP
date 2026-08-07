"""
⚠️ `reason` porte des CODES, pas de la prose. Première intégration avec la page : l'endpoint
renvoyait « 2 jours pleins seulement » en toutes lettres, qui s'affichait tel quel dans une
interface anglaise. Le serveur ne décide pas de la langue de l'écran — il nomme la cause, la
page possède la formulation (`reasonLabel`, static/transactions.js). Plusieurs causes se
cumulent avec « + ».

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
from datetime import date, timedelta

sys.path.insert(0, ".")

import app
from config import count_open_days_raw, SCHEDULE_CUTOVER
from app import TX_WINDOW_DAYS, TX_MIN_FULL_DAYS

# ⚠️ Ces tests décrivent des RÈGLES, pas un réglage. Ils lisent donc la taille de fenêtre et le
# seuil de fiabilité dans le module plutôt que de les recopier : le passage de 14 à 7 jours en
# avait cassé sept d'un coup alors qu'aucune règle n'avait changé.
NB_FENETRES = lambda deb, fin: -(-((fin - deb).days + 1) // TX_WINDOW_DAYS)


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
    assert derniere["tx_median"] == 20.0
    assert all(d["nb"] > 0 for d in out["days"]), "aucun jour matérialisé à zéro"


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
    assert wins[-1]["from"] == (date(2026, 8, 6) - timedelta(TX_WINDOW_DAYS - 1)).isoformat()
    assert [w["from"] for w in wins] == sorted(w["from"] for w in wins), "du plus ancien au plus récent"
    assert wins[0]["from"] == OUVERTURE.isoformat(), "on ne remonte pas avant l'ouverture"


def test_le_decoupage_ne_depend_pas_des_donnees():
    """Une fenêtre creuse EXISTE, avec None et sa raison — un trou constaté, pas un trou masqué."""
    today = date(2026, 8, 7)
    vides = app._tx_windows(app._tx_day_records([], today), OUVERTURE, today)
    pleines = app._tx_windows(
        app._tx_day_records(_rows({"2026-07-24": 20}), today), OUVERTURE, today)
    assert len(vides) == len(pleines) == NB_FENETRES(OUVERTURE, date(2026, 8, 6))
    assert [(w["from"], w["to"]) for w in vides] == [(w["from"], w["to"]) for w in pleines]


def test_la_plus_ancienne_fenetre_annonce_sa_troncature():
    """
    L'histoire ne fait pas un multiple entier de fenêtres. On garde les jours qui dépassent
    plutôt que de les jeter en silence — mais la fenêtre dit qu'elle est plus courte.
    """
    wins = app._tx_windows(app._tx_day_records([], date(2026, 8, 7)),
                           OUVERTURE, date(2026, 8, 7))
    assert wins[0]["from"] == OUVERTURE.isoformat()
    span = (date.fromisoformat(wins[0]["to"]) - date.fromisoformat(wins[0]["from"])).days + 1
    assert span < TX_WINDOW_DAYS
    assert "truncated" in wins[0]["reason"]
    assert all("tronquée" not in (w["reason"] or "") for w in wins[1:])


def test_une_fenetre_sans_jour_plein_ne_rend_aucun_chiffre():
    today = date(2026, 8, 7)
    w = _fenetre([], date(2026, 7, 24), date(2026, 8, 6), today)
    assert w["full_days"] == 0
    assert w["tx_median"] is None and w["ca_median"] is None
    assert w["basket_median"] is None and w["multi_pct"] is None
    assert w["reliable"] is False
    assert "no-days" in w["reason"]


def test_sous_le_seuil_la_fenetre_n_est_pas_fiable_mais_reste_chiffree():
    """Non fiable ≠ tue. Le chiffre est publié, accompagné de ce qui le fragilise."""
    today = date(2026, 8, 7)
    fin, deb = date(2026, 8, 6), date(2026, 8, 6) - timedelta(TX_WINDOW_DAYS - 1)
    # Un jour sous le seuil, puis exactement le seuil.
    jours = [(deb + timedelta(i)).isoformat() for i in range(TX_WINDOW_DAYS)]
    maigre = _rows({d: 20 for d in jours[:TX_MIN_FULL_DAYS - 1]})
    w = _fenetre(maigre, deb, fin, today)
    assert w["full_days"] == TX_MIN_FULL_DAYS - 1 and w["reliable"] is False
    assert w["reason"] == "too-few-days"
    assert w["tx_median"] == 20.0, "la médiane existe quand même"

    juste = _fenetre(_rows({d: 20 for d in jours[:TX_MIN_FULL_DAYS]}), deb, fin, today)
    assert juste["full_days"] == TX_MIN_FULL_DAYS
    assert juste["reliable"] is True and juste["reason"] is None


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
    # La fin est choisie pour que la fenêtre enjambe le 12 juin QUEL QUE SOIT son réglage :
    # deux jours après la bascule, donc le début retombe forcément avant.
    fin   = SCHEDULE_CUTOVER + timedelta(2)
    deb   = fin - timedelta(TX_WINDOW_DAYS - 1)
    today = fin + timedelta(1)
    assert deb < SCHEDULE_CUTOVER <= fin, "la fenêtre doit bien enjamber la bascule"

    jours = [(deb + timedelta(i)) for i in range(TX_WINDOW_DAYS)]
    ouverts = [d.isoformat() for d in jours if count_open_days_raw(d, d) == 1]

    out = app._transactions_payload(_rows({d: 20 for d in ouverts}), deb, today)
    w = out["windows"][-1]
    assert (w["from"], w["to"]) == (deb.isoformat(), fin.isoformat())
    assert w["full_days"] == len(ouverts), "on compte l'OBSERVÉ, pas un calendrier supposé"
    assert w["reliable"] is (len(ouverts) >= TX_MIN_FULL_DAYS)
    fermes = [d.isoformat() for d in jours if d.isoformat() not in ouverts]
    vus = {d["day"] for d in out["days"]}
    assert not (set(fermes) & vus), "un jour fermé est absent, pas présent à zéro"

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

def _deux_fenetres(prev_nb, cur_nb, today=date(2026, 8, 7)):
    """
    Deux fenêtres pleines et ADJACENTES, construites à partir du réglage courant plutôt que
    de dates écrites à la main — la version figée cassait au moindre changement de fenêtre.
    Chacune reçoit exactement le seuil de jours pleins.
    """
    fin_cur  = today - timedelta(1)
    deb_cur  = fin_cur - timedelta(TX_WINDOW_DAYS - 1)
    fin_prev = deb_cur - timedelta(1)
    deb_prev = fin_prev - timedelta(TX_WINDOW_DAYS - 1)

    def jours(deb):
        return [(deb + timedelta(i)).isoformat() for i in range(TX_MIN_FULL_DAYS)]

    rows = _rows({**{d: prev_nb for d in jours(deb_prev)},
                  **{d: cur_nb for d in jours(deb_cur)}})
    out = app._transactions_payload(rows, deb_prev, today)
    return out, (deb_cur, fin_cur, deb_prev, fin_prev)


def test_le_delta_compare_les_deux_dernieres_fenetres_fiables():
    out, (dc, fc, dp, fp) = _deux_fenetres(prev_nb=30, cur_nb=20)
    h = out["headline"]
    assert (h["tx_median"], h["from"], h["to"]) == (20.0, dc.isoformat(), fc.isoformat())
    assert (h["prev_tx_median"], h["prev_from"], h["prev_to"]) \
        == (30.0, dp.isoformat(), fp.isoformat())
    assert h["n"] == h["prev_n"] == TX_MIN_FULL_DAYS
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
    assert "no-prev-window" in h["reason"]


def test_une_fenetre_trop_maigre_ne_sert_pas_de_reference():
    """Deux jours pleins en face : l'écart serait tiré d'un seul jour. Pas de delta."""
    jours_cur = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    rows = _rows({**{"2026-07-16": 30, "2026-07-17": 30}, **{d: 20 for d in jours_cur}})
    h = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 8, 7))["headline"]
    assert h["delta_pct"] is None
    assert h["prev_tx_median"] is None
    assert "no-prev-window" in h["reason"]


def test_sans_aucune_fenetre_fiable_le_headline_ne_dit_rien_et_explique():
    h = app._transactions_payload(_rows({"2026-07-24": 20}), OUVERTURE, date(2026, 8, 7))["headline"]
    assert h["tx_median"] is None and h["delta_pct"] is None and h["n"] == 0
    assert "no-reliable-window" in h["reason"]


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
    today = date(2026, 8, 7)
    fin_derniere = today - timedelta(1)
    deb_derniere = fin_derniere - timedelta(TX_WINDOW_DAYS - 1)
    fin_b = deb_derniere - timedelta(1)
    deb_b = fin_b - timedelta(TX_WINDOW_DAYS - 1)
    fin_a = deb_b - timedelta(1)
    deb_a = fin_a - timedelta(TX_WINDOW_DAYS - 1)

    def jours(deb):
        return [(deb + timedelta(i)).isoformat() for i in range(TX_MIN_FULL_DAYS)]

    rows = _rows({**{d: 30 for d in jours(deb_a)}, **{d: 20 for d in jours(deb_b)},
                  deb_derniere.isoformat(): 5})           # dernière fenêtre : 1 jour plein
    h = app._transactions_payload(rows, deb_a, today)["headline"]
    assert (h["from"], h["to"]) == (deb_b.isoformat(), fin_b.isoformat())
    assert h["delta_pct"] == -33
    assert "latest-window-skipped" in h["reason"]
    # Le DÉTAIL de l'écart (« 1 jour plein seulement ») n'est plus imbriqué dans le code du
    # headline : il vit dans la fenêtre concernée, que la page affiche juste en dessous avec
    # son n et sa propre raison. L'information n'est pas perdue, elle est à un seul endroit.
    derniere = app._transactions_payload(rows, deb_a, today)["windows"][-1]
    assert derniere["full_days"] == 1
    assert "too-few-days" in derniere["reason"]


# ── 7. Le contrat de la réponse ──────────────────────────────────────────────

def test_la_forme_de_la_reponse_est_celle_attendue_par_la_page():
    """
    La page est construite en parallèle sur ce contrat : un renommage silencieux casserait un
    écran sans casser un test. Les clés sont donc fixées ici.
    """
    today = date(2026, 8, 7)
    jours = ["2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27", "2026-07-30", "2026-07-31"]
    out = app._transactions_payload(_rows({d: 20 for d in jours}), OUVERTURE, today)

    assert set(out) == {"from", "to", "days", "windows", "hourly", "weekday", "headline"}
    assert (out["from"], out["to"]) == ("2026-05-27", "2026-08-07")
    assert set(out["days"][0]) == {"day", "nb", "ca_ttc", "covers", "weekday", "partial"}
    assert set(out["windows"][0]) == {"from", "to", "full_days", "tx_median", "ca_median",
                                      "basket_median", "multi_pct", "reliable", "reason",
                                      "covers_median", "ca_per_cover", "covers_capped"}
    assert set(out["weekday"][0]) == {"weekday", "label", "tx_median", "n"}
    assert set(out["headline"]) == {"tx_median", "n", "from", "to", "prev_tx_median", "prev_n",
                                    "prev_from", "prev_to", "delta_pct", "reason"}
    assert set(out["hourly"]) == {"days_measured", "reason", "by_hour", "blocks"}
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
    assert "_ensure_summaries(debut, today_real - timedelta(1), catalog)" in src


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
    # ⚠️ Le cache démarre à TX_ANALYSIS_START, pas à l'ouverture : juin est volontairement
    # hors analyse (ouverture atypique + commandes de groupe). Décision assumée et annoncée
    # par la page, pas une troncature muette.
    assert vu["bornes"] == (app.TX_ANALYSIS_START, date(2026, 8, 6)), "le cache s'arrête à HIER"

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


# ── Le compte multi-lignes : mesuré, ou pas mesuré — jamais zéro par défaut ───

def test_un_champ_multi_count_absent_ne_vaut_pas_zero():
    """
    Trouvé à l'intégration : une reconstitution sans `multi_count` affichait « 0.0 % » sur
    toutes les fenêtres — un chiffre qui se lit « personne ne prend deux articles » là où il
    n'y a aucune mesure. Les lignes de cache écrites avant l'existence du champ sont dans ce
    cas, et rien à l'écran ne le disait.
    """
    rows = [{"day": f"2026-07-{d:02d}", "nb": 20, "ca_ttc": 200.0, "ca_ht": 177.0}
            for d in (10, 11, 12, 13, 16, 17, 18)]          # aucun multi_count
    w = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["windows"][-1]
    assert w["tx_median"] == 20.0, "le reste de la fenêtre reste mesuré"
    assert w["multi_pct"] is None, "multi_pct fabriqué à 0 alors que rien n'est mesuré"


def test_une_mesure_partielle_ne_produit_pas_une_proportion():
    """
    Trois jours sur sept portent le compte : la proportion se calculerait sur un dénominateur
    qui ne lui correspond pas. Mieux vaut ne rien dire que dire un chiffre sur mesuré.
    """
    rows = []
    for i, d in enumerate((10, 11, 12, 13, 16, 17, 18)):
        r = {"day": f"2026-07-{d:02d}", "nb": 20, "ca_ttc": 200.0, "ca_ht": 177.0}
        if i < 3:
            r["multi_count"] = 6
        rows.append(r)
    w = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["windows"][-1]
    assert w["multi_pct"] is None


def test_quand_tout_est_mesure_la_proportion_est_calculee():
    """Contrepartie : un vrai 0 mesuré doit bien s'afficher 0, pas disparaître."""
    rows = [{"day": f"2026-07-{d:02d}", "nb": 20, "ca_ttc": 200.0, "ca_ht": 177.0,
             "multi_count": 0} for d in (10, 11, 12, 13, 16, 17, 18)]
    w = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["windows"][-1]
    assert w["multi_pct"] == 0.0, "un zéro MESURÉ est une information, il s'affiche"


# ── Les heures : deux clientèles, et ce qui n'est pas instrumenté ────────────

def _jour_h(day, nb, hours=None):
    r = _jour(day, nb)
    if hours is not None:
        r["hours"] = hours
    return r


def test_sans_champ_hours_la_repartition_n_existe_pas():
    """
    Les lignes écrites avant l'existence du champ n'ont pas « zéro ticket à chaque heure »,
    elles n'ont pas la mesure. Les compter à zéro ferait passer un historique à moitié
    instrumenté pour un historique complet.
    """
    rows = [_jour_h(f"2026-07-{d:02d}", 20) for d in (10, 11, 12, 13, 16, 17, 18)]
    h = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["hourly"]
    assert h["days_measured"] == 0
    assert h["reason"] == "too-few-measured-days"
    assert h["by_hour"] == [] and h["blocks"] == []


def test_les_deux_pics_ressortent_quand_la_mesure_existe():
    """Matin et soir séparés : ce sont deux clientèles, pas une seule étalée."""
    rows = [_jour_h(f"2026-07-{d:02d}", 20, {"9": 8, "11": 4, "15": 2, "21": 6})
            for d in (10, 11, 12, 13, 16, 17, 18)]
    h = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["hourly"]
    assert h["days_measured"] == 7
    blocs = {b["block"]: b for b in h["blocks"]}
    assert blocs["morning"]["tickets"] == 7 * 12
    assert blocs["afternoon"]["tickets"] == 7 * 2
    assert blocs["evening"]["tickets"] == 7 * 6
    assert round(sum(b["pct"] for b in h["blocks"])) == 100


def test_le_jour_en_cours_n_entre_pas_dans_la_repartition():
    """Consulté à 10 h, il n'aurait que des heures du matin et fausserait les deux pics."""
    today = date(2026, 8, 7)
    passe = [_jour_h(f"2026-07-{d:02d}", 20, {"9": 10, "21": 10}) for d in (10, 11, 12, 13, 16, 17)]
    rows  = passe + [_jour_h("2026-08-07", 3, {"9": 3})]
    h = app._transactions_payload(rows, date(2026, 7, 10), today)["hourly"]
    assert h["days_measured"] == 6, "aujourd'hui est écarté de la mesure"
    blocs = {b["block"]: b for b in h["blocks"]}
    assert blocs["morning"]["tickets"] == blocs["evening"]["tickets"], \
        "les 3 tickets du matin en cours ne doivent pas déséquilibrer les pics"


def test_une_mesure_trop_maigre_ne_produit_pas_de_repartition():
    """Trois jours instrumentés ne décrivent pas une journée type."""
    rows = ([_jour_h(f"2026-07-{d:02d}", 20, {"9": 20}) for d in (10, 11, 12)]
            + [_jour_h(f"2026-07-{d:02d}", 20) for d in (13, 16, 17, 18)])
    h = app._transactions_payload(rows, date(2026, 7, 10), date(2026, 7, 24))["hourly"]
    assert h["days_measured"] == 3 and h["reason"] == "too-few-measured-days"
    assert h["by_hour"] == []


# ── Le repli qui protège la production ───────────────────────────────────────

def test_une_colonne_hours_absente_ne_fait_pas_perdre_la_ligne(monkeypatch):
    """
    `hours` demande une migration SQL. Déployer le code avant de l'exécuter ferait échouer
    TOUTE écriture de cache — pas seulement les heures : le jour entier serait perdu, et le
    cache prendrait du retard sans que rien ne le dise.

    Le dépôt applique déjà ce repli trois fois (supplier, waste_pct, category). On vérifie ici
    qu'il vaut aussi pour daily_summary, et surtout qu'il ne se déclenche QUE pour cette
    colonne : avaler une autre erreur Supabase masquerait une vraie panne.
    """
    appels = []

    def faux_upsert(table, data):
        appels.append(dict(data))
        if "hours" in data:
            return False, 'column "hours" of relation "daily_summary" does not exist'
        return True, None

    monkeypatch.setattr(app, "_supa_upsert", faux_upsert)
    ok, err = app._upsert_summary("2026-08-06", {"nb": 20, "ca_ttc": 200.0, "hours": {"9": 20}})

    assert ok is True, "la ligne doit être écrite malgré la colonne manquante"
    assert len(appels) == 2, "un essai avec hours, puis un sans"
    assert "hours" in appels[0] and "hours" not in appels[1]
    assert appels[1]["nb"] == 20, "le reste de la journée est bien conservé"


def test_une_autre_erreur_supabase_n_est_pas_avalee(monkeypatch):
    """Le repli est ciblé : une panne réelle doit remonter, pas être réessayée en silence."""
    appels = []

    def faux_upsert(table, data):
        appels.append(dict(data))
        return False, "permission denied for table daily_summary"

    monkeypatch.setattr(app, "_supa_upsert", faux_upsert)
    ok, err = app._upsert_summary("2026-08-06", {"nb": 20, "hours": {"9": 20}})

    assert ok is False and "permission denied" in err
    assert len(appels) == 1, "aucun réessai : l'erreur n'a rien à voir avec la colonne"


def test_plusieurs_colonnes_neuves_peuvent_manquer_ensemble(monkeypatch):
    """
    `hours` et `covers` arrivent par deux migrations distinctes : l'une peut être passée et pas
    l'autre. Le repli doit retirer CHAQUE colonne nommée par Supabase, pas seulement la
    première — sinon la ligne entière est perdue quand il en manque deux.
    """
    essais = []

    def faux_upsert(table, data):
        essais.append(sorted(k for k in data if k in ("hours", "covers", "covers_capped")))
        for c in ("hours", "covers"):
            if c in data:
                return False, f'column "{c}" of relation "daily_summary" does not exist'
        return True, None

    monkeypatch.setattr(app, "_supa_upsert", faux_upsert)
    ok, err = app._upsert_summary("2026-08-06", {"nb": 20, "hours": {"9": 20},
                                                 "covers": 28, "covers_capped": 0})
    assert ok is True, f"ligne perdue alors que seules des colonnes neuves manquaient : {err}"
    # Le repli est CIBLÉ : il retire ce que Supabase nomme, et RIEN d'autre. `covers_capped`
    # n'a jamais été refusé ici, il doit donc survivre — retirer des colonnes au passage
    # perdrait des mesures qu'aucune erreur ne demandait d'abandonner.
    assert essais[-1] == ["covers_capped"], essais
    assert len(essais) == 3, f"un essai par colonne refusée, puis le bon : {essais}"
