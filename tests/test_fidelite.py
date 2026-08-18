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
