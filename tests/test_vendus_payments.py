"""
LA RÉPARTITION PAR MOYEN DE PAIEMENT, À LA SOURCE.

⚠️ `view=detailed` EST LA SEULE SOURCE CONNUE DU CHAMP `payments`. L'endpoint d'un document
isolé porte les lignes produits mais pas toujours les paiements — et `get_documents_with_items`
appelait la liste SANS `detailed`, puis écrasait chaque document par son détail.

Résultat le 21/09/2026 : le cache `daily_summary` s'est rempli avec une répartition vide. Des
journées entières affichaient « 0 € facturé carte » et un écart de réconciliation égal au
chiffre d'affaires. Rien n'a levé.
"""

import vendus


def test_la_liste_est_demandee_en_detailed(monkeypatch):
    """⚠️ SANS CE DRAPEAU, `payments` N'EXISTE NULLE PART dans ce qui alimente le cache."""
    vus = {}

    def faux_get_documents(since, until, detailed=False):
        vus["detailed"] = detailed
        return []

    monkeypatch.setattr(vendus, "get_documents", faux_get_documents)
    vendus.get_documents_with_items("2026-09-01", "2026-09-02")
    assert vus["detailed"] is True


def test_les_paiements_de_la_liste_survivent_au_detail(monkeypatch):
    """
    ⚠️ LA RÈGLE : CELLE QUI SAIT QUELQUE CHOSE L'EMPORTE SUR CELLE QUI SE TAIT. Écraser une
    information par une absence est la façon la plus discrète de perdre une donnée.
    """
    monkeypatch.setattr(vendus, "get_documents", lambda s, u, detailed=False: [
        {"id": 1, "payments": [{"title": "Cartão", "amount": 9.6}]},
    ])
    # Le détail porte les lignes produits, mais pas les paiements.
    monkeypatch.setattr(vendus, "get_document_detail",
                        lambda i: {"id": 1, "items": [{"qty": 1}]})
    docs = vendus.get_documents_with_items("2026-09-01", "2026-09-02")
    assert docs[0]["items"], "les lignes produits ont été perdues"
    assert docs[0]["payments"][0]["title"] == "Cartão", "les paiements ont été perdus"


def test_le_detail_lemporte_quand_il_porte_les_paiements(monkeypatch):
    """Si un jour l'API se met à les renvoyer, c'est la source la plus précise qui gagne."""
    monkeypatch.setattr(vendus, "get_documents", lambda s, u, detailed=False: [
        {"id": 1, "payments": [{"title": "Ancien", "amount": 1.0}]},
    ])
    monkeypatch.setattr(vendus, "get_document_detail",
                        lambda i: {"id": 1, "payments": [{"title": "Cartão", "amount": 9.6}]})
    docs = vendus.get_documents_with_items("2026-09-01", "2026-09-02")
    assert docs[0]["payments"][0]["title"] == "Cartão"


def test_un_avoir_reste_negatif(monkeypatch):
    """Le détail brut annule la négation des avoirs ; la fusion ne doit pas la reperdre."""
    monkeypatch.setattr(vendus, "get_documents", lambda s, u, detailed=False: [
        {"id": 1, "_refund": True, "amount_gross": -9.6,
         "payments": [{"title": "Cartão", "amount": -9.6}]},
    ])
    monkeypatch.setattr(vendus, "get_document_detail",
                        lambda i: {"id": 1, "amount_gross": 9.6})
    docs = vendus.get_documents_with_items("2026-09-01", "2026-09-02")
    assert docs[0].get("_refund") is True
    assert docs[0]["amount_gross"] < 0
