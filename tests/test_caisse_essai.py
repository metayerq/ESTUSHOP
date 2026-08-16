"""
Écarter une caisse des chiffres — mécanisme conservé, garde levée.

HISTOIRE, PARCE QU'ELLE EXPLIQUE POURQUOI CE CODE EXISTE ENCORE.
Pendant le rodage, le POS Mesa émettait sur une caisse dédiée du compte de PRODUCTION, faute
de compte Vendus de test — et son `.env` portait la clé de production alors que son propre
README exigeait un compte de test. L'isolement ne tenait qu'à un identifiant de caisse. Le
dashboard a donc écarté ces documents lui-même, plutôt que de faire confiance à une ligne de
configuration que personne ne relit.

DÉCOUVERT DEPUIS : les documents en mode formation ne sortent de l'API Vendus que si l'on
demande explicitement `mode=tests`. Le dashboard ne le demande pas — il ne les a jamais vus.
La garde était une ceinture par-dessus des bretelles.

AUJOURD'HUI elle est LEVÉE : `TEST_REGISTER_IDS` est vide, et les ventes du POS comptent comme
celles du comptoir. Le mécanisme reste en place et testé — remettre un identifiant suffirait à
réisoler une caisse, sans rien réécrire.
"""
import sys
sys.path.insert(0, ".")

import pytest

import vendus


CAISSE_REELLE = "342853246"      # « Caixa principal »
CAISSE_POS    = "360703227"      # « API Mesa »


def _doc(register, gross=10.0, type_="FT"):
    return {"type": type_, "register_id": register,
            "amount_gross": gross, "amount_net": gross / 1.13, "items": []}


# ── L'état voulu aujourd'hui ─────────────────────────────────────────────────

def test_plus_aucune_caisse_n_est_ecartee():
    """
    ⚠️ C'EST L'ÉTAT ATTENDU DEPUIS LE PASSAGE EN RÉEL.

    Si ce test tombe, quelqu'un a réisolé une caisse : vérifiez que c'est voulu, et que l'écran
    l'annonce. Laisser un identifiant ici ferait DISPARAÎTRE de vraies ventes des chiffres —
    le défaut symétrique de celui qu'on corrigeait, et bien plus coûteux.
    """
    assert vendus.TEST_REGISTER_IDS == set()


def test_les_ventes_du_pos_comptent_comme_les_autres():
    docs = [_doc(CAISSE_REELLE, 12.0), _doc(CAISSE_POS, 2.80)]
    gardes = vendus._drop_test_registers(docs)
    assert len(gardes) == 2
    assert 2.80 in [d["amount_gross"] for d in gardes], "une vente du POS a été écartée"
    assert vendus.LAST_TEST_DOCS_DROPPED == 0


# ── Le mécanisme, conservé et exercé ────────────────────────────────────────

@pytest.fixture
def caisse_isolee(monkeypatch):
    """Réisole une caisse le temps d'un test : on exerce le MÉCANISME, pas la configuration."""
    monkeypatch.setattr(vendus, "TEST_REGISTER_IDS", {CAISSE_POS})


def test_le_mecanisme_ecarte_encore_ce_qu_on_lui_nomme(caisse_isolee):
    docs = [_doc(CAISSE_REELLE, 12.0), _doc(CAISSE_POS, 999.0), _doc(CAISSE_REELLE, 8.0)]
    gardes = vendus._drop_test_registers(docs)
    assert [d["amount_gross"] for d in gardes] == [12.0, 8.0]


def test_le_nombre_d_ecartes_reste_annoncable(caisse_isolee):
    """Une troncature muette se lirait « il ne s'est rien passé sur cette caisse »."""
    vendus._drop_test_registers([_doc(CAISSE_REELLE), _doc(CAISSE_POS), _doc(CAISSE_POS)])
    assert vendus.LAST_TEST_DOCS_DROPPED == 2


def test_l_identifiant_est_compare_en_texte(caisse_isolee):
    """
    Vendus renvoie `register_id` tantôt en nombre, tantôt en chaîne selon la vue. Comparer sans
    normaliser laisserait passer la moitié des documents — et le filtre aurait l'air de marcher,
    puisqu'il en écarterait quand même.
    """
    assert vendus._drop_test_registers([_doc(int(CAISSE_POS)), _doc(CAISSE_POS)]) == []


def test_le_filtre_est_toujours_branche_sur_get_documents(caisse_isolee, monkeypatch):
    """
    ⚠️ VÉRIFIE LE BRANCHEMENT, PAS LA RÈGLE.

    Les tests ci-dessus exercent `_drop_test_registers` directement : débrancher son appel de
    `get_documents` les laissait tous verts. C'est le trou classique — la règle juste, et plus
    personne pour l'appeler. Il reste utile maintenant que l'ensemble est vide : le jour où on
    réisole une caisse, le branchement doit être encore là.
    """
    lot = [_doc(CAISSE_REELLE, 12.0), _doc(CAISSE_POS, 999.0)]
    monkeypatch.setattr(vendus, "vendus",
                        lambda ep, params=None: lot if params.get("page") == 1 else [])
    out = vendus.get_documents("2026-08-16", "2026-08-16")
    assert [abs(float(d["amount_gross"])) for d in out] == [12.0]
    assert vendus.LAST_TEST_DOCS_DROPPED == 1
