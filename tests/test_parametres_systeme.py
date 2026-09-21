"""
L'ONGLET SYSTÈME — l'inventaire de ce qui se règle ailleurs.

⚠️ C'EST LA RÉPONSE À « NE RIEN LAISSER AU HASARD », ET ELLE EST EN LECTURE SEULE. Rendre tout
éditable créerait des mensonges silencieux : les mots qui reconnaissent un paiement carte, les
bornes de validation, la TVA du business plan sont des règles techniques dont l'édition à
l'écran ferait diverger deux endroits. Ce qu'il faut n'est pas de pouvoir les changer ici —
c'est de SAVOIR qu'ils existent, et où ils se changent.
"""

import json
import os
import re

import pytest

import app as flask_app

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GABARIT = open(os.path.join(RACINE, "templates", "parametres.html"), encoding="utf-8").read()


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


# ── Ce qui ne doit jamais traverser ──────────────────────────────────────────────────────────

def test_aucune_valeur_de_secret_ne_traverse(admin, monkeypatch):
    """
    ⚠️ CET ÉCRAN SE PHOTOGRAPHIE. « Configuré » ou « absent » suffit à diagnostiquer ; la valeur
    ne sert à rien à l'écran et ne se reprend jamais une fois partie.
    """
    monkeypatch.setenv("DASHBOARD_PASSWORD", "mon-mot-de-passe-secret")
    monkeypatch.setenv("SUPABASE_KEY", "cle-supabase-tres-secrete")
    brut = json.dumps(admin.get("/api/parametres/systeme").get_json())
    assert "mon-mot-de-passe-secret" not in brut
    assert "cle-supabase-tres-secrete" not in brut


def test_la_presence_dun_secret_est_bien_rapportee(admin, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "x")
    monkeypatch.delenv("ACCOUNTANT_TOKEN", raising=False)
    d = admin.get("/api/parametres/systeme").get_json()
    par_nom = {s["nom"]: s["configure"] for s in d["secrets"]}
    assert par_nom["CRON_SECRET"] is True
    assert par_nom["ACCOUNTANT_TOKEN"] is False


def test_un_espace_ne_compte_pas_comme_configure(admin, monkeypatch):
    """Une variable posée à «  » dans Vercel est une variable oubliée, pas une variable réglée."""
    monkeypatch.setenv("CRON_SECRET", "   ")
    d = admin.get("/api/parametres/systeme").get_json()
    assert {s["nom"]: s["configure"] for s in d["secrets"]}["CRON_SECRET"] is False


def test_chaque_secret_dit_a_quoi_il_sert_et_ou_il_se_change(admin):
    """
    ⚠️ UNE LISTE DE NOMS DE VARIABLES N'AIDE PERSONNE. « MESA_CAMPAIGN_SECRET : absent » ne dit
    ni ce qui ne marchera pas, ni où aller.
    """
    for s in admin.get("/api/parametres/systeme").get_json()["secrets"]:
        assert s["quoi"] and len(s["quoi"]) > 10, s["nom"]
        assert s["ou"], s["nom"]


# ── Ce qui est mesuré, pas réglé ─────────────────────────────────────────────────────────────

def test_le_taux_de_frais_dit_sur_quel_mois_il_est_calibre(admin, monkeypatch):
    """
    ⚠️ UN TAUX SANS SA DATE VIEILLIT SANS QUE RIEN NE LE SIGNALE. « 1,44 % » et « 1,44 %,
    calibré sur juillet » ne se lisent pas pareil six mois plus tard.
    """
    monkeypatch.setattr(flask_app, "_load_revolut_days",
                        lambda: {"2026-07-01": {"gross": 1000.0, "fees": 20.0}})
    m = admin.get("/api/parametres/systeme").get_json()["mesure"]
    assert m["taux_calibre_sur"] == "2026-07"
    assert m["taux_frais_pct"] == pytest.approx(2.0)


def test_sans_releve_le_taux_est_annonce_comme_un_repli(admin, monkeypatch):
    monkeypatch.setattr(flask_app, "_load_revolut_days", lambda: {})
    m = admin.get("/api/parametres/systeme").get_json()["mesure"]
    assert m["taux_calibre_sur"] is None


def test_une_panne_de_releve_ne_fait_pas_tomber_linventaire(admin, monkeypatch):
    """L'inventaire est ce qu'on vient consulter QUAND quelque chose ne marche pas."""
    def casse():
        raise RuntimeError("Supabase muet")

    monkeypatch.setattr(flask_app, "_load_revolut_days", casse)
    r = admin.get("/api/parametres/systeme")
    assert r.status_code == 200
    assert r.get_json()["mesure"]["taux_frais_pct"] > 0


# ── L'inventaire est complet ─────────────────────────────────────────────────────────────────

def test_les_familles_attendues_sont_toutes_la(admin):
    d = admin.get("/api/parametres/systeme").get_json()
    for famille in ("secrets", "mesure", "calendrier", "hypotheses", "fidelite",
                    "paiements", "places"):
        assert famille in d, famille


def test_les_mots_qui_classent_les_paiements_sont_montres(admin):
    """
    ⚠️ MAL RÉGLÉS, ILS PRODUISENT UN ÉCART DE CAISSE PERMANENT dont on ne trouve jamais la
    cause — c'est arrivé le 21/09 avec « Cartão de Crédito ». Les montrer, c'est permettre de
    reconnaître le symptôme.
    """
    p = admin.get("/api/parametres/systeme").get_json()["paiements"]
    assert "cartao" in p["mots_carte"]
    assert "dinheiro" in p["mots_especes"]
    assert p["fenetre_rapprochement_min"] > 0


def test_le_calendrier_montre_le_diviseur_du_compte_de_resultat(admin):
    c = admin.get("/api/parametres/systeme").get_json()["calendrier"]
    assert c["jours_ouverts"] and "mardi" not in c["jours_ouverts"]
    assert c["jours_ouverts_mois"] > 0


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_voit_linventaire(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().get("/api/parametres/systeme")
    assert r.status_code in (401, 403)


# ── L'écran ──────────────────────────────────────────────────────────────────────────────────

def test_les_trois_onglets_existent_et_sont_disjoints():
    for o in ("acces", "economie", "systeme"):
        assert f'id="pa-{o}"' in GABARIT
    pos = [GABARIT.index(f'id="pa-{o}"') for o in ("acces", "economie", "systeme")]
    assert pos == sorted(pos), "les panneaux s'imbriquent"


def test_le_panneau_masque_lest_vraiment():
    """⚠️ Le bogue de la barre blanche du 19/09 : une règle d'affichage écrasait `hidden`."""
    # ⚠️ LA RÈGLE VIT DÉSORMAIS DANS LA FEUILLE COMMUNE, avec la barre d'onglets partagée.
    import os
    commun = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "static", "style.css"), encoding="utf-8").read()
    assert ".pa-panneau[hidden] { display: none !important; }" in commun


def test_longlet_economie_renvoie_et_ne_duplique_pas():
    """
    ⚠️ LA SIMULATION DES RÉGLAGES FIDÉLITÉ A BESOIN DES 2 500 VISITES déjà chargées par
    /loyalty. La refaire ici donnerait deux écrans qui écrivent la même ligne — et un jour deux
    réponses différentes à la même question.
    """
    i = GABARIT.index('id="pa-economie"')
    bloc = GABARIT[i:GABARIT.index('id="pa-systeme"')]
    assert 'href="/charges"' in bloc
    assert 'href="/loyalty#reglages"' in bloc
    assert "<input" not in bloc, "un éditeur a été dupliqué dans l'onglet Économie"


def test_lavertissement_sur_les_charges_ne_survit_pas_a_sa_correction():
    """
    ⚠️ CET ÉCRAN METTAIT EN GARDE CONTRE UN DANGER CORRIGÉ LE 21/09/2026 : « modifier un montant
    réécrit la marge des mois passés ». C'est faux depuis qu'un changement porte une date d'effet.
    Un avertissement qui décrit un péril disparu apprend à ignorer les avertissements de l'écran
    — y compris ceux qui disent encore vrai.

    ⚠️ ET LE DÉCOUPAGE SE FAIT SUR L'ONGLET SUIVANT, QUEL QU'IL SOIT. La version d'avant coupait
    à `pa-systeme` ; l'onglet Menu s'est glissé entre les deux, et la tranche a silencieusement
    doublé de taille — le test cherchait alors ses mots dans un bloc qui n'était plus le sien.
    """
    i = GABARIT.index('id="pa-economie"')
    fin = min(j for j in (GABARIT.find('id="pa-menu"', i), GABARIT.find('id="pa-systeme"', i))
              if j > 0)
    bloc = GABARIT[i:fin]
    assert "réécrit" not in bloc and "r&eacute;&eacute;crit" not in bloc
    assert "date d'effet" in bloc, "l'écran ne dit pas ce qui protège désormais les mois passés"


def test_linventaire_ne_se_charge_quen_ouvrant_son_onglet():
    """Une page de réglages qui appelle tout au chargement est une page qu'on n'ouvre plus."""
    i = GABARIT.index("function activer(")
    assert "!E('sys').dataset.charge" in GABARIT[i:i + 700]


def test_longlet_est_dans_ladresse():
    assert "location.hash" in GABARIT and "hashchange" in GABARIT
