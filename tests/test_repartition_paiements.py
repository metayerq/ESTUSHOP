"""
LA RÉPARTITION PAR MOYEN DE PAIEMENT.

⚠️ SANS ELLE, COMPARER L'ENCAISSEMENT TERMINAL AU FACTURÉ VENDUS EXIGE DE RECHARGER TOUT LE MOIS
document par document — la rafale qui dépasse le timeout serverless et rend la page à zéro.

⚠️ ET ELLE PEUT MENTIR DE DEUX FAÇONS SILENCIEUSES : confondre « information absente » avec
« zéro euro en carte », et ignorer les avoirs, ce qui produirait un écart permanent avec le
terminal du montant exact des remboursements.
"""

import app as flask_app

_r = flask_app._repartition_paiements


def doc(payments, refund=False):
    d = {"payments": payments}
    if refund:
        d["_refund"] = True
    return d


def test_les_moyens_sont_additionnes_par_titre():
    r = _r([doc([{"title": "Cartão", "amount": 10.0}]),
            doc([{"title": "Cartão", "amount": 5.5}, {"title": "Dinheiro", "amount": 2.0}])])
    assert r == {"Cartão": 15.5, "Dinheiro": 2.0}


def test_un_avoir_diminue_lencaissement():
    """
    ⚠️ UN REMBOURSEMENT RENDU EN CARTE DIMINUE L'ENCAISSEMENT CARTE DU JOUR. L'exclure ferait
    apparaître un écart permanent avec le terminal, du montant exact des avoirs — et on
    chercherait une facture oubliée qui n'existe pas.
    """
    r = _r([doc([{"title": "Cartão", "amount": 10.0}]),
            doc([{"title": "Cartão", "amount": 4.0}], refund=True)])
    assert r == {"Cartão": 6.0}


def test_linformation_absente_nest_pas_zero():
    """
    ⚠️ LE CHAMP VIENT DE LA VUE DÉTAILLÉE DE VENDUS, QUI N'EST PAS DOCUMENTÉE. Si elle cesse un
    jour de le porter, l'écran doit dire « répartition indisponible » et non « zéro euro
    encaissé en carte ». Les deux se ressemblent et mènent à des conclusions opposées.
    """
    assert _r([{"amount_gross": 12.0}]) is None
    assert _r([]) is None


def test_un_jour_sans_paiement_mais_avec_la_vue_rend_un_dictionnaire_vide():
    """Distinct de `None` : ici on SAIT qu'il n'y a rien, on ne l'ignore pas."""
    assert _r([doc([])]) == {}


def test_un_moyen_sans_titre_nest_pas_perdu():
    assert _r([doc([{"amount": 3.0}])]) == {"Autre": 3.0}
    assert _r([doc([{"title": "   ", "amount": 3.0}])]) == {"Autre": 3.0}


def test_les_centimes_ne_derivent_pas():
    """Trente paiements à 0,10 € font 3,00 €, pas 2,9999999999999996."""
    r = _r([doc([{"title": "Cartão", "amount": 0.1}]) for _ in range(30)])
    assert r == {"Cartão": 3.0}


def test_la_colonne_manquante_ne_fait_pas_perdre_la_ligne(monkeypatch):
    """
    ⚠️ DÉPLOYER LE CODE AVANT D'EXÉCUTER LA MIGRATION ferait échouer TOUTE écriture de cache —
    pas seulement la répartition. Le repli existant doit couvrir la colonne neuve.
    """
    essais = []

    def faux_upsert(table, row):
        essais.append(dict(row))
        if "payments" in row:
            return False, "column daily_summary.payments does not exist"
        return True, None

    monkeypatch.setattr(flask_app, "_supa_upsert", faux_upsert)
    ok, err = flask_app._upsert_summary("2026-09-20", {"ca_ttc": 10.0, "payments": {"Cartão": 10.0}})
    assert ok is True
    assert "payments" not in essais[-1]
    assert essais[-1]["ca_ttc"] == 10.0
