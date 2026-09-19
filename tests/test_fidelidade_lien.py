"""
CORRIGER UN RATTACHEMENT — la seule issue à un numéro mal tapé.

⚠️ NEUF CHIFFRES TAPÉS SUR UN IPAD, EN SERVICE, PENDANT QUE LE CLIENT ATTEND. Le jour où il y en
a un de faux, la carte est rattachée au numéro d'un INCONNU — qui reçoit les SMS et le lien vers
la page de compte de quelqu'un d'autre. Et le bandeau du comptoir ne repropose jamais rien : il
ne s'affiche que pour une carte NON liée. Sans cette route, la faute est définitive.

Trois choses doivent être vraies après une correction : la carte pointe le bon numéro, la fiche
créée par erreur a disparu, et le geste a laissé une trace.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("VENDUS_API_KEY", "x")
import app as A  # noqa: E402

FP = "abc123def456"
FAUX = "+351911111111"      # le numéro saisi par erreur
VRAI = "+351922222222"      # celui du vrai client


@pytest.fixture
def client(monkeypatch):
    etat = {
        "card_links": [{"fp": FP, "phone": FAUX, "linked_at": "2026-09-20T09:00:00+00:00"}],
        "card_customers": [{"phone": FAUX, "name": "Ana", "welcome_points": 20,
                            "consent_at": "2026-09-20T09:00:00+00:00", "token": "T"}],
        "card_actions_log": [],
    }
    ecrits, supprimes = [], []

    def faux_get(table, params=None):
        if table not in etat:
            raise A.SupabaseSchemaError(f"table '{table}' absente")
        lignes = etat[table]
        p = params or {}
        for col in ("fp", "phone"):
            f = p.get(col)
            if f and f.startswith("eq."):
                lignes = [l for l in lignes if l.get(col) == f[3:]]
        return lignes

    def faux_upsert(table, data):
        ecrits.append((table, data))
        if table in etat and isinstance(data, dict):
            cle = "fp" if table == "card_links" else "phone"
            etat[table] = [l for l in etat[table] if l.get(cle) != data.get(cle)] + [data]
        return True, None

    def faux_delete(table, col, val):
        supprimes.append((table, col, val))
        etat[table] = [l for l in etat.get(table, []) if l.get(col) != val]
        return True

    monkeypatch.setattr(A, "_supa_get", faux_get)
    monkeypatch.setattr(A, "_supa_upsert", faux_upsert)
    monkeypatch.setattr(A, "_supa_delete", faux_delete)
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.etat, c.ecrits, c.supprimes = etat, ecrits, supprimes
    return c


def _role(monkeypatch, role):
    monkeypatch.setattr(A, "_current_role", lambda: role)


def _corriger(client, **kw):
    corps = {"fp": FP, "reason": "numéro mal saisi au comptoir"}
    corps.update(kw)
    return client.put("/api/fidelidade/lien", json=corps)


# ─── qui a le droit ───────────────────────────────────────────────────────────────────────────

def test_seul_l_admin_corrige(client, monkeypatch):
    for role in (None, "staff", "investor"):
        _role(monkeypatch, role)
        assert _corriger(client, phone=VRAI).status_code == 403, role
    assert client.ecrits == [] and client.supprimes == []


def test_un_geste_sans_motif_est_refuse(client, monkeypatch):
    """Délier retire à quelqu'un tout ce que sa carte portait. Ça se justifie par écrit."""
    _role(monkeypatch, "admin")
    r = client.put("/api/fidelidade/lien", json={"fp": FP, "phone": VRAI})
    assert r.status_code == 400 and "motif" in r.get_json()["error"]
    assert client.ecrits == []


# ─── corriger ─────────────────────────────────────────────────────────────────────────────────

def test_la_carte_pointe_le_bon_numero(client, monkeypatch):
    _role(monkeypatch, "admin")
    r = _corriger(client, phone="922 222 222")     # tapé comme on le lit
    assert r.status_code == 200
    assert r.get_json()["phone_masked"] == "••• 2222"
    assert client.etat["card_links"][0]["phone"] == VRAI


def test_la_date_de_rattachement_d_origine_est_conservee(client, monkeypatch):
    """
    ⚠️ LA DATER D'AUJOURD'HUI SERAIT DEUX MENSONGES POUR UNE FAUTE DE FRAPPE. Le bonus de
    bienvenue repartirait, et la personne apparaîtrait comme une NOUVELLE inscription dans le
    suivi de conversion — gonflant la semaine d'un client qu'on avait déjà.
    """
    _role(monkeypatch, "admin")
    _corriger(client, phone=VRAI)
    assert client.etat["card_links"][0]["linked_at"] == "2026-09-20T09:00:00+00:00"
    fiche = [c for c in client.etat["card_customers"] if c["phone"] == VRAI][0]
    assert fiche["consent_at"] == "2026-09-20T09:00:00+00:00"


def test_le_bonus_et_le_prenom_suivent_la_personne(client, monkeypatch):
    """C'est elle qui s'était inscrite ; la faute de frappe ne doit rien lui coûter."""
    _role(monkeypatch, "admin")
    _corriger(client, phone=VRAI)
    fiche = [c for c in client.etat["card_customers"] if c["phone"] == VRAI][0]
    assert fiche["welcome_points"] == 20
    assert fiche["name"] == "Ana"


def test_la_fiche_creee_par_erreur_disparait(client, monkeypatch):
    """
    ⚠️ ON AVAIT CRÉÉ UN ENREGISTREMENT AU NOM DE QUELQU'UN QUI N'A RIEN DEMANDÉ — avec un jeton
    ouvrant une page de points et un SMS de bienvenue déjà reçu. Il ne reste aucune raison de le
    garder, et une bonne raison de l'effacer.
    """
    _role(monkeypatch, "admin")
    r = _corriger(client, phone=VRAI)
    assert r.get_json()["orphan_removed"] is True
    assert all(c["phone"] != FAUX for c in client.etat["card_customers"])


def test_une_fiche_qui_garde_d_autres_cartes_n_est_PAS_supprimee(client, monkeypatch):
    """
    ⚠️ LE CAS QUI FERAIT DISPARAÎTRE UN VRAI CLIENT. Si le numéro « fautif » porte une autre
    carte, ce n'est pas une erreur de saisie : c'est quelqu'un qui existe, et dont on vient
    seulement de détacher une carte.
    """
    _role(monkeypatch, "admin")
    client.etat["card_links"].append({"fp": "autre", "phone": FAUX,
                                      "linked_at": "2026-08-01T10:00:00+00:00"})
    r = _corriger(client, phone=VRAI)
    assert r.get_json()["orphan_removed"] is False
    assert any(c["phone"] == FAUX for c in client.etat["card_customers"])


def test_un_numero_deja_connu_n_est_pas_recree(client, monkeypatch):
    """Sinon on écraserait le jeton et les points d'un client existant."""
    _role(monkeypatch, "admin")
    client.etat["card_customers"].append({"phone": VRAI, "name": "Rui", "welcome_points": 0,
                                          "consent_at": "2026-06-01T10:00:00+00:00", "token": "X"})
    _corriger(client, phone=VRAI)
    fiches = [c for c in client.etat["card_customers"] if c["phone"] == VRAI]
    assert len(fiches) == 1
    assert fiches[0]["name"] == "Rui" and fiches[0]["token"] == "X"


# ─── délier ───────────────────────────────────────────────────────────────────────────────────

def test_delier_rend_la_carte_anonyme(client, monkeypatch):
    """
    ⚠️ CE N'EST PAS UNE PERTE, C'EST UN RETOUR EN ARRIÈRE. Les points restent attachés à la
    carte, et le bandeau du comptoir reproposera l'inscription au prochain passage — cette fois
    avec le bon numéro.
    """
    _role(monkeypatch, "admin")
    r = _corriger(client, phone=None)
    assert r.status_code == 200 and r.get_json()["unlinked"] is True
    assert client.etat["card_links"] == []
    assert client.etat["card_customers"] == []      # la fiche orpheline part aussi


# ─── les refus ────────────────────────────────────────────────────────────────────────────────

def test_un_numero_invalide_est_refuse_avec_la_raison(client, monkeypatch):
    _role(monkeypatch, "admin")
    for mauvais, attendu in [("21 345 6789", "9"), ("12345", "court"), ("abc", "chiffres")]:
        r = _corriger(client, phone=mauvais)
        assert r.status_code == 400, mauvais
        assert attendu in r.get_json()["error"], (mauvais, r.get_json()["error"])
    assert client.etat["card_links"][0]["phone"] == FAUX


def test_une_carte_non_rattachee_n_a_rien_a_corriger(client, monkeypatch):
    _role(monkeypatch, "admin")
    r = client.put("/api/fidelidade/lien",
                   json={"fp": "inconnue", "phone": VRAI, "reason": "essai"})
    assert r.status_code == 404


def test_le_meme_numero_n_est_pas_un_changement(client, monkeypatch):
    """Réécrire à l'identique effacerait la date d'origine pour rien."""
    _role(monkeypatch, "admin")
    r = _corriger(client, phone=FAUX)
    assert r.status_code == 400


# ─── la trace ─────────────────────────────────────────────────────────────────────────────────

def test_le_geste_est_journalise_SANS_les_numeros(client, monkeypatch):
    """
    ⚠️ UN JOURNAL D'INCIDENTS QUI RECOPIE LES NUMÉROS DEVIENT UN FICHIER DE CONTACTS. Conservé
    plus longtemps que le reste, et que personne ne pense à purger. L'empreinte suffit à
    retrouver le compte.
    """
    _role(monkeypatch, "admin")
    _corriger(client, phone=VRAI)
    journal = [d for t, d in client.ecrits if t == "card_actions_log"]
    assert len(journal) == 1
    j = journal[0]
    assert j["action"] == "relink" and j["fp"] == FP
    assert "comptoir" in j["reason"]
    brut = str(j)
    assert FAUX not in brut and VRAI not in brut
    assert j["before"]["phone"] == "••• 1111"
    assert j["after"]["phone"] == "••• 2222"


def test_un_journal_muet_n_annule_pas_la_correction(client, monkeypatch):
    """La carte est déjà rattachée quand le journal s'écrit. Renvoyer une erreur ferait
    recommencer le geste sur un état déjà corrigé."""
    _role(monkeypatch, "admin")
    vrai = A._supa_upsert

    def upsert(table, data):
        if table == "card_actions_log":
            raise RuntimeError("journal indisponible")
        return vrai(table, data)

    monkeypatch.setattr(A, "_supa_upsert", upsert)
    r = _corriger(client, phone=VRAI)
    assert r.status_code == 200 and r.get_json()["log"] == "non écrit"
    assert client.etat["card_links"][0]["phone"] == VRAI
