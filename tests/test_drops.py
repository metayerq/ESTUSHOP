"""
LES PRÉCOMMANDES DES CHEFS — CE QUE LE BUREAU EN DÉCIDE (`drops.py`).

La vente elle-même (créneaux, stock, panier, paiement, facture) vit dans la caisse Mesa et s'y
teste. Ici : les dates des soirées, ce qui empêche d'ouvrir, le bilan du chef.
"""

from datetime import date

import pytest

import drops as D


# ── Les soirées ──────────────────────────────────────────────────────────────────────────────

def test_un_soir():
    assert D.jours_de_l_operation({"kind": "unique", "jour": "2026-11-15"}) == [date(2026, 11, 15)]


def test_tous_les_jeudis_dun_mois():
    jours = D.jours_de_l_operation({"kind": "hebdo", "debut": "2026-11-01", "fin": "2026-11-30",
                                    "jours": [3]})
    assert [j.isoformat() for j in jours] == ["2026-11-05", "2026-11-12", "2026-11-19", "2026-11-26"]


def test_une_semaine_daffilee():
    assert len(D.jours_de_l_operation({"kind": "plage", "debut": "2026-11-16", "fin": "2026-11-22"})) == 7


@pytest.mark.parametrize("duree", [
    {"kind": "unique", "jour": "2026-02-30"},
    {"kind": "plage", "debut": "2026-11-22", "fin": "2026-11-16"},
    {"kind": "hebdo", "debut": "2026-11-01", "fin": "2026-11-30", "jours": []},
    {"kind": "hebdo", "debut": "2026-11-01", "fin": "2026-11-30", "jours": [3, 7]},
    {"kind": "hebdo", "debut": "2026-11-02", "fin": "2026-11-04", "jours": [6]},
    {"kind": "semestre"},
    None,
])
def test_une_duree_illisible_est_refusee(duree):
    with pytest.raises(D.DropInvalide):
        D.jours_de_l_operation(duree)


def test_une_annee_de_trop_est_une_faute_de_frappe():
    with pytest.raises(D.DropInvalide):
        D.jours_de_l_operation({"kind": "plage", "debut": "2026-11-01", "fin": "2027-11-01"})
    assert len(D.jours_de_l_operation({"kind": "plage", "debut": "2026-01-01", "fin": "2026-03-03"})) == 62


def test_les_reglages_dune_soiree_ont_leurs_defauts():
    s = D.soiree_propre({"capacite_creneau": "8"})
    assert s == {**D.SOIREE_DEFAUT, "capacite_creneau": 8}
    # Les heures de Postgres arrivent avec leurs secondes.
    assert D.soiree_propre({"ouvre": "18:00:00"})["ouvre"] == "18:00"


@pytest.mark.parametrize("brut", [
    {"ouvre": "23:00", "ferme": "18:00"},
    {"retrait_debut": "22:30", "retrait_fin": "22:30"},
    {"pas_minutes": 7},
    {"capacite_creneau": 0},
    {"limite": "4pm"},
    {"capacite_creneau": "beaucoup"},
])
def test_une_soiree_incoherente_est_refusee_en_francais(brut):
    with pytest.raises(D.DropInvalide):
        D.soiree_propre(brut)


def test_un_champ_inconnu_ne_passe_pas_en_base():
    assert "etablissement" not in D.soiree_propre({"etablissement": "autre-cafe"})


def test_le_slug_dun_plat():
    assert D.slug("Salmon & shiso onigiri") == "salmon-shiso-onigiri"
    assert D.slug("Thé glacé à l'ume") == "the-glace-a-l-ume"
    assert D.identifiant_valide("toro-toro-nov-2026")
    assert not D.identifiant_valide("Toro Toro")
    assert not D.identifiant_valide("ab")


# ── Ouvrir ───────────────────────────────────────────────────────────────────────────────────

PLATS = [
    {"nom": "Salmon onigiri", "prix_cents": 450, "vendus_product_id": 101, "actif": True},
    {"nom": "Umeboshi onigiri", "prix_cents": 390, "vendus_product_id": None, "actif": True},
    {"nom": "Unagi onigiri", "prix_cents": 550, "vendus_product_id": None, "actif": False},
]


def test_ce_qui_empeche_douvrir_plat_par_plat():
    assert D.empechements(PLATS, {101: 4.5}, ["2026-11-15"]) == [
        "Umeboshi onigiri : pas de produit Vendus"]


def test_un_centime_decart_avec_vendus_bloque():
    assert D.empechements(PLATS[:1], {101: 4.49}, ["2026-11-15"]) == [
        "Salmon onigiri : prix du menu 4.50 € ≠ prix Vendus 4.49 €"]
    assert D.empechements(PLATS[:1], {}, ["2026-11-15"]) == [
        "Salmon onigiri : produit Vendus 101 introuvable"]


def test_sans_menu_ni_soiree():
    assert D.empechements([], {}, []) == ["Le menu est vide", "Aucune soirée prévue"]


def test_tout_est_pret():
    assert D.empechements(PLATS[:1], {101: 4.5}, ["2026-11-15"]) == []


# ── Le bilan ─────────────────────────────────────────────────────────────────────────────────

def test_vingt_pour_cent_du_ttc_et_la_part_du_chef_est_le_reste():
    b = D.bilan([
        {"statut": "payee", "total_cents": 1350},
        {"statut": "retiree", "total_cents": 3333},
        {"statut": "remboursee", "total_cents": 9999},
        {"statut": "refusee", "total_cents": 9999},
        {"statut": "en_attente", "total_cents": 9999},
        {"statut": "abandonnee", "total_cents": 9999},
    ], [(3, 450)], 20)
    assert b == {"en_ligne_cents": 4683, "sur_place_cents": 1350, "encaisse_cents": 6033,
                 "commission_cents": 1207, "part_chef_cents": 4826}


def test_deux_arrondis_separes_creeraient_un_centime():
    # 12,5 % de 4 centimes = 0,5 → 1 ; la part du chef est 3, pas round(3,5) = 4.
    b = D.bilan([{"statut": "payee", "total_cents": 4}], [], 12.5)
    assert (b["commission_cents"], b["part_chef_cents"]) == (1, 3)


def test_le_demi_centime_monte_meme_quand_round_le_ferait_descendre():
    # 2,5 centimes : `round()` donnerait 2 (arrondi bancaire).
    assert D.bilan([{"statut": "payee", "total_cents": 25}], [], 10)["commission_cents"] == 3
