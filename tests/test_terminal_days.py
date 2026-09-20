"""
L'ENCAISSEMENT TERMINAL, EN SOURCE COMPTABLE.

⚠️ CE MODULE EXISTE PARCE QUE `card_visits` SOUS-COMPTE. Elle sert la fidélité : elle écarte les
paiements sans derniers chiffres et ignore les remboursements. Mesuré sur juillet 2026 : 605
lignes retenues pour 606 paiements réglés, 13,44 € manquants. Sommer cette table et appeler ça
« encaissé » ment en silence — les chiffres restent plausibles.
"""

from datetime import date

import pytest

import app as flask_app
import revolut_merchant as rm

JOUR = date(2026, 9, 18)


def paiement(cents, tip=None, state="captured", ts="2026-09-18T10:00:00Z"):
    p = {"id": "p", "state": state, "amount": cents, "created_at": ts,
         "payment_method": {"card_last_four": "4242", "application_name": "Visa"}}
    if tip is not None:
        p["tip_amount"] = tip
    return p


@pytest.fixture
def api(monkeypatch):
    """Pose les commandes et leurs paiements ; renvoie le dictionnaire à remplir."""
    monde = {"orders": [], "payments": {}}
    monkeypatch.setattr(rm, "_key", lambda: "k")
    monkeypatch.setattr(rm, "_session", lambda: None)

    def faux_get(s, url, params=None, tries=6):
        if url.endswith("/orders"):
            return {"orders": monde["orders"]}
        oid = url.split("/orders/")[1].split("/")[0]
        return monde["payments"].get(oid, [])

    monkeypatch.setattr(rm, "_get", faux_get)
    return monde


def commande(monde, oid, paiements, **extra):
    monde["orders"].append({"id": oid, "state": "completed", **extra})
    monde["payments"][oid] = paiements


def test_un_paiement_sans_derniers_chiffres_est_compte(api):
    """
    ⚠️ LA DIFFÉRENCE AVEC `fetch_day`, ET TOUTE LA RAISON D'ÊTRE DE CETTE FONCTION. Tap to Pay
    ne rattache aucun numéro de carte : la fidélité ne peut pas lui inventer d'empreinte, mais
    la comptabilité doit compter l'argent.
    """
    p = paiement(1000)
    del p["payment_method"]
    commande(api, "a", [p])
    assert rm.fetch_day_totals(JOUR)["gross_cents"] == 1000


def test_les_pourboires_sont_comptes_a_part(api):
    """
    ⚠️ `amount` EXCLUT LE POURBOIRE — vérifié sur juillet 2026 : 6 078,11 € côté API contre
    6 091,55 € de ventes et 99,35 € de pourboires au relevé. Les additionner surévaluerait le
    chiffre d'affaires de 1,6 %.
    """
    commande(api, "a", [paiement(1000, tip=150)])
    t = rm.fetch_day_totals(JOUR)
    assert t["gross_cents"] == 1000
    assert t["tips_cents"] == 150


def test_labsence_de_tip_amount_nest_pas_une_erreur(api):
    """⚠️ Revolut OMET le champ plutôt que de rendre zéro : 5 paiements sur 7 n'en ont pas."""
    commande(api, "a", [paiement(1000)])
    assert rm.fetch_day_totals(JOUR)["tips_cents"] == 0


def test_un_remboursement_se_soustrait(api):
    """
    ⚠️ LES REMBOURSEMENTS N'ENTRENT JAMAIS DANS `card_visits` — le webhook n'écoute que
    `ORDER_COMPLETED`. Une journée avec un avoir afficherait sinon un écart inexplicable avec
    Vendus, et on chercherait une facture oubliée qui n'existe pas.
    """
    commande(api, "a", [paiement(1000)])
    commande(api, "b", [paiement(400)], related_order_id="a")
    t = rm.fetch_day_totals(JOUR)
    assert t["gross_cents"] == 1000
    assert t["refunds_cents"] == 400
    assert t["tx"] == 1, "un remboursement n'est pas une vente"


def test_un_paiement_du_jour_voisin_est_ecarte(api):
    """La fenêtre déborde d'une heure de chaque côté ; le jour retenu est celui de Lisbonne."""
    commande(api, "a", [paiement(1000, ts="2026-09-17T22:00:00Z")])
    assert rm.fetch_day_totals(JOUR)["gross_cents"] == 0


def test_un_paiement_non_abouti_est_ecarte(api):
    commande(api, "a", [paiement(1000, state="pending")])
    assert rm.fetch_day_totals(JOUR)["gross_cents"] == 0


# ── L'écriture ───────────────────────────────────────────────────────────────────────────────

def test_la_ligne_du_jour_se_reecrit_en_entier(monkeypatch):
    """
    ⚠️ LE CRON REPASSE SUR HIER TOUTES LES CINQ MINUTES. Additionner à l'existant doublerait les
    montants à chaque passage — et le chiffre grandirait tout seul, sans qu'aucune erreur ne
    s'affiche.
    """
    ecrits = []
    monkeypatch.setattr(flask_app._rm, "fetch_day_totals",
                        lambda d: {"gross_cents": 1000, "tips_cents": 50,
                                   "refunds_cents": 0, "tx": 3})
    monkeypatch.setattr(flask_app, "_supa_upsert",
                        lambda t, r: (ecrits.append((t, r)), (True, None))[1])
    flask_app._terminal_days_sync(JOUR, JOUR)
    flask_app._terminal_days_sync(JOUR, JOUR)
    assert all(r["gross_cents"] == 1000 for _, r in ecrits)
    assert ecrits[0][0] == "terminal_days"


def test_les_frais_ne_sont_jamais_ecrits_ici(monkeypatch):
    """
    ⚠️ LES FRAIS NE SONT CONNUS QU'AU RELEVÉ MENSUEL. Poser 0 en attendant ferait lire « aucun
    frais » là où il faut lire « pas encore connu ». Cette colonne reste NULL trois semaines par
    mois, et c'est voulu.
    """
    ecrits = []
    monkeypatch.setattr(flask_app._rm, "fetch_day_totals",
                        lambda d: {"gross_cents": 1000, "tips_cents": 0,
                                   "refunds_cents": 0, "tx": 1})
    monkeypatch.setattr(flask_app, "_supa_upsert",
                        lambda t, r: (ecrits.append(r), (True, None))[1])
    flask_app._terminal_days_sync(JOUR, JOUR)
    assert "fees_cents" not in ecrits[0]


def test_une_panne_comptable_ne_prive_pas_la_fidelite(monkeypatch):
    """
    ⚠️ LES DEUX LISENT LA MÊME API MAIS NE SERVENT PAS LE MÊME USAGE. Les grouper dans un même
    `try` ferait perdre les points d'un client parce qu'un total comptable a échoué.
    """
    import inspect
    src = inspect.getsource(flask_app.api_cron_refresh)
    i = src.index("_card_visits_sync")
    j = src.index("_terminal_days_sync")
    entre = src[i:j]
    assert entre.count("try:") >= 1, "les deux synchronisations partagent le même try"


# ── Le backfill ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app._rm, "enabled", lambda: True)
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def test_la_plage_est_plafonnee_a_dix_jours(admin, monkeypatch):
    """
    ⚠️ CHAQUE JOUR COÛTE UN APPEL À LA LISTE PLUS UN PAR COMMANDE. Sur un mois entier, la
    fonction est tuée par le timeout serverless AU MILIEU de la plage — et on ne sait pas où
    elle s'est arrêtée. Refuser est plus honnête qu'échouer à mi-chemin.
    """
    appels = []
    monkeypatch.setattr(flask_app, "_terminal_days_sync",
                        lambda f, t: appels.append((f, t)) or 1)
    r = admin.post("/api/terminal-days/sync",
                   json={"from": "2026-05-01", "to": "2026-05-31"})
    assert r.status_code == 400
    assert not appels, "la plage trop longue a quand même été lancée"

    ok = admin.post("/api/terminal-days/sync", json={"from": "2026-05-01", "to": "2026-05-10"})
    assert ok.status_code == 200


def test_des_bornes_inversees_sont_refusees(admin):
    r = admin.post("/api/terminal-days/sync", json={"from": "2026-05-10", "to": "2026-05-01"})
    assert r.status_code == 400


def test_sans_cle_revolut_elle_le_dit(admin, monkeypatch):
    monkeypatch.setattr(flask_app._rm, "enabled", lambda: False)
    r = admin.post("/api/terminal-days/sync", json={"from": "2026-05-01", "to": "2026-05-02"})
    assert r.status_code == 503


@pytest.mark.parametrize("role", [None, "investor", "staff"])
def test_seul_ladmin_reconstruit(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    r = flask_app.app.test_client().post("/api/terminal-days/sync",
                                         json={"from": "2026-05-01", "to": "2026-05-02"})
    assert r.status_code in (401, 403)
