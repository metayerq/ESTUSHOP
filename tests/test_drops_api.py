"""
L'ÉCRAN /drops — CE QUE LE BUREAU ÉCRIT DANS LES TABLES QUE LA CAISSE VEND.

⚠️ CE QUI EST ÉCRIT ICI SE VEND LÀ-BAS. Une opération ouverte est en vente sur la vitrine ; un
prix modifié ici est un prix encaissé par la caisse Mesa. Ces tests vérifient surtout les refus.
"""

import pytest

import app as A
import drops as D


class Base:
    """Les tables `drop_*`, en mémoire, avec les filtres PostgREST que les routes emploient."""

    def __init__(self):
        self.t = {k: [] for k in ("drop_operations", "drop_plats", "drop_soirees", "drop_stocks",
                                  "drop_commandes")}

    def _garde(self, ligne, params):
        for k, v in (params or {}).items():
            if k in ("order", "select", "limit", "on_conflict"):
                continue
            if isinstance(v, str) and v.startswith("eq.") and str(ligne.get(k)) != v[3:]:
                return False
        return True

    def get(self, table, params=None):
        return [dict(l) for l in self.t[table] if self._garde(l, params)]

    def insert(self, table, data):
        lignes = data if isinstance(data, list) else [data]
        if table == "drop_operations" and any(o["id"] == l["id"] for l in lignes for o in self.t[table]):
            return False, "duplicate key"
        # Les valeurs par défaut de la vraie table.
        defauts = {"drop_operations": {"statut": "brouillon"}}.get(table, {})
        self.t[table].extend({**defauts, **l} for l in lignes)
        return True, None

    def patch(self, table, filtre, data, dire_combien=False):
        for l in self.t[table]:
            if self._garde(l, filtre):
                l.update(data)
        return True, None

    def upsert(self, table, data, on_conflict=None):
        cles = on_conflict.split(",")
        for l in data:
            ex = next((x for x in self.t[table] if all(x.get(c) == l.get(c) for c in cles)), None)
            if ex:
                ex.update(l)
            else:
                self.t[table].append({"vendu_precommande": 0, "vendu_sur_place": 0, **l}
                                     if table == "drop_stocks" else dict(l))
        return True, None


class Reponse:
    ok = True


@pytest.fixture
def base(monkeypatch):
    b = Base()
    monkeypatch.setattr(A, "_current_role", lambda: "admin")
    monkeypatch.setattr(A, "_supa_get", b.get)
    monkeypatch.setattr(A, "_supa_insert", b.insert)
    monkeypatch.setattr(A, "_supa_patch", b.patch)
    monkeypatch.setattr(A, "_supa_upsert", b.upsert)
    monkeypatch.setattr(A, "_journal_action", lambda *a, **k: None)
    monkeypatch.setattr(A, "get_catalog", lambda: {
        "Salmon onigiri": {"id": 101, "name": "Salmon onigiri", "price": 4.5, "category_name": "Pop-up Toro Toro"},
        "Umeboshi onigiri": {"id": 102, "name": "Umeboshi onigiri", "price": 3.9, "category_name": "Pop-up Toro Toro"},
    })

    def supprimer(url, headers=None, params=None):
        table = url.rsplit("/", 1)[1]
        b.t[table] = [l for l in b.t[table] if not b._garde(l, params)]
        return Reponse()
    monkeypatch.setattr(A._req, "delete", supprimer)
    A.app.config["TESTING"] = True
    return b


NOUVELLE = {"id": "toro-toro-nov", "chef": "Toro Toro", "titre": "Onigiri night",
            "commission_pct": 20, "duree": {"kind": "unique", "jour": "2026-11-15"}}


def client():
    return A.app.test_client()


def creer(base, **extra):
    r = client().post("/api/drops", json={**NOUVELLE, **extra})
    assert r.status_code == 200, r.get_json()
    return r


MENU = [{"nom": "Salmon onigiri", "prix": "4,50", "vendus_product_id": 101},
        {"nom": "Umeboshi onigiri", "prix": "3.90", "vendus_product_id": 102}]


# ── Créer ────────────────────────────────────────────────────────────────────────────────────

def test_creer_une_operation_cree_ses_soirees_et_un_lien_de_chef(base):
    creer(base, duree={"kind": "hebdo", "debut": "2026-11-01", "fin": "2026-11-30", "jours": [3]})
    op = base.t["drop_operations"][0]
    assert op["statut"] == "brouillon", "une opération neuve ne se vend pas avant d'être ouverte"
    assert len(op["jeton_chef"]) >= 20
    assert [s["jour"] for s in base.t["drop_soirees"]] == ["2026-11-05", "2026-11-12", "2026-11-19", "2026-11-26"]
    assert base.t["drop_soirees"][0]["ouvre"] == "18:00" and base.t["drop_soirees"][0]["ferme"] == "23:00"


@pytest.mark.parametrize("mauvais", [
    {"id": "Toro Toro"},
    {"chef": ""},
    {"commission_pct": 120},
    {"duree": {"kind": "plage", "debut": "2026-11-22", "fin": "2026-11-16"}},
])
def test_une_operation_mal_decrite_nest_pas_creee(base, mauvais):
    r = client().post("/api/drops", json={**NOUVELLE, **mauvais})
    assert r.status_code == 400
    assert base.t["drop_operations"] == []


def test_un_identifiant_deja_pris_est_refuse(base):
    creer(base)
    assert client().post("/api/drops", json=NOUVELLE).status_code == 409


def test_des_soirees_refusees_ne_laissent_pas_une_operation_vide(base, monkeypatch):
    vrai = base.insert
    monkeypatch.setattr(A, "_supa_insert",
                        lambda t, d: (False, "refus") if t == "drop_soirees" else vrai(t, d))
    assert client().post("/api/drops", json=NOUVELLE).status_code == 502
    assert base.t["drop_operations"] == []


# ── Le menu ──────────────────────────────────────────────────────────────────────────────────

def test_le_menu_senregistre_en_centimes_avec_un_identifiant_par_plat(base):
    creer(base)
    r = client().put("/api/drops/toro-toro-nov/plats", json={"plats": MENU})
    assert r.status_code == 200
    assert [(p["id"], p["prix_cents"], p["vendus_product_id"], p["ordre"]) for p in base.t["drop_plats"]] == [
        ("salmon-onigiri", 450, 101, 0), ("umeboshi-onigiri", 390, 102, 1)]


@pytest.mark.parametrize("plat", [
    {"nom": "", "prix": "4.5"},
    {"nom": "Salmon", "prix": "gratuit"},
    {"nom": "Salmon", "prix": "0"},
])
def test_un_plat_mal_decrit_est_refuse(base, plat):
    creer(base)
    assert client().put("/api/drops/toro-toro-nov/plats", json={"plats": [plat]}).status_code == 400


def test_deux_plats_au_meme_identifiant_sont_refuses(base):
    creer(base)
    r = client().put("/api/drops/toro-toro-nov/plats", json={"plats": [MENU[0], MENU[0]]})
    assert r.status_code == 400


def test_une_operation_ouverte_ne_change_pas_de_prix_en_douce(base):
    """⚠️ La vitrine vendrait 5,00 € et la caisse facturerait 4,50 €."""
    creer(base)
    client().put("/api/drops/toro-toro-nov/plats", json={"plats": MENU})
    assert client().post("/api/drops/toro-toro-nov/statut", json={"statut": "ouverte"}).status_code == 200
    r = client().put("/api/drops/toro-toro-nov/plats",
                     json={"plats": [{**MENU[0], "prix": "5.00"}, MENU[1]]})
    assert r.status_code == 409 and "4.50" in r.get_json()["error"]
    assert base.t["drop_plats"][0]["prix_cents"] == 450


# ── Ouvrir ───────────────────────────────────────────────────────────────────────────────────

def test_ouvrir_exige_un_menu_rattache_a_vendus_au_bon_prix(base):
    creer(base)
    client().put("/api/drops/toro-toro-nov/plats",
                 json={"plats": [MENU[0], {**MENU[1], "vendus_product_id": None}]})
    r = client().post("/api/drops/toro-toro-nov/statut", json={"statut": "ouverte"})
    assert r.status_code == 409
    assert r.get_json()["empechements"] == ["Umeboshi onigiri : pas de produit Vendus"]
    assert base.t["drop_operations"][0].get("statut") != "ouverte"


def test_un_statut_inconnu_est_refuse(base):
    creer(base)
    assert client().post("/api/drops/toro-toro-nov/statut", json={"statut": "publiee"}).status_code == 400


# ── Les soirées et les stocks ────────────────────────────────────────────────────────────────

def test_les_stocks_nenvoient_jamais_les_quantites_vendues(base):
    """⚠️ La caisse les décompte ; les renvoyer d'ici remettrait les ventes de la soirée à zéro."""
    creer(base)
    client().put("/api/drops/toro-toro-nov/plats", json={"plats": MENU})
    base.t["drop_stocks"].append({"etablissement": "estudantina", "operation_id": "toro-toro-nov",
                                  "jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": 10,
                                  "sur_place": 5, "vendu_precommande": 4, "vendu_sur_place": 2})
    r = client().put("/api/drops/toro-toro-nov/stocks", json={"stocks": [
        {"jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": "30", "sur_place": "15",
         "vendu_precommande": 0}]})
    assert r.status_code == 200
    s = base.t["drop_stocks"][0]
    assert (s["precommande"], s["sur_place"], s["vendu_precommande"], s["vendu_sur_place"]) == (30, 15, 4, 2)


def test_un_stock_ne_descend_pas_sous_ce_qui_est_deja_vendu(base):
    creer(base)
    base.t["drop_stocks"].append({"etablissement": "estudantina", "operation_id": "toro-toro-nov",
                                  "jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": 10,
                                  "sur_place": 5, "vendu_precommande": 4, "vendu_sur_place": 0})
    r = client().put("/api/drops/toro-toro-nov/stocks", json={"stocks": [
        {"jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": 3, "sur_place": 5}]})
    assert r.status_code == 409 and "4 vendus" in r.get_json()["error"]


def test_une_quantite_negative_est_refusee(base):
    creer(base)
    r = client().put("/api/drops/toro-toro-nov/stocks", json={"stocks": [
        {"jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": -1, "sur_place": 0}]})
    assert r.status_code == 400


def test_les_reglages_dune_soiree_sont_verifies(base):
    creer(base)
    assert client().patch("/api/drops/toro-toro-nov/soirees/2026-11-15",
                          json={"capacite_creneau": 8, "limite": "17:00"}).status_code == 200
    s = base.t["drop_soirees"][0]
    assert (s["capacite_creneau"], s["limite"], s["ouvre"]) == (8, "17:00", "18:00")
    assert client().patch("/api/drops/toro-toro-nov/soirees/2026-11-15",
                          json={"retrait_debut": "23:00", "retrait_fin": "18:00"}).status_code == 400


def test_ajouter_des_soirees_ne_touche_pas_celles_qui_existent(base):
    creer(base)
    client().patch("/api/drops/toro-toro-nov/soirees/2026-11-15", json={"capacite_creneau": 9})
    r = client().post("/api/drops/toro-toro-nov/soirees",
                      json={"duree": {"kind": "plage", "debut": "2026-11-15", "fin": "2026-11-16"}})
    assert r.get_json()["ajoutees"] == 1
    assert [(s["jour"], s["capacite_creneau"]) for s in base.t["drop_soirees"]] == [
        ("2026-11-15", 9), ("2026-11-16", 6)]


def test_une_soiree_qui_a_des_commandes_ne_se_supprime_pas(base):
    creer(base)
    base.t["drop_commandes"].append({"etablissement": "estudantina", "operation_id": "toro-toro-nov",
                                     "jour": "2026-11-15", "id": "x" * 22})
    assert client().delete("/api/drops/toro-toro-nov/soirees/2026-11-15").status_code == 409
    assert len(base.t["drop_soirees"]) == 1
    base.t["drop_commandes"].clear()
    assert client().delete("/api/drops/toro-toro-nov/soirees/2026-11-15").status_code == 200
    assert base.t["drop_soirees"] == []


# ── Lire ─────────────────────────────────────────────────────────────────────────────────────

def test_le_detail_porte_le_bilan_les_liens_et_ce_qui_bloque(base):
    creer(base)
    client().put("/api/drops/toro-toro-nov/plats", json={"plats": MENU})
    base.t["drop_stocks"].append({"etablissement": "estudantina", "operation_id": "toro-toro-nov",
                                  "jour": "2026-11-15", "plat_id": "salmon-onigiri", "precommande": 10,
                                  "sur_place": 5, "vendu_precommande": 2, "vendu_sur_place": 3})
    base.t["drop_commandes"].extend([
        {"etablissement": "estudantina", "operation_id": "toro-toro-nov", "jour": "2026-11-15",
         "statut": "payee", "total_cents": 900},
        {"etablissement": "estudantina", "operation_id": "toro-toro-nov", "jour": "2026-11-15",
         "statut": "remboursee", "total_cents": 390}])
    d = client().get("/api/drops/toro-toro-nov").get_json()
    assert d["bilan"] == {"en_ligne_cents": 900, "sur_place_cents": 1350, "encaisse_cents": 2250,
                          "commission_cents": 450, "part_chef_cents": 1800}
    assert d["empechements"] == []
    jeton = base.t["drop_operations"][0]["jeton_chef"]
    assert d["liens"] == {"vitrine": "https://drop.estudantina.com/toro-toro-nov",
                          "chef": f"https://drop.estudantina.com/chef/{jeton}"}
    assert {p["id"] for p in d["catalogue"]} == {101, 102}


def test_un_nouveau_lien_de_chef_revoque_lancien(base):
    creer(base)
    ancien = base.t["drop_operations"][0]["jeton_chef"]
    r = client().post("/api/drops/toro-toro-nov/jeton").get_json()
    assert base.t["drop_operations"][0]["jeton_chef"] != ancien
    assert r["chef"].endswith(base.t["drop_operations"][0]["jeton_chef"])


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_touche_aux_precommandes(base, monkeypatch, role):
    creer(base)
    monkeypatch.setattr(A, "_current_role", lambda: role)
    c = client()
    for methode, url, corps in [
        ("get", "/api/drops", None), ("get", "/api/drops/toro-toro-nov", None),
        ("post", "/api/drops", NOUVELLE), ("put", "/api/drops/toro-toro-nov/plats", {"plats": MENU}),
        ("post", "/api/drops/toro-toro-nov/statut", {"statut": "ouverte"}),
        ("put", "/api/drops/toro-toro-nov/stocks", {"stocks": []}),
        ("post", "/api/drops/toro-toro-nov/jeton", None),
    ]:
        assert getattr(c, methode)(url, json=corps).status_code in (401, 403), url
    assert base.t["drop_plats"] == []


def test_la_page_est_fermee_a_linvestisseur():
    """⚠️ Elle montre le prénom et le téléphone de chaque client."""
    assert any("/drops".startswith(p) for p in A.INVESTOR_BLOCKED_PREFIXES)
    assert any("/api/drops/x".startswith(p) for p in A.INVESTOR_BLOCKED_PREFIXES)
