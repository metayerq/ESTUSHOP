"""
CE QU'UN LIBELLÉ DE PAIEMENT DÉSIGNE.

⚠️ CE CLASSEMENT DÉCIDE DE L'ÉCART DE RÉCONCILIATION. Un libellé carte rangé dans « autre » fait
tomber « Facturé carte » à zéro — et l'écran, qui est conçu pour rendre les écarts actionnables,
annonce alors un écart égal au chiffre d'affaires du jour. C'est arrivé le 21/09/2026 : le vrai
libellé du café est « Cartão de Crédito », et la comparaison portait sur le libellé ENTIER.

⚠️ AUCUNE DE CES ERREURS NE LÈVE. Elles produisent des nombres plausibles.
"""

import pytest

import app as flask_app

_c = flask_app._classe_titre


@pytest.mark.parametrize("titre", [
    "Cartão de Crédito",   # ⚠️ LE LIBELLÉ RÉEL DU CAFÉ, et celui qui a cassé.
    "Cartão de Débito",
    "Cartão",
    "CARTAO",
    "cartao de credito",
    "Multibanco",
    "MB Way",
    "MBWay",
    "TPA",
    "Visa/Mastercard",
    "Cartão Refeição",
])
def test_la_famille_carte_est_reconnue(titre):
    assert _c(titre) == "carte"


@pytest.mark.parametrize("titre", ["Dinheiro", "DINHEIRO", "numerário", "Cash", "Espèces"])
def test_la_famille_especes_est_reconnue(titre):
    assert _c(titre) == "especes"


@pytest.mark.parametrize("titre", ["Cheque", "Transferência", "Vale", "", None])
def test_le_reste_tombe_dans_autre_et_sera_signale(titre):
    """
    ⚠️ ET C'EST VOULU. « Autre » n'est pas un fourre-tout silencieux : tout libellé qui y tombe
    est NOMMÉ à l'écran. Le danger n'est pas d'avoir une catégorie « autre », c'est qu'elle
    avale quelque chose sans le dire.
    """
    assert _c(titre) == "autre"


def test_on_reconnait_des_MOTS_pas_des_libelles_entiers():
    """
    ⚠️ LA CORRECTION DU 21/09/2026. Énumérer les libellés exacts, c'est s'engager à les deviner
    tous : « Cartão de Débito », « Cartão Refeição », un « Visa » tapé à la main le jour où
    quelqu'un configure un nouveau terminal. Reconnaître le mot couvre la famille.
    """
    assert _c("Cartão de Crédito") == _c("Cartão") == "carte"
    assert _c("Pagamento em Dinheiro") == "especes"


def test_un_seul_endroit_decide():
    """
    ⚠️ LE CLASSEMENT SERT À TROIS ÉCRANS : la répartition quotidienne, le rapprochement
    transaction par transaction, et la sonde. Trois copies de la règle, c'est la garantie qu'un
    jour l'une reconnaîtra « Cartão de Crédito » et pas les autres — et l'écart changera selon
    l'écran qu'on regarde.
    """
    import inspect
    src = inspect.getsource(flask_app)
    # Personne ne compare un titre à la liste directement.
    assert "in TITRES_CARTE" not in src.replace("n in TITRES_CARTE or (mots & MOTS_CARTE)", "")
    for fonction in ("_classer_paiements", "api_reconciliation_detail", "api_vendus_paiements"):
        bloc = inspect.getsource(getattr(flask_app, fonction))
        assert "_classe_titre" in bloc, f"{fonction} n'utilise pas le classement commun"


def test_la_repartition_utilise_le_classement(monkeypatch):
    r = flask_app._classer_paiements({"Cartão de Crédito": 380.20, "Dinheiro": 10.80})
    assert r["carte_cents"] == 38020
    assert r["especes_cents"] == 1080
    assert r["autre_cents"] == 0
    assert r["titres_inconnus"] == []
