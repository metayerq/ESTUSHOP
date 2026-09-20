"""
LA PAGE MARKETING — ET CE QU'ELLE NE FAIT PAS.

⚠️ ELLE N'ENVOIE RIEN, ET C'EST LA GARANTIE PRINCIPALE. Twilio vit dans Mesa ; le fichier clients
vit ici. Deux expéditeurs, ce serait deux endroits où vérifier le consentement, deux registres
anti-doublon, et un jour l'un des deux oublié.

⚠️ ET ELLE N'ENVOIE AUCUNE LISTE DE NUMÉROS. Elle transmet un texte et un critère ; la caisse
résout la cible dans sa propre base. Si l'expéditeur envoyait ce qu'on lui tend, `consent_scope`
ne serait qu'une décoration : une lecture périmée ou un mot de passe de bureau égaré suffiraient
à contourner le refus de quelqu'un.
"""

import json
import os

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")


class FausseReponse:
    def __init__(self, code=200, corps=None):
        self.status_code = code
        self._corps = corps if corps is not None else {}
        self.text = json.dumps(self._corps)

    def json(self):
        return self._corps


APERCU = {
    "dryRun": True,
    "destinataires": 12,
    "segments": 1,
    "segmentsTotal": 12,
    "message": "Estudantina: ola https://x STOP para sair",
    "ecartes": {"horsPortee": 30, "desabonne": 1, "sansPage": 0, "horsCritere": 0, "dejaRecu": 0},
}


@pytest.fixture
def mesa(monkeypatch):
    """Intercepte l'appel à la caisse et garde ce qui lui a été transmis."""
    vus = []

    def faux_post(url, json=None, headers=None, timeout=None):
        vus.append({"url": url, "corps": json, "headers": headers or {}})
        return FausseReponse(200, dict(APERCU))

    monkeypatch.setattr(flask_app, "MESA_URL", "https://caisse.example")
    monkeypatch.setattr(flask_app, "MESA_CAMPAIGN_SECRET", "secret-de-campagne")
    monkeypatch.setattr(flask_app._req, "post", faux_post)
    return vus


# ── Qui a le droit ───────────────────────────────────────────────────────────────────────────

def test_la_page_est_fermee_sans_session(client, monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: None)
    assert client.get("/marketing").status_code == 302


@pytest.mark.parametrize("chemin", ["/api/marketing/apercu", "/api/marketing/envoi",
                                    "/api/marketing/cout"])
def test_seul_ladmin_peut_composer(client, monkeypatch, chemin):
    """
    ⚠️ ÉCRIRE AU NOM DU CAFÉ N'EST PAS CONSULTER UN CHIFFRE. Le rôle investisseur ouvre un
    tableau de bord ; il ne doit pas pouvoir envoyer un SMS à la clientèle.
    """
    for role in (None, "investor", "staff"):
        monkeypatch.setattr(flask_app, "_current_role", lambda r=role: r)
        assert client.post(chemin, json={"texte": "bonjour tout le monde"}).status_code in (401, 403)


def test_le_marketing_est_ferme_au_role_investisseur():
    """La garde globale, pas seulement celle de chaque route."""
    assert "/marketing" in flask_app.INVESTOR_BLOCKED_PREFIXES
    assert "/api/marketing" in flask_app.INVESTOR_BLOCKED_PREFIXES


# ── Ce qui traverse jusqu'à la caisse ────────────────────────────────────────────────────────

def test_lapercu_ne_demande_pas_lenvoi(client, admin, mesa):
    """
    ⚠️ `send` ABSENT VEUT DIRE ESSAI À BLANC. La caisse n'envoie que sur demande explicite ; si
    cet écran le demandait par mégarde, le bouton « Vérifier » deviendrait un bouton « Envoyer ».
    """
    client.post("/api/marketing/apercu", json={"texte": "Amanha temos pao quente"})
    assert mesa[0]["corps"].get("send") is None


def test_lenvoi_le_demande_explicitement(client, admin, mesa):
    client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente"})
    assert mesa[0]["corps"]["send"] is True


def test_le_secret_est_presente_a_la_caisse(client, admin, mesa):
    client.post("/api/marketing/apercu", json={"texte": "Amanha temos pao quente"})
    assert mesa[0]["headers"]["Authorization"] == "Bearer secret-de-campagne"


def test_aucune_liste_de_numeros_ne_part_dici(client, admin, mesa):
    """
    ⚠️ LA GARANTIE ARCHITECTURALE, TENUE PAR UN TEST. Le jour où quelqu'un trouverait commode de
    calculer la cible ici et de l'envoyer toute faite, la vérification du consentement
    passerait du côté qui envoie à celui qui demande — et cesserait d'être une garantie.
    """
    client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente",
                                              "audience": "habitues", "arg": 4})
    envoye = mesa[0]["corps"]
    assert set(envoye) <= {"texte", "audience", "arg", "send"}
    assert "+351" not in json.dumps(envoye)


def test_la_configuration_absente_se_dit_en_clair(client, admin, monkeypatch):
    """
    ⚠️ « 502 » SUR UNE VARIABLE D'ENVIRONNEMENT ENVERRAIT CHERCHER UNE PANNE RÉSEAU PENDANT UNE
    HEURE. Le message nomme la variable et l'endroit où l'ajouter.
    """
    monkeypatch.setattr(flask_app, "MESA_URL", "")
    monkeypatch.setattr(flask_app, "MESA_CAMPAIGN_SECRET", "")
    r = client.post("/api/marketing/apercu", json={"texte": "Amanha temos pao quente"})
    assert r.status_code == 500
    erreur = r.get_json()["error"]
    assert "MESA_URL" in erreur and "MESA_CAMPAIGN_SECRET" in erreur and "Vercel" in erreur


def test_un_delai_depasse_ne_dit_pas_que_rien_nest_parti(client, admin, monkeypatch):
    """
    ⚠️ AMBIGU, ET IL FAUT LE DIRE. Un délai dépassé ne signifie pas que rien n'est parti : la
    caisse a pu envoyer avant de ne plus répondre. Annoncer « échec » ferait recommencer — et
    seule la contrainte unique en base empêcherait alors le doublon. Le message doit dire que la
    relance est sûre, au lieu de laisser deviner.
    """
    monkeypatch.setattr(flask_app, "MESA_URL", "https://caisse.example")
    monkeypatch.setattr(flask_app, "MESA_CAMPAIGN_SECRET", "s")

    def timeout(*a, **k):
        raise TimeoutError("trop long")

    monkeypatch.setattr(flask_app._req, "post", timeout)
    r = client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente"})
    assert r.status_code == 504
    erreur = r.get_json()["error"]
    assert "PEUT-ÊTRE" in erreur
    assert "relance" in erreur.lower()


def test_le_cout_en_euros_est_calcule_sur_les_segments(client, admin, mesa):
    r = client.post("/api/marketing/apercu", json={"texte": "Amanha temos pao quente"})
    d = r.get_json()
    assert d["cout_centimes"] == 12 * flask_app.PRIX_SEGMENT_CENTIMES


def test_un_refus_de_la_caisse_est_rendu_tel_quel(client, admin, monkeypatch):
    """Le texte trop long, l'audience inconnue : c'est la caisse qui tranche, pas cet écran."""
    monkeypatch.setattr(flask_app, "MESA_URL", "https://caisse.example")
    monkeypatch.setattr(flask_app, "MESA_CAMPAIGN_SECRET", "s")
    monkeypatch.setattr(flask_app._req, "post",
                        lambda *a, **k: FausseReponse(400, {"error": "audience inconnue"}))
    r = client.post("/api/marketing/envoi", json={"texte": "x" * 20, "audience": "n'importe"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "audience inconnue"


# ── Le compteur de caractères ────────────────────────────────────────────────────────────────

def test_le_compteur_signale_lalphabet(client, admin):
    propre = client.post("/api/marketing/cout", json={"texte": "Amanha temos pao"}).get_json()
    piege = client.post("/api/marketing/cout", json={"texte": "Amanhã temos pão"}).get_json()
    assert propre["gsm7"] is True
    assert piege["gsm7"] is False


def test_le_compteur_annonce_le_budget_reel(client, admin):
    """Pas 160 : l'enveloppe posée par la caisse en mange une bonne moitié."""
    d = client.post("/api/marketing/cout", json={"texte": ""}).get_json()
    assert 40 < d["budget"] < 120


# ── L'historique ─────────────────────────────────────────────────────────────────────────────

def test_lhistorique_survit_a_une_table_absente(client, admin, monkeypatch):
    def absent(*a, **k):
        raise flask_app.SupabaseSchemaError("card_campaigns n'existe pas")

    monkeypatch.setattr(flask_app, "_supa_get", absent)
    r = client.get("/api/marketing/historique")
    assert r.status_code == 200
    assert r.get_json() == {"campagnes": [], "missing": True}


# ── L'écran ──────────────────────────────────────────────────────────────────────────────────

def _gabarit():
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "marketing.html")
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def test_lecran_ne_compte_pas_les_caracteres_lui_meme():
    """
    ⚠️ UNE TROISIÈME IMPLÉMENTATION DE GSM-7 FINIRAIT PAR DIVERGER DES DEUX AUTRES. L'alphabet
    est une table de 128 caractères avec des pièges — « ç » minuscule absent, « Ç » majuscule
    présent. Le compteur vient du serveur ; l'écran ne fait que l'afficher.
    """
    html = _gabarit()
    assert "/api/marketing/cout" in html
    assert "GSM7" not in html
    assert ".length <= 160" not in html


def test_lecran_perime_lapercu_quand_le_texte_change():
    """
    ⚠️ SANS ÇA, ON VÉRIFIE UN TEXTE ET ON EN ENVOIE UN AUTRE — avec, affiché à l'écran, le
    nombre de destinataires de la version d'avant. Le bouton d'envoi doit se refermer dès la
    première frappe.
    """
    html = _gabarit()
    assert "perimer" in html
    assert "texteVu" in html


def test_lecran_demande_confirmation_avec_le_nombre():
    """Un « Êtes-vous sûr ? » ne fait rien relire. Le chiffre, si."""
    html = _gabarit()
    i = html.index("confirm(")
    bloc = html[i:i + 400]
    assert "destinataires" in bloc
    assert "irréversible" in bloc


def test_lhistorique_est_insere_en_texte_pas_en_html():
    """
    ⚠️ CE CORPS DE MESSAGE A ÉTÉ TAPÉ À LA MAIN DANS UNE ZONE DE SAISIE. Le réinjecter en
    balisage ferait exécuter ce qu'on y aurait collé — et cette page-ci est celle qui a accès au
    fichier clients.
    """
    html = _gabarit()
    i = html.index("function historique()")
    bloc = html[i:html.index("})();", i)]
    assert "textContent = l.body" in bloc
    assert "innerHTML = l.body" not in bloc
