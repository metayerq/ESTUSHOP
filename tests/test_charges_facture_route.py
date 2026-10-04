# -*- coding: utf-8 -*-
"""
SAISIR LA FACTURE D'UN MOIS.

⚠️ NI DATE D'EFFET NI MOTIF — et c'est tout l'objet. Une facture n'articule pas un changement :
son motif, c'est elle-même, et sa date, c'est son mois. Les demander posait deux questions dont
la réponse est connue d'avance, et rendait la saisie assez pénible pour être repoussée.

⚠️ ELLE S'APPLIQUE À SON MOIS, DONC RÉTROACTIVEMENT. C'est l'entorse assumée : la facture
d'octobre reçue le 5 novembre couvrait octobre. La faire commencer le 6 novembre laissait
octobre porter le montant de septembre, à jamais. L'invariant n'est pas « jamais rétroactif »,
il est « jamais en silence ».
"""
from datetime import date

import pytest

import app as flask_app


ELEC_SEPT = {"id": "c1", "name": "Électricité", "mode": "facture", "mois": "2026-09-01",
             "amount": 77.10, "frequency": "monthly", "category": "Energy & utilities",
             "notes": "", "valid_from": "2026-09-01", "valid_to": None, "active": True}
LOYER = {"id": "c9", "name": "Loyer", "mode": "stable", "mois": None, "amount": 700.0,
         "frequency": "monthly", "category": "Real estate", "notes": "",
         "valid_from": None, "valid_to": None, "active": True}


@pytest.fixture
def base(monkeypatch):
    etat = {"lignes": [dict(ELEC_SEPT), dict(LOYER)], "ecrits": []}
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p=None:
                        list(etat["lignes"]) if t == "charges_fixes" else [])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d, dire_combien=False:
                            (etat["ecrits"].append(("patch", f, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_insert",
                        lambda t, r: (etat["ecrits"].append(("insert", r)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_journal_action",
                        lambda *a: etat["ecrits"].append(("journal", a)))
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 11, 5))
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    flask_app.app.config["TESTING"] = True
    etat["client"] = flask_app.app.test_client()
    return etat


def poser(base, mois="2026-10", montant=86.40, nom="Électricité"):
    return base["client"].post("/api/charges/facture",
                               json={"name": nom, "mois": mois, "amount": montant})


# ── La saisie ───────────────────────────────────────────────────────────────────────────────

def test_UNE_FACTURE_COUVRE_SON_MOIS_PAS_LE_LENDEMAIN(base):
    """Le défaut d'origine : reçue le 5 novembre, elle doit quand même couvrir octobre."""
    assert poser(base).get_json()["ok"] is True
    insert = next(e[1] for e in base["ecrits"] if e[0] == "insert")
    assert insert["valid_from"] == "2026-10-01"
    assert insert["mois"] == "2026-10-01"
    assert insert["amount"] == 86.40


def test_la_facture_precedente_est_close_au_debut_du_mois(base):
    poser(base)
    patch = next(e for e in base["ecrits"] if e[0] == "patch")
    assert patch[1] == {"id": "eq.c1"}
    assert patch[2]["valid_to"] == "2026-10-01"


def test_NI_DATE_DEFFET_NI_MOTIF_NE_SONT_DEMANDES(base):
    """Le corps ne porte que trois champs : la charge, le mois, le montant."""
    assert poser(base).get_json()["ok"] is True
    insert = next(e[1] for e in base["ecrits"] if e[0] == "insert")
    assert "reason" not in insert and "effective_from" not in insert


def test_la_nouvelle_ligne_herite_du_nom_et_de_la_categorie(base):
    poser(base)
    insert = next(e[1] for e in base["ecrits"] if e[0] == "insert")
    assert insert["name"] == "Électricité"
    assert insert["category"] == "Energy & utilities"
    assert insert["mode"] == "facture"
    assert "id" not in insert, "la nouvelle ligne ne doit pas reprendre l'identifiant"


# ── Corriger un mois passé ──────────────────────────────────────────────────────────────────

def test_CORRIGER_UN_MOIS_DEJA_SAISI_EST_PERMIS_ET_TRACE(base):
    """
    ⚠️ C'EST LA SEULE ENTORSE AU « JAMAIS RÉTROACTIF », et elle est tracée plutôt qu'interdite.
    Une faute de frappe, ou un fournisseur qui réémet, doivent pouvoir se rattraper : vivre avec
    un chiffre faux pour toujours serait pire.
    """
    d = base["client"].post("/api/charges/facture",
                            json={"name": "Électricité", "mois": "2026-09",
                                  "amount": 75.00}).get_json()
    assert d["ok"] is True and d["corrige"] is True and d["ancien"] == 77.10
    # La période part avec le montant : corriger la fin change le taux, donc tous les mois
    # couverts — c'est le même geste, il s'écrit d'un bloc.
    assert any(e[0] == "patch" and e[2] == {"amount": 75.00, "periode_fin": None}
               for e in base["ecrits"]), base["ecrits"]
    assert any(e[0] == "journal" for e in base["ecrits"]), "la correction n'est pas journalisée"
    assert not any(e[0] == "insert" for e in base["ecrits"]), "une ligne a été dupliquée"


def test_un_montant_identique_nest_pas_une_correction(base):
    d = base["client"].post("/api/charges/facture",
                            json={"name": "Électricité", "mois": "2026-09",
                                  "amount": 77.10}).get_json()
    assert d.get("inchange") is True
    assert base["ecrits"] == [], "réenregistrer le même montant a écrit quelque chose"


# ── Ce qui est refusé ───────────────────────────────────────────────────────────────────────

def test_seul_ladmin_saisit_une_facture(base, monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "staff")
    assert poser(base).status_code == 403
    assert base["ecrits"] == []


def test_UN_MOIS_NON_COMMENCE_EST_REFUSE(base):
    """Imputer une mesure à une période qu'on n'a pas vécue."""
    r = poser(base, mois="2026-12")
    assert r.status_code == 400
    assert "commencé" in r.get_json()["error"]
    assert base["ecrits"] == []


def test_le_mois_courant_est_accepte(base):
    """Il n'est pas réclamé tant qu'il n'est pas clos, mais rien n'interdit de l'anticiper."""
    assert poser(base, mois="2026-11").get_json()["ok"] is True


def test_UNE_FACTURE_A_ZERO_EST_REFUSEE(base):
    """
    ⚠️ ELLE FERAIT DISPARAÎTRE LA CHARGE DU POINT MORT en se faisant passer pour une mesure —
    plus trompeur qu'un mois laissé en attente, qui au moins s'annonce.
    """
    assert poser(base, montant=0).status_code == 400
    assert poser(base, montant=-5).status_code == 400
    assert base["ecrits"] == []


@pytest.mark.parametrize("mauvais", [{"mois": "octobre"}, {"mois": ""}, {"name": ""},
                                     {"amount": "beaucoup"}])
def test_une_saisie_illisible_est_refusee(base, mauvais):
    corps = {"name": "Électricité", "mois": "2026-10", "amount": 86.40}
    corps.update(mauvais)
    assert base["client"].post("/api/charges/facture", json=corps).status_code == 400
    assert base["ecrits"] == []


def test_UNE_CHARGE_STABLE_NE_SE_SAISIT_PAS_PAR_FACTURE(base):
    """Le loyer garde sa cérémonie : date d'effet et motif. Il ne passe pas par cette porte."""
    r = poser(base, nom="Loyer")
    assert r.status_code == 400
    assert "sur facture" in r.get_json()["error"]
    assert base["ecrits"] == []


def test_une_charge_inconnue_est_refusee(base):
    assert poser(base, nom="Gaz").status_code == 404


# ── Ce que la lecture annonce ───────────────────────────────────────────────────────────────

def test_LA_LECTURE_DIT_JUSQUOU_LA_CHARGE_EST_MESUREE(base, monkeypatch):
    """
    ⚠️ LA RÈGLE VIT DANS `charges.py`, PAS DANS LE NAVIGATEUR. La réécrire en JavaScript
    donnerait deux définitions de « en retard », et l'écran finirait par réclamer une période
    que le calcul ignore.

    ⚠️ ET ELLE SE COMPTE EN JOURS. Elle réclamait les mois clos sans facture ; une facture
    d'eau couvre du 21/07 au 18/09, donc aucun mois n'est jamais complet ni jamais vide.
    """
    monkeypatch.setattr(flask_app, "_resynchroniser_active", lambda t: None)
    d = base["client"].get("/api/charges").get_json()
    # La facture de septembre n'a pas de période : on la lit comme couvrant son mois.
    assert d["couverture"]["Électricité"] == {
        "jusqua": "2026-09-30", "jours": 36, "debut_suivant": "2026-10-01"}
    assert d["aujourdhui"] == "2026-11-05"


def test_une_facture_qui_couvre_aujourdhui_nestime_aucun_jour(base, monkeypatch):
    monkeypatch.setattr(flask_app, "_resynchroniser_active", lambda t: None)
    base["lignes"].append(dict(ELEC_SEPT, id="c2", periode_debut="2026-10-01",
                               periode_fin="2026-11-30", amount=86.40))
    d = base["client"].get("/api/charges").get_json()
    assert d["couverture"]["Électricité"]["jours"] == 0


# ══ CONVERTIR UNE CHARGE ════════════════════════════════════════════════════════════════════

def test_LA_CONVERSION_TOUCHE_TOUTES_LES_LIGNES_DU_MEME_NOM(base):
    """
    ⚠️ UNE CHARGE AUGMENTÉE A PLUSIEURS LIGNES DATÉES. N'en convertir qu'une ferait apparaître
    la même charge dans les DEUX onglets, avec deux gestes différents pour la même histoire.
    """
    d = base["client"].post("/api/charges/mode",
                            json={"name": "Loyer", "mode": "facture"}).get_json()
    assert d["ok"] is True
    patch = next(e for e in base["ecrits"] if e[0] == "patch")
    assert patch[1] == {"name": "eq.Loyer"}, "la conversion ne vise pas toutes les lignes"
    assert patch[2] == {"mode": "facture"}


def test_LA_CONVERSION_NE_POSE_AUCUN_MOIS(base):
    """
    ⚠️ ON NE SAIT PAS À QUEL MOIS CORRESPOND LE MONTANT DÉJÀ SAISI. L'inventer serait affirmer
    une mesure qu'on n'a pas : la charge s'affiche « aucune facture saisie » et la première
    facture prend le relais à partir de son propre mois.
    """
    base["client"].post("/api/charges/mode", json={"name": "Loyer", "mode": "facture"})
    patch = next(e for e in base["ecrits"] if e[0] == "patch")
    assert "mois" not in patch[2]


def test_la_conversion_est_journalisee(base):
    base["client"].post("/api/charges/mode", json={"name": "Loyer", "mode": "facture"})
    assert any(e[0] == "journal" for e in base["ecrits"])


def test_seul_ladmin_convertit(base, monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "staff")
    assert base["client"].post("/api/charges/mode",
                               json={"name": "Loyer", "mode": "facture"}).status_code == 403
    assert base["ecrits"] == []


@pytest.mark.parametrize("corps", [{"name": "", "mode": "facture"},
                                   {"name": "Loyer", "mode": "autre"},
                                   {"name": "Loyer", "mode": ""}])
def test_une_conversion_mal_formee_est_refusee(base, corps):
    assert base["client"].post("/api/charges/mode", json=corps).status_code == 400
    assert base["ecrits"] == []


def test_une_charge_inconnue_ne_se_convertit_pas(base, monkeypatch):
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p=None: [])
    assert base["client"].post("/api/charges/mode",
                               json={"name": "Gaz", "mode": "facture"}).status_code == 404


# ── La ligne héritée de la bascule ──────────────────────────────────────────────────────────

CONVERTIE = {"id": "c7", "name": "Eau", "mode": "facture", "mois": None, "amount": 31.40,
             "frequency": "monthly", "category": "Energy & utilities", "notes": "",
             "valid_from": None, "valid_to": None, "active": True}


def test_LA_PREMIERE_FACTURE_FERME_LA_LIGNE_HERITEE_DE_LA_BASCULE(base):
    """
    ⚠️ TROUVÉ LE JOUR OÙ QUENTIN A BASCULÉ SES DEUX CHARGES, avant qu'il saisisse quoi que ce
    soit. Passer « Eau » en mode facture garde sa ligne d'avant, sans mois et OUVERTE. La route
    ne fermait que la facture PRÉCÉDENTE — il n'y en avait pas — donc la ligne héritée restait
    ouverte à côté de la neuve : 31,40 + 29,80 imputés au même mois. Un point mort gonflé d'une
    charge entière, et rien à l'écran pour le dire.
    """
    base["lignes"] = [dict(CONVERTIE), dict(LOYER)]
    r = poser(base, mois="2026-10", montant=29.80, nom="Eau")
    assert r.get_json()["ok"] is True

    fermetures = [e for e in base["ecrits"]
                  if e[0] == "patch" and e[2].get("valid_to") == "2026-10-01"]
    assert len(fermetures) == 1, f"la ligne héritée n'est pas fermée : {base['ecrits']}"
    assert fermetures[0][1] == {"id": "eq.c7"}, fermetures[0]
    assert fermetures[0][2]["active"] is False


def test_LES_DEUX_LIGNES_A_RECOUPER_SONT_FERMEES_TOUTES_LES_DEUX(base):
    """
    ⚠️ LA ROUTE N'EN FERMAIT QU'UNE. Avec une facture précédente ET l'héritage encore ouvert,
    fermer la première laissait la seconde se superposer — exactement le défaut d'origine,
    déplacé d'un cran.
    """
    base["lignes"] = [dict(CONVERTIE),
                      {**ELEC_SEPT, "id": "c8", "name": "Eau", "amount": 30.0}]
    r = poser(base, mois="2026-10", montant=29.80, nom="Eau")
    assert r.get_json()["ok"] is True
    fermes = sorted(e[1]["id"] for e in base["ecrits"]
                    if e[0] == "patch" and e[2].get("valid_to") == "2026-10-01")
    assert fermes == ["eq.c7", "eq.c8"], base["ecrits"]


def test_UNE_LIGNE_HERITEE_DEJA_FERMEE_NEST_PAS_RETOUCHEE(base):
    base["lignes"] = [{**CONVERTIE, "valid_to": "2026-09-01", "active": False},
                      {**ELEC_SEPT, "id": "c8", "name": "Eau", "amount": 30.0}]
    r = poser(base, mois="2026-10", montant=29.80, nom="Eau")
    assert r.get_json()["ok"] is True
    fermes = [e[1]["id"] for e in base["ecrits"]
              if e[0] == "patch" and e[2].get("valid_to") == "2026-10-01"]
    assert fermes == ["eq.c8"], base["ecrits"]


# ── Une facture couvre une période ──────────────────────────────────────────────────────────

def poser_periode(base, debut, fin, montant, nom="Eau"):
    return base["client"].post("/api/charges/facture",
                               json={"name": nom, "mois": debut, "fin": fin,
                                     "amount": montant})


EAU_HERITEE = {"id": "w0", "name": "Eau", "mode": "facture", "mois": None, "amount": 31.40,
               "frequency": "monthly", "category": "Energy & utilities", "notes": "",
               "valid_from": None, "valid_to": None, "active": True}


def test_LA_PERIODE_EST_ENREGISTREE_AVEC_LA_FACTURE(base):
    """
    ⚠️ LA VRAIE FACTURE EPAL. 60 jours, 176,14 €, à cheval sur juillet, août et septembre.
    Sans les deux dates, le système en faisait 176,14 €/mois — 86,78 € de trop chaque mois.
    """
    base["lignes"] = [dict(EAU_HERITEE), dict(LOYER)]
    r = poser_periode(base, "2026-07-21", "2026-09-18", 176.14)
    assert r.get_json()["ok"] is True
    ins = [e[1] for e in base["ecrits"] if e[0] == "insert"]
    assert len(ins) == 1, base["ecrits"]
    assert ins[0]["periode_debut"] == "2026-07-21"
    assert ins[0]["periode_fin"] == "2026-09-18"
    assert ins[0]["valid_from"] == "2026-07-21"
    assert ins[0]["valid_to"] is None, "la dernière facture reste ouverte"
    assert ins[0]["mois"] == "2026-07-01", "le mois reste écrit, comme étiquette"


def test_UNE_PERIODE_NON_TERMINEE_EST_REFUSEE(base):
    """On ne mesure pas une période qu'on n'a pas fini de vivre. (On est le 05/11/2026.)"""
    base["lignes"] = [dict(EAU_HERITEE)]
    d = poser_periode(base, "2026-10-20", "2026-12-18", 150.0).get_json()
    assert d["ok"] is False and "pas terminée" in d["error"]
    assert not any(e[0] == "insert" for e in base["ecrits"])


def test_UNE_PERIODE_A_LENVERS_EST_REFUSEE(base):
    base["lignes"] = [dict(EAU_HERITEE)]
    d = poser_periode(base, "2026-09-18", "2026-07-21", 176.14).get_json()
    assert d["ok"] is False and "précède" in d["error"]


def test_LA_FACTURE_SUIVANTE_BORNE_LA_PRECEDENTE_AU_JOUR(base):
    """L'EPAL enchaîne sans trou : la précédente doit s'arrêter là où celle-ci commence."""
    precedente = {"id": "w1", "name": "Eau", "mode": "facture", "mois": "2026-07-01",
                  "amount": 176.14, "frequency": "monthly", "category": "", "notes": "",
                  "periode_debut": "2026-07-21", "periode_fin": "2026-09-18",
                  "valid_from": "2026-07-21", "valid_to": None, "active": True}
    base["lignes"] = [precedente]
    # ⚠️ LA PÉRIODE DOIT ÊTRE TERMINÉE : on est le 05/11 dans ce bouchon, et ma première
    # version la faisait courir jusqu'au 18/11. La route avait raison de la refuser.
    r = poser_periode(base, "2026-09-19", "2026-10-31", 168.0)
    assert r.get_json()["ok"] is True
    fermetures = [e for e in base["ecrits"]
                  if e[0] == "patch" and e[2].get("valid_to") == "2026-09-19"]
    assert len(fermetures) == 1 and fermetures[0][1] == {"id": "eq.w1"}, base["ecrits"]


def test_RESAISIR_LA_MEME_PERIODE_CORRIGE_AU_LIEU_DE_DUPLIQUER(base):
    precedente = {"id": "w1", "name": "Eau", "mode": "facture", "mois": "2026-07-01",
                  "amount": 176.14, "frequency": "monthly", "category": "", "notes": "",
                  "periode_debut": "2026-07-21", "periode_fin": "2026-09-18",
                  "valid_from": "2026-07-21", "valid_to": None, "active": True}
    base["lignes"] = [precedente]
    d = poser_periode(base, "2026-07-21", "2026-09-18", 180.0).get_json()
    assert d["ok"] is True and d["corrige"] is True and d["ancien"] == 176.14
    assert not any(e[0] == "insert" for e in base["ecrits"]), "une ligne a été dupliquée"


def test_CORRIGER_LA_FIN_DE_PERIODE_EST_UNE_CORRECTION(base):
    """
    ⚠️ CHANGER LA FIN CHANGE LE TAUX JOURNALIER, donc tous les mois couverts. Le montant seul
    ne suffit pas à décider qu'il n'y a « rien à faire ».
    """
    precedente = {"id": "w1", "name": "Eau", "mode": "facture", "mois": "2026-07-01",
                  "amount": 176.14, "frequency": "monthly", "category": "", "notes": "",
                  "periode_debut": "2026-07-21", "periode_fin": "2026-09-18",
                  "valid_from": "2026-07-21", "valid_to": None, "active": True}
    base["lignes"] = [precedente]
    d = poser_periode(base, "2026-07-21", "2026-09-20", 176.14).get_json()
    assert d["ok"] is True and d.get("inchange") is not True
    assert any(e[0] == "patch" and e[2].get("periode_fin") == "2026-09-20"
               for e in base["ecrits"]), base["ecrits"]


def test_UNE_FACTURE_SANS_FIN_RESTE_ACCEPTEE(base):
    """L'ancien geste — un mois, un montant — ne doit pas se mettre à refuser."""
    base["lignes"] = [dict(ELEC_SEPT), dict(LOYER)]
    r = poser(base, mois="2026-10", montant=86.40)
    assert r.get_json()["ok"] is True
    ins = [e[1] for e in base["ecrits"] if e[0] == "insert"][0]
    assert ins["periode_fin"] is None and ins["periode_debut"] == "2026-10-01"
