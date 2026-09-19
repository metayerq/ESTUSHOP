"""
LA ROUTE DU BACKOFFICE FIDÉLITÉ — ce qui sort, et pour qui.

Le calcul est vérifié ailleurs (`test_points.py`, `test_programme.py`). Ici on tient le reste :
qui a le droit de lire, ce qui ne descend pas jusqu'à l'écran, et le fait que la lecture ne
s'arrête pas en silence à mille lignes.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("VENDUS_API_KEY", "x")
import app as A  # noqa: E402


TABLES = {
    "card_visits": [
        {"fp": "fpA", "ts": "2026-09-01T10:00:00+00:00", "amount": 3000},
        {"fp": "fpA", "ts": "2026-09-08T10:00:00+00:00", "amount": 3000},
        {"fp": "fpB", "ts": "2026-09-02T10:00:00+00:00", "amount": 1200},
    ],
    "card_rewards": [{"fp": "fpA", "ts": "2026-09-08T10:05:00+00:00",
                      "points_spent": 50, "amount_cents": 300, "label": "Galao"}],
    "card_links": [{"fp": "fpA", "phone": "+351912345678"}],
    "card_customers": [{"phone": "+351912345678", "name": "Ana", "token": "SECRET-TOKEN",
                        "consent_at": "2026-08-01T09:00:00+00:00", "opted_out_at": None}],
}


@pytest.fixture
def client(monkeypatch):
    def faux_supa_get(table, params=None):
        lignes = TABLES.get(table, [])
        dec = int((params or {}).get("offset") or 0)
        lim = int((params or {}).get("limit") or 1000)
        return lignes[dec:dec + lim]

    monkeypatch.setattr(A, "_supa_get", faux_supa_get)
    A.app.config["TESTING"] = True
    return A.app.test_client()


def _role(monkeypatch, role):
    monkeypatch.setattr(A, "_current_role", lambda: role)


def test_sans_session_la_route_refuse(client, monkeypatch):
    """
    ⚠️ LA ROUTE LIT UN FICHIER DE CLIENTS NOMINATIF. L'ancienne API fidélité échappait au login
    parce qu'un POS l'appelait ; ce contournement a été retiré et ne doit pas revenir.
    """
    _role(monkeypatch, None)
    r = client.get("/api/fidelidade/resumo")
    assert r.status_code == 401


def test_l_ancienne_api_fidelite_ne_contourne_plus_le_login(monkeypatch):
    """
    ⚠️ CE N'EST PAS UN TEST SUR UNE ROUTE, C'EST UN TEST SUR UNE EXCEPTION DISPARUE. Tant que
    `_require_auth` laissait passer `/api/loyalty/`, n'importe quelle route créée sous ce
    préfixe naissait publique — sans que son auteur ait rien décidé.
    """
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "app.py"), encoding="utf-8").read()
    debut = source.index("def _require_auth()")
    corps = source[debut:debut + 2000]
    assert 'startswith("/api/loyalty/")' not in corps
    assert 'startswith("/carte/")' not in corps


def test_le_fichier_clients_est_ferme_a_l_investisseur():
    """
    ⚠️ DES PRÉNOMS ET DES NUMÉROS NE SONT PAS UNE DONNÉE D'ACTIONNAIRE. L'accès investisseur
    existe pour des chiffres ; il montrait un fichier de personnes.
    """
    assert "/loyalty" in A.INVESTOR_BLOCKED_PREFIXES
    assert "/api/fidelidade" in A.INVESTOR_BLOCKED_PREFIXES


def test_l_admin_voit_les_comptes_et_les_soldes(client, monkeypatch):
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/resumo").get_json()
    assert d["threshold"] == 50
    assert d["truncated"] is False
    par_genre = {c["kind"]: c for c in d["accounts"]}
    # Ana : une carte rattachée, 60 € dépensés, une boisson déjà prise. ⚠️ IL LUI RESTE
    # 10 POINTS, et non zéro : une récompense RETRANCHE le seuil, elle ne remet pas le compteur
    # à plat. (Le regroupement de PLUSIEURS cartes est tenu par `test_programme.py`.)
    assert par_genre["phone"]["name"] == "Ana"
    assert par_genre["phone"]["cards"] == 1
    assert par_genre["phone"]["state"]["balance_points"] == 10
    assert par_genre["phone"]["state"]["spent_points"] == 50
    assert par_genre["phone"]["state"]["rewards_due"] == 0
    assert par_genre["card"]["state"]["balance_points"] == 12
    assert par_genre["card"]["name"] is None


def test_ni_la_cle_interne_ni_l_empreinte_entiere_ne_descendent(client, monkeypatch):
    """
    ⚠️ LA FUITE QUI NE RESSEMBLE PAS À UNE FUITE. La clé d'un compte est
    `phone:+351912345678` : la renvoyer telle quelle enverrait le numéro complet à tous les
    rôles, et masquer le champ `phone` juste à côté n'aurait servi à rien. Même chose pour
    l'empreinte : elle rattache une ligne à un moyen de paiement, et l'écran n'en montre que
    quatre caractères — le reste n'a aucune raison de traverser.
    """
    _role(monkeypatch, "staff")
    d = client.get("/api/fidelidade/resumo").get_json()
    for c in d["accounts"]:
        assert "key" not in c
        assert "fps" not in c
        assert c["id"].startswith("c")
        assert len(c["short"]) <= 4
    # Et les listes d'action portent les mêmes identifiants d'écran, pas les clés internes.
    for c in d["summary"]["at_risk"] + d["summary"]["near_reward"]:
        assert "key" not in c and "fps" not in c


def test_le_jeton_de_la_page_client_ne_descend_jamais(client, monkeypatch):
    """
    ⚠️ CE JETON OUVRE LA PAGE DE POINTS DE QUELQU'UN, SANS MOT DE PASSE. Il n'a aucune raison
    d'être dans une réponse HTTP que le navigateur garde en mémoire, ni dans un journal, ni dans
    une capture d'écran. L'écran n'en a pas l'usage : il ne l'affiche pas.
    """
    _role(monkeypatch, "admin")
    brut = client.get("/api/fidelidade/resumo").get_data(as_text=True)
    assert "SECRET-TOKEN" not in brut


def test_le_numero_complet_ne_descend_qu_a_l_admin(client, monkeypatch):
    _role(monkeypatch, "admin")
    admin = client.get("/api/fidelidade/resumo").get_json()
    assert any(c["phone"] == "+351912345678" for c in admin["accounts"])

    _role(monkeypatch, "staff")
    staff = client.get("/api/fidelidade/resumo").get_json()
    assert all(c["phone"] is None for c in staff["accounts"])
    # Les quatre derniers chiffres suffisent à confirmer qu'on parle de la bonne personne.
    assert any(c["phone_masked"] == "••• 5678" for c in staff["accounts"])
    assert "+351912345678" not in client.get("/api/fidelidade/resumo").get_data(as_text=True)


def test_une_table_absente_est_une_erreur_et_non_un_programme_vide(client, monkeypatch):
    """
    ⚠️ UNE MIGRATION NON PASSÉE NE DOIT PAS RESSEMBLER À « AUCUN CLIENT ». C'est exactement la
    panne qui a fait tourner `daily_summary` à vide pendant deux mois sans que rien ne le dise.
    """
    _role(monkeypatch, "admin")

    def absente(table, params=None):
        raise A.SupabaseSchemaError("table 'card_visits' absente du projet Supabase")

    monkeypatch.setattr(A, "_supa_get", absente)
    r = client.get("/api/fidelidade/resumo")
    assert r.status_code == 500
    assert "card_visits" in r.get_json()["error"]


# ─── la pagination ────────────────────────────────────────────────────────────────────────────

def test_la_lecture_ne_s_arrete_pas_a_la_premiere_page(monkeypatch):
    """
    ⚠️ POSTGREST TRONQUE SANS PRÉVENIR. Lire 1 000 visites sur 2 500 donnerait des soldes faux
    pour tous ceux dont les passages les plus anciens tombent hors de la page — et l'erreur
    serait invisible, parce qu'un solde trop petit ressemble à un client peu fidèle.
    """
    toutes = [{"fp": f"fp{i}", "ts": "2026-09-01T10:00:00+00:00", "amount": 100}
              for i in range(2500)]

    def par_pages(table, params=None):
        dec = int((params or {}).get("offset") or 0)
        lim = int((params or {}).get("limit") or 1000)
        return toutes[dec:dec + lim]

    monkeypatch.setattr(A, "_supa_get", par_pages)
    lignes, tronque = A._supa_all("card_visits", {"select": "*"})
    assert len(lignes) == 2500
    assert tronque is False


def test_au_dela_du_plafond_la_page_le_dit(monkeypatch):
    """Un tableau de bord qui tronque en silence affiche des chiffres faux avec l'aplomb des vrais."""
    toutes = [{"fp": f"fp{i}"} for i in range(5000)]
    monkeypatch.setattr(A, "_supa_get", lambda t, p=None: toutes[
        int((p or {}).get("offset") or 0):int((p or {}).get("offset") or 0) + int((p or {}).get("limit") or 1000)])
    lignes, tronque = A._supa_all("card_visits", {}, page=1000, cap=2000)
    assert tronque is True
    assert len(lignes) == 2000


def test_une_table_vide_n_est_pas_une_troncature(monkeypatch):
    monkeypatch.setattr(A, "_supa_get", lambda t, p=None: [])
    lignes, tronque = A._supa_all("card_visits", {})
    assert lignes == []
    assert tronque is False


def test_le_masque_du_numero_ne_laisse_que_quatre_chiffres():
    assert A._masque_tel("+351912345678") == "••• 5678"
    assert A._masque_tel(None) == ""
    assert A._masque_tel("12") == "12"


# ─── l'écran et le serveur parlent-ils de la même chose ? ─────────────────────────────────────

def test_le_gabarit_ne_lit_que_des_champs_qui_existent(client, monkeypatch):
    """
    ⚠️ AUCUN TEST PYTHON NE VOIT UN « undefined » À L'ÉCRAN. Renommer un champ côté serveur
    laisse toute la suite au vert et affiche des cases vides au bureau — ou pire, « NaN points »
    en face du nom de quelqu'un. Ici on confronte les champs que le JavaScript lit à ceux que la
    route renvoie vraiment.
    """
    import re

    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/resumo").get_json()
    compte = d["accounts"][0]
    resume = d["summary"]
    etat = compte["state"]
    # ⚠️ PAR GENRE D'ÉVÉNEMENT, ET NON EN BLOC. Un passage n'a pas de `points` et une récompense
    # n'a pas de `amount_cents` : réunir les deux jeux de champs laisserait passer un
    # « +undefined pts » en face de chaque ligne d'achat. C'est exactement ce qui est arrivé, et
    # c'est la version permissive de ce test qui l'avait laissé passer.
    genres = {}
    for c2 in d["accounts"]:
        for e2 in c2["events"]:
            genres.setdefault(e2["kind"], set()).update(e2)
    assert set(genres) == {"visit", "reward"}, "les deux genres doivent être représentés"

    gabarit = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "templates", "fidelidade.html"), encoding="utf-8").read()
    js = gabarit[gabarit.index("<script>\n(function(){"):]

    # ⚠️ `e` DÉSIGNE AUSSI UN ÉVÉNEMENT DU NAVIGATEUR (`e.key`, `e.target`) : balayer tout le
    # script confondrait le DOM et les données. On ne lit que le bloc qui rend l'historique, et
    # on sépare ses DEUX BRANCHES — celle d'une récompense et celle d'un passage.
    debut = js.index("c.events.map(function(e){")
    bloc_evt = js[debut:js.index("}).join('')", debut)]
    recompense, _, passage = bloc_evt.partition("\n        : ")
    assert passage, "la forme du rendu d'historique a changé — relire le gabarit"

    def lus(prefixe, ou=js):
        return {m for m in re.findall(rf"\b{prefixe}\.([a-z_]+)\b(?!\s*\()", ou)}

    manquants = {
        "compte (c.)": lus("c") - set(compte) - {"state", "events"},
        "état (c.state.)": {m for m in re.findall(r"\bs\.(?:state\.)?([a-z_]+)\b(?!\s*\()", js)}
                           - set(resume) - set(etat),
        "ligne « récompense » (e.)": lus("e", recompense) - genres["reward"],
        "ligne « passage » (e.)": lus("e", passage) - genres["visit"],
    }
    manquants = {k: sorted(v) for k, v in manquants.items() if v}
    assert not manquants, f"le gabarit lit des champs que la route ne renvoie pas : {manquants}"
