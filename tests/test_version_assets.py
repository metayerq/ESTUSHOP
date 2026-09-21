"""
LA VERSION DES FICHIERS STATIQUES.

⚠️ ELLE ÉTAIT ÉCRITE À LA MAIN, ET ELLE A ÉTÉ OUBLIÉE. Elle valait « 20260916d » le
21 septembre, après une journée passée à déplacer des règles dans `style.css`. Chaque navigateur
servait donc l'ancienne feuille, où les nouvelles classes n'existaient pas : les onglets sont
sortis en boutons nus, le bandeau-réponse sans mise en forme.

⚠️ C'EST LA PIRE FAMILLE DE BOGUE. Le déploiement réussit, les tests passent, la page rendue par
le serveur est juste — et l'écran est faux. On cherche l'erreur dans le code qu'on vient
d'écrire, qui n'a rien à se reprocher.
"""

import os

import app as flask_app

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(RACINE, "static")


def test_la_version_suit_le_contenu_des_fichiers(tmp_path, monkeypatch):
    avant = flask_app._version_assets()
    chemin = os.path.join(STATIC, "style.css")
    original = open(chemin, "rb").read()
    try:
        with open(chemin, "ab") as f:
            f.write(b"\n/* changement */\n")
        assert flask_app._version_assets() != avant, \
            "la version ne bouge pas quand une feuille change"
    finally:
        with open(chemin, "wb") as f:
            f.write(original)
    assert flask_app._version_assets() == avant, "la version ne revient pas en arrière"


def test_elle_ne_bouge_pas_quand_rien_ne_change():
    """
    ⚠️ SINON CHAQUE DÉPLOIEMENT FORCE UN RECHARGEMENT COMPLET. C'est pourquoi c'est le CONTENU
    qui est lu, et non `mtime` — qui change à chaque `git clone`, donc à chaque déploiement
    Vercel, même quand pas un octet n'a bougé.
    """
    assert flask_app._version_assets() == flask_app._version_assets()
    src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    bloc = src[src.index("def _version_assets("):src.index("ASSET_VERSION = _version_assets()")]
    assert "getmtime" not in bloc and "st_mtime" not in bloc


def test_elle_couvre_les_feuilles_et_les_scripts():
    """
    ⚠️ `transactions.js` A CHANGÉ LE MÊME JOUR QUE `style.css`. Ne surveiller que la feuille
    aurait laissé le navigateur exécuter l'ancien script — les boutons journée/soir auraient été
    dessinés sans rien faire au clic, ce qui est pire qu'absent.
    """
    src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    bloc = src[src.index("def _version_assets("):src.index("ASSET_VERSION = _version_assets()")]
    assert '(".css", ".js")' in bloc


def test_elle_nest_plus_une_constante_ecrite_a_la_main():
    src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    assert 'ASSET_VERSION = "' not in src, "une version en dur est revenue"
    assert "ASSET_VERSION = _version_assets()" in src


def test_les_gabarits_la_portent_sur_leurs_assets():
    """Une page qui oublie `?v=` sert un fichier que le navigateur garde cinq minutes — et une
    feuille périmée cinq minutes après un déploiement, c'est un écran cassé cinq minutes."""
    manquants = []
    for nom in sorted(os.listdir(os.path.join(RACINE, "templates"))):
        if not nom.endswith(".html"):
            continue
        g = open(os.path.join(RACINE, "templates", nom), encoding="utf-8").read()
        for ref in ("/static/style.css", "/static/dashboard.js", "/static/transactions.js",
                    "/static/ui.js"):
            if ref in g and f"{ref}?v=" not in g:
                manquants.append(f"{nom} → {ref}")
    assert not manquants, manquants


def test_un_statique_illisible_ne_fige_pas_la_version(monkeypatch):
    """
    ⚠️ MIEUX VAUT FAIRE RECHARGER TROP SOUVENT QUE SERVIR UNE FEUILLE PÉRIMÉE EN SILENCE. Un
    repli sur une constante rendrait le cache définitivement collant le jour où le dossier
    devient illisible.
    """
    def boum(_):
        raise OSError("dossier absent")
    monkeypatch.setattr(flask_app.os, "listdir", boum)
    v = flask_app._version_assets()
    assert v.startswith("boot") and len(v) > 4
