"""
LES RÉGLAGES DU PROGRAMME — et la simulation qui doit précéder la décision.

⚠️ CES RÉGLAGES TOUCHENT DES GENS QUI ONT DÉJÀ PAYÉ. Relever le seuil fait reculer tous les
soldes d'un coup ; raccourcir l'expiration tue des points acquis ; une date de lancement efface
d'un trait tout l'historique. Un écran qui rend ces gestes faciles est un écran dangereux — d'où
des bornes, un motif obligatoire, un journal, et surtout une simulation sur les clients RÉELS
avant tout enregistrement.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("VENDUS_API_KEY", "x")
import app as A  # noqa: E402


REGLAGES = {
    "id": 1, "start_date": None, "legacy_rate_pct": 0, "legacy_cap_points": 0,
    "threshold_points": 50, "expiry_months": 12, "welcome_bonus_points": 0,
    "updated_at": "2026-09-19T08:00:00+00:00", "updated_by": "admin",
}

# ⚠️ LE CLIENT DU PROBLÈME RÉEL. 1 400 € dépensés depuis mai, sur un programme qui n'existait
# pas — vingt-huit boissons dues si rien ne les arrête.
HABITUE = [{"fp": "vieux", "ts": f"2026-0{m}-{j:02d}T10:00:00+00:00", "amount": 20000}
           for m, j in [(5, 3), (5, 17), (6, 4), (6, 20), (7, 8), (7, 22), (8, 5)]]


def _tables(reglages=None):
    return {
        "card_visits": HABITUE + [{"fp": "neuf", "ts": "2026-09-25T10:00:00+00:00",
                                   "amount": 1000}],
        "card_rewards": [],
        "card_links": [],
        "card_customers": [],
        "card_settings": [reglages if reglages is not None else REGLAGES],
        "card_settings_log": [],
    }


@pytest.fixture
def client(monkeypatch):
    etat = {"tables": _tables(), "ecrit": []}

    def faux_get(table, params=None):
        if table not in etat["tables"]:
            raise A.SupabaseSchemaError(f"table '{table}' absente du projet Supabase")
        lignes = etat["tables"][table]
        dec = int((params or {}).get("offset") or 0)
        lim = int((params or {}).get("limit") or 1000)
        return lignes[dec:dec + lim]

    def faux_upsert(table, data):
        etat["ecrit"].append((table, data))
        if table == "card_settings":
            etat["tables"]["card_settings"] = [{**REGLAGES, **data}]
        return True, None

    monkeypatch.setattr(A, "_supa_get", faux_get)
    monkeypatch.setattr(A, "_supa_upsert", faux_upsert)
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.etat = etat
    return c


def _role(monkeypatch, role):
    monkeypatch.setattr(A, "_current_role", lambda: role)


# ─── la lecture ───────────────────────────────────────────────────────────────────────────────

def test_les_reglages_et_leurs_bornes_descendent_a_l_ecran(client, monkeypatch):
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/config").get_json()
    assert d["settings"]["threshold_points"] == 50
    assert d["bounds"]["legacy_rate_pct"] == [0, 100]
    assert d["settings"]["missing"] is False


def test_sans_la_table_on_sert_les_defauts_et_on_le_dit(client, monkeypatch):
    """
    ⚠️ UNE MIGRATION NON PASSÉE NE DOIT PAS ÉTEINDRE LA PAGE. Les soldes restent lisibles ; seul
    le réglage manque, et l'écran le sait. Le repli est `start_date = None` — l'état d'avant,
    le seul qui ne retire rien à personne par accident.
    """
    _role(monkeypatch, "admin")
    del client.etat["tables"]["card_settings"]
    d = client.get("/api/fidelidade/config").get_json()
    assert d["settings"]["missing"] is True
    assert d["settings"]["start_date"] is None
    assert d["settings"]["threshold_points"] == 50


# ─── la simulation ────────────────────────────────────────────────────────────────────────────

def test_sans_date_de_lancement_l_habitue_reclame_vingt_huit_boissons(client, monkeypatch):
    """Le point de départ, chiffré : c'est le problème qu'on vient résoudre."""
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/simulation").get_json()
    assert d["before"]["rewards_due_now"] == 28
    assert d["before"]["cost_cents"] == 28 * A.REWARD_COST_CENTS


def test_une_date_de_lancement_sans_credit_remet_tout_a_zero(client, monkeypatch):
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/simulation"
                   "?start_date=2026-09-22&legacy_rate_pct=0&legacy_cap_points=0").get_json()
    assert d["after"]["rewards_due_now"] == 0
    assert d["after"]["points_outstanding"] == 10       # les 10 € du 25 septembre
    assert d["after"]["pre_start_cents"] == 140000


def test_le_credit_plafonne_rend_UNE_boisson_et_non_vingt_huit(client, monkeypatch):
    """
    ⚠️ LA RÈGLE QUE QUENTIN A DEMANDÉE, CHIFFRÉE. Proportionnelle — 10 % de ce qui a été dépensé
    — et plafonnée à une boisson. L'habitué de 1 400 € reçoit un café, pas vingt-huit.
    """
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/simulation"
                   "?start_date=2026-09-22&legacy_rate_pct=10&legacy_cap_points=50").get_json()
    assert d["after"]["credited"] == 1
    assert d["after"]["at_cap"] == 1
    assert d["after"]["rewards_due_now"] == 1
    assert d["after"]["cost_cents"] == A.REWARD_COST_CENTS


def test_la_simulation_n_ecrit_rien(client, monkeypatch):
    """
    ⚠️ C'EST CE QUI PERMET D'ESSAYER. Un taux, un plafond, une date, et revenir en arrière sans
    conséquence — le contraire d'une campagne de crédits inscrits en base qu'il faudrait défaire
    ligne à ligne.
    """
    _role(monkeypatch, "admin")
    client.get("/api/fidelidade/simulation?start_date=2026-09-22&legacy_rate_pct=10"
               "&legacy_cap_points=50")
    assert client.etat["ecrit"] == []


def test_les_plus_gros_soldes_montrent_leurs_passages(client, monkeypatch):
    """
    ⚠️ UN SOLDE DE 1 400 POINTS SUR 150 PASSAGES EST UN HABITUÉ ; SUR 7 PASSAGES, C'EST SUSPECT.
    Cinq à neuf pour cent des cartes se confondent — mêmes quatre chiffres, même libellé. Sans
    le nombre de passages à côté du solde, on ne peut pas distinguer un bon client d'une
    collision, et on offrirait des boissons à un agrégat de trois personnes.
    """
    _role(monkeypatch, "admin")
    d = client.get("/api/fidelidade/simulation").get_json()
    gros = d["before"]["top"][0]
    assert gros["balance_points"] == 1400
    assert gros["visits"] == 7
    assert gros["distinct_days"] == 7


def test_une_date_impossible_est_refusee(client, monkeypatch):
    _role(monkeypatch, "admin")
    for mauvaise in ("2026-13-01", "hier", "2026-09-31", "22/09/2026"):
        r = client.get(f"/api/fidelidade/simulation?start_date={mauvaise}")
        assert r.status_code == 400, mauvaise


def test_les_bornes_refusent_les_reglages_qui_videraient_le_programme(client, monkeypatch):
    """
    ⚠️ UN SEUIL À 5 000 POINTS NE DÉCLENCHE AUCUNE ERREUR — il rend simplement la récompense
    inatteignable, et le programme meurt sans que rien ne le dise. La borne transforme une faute
    de frappe en refus.
    """
    _role(monkeypatch, "admin")
    assert client.get("/api/fidelidade/simulation?threshold_points=5000").status_code == 400
    assert client.get("/api/fidelidade/simulation?legacy_rate_pct=300").status_code == 400
    assert client.get("/api/fidelidade/simulation?expiry_months=0").status_code == 400
    assert client.get("/api/fidelidade/simulation?threshold_points=abc").status_code == 400


# ─── l'enregistrement ─────────────────────────────────────────────────────────────────────────

def test_seul_l_admin_enregistre(client, monkeypatch):
    for role in (None, "staff", "investor"):
        _role(monkeypatch, role)
        r = client.put("/api/fidelidade/config",
                       json={"start_date": "2026-09-22", "reason": "lancement"})
        assert r.status_code == 403, role
    assert client.etat["ecrit"] == []


def test_un_changement_sans_motif_est_refuse(client, monkeypatch):
    """Un réglage sans raison écrite est un réglage que personne ne saura expliquer dans six mois."""
    _role(monkeypatch, "admin")
    r = client.put("/api/fidelidade/config", json={"start_date": "2026-09-22"})
    assert r.status_code == 400
    assert "motif" in r.get_json()["error"]
    assert client.etat["ecrit"] == []


def test_enregistrer_ecrit_le_reglage_ET_le_journal(client, monkeypatch):
    _role(monkeypatch, "admin")
    r = client.put("/api/fidelidade/config", json={
        "start_date": "2026-09-22", "legacy_rate_pct": 10, "legacy_cap_points": 50,
        "reason": "lancement du programme, crédit d'ancienneté plafonné à une boisson",
    })
    assert r.status_code == 200
    ecrit = dict((t, d) for t, d in client.etat["ecrit"])
    assert ecrit["card_settings"]["start_date"] == "2026-09-22"
    assert ecrit["card_settings"]["legacy_cap_points"] == 50
    journal = ecrit["card_settings_log"]
    assert journal["before"]["start_date"] is None
    assert journal["after"]["start_date"] == "2026-09-22"
    assert "ancienneté" in journal["reason"]


def test_un_reglage_hors_bornes_n_est_pas_enregistre(client, monkeypatch):
    _role(monkeypatch, "admin")
    r = client.put("/api/fidelidade/config",
                   json={"threshold_points": 99999, "reason": "essai"})
    assert r.status_code == 400
    assert client.etat["ecrit"] == []


def test_sans_la_table_on_refuse_d_enregistrer_plutot_que_d_inventer(client, monkeypatch):
    """
    ⚠️ ÉCRIRE DANS UNE TABLE ABSENTE ÉCHOUERAIT PLUS LOIN, ET PLUS MAL. Mieux vaut dire « la
    migration n'est pas passée » que laisser un upsert partir dans le vide et afficher un succès.
    """
    _role(monkeypatch, "admin")
    del client.etat["tables"]["card_settings"]
    r = client.put("/api/fidelidade/config",
                   json={"start_date": "2026-09-22", "reason": "lancement"})
    assert r.status_code == 500
    assert "card_settings" in r.get_json()["error"]
    assert client.etat["ecrit"] == []


def test_un_journal_muet_n_annule_pas_le_reglage(client, monkeypatch):
    """
    ⚠️ LE RÉGLAGE EST DÉJÀ EN BASE QUAND LE JOURNAL S'ÉCRIT. Renvoyer une erreur ferait croire
    que rien n'a changé, et le geste suivant serait de recommencer — sur un réglage déjà appliqué.
    """
    _role(monkeypatch, "admin")
    vrai = A._supa_upsert

    def upsert(table, data):
        if table == "card_settings_log":
            raise RuntimeError("journal indisponible")
        return vrai(table, data)

    monkeypatch.setattr(A, "_supa_upsert", upsert)
    r = client.put("/api/fidelidade/config",
                   json={"start_date": "2026-09-22", "reason": "lancement"})
    assert r.status_code == 200
    assert r.get_json()["log"] == "non écrit"
    assert r.get_json()["settings"]["start_date"] == "2026-09-22"


def test_le_reglage_enregistre_change_vraiment_les_soldes(client, monkeypatch):
    """
    ⚠️ LE BRANCHEMENT, PAS LA RÈGLE. Les réglages pourraient être parfaitement enregistrés et
    n'être lus par personne — le trou classique. On enregistre, puis on relit les comptes.
    """
    _role(monkeypatch, "admin")
    avant = client.get("/api/fidelidade/resumo").get_json()
    assert avant["summary"]["rewards_due_now"] == 28

    client.put("/api/fidelidade/config", json={
        "start_date": "2026-09-22", "legacy_rate_pct": 10, "legacy_cap_points": 50,
        "reason": "lancement",
    })
    apres = client.get("/api/fidelidade/resumo").get_json()
    assert apres["summary"]["rewards_due_now"] == 1
    assert apres["settings"]["start_date"] == "2026-09-22"
