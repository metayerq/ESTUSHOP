"""
Quatre correctifs de la même famille : un ratio ne mélange pas mesure et hypothèse sans le dire.

 1. Le point mort convertissait un seuil HT en TTC avec le taux de TVA du business plan (13 %),
    puis le comparait à un CA TTC RÉEL. Avec des livres à 6 %, le taux effectif tombe vers 10 % :
    le « manque » était gonflé et le pourcentage d'atteinte sous-estimé.
 2. Une période sans aucun jour d'ouverture se voyait facturer un jour fictif — `count_open_days`
    plafonne à ≥ 1 pour éviter les divisions par zéro, ce qui transformait « aucune ouverture »
    en « une journée » : 197 € de charges et un EBITDA de −197 € pour un mardi-mercredi fermés.
 3. (prime cost — côté client, couvert par tests/test_prime_cost.js)
 4. Le seuil du mois descendait de la marge de la période AFFICHÉE, dans une zone qui s'annonce
    « indépendante du preset ».
"""
import sys
from datetime import date
sys.path.insert(0, ".")

import pytest
import vendus


@pytest.fixture(autouse=True)
def _pas_de_reseau(monkeypatch):
    """Les charges viennent de Supabase ; on les fournit en dur pour isoler les calculs."""
    def _fake(table, params=None):
        if table == "charges_fixes":
            return [{"label": "loyer", "amount": 1000.0, "frequency": "monthly", "active": True}]
        return []
    monkeypatch.setattr(vendus, "_supa_get_economics", _fake)


def _docs(ca_ht, ca_ttc, n=10):
    """n documents se partageant le CA — le ratio TTC/HT est ce qui compte ici."""
    return [{"type": "FT", "amount_net": ca_ht / n, "amount_gross": ca_ttc / n, "items": []}
            for _ in range(n)]


# ── 1 · TVA du seuil : mesurée, pas supposée ─────────────────────────────────

def test_le_seuil_utilise_la_tva_reellement_encaissee():
    """
    CA 1000 HT / 1060 TTC → taux effectif 6 %, pas les 13 % du business plan.
    Le seuil TTC doit suivre ce 6 %.
    """
    eco = vendus.daily_economics(_docs(1000.0, 1060.0), {}, n_days=1,
                                 from_date=date(2026, 8, 3), to_date=date(2026, 8, 3),
                                 cogs_agg=(300.0, 1000.0, 1000.0))
    assert eco["seuil_tva_src"] == "mesure"
    assert eco["seuil_tva_pct"] == 6.0
    ratio = eco["seuil_ca_ttc_jour"] / eco["seuil_ca_ht"]
    assert abs(ratio - 1.06) < 0.001, f"le seuil est converti à {ratio:.3f}, pas 1.06"


def test_sans_ca_on_retombe_sur_l_hypothese_et_on_le_dit():
    """Aucune vente : le taux effectif n'existe pas. On assume — et `seuil_tva_src` l'annonce."""
    eco = vendus.daily_economics([], {}, n_days=1,
                                 from_date=date(2026, 8, 3), to_date=date(2026, 8, 3))
    assert eco["seuil_tva_src"] == "hypothese"
    assert eco["seuil_tva_pct"] == 13.0


# ── 2 · Une période fermée ne compte pas un jour ─────────────────────────────

def test_une_periode_entierement_fermee_ne_facture_pas_un_jour_fictif():
    """
    Mardi 4 → mercredi 5 août : le café est fermé les deux jours. Aucune charge de période
    n'est imputable, et aucun seuil n'est calculable. `None`, jamais 0 — un 0 se lirait
    « la période n'a rien coûté ».
    """
    eco = vendus.daily_economics([], {}, n_days=2,
                                 from_date=date(2026, 8, 4), to_date=date(2026, 8, 5))
    assert eco["open_days"] == 0
    assert eco["cout_total_periode"] is None
    assert eco["seuil_ca_ttc"] is None
    assert eco["ebitda_ht"] is None


def test_une_periode_avec_un_jour_ouvre_compte_bien_ce_jour():
    """Contrepartie : le lundi 3 août est ouvert, la charge du jour doit apparaître."""
    eco = vendus.daily_economics([], {}, n_days=1,
                                 from_date=date(2026, 8, 3), to_date=date(2026, 8, 3))
    assert eco["open_days"] == 1
    assert eco["cout_total_periode"] is not None and eco["cout_total_periode"] > 0
