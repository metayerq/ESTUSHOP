"""
MODIFIER UNE CHARGE SANS RÉÉCRIRE LE PASSÉ.

⚠️ AVANT CE CHANGEMENT, augmenter le loyer en septembre changeait l'EBITDA de juin — partout,
sans que rien ne le signale. Et supprimer un poste le retirait de TOUS les mois passés : trois
mois qui devenaient soudain rentables.

⚠️ AUCUNE DE CES DEUX ERREURS NE LEVAIT. Elles produisaient des chiffres cohérents entre eux, et
faux.
"""

from datetime import date, timedelta

import pytest

import app as flask_app

LIGNE = {"id": "c1", "name": "Loyer", "amount": 700.0, "frequency": "monthly",
         "category": "local", "notes": "", "active": True,
         "valid_from": None, "valid_to": None}


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 9, 21))
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a: "écrit")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


@pytest.fixture
def base(monkeypatch):
    """Capture ce qui est écrit, et laisse tout réussir."""
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(LIGNE)])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(("patch", t, f, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_insert",
                        lambda t, r: (ecrits.append(("insert", t, r)), (True, None))[1])
    # ⚠️ LA FUSION EST PIÉGÉE, PAS SIMULÉE. Une ligne de remplacement qui passerait par
    # `merge-duplicates` écraserait la ligne clôturée — l'historique que tout ceci protège.
    monkeypatch.setattr(flask_app, "_supa_upsert",
                        lambda t, r: (ecrits.append(("fusion", t, r)), (True, None))[1])
    return ecrits


# ── La date d'effet ──────────────────────────────────────────────────────────────────────────

def test_une_date_deffet_passee_est_refusee(admin, base):
    """
    ⚠️ AUTORISER UNE DATE PASSÉE RENDRAIT LE VERSIONNEMENT INUTILE : on pourrait réécrire juin
    depuis septembre, ce qu'on vient précisément d'empêcher.
    """
    r = admin.patch("/api/charges/c1",
                    json={"amount": 750, "reason": "hausse", "effective_from": "2026-06-01"})
    assert r.status_code == 400
    assert not base, "la base a été modifiée malgré une date rétroactive"


def test_aujourdhui_est_deja_trop_tard(admin, base):
    """Le jour courant a déjà pu être lu ; la borne est demain."""
    r = admin.patch("/api/charges/c1",
                    json={"amount": 750, "reason": "hausse", "effective_from": "2026-09-21"})
    assert r.status_code == 400


def test_sans_date_leffet_est_le_premier_du_mois_prochain(admin, base):
    """Les charges se pensent en mois — un loyer ne change pas un 17."""
    r = admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse annuelle"})
    assert r.get_json()["effet"] == "2026-10-01"


def test_decembre_bascule_sur_lannee_suivante(admin, base, monkeypatch):
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 12, 10))
    r = admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    assert r.get_json()["effet"] == "2027-01-01"


# ── La clôture et le remplacement ────────────────────────────────────────────────────────────

def test_un_changement_de_montant_clot_et_remplace(admin, base):
    admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse annuelle"})
    patch = [e for e in base if e[0] == "patch"][0]
    upsert = [e for e in base if e[0] == "insert"][0]
    assert patch[3]["valid_to"] == "2026-10-01"
    assert upsert[2]["valid_from"] == "2026-10-01"
    assert upsert[2]["amount"] == 750
    assert upsert[2]["valid_to"] is None


def test_la_nouvelle_ligne_nherite_pas_de_lancien_identifiant(admin, base):
    """
    ⚠️ RÉUTILISER L'ID ÉCRASERAIT LA LIGNE CLÔTURÉE — et le passé avec elle. C'est exactement
    le bogue que cette migration corrige, reproduit d'une autre manière.
    """
    admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    upsert = [e for e in base if e[0] == "insert"][0]
    assert "id" not in upsert[2]


def test_la_nouvelle_ligne_garde_le_nom_et_la_categorie(admin, base):
    """Sinon le poste change d'identité au moindre changement de montant."""
    admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    upsert = [e for e in base if e[0] == "insert"][0]
    assert upsert[2]["name"] == "Loyer"
    assert upsert[2]["category"] == "local"


def test_active_ne_devance_pas_la_date_deffet(admin, base):
    """
    ⚠️ LA CAISSE MESA LIT ENCORE `active=eq.true`, ET CE DRAPEAU SUIT LA DATE. Le passer à faux
    dès la saisie ferait chuter le coût du jour un mois avant la clôture, et la ligne neuve,
    active tout de suite, ferait payer le nouveau loyer un mois en avance. Les deux erreurs se
    lisent au comptoir, sur le point mort.
    """
    admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    patch = [e for e in base if e[0] == "patch"][0]
    upsert = [e for e in base if e[0] == "insert"][0]
    assert patch[3]["active"] is True, "la charge en cours a cessé de compter trop tôt"
    assert upsert[2]["active"] is False, "le nouveau montant compte déjà"


def test_un_effet_immediat_bascule_tout_de_suite(admin, base, monkeypatch):
    """Quand la date d'effet est demain et qu'on est demain, la bascule a bien lieu."""
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 10, 1))
    admin.patch("/api/charges/c1",
                json={"amount": 750, "reason": "hausse", "effective_from": "2026-10-01"})
    # 2026-10-01 est aujourd'hui : refusé comme rétroactif, donc rien n'est écrit.
    assert not base
    admin.patch("/api/charges/c1",
                json={"amount": 750, "reason": "hausse", "effective_from": "2026-10-02"})
    assert [e for e in base if e[0] == "insert"][0][2]["active"] is False


def test_le_rattrapage_fait_basculer_le_jour_venu(monkeypatch):
    """
    ⚠️ AUCUNE ÉCRITURE NE FAIT BASCULER UNE DATE. Une clôture au 1er novembre est décidée en
    septembre ; entre les deux, rien n'est écrit. Sans rattrapage, la ligne remplacée resterait
    active jusqu'au prochain clic de quelqu'un sur la page.
    """
    lignes = [
        {"id": "a", "active": True,  "valid_from": None, "valid_to": "2026-10-01"},   # clôturée
        {"id": "b", "active": False, "valid_from": "2026-10-01", "valid_to": None},   # reprend
        {"id": "c", "active": True,  "valid_from": None, "valid_to": None},           # inchangée
    ]
    ecrits = {}
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: lignes)
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.__setitem__(f["id"], d), (True, None))[1])
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 10, 15))
    assert flask_app._resynchroniser_active("charges_fixes") == 2
    assert ecrits == {"eq.a": {"active": False}, "eq.b": {"active": True}}


def test_un_echec_a_mi_chemin_remet_la_ligne_en_service(admin, monkeypatch):
    """
    ⚠️ SANS RETOUR EN ARRIÈRE, la charge resterait clôturée et aucune ligne ne la remplacerait :
    le poste disparaîtrait des mois à venir, en silence.
    """
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(LIGNE)])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(d), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_insert", lambda t, r: (False, "refusé"))
    r = admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    assert r.status_code == 502
    assert ecrits[-1] == {"valid_to": None, "active": True}, "la ligne est restée clôturée"


# ── Le motif ─────────────────────────────────────────────────────────────────────────────────

def test_un_changement_de_montant_exige_un_motif(admin, base):
    r = admin.patch("/api/charges/c1", json={"amount": 750})
    assert r.status_code == 400
    assert "motif" in r.get_json()["error"]
    assert not base


def test_corriger_un_libelle_nexige_ni_motif_ni_date(admin, base):
    """
    ⚠️ CORRIGER UNE FAUTE DE FRAPPE N'EST PAS CHANGER UN LOYER. Demander un motif et une date
    d'effet pour remettre un accent ferait contourner le formulaire.
    """
    r = admin.patch("/api/charges/c1", json={"name": "Loyer (Rua da Indústria)"})
    assert r.status_code == 200
    assert not [e for e in base if e[0] == "insert"], "une nouvelle ligne a été créée"


def test_un_montant_identique_nest_pas_un_changement(admin, base):
    """Réenregistrer sans rien changer ne doit pas créer une ligne ni exiger un motif."""
    r = admin.patch("/api/charges/c1", json={"amount": 700, "notes": "à revoir"})
    assert r.status_code == 200
    assert not [e for e in base if e[0] == "insert"]


# ── La suppression devient une clôture ───────────────────────────────────────────────────────

def test_supprimer_une_charge_la_cloture(admin, base):
    """
    ⚠️ UN `DELETE` RETIRAIT LE LOYER DE MAI, JUIN ET JUILLET. Une charge qui s'arrête a une
    date : le poste reste, borné au jour où il cesse.
    """
    r = admin.delete("/api/charges/c1", json={"effective_from": "2026-11-01"})
    assert r.status_code == 200
    patch = [e for e in base if e[0] == "patch"][0]
    assert patch[3]["valid_to"] == "2026-11-01"


def test_la_suppression_nefface_jamais_rien(monkeypatch, admin):
    supprimes = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(LIGNE)])
    monkeypatch.setattr(flask_app, "_supa_patch", lambda t, f, d: (True, None))
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: supprimes.append(v) or True)
    admin.delete("/api/charges/c1", json={})
    assert not supprimes, "un DELETE destructif a eu lieu"


# ── L'accès ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_touche_aux_charges(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    c = flask_app.app.test_client()
    assert c.patch("/api/charges/c1", json={"amount": 1}).status_code in (401, 403)
    assert c.delete("/api/charges/c1", json={}).status_code in (401, 403)


# ── Le chemin que l'écran emprunte réellement ────────────────────────────────────────────────
#
# ⚠️ LE FORMULAIRE ENREGISTRE PAR `POST`, MÊME POUR UNE MODIFICATION. Tout le garde ci-dessus
# vivait sur `PATCH`, que l'écran n'appelle jamais pour un montant : la protection était réelle,
# testée, et aucun clic ne la traversait. Ces tests-là passent par la porte que Quentin pousse.

def test_enregistrer_le_formulaire_ne_reecrit_pas_le_passe(admin, base):
    r = admin.post("/api/charges",
                   json={"id": "c1", "name": "Loyer", "amount": 750, "frequency": "monthly",
                         "reason": "hausse annuelle"})
    assert r.status_code == 200
    upsert = [e for e in base if e[0] == "insert"][0]
    assert "id" not in upsert[2], "la ligne d'origine a été écrasée"
    assert upsert[2]["valid_from"] == "2026-10-01"


def test_le_formulaire_exige_aussi_un_motif(admin, base):
    r = admin.post("/api/charges",
                   json={"id": "c1", "name": "Loyer", "amount": 750, "frequency": "monthly"})
    assert r.status_code == 400
    assert not base


def test_creer_une_charge_reste_un_simple_ajout(admin, base):
    """Un poste NOUVEAU n'a rien à clôturer, et n'a pas à se justifier."""
    r = admin.post("/api/charges", json={"name": "Wi-Fi", "amount": 40, "frequency": "monthly"})
    assert r.status_code == 200
    assert [e for e in base if e[0] == "insert"]


def test_une_charge_creee_ne_sapplique_pas_aux_mois_clos(admin, base):
    """
    ⚠️ `valid_from` NUL VEUT DIRE « DEPUIS TOUJOURS ». Sans borne à la création, ajouter le Wi-Fi
    en septembre l'ajoutait à mai, juin et juillet — trois mois clos qui changeaient d'EBITDA.
    """
    admin.post("/api/charges", json={"name": "Wi-Fi", "amount": 40, "frequency": "monthly"})
    assert [e for e in base if e[0] == "insert"][0][2]["valid_from"] == "2026-09-01"


def test_on_peut_enregistrer_une_charge_oubliee_qui_court_depuis_mai(admin, base):
    """Une date passée est permise à la CRÉATION : elle est écrite, pas subie."""
    admin.post("/api/charges",
               json={"name": "Assurance", "amount": 60, "effective_from": "2026-05-01"})
    assert [e for e in base if e[0] == "insert"][0][2]["valid_from"] == "2026-05-01"


# ── Les salariés ─────────────────────────────────────────────────────────────────────────────
#
# ⚠️ MÊME PROBLÈME, ENJEU PLUS LOURD. Augmenter quelqu'un en septembre changeait sa paie de
# juin ; un départ l'effaçait de tout l'historique — alors que ces mois-là, il a bien été payé.
# `api_employees_patch` recopiait en plus le JSON reçu dans la base, champ par champ, sans
# contrôle de rôle propre.

SALARIE = {"id": "e1", "name": "Ana", "type": "full_time", "gross_monthly": 900.0,
           "hours_week": 40, "tsu_exempt": False, "meal_card_daily": 10.20,
           "days_per_month": 21.25, "notes": "", "active": True,
           "valid_from": None, "valid_to": None}


@pytest.fixture
def equipe(monkeypatch):
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(SALARIE)])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(("patch", t, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "_supa_insert",
                        lambda t, r: (ecrits.append(("insert", t, r)), (True, None))[1])
    # ⚠️ LA FUSION EST PIÉGÉE, PAS SIMULÉE. Une ligne de remplacement qui passerait par
    # `merge-duplicates` écraserait la ligne clôturée — l'historique que tout ceci protège.
    monkeypatch.setattr(flask_app, "_supa_upsert",
                        lambda t, r: (ecrits.append(("fusion", t, r)), (True, None))[1])
    return ecrits


def test_une_augmentation_ne_change_pas_la_paie_de_juin(admin, equipe):
    r = admin.post("/api/employees",
                   json={"id": "e1", "name": "Ana", "gross_monthly": 1000,
                         "reason": "augmentation annuelle"})
    assert r.status_code == 200
    upsert = [e for e in equipe if e[0] == "insert"][0]
    assert "id" not in upsert[2], "la fiche a été écrasée"
    assert upsert[2]["gross_monthly"] == 1000
    assert upsert[2]["valid_from"] == "2026-10-01"
    assert [e for e in equipe if e[0] == "patch"][0][2]["valid_to"] == "2026-10-01"


def test_une_augmentation_exige_un_motif(admin, equipe):
    assert admin.post("/api/employees",
                      json={"id": "e1", "name": "Ana", "gross_monthly": 1000}).status_code == 400
    assert not equipe


def test_passer_en_extra_est_un_changement_de_cout(admin, equipe):
    """Un extra n'a ni 14e mois ni carte repas : le type change le coût de 40 %."""
    r = admin.patch("/api/employees/e1", json={"type": "extra", "reason": "passage en extra"})
    assert r.status_code == 200
    assert [e for e in equipe if e[0] == "insert"][0][2]["type"] == "extra"


def test_lexemption_tsu_est_un_changement_de_cout(admin, equipe):
    r = admin.patch("/api/employees/e1", json={"tsu_exempt": True, "reason": "1er emploi"})
    assert [e for e in equipe if e[0] == "insert"][0][2]["tsu_exempt"] is True


def test_corriger_un_horaire_indicatif_ne_demande_rien(admin, equipe):
    """
    ⚠️ `hours_week` N'ENTRE PAS DANS LE COÛT. `cout_employe_mensuel` ne lit que le brut, le type,
    l'exemption TSU et la carte repas. Exiger un motif pour un horaire indicatif ferait
    contourner le formulaire.
    """
    r = admin.patch("/api/employees/e1", json={"hours_week": 35})
    assert r.status_code == 200
    assert not [e for e in equipe if e[0] == "insert"]


def test_un_depart_cloture_la_fiche(admin, equipe):
    r = admin.delete("/api/employees/e1", json={"effective_from": "2026-11-01"})
    assert r.status_code == 200
    assert [e for e in equipe if e[0] == "patch"][0][2]["valid_to"] == "2026-11-01"


def test_un_depart_neface_pas_les_mois_ou_la_personne_a_ete_payee(monkeypatch, admin):
    supprimes = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(SALARIE)])
    monkeypatch.setattr(flask_app, "_supa_patch", lambda t, f, d: (True, None))
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: supprimes.append(v) or True)
    admin.delete("/api/employees/e1", json={})
    assert not supprimes


def test_une_embauche_nest_pas_payee_depuis_mai(admin, equipe):
    admin.post("/api/employees", json={"name": "Rui", "gross_monthly": 870})
    assert [e for e in equipe if e[0] == "insert"][0][2]["valid_from"] == "2026-09-01"


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_touche_aux_salaires(monkeypatch, role):
    """
    ⚠️ `api_employees_patch` N'AVAIT AUCUN CONTRÔLE DE RÔLE PROPRE — elle ne devait sa
    protection qu'au garde global. Une exception ajoutée un jour dans `_require_auth`, et
    n'importe qui réécrivait les salaires.
    """
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    c = flask_app.app.test_client()
    assert c.patch("/api/employees/e1", json={"gross_monthly": 1}).status_code in (401, 403)
    assert c.delete("/api/employees/e1", json={}).status_code in (401, 403)


def test_le_rattrapage_ne_ressuscite_pas_ce_qui_a_ete_eteint_a_la_main(monkeypatch):
    """
    ⚠️ LE RATTRAPAGE A FAILLI RALLUMER TOUT CE QUI ÉTAIT ÉTEINT. Une charge désactivée avant que
    les dates existent n'a aucune borne : `applicable()` la disait applicable, et le rattrapage
    remettait `active` à vrai. Un logiciel résilié qui se remet à coûter 120 € par mois, et
    l'écran qui le montre de nouveau actif — sans que personne ait rien fait.
    """
    lignes = [{"id": "vieux", "active": False, "valid_from": None, "valid_to": None}]
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: lignes)
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append((f, d)), (True, None))[1])
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: date(2026, 9, 21))
    assert flask_app._resynchroniser_active("charges_fixes") == 0
    assert not ecrits


def test_la_ligne_de_remplacement_ne_passe_jamais_par_une_fusion(admin, base):
    """
    ⚠️ `_supa_upsert` ENVOIE `resolution=merge-duplicates`. Sur une contrainte d'unicité, il
    fusionne au lieu d'ajouter : la ligne neuve écraserait la ligne clôturée — l'historique que
    tout ce mécanisme existe pour garder. Le même piège qu'avec `card_campaigns`, où une
    campagne relancée effaçait sa propre trace.

    ⚠️ ET UN ÉCHEC DOIT ÊTRE BRUYANT. Mieux vaut un message d'erreur et une clôture annulée
    qu'un passé réécrit en silence : des deux issues, une seule se voit.
    """
    admin.patch("/api/charges/c1", json={"amount": 750, "reason": "hausse"})
    assert not [e for e in base if e[0] == "fusion"]


def test_creer_une_charge_ne_fusionne_pas_avec_une_homonyme(admin, base):
    """
    ⚠️ AVEC LE VERSIONNEMENT, « LOYER » EXISTE LÉGITIMEMENT PLUSIEURS FOIS. Une fusion sur le
    nom écraserait la ligne précédente au lieu d'en ouvrir une neuve — et c'est précisément ce
    que fait le bouton « Reopen… » : rouvrir un poste qui porte déjà son nom dans l'historique.
    """
    admin.post("/api/charges", json={"name": "Loyer", "amount": 750})
    assert not [e for e in base if e[0] == "fusion"]
    assert [e for e in base if e[0] == "insert"]


def test_linsertion_franche_ne_demande_aucune_fusion(monkeypatch):
    """
    ⚠️ LA GARANTIE VIT DANS UN EN-TÊTE, ET RIEN NE LE REGARDAIT. Les tests ci-dessus simulent
    `_supa_insert` : ils prouvent qu'on l'appelle, pas qu'il insère. Un `Prefer:
    resolution=merge-duplicates` ajouté ici un jour écraserait la ligne clôturée, et les douze
    tests du dessus continueraient de passer au vert.
    """
    vus = {}

    class Reponse:
        ok = True

    monkeypatch.setattr(flask_app._req, "post",
                        lambda url, json, headers: (vus.update(headers), Reponse())[1])
    assert flask_app._supa_insert("charges_fixes", {"name": "Loyer"}) == (True, None)
    assert "merge-duplicates" not in vus.get("Prefer", "")


def test_lecriture_fusionnante_existe_toujours_pour_qui_en_a_besoin(monkeypatch):
    """`_supa_upsert` reste légitime ailleurs — les visites carte s'y appuient (upsert sur pid)."""
    vus = {}

    class Reponse:
        ok = True

    monkeypatch.setattr(flask_app._req, "post",
                        lambda url, json, headers: (vus.update(headers), Reponse())[1])
    flask_app._supa_upsert("card_visits", {"pid": "x"})
    assert "merge-duplicates" in vus.get("Prefer", "")


# ── Se raviser ───────────────────────────────────────────────────────────────────────────────
#
# ⚠️ ANNULER UN ARRÊT PROGRAMMÉ ÉTAIT IMPOSSIBLE. « Reopen… » ouvre une ligne NEUVE à une date :
# juste pour une reprise après interruption, absurde pour un arrêt décidé le matin et regretté
# l'après-midi — on se retrouvait avec deux fiches pour quelqu'un qui n'était jamais parti.

@pytest.fixture
def programmee(monkeypatch):
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [dict(SALARIE, valid_to="2026-10-01")])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(d), (True, None))[1])
    return ecrits


def test_annuler_un_arret_a_venir_remet_le_poste_en_service(admin, programmee):
    r = admin.post("/api/employees/e1/annuler")
    assert r.status_code == 200
    assert programmee[0] == {"valid_to": None, "active": True}


def test_annuler_un_arret_deja_pris_est_refuse(admin, monkeypatch):
    """
    ⚠️ RETIRER UNE BORNE DÉJÀ FRANCHIE REMET LE POSTE EN SERVICE SUR TOUTE L'INTERRUPTION. Des
    mois déjà lus qui changent d'EBITDA — précisément ce que ce mécanisme existe pour empêcher.
    Après la date, la bonne porte est « Reopen… », qui laisse l'interruption dans l'historique.
    """
    ecrits = []
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [dict(SALARIE, valid_to="2026-08-01")])
    monkeypatch.setattr(flask_app, "_supa_patch",
                        lambda t, f, d: (ecrits.append(d), (True, None))[1])
    r = admin.post("/api/employees/e1/annuler")
    assert r.status_code == 400
    assert "Reopen" in r.get_json()["error"]
    assert not ecrits


def test_la_borne_atteinte_aujourdhui_nest_plus_annulable(admin, monkeypatch):
    """La journée a déjà pu être lue : la borne du jour est franchie."""
    monkeypatch.setattr(flask_app, "_supa_get",
                        lambda t, p: [dict(SALARIE, valid_to="2026-09-21")])
    monkeypatch.setattr(flask_app, "_supa_patch", lambda t, f, d: (True, None))
    assert admin.post("/api/employees/e1/annuler").status_code == 400


def test_annuler_sans_arret_programme_le_dit(admin, equipe):
    r = admin.post("/api/employees/e1/annuler")
    assert r.status_code == 400
    assert not equipe


# ── Effacer ce qui n'aurait jamais dû exister ────────────────────────────────────────────────
#
# ⚠️ CETTE PORTE EST DANGEREUSE ET ELLE EST NÉCESSAIRE. Une fiche créée par erreur n'a aucun
# passé à préserver, et « Stop… » la laisserait dans la liste pour toujours. Ne pas l'offrir
# revient à demander de vivre avec ses fautes de saisie — ce que personne ne fait : on met le
# montant à zéro, et la ligne fausse reste, avec un zéro que plus rien n'explique.

def test_la_suppression_definitive_efface_vraiment(admin, monkeypatch):
    supprimes = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(SALARIE)])
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: supprimes.append((t, v)) or True)
    r = admin.delete("/api/employees/e1/definitif")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert supprimes == [("employees", "e1")]


def test_la_ligne_est_journalisee_avant_de_disparaitre(admin, monkeypatch):
    """
    ⚠️ APRÈS, IL NE RESTE RIEN À DÉCRIRE. C'est la seule trace qui dira un jour pourquoi un mois
    a changé de chiffre — et elle doit être écrite pendant que la ligne existe encore.
    """
    ordre = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [dict(SALARIE)])
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: ordre.append("efface") or True)
    monkeypatch.setattr(flask_app, "_journal_action",
                        lambda *a: ordre.append(("journal", a[3])) or "écrit")
    admin.delete("/api/employees/e1/definitif")
    assert [o[0] if isinstance(o, tuple) else o for o in ordre] == ["journal", "efface"]
    assert ordre[0][1]["name"] == "Ana", "la ligne effacée n'est pas dans le journal"


def test_supprimer_un_poste_inconnu_nefface_rien(admin, monkeypatch):
    supprimes = []
    monkeypatch.setattr(flask_app, "_supa_get", lambda t, p: [])
    monkeypatch.setattr(flask_app, "_supa_delete",
                        lambda t, c, v: supprimes.append(v) or True)
    assert admin.delete("/api/charges/inconnu/definitif").status_code == 404
    assert not supprimes


@pytest.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_efface_ou_annule(monkeypatch, role):
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    c = flask_app.app.test_client()
    assert c.delete("/api/employees/e1/definitif").status_code in (401, 403)
    assert c.delete("/api/charges/c1/definitif").status_code in (401, 403)
    assert c.post("/api/employees/e1/annuler").status_code in (401, 403)
    assert c.post("/api/charges/c1/annuler").status_code in (401, 403)
