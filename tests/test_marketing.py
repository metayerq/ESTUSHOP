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


def test_lecran_demande_confirmation_avec_le_nombre_et_le_texte():
    """
    Un « Êtes-vous sûr ? » ne fait rien relire. Le chiffre et le message, si.

    ⚠️ LE TEXTE EST DANS LA CONFIRMATION PARCE QUE C'EST LE DERNIER MOMENT OÙ ON PEUT LE LIRE.
    Après, il est chez des dizaines de gens.
    """
    html = _gabarit()
    i = html.index("confirm(")
    bloc = html[i:i + 400]
    assert "' + n + ' personne(s)" in bloc
    assert "vu.message" in bloc
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


# ── Le ciblage par la dépense, et la sélection à la main ─────────────────────────────────────

def test_les_refs_cochees_traversent_jusqua_la_caisse(client, admin, mesa):
    client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente",
                                              "refs": ["r1", "r2"]})
    assert mesa[0]["corps"]["refs"] == ["r1", "r2"]


def test_labsence_de_selection_nenvoie_pas_une_liste_vide(client, admin, mesa):
    """
    ⚠️ UN CHAMP ABSENT ET UNE LISTE VIDE SONT DEUX CHOSES DIFFÉRENTES. Transmettre `refs: []`
    quand rien n'est coché ferait comprendre à la caisse « n'écris à personne » — l'envoi
    réussirait, ne partirait à personne, et l'écran dirait « 0 envoyé » sans qu'on sache
    pourquoi.
    """
    client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente"})
    assert "refs" not in mesa[0]["corps"]


def test_une_selection_qui_nest_pas_une_liste_est_ignoree(client, admin, mesa):
    """Une chaîne, un nombre, un dictionnaire : rien de tout ça ne doit traverser tel quel."""
    for mauvais in ("r1", 42, {"r": 1}):
        mesa.clear()
        client.post("/api/marketing/envoi", json={"texte": "Amanha temos pao quente",
                                                  "refs": mauvais})
        assert "refs" not in mesa[0]["corps"]


def test_lapercu_ne_transmet_pas_la_selection(client, admin, mesa):
    """
    ⚠️ LA VÉRIFICATION DOIT MONTRER TOUT CE QUE LE CRITÈRE RETIENT. Filtrer l'aperçu sur les
    cases cochées ferait disparaître de la liste celui qu'on vient de décocher — et on ne
    pourrait plus le recocher.
    """
    client.post("/api/marketing/apercu", json={"texte": "Amanha temos pao quente",
                                               "refs": ["r1"]})
    assert "refs" not in mesa[0]["corps"]


def test_le_seuil_de_depense_est_annonce_en_euros():
    """
    ⚠️ QUELQU'UN QUI TAPE 50 EN PENSANT EUROS ET OBTIENT 50 CENTIMES écrirait à toute la liste
    en croyant viser ses meilleurs clients. L'unité doit être écrite dans le libellé.
    """
    # ⚠️ ON VISE LA LIGNE DU LIBELLÉ, PAS LE BLOC. La première version de ce test lisait
    # « euros » dans le commentaire juste au-dessus : retirer l'unité du texte affiché le
    # laissait passer — le test gardait le commentaire, pas l'écran.
    html = _gabarit()
    i = html.index("a === 'depense'")
    ligne = [l for l in html[i:i + 500].split("\n") if "mk-arg-l" in l][0]
    assert "euros" in ligne


def test_lecran_trie_sur_la_depense_et_le_solde():
    html = _gabarit()
    for colonne in ("lifetimeCents", "balancePoints", "distinctDays", "daysSinceLast"):
        assert 'data-tri="%s"' % colonne in html


def test_jamais_vu_ne_se_trie_pas_comme_zero_jour():
    """
    ⚠️ `null` TRIÉ COMME ZÉRO METTRAIT EN TÊTE DE « VU IL Y A » CEUX QU'ON N'A JAMAIS VUS —
    exactement ceux qu'une relance ne doit pas viser. Le tri les envoie en fin de liste.
    """
    html = _gabarit()
    i = html.index("function tableau()")
    bloc = html[i:i + 1200]
    assert "x === null" in bloc and "return 1" in bloc


def test_la_liste_est_construite_en_texte_pas_en_html():
    """Ces prénoms ont été dictés au comptoir et tapés à la main sur un iPad."""
    html = _gabarit()
    i = html.index("function tableau()")
    bloc = html[i:html.index("function compteCoches()")]
    assert "nom.textContent" in bloc
    assert "innerHTML = l.name" not in bloc


def test_la_confirmation_annonce_le_nombre_reellement_coche():
    """
    ⚠️ ANNONCER LE CHIFFRE DU CRITÈRE APRÈS AVOIR DÉCOCHÉ DIX PERSONNES SERAIT UN MENSONGE au
    moment précis où l'on demande de confirmer un geste irréversible.
    """
    html = _gabarit()
    i = html.index("confirm(")
    # Le nombre annoncé est la variable calculée juste au-dessus, pas le chiffre du critère.
    assert "var n = liste.length ? coches().length : vu.destinataires;" in html
    assert "' + n + ' personne(s)" in html[i:i + 200]


# ── L'enveloppe de la page ───────────────────────────────────────────────────────────────────

def test_la_nav_a_son_style():
    """
    ⚠️ CE BOGUE A ÉTÉ LIVRÉ, ET IL RENDAIT LA PAGE ILLISIBLE. La barre de navigation est
    recopiée dans chaque gabarit, accompagnée d'un bloc `<style>` qui la précède. En fabriquant
    `marketing.html` à partir de `fidelidade.html`, j'ai pris le `<nav>` sans ce bloc : sans
    `.nav-menu { display:none }`, TOUS les menus déroulants s'affichent en permanence et la
    navigation se déverse dans la page.

    ⚠️ ET RIEN NE SIGNALAIT L'ABSENCE. Le HTML était valide, la page se rendait, les tests
    passaient — une règle CSS manquante ne lève pas.
    """
    html = _gabarit()
    assert '<nav class="topnav"' in html
    for regle in (".topnav {", ".nav-menu {", ".nav-group {", ".nav-link.active"):
        assert regle in html, f"règle de navigation absente du gabarit : {regle}"


def test_le_style_de_la_nav_precede_la_nav():
    """Une feuille de style posée après l'élément laisse un clignotement à chaque chargement."""
    html = _gabarit()
    assert html.index(".nav-menu {") < html.index('<nav class="topnav"')
