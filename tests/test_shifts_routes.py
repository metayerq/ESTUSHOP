# -*- coding: utf-8 -*-
"""
LES ROUTES DU PLANNING.

⚠️ CE QUI EST GARDÉ ICI N'EST PAS « L'API RÉPOND ». C'est : qui a le droit d'écrire, ce qui est
refusé plutôt qu'enregistré de travers, et le fait qu'un shift ne porte PAS son coût.

⚠️ UN SHIFT QUI PORTERAIT SON COÛT FIGÉ rendrait toute correction de taux invisible sur
l'historique — et on ne s'en apercevrait qu'en comparant deux écrans.
"""
from datetime import date

import pytest

import app as flask_app


@pytest.fixture
def ecrits(monkeypatch):
    out = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p=None: [])
    monkeypatch.setattr(flask_app, "_supa_insert",
                        lambda t, r: (out.append(("insert", t, r)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (out.append(("patch", t, f, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: (out.append(("delete", t, c, v)), True)[1])
    flask_app.app.config["TESTING"] = True
    return out


@pytest.fixture
def admin(monkeypatch, ecrits):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    return flask_app.app.test_client()


@pytest.fixture
def staff(monkeypatch, ecrits):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "staff")
    return flask_app.app.test_client()


SHIFT = {"person_id": "p-ana", "day": "2026-10-10",
         "start_time": "09:00", "end_time": "17:00"}


# ── Qui peut écrire ─────────────────────────────────────────────────────────────────────────

def test_seul_ladmin_pose_un_shift(staff, ecrits):
    r = staff.post("/api/shifts", json=SHIFT)
    assert r.status_code == 403
    assert ecrits == [], "un refus ne doit rien écrire"


def test_seul_ladmin_supprime_un_shift(staff, ecrits):
    assert staff.delete("/api/shifts/abc").status_code == 403
    assert ecrits == []


def test_LE_PLANNING_EST_FERME_A_LINVESTISSEUR():
    """
    ⚠️ IL AFFICHE QUI TRAVAILLE, QUAND, ET À QUEL TAUX. C'est l'emploi du temps de personnes
    identifiées, pas un chiffre d'actionnaire — même raison que les congés.
    """
    assert "/planning" in flask_app.INVESTOR_BLOCKED_PREFIXES
    assert "/api/shifts" in flask_app.INVESTOR_BLOCKED_PREFIXES


# ── Ce qui est refusé plutôt qu'enregistré de travers ───────────────────────────────────────

@pytest.mark.parametrize("manque", ["person_id", "day", "start_time", "end_time"])
def test_un_champ_manquant_est_refuse(admin, ecrits, manque):
    data = dict(SHIFT)
    data.pop(manque)
    assert admin.post("/api/shifts", json=data).status_code == 400
    assert ecrits == []


def test_UNE_FIN_AVANT_LE_DEBUT_EST_REFUSEE_PAS_COMPTEE_ZERO(admin, ecrits):
    """
    ⚠️ LE CALCUL REND 0 SUR UNE SAISIE INVERSÉE, ET C'EST JUSTE POUR LUI. Mais l'enregistrer
    ferait apparaître le service au planning en ne coûtant rien : le point mort du jour serait
    faux, sans un mot. On refuse au moment où quelqu'un peut encore corriger.
    """
    r = admin.post("/api/shifts", json=dict(SHIFT, start_time="17:00", end_time="09:00"))
    assert r.status_code == 400
    assert "fin" in r.get_json()["error"]
    assert ecrits == []


def test_un_jour_illisible_est_refuse(admin, ecrits):
    assert admin.post("/api/shifts", json=dict(SHIFT, day="le 10")).status_code == 400
    assert ecrits == []


def test_des_horaires_identiques_sont_refuses(admin, ecrits):
    assert admin.post("/api/shifts",
                      json=dict(SHIFT, start_time="09:00", end_time="09:00")).status_code == 400
    assert ecrits == []


# ── Ce qui est écrit ────────────────────────────────────────────────────────────────────────

def test_un_shift_valide_est_insere(admin, ecrits):
    assert admin.post("/api/shifts", json=SHIFT).get_json()["ok"] is True
    op, table, row = ecrits[0]
    assert (op, table) == ("insert", "shifts")
    assert row["person_id"] == "p-ana" and row["day"] == "2026-10-10"


def test_UN_SHIFT_NE_PORTE_JAMAIS_SON_COUT(admin, ecrits):
    """
    ⚠️ LE TAUX SE RÉSOUT À LA LECTURE, À LA DATE DU SERVICE. Figer un montant à la saisie
    rendrait toute correction de taux invisible sur l'historique, et deux écrans finiraient par
    annoncer deux chiffres.
    """
    admin.post("/api/shifts", json=dict(SHIFT, cost=96.0, hourly_rate=12.0, amount=96.0))
    row = ecrits[0][2]
    for interdit in ("cost", "amount", "hourly_rate", "total"):
        assert interdit not in row, f"le shift porte « {interdit} » — le coût doit se recalculer"


def test_un_shift_pointe_sur_lidentite_pas_sur_la_fiche(admin, ecrits):
    """`employee_id` change à chaque augmentation ; `person_id` traverse les versions."""
    admin.post("/api/shifts", json=SHIFT)
    row = ecrits[0][2]
    assert "person_id" in row and "employee_id" not in row


def test_renvoyer_un_id_modifie_au_lieu_de_dupliquer(admin, ecrits):
    admin.post("/api/shifts", json=dict(SHIFT, id="s1"))
    op, table, filtre, _ = ecrits[0]
    assert (op, table) == ("patch", "shifts") and filtre == {"id": "eq.s1"}


def test_la_suppression_passe_par_lidentifiant(admin, ecrits):
    assert admin.delete("/api/shifts/s9").get_json()["ok"] is True
    assert ecrits[0] == ("delete", "shifts", "id", "s9")


# ── La lecture ──────────────────────────────────────────────────────────────────────────────

def test_la_lecture_rend_les_fiches_avec_les_shifts(admin, monkeypatch):
    """Sans les fiches, l'écran affiche un planning dont il ne peut pas annoncer le coût."""
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p=None: [{"marqueur": t}])
    d = admin.get("/api/shifts?from=2026-10-01&to=2026-10-31").get_json()
    assert d["shifts"] == [{"marqueur": "shifts"}]
    assert d["employees"] == [{"marqueur": "employees"}]


def test_la_lecture_annonce_la_bascule(admin):
    """L'écran doit pouvoir dire « avant cette date, les extras sont au forfait »."""
    d = admin.get("/api/shifts").get_json()
    assert d["bascule"] == flask_app.PLANNING_CUTOVER.isoformat()


def test_la_fenetre_demandee_est_transmise_a_la_base(admin, monkeypatch):
    vus = {}
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p=None: (vus.setdefault(t, p), [])[1])
    admin.get("/api/shifts?from=2026-10-01&to=2026-10-31")
    filtre = str(vus["shifts"])
    assert "2026-10-01" in filtre and "2026-10-31" in filtre, (
        "sans fenêtre, l'écran rapatrie tout le planning à chaque semaine affichée")


def test_une_table_absente_remonte_au_lieu_de_rendre_un_planning_vide(admin, monkeypatch):
    """
    ⚠️ « AUCUN SHIFT » ET « TABLE ABSENTE » MÈNENT À DEUX GESTES OPPOSÉS. Un calendrier vide se
    lit « personne ne travaille » ; la migration non exécutée se lit « il faut la lancer ».
    """
    # ⚠️ SEULE `shifts` EST ABSENTE. Faire lever TOUTES les tables rendait ce test creux :
    # l'exception remontait depuis l'appel à `employees`, et avaler celle de `shifts` passait
    # inaperçu. Trouvé par mutation.
    def absente(t, p=None):
        if t == "shifts":
            raise flask_app.SupabaseSchemaError("table 'shifts' absente")
        return []
    monkeypatch.setattr(flask_app, "_supa_get", absente)
    with pytest.raises(flask_app.SupabaseSchemaError):
        admin.get("/api/shifts")
