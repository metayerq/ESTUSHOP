"""
CE À QUOI LES GENS ONT DIT OUI.

⚠️ CE FICHIER GARDE UNE PREUVE, PAS UNE FONCTIONNALITÉ. Le consentement est oral : on demande un
numéro au comptoir, il n'y a pas d'écran client à l'inscription. La seule chose qui rende ce oui
démontrable est que la phrase PRONONCÉE et la portée ENREGISTRÉE sortent du même réglage. Une
divergence entre les deux ne casserait rien de visible — elle rendrait simplement fausse la seule
réponse qu'on ait à « il a accepté quoi, exactement ? ».
"""

import json
import os

import pytest

import app as flask_app
from programme import build_accounts

VECTEURS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors",
                        "loyalty_state.json")


def _vecteurs():
    with open(VECTEURS, "rb") as f:
        brut = f.read()
    return json.loads(brut)


def test_les_phrases_sont_mot_pour_mot_celles_de_la_caisse():
    """
    ⚠️ LE BACKOFFICE MONTRE LA PHRASE, LA CAISSE LA FAIT LIRE. Le patron choisit ici ce qui sera
    dit là-bas ; si les deux textes différaient, il choisirait une phrase que personne ne
    prononce — et le consentement consigné ne correspondrait à rien de réel.

    Les phrases voyagent dans le fichier de vecteurs, produit par l'implémentation TypeScript.
    ⚠️ SI CE TEST TOMBE, NE RECOPIE PAS LA PHRASE : regarde laquelle des deux a bougé, et
    pourquoi. Un texte de consentement ne se modifie pas en passant.
    """
    attendu = _vecteurs()["consentPhrases"]
    assert flask_app.FIDELIDADE_CONSENTEMENTS == attendu


def test_chaque_phrase_dit_comment_sortir():
    """
    ⚠️ UN CONSENTEMENT DONT ON NE PEUT PAS SORTIR N'EN EST PAS UN. Le dire à l'inscription est ce
    qui le rend libre — et c'est la première chose qu'on retire en réécrivant une phrase « pour
    faire plus court ».
    """
    for portee, phrase in flask_app.FIDELIDADE_CONSENTEMENTS.items():
        assert "sair quando quiser" in phrase, portee
        assert "SMS" in phrase, portee


def test_la_portee_large_annonce_les_nouvelles_letroite_non():
    """
    ⚠️ « LES POINTS PAR SMS » NE COUVRE PAS « VENEZ À NOTRE ÉVÉNEMENT ». Si la phrase étroite
    parlait déjà de nouvelles, la distinction entre les deux portées ne voudrait plus rien dire —
    et la future page marketing écrirait à des gens qui n'ont accepté que leurs points.
    """
    assert "novidades" in flask_app.FIDELIDADE_CONSENTEMENTS["points+news"]
    assert "novidades" not in flask_app.FIDELIDADE_CONSENTEMENTS["points"]


# ── Ce qui est lu en base ────────────────────────────────────────────────────────────────────

def test_une_portee_inconnue_retombe_sur_la_plus_etroite(monkeypatch):
    """
    ⚠️ SE TROMPER VERS « POINTS » NE COÛTE QU'UN MESSAGE NON ENVOYÉ ; SE TROMPER VERS
    « POINTS+NEWS » ÉCRIT À QUELQU'UN QUI N'A RIEN DEMANDÉ. Un texte saisi à la main dans
    Supabase, une valeur d'une version future, une colonne absente : aucun ne doit élargir un
    consentement.
    """
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [{"consent_scope": "points+news+partenaires"}])
    assert flask_app._fidelidade_reglages()["consent_scope"] == "points"


def test_la_portee_enregistree_est_relue_telle_quelle(monkeypatch):
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [{"consent_scope": "points+news"}])
    assert flask_app._fidelidade_reglages()["consent_scope"] == "points+news"


def test_le_repli_sans_table_est_le_plus_etroit():
    """Avant la migration, la colonne n'existe pas — et personne n'a accepté davantage."""
    assert flask_app.FIDELIDADE_DEFAUTS["consent_scope"] == "points"


# ── Ce que l'écran a le droit d'enregistrer ──────────────────────────────────────────────────

def test_le_formulaire_refuse_une_portee_inventee():
    """
    ⚠️ ACCEPTER SILENCIEUSEMENT SERAIT PIRE QU'UN REFUS. La valeur serait écrite, la relecture
    retomberait sur le repli étroit, et l'écran afficherait un réglage qui n'a aucun effet.
    """
    _, erreurs = flask_app._reglages_du_formulaire(
        {"consent_scope": "tout"}, dict(flask_app.FIDELIDADE_DEFAUTS))
    assert erreurs and "portée de consentement" in erreurs[0]


def test_le_formulaire_accepte_les_deux_portees_connues():
    for v in ("points", "points+news"):
        sortie, erreurs = flask_app._reglages_du_formulaire(
            {"consent_scope": v}, dict(flask_app.FIDELIDADE_DEFAUTS))
        assert not erreurs
        assert sortie["consent_scope"] == v


def test_la_portee_est_enregistree_comme_les_autres_reglages():
    """
    ⚠️ LA LIGNE ÉCRITE EST CONSTRUITE SUR `FIDELIDADE_DEFAUTS`. Un champ validé mais absent de
    ce dictionnaire serait accepté à l'écran, confirmé par l'API, et jamais écrit — le pire des
    trois états possibles.
    """
    assert "consent_scope" in flask_app.FIDELIDADE_DEFAUTS


# ── Ce que chaque client, lui, a accepté ─────────────────────────────────────────────────────

def _compte(fiche):
    visits = [{"fp": "aaaa1111", "ts": "2026-09-01T10:00:00Z", "amount_cents": 500}]
    links = [{"fp": "aaaa1111", "phone": "+351912345678"}]
    comptes = build_accounts(visits, [], links, [fiche] if fiche else [], 50,
                             flask_app.now_lisbon(), 12, {})
    return comptes[0]


def test_la_portee_du_client_est_celle_de_sa_fiche():
    c = _compte({"phone": "+351912345678", "consent_scope": "points+news",
                 "consent_at": "2026-09-01T10:00:00Z", "consent_source": "pos"})
    assert c["consent_scope"] == "points+news"
    assert c["consent_source"] == "pos"


def test_une_fiche_anterieure_a_la_migration_reste_etroite():
    """
    ⚠️ CEUX QUI SE SONT INSCRITS QUAND ON NE PARLAIT QUE DES POINTS N'ONT ENTENDU QUE ÇA. Leur
    fiche n'a pas de colonne ; la présumer large leur attribuerait un accord qu'ils n'ont jamais
    donné — et c'est exactement le jour où l'on veut lancer une campagne qu'on serait tenté de le
    faire.
    """
    c = _compte({"phone": "+351912345678", "consent_at": "2026-05-01T10:00:00Z"})
    assert c["consent_scope"] == "points"


def test_une_portee_nulle_en_base_reste_etroite():
    """`consent_scope: null` est ce que renvoie PostgREST pour une colonne jamais remplie."""
    c = _compte({"phone": "+351912345678", "consent_scope": None,
                 "consent_at": "2026-05-01T10:00:00Z"})
    assert c["consent_scope"] == "points"


def test_un_numero_sans_fiche_reste_etroit():
    c = _compte(None)
    assert c["consent_scope"] == "points"


# ── Ce qui descend à l'écran ─────────────────────────────────────────────────────────────────

def test_le_gabarit_affiche_la_phrase_sans_la_reecrire():
    """
    ⚠️ L'ÉCRAN NE DOIT PAS PORTER SA PROPRE COPIE DU TEXTE. Une phrase recopiée dans le HTML
    resterait figée le jour où la vraie changerait — et le backoffice montrerait au patron une
    phrase que personne n'a jamais dite à personne.
    """
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "fidelidade.html")
    with open(chemin, encoding="utf-8") as f:
        html = f.read()
    for phrase in flask_app.FIDELIDADE_CONSENTEMENTS.values():
        assert phrase not in html, (
            "la phrase de consentement est recopiée dans le gabarit — elle doit venir de "
            "/api/fidelidade/config, sinon les deux divergeront")
    assert "consent_phrases" in html


@pytest.mark.parametrize("champ", ["consent_scope", "consent_source"])
def test_la_fiche_client_recoit_la_portee(champ):
    """
    La liste blanche de `vue()` : un champ oublié ici n'arrive jamais à l'écran, et l'omission
    ne ressemble pas à une erreur — la page s'affiche, simplement sans la réponse.
    """
    import re
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app.py"), encoding="utf-8").read()
    bloc = src[src.index("    def vue(c):"):src.index("    return jsonify({\n        \"threshold\"")]
    assert re.search(r'"%s": c\["%s"\]' % (champ, champ), bloc)


def test_une_colonne_manquante_dit_quoi_faire(monkeypatch):
    """
    ⚠️ CE REFUS-LÀ EST ARRIVÉ EN PRODUCTION, SOUS UNE AUTRE FORME. Du code déployé dépendait
    d'une colonne (`welcome_points`) dont la migration n'était pas passée : tout le chemin
    fidélité répondait 503 pendant des heures, avec un message que rien ne reliait à un fichier
    SQL. Ici, la table existe, l'écran s'affiche — seul l'enregistrement échoue.
    """
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_fidelidade_reglages",
                        lambda: {**flask_app.FIDELIDADE_DEFAUTS, "missing": False})
    monkeypatch.setattr(
        flask_app, "_supa_upsert",
        lambda t, d: (False, 'column card_settings.consent_scope does not exist'))
    client = flask_app.app.test_client()
    r = client.put("/api/fidelidade/config", json={"reason": "essai"})
    assert r.status_code == 500
    erreur = r.get_json()["error"]
    assert "consent_scope" in erreur and "migration" in erreur
