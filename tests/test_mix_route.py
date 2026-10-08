# -*- coding: utf-8 -*-
"""
LA ROUTE QUI RÉPOND À « GARDE-T-ON LE BRUNCH EN SEMAINE ? »

⚠️ CE FICHIER EXISTE PARCE QUE LA ROUTE A ÉTÉ ÉCRITE SANS SON IMPORT DE `Response` et que la
suite entière est restée verte : aucun test ne la traversait. Une route qu'on n'appelle jamais
est une route qui plante le jour où quelqu'un l'ouvre — et ce jour-là, c'est au moment de
prendre une décision.
"""
from datetime import date

import pytest

import app as flask_app


def doc(jour, *articles):
    return {"date": f"{jour} 10:30:00",
            "items": [{"title": t, "qty": q, "amounts": {"net_total": ht}}
                      for t, q, ht in articles]}


LUNDIS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_load_ingredients", lambda: {"farine": {"price": 2.0,
                                                                            "unit": "kg"}})
    monkeypatch.setattr(flask_app, "_load_preparations", lambda: [])
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


def servir(monkeypatch, docs, recettes=()):
    """
    ⚠️ LA LISTE DÉTAILLÉE EST BOUCHONNÉE AUSSI, parce que la route l'interroge EN PREMIER depuis
    qu'un mois entier ne tient plus dans une fonction serverless. Mes quatre premiers cas ne
    stubaient que le détail : ils se sont mis à appeler le vrai Vendus, et c'est l'absence de
    clé qui les a arrêtés — pas une assertion.
    """
    import vendus
    monkeypatch.setattr(vendus, "get_documents",
                        lambda a, b, detailed=False: list(docs))
    monkeypatch.setattr(vendus, "get_documents_with_items", lambda a, b: list(docs))
    monkeypatch.setattr(flask_app, "_load_recipes", lambda: list(recettes))


def appel(c, q="sourdough", debut="2026-09-01", fin="2026-09-30"):
    return c.get(f"/api/mix-jours?debut={debut}&fin={fin}&q={q}")


def test_LA_ROUTE_REPOND_VRAIMENT(admin, monkeypatch):
    """⚠️ LE CONTRÔLE QUI MANQUAIT : `Response` n'était pas importé, et rien ne le voyait."""
    servir(monkeypatch, [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))])
    r = appel(admin)
    assert r.status_code == 200
    assert r.mimetype == "text/plain"


def test_le_tableau_porte_les_jours_et_les_moyennes(admin, monkeypatch):
    servir(monkeypatch, [doc(j, ("Café", 1, 2.0)) for j in LUNDIS]
           + [doc(LUNDIS[0], ("Sourdough toast", 4, 20.0))])
    t = appel(admin).get_data(as_text=True)
    assert "lundi" in t
    # Quatre lundis ouverts, 4 vendus sur l'un d'eux → une unité par lundi en moyenne.
    ligne = [l for l in t.splitlines() if l.startswith("lundi")][0]
    assert "    4" in ligne and "1.0" in ligne


def test_UN_ARTICLE_SANS_RECETTE_A_UNE_MARGE_INCONNUE_PAS_NULLE(admin, monkeypatch):
    """⚠️ AFFICHER « marge = chiffre d'affaires » FERAIT GARDER UN PRODUIT SUR UNE ABSENCE DE
    DONNÉES. Le point d'interrogation dit qu'on ne sait pas."""
    servir(monkeypatch, [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))], recettes=[])
    t = appel(admin).get_data(as_text=True)
    assert "sans recette, donc marge inconnue" in t
    assert "?" in [c.strip() for c in
                   [l for l in t.splitlines() if l.startswith("lundi")][0].split()]


def test_UNE_RECHERCHE_SANS_RESULTAT_LE_CRIE(admin, monkeypatch):
    """
    ⚠️ DES ZÉROS SE LISENT « ÇA NE SE VEND PAS » — la réponse exactement inverse de la vérité
    quand c'est le mot cherché qui ne correspond à rien.
    """
    servir(monkeypatch, [doc(LUNDIS[0], ("Café", 1, 2.0))])
    t = appel(admin, q="sourdough").get_data(as_text=True)
    assert "AUCUN ARTICLE TROUVÉ" in t


def test_les_titres_trouves_sont_affiches(admin, monkeypatch):
    servir(monkeypatch, [doc(LUNDIS[0], ("Bowl granola maison", 1, 6.0))])
    assert "Bowl granola maison" in appel(admin, q="granola").get_data(as_text=True)


def test_un_jour_jamais_ouvert_est_annonce_comme_ferme(admin, monkeypatch):
    """Et surtout pas comme un jour à zéro vente."""
    servir(monkeypatch, [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))])
    t = appel(admin).get_data(as_text=True)
    assert "café fermé ce jour-là" in t


@pytest.mark.parametrize("params", ["", "?debut=2026-09-01", "?debut=x&fin=y&q=a",
                                    "?debut=2026-09-01&fin=2026-09-30"])
def test_une_demande_incomplete_est_refusee(admin, monkeypatch, params):
    servir(monkeypatch, [])
    assert admin.get(f"/api/mix-jours{params}").status_code == 400


def test_une_fin_avant_le_debut_est_refusee(admin, monkeypatch):
    servir(monkeypatch, [])
    assert appel(admin, debut="2026-09-30", fin="2026-09-01").status_code == 400


def test_elle_est_fermee_aux_roles_sans_les_chiffres(admin, monkeypatch):
    servir(monkeypatch, [])
    for role in ("investor", "staff", None):
        monkeypatch.setattr(flask_app, "_current_role", lambda r=role: r)
        assert appel(admin).status_code == 403, role


# ── Le mois ne tient pas dans une fonction serverless ───────────────────────────────────────
#
# ⚠️ LA PREMIÈRE VERSION APPELAIT `get_documents_with_items` SUR LE MOIS ENTIER — un appel par
# document, mille deux cents pour un mois à quarante tickets par jour. La page ne chargeait pas,
# et rien ne disait pourquoi : le navigateur attendait, puis abandonnait.

def servir_liste(monkeypatch, liste, par_jour=None):
    """La liste détaillée, et éventuellement le détail document par document."""
    import vendus
    appels = {"liste": 0, "detail": []}

    def _liste(a, b, detailed=False):
        appels["liste"] += 1
        return list(liste)

    def _detail(a, b):
        appels["detail"].append(a)
        return list((par_jour or {}).get(a, []))

    monkeypatch.setattr(vendus, "get_documents", _liste)
    monkeypatch.setattr(vendus, "get_documents_with_items", _detail)
    monkeypatch.setattr(flask_app, "_load_recipes", lambda: [])
    return appels


def test_SI_LA_LISTE_PORTE_DEJA_LES_ARTICLES_ON_NE_DESCEND_PAS_AU_DOCUMENT(admin, monkeypatch):
    """⚠️ C'EST CE QUI FAIT LA DIFFÉRENCE ENTRE DEUX SECONDES ET UN DÉLAI DÉPASSÉ."""
    appels = servir_liste(monkeypatch, [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))])
    t = appel(admin).get_data(as_text=True)
    assert appels["detail"] == [], "on a interrogé chaque document pour rien"
    assert "lundi" in t


def test_sinon_on_descend_jour_par_jour(admin, monkeypatch):
    sans_items = [{"date": f"{LUNDIS[0]} 10:00:00", "items": []}]
    appels = servir_liste(monkeypatch, sans_items,
                          par_jour={LUNDIS[0]: [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))]})
    t = appel(admin, debut="2026-09-07", fin="2026-09-09").get_data(as_text=True)
    assert appels["detail"] == ["2026-09-07", "2026-09-08", "2026-09-09"]
    assert "lundi" in t


def test_UNE_PERIODE_TRONQUEE_LE_DIT_ET_DONNE_LA_SUITE(admin, monkeypatch):
    """
    ⚠️ UN TABLEAU PARTIEL QUI SE PRÉSENTE COMME COMPLET ferait décider sur la moitié d'un mois
    sans que personne le sache. Il doit dire où il s'est arrêté ET comment reprendre.
    """
    import app as a
    sans_items = [{"date": f"{LUNDIS[0]} 10:00:00", "items": []}]
    servir_liste(monkeypatch, sans_items, par_jour={})
    # On épuise le budget dès le premier jour.
    faux_temps = iter([0.0] + [999.0] * 40)
    monkeypatch.setattr("time.monotonic", lambda: next(faux_temps))
    t = appel(admin, debut="2026-09-01", fin="2026-09-30").get_data(as_text=True)
    assert "PÉRIODE INCOMPLÈTE" in t
    assert "debut=2026-09-01" in t, "la reprise ne dit pas où redémarrer"


def test_une_periode_complete_ne_sexcuse_pas(admin, monkeypatch):
    servir_liste(monkeypatch, [doc(LUNDIS[0], ("Sourdough toast", 2, 10.0))])
    assert "PÉRIODE INCOMPLÈTE" not in appel(admin).get_data(as_text=True)
