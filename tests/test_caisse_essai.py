"""
La caisse d'essai du POS ne doit pas déplacer les chiffres du café.

Le POS Mesa est en rodage. Faute de compte Vendus de test, il émet sur une caisse dédiée du
compte de PRODUCTION — son .env portait même la clé de production alors que son README exige
un compte de test. L'isolement ne tient donc qu'à un identifiant de caisse, c'est-à-dire à une
ligne de configuration que personne ne relit.

Le dashboard ne fait pas confiance à cette configuration : il écarte lui-même ces documents.

⚠️ CE FICHIER RAPPELLE UNE DETTE. Le jour où le POS encaisse pour de vrai, `TEST_REGISTER_IDS`
doit être VIDÉ, sinon les vraies ventes disparaîtront des chiffres — le défaut symétrique, et
bien plus coûteux qu'un ticket d'essai compté en trop. Le dernier test ci-dessous existe pour
qu'on tombe dessus à ce moment-là.
"""
import sys
sys.path.insert(0, ".")

import vendus


CAISSE_REELLE = "342853246"      # « Caixa principal » — 1430 documents réels
CAISSE_ESSAI  = "360703227"      # « API Mesa » — le POS en rodage


def _doc(register, gross=10.0, type_="FT"):
    return {"type": type_, "register_id": register,
            "amount_gross": gross, "amount_net": gross / 1.13, "items": []}


def test_les_documents_de_la_caisse_d_essai_sont_ecartes():
    docs = [_doc(CAISSE_REELLE, 12.0), _doc(CAISSE_ESSAI, 999.0), _doc(CAISSE_REELLE, 8.0)]
    gardes = vendus._drop_test_registers(docs)
    assert len(gardes) == 2
    assert all(d["register_id"] == CAISSE_REELLE for d in gardes)
    assert 999.0 not in [d["amount_gross"] for d in gardes], "le ticket d'essai a survécu"


def test_le_nombre_d_ecartes_est_retenu_pour_etre_annonce():
    """Une troncature muette se lirait « il ne s'est rien passé » sur la caisse d'essai."""
    vendus._drop_test_registers([_doc(CAISSE_REELLE), _doc(CAISSE_ESSAI), _doc(CAISSE_ESSAI)])
    assert vendus.LAST_TEST_DOCS_DROPPED == 2


def test_une_journee_sans_essai_ne_declenche_aucune_annonce():
    vendus._drop_test_registers([_doc(CAISSE_REELLE), _doc(CAISSE_REELLE)])
    assert vendus.LAST_TEST_DOCS_DROPPED == 0


def test_l_identifiant_est_compare_en_texte():
    """
    Vendus renvoie `register_id` tantôt en nombre, tantôt en chaîne selon la vue. Comparer sans
    normaliser laisserait passer la moitié des tickets d'essai — et le filtre aurait l'air de
    marcher, puisqu'il en écarterait quand même.
    """
    docs = [_doc(int(CAISSE_ESSAI)), _doc(CAISSE_ESSAI)]
    assert vendus._drop_test_registers(docs) == []
    assert vendus.LAST_TEST_DOCS_DROPPED == 2


def test_un_ensemble_vide_laisse_tout_passer(monkeypatch):
    """
    C'est l'état visé au passage en réel : plus aucune caisse écartée, les ventes du POS
    comptent comme les autres. Le chemin doit être exercé AVANT qu'on en ait besoin.
    """
    monkeypatch.setattr(vendus, "TEST_REGISTER_IDS", set())
    docs = [_doc(CAISSE_REELLE), _doc(CAISSE_ESSAI)]
    assert len(vendus._drop_test_registers(docs)) == 2
    assert vendus.LAST_TEST_DOCS_DROPPED == 0


def test_la_dette_est_encore_ouverte():
    """
    ⚠️ CE TEST N'EST PAS UNE VÉRIFICATION, C'EST UN RAPPEL.

    Tant qu'il passe, le POS est en rodage et ses tickets sont écartés des chiffres. Le jour où
    il encaisse pour de vrai, videz `TEST_REGISTER_IDS` : ce test tombera, et ce sera le signal
    de supprimer ce fichier avec lui.
    """
    assert vendus.TEST_REGISTER_IDS == {CAISSE_ESSAI}, (
        "TEST_REGISTER_IDS a changé. Si le POS est passé en réel, supprimez ce fichier ; "
        "sinon, vérifiez que la bonne caisse est bien écartée.")


def test_get_documents_applique_reellement_le_filtre(monkeypatch):
    """
    ⚠️ CE TEST VÉRIFIE LE BRANCHEMENT, PAS LA RÈGLE.

    Les tests ci-dessus exercent `_drop_test_registers` directement : débrancher son appel de
    `get_documents` les laissait tous verts. C'est le trou classique — la règle est juste, plus
    personne ne l'applique. On passe donc par la vraie fonction, avec l'appel HTTP bouchonné.
    """
    lot = [_doc(CAISSE_REELLE, 12.0), _doc(CAISSE_ESSAI, 999.0),
           _doc(CAISSE_REELLE, 8.0, "NC")]
    monkeypatch.setattr(vendus, "vendus", lambda ep, params=None: lot if params.get("page") == 1 else [])

    out = vendus.get_documents("2026-08-10", "2026-08-10")
    montants = [abs(float(d["amount_gross"])) for d in out]
    assert 999.0 not in montants, "un ticket d'essai a traversé get_documents"
    assert sorted(montants) == [8.0, 12.0]
    assert vendus.LAST_TEST_DOCS_DROPPED == 1
