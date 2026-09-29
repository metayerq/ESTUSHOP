"""
Les devoluções du terminal, qui n'entraient nulle part.

L'import du Merchant reconciliation statement ne gardait que `Type = Settlement`. Le même
fichier contient aussi des `Refund` — sur septembre 2026, 41 lignes pour 230,90 € — et des
`Transfer`, qui sont les virements vers le compte. Les remboursements tombaient donc à côté :
`gross` surestimait les ventes carte de leur montant exact, et la réconciliation
Vendus ↔ Revolut ne pouvait pas tomber juste. Personne ne pouvait nommer l'écart.

Ils étaient tombés à côté pour une raison précise, qui est la seule chose à ne pas casser ici :
UN REMBOURSEMENT N'A PAS DE DATE DE CAPTURE dans le fichier Revolut (vérifié : 0 sur 41). Or
l'import indexe tout sur la capture. On les pose donc sur la date de RÈGLEMENT — qui est aussi
la bonne date comptablement, un remboursement étant un événement de son propre jour.

La preuve que le traitement est juste tient en une ligne : net des règlements moins devoluções
doit redonner le « Total » net du Sales statement PDF, que rien ne permettait d'atteindre avant.
"""
import io
import sys

sys.path.insert(0, ".")

import app


COLS = ("Type,Original amount,Settlement amount,Processing fee,Tip amount,"
        "Payment Capture Date & Time (UTC),Date & Time Completed (UTC)")


def _csv(*lignes):
    return (COLS + "\n" + "\n".join(lignes)).encode("utf-8")


def _importe(contenu, monkeypatch):
    ecrit = {}
    monkeypatch.setattr(app, "_supa_upsert",
                        lambda table, row: ecrit.__setitem__(row["day"], row) or True)
    monkeypatch.setattr(app, "_is_admin", lambda: True)
    client = app.app.test_client()
    rep = client.post("/api/tpa/upload",
                      data={"file": (io.BytesIO(contenu), "stmt.csv")},
                      content_type="multipart/form-data")
    return rep.get_json(), ecrit


def test_le_remboursement_est_pose_sur_sa_date_de_reglement(monkeypatch):
    # Un remboursement n'a PAS de date de capture — la colonne est vide, comme chez Revolut.
    rep, ecrit = _importe(_csv(
        "Settlement,10.00,9.90,-0.10,0.00,2026-09-10 08:00:00,2026-09-11 02:00:00",
        "Refund,-4.00,-4.00,0.00,0.00,,2026-09-12 02:00:00",
    ), monkeypatch)

    assert rep["ok"] is True
    assert rep["transactions"] == 1
    assert rep["refunds"] == 1
    # La vente est rangée à sa capture, le remboursement à son règlement : deux jours distincts.
    assert sorted(ecrit) == ["2026-09-10", "2026-09-12"]
    assert ecrit["2026-09-10"]["gross"] == 10.00
    assert ecrit["2026-09-10"]["refunds"] == 0
    assert ecrit["2026-09-12"]["refunds"] == 4.00
    # Un jour qui ne porte qu'un remboursement n'invente aucune vente.
    assert ecrit["2026-09-12"]["gross"] == 0
    assert ecrit["2026-09-12"]["tx"] == 0


def test_le_remboursement_est_stocke_en_positif(monkeypatch):
    # Le CSV le donne en négatif ; on stocke la valeur absolue, comme `fees`, pour que les
    # formules soustraient au lieu d'additionner un négatif.
    _, ecrit = _importe(_csv(
        "Refund,-12.34,-12.34,0.00,0.00,,2026-09-12 02:00:00",
    ), monkeypatch)
    assert ecrit["2026-09-12"]["refunds"] == 12.34


def test_les_virements_ne_comptent_nulle_part(monkeypatch):
    # `Transfer` = l'argent qui sort de Revolut vers le compte. Ce n'est pas du chiffre.
    rep, ecrit = _importe(_csv(
        "Settlement,10.00,9.90,-0.10,0.00,2026-09-10 08:00:00,2026-09-11 02:00:00",
        "Transfer,-307.52,-307.52,0.00,0.00,,2026-09-11 02:00:00",
    ), monkeypatch)
    assert rep["transactions"] == 1 and rep["refunds"] == 0
    assert list(ecrit) == ["2026-09-10"]
    assert ecrit["2026-09-10"]["gross"] == 10.00


def test_le_net_credite_redonne_le_total_du_pdf(monkeypatch):
    """Chiffres réels de septembre 2026, ramenés à trois lignes.

    Le Sales statement annonce trois totaux : règlements 7 695,72 € brut pour 7 582,30 € net,
    remboursements −230,90 €, et un « Total » net de 7 351,40 €. Ce dernier était inatteignable
    tant que les remboursements n'entraient pas.
    """
    _, ecrit = _importe(_csv(
        "Settlement,7695.72,7582.30,-113.42,151.50,2026-09-15 08:00:00,2026-09-16 02:00:00",
        "Refund,-230.90,-230.90,0.00,0.00,,2026-09-16 02:00:00",
    ), monkeypatch)

    net = sum(j["net"] for j in ecrit.values())
    devolucoes = sum(j["refunds"] for j in ecrit.values())
    assert round(net - devolucoes, 2) == 7351.40

    # Et les ventes carte : le brut, moins ce qui transite (gorjetas) et ce qui est rendu.
    brut = sum(j["gross"] for j in ecrit.values())
    gorjetas = sum(j["tips"] for j in ecrit.values())
    assert round(brut - gorjetas - devolucoes, 2) == 7313.32
