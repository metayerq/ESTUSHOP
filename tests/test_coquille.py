"""
LA COQUILLE — rail de navigation et bande d'état.

⚠️ LA NAVIGATION ÉTAIT RECOPIÉE À LA MAIN DANS TREIZE GABARITS. Ajouter une page demandait
treize modifications, et j'en ai déjà raté une : la feuille de style de la nav, oubliée sur
`marketing.html`, a rendu la page illisible sans qu'aucun test ne rougisse. Un partiel unique
supprime la classe entière de ce bogue — ces tests l'empêchent de revenir.
"""

import glob
import os
import re

import flask
import pytest

import app as flask_app

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = {"v": "t", "role": "admin", "open_date": "2026-05-27", "hier": "2026-09-20",
       "token": "x", "rail": True}


def gabarits():
    for f in sorted(glob.glob(os.path.join(RACINE, "templates", "*.html"))):
        nom = os.path.basename(f)
        if not nom.startswith("_"):
            yield nom


def rendre(nom):
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_request_context("/"):
        return flask.render_template(nom, **CTX)


# ── Plus une seule copie de la navigation ────────────────────────────────────────────────────

@pytest.mark.parametrize("nom", list(gabarits()))
def test_aucun_gabarit_ne_recopie_la_navigation(nom):
    """
    ⚠️ C'EST LA GARANTIE PRINCIPALE. Une copie qui subsiste, c'est deux barres de navigation
    affichées, ou une seule mais qui ne suit plus les autres quand on ajoute une page.
    """
    with open(os.path.join(RACINE, "templates", nom), encoding="utf-8") as f:
        src = f.read()
    assert '<nav class="topnav"' not in src, "la vieille barre est encore recopiée ici"
    assert ".nav-menu {" not in src, "la feuille de style de la vieille nav traîne encore"


@pytest.mark.parametrize("nom", [n for n in gabarits() if n not in ("tpa.html",)])
def test_chaque_page_porte_le_rail(nom):
    h = rendre(nom)
    assert 'class="rail"' in h, "cette page n'a aucune navigation"
    assert 'class="statut"' in h, "cette page n'a pas la bande d'état"


def test_la_page_du_comptable_na_pas_le_rail():
    """
    ⚠️ LE RAIL N'EST PAS POUR LE COMPTABLE. `tpa.html` lui est destinée, et lui montrer la
    navigation du backoffice l'inviterait dans des écrans qui ne le regardent pas : dépenses,
    fichier clients, marketing.
    """
    assert 'class="rail"' not in rendre("tpa.html")


def test_contabilidade_montre_le_rail_a_ladmin_seulement(monkeypatch):
    """
    Même page, deux publics. ⚠️ ET L'ADMIN QUI Y ARRIVE DOIT POUVOIR EN REPARTIR : sans issue,
    il ferme l'onglet et n'y revient plus.
    """
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_request_context("/"):
        assert 'class="rail"' in flask.render_template("contabilidade.html", rail=True, v="t")
        assert 'class="rail"' not in flask.render_template("contabilidade.html", rail=False, v="t")


# ── Le balisage tient ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nom", list(gabarits()))
def test_la_coquille_souvre_et_se_referme(nom):
    """
    ⚠️ DEUX PARTIELS, UN AU DÉBUT ET UN À LA FIN. En oublier un laisse la page entière hors de
    la zone de travail — à côté du rail, sans marges — et le symptôme est une page « décalée »
    dont la cause ne se lit nulle part.
    """
    h = rendre(nom)
    if 'class="rail"' not in h:
        pytest.skip("page sans rail, par décision")
    assert h.count('<div class="app">') == 1
    assert h.count("<!-- /app -->") == 1
    assert h.index('<div class="app">') < h.index("<!-- /app -->")


@pytest.mark.parametrize("nom", list(gabarits()))
def test_le_contenu_est_dans_la_zone_de_travail(nom):
    """Sinon il s'affiche À CÔTÉ du rail, hors de la bande d'état et sans les marges."""
    h = rendre(nom)
    if 'class="rail"' not in h:
        pytest.skip("page sans rail, par décision")
    assert h.index('class="statut"') < h.index('<div class="page">')
    assert h.index('<div class="page">') < h.index("<!-- /app -->")


# ── Le rail lui-même ─────────────────────────────────────────────────────────────────────────

def test_toutes_les_destinations_du_rail_existent():
    """
    ⚠️ UN LIEN MORT DANS UNE NAVIGATION PERMANENTE SE CLIQUE TOUS LES JOURS. Il mène à une 404
    ou, pire, à une redirection vers la connexion — qui se lit comme une déconnexion.
    """
    with open(os.path.join(RACINE, "templates", "_rail.html"), encoding="utf-8") as f:
        rail = f.read()
    chemins = re.findall(r'data-p="([^"]+)"', rail)
    assert len(chemins) >= 10
    connues = {str(r.rule) for r in flask_app.app.url_map.iter_rules()}
    for c in chemins:
        assert c in connues, f"le rail pointe vers {c}, qui n'est pas une route"


def test_la_racine_ne_sallume_pas_sur_toutes_les_pages():
    """
    ⚠️ SANS LA GARDE, « / » EST PRÉFIXE DE TOUT et le rail annonce « Dashboard » partout —
    l'indicateur de position cesse d'indiquer quoi que ce soit.
    """
    with open(os.path.join(RACINE, "templates", "_rail.html"), encoding="utf-8") as f:
        rail = f.read()
    assert "p !== '/'" in rail


def test_la_bande_dit_tiret_quand_elle_ne_sait_pas():
    """
    ⚠️ « PAS ENCORE DE VENTE » ET « ZÉRO EURO ENCAISSÉ » mènent à deux lectures opposées à 11 h
    du matin.
    """
    with open(os.path.join(RACINE, "templates", "_rail.html"), encoding="utf-8") as f:
        rail = f.read()
    assert 'id="st-ca">&mdash;<' in rail


def test_lechec_de_la_bande_est_silencieux():
    """
    ⚠️ UN BANDEAU D'INFORMATION QUI AFFICHE UNE ERREUR ROUGE EN TRAVERS DE L'ÉCRAN DE TRAVAIL
    est pire que pas de bandeau : le réseau qui hoquette ne doit pas ressembler à une panne de
    caisse.
    """
    with open(os.path.join(RACINE, "templates", "_rail.html"), encoding="utf-8") as f:
        rail = f.read()
    i = rail.index("fetch('/api/statut')")
    assert ".catch(" in rail[i:i + 1800]
