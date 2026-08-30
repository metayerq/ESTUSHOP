"""
Le produit vendu pour quelqu'un d'autre — et les trois façons de s'en attribuer la marge.

Un plat de chef invité passe par la caisse du café : il est facturé par nous, donc il est dans
notre chiffre d'affaires — mais l'argent repart. Le compter comme une vente ordinaire gonfle la
marge du catalogue du montant exact qu'on doit à quelqu'un d'autre.

LES TROIS FAUTES, AUCUNE NE LÈVE :

  1. traiter « 0 % de commission » comme « pas de commission » — tout le pop-up devient du
     revenu propre, et l'erreur est maximale précisément quand elle est totale ;
  2. remplacer le coût propre par le reversement au lieu de les additionner — le café qui
     fournit le pain d'un toast dont le reste est au chef supporte les deux ;
  3. rendre 0 % de marge sur un prix nul — une division impossible déguisée en performance.

Les chiffres viennent du pop-up réel d'Estudantina des 27 et 28 août : 95 toasts, 455,50 € HT
qui sont repartis chez le chef, à 0 % de commission.
"""
import sys

sys.path.insert(0, ".")

from app import product_economics


# ── 0 %, le cas le plus courant ───────────────────────────────────────────────

def test_zero_pourcent_ne_laisse_rien_au_cafe():
    """⚠️ LA FAUTE LA PLUS COÛTEUSE. À 0 %, la TOTALITÉ du hors taxe repart."""
    marge, pct, reverse = product_economics(price_ht=5.31, own_cost=0, commission_pct=0)
    assert marge == 0.0, "le café garde une marge sur un produit qu'il ne fait que collecter"
    assert pct == 0.0
    assert reverse == 5.31


def test_zero_se_distingue_de_pas_de_commission():
    """`None` et `0` ne veulent pas dire la même chose, et l'écart est le prix entier."""
    normal = product_economics(5.31, own_cost=1.20, commission_pct=None)
    depot = product_economics(5.31, own_cost=1.20, commission_pct=0)
    assert normal[0] == 4.11   # 5,31 − 1,20
    assert depot[0] == -1.20   # on reverse tout ET on a payé le pain
    assert normal[2] == 0.0
    assert depot[2] == 5.31


# ── Les commissions intermédiaires ────────────────────────────────────────────

def test_vingt_pourcent_garde_un_cinquieme():
    marge, pct, reverse = product_economics(10.0, own_cost=0, commission_pct=20)
    assert marge == 2.0
    assert pct == 20.0
    assert reverse == 8.0


def test_la_marge_pct_egale_la_commission_quand_le_cafe_ne_paie_rien():
    """Propriété qui rend le chiffre lisible : sans coût propre, marge % = commission."""
    for c in (0, 5, 10, 15, 20, 33, 50, 100):
        _, pct, _ = product_economics(7.40, own_cost=0, commission_pct=c)
        assert pct == float(c), f"à {c} % la marge affichée devrait être {c} %"


def test_cent_pourcent_est_un_produit_ordinaire():
    avec = product_economics(10.0, own_cost=2.0, commission_pct=100)
    sans = product_economics(10.0, own_cost=2.0, commission_pct=None)
    assert avec == sans


# ── Le coût propre s'ajoute ───────────────────────────────────────────────────

def test_le_cout_propre_s_ajoute_au_reversement():
    """⚠️ LA FAUTE N°2. Le café fournit le pain (1,20 €), le chef garde 80 % du reste.

    Les traiter comme exclusifs — reversement OU coût — sous-estimerait la dépense et
    remonterait la marge. Ils s'additionnent : on reverse ET on a payé.
    """
    marge, pct, reverse = product_economics(10.0, own_cost=1.20, commission_pct=20)
    assert reverse == 8.0
    assert marge == 0.8, "le pain fourni par le café a disparu du calcul"
    assert pct == 8.0


# ── Ce qui n'est pas calculable ───────────────────────────────────────────────

def test_sans_prix_la_marge_est_inconnue_pas_nulle():
    """⚠️ LA FAUTE N°3. Une division impossible ne doit pas ressortir en « 0 % »."""
    marge, pct, _ = product_economics(0, own_cost=0, commission_pct=0)
    assert marge is None
    assert pct is None
    marge2, pct2, _ = product_economics(None, own_cost=1, commission_pct=None)
    assert marge2 is None and pct2 is None


def test_une_commission_illisible_ne_fait_pas_tomber_le_calcul():
    """Ces valeurs viennent d'un formulaire et d'un JSON : rien ne garantit un nombre."""
    for mauvais in ("", "abc", None if False else "  "):
        marge, pct, reverse = product_economics(10.0, 0, commission_pct=mauvais)
        assert reverse == 10.0, "une commission illisible doit valoir 0, pas tout garder"
        assert marge == 0.0


def test_une_commission_hors_bornes_est_ramenee_dans_zero_cent():
    haut = product_economics(10.0, 0, commission_pct=140)
    bas = product_economics(10.0, 0, commission_pct=-20)
    assert haut[2] == 0.0, "au-delà de 100 % on ne reverse rien, on ne rend pas de l'argent"
    assert bas[2] == 10.0, "en dessous de 0 % tout repart, on ne facture pas le partenaire"


def test_un_cout_negatif_est_ignore_plutot_que_credite():
    """Un coût négatif serait un revenu déguisé : on le ramène à zéro."""
    marge, _, _ = product_economics(10.0, own_cost=-5, commission_pct=None)
    assert marge == 10.0


# ── Le cas réel ───────────────────────────────────────────────────────────────

def test_le_popup_reel_du_chef():
    """40 Toast Sardine à 5,31 € HT et 55 Toast Tartare à 4,42 €, tous à 0 %."""
    du_chef = 0.0
    for prix, qte in ((5.31, 40), (4.42, 55)):
        _, _, reverse = product_economics(prix, 0, commission_pct=0)
        du_chef += reverse * qte
    assert round(du_chef, 2) == 455.50, "le montant dû au chef ne tombe plus juste"


# ── Le stockage : ce qui part en base, et ce qui en revient ───────────────────
#
# ⚠️ CES TESTS EXISTENT PARCE QUE `0` EST FAUX EN PYTHON COMME EN JAVASCRIPT. Chaque
# couche traversée est une occasion de le rabattre sur « rien » : `or None`, `if
# commission:`, `data.get(...) or 0`. Une seule suffit à faire compter tout un pop-up
# comme du revenu propre — et rien ne lève.

import app as flask_app


def test_zero_est_ecrit_en_base_et_pas_rabattu_sur_rien(monkeypatch):
    ecrit = {}
    monkeypatch.setattr(flask_app, "_supa_upsert", lambda t, row: (ecrit.update(row), (True, None))[1])

    flask_app._save_recipe("Toast Sardine", [], "", 0, partner="Chef", commission_pct=0)

    assert ecrit["commission_pct"] == 0.0, "0 % a été perdu en chemin : le pop-up compterait comme du revenu propre"
    assert ecrit["partner"] == "Chef"


def test_sans_marquage_les_colonnes_ne_sont_pas_ecrites(monkeypatch):
    """Un produit ordinaire ne doit pas se voir poser un marquage vide en base."""
    ecrit = {}
    monkeypatch.setattr(flask_app, "_supa_upsert", lambda t, row: (ecrit.update(row), (True, None))[1])
    flask_app._save_recipe("Cappuccino", [{"name": "Café", "qty": 18, "unit": "g"}], "")
    assert "commission_pct" not in ecrit
    assert "partner" not in ecrit


def test_rendre_un_produit_au_cafe_efface_le_marquage(monkeypatch):
    """⚠️ Décocher la case doit ÉCRIRE `null`, pas omettre le champ.

    Omettre laisserait l'ancienne valeur en base : le produit continuerait d'être
    reversé à un partenaire qui n'a plus rien à voir avec lui.
    """
    ecrit = {}
    monkeypatch.setattr(flask_app, "_supa_upsert", lambda t, row: (ecrit.update(row), (True, None))[1])
    flask_app._save_recipe("Toast Sardine", [], "", 0, partner=None, commission_pct=None)
    # `partner=None` seul suffit à déclencher l'écriture des deux colonnes.
    assert "partner" in ecrit and ecrit["partner"] is None
    assert ecrit["commission_pct"] is None


def test_une_colonne_absente_ne_perd_pas_la_recette(monkeypatch):
    """Tolérance de migration : si le SQL n'a pas été passé, la recette se sauve quand même."""
    essais = []

    def faux_upsert(table, row):
        essais.append(dict(row))
        if "commission_pct" in row:
            return False, "column recipes.commission_pct does not exist"
        if "partner" in row:
            return False, "column recipes.partner does not exist"
        return True, None

    monkeypatch.setattr(flask_app, "_supa_upsert", faux_upsert)
    ok = flask_app._save_recipe("Toast", [], "", 0, partner="Chef", commission_pct=0)
    assert ok, "la recette a été perdue parce qu'une colonne manquait"
    assert "ingredients" in essais[-1]


def test_la_lecture_remonte_zero_et_pas_none(monkeypatch):
    monkeypatch.setattr(flask_app, "_supa_get", lambda *a, **k: [
        {"product_title": "Toast Sardine", "ingredients": [], "notes": "",
         "waste_pct": 0, "partner": "Chef", "commission_pct": 0},
        {"product_title": "Cappuccino", "ingredients": [], "notes": "", "waste_pct": 0},
    ])
    r = flask_app._load_recipes()
    assert r["Toast Sardine"]["commission_pct"] == 0, "0 est remonté comme absence"
    assert r["Cappuccino"]["commission_pct"] is None, "un produit normal ne doit pas être marqué"
