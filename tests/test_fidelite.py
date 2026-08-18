"""
Fidélité : dix boissons, la onzième offerte.

⚠️ POURQUOI DES BOISSONS ET NON DES EUROS. Un livre à 25 € laisse 10 € de marge (40 %), un café
à 4 € en laisse 3,30 (82 %). Avec « 1 € = 1 point », un seul livre vaudrait la moitié d'une
récompense sur des euros deux fois moins margés : les cafés offerts seraient financés par la
librairie — celle qui en a le moins les moyens. Ces tests portent cette règle.
"""
import sys
sys.path.insert(0, ".")

import app as A
from datetime import date


CAFE = "Bica"
LIVRE = "Livro"
CATALOGUE = {CAFE: {"category_id": next(iter(A.DRINK_CAT_IDS))}, LIVRE: {"category_id": 999}}


# ── Compter les boissons ────────────────────────────────────────────────────

def test_compte_les_boissons_et_ignore_le_reste():
    """C'est toute la règle : un livre ne rapproche pas d'un café offert."""
    items = [{"title": CAFE, "qty": 2}, {"title": LIVRE, "qty": 1}]
    assert A._loyalty_count_drinks(items, CATALOGUE) == 2


def test_compte_les_QUANTITÉS():
    assert A._loyalty_count_drinks([{"title": CAFE, "qty": 3}], CATALOGUE) == 3


def test_un_article_inconnu_ne_compte_pas():
    """
    ⚠️ SENS SÛR DE L'ERREUR. Créditer un article qu'on ne sait pas classer offrirait des cafés
    sur des ventes qui n'en sont pas.
    """
    assert A._loyalty_count_drinks([{"title": "Inconnu", "qty": 5}], CATALOGUE) == 0


def test_une_quantité_absurde_ne_crédite_rien():
    for q in (0, -3, None, "x"):
        assert A._loyalty_count_drinks([{"title": CAFE, "qty": q}], CATALOGUE) == 0, q


def test_un_panier_vide_ne_crédite_rien():
    assert A._loyalty_count_drinks(None, CATALOGUE) == 0
    assert A._loyalty_count_drinks([], CATALOGUE) == 0


# ── Le seuil ────────────────────────────────────────────────────────────────

def test_la_récompense_arrive_à_dix_boissons():
    assert A._loyalty_rewards_available(9) == 0
    assert A._loyalty_rewards_available(10) == 1
    assert A._loyalty_rewards_available(21) == 2


def test_un_solde_négatif_ne_donne_jamais_de_récompense():
    """Une donnée abîmée ne doit pas se transformer en cafés offerts."""
    assert A._loyalty_rewards_available(-5) == 0
    assert A._loyalty_rewards_available(None) == 0


# ── Les numéros ─────────────────────────────────────────────────────────────

def test_le_premier_membre_reçoit_le_numéro_1():
    """Court et séquentiel : on le récite au comptoir."""
    assert A._loyalty_next_number([]) == 1


def test_un_numéro_n_est_JAMAIS_réemployé():
    """
    ⚠️ MÊME APRÈS UNE SUPPRESSION. Reboucher un trou rattacherait les points d'hier à quelqu'un
    d'autre, et le client concerné réciterait un numéro qui n'est plus le sien sans que rien ne
    l'indique.
    """
    existants = [{"number": 1}, {"number": 2}, {"number": 7}]   # 3 à 6 supprimés
    assert A._loyalty_next_number(existants) == 8


# ── Ce que le POS reçoit ────────────────────────────────────────────────────

def test_la_fiche_publique_ne_porte_pas_le_téléphone():
    """Le POS n'en a aucun usage : ce qu'il ne reçoit pas ne peut pas fuir de son écran."""
    vue = A._loyalty_public({"number": 3, "first_name": "Maria", "drinks": 12,
                             "rewards": 1, "phone": "912345678"})
    assert "phone" not in vue
    assert vue["first_name"] == "Maria"
    assert vue["rewards_available"] == 1
    assert vue["threshold"] == A.LOYALTY_THRESHOLD


# ── Le jeton ────────────────────────────────────────────────────────────────

def test_un_jeton_absent_REFUSE_tout(monkeypatch):
    """
    ⚠️ UN SECRET NON CONFIGURÉ NE VAUT PAS « ACCÈS LIBRE ». Ce serait la panne qu'on ne remarque
    jamais — jusqu'au jour où quelqu'un s'offre des cafés.
    """
    monkeypatch.delenv("LOYALTY_TOKEN", raising=False)
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "peu-importe"}):
        assert A._loyalty_authorized() is False


def test_le_bon_jeton_passe_et_le_mauvais_non(monkeypatch):
    monkeypatch.setenv("LOYALTY_TOKEN", "secret-partagé")
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "secret-partagé"}):
        assert A._loyalty_authorized() is True
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "autre"}):
        assert A._loyalty_authorized() is False
    with A.app.test_request_context("/api/loyalty/member/1"):
        assert A._loyalty_authorized() is False


def test_l_API_fidélité_échappe_au_login_dashboard_mais_pas_au_jeton():
    """
    ⚠️ VÉRIFIE LE BRANCHEMENT. Le POS n'a pas de session dashboard : sans cette dérogation il
    ne pourrait rien créditer. Mais la dérogation ne doit ouvrir QUE le chemin fidélité, et le
    jeton doit rester exigé dans chaque route.
    """
    import inspect
    src = inspect.getsource(A._require_auth)
    assert 'request.path.startswith("/api/loyalty/")' in src
    for route in (A.api_loyalty_member, A.api_loyalty_create,
                  A.api_loyalty_credit, A.api_loyalty_redeem):
        assert "_loyalty_authorized()" in inspect.getsource(route), route.__name__


# ── La liste du dashboard ───────────────────────────────────────────────────

def test_la_liste_des_membres_reste_SOUS_LE_LOGIN():
    """
    ⚠️ LE PIÈGE DE LA DÉROGATION. `/api/loyalty/` échappe au login pour laisser passer le POS.
    La liste des clients vit sur ce même chemin : sans contrôle explicite dans la route, le
    fichier des membres serait PUBLIC. Le jeton du POS ne suffit pas non plus — il sert à
    créditer des points, pas à lire le fichier.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_list)
    assert "_current_role()" in src, "la liste n'est plus protégée par le login"


def test_la_page_fidélité_est_servie():
    with A.app.test_request_context("/loyalty"):
        assert A.page_loyalty() is not None


def test_l_onglet_figure_dans_la_navigation():
    """Une page qu'aucun lien n'atteint n'existe pas — c'est arrivé au bouton « Éditer »."""
    import pathlib
    nav = pathlib.Path("templates/index.html").read_text()
    assert 'data-path="/loyalty"' in nav


# ── Le jeton et les blancs de bord ──────────────────────────────────────────

def test_un_retour_à_la_ligne_ne_change_pas_le_secret(monkeypatch):
    """
    ⚠️ LE DÉFAUT RÉELLEMENT RENCONTRÉ. `openssl rand -hex` produit un retour à la ligne, et
    l'interface de Vercel conserve ce qu'on lui colle. Un secret correct suivi d'un « \\n »
    donnait un refus strictement indiscernable d'un mauvais jeton — et personne ne pense à
    chercher un caractère invisible.
    """
    monkeypatch.setenv("LOYALTY_TOKEN", "abc123\n")
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "abc123"}):
        assert A._loyalty_authorized() is True
    monkeypatch.setenv("LOYALTY_TOKEN", "abc123")
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": " abc123 "}):
        assert A._loyalty_authorized() is True


def test_un_jeton_réellement_différent_est_toujours_refusé(monkeypatch):
    """Le nettoyage ne doit pas devenir une tolérance."""
    monkeypatch.setenv("LOYALTY_TOKEN", "abc123")
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "abc124"}):
        assert A._loyalty_authorized() is False


def test_un_jeton_qui_n_est_QUE_des_blancs_refuse(monkeypatch):
    """Sinon un secret mal collé (vide + espaces) vaudrait « accès libre »."""
    monkeypatch.setenv("LOYALTY_TOKEN", "   ")
    with A.app.test_request_context("/api/loyalty/member/1",
                                    headers={"X-Loyalty-Token": "   "}):
        assert A._loyalty_authorized() is False


# ── Un numéro imposé ────────────────────────────────────────────────────────

def test_un_numéro_déjà_pris_est_REFUSÉ():
    """
    ⚠️ REFUSER PLUTÔT QU'ÉCRASER. Reprendre le numéro d'un membre existant rattacherait ses
    points à quelqu'un d'autre, et les deux réciteraient le même numéro au comptoir — jusqu'au
    jour où l'un réclame une récompense que l'autre a consommée.
    """
    existants = [{"number": 1}, {"number": 47}]
    assert A._loyalty_number_taken(existants, 47) is True
    assert A._loyalty_number_taken(existants, 48) is False


def test_le_refus_est_BRANCHÉ_sur_l_inscription():
    """La règle juste que plus personne n'appelle : le trou classique de ce dépôt."""
    import inspect
    src = inspect.getsource(A.api_loyalty_create)
    assert "_loyalty_number_taken(existants, numero)" in src
    assert "number_taken" in src


# ── La recherche par prénom ─────────────────────────────────────────────────

def test_la_recherche_exige_le_jeton_et_ne_déverse_pas_le_fichier():
    """
    ⚠️ DEUX GARDES EN UNE. Le jeton, comme partout ici ; et surtout : une requête VIDE ne rend
    pas tout le fichier. Déverser la liste des clients sur un écran de comptoir n'aide personne
    à retrouver quelqu'un, et expose tout le monde.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_search)
    assert "_loyalty_authorized()" in src
    assert 'return jsonify({"members": []})' in src
    # Bornée : au-delà de huit, la liste ne se lit plus d'un coup d'œil.
    assert '"limit": 8' in src
    # Insensible à la casse : on tape deux lettres au comptoir, pas un prénom exact.
    assert "ilike" in src


# ── Corriger un solde ───────────────────────────────────────────────────────

def test_une_correction_ne_descend_jamais_sous_zéro():
    """
    ⚠️ Un solde négatif se propagerait : le client verrait « −3 / 10 » sans comprendre, et le
    prochain crédit partirait d'un trou qu'il n'a pas creusé.
    """
    assert A._loyalty_apply_adjust(2, -10) == 0
    assert A._loyalty_apply_adjust(12, -10) == 2
    assert A._loyalty_apply_adjust(None, 3) == 3


def test_la_correction_exige_le_LOGIN_et_un_MOTIF():
    """
    ⚠️ DEUX GARDES. Corriger un solde est un geste de patron, pas de caisse : le jeton du POS
    sert à créditer ce qui a été vendu, jamais à réécrire un compte. Et sans motif, une
    correction devient indiscernable d'une erreur de plus.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_adjust)
    assert "_current_role()" in src, "la correction n'est pas protégée par le login"
    assert "_loyalty_authorized" not in src, "le jeton du POS ne doit PAS suffire ici"
    assert "reason_required" in src


# ── Mesurer le programme ────────────────────────────────────────────────────

from datetime import date as _d


def _ev(n, jour, drinks=1, kind="credit"):
    return {"number": n, "kind": kind, "drinks": drinks, "at": f"{jour}T10:00:00+00:00"}


def test_aucune_moyenne_sur_moins_de_deux_visites():
    """
    ⚠️ LE PIÈGE. Un membre vu une seule fois n'a pas de « fréquence de retour ». L'inclure à zéro
    écraserait la moyenne et ferait conclure que le programme ne fait revenir personne — alors
    qu'on n'en sait rien.
    """
    s = A._loyalty_stats([{"number": 1, "rewards": 0}], [_ev(1, "2026-08-01")], _d(2026, 8, 18))
    assert s["avg_days_between_visits"] is None
    assert s["returned"] == 0


def test_la_fréquence_se_calcule_sur_les_revenus():
    events = [_ev(1, "2026-08-01"), _ev(1, "2026-08-05"), _ev(2, "2026-08-02"), _ev(2, "2026-08-12")]
    s = A._loyalty_stats([{"number": 1}, {"number": 2}], events, _d(2026, 8, 18))
    assert s["returned"] == 2
    assert s["avg_days_between_visits"] == 7.0   # (4 + 10) / 2


def test_deux_crédits_le_MÊME_JOUR_ne_font_pas_deux_visites():
    """Deux tickets d'affilée, c'est une visite — sinon la fréquence paraît deux fois meilleure."""
    s = A._loyalty_stats([{"number": 1}], [_ev(1, "2026-08-01"), _ev(1, "2026-08-01")], _d(2026, 8, 2))
    assert s["avg_days_between_visits"] is None


def test_le_coût_est_une_FOURCHETTE():
    """
    ⚠️ Une boisson offerte à quelqu'un qui serait venu coûte son PRIX ; une qui provoque une
    visite ne coûte que son ACHAT. On ne peut pas trancher a posteriori — un chiffre unique
    serait faussement précis.
    """
    s = A._loyalty_stats([{"number": 1, "rewards": 3}], [], _d(2026, 8, 18))
    assert s["cost_low_eur"] == round(3 * A.LOYALTY_COST_EUR, 2)
    assert s["cost_high_eur"] == round(3 * A.LOYALTY_PRICE_EUR, 2)
    assert s["cost_low_eur"] < s["cost_high_eur"]


def test_un_programme_vide_ne_rend_pas_des_zéros_trompeurs():
    s = A._loyalty_stats([], [], _d(2026, 8, 18))
    assert s["avg_days_between_visits"] is None
    assert s["reward_rate_pct"] is None


# ── Ce qui compte comme boisson ─────────────────────────────────────────────

def test_exactement_trois_catégories_comptent():
    """
    ⚠️ LA RÈGLE DU CAFÉ, ÉPINGLÉE. Coffee, Cold Coffee, Non-Coffee — et rien d'autre. Un
    cheesecake ne rapproche pas d'un café offert, et une catégorie ajoutée au catalogue ne doit
    pas se mettre à compter parce que personne n'a relu cette ligne.

    Les identifiants sont ceux du compte réel :
      343052000 Coffee · 343053226 Cold Coffee · 343046110 Non-Coffee
    """
    import vendus
    assert vendus.DRINK_CAT_IDS == {343052000, 343053226, 343046110}


def test_un_ticket_sans_boisson_ne_compte_pas():
    """« Si pas de boissons, pas de passage. » Un cheesecake seul ne crédite rien."""
    catalogue = {"Cheesecake": {"category_id": 343055566}}   # Food
    assert A._loyalty_count_drinks([{"title": "Cheesecake", "qty": 1}], catalogue) == 0


def test_un_ticket_mixte_ne_compte_que_la_boisson():
    """« Cheesecake basque et americano » : la boisson compte, la pâtisserie non."""
    catalogue = {"Cheesecake": {"category_id": 343055566},
                 "Americano": {"category_id": 343052000}}
    items = [{"title": "Cheesecake", "qty": 1}, {"title": "Americano", "qty": 1}]
    assert A._loyalty_count_drinks(items, catalogue) == 1


def test_les_livres_et_le_retail_ne_comptent_jamais():
    catalogue = {"Livro": {"category_id": 343071668}, "Papeterie": {"category_id": 343077316}}
    items = [{"title": "Livro", "qty": 2}, {"title": "Papeterie", "qty": 1}]
    assert A._loyalty_count_drinks(items, catalogue) == 0


def test_deux_cafés_sur_un_ticket_font_DEUX_boissons():
    """
    ⚠️ DÉCISION EXPLICITE DU CAFÉ, à ne pas « simplifier » plus tard.

    On compte des BOISSONS, pas des passages. Deux cafés sur un même ticket valent deux, et non
    un. L'écart n'est pas cosmétique : à 1,40 boisson par ticket — mesuré sur les données réelles
    de juillet-août —, dix boissons représentent environ SEPT visites, tandis que dix passages en
    représenteraient DIX. Plafonner à un par ticket rendrait la récompense 40 % moins fréquente,
    donc le programme 40 % moins généreux, sans que personne ne l'ait décidé.
    """
    catalogue = {"Americano": {"category_id": 343052000}}
    assert A._loyalty_count_drinks([{"title": "Americano", "qty": 2}], catalogue) == 2
    # Et deux LIGNES de boissons différentes s'additionnent aussi.
    catalogue["Cold Brew"] = {"category_id": 343053226}
    items = [{"title": "Americano", "qty": 1}, {"title": "Cold Brew", "qty": 2}]
    assert A._loyalty_count_drinks(items, catalogue) == 3


# ── La fiche, l'édition, la suppression ─────────────────────────────────────

def test_supprimer_le_DERNIER_membre_ne_libère_pas_son_numéro():
    """
    ⚠️ LE DÉFAUT QUE LE TEST PRÉCÉDENT NE VOYAIT PAS. Il couvrait un trou au MILIEU
    (1, 2, 7 → 8), qui passe même avec un « max + 1 » naïf. Supprimer le DERNIER, lui, libérait
    son numéro : deux personnes auraient récité le même au comptoir à des mois d'intervalle, et
    les points de la première seraient allés à la seconde.

    La ligne reste donc en base, anonymisée — elle ne réserve plus qu'un numéro.
    """
    apres = A._loyalty_anonymise({"number": 3, "drinks": 4, "rewards": 1, "first_name": "Maria"})
    # La ligne existe toujours, donc `_loyalty_next_number` la voit encore.
    assert A._loyalty_next_number([{"number": 1}, {"number": 2}, apres]) == 4


def test_la_suppression_efface_VRAIMENT_les_données_personnelles():
    """Réserver un numéro ne doit pas servir de prétexte à conserver un fichier."""
    apres = A._loyalty_anonymise({"number": 3, "first_name": "Maria", "phone": "912345678",
                                  "email": "m@x.co", "notes": "lait d'avoine",
                                  "birth_day": 4, "birth_month": 7, "drinks": 4, "rewards": 1})
    for champ in ("phone", "email", "notes", "birth_day", "birth_month", "consent_at"):
        assert apres[champ] is None, champ
    assert apres["first_name"] == "—"
    assert apres["status"] == "deleted"
    # Les compteurs restent : l'historique du programme ne se réécrit pas.
    assert apres["drinks"] == 4 and apres["rewards"] == 1


def test_une_fiche_supprimée_n_est_plus_un_membre():
    assert A._loyalty_is_deleted({"status": "deleted"}) is True
    assert A._loyalty_is_deleted({"status": None}) is False


def test_la_caisse_ne_retrouve_PAS_une_fiche_supprimée():
    """
    ⚠️ Sinon elle y créditerait des points, et afficherait « — » comme un prénom à confronter au
    visage — c'est-à-dire aucune garde du tout.
    """
    import inspect
    assert "_loyalty_is_deleted(row)" in inspect.getsource(A.api_loyalty_member)
    assert "_loyalty_is_deleted(r)" in inspect.getsource(A.api_loyalty_search)


def test_l_édition_ne_touche_QU_AUX_champs_envoyés():
    """
    ⚠️ UN CHAMP ABSENT N'EST PAS UN CHAMP VIDÉ. Corriger un prénom ne doit pas effacer un
    téléphone — c'est la différence entre une correction et une perte silencieuse.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_edit)
    for champ in ("first_name", "phone", "email", "notes"):
        assert f'if "{champ}" in data:' in src, champ


def test_l_édition_refuse_de_vider_le_prénom():
    """C'est la seule garde contre la faute de frappe au comptoir."""
    import inspect
    assert "first_name_required" in inspect.getsource(A.api_loyalty_edit)


def test_l_e_mail_est_vérifié_a_minima_et_peut_être_EFFACÉ():
    assert A._loyalty_clean_email("  m@example.com ") == ("m@example.com", None)
    assert A._loyalty_clean_email("pasunemail")[1] == "email_invalid"
    # Un champ vidé efface, il ne refuse pas : c'est le geste « retirer le contact ».
    assert A._loyalty_clean_email("") == (None, None)


def test_la_fiche_du_dashboard_porte_les_contacts_mais_pas_celle_du_POS():
    """
    ⚠️ Le POS n'a aucun usage d'un téléphone : ce qu'il ne reçoit pas ne peut pas s'afficher par
    mégarde sur un écran de comptoir.
    """
    row = {"number": 3, "first_name": "Maria", "drinks": 2, "rewards": 0,
           "phone": "912345678", "email": "m@x.co"}
    assert "phone" not in A._loyalty_public(row)
    assert A._loyalty_full(row)["phone"] == "912345678"


def test_la_fiche_et_l_édition_sont_sous_le_LOGIN():
    import inspect
    for route in (A.api_loyalty_card, A.api_loyalty_edit, A.api_loyalty_delete):
        src = inspect.getsource(route)
        assert "_current_role()" in src, route.__name__
        assert "_loyalty_authorized" not in src, route.__name__


def test_la_fiche_est_atteignable_depuis_la_liste():
    """
    ⚠️ UNE FICHE QU'AUCUN CLIC N'ATTEINT N'EXISTE PAS. C'est arrivé au bouton « Éditer » des
    événements — rendu, cliquable pour un test, et caché derrière un tiroir par son z-index.
    On vérifie ici les trois maillons : le nom est un bouton, le modal existe, et il passe
    au-dessus du reste.
    """
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert 'class="voir"' in page, "le prénom n'est pas cliquable"
    assert 'id="fiche"' in page, "le modal n'existe pas"
    assert "z-index:9999" in page, "le modal peut passer derrière un autre élément"
    assert "/card" in page, "la fiche ne charge pas l'historique"


def test_la_fiche_propose_l_édition_ET_la_suppression():
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "method:'PATCH'" in page
    assert "method:'DELETE'" in page
    # ⚠️ La suppression se confirme, et la confirmation DIT ce qu'elle efface et ce qu'elle garde.
    assert "confirm(" in page
    assert "reste r\\u00e9serv\\u00e9" in page


# ── L'anniversaire ──────────────────────────────────────────────────────────

def test_jour_et_mois_seulement_jamais_l_année():
    """
    ⚠️ On n'a aucun usage de l'âge d'un client, et s'en passer retire à cette donnée l'essentiel
    de sa sensibilité : c'est une date de fête, pas un élément d'identité.
    """
    assert A._loyalty_clean_birthday(4, 7) == (4, 7, None)


def test_une_date_impossible_est_REFUSÉE_et_non_corrigée():
    """Un 31 février corrigé en silence ferait fêter quelqu'un le mauvais jour, tous les ans."""
    assert A._loyalty_clean_birthday(31, 2)[2] == "birthday_invalid"
    assert A._loyalty_clean_birthday(0, 5)[2] == "birthday_invalid"
    assert A._loyalty_clean_birthday(12, 13)[2] == "birthday_invalid"
    assert A._loyalty_clean_birthday("abc", 5)[2] == "birthday_invalid"


def test_le_29_février_est_une_date_valide():
    """Il existe, et des gens sont nés ce jour-là."""
    assert A._loyalty_clean_birthday(29, 2) == (29, 2, None)


def test_deux_champs_vides_EFFACENT_l_anniversaire():
    assert A._loyalty_clean_birthday(None, None) == (None, None, None)
    assert A._loyalty_clean_birthday("", "") == (None, None, None)


def test_l_anniversaire_se_reconnaît_le_bon_jour():
    m = {"birth_day": 4, "birth_month": 7}
    assert A._loyalty_is_birthday(m, date(2026, 7, 4)) is True
    assert A._loyalty_is_birthday(m, date(2026, 7, 5)) is False
    # Toutes les années, pas seulement celle de la saisie.
    assert A._loyalty_is_birthday(m, date(2031, 7, 4)) is True


def test_sans_anniversaire_renseigné_rien_ne_se_déclenche():
    assert A._loyalty_is_birthday({}, date(2026, 7, 4)) is False
    assert A._loyalty_is_birthday({"birth_day": 4, "birth_month": None}, date(2026, 7, 4)) is False


def test_le_29_fevrier_se_fete_le_28_les_annees_non_bissextiles():
    """
    Sans cette règle, un client né le 29 février ne serait JAMAIS fêté trois années sur quatre.
    Le décaler d'un jour vaut mieux que de l'oublier.
    """
    m = {"birth_day": 29, "birth_month": 2}
    assert A._loyalty_is_birthday(m, date(2027, 2, 28)) is True    # 2027 non bissextile
    assert A._loyalty_is_birthday(m, date(2028, 2, 28)) is False   # 2028 bissextile : c'est le 29
    assert A._loyalty_is_birthday(m, date(2028, 2, 29)) is True


def test_le_POS_reçoit_un_BOOLÉEN_et_jamais_la_date():
    """
    ⚠️ Ce que la caisse ne reçoit pas ne peut pas s'afficher par mégarde sur un écran de
    comptoir. Le calcul se fait sur le dashboard.
    """
    vue = A._loyalty_public({"number": 1, "first_name": "Maria", "drinks": 0, "rewards": 0,
                             "birth_day": 4, "birth_month": 7})
    assert "birth_day" not in vue and "birth_month" not in vue
    assert "birthday_today" in vue


# ── La page est lisible dans les deux thèmes ────────────────────────────────

def test_la_page_applique_le_thème_mémorisé():
    """
    ⚠️ DÉFAUT RÉEL. Le gabarit a été extrait d'events.html AVANT la ligne qui charge `ui.js` :
    la page restait en clair pendant que le reste du dashboard était en sombre, et le contraste
    devenait imprévisible.
    """
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "/static/ui.js" in page, "le thème mémorisé n'est pas appliqué sur cette page"


def test_aucun_jeton_de_style_INVENTÉ():
    """
    ⚠️ LA CAUSE DU BLANC SUR BLANC. Le modal employait `var(--card)` et `var(--line)`, qui
    n'existent NULLE PART dans ce dépôt : le repli codé en dur donnait une carte blanche avec un
    texte clair hérité de la page en thème sombre. Les jetons réels sont `--bg-card`, `--border`,
    `--text`, `--bg-page`.

    Un jeton absent ne casse rien de visible au moment où on l'écrit — c'est précisément
    pourquoi il faut un test.
    """
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "var(--card" not in page
    assert "var(--line" not in page
    # Et le modal fixe SES couleurs plutôt que d'hériter : c'est l'héritage qui produisait
    # le texte invisible.
    assert "background:var(--bg-card);color:var(--text)" in page
    assert "background:var(--bg-page);color:var(--text)" in page


# ── Le NIF sur la carte ─────────────────────────────────────────────────────

def test_le_NIF_réel_du_compte_passe():
    """Jumeau de `apps/pos/lib/nif.ts` — même clé de contrôle, confirmée sur un NIF réel."""
    assert A._loyalty_clean_nif("517659328") == ("517659328", None)
    assert A._loyalty_clean_nif("517 659 328") == ("517659328", None)   # dicté, tapé avec espaces


def test_un_NIF_faux_est_REFUSÉ_et_non_stocké():
    """
    ⚠️ IL PART SUR UN DOCUMENT OPPOSABLE, ET À CHAQUE VISITE. Un NIF stocké faux se retrouverait
    sur toutes les factures suivantes sans que personne ne le retape — l'erreur se répète au lieu
    de se corriger.
    """
    for mauvais in ("517659327", "51765932", "01234567 8", "412345678", "abcdefghi"):
        assert A._loyalty_clean_nif(mauvais)[1] == "nif_invalid", mauvais


def test_un_NIF_vidé_efface_sans_refuser():
    assert A._loyalty_clean_nif("") == (None, None)
    assert A._loyalty_clean_nif(None) == (None, None)


def test_le_NIF_descend_jusqu_à_la_caisse_contrairement_au_téléphone():
    """
    ⚠️ LA DIFFÉRENCE EST L'USAGE. La caisse pré-remplit la facture avec le NIF — neuf chiffres
    que le client ne récite plus. Elle n'a aucun usage d'un téléphone, donc elle ne le reçoit
    pas : ce qu'elle ne reçoit pas ne peut pas s'afficher par mégarde.
    """
    row = {"number": 3, "first_name": "Maria", "drinks": 0, "rewards": 0,
           "fiscal_id": "517659328", "phone": "912345678"}
    vue = A._loyalty_public(row)
    assert vue["fiscal_id"] == "517659328"
    assert "phone" not in vue


def test_la_création_accepte_les_champs_facultatifs_sans_les_exiger():
    """
    L'inscription est le seul moment qui coûte du temps au CLIENT : chaque champ exige s'y
    ajoute. Aucun n'est obligatoire — mais un champ FAUX est refusé, car le garder serait pire.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_create)
    for champ in ("email", "fiscal_id", "birth_day"):
        assert champ in src, champ
    assert "first_name_required" in src   # le prénom, lui, reste exigé


# ── Les visites sans boisson ────────────────────────────────────────────────

def test_le_montant_est_en_CENTIMES_entiers():
    """
    ⚠️ Un montant en virgule flottante dérive à l'addition : sur des centaines de tickets, le
    cumul finit par ne plus tomber juste, et la dérive reste invisible jusqu'au jour où on la
    compare à la comptabilité.
    """
    assert A._loyalty_amount_cents(9.61) == 961
    assert A._loyalty_amount_cents("7.40") == 740
    # Les prix qui dérivent le plus : 0,07 et 2,675.
    assert A._loyalty_amount_cents(0.07) == 7
    assert A._loyalty_amount_cents(2.675) == 268


def test_un_montant_absent_ou_absurde_rend_None_et_jamais_0():
    """« 0 € dépensé » se lirait comme un client qui ne consomme rien, pas comme une absence."""
    for v in (None, "", 0, -5, "abc"):
        assert A._loyalty_amount_cents(v) is None, v


def test_une_visite_SANS_boisson_est_enregistrée():
    """
    ⚠️ LE POINT AVEUGLE CORRIGÉ. Un ticket sans boisson ne laissait aucune trace : ni passage, ni
    date, ni montant. Quelqu'un qui vient acheter un livre chaque semaine était invisible — et
    cet historique ne se reconstruit pas, chaque jour passé est perdu définitivement.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_credit)
    # Il n'y a plus de sortie anticipée à zéro boisson.
    assert "if n == 0:" not in src, "un ticket sans boisson ressort sans laisser de trace"
    assert "last_seen" in src
    assert "amount_cents" in src


def test_les_visites_sans_boisson_se_comptent_à_part():
    """Pour voir si la fidélité ne parle qu'aux buveurs de café."""
    events = [_ev(1, "2026-08-01", drinks=2), _ev(1, "2026-08-05", drinks=0)]
    for e in events:
        e["amount_cents"] = 1000
    s = A._loyalty_stats([{"number": 1}], events, _d(2026, 8, 18))
    assert s["visits"] == 2
    assert s["visits_without_drink"] == 1
    assert s["spent_eur"] == 20.0
    assert s["avg_ticket_eur"] == 10.0


def test_sans_montant_remonté_aucune_dépense_n_est_inventée():
    s = A._loyalty_stats([{"number": 1}], [_ev(1, "2026-08-01")], _d(2026, 8, 18))
    assert s["spent_eur"] is None
    assert s["avg_ticket_eur"] is None


# ── Les trois listes ────────────────────────────────────────────────────────

def _membre(n, drinks=0, last_seen=None, created="2026-01-01", **kw):
    return {"number": n, "first_name": f"M{n}", "drinks": drinks, "rewards": 0,
            "last_seen": last_seen, "created_at": created, **kw}


AUJ = date(2026, 8, 21)


def test_bientot_ne_retient_que_ceux_qui_y_sont_presque():
    """C'est la liste qui fait revenir : « encore une et elle est offerte », dit en servant."""
    r = A._loyalty_lists([_membre(1, drinks=9), _membre(2, drinks=8), _membre(3, drinks=5)], AUJ)
    assert [m["number"] for m in r["almost"]] == [1, 2]      # triés par ce qui manque
    assert r["almost"][0]["missing"] == 1


def test_une_recompense_DEJA_DUE_ne_figure_pas_dans_bientot():
    """
    Elle est due, pas proche — la mêler brouillerait la seule liste qui appelle une phrase.

    ⚠️ LE CAS QUI DISCRIMINE EST 19, PAS 10. À 10 ou 20, le reste vaut 10 et la borne les écarte
    déjà : la première version de ce test passait donc même sans la garde. À 19, une récompense
    est due ET il ne manque qu'une boisson pour la suivante — c'est là que « due » et « proche »
    se confondent si l'on n'y prend pas garde.
    """
    r = A._loyalty_lists([_membre(1, drinks=10), _membre(2, drinks=20), _membre(3, drinks=19)], AUJ)
    assert r["almost"] == []


def test_un_membre_JAMAIS_VU_n_est_pas_perdu_de_vue():
    """
    ⚠️ Il n'est jamais revenu, ce qui est un autre problème. Le compter comme un client qui
    décroche mêlerait deux populations et gonflerait l'alarme d'inscrits qui n'ont jamais rien
    acheté.
    """
    r = A._loyalty_lists([_membre(1, last_seen=None)], AUJ)
    assert r["lapsed"] == []


def test_perdus_de_vue_au_dela_du_seuil_et_tries_du_plus_ancien():
    r = A._loyalty_lists(
        [_membre(1, last_seen="2026-08-19"),   # 2 jours
         _membre(2, last_seen="2026-07-01"),   # 51 jours
         _membre(3, last_seen="2026-06-01")],  # 81 jours
        AUJ)
    assert [m["number"] for m in r["lapsed"]] == [3, 2]
    assert r["lapsed"][0]["days"] == 81


def test_les_nouveaux_de_la_semaine():
    r = A._loyalty_lists([_membre(1, created="2026-08-20"), _membre(2, created="2026-06-01")], AUJ)
    assert [m["number"] for m in r["new"]] == [1]


def test_les_fiches_supprimees_ne_figurent_dans_AUCUNE_liste():
    """Une fiche anonymisée n'est plus un membre : la relancer serait absurde."""
    supprime = _membre(1, drinks=9, last_seen="2026-01-01", created="2026-08-20",
                       status="deleted")
    r = A._loyalty_lists([supprime], AUJ)
    assert r["almost"] == [] and r["lapsed"] == [] and r["new"] == []


def test_une_date_illisible_n_invente_rien():
    """Elle ne doit ni faire planter la page, ni classer quelqu'un au hasard."""
    r = A._loyalty_lists([_membre(1, last_seen="pas-une-date", created="pas-une-date")], AUJ)
    assert r["lapsed"] == [] and r["new"] == []


def test_les_listes_sont_sous_le_LOGIN():
    import inspect
    assert "_current_role()" in inspect.getsource(A.api_loyalty_lists)


def test_les_trois_listes_sont_affichees_et_expliquees():
    """
    ⚠️ UNE LISTE VIDE DOIT DIRE POURQUOI. Un cadre vide se lit « c'est cassé » — surtout au
    démarrage du programme, où les trois le seront.
    """
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "/api/loyalty/lists" in page
    assert "Perdus de vue" in page and "Nouveaux" in page
    assert "Personne pour l" in page          # l'état vide est expliqué
    # Les prénoms sont posés comme TEXTE, jamais comme HTML : ils viennent d'une saisie libre.
    assert 'class="nom"' in page and "textContent = m.first_name" in page


# ── Fusionner deux cartes ───────────────────────────────────────────────────

def test_la_fusion_ADDITIONNE_les_soldes():
    """
    ⚠️ LE DÉFAUT QU'ELLE RÉPARE. Quelqu'un oublie son numéro, on cherche par prénom, on ne trouve
    pas — orthographe, diminutif, prénom courant — et une seconde carte est créée. Les points se
    répartissent sur deux numéros et le client n'atteint JAMAIS dix. Les deux cartes sont
    valides, les deux soldes progressent, et c'est le client le plus assidu qui en fait les
    frais. Rien ne le signale.
    """
    source = {"number": 12, "drinks": 6, "rewards": 1, "spent_cents": 3000}
    cible = {"number": 3, "first_name": "Maria", "drinks": 5, "rewards": 2, "spent_cents": 4500}
    f = A._loyalty_merge_payload(source, cible)
    assert f["drinks"] == 11        # et non 5 ou 6 : le client a bien bu onze fois
    assert f["rewards"] == 3
    assert f["spent_cents"] == 7500


def test_un_contact_PRESENT_n_est_jamais_ecrase():
    """
    On ne peut pas savoir lequel des deux est le bon, et le plus récent n'est pas forcément le
    meilleur. Un champ VIDE, lui, se remplit : c'est du gain sans risque.
    """
    source = {"number": 12, "phone": "911111111", "email": "vieux@x.co", "country": "Brasil"}
    cible = {"number": 3, "first_name": "Maria", "phone": "922222222"}
    f = A._loyalty_merge_payload(source, cible)
    assert f["phone"] == "922222222"     # conservé
    assert f["email"] == "vieux@x.co"    # récupéré, la cible n'en avait pas
    assert f["country"] == "Brasil"


def test_la_fusion_garde_la_PREMIERE_inscription_et_le_DERNIER_passage():
    """Le client est là depuis la première, et il est venu la dernière fois qu'il est venu."""
    source = {"number": 12, "created_at": "2026-05-02", "last_seen": "2026-08-20"}
    cible = {"number": 3, "first_name": "M", "created_at": "2026-07-01", "last_seen": "2026-08-01"}
    f = A._loyalty_merge_payload(source, cible)
    assert f["created_at"] == "2026-05-02"
    assert f["last_seen"] == "2026-08-20"


def test_une_carte_FUSIONNEE_n_est_plus_un_membre():
    """
    ⚠️ Son numéro reste réservé — quelqu'un peut encore le réciter pendant des mois — mais une
    recherche dessus doit échouer proprement au lieu de tomber sur un compte vide.
    """
    assert A._loyalty_is_deleted({"status": "merged"}) is True
    assert A._loyalty_is_deleted({"status": "deleted"}) is True
    assert A._loyalty_is_deleted({"status": None}) is False


def test_la_fusion_exige_le_login_un_motif_et_deux_cartes_distinctes():
    import inspect
    src = inspect.getsource(A.api_loyalty_merge)
    assert "_current_role()" in src
    assert "_loyalty_authorized" not in src, "le jeton de la caisse ne doit PAS suffire"
    assert "reason_required" in src
    assert "same_card" in src, "fusionner une carte avec elle-même doublerait son solde"
    assert "member_deleted" in src


def test_l_historique_SUIT_les_points():
    """
    ⚠️ Le laisser sur la fiche anonymisée le rendrait illisible : « j'avais neuf cafés » ne se
    tranche qu'avec les mouvements sous les yeux.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_merge)
    assert '_supa_patch("loyalty_events"' in src


def test_la_fusion_est_atteignable_depuis_la_fiche():
    """Une fonction qu'aucun clic n'atteint n'existe pas."""
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "/api/loyalty/merge" in page
    assert "f-merge" in page
    # La confirmation DIT ce qui est transféré et ce qu'il advient du doublon.
    assert "reste r\\u00e9serv\\u00e9" in page


# ── Ce que les membres achètent ─────────────────────────────────────────────

def test_on_garde_le_titre_et_la_quantite_rien_d_autre():
    """
    ⚠️ Ni prix, ni identifiant : le prix change et se relit sur le document, l'identifiant ne dit
    rien à un humain. Ce qu'on veut savoir, c'est « quoi », pas « combien ça coûtait ce jour-là ».
    """
    r = A._loyalty_clean_items([{"title": " Flat White ", "qty": 2, "price": 4.0, "id": 7}])
    assert r == [{"t": "Flat White", "q": 2}]


def test_une_ligne_absurde_est_ecartee_sans_jeter_le_reste():
    r = A._loyalty_clean_items([{"title": "", "qty": 1}, {"title": "Bica", "qty": 0},
                                {"title": "Chá", "qty": "x"}, {"title": "Cold Brew", "qty": 1}])
    assert r == [{"t": "Cold Brew", "q": 1}]


def test_aucune_ligne_rend_None_et_pas_une_liste_vide():
    """Une absence de lignes n'est pas un ticket vide : c'est une requête qui n'en portait pas."""
    assert A._loyalty_clean_items([]) is None
    assert A._loyalty_clean_items(None) is None


def test_le_nombre_de_lignes_conservees_est_borne():
    """Une requête anormale ne doit pas faire grossir la base sans limite."""
    beaucoup = [{"title": f"P{i}", "qty": 1} for i in range(200)]
    assert len(A._loyalty_clean_items(beaucoup)) == A.LOYALTY_MAX_ITEMS


def test_le_palmares_compte_les_QUANTITES_pas_les_tickets():
    """
    ⚠️ Quelqu'un qui prend deux cafés à chaque fois en boit deux. Dire « une visite avec du
    café » effacerait la moitié de sa consommation.
    """
    events = [{"items": [{"t": "Flat White", "q": 2}]},
              {"items": [{"t": "Flat White", "q": 1}, {"t": "Bica", "q": 1}]}]
    assert A._loyalty_top_products(events) == [{"title": "Flat White", "qty": 3},
                                               {"title": "Bica", "qty": 1}]


def test_les_visites_SANS_lignes_ne_comptent_pas_pour_zero():
    """
    Les visites d'avant cette collecte n'en portent pas. Les faire peser à zéro ferait croire à
    des clients qui ne prennent rien.
    """
    events = [{"items": None}, {"kind": "credit"}, {"items": [{"t": "Bica", "q": 1}]}]
    assert A._loyalty_top_products(events) == [{"title": "Bica", "qty": 1}]


def test_le_palmares_est_borne_et_deterministe_a_egalite():
    """Un classement qui permute d'un rendu à l'autre n'inspire aucune confiance."""
    events = [{"items": [{"t": "B", "q": 1}, {"t": "A", "q": 1}]}]
    assert [p["title"] for p in A._loyalty_top_products(events)] == ["A", "B"]
    gros = [{"items": [{"t": f"P{i}", "q": 100 - i} for i in range(30)]}]
    assert len(A._loyalty_top_products(gros, 8)) == 8


def test_les_lignes_sont_BRANCHEES_sur_le_credit():
    """
    ⚠️ VÉRIFIE LE BRANCHEMENT, PAS LA RÈGLE. Les lignes remontaient déjà à chaque encaissement et
    étaient JETÉES : la règle de nettoyage peut être parfaite et personne pour l'appeler. Et
    comme cette donnée ne se reconstruit pas, un débranchement se paierait en jours perdus avant
    que quiconque le remarque.
    """
    import inspect
    src = inspect.getsource(A.api_loyalty_credit)
    assert '"items": _loyalty_clean_items(data.get("items"))' in src


def test_la_fiche_et_les_mesures_rendent_le_palmares():
    import inspect
    assert "_loyalty_top_products(events)" in inspect.getsource(A.api_loyalty_card)
    assert "_loyalty_top_products(events, 10)" in inspect.getsource(A.api_loyalty_stats)


# ── Les chiffres d'un client ────────────────────────────────────────────────

def _c(jour, drinks=1, cents=None):
    e = {"kind": "credit", "drinks": drinks, "at": f"{jour}T10:00:00+00:00"}
    if cents is not None:
        e["amount_cents"] = cents
    return e


def test_les_visites_se_comptent_par_JOUR():
    """Deux tickets d'affilée, c'est une visite : les additionner gonflerait l'assiduité."""
    st = A._loyalty_member_stats({}, [_c("2026-08-01"), _c("2026-08-01"), _c("2026-08-05")],
                                 date(2026, 8, 21))
    assert st["visits"] == 2
    assert st["tickets"] == 3


def test_aucun_zero_invente():
    """
    ⚠️ Un client sans montant enregistré n'a pas « dépensé 0 € » — les visites d'avant la
    collecte n'en portent pas. Un tiret dit la vérité; un zéro se lirait comme une mesure.
    """
    st = A._loyalty_member_stats({}, [_c("2026-08-01")], date(2026, 8, 21))
    assert st["spent_eur"] is None
    assert st["avg_ticket_eur"] is None
    st_vide = A._loyalty_member_stats({}, [], date(2026, 8, 21))
    assert st_vide["visits"] is None and st_vide["tickets"] is None


def test_la_moyenne_ne_porte_que_sur_les_tickets_CHIFFRES():
    """Diviser par tous les tickets ferait chuter le panier moyen à mesure qu'on remonte."""
    st = A._loyalty_member_stats({}, [_c("2026-08-01", cents=1000), _c("2026-08-02")],
                                 date(2026, 8, 21))
    assert st["spent_eur"] == 10.0
    assert st["avg_ticket_eur"] == 10.0


def test_les_delais_se_calculent_et_une_date_illisible_ne_ment_pas():
    st = A._loyalty_member_stats({"last_seen": "2026-08-11", "created_at": "2026-06-21"},
                                 [], date(2026, 8, 21))
    assert st["days_since_last"] == 10
    assert st["member_since_days"] == 61
    st2 = A._loyalty_member_stats({"last_seen": "n'importe quoi"}, [], date(2026, 8, 21))
    assert st2["days_since_last"] is None


def test_la_fiche_est_organisee_en_deux_onglets():
    """
    ⚠️ ELLE MELAIT UN FORMULAIRE D'EDITION ET DE LA LECTURE, empilés : on venait pour comprendre
    un client et on tombait sur des champs de saisie. « Activité » est l'onglet par défaut — on
    vient lire neuf fois sur dix, corriger est l'exception.
    """
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "onglet-act" in page and "onglet-fic" in page
    assert "montrer('act');" in page, "l'activité doit être l'onglet par défaut"
    # Les trois actions restent atteignables depuis l'onglet Fiche.
    for bouton in ("f-save", "f-merge", "f-del"):
        assert bouton in page, bouton


def test_les_chiffres_de_la_fiche_affichent_un_TIRET_et_non_un_zero():
    """Un zéro se lirait comme une mesure ; un tiret dit qu'on ne sait pas."""
    import pathlib
    page = pathlib.Path("templates/loyalty.html").read_text()
    assert "\\u2014" in page
    assert "var nf = function(v, suf)" in page
