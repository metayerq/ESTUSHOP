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
