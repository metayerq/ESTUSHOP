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


# ── Enregistrer un consentement donné après coup ─────────────────────────────────────────────
#
# ⚠️ SANS CE CHEMIN, TOUTE LA CLIENTÈLE DÉJÀ INSCRITE EST BLOQUÉE À VIE sur la portée étroite.
# La seule issue aurait été de réécrire la base à la main — sans trace, sans motif, sans
# personne pour en répondre. C'est exactement ce qu'on a failli faire le 20/09/2026 pour un
# client dont le patron « connaissait » l'accord sans l'avoir demandé.

@pytest.fixture
def client_http():
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


@pytest.fixture
def base(monkeypatch):
    """Une fiche existante sur la portée étroite, et ce qu'on lui écrit."""
    ecrits = []
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [{"phone": "+351912345678", "consent_scope": "points"}])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append((t, f, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_journal_action",
                        lambda *a: ecrits.append(("journal",) + a) or "écrit")
    return ecrits


def _put(c, **corps):
    return c.put("/api/fidelidade/consentement", json=corps)


def test_le_motif_est_obligatoire(client_http, base):
    """
    ⚠️ « MON FRÈRE, JE LE CONNAIS » N'EST PAS UN CONSENTEMENT ; « demandé au comptoir le 20/09,
    a dit oui » en est un. La différence entre consigner et fabriquer tient dans ce champ — et
    c'est pour ça qu'il est refusé vide.
    """
    r = _put(client_http, phone="912345678", scope="points+news", reason="")
    assert r.status_code == 400
    assert "motif" in r.get_json()["error"]
    assert not base, "la base a été modifiée sans motif"


def test_un_oui_donne_apres_coup_selargit(client_http, base):
    r = _put(client_http, phone="912345678", scope="points+news",
             reason="demandé au comptoir le 20/09, a dit oui")
    assert r.status_code == 200
    ecriture = [e for e in base if e[0] == "card_customers"][0]
    assert ecriture[2] == {"consent_scope": "points+news"}


def test_le_retrait_est_possible_dans_lautre_sens(client_http, base, monkeypatch):
    """
    ⚠️ UN RETRAIT DE CONSENTEMENT NE SE DISCUTE PAS, et personne ne doit avoir à se désabonner
    de TOUT pour cesser d'être démarché. Le chemin inverse doit être au moins aussi simple.
    """
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [{"phone": "+351912345678", "consent_scope": "points+news"}])
    r = _put(client_http, phone="912345678", scope="points",
             reason="m'a demandé d'arrêter les nouvelles")
    assert r.status_code == 200
    assert [e for e in base if e[0] == "card_customers"][0][2] == {"consent_scope": "points"}


def test_le_changement_est_journalise_sans_le_numero(client_http, base):
    """
    ⚠️ LA TRACE EST LA MOITIÉ DE LA FONCTIONNALITÉ — et elle ne recopie pas le numéro : un
    journal d'incidents qui garde les numéros devient lui-même un fichier de contacts.
    """
    _put(client_http, phone="912345678", scope="points+news", reason="a dit oui au comptoir")
    ligne = [e for e in base if e[0] == "journal"][0]
    assert ligne[2] == "consent-scope"
    assert "912345678" not in str(ligne)
    assert ligne[4] == {"consent_scope": "points"}
    assert ligne[5] == {"consent_scope": "points+news"}


def test_une_portee_inventee_est_refusee(client_http, base):
    r = _put(client_http, phone="912345678", scope="points+news+partenaires", reason="essai")
    assert r.status_code == 400
    assert not base


def test_un_numero_sans_fiche_est_refuse(client_http, base, monkeypatch):
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [])
    r = _put(client_http, phone="912345678", scope="points+news", reason="a dit oui")
    assert r.status_code == 404


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_peut_consigner(client_http, monkeypatch, role):
    """Attester du consentement de quelqu'un n'est pas consulter un chiffre."""
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    r = _put(client_http, phone="912345678", scope="points+news", reason="a dit oui")
    assert r.status_code in (401, 403)


def test_lecran_dit_quil_consigne_et_non_quil_accorde():
    """
    ⚠️ CELUI QUI CLIQUE DOIT SAVOIR QU'IL ATTESTE, pas qu'il coche une préférence. Un libellé
    du genre « activer les nouvelles » ferait de ce bouton un interrupteur — et du champ
    `consent_scope` une décoration.
    """
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "fidelidade.html")
    with open(chemin, encoding="utf-8") as f:
        html = f.read()
    i = html.index("Ce qu\\'il accepte de recevoir")
    bloc = html[i:i + 1200]
    assert "Demande-lui" in bloc
    assert "Il a accepté nos nouvelles" in bloc
    assert "Qu\\'a-t-il dit, et quand" in bloc
