"""
LES COMPTES DU PROGRAMME, VUS DU BUREAU.

Ces tests ne vérifient pas que le code tourne : ils exigent que chaque règle de regroupement
reste vraie. Un client qui a deux cartes est UNE personne ; une carte jamais liée est quand
même un client ; et un taux de liaison mesuré sur les passants ne veut rien dire.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from programme import (  # noqa: E402
    REGULAR_AFTER_VISITS,
    build_accounts,
    programme_summary,
)

SEUIL = 50
COUT_BOISSON = 70  # centimes de matière — pas le prix de carte
MAINTENANT = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)


def v(fp, jour, cents):
    return {"fp": fp, "ts": f"2026-{jour}T10:00:00+00:00", "amount_cents": cents}


def rec(fp, jour, points=SEUIL):
    return {"fp": fp, "ts": f"2026-{jour}T10:00:00+00:00", "points_spent": points}


def comptes(visits=(), rewards=(), links=(), customers=(), now=MAINTENANT):
    return build_accounts(list(visits), list(rewards), list(links), list(customers), SEUIL, now)


def par_cle(cs):
    return {c["key"]: c for c in cs}


# ─── le regroupement ──────────────────────────────────────────────────────────────────────────

def test_deux_cartes_un_seul_telephone_font_un_seul_client():
    """
    ⚠️ LA RAISON D'ÊTRE DU NUMÉRO DE TÉLÉPHONE. Quelqu'un qui paie tantôt avec sa carte, tantôt
    avec Apple Pay, produit deux empreintes différentes. Le compter deux fois lui ferait
    atteindre la récompense deux fois plus lentement — la punition exacte de celui qui paie
    comme il veut.
    """
    cs = par_cle(comptes(
        visits=[v("fpA", "08-01", 3000), v("fpB", "08-10", 3000)],
        links=[{"fp": "fpA", "phone": "+351911"}, {"fp": "fpB", "phone": "+351911"}],
        customers=[{"phone": "+351911", "name": "Ana", "token": "t1"}],
    ))
    assert list(cs) == ["phone:+351911"]
    c = cs["phone:+351911"]
    assert c["state"]["balance_points"] == 60
    assert c["fps"] == ["fpA", "fpB"]
    assert c["name"] == "Ana"


def test_une_recompense_sur_une_carte_consomme_les_points_de_l_autre():
    """
    ⚠️ LE CAS QUI PROUVE QUE LE REGROUPEMENT SE FAIT AVANT LE CALCUL, ET NON APRÈS. Additionner
    deux soldes calculés séparément laisserait la récompense prise sur une carte sans effet sur
    les points de l'autre : le client serait offert deux fois avec les mêmes euros.
    """
    cs = par_cle(comptes(
        visits=[v("fpA", "03-01", 3000), v("fpB", "03-10", 3000)],
        rewards=[rec("fpA", "04-01")],
        links=[{"fp": "fpA", "phone": "+351911"}, {"fp": "fpB", "phone": "+351911"}],
        customers=[{"phone": "+351911"}],
    ))
    assert cs["phone:+351911"]["state"]["balance_points"] == 10
    assert cs["phone:+351911"]["state"]["spent_points"] == 50


def test_une_carte_jamais_liee_est_quand_meme_un_client():
    """
    ⚠️ ET C'EST LA MAJORITÉ D'ENTRE EUX. Ne lister que les inscrits ferait croire que le
    programme touche trente personnes alors qu'il en voit des centaines — et masquerait
    exactement la population qu'il faut convaincre de donner son numéro.
    """
    cs = par_cle(comptes(visits=[v("fpX", "09-01", 1200)]))
    assert list(cs) == ["card:fpX"]
    assert cs["card:fpX"]["kind"] == "card"
    assert cs["card:fpX"]["phone"] is None
    assert cs["card:fpX"]["state"]["balance_points"] == 12


def test_un_inscrit_qui_n_a_encore_rien_paye_existe():
    """
    Il a donné son numéro et reçu son SMS de bienvenue. Ne pas le lister le rendrait
    introuvable le jour où il demande au comptoir où en est son compte.
    """
    cs = par_cle(comptes(
        links=[{"fp": "fpN", "phone": "+351922"}],
        customers=[{"phone": "+351922", "name": "Rui"}],
    ))
    c = cs["phone:+351922"]
    assert c["name"] == "Rui"
    assert c["state"]["visits"] == 0
    assert c["days_since_last"] is None


def test_une_carte_liee_a_un_telephone_sans_fiche_est_signalee_pas_perdue():
    """
    ⚠️ UNE INCOHÉRENCE DE BASE NE DOIT PAS MANGER DES POINTS. Migration à moitié passée,
    suppression partielle : le compte existe, il est simplement sans nom — et le drapeau est
    la seule chance qu'il a d'être réparé.
    """
    cs = par_cle(comptes(
        visits=[v("fpO", "09-01", 5000)],
        links=[{"fp": "fpO", "phone": "+351933"}],
        customers=[],
    ))
    c = cs["phone:+351933"]
    assert c["orphan"] is True
    assert c["state"]["balance_points"] == 50


def test_les_comptes_sont_tries_du_plus_recent_au_plus_ancien():
    cs = comptes(visits=[v("vieux", "01-05", 1000), v("frais", "09-15", 1000)])
    assert [c["key"] for c in cs] == ["card:frais", "card:vieux"]


def test_celui_qui_n_est_jamais_venu_passe_en_dernier():
    cs = comptes(
        visits=[v("fpV", "01-05", 1000)],
        links=[{"fp": "fpZ", "phone": "+351944"}],
        customers=[{"phone": "+351944"}],
    )
    assert cs[-1]["key"] == "phone:+351944"


# ─── les habitués et ceux qui ne reviennent pas ───────────────────────────────────────────────

def test_un_habitue_absent_au_dela_de_son_rythme_est_a_risque():
    """Quatre passages hebdomadaires puis plus rien : seuil 21 jours, absent depuis bien plus."""
    cs = par_cle(comptes(visits=[
        v("fpR", "06-01", 1000), v("fpR", "06-08", 1000),
        v("fpR", "06-15", 1000), v("fpR", "06-22", 1000),
    ]))
    c = cs["card:fpR"]
    assert c["regular"] is True
    assert c["absence_threshold_days"] == 21
    assert c["at_risk"] is True


def test_un_habitue_dans_son_rythme_n_est_pas_a_risque():
    cs = par_cle(comptes(visits=[
        v("fpR", "08-25", 1000), v("fpR", "09-01", 1000),
        v("fpR", "09-08", 1000), v("fpR", "09-15", 1000),
    ]))
    assert cs["card:fpR"]["at_risk"] is False


def test_un_client_de_passage_n_est_jamais_a_risque():
    """
    ⚠️ ON NE PEUT PAS CONSTATER L'INTERRUPTION D'UNE HABITUDE QUI N'EXISTE PAS. Sans ce garde,
    la liste se remplirait de touristes venus deux fois en avril, et on cesserait de la lire.
    """
    cs = par_cle(comptes(visits=[v("fpT", "04-01", 1000), v("fpT", "04-03", 1000)]))
    c = cs["card:fpT"]
    assert c["state"]["visits"] < REGULAR_AFTER_VISITS
    assert c["at_risk"] is False


def test_le_client_quotidien_n_est_pas_signale_apres_une_fermeture():
    """
    ⚠️ LE CAFÉ FERME MARDI ET MERCREDI. Trois fois un jour d'écart ferait un seuil de 3 jours,
    et chaque week-end prolongé fabriquerait un faux départ. Le plancher à sept jours est ce qui
    empêche la liste de devenir du bruit.
    """
    cs = par_cle(comptes(visits=[
        v("fpQ", "09-14", 800), v("fpQ", "09-15", 800),
        v("fpQ", "09-16", 800), v("fpQ", "09-17", 800),
    ], now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)))
    c = cs["card:fpQ"]
    assert c["absence_threshold_days"] == 7
    assert c["at_risk"] is False


# ─── les chiffres du tableau de bord ──────────────────────────────────────────────────────────

def test_le_taux_de_liaison_ignore_les_passants():
    """
    ⚠️ UN TOURISTE QUI PAIE UNE FOIS N'AVAIT AUCUNE RAISON DE DONNER SON NUMÉRO. Le compter au
    dénominateur ferait baisser le taux à chaque inconnu qui entre, et la mesure ne dirait plus
    rien de ce qu'on fait au comptoir.
    """
    s = programme_summary(comptes(
        visits=[
            v("fpA", "08-01", 1000), v("fpA", "08-08", 1000),   # revenant, lié
            v("fpB", "08-02", 1000), v("fpB", "08-09", 1000),   # revenant, pas lié
            v("fpC", "08-03", 1000),                            # passant unique
            v("fpD", "08-04", 1000),                            # passant unique
        ],
        links=[{"fp": "fpA", "phone": "+351911"}],
        customers=[{"phone": "+351911"}],
    ), SEUIL, COUT_BOISSON)
    assert s["returning"] == 2
    assert s["returning_linked"] == 1
    assert s["link_rate_pct"] == 50.0
    assert s["accounts"] == 4


def test_sans_aucun_revenant_le_taux_est_absent_et_non_nul():
    """Un taux de 0 % se lit comme un échec ; l'absence de mesure se lit comme ce qu'elle est."""
    s = programme_summary(comptes(visits=[v("fpC", "08-03", 1000)]), SEUIL, COUT_BOISSON)
    assert s["link_rate_pct"] is None


def test_le_passif_est_valorise_en_matiere_et_non_au_prix_de_carte():
    """
    ⚠️ VALORISER LA DETTE AU PRIX DE VENTE LA MULTIPLIERAIT PAR CINQ et ferait paraître
    effrayant un programme qui coûte quelques dizaines d'euros par mois. Cent points en
    circulation, c'est deux boissons, c'est 1,40 € de matière.
    """
    s = programme_summary(comptes(visits=[v("fpA", "09-01", 10000)]), SEUIL, COUT_BOISSON)
    assert s["points_outstanding"] == 100
    assert s["liability_cents"] == 2 * COUT_BOISSON


def test_le_taux_de_consommation_compte_les_points_perimes_comme_emis():
    """
    ⚠️ SINON LE PROGRAMME PARAÎT PARFAIT. Des points qui meurent sans être bus sont des points
    qu'on a promis et qui n'ont fait plaisir à personne : les retirer du dénominateur ferait
    monter le taux à mesure que le programme échoue. Ici cent points ont été émis, cinquante
    bus, cinquante enterrés — c'est 50 %, pas 100 %.
    """
    s = programme_summary(comptes(
        visits=[
            {"fp": "fpA", "ts": "2025-08-01T10:00:00+00:00", "amount_cents": 5000},
            v("fpA", "09-01", 5000),
        ],
        rewards=[rec("fpA", "09-05")],
    ), SEUIL, COUT_BOISSON)
    assert s["points_spent"] == 50
    assert s["points_expired"] == 50
    assert s["points_outstanding"] == 0
    assert s["points_issued"] == 100
    assert s["redemption_rate_pct"] == 50.0


def test_pile_a_son_rythme_n_est_pas_un_depart():
    """
    ⚠️ LA FRONTIÈRE EST OUVERTE, ET C'EST LE BON SENS. Un client hebdomadaire dont le seuil est
    de 21 jours et qui revient le 21e jour n'est pas parti : il est à l'heure. Signaler quelqu'un
    au moment exact où il respecte encore son rythme, c'est relancer un client fidèle pour rien.
    """
    cs = par_cle(comptes(
        visits=[
            v("fpP", "08-04", 1000), v("fpP", "08-11", 1000),
            v("fpP", "08-18", 1000), v("fpP", "08-25", 1000),
        ],
        now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    ))
    c = cs["card:fpP"]
    assert c["absence_threshold_days"] == 21
    assert c["days_since_last"] == 21
    assert c["at_risk"] is False


def test_bientot_recompenses_exclut_ceux_qui_le_sont_deja():
    """« Bientôt » est une liste d'attente, pas un palmarès : une boisson due appelle une autre
    action — la servir."""
    s = programme_summary(comptes(visits=[
        v("fpProche", "09-01", 4500),   # 45 points : proche
        v("fpDu", "09-01", 6000),       # 60 points : une récompense est due
        v("fpLoin", "09-01", 1000),     # 10 points : rien à dire
    ]), SEUIL, COUT_BOISSON)
    assert [c["key"] for c in s["near_reward"]] == ["card:fpProche"]
    assert s["rewards_due_now"] == 1


def test_les_desabonnes_sont_comptes():
    s = programme_summary(comptes(
        visits=[v("fpA", "09-01", 1000)],
        links=[{"fp": "fpA", "phone": "+351911"}],
        customers=[{"phone": "+351911", "opted_out_at": "2026-09-02T10:00:00+00:00"}],
    ), SEUIL, COUT_BOISSON)
    assert s["opted_out"] == 1


def test_un_programme_vide_ne_divise_par_rien():
    s = programme_summary([], SEUIL, COUT_BOISSON)
    assert s["accounts"] == 0
    assert s["link_rate_pct"] is None
    assert s["redemption_rate_pct"] is None
    assert s["liability_cents"] == 0


# ─── le cumul brut, sans aucune pondération ───────────────────────────────────────────────────

def test_le_cumul_ignore_la_date_de_lancement():
    """
    ⚠️ LE SOLDE ET LE CUMUL RÉPONDENT À DEUX QUESTIONS DIFFÉRENTES. Le solde dit « que lui
    dois-je ? » ; le cumul dit « qui est-ce ? ». Après le lancement, un habitué de six mois
    tombe à 50 points de solde — sans le cumul, il ressemble à quelqu'un qui vient d'arriver, et
    on le traite comme tel.
    """
    cs = par_cle(build_accounts(
        [{"fp": "fpA", "ts": "2026-05-01T10:00:00+00:00", "amount_cents": 140000},
         {"fp": "fpA", "ts": "2026-09-25T10:00:00+00:00", "amount_cents": 1000}],
        [], [], [], SEUIL, datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
        options={"start_date": "2026-09-22", "legacy_rate_pct": 10, "legacy_cap_points": 50},
    ))
    c = cs["card:fpA"]
    assert c["state"]["balance_points"] == 60      # 50 de crédit + 10 du 25 septembre
    assert c["lifetime_points"] == 1410            # tout, sans pondération
    assert c["lifetime_cents"] == 141000


def test_le_cumul_ignore_l_expiration_et_les_boissons_offertes():
    """Ce qui a été dépensé l'a été. Ni le calendrier ni une récompense ne l'effacent."""
    cs = par_cle(build_accounts(
        [{"fp": "fpB", "ts": "2024-01-01T10:00:00+00:00", "amount_cents": 5000},
         {"fp": "fpB", "ts": "2026-09-01T10:00:00+00:00", "amount_cents": 6000}],
        [{"fp": "fpB", "ts": "2026-09-02T10:00:00+00:00", "points_spent": 50}],
        [], [], SEUIL, MAINTENANT,
    ))
    c = cs["card:fpB"]
    assert c["state"]["expired_points"] == 50      # le lot de 2024 est mort
    assert c["state"]["spent_points"] == 50        # une boisson offerte
    assert c["state"]["balance_points"] == 10
    assert c["lifetime_points"] == 110             # 50 + 60, intacts


def test_le_cumul_additionne_toutes_les_cartes_du_client():
    cs = par_cle(comptes(
        visits=[v("fpA", "08-01", 3000), v("fpB", "08-10", 4500)],
        links=[{"fp": "fpA", "phone": "+351911"}, {"fp": "fpB", "phone": "+351911"}],
        customers=[{"phone": "+351911"}],
    ))
    assert cs["phone:+351911"]["lifetime_points"] == 75


def test_un_montant_absurde_n_entre_pas_dans_le_cumul():
    """Un remboursement ne doit pas gonfler — ni amputer — la valeur d'un client."""
    cs = par_cle(comptes(visits=[
        v("fpC", "09-01", 5000), v("fpC", "09-02", -2000), v("fpC", "09-03", 0),
    ]))
    assert cs["card:fpC"]["lifetime_points"] == 50
