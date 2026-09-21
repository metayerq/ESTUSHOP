"""
LES COMPTES NOMINATIFS.

⚠️ L'ACCÈS ÉTAIT UN MOT DE PASSE PARTAGÉ PAR RÔLE, dans une variable d'environnement. On ne
savait pas QUI s'était connecté ; retirer l'accès à une personne obligeait à changer le mot de
passe de toutes celles qui partageaient son rôle ; et un mot de passe transmis par message ne se
reprend jamais.

⚠️ CE FICHIER GARDE DES PORTES. Chacune de ses vérifications porte sur quelque chose qui, s'il
cédait, ne se verrait pas : un mot de passe lisible, un rôle qu'on s'attribue, un dernier
administrateur désactivé.
"""

from datetime import datetime, timezone

import pytest

import app as flask_app


# ── Le hachage ───────────────────────────────────────────────────────────────────────────────

def test_le_mot_de_passe_nest_jamais_dans_lempreinte():
    """⚠️ UNE BASE LUE PAR UN TIERS NE DOIT DONNER AUCUN ACCÈS."""
    e = flask_app._empreinte_mdp("mon-secret-en-clair")
    assert "mon-secret-en-clair" not in e
    assert e.startswith("pbkdf2$")


def test_deux_comptes_avec_le_meme_mot_de_passe_ont_des_empreintes_differentes():
    """
    ⚠️ LE SEL EST PAR COMPTE. Sans lui, deux empreintes identiques révèlent que deux personnes
    ont choisi le même mot de passe — et casser l'une les casse toutes les deux.
    """
    assert flask_app._empreinte_mdp("meme") != flask_app._empreinte_mdp("meme")


def test_le_hachage_est_lent_a_dessein():
    """
    ⚠️ UN SHA SIMPLE SE FORCE AU DICTIONNAIRE EN QUELQUES HEURES sur du matériel ordinaire.
    Deux cent mille tours coûtent une fraction de seconde à la connexion et des années à qui
    essaie un million de mots.
    """
    assert flask_app._PBKDF2_TOURS >= 100_000


def test_la_verification_accepte_le_bon_et_refuse_le_reste():
    e = flask_app._empreinte_mdp("bon")
    assert flask_app._verifie_mdp("bon", e) is True
    assert flask_app._verifie_mdp("mauvais", e) is False
    assert flask_app._verifie_mdp("bon", "") is False
    assert flask_app._verifie_mdp("bon", "n'importe quoi") is False
    assert flask_app._verifie_mdp(None, e) is False


# ── Le cookie ────────────────────────────────────────────────────────────────────────────────

def test_le_role_est_dans_la_signature():
    """
    ⚠️ SANS LUI, quelqu'un qui connaît son propre cookie pourrait en changer le rôle et se
    promouvoir administrateur — la signature resterait valable.
    """
    a = flask_app._signature_compte("ana@x.pt", "accountant")
    b = flask_app._signature_compte("ana@x.pt", "admin")
    assert a != b


def test_ladresse_est_normalisee_dans_la_signature():
    """« Ana@X.pt » et « ana@x.pt » sont la même personne."""
    assert flask_app._signature_compte("Ana@X.pt", "admin") == \
        flask_app._signature_compte("ana@x.pt", "admin")


# ── Les routes ───────────────────────────────────────────────────────────────────────────────

COMPTE = {"email": "ana@x.pt", "nom": "Ana", "role": "accountant",
          "empreinte": "pbkdf2$1$00$ff", "actif": True,
          "cree_le": "2026-09-01T10:00:00Z", "cree_par": "moi@x.pt",
          "derniere_connexion": None}


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_current_email", lambda: "moi@x.pt")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def poser(monkeypatch, comptes):
    monkeypatch.setattr(flask_app, "_comptes", lambda force=False: list(comptes))
    monkeypatch.setattr(flask_app, "_compte_par_email",
                        lambda e: next((c for c in comptes
                                        if c["email"] == (e or "").lower()), None))


def test_lempreinte_ne_sort_jamais_de_lapi(admin, monkeypatch):
    """
    ⚠️ MÊME VERS UN ADMINISTRATEUR, MÊME EN LECTURE. Elle n'a aucun usage à l'écran, et tout ce
    qui traverse le réseau finit un jour dans un journal, un cache ou une capture.
    """
    poser(monkeypatch, [COMPTE])
    import json
    brut = json.dumps(admin.get("/api/comptes").get_json())
    assert "empreinte" not in brut
    assert "pbkdf2" not in brut


def test_les_mots_de_passe_partages_encore_actifs_sont_annonces(admin, monkeypatch):
    """
    ⚠️ CRÉER DES COMPTES NOMINATIFS EN CROYANT AVOIR FERMÉ LES ANCIENS ACCÈS est exactement la
    fausse sécurité qu'un écran de réglages ne doit pas laisser s'installer.
    """
    poser(monkeypatch, [])
    monkeypatch.setattr(flask_app, "DASHBOARD_PASSWORD", "x")
    monkeypatch.setattr(flask_app, "ACCOUNTANT_PASSWORD", "y")
    monkeypatch.setattr(flask_app, "INVESTOR_PASSWORD", "")
    monkeypatch.setattr(flask_app, "STAFF_PASSWORD", "")
    d = admin.get("/api/comptes").get_json()
    assert set(d["partages_actifs"]) == {"admin", "accountant"}


def test_le_mot_de_passe_est_rendu_une_fois_a_la_creation(admin, monkeypatch):
    poser(monkeypatch, [])
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_upsert",
                        lambda t, r: (ecrits.append(r), (True, None))[1])
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a: "écrit")
    d = admin.post("/api/comptes", json={"email": "Ana@X.pt", "role": "accountant"}).get_json()
    assert len(d["mot_de_passe"]) >= 16
    assert d["email"] == "ana@x.pt", "l'adresse n'a pas été normalisée"
    # ⚠️ ET LA BASE NE REÇOIT QUE L'EMPREINTE.
    assert d["mot_de_passe"] not in str(ecrits[0])
    assert ecrits[0]["empreinte"].startswith("pbkdf2$")


def test_une_adresse_invalide_est_refusee(admin, monkeypatch):
    poser(monkeypatch, [])
    for mauvaise in ("ana", "ana@", "@x.pt", "ana@x", "ana x@y.pt"):
        r = admin.post("/api/comptes", json={"email": mauvaise, "role": "admin"})
        assert r.status_code == 400, mauvaise


def test_un_role_inconnu_est_refuse(admin, monkeypatch):
    poser(monkeypatch, [])
    assert admin.post("/api/comptes",
                      json={"email": "a@x.pt", "role": "superadmin"}).status_code == 400


def test_une_adresse_deja_prise_est_refusee(admin, monkeypatch):
    poser(monkeypatch, [COMPTE])
    assert admin.post("/api/comptes",
                      json={"email": "ana@x.pt", "role": "admin"}).status_code == 409


# ── Les gardes qui empêchent de se fermer la porte ───────────────────────────────────────────

def test_on_ne_se_retire_pas_ses_propres_droits(admin, monkeypatch):
    """
    ⚠️ L'ERREUR EST IRRÉVERSIBLE DEPUIS L'ÉCRAN. Une fois passé « investisseur », on ne peut
    plus ouvrir cette page pour se corriger.
    """
    moi = {**COMPTE, "email": "moi@x.pt", "role": "admin"}
    poser(monkeypatch, [moi])
    r = admin.put("/api/comptes", json={"email": "moi@x.pt", "role": "investor"})
    assert r.status_code == 400
    assert "propre" in r.get_json()["error"]


def test_on_ne_desactive_pas_son_propre_compte(admin, monkeypatch):
    poser(monkeypatch, [{**COMPTE, "email": "moi@x.pt", "role": "admin"}])
    assert admin.put("/api/comptes",
                     json={"email": "moi@x.pt", "actif": False}).status_code == 400


def test_le_dernier_administrateur_ne_peut_pas_etre_desactive(admin, monkeypatch):
    """
    ⚠️ SANS CE GARDE, LA DERNIÈRE DÉSACTIVATION FERME LE BACKOFFICE À TOUT LE MONDE — et il n'y
    a plus d'écran pour le rouvrir.
    """
    autre = {**COMPTE, "email": "autre@x.pt", "role": "admin"}
    poser(monkeypatch, [autre])
    r = admin.put("/api/comptes", json={"email": "autre@x.pt", "actif": False})
    assert r.status_code == 400
    assert "dernier administrateur" in r.get_json()["error"]


def test_un_administrateur_peut_etre_desactive_sil_en_reste_un(admin, monkeypatch):
    poser(monkeypatch, [{**COMPTE, "email": "a@x.pt", "role": "admin"},
                        {**COMPTE, "email": "b@x.pt", "role": "admin"}])
    monkeypatch.setattr(flask_app, "_supa_patch", lambda t, f, d: (True, None))
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a: "écrit")
    assert admin.put("/api/comptes",
                     json={"email": "a@x.pt", "actif": False}).status_code == 200


def test_regenerer_rend_un_mot_de_passe_neuf(admin, monkeypatch):
    poser(monkeypatch, [COMPTE])
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(d), (True, None))[1])
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a: "écrit")
    d = admin.put("/api/comptes", json={"email": "ana@x.pt", "regenerer": True}).get_json()
    assert len(d["mot_de_passe"]) >= 16
    assert ecrits[0]["empreinte"].startswith("pbkdf2$")
    assert d["mot_de_passe"] not in str(ecrits[0])


def test_le_journal_ne_recopie_pas_ladresse_entiere(admin, monkeypatch):
    """Un journal d'incidents qui garde les adresses devient un carnet d'adresses."""
    poser(monkeypatch, [])
    traces = []
    monkeypatch.setattr(flask_app, "_supa_upsert", lambda t, r: (True, None))
    monkeypatch.setattr(flask_app, "_journal_action",
                        lambda *a: traces.append(a) or "écrit")
    admin.post("/api/comptes", json={"email": "ana.silva@exemple.pt", "role": "staff"})
    assert "ana.silva@exemple.pt" not in str(traces)


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_gere_les_acces(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    c = flask_app.app.test_client()
    assert c.get("/api/comptes").status_code in (401, 403)
    assert c.post("/api/comptes", json={}).status_code in (401, 403)
    assert c.put("/api/comptes", json={}).status_code in (401, 403)


def test_les_reglages_sont_fermes_a_linvestisseur():
    assert "/parametres" in flask_app.INVESTOR_BLOCKED_PREFIXES
    assert "/api/comptes" in flask_app.INVESTOR_BLOCKED_PREFIXES
