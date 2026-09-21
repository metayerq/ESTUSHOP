"""
LA CONNEXION — par compte nominatif, ou par le trousseau de secours.

⚠️ LE PLUS GRAND RISQUE DE CE CHANGEMENT EST DE FERMER LA PORTE À TOUT LE MONDE. Les mots de
passe partagés vivent dans l'environnement ; les retirer d'un coup empêcherait celui qui
installe cette page de créer le premier compte. Ils restent, et ces tests l'exigent.
"""

import pytest

import app as flask_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(flask_app, "DASHBOARD_PASSWORD", "mdp-admin")
    monkeypatch.setattr(flask_app, "ACCOUNTANT_PASSWORD", "mdp-compta")
    monkeypatch.setattr(flask_app, "INVESTOR_PASSWORD", "")
    monkeypatch.setattr(flask_app, "STAFF_PASSWORD", "")
    monkeypatch.setattr(flask_app, "AUTH_SECRET", "secret-de-test")
    monkeypatch.setattr(flask_app, "_supa_patch", lambda t, f, d: (True, None))
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def compte(email, role, mdp, actif=True):
    return {"email": email, "nom": None, "role": role,
            "empreinte": flask_app._empreinte_mdp(mdp), "actif": actif,
            "cree_le": None, "cree_par": None, "derniere_connexion": None}


def poser(monkeypatch, comptes):
    monkeypatch.setattr(flask_app, "_comptes", lambda force=False: list(comptes))
    monkeypatch.setattr(flask_app, "_compte_par_email",
                        lambda e: next((c for c in comptes
                                        if c["email"] == (e or "").strip().lower()), None))


def test_le_trousseau_partage_fonctionne_toujours(client, monkeypatch):
    """
    ⚠️ SANS LUI, DÉPLOYER CETTE PAGE FERMERAIT LE BACKOFFICE. Personne ne pourrait créer le
    premier compte, et il faudrait un déploiement pour rouvrir.
    """
    poser(monkeypatch, [])
    r = client.post("/login", data={"password": "mdp-admin"})
    assert r.status_code == 302
    assert "estu_auth" in r.headers.get("Set-Cookie", "")


def test_un_compte_nominatif_ouvre_sur_sa_page(client, monkeypatch):
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "secret-ana")])
    r = client.post("/login", data={"email": "Ana@X.pt", "password": "secret-ana"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/contabilidade")


def test_le_cookie_nominatif_porte_ladresse_et_le_role(client, monkeypatch):
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "secret-ana")])
    r = client.post("/login", data={"email": "ana@x.pt", "password": "secret-ana"})
    cookie = r.headers["Set-Cookie"]
    assert "ana@x.pt" in cookie and "accountant" in cookie


def test_un_mauvais_mot_de_passe_ne_dit_pas_si_ladresse_existe(client, monkeypatch):
    """
    ⚠️ « CETTE ADRESSE N'EXISTE PAS » EST UNE LISTE DE COMPTES VALIDES offerte à qui essaie des
    adresses au hasard. Les deux cas rendent le même message.
    """
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "secret-ana")])
    a = client.post("/login", data={"email": "ana@x.pt", "password": "faux"})
    b = client.post("/login", data={"email": "inconnu@x.pt", "password": "faux"})
    assert a.status_code == b.status_code == 200
    assert b"Identifiants incorrects" in a.data
    assert a.data == b.data


def test_un_compte_desactive_nentre_pas(client, monkeypatch):
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "secret-ana", actif=False)])
    r = client.post("/login", data={"email": "ana@x.pt", "password": "secret-ana"})
    assert r.status_code == 200
    assert b"Identifiants incorrects" in r.data


def test_le_role_vient_du_compte_pas_du_cookie(client, monkeypatch):
    """
    ⚠️ LE COMPTE EST RELU À CHAQUE REQUÊTE. Un cookie signé resterait valable éternellement ;
    c'est la relecture qui permet de fermer une porte sans attendre l'expiration.
    """
    cs = [compte("ana@x.pt", "accountant", "s")]
    poser(monkeypatch, cs)
    sig = flask_app._signature_compte("ana@x.pt", "accountant")
    client.set_cookie("estu_auth", f"ana@x.pt|accountant|{sig}")
    with flask_app.app.test_request_context(
            "/", headers={"Cookie": f"estu_auth=ana@x.pt|accountant|{sig}"}):
        assert flask_app._current_role() == "accountant"
        # Le compte est désactivé : le MÊME cookie ne vaut plus rien.
        cs[0]["actif"] = False
        assert flask_app._current_role() is None


def test_un_cookie_dont_le_role_a_ete_modifie_est_rejete(client, monkeypatch):
    """
    ⚠️ LA SIGNATURE COUVRE LE RÔLE. Sans ça, quelqu'un qui lit son propre cookie le réécrit en
    « admin » et se promeut lui-même.
    """
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "s")])
    sig = flask_app._signature_compte("ana@x.pt", "accountant")
    forge = f"estu_auth=ana@x.pt|admin|{sig}"
    with flask_app.app.test_request_context("/", headers={"Cookie": forge}):
        assert flask_app._current_role() is None


def test_un_compte_lemporte_sur_le_trousseau(client, monkeypatch):
    """
    ⚠️ SINON LA DERNIÈRE CONNEXION ET LES ACTIONS JOURNALISÉES NE PORTENT PAS SON NOM. Quelqu'un
    qui a un compte et connaît aussi l'ancien mot de passe doit entrer par son compte.
    """
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "mdp-admin")])
    r = client.post("/login", data={"email": "ana@x.pt", "password": "mdp-admin"})
    assert r.headers["Location"].endswith("/contabilidade"), "le rôle partagé a pris le dessus"


def test_la_derniere_connexion_est_notee_mais_nempeche_pas_dentrer(client, monkeypatch):
    poser(monkeypatch, [compte("ana@x.pt", "accountant", "s")])

    def casse(*a, **k):
        raise RuntimeError("Supabase muet")

    monkeypatch.setattr(flask_app, "_supa_patch", casse)
    r = client.post("/login", data={"email": "ana@x.pt", "password": "s"})
    assert r.status_code == 302, "une trace qui échoue a empêché d'entrer"
