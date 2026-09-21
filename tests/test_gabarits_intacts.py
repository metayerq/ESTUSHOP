"""
LES GABARITS SONT-ILS ENTIERS ?

⚠️ UN ATTRIBUT NON TERMINÉ AVALE LE DOCUMENT. Une découpe de la refonte a emporté le `">` qui
ferme le lien vers la feuille de style, ET la balise `<style>` ouvrante qui suivait. Le
navigateur consomme alors tout jusqu'au guillemet suivant : la page sort blanche et
désorganisée, sans qu'aucune erreur n'apparaisse nulle part.

⚠️ CINQ PAGES ONT PORTÉ CETTE BLESSURE PENDANT DES JOURS — events, fidelidade, holidays,
reconciliation, sop. Le serveur rendait exactement ce qu'il fallait, Jinja compilait, les mille
tests passaient. Rien dans ce dépôt ne regardait la STRUCTURE du HTML produit, parce que chaque
test regardait le contenu qui l'intéressait.

⚠️ ET C'EST UNE ERREUR DE CISEAUX, PAS DE RAISONNEMENT. Couper d'une chaîne à une autre dans un
fichier est rapide et prend deux caractères de trop sans prévenir. Ce contrôle-ci est le prix à
payer pour continuer d'éditer ainsi.
"""

import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "templates")

PAGES = sorted(n for n in os.listdir(DOSSIER)
               if n.endswith(".html") and not n.startswith("_"))
PARTIELS = sorted(n for n in os.listdir(DOSSIER)
                  if n.endswith(".html") and n.startswith("_"))


def lire(nom):
    return open(os.path.join(DOSSIER, nom), encoding="utf-8").read()


def _hors_code(s):
    """Le balisage seul : ni script, ni style, ni commentaire — leurs `<` et `>` leur appartiennent."""
    s = re.sub(r"<script\b.*?</script>", "", s, flags=re.S)
    s = re.sub(r"<style>.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    return re.sub(r"\{#.*?#\}", "", s, flags=re.S)


@pytest.mark.parametrize("nom", PAGES + PARTIELS)
def test_aucune_balise_ne_reste_ouverte(nom):
    """
    ⚠️ C'EST LE CONTRÔLE QUI AURAIT ÉVITÉ CINQ PAGES CASSÉES. Une balise dont le `>` manque
    transforme tout ce qui suit en valeur d'attribut — y compris le reste de la feuille de
    style et le corps de la page.

    ⚠️ UNE BALISE SUR PLUSIEURS LIGNES EST NORMALE. La première version de ce test cherchait
    « pas de `>` avant la fin de la ligne » et accusait vingt `<input>` parfaitement sains. Un
    contrôle qui crie sur du code correct finit désactivé, et il emporte avec lui le cas qu'il
    devait attraper. Ce qui compte : un `<` qui arrive AVANT le `>` attendu.
    """
    s = _hors_code(lire(nom))
    ouvertes = []
    for m in re.finditer(r"<[a-zA-Z][^\s>/]*", s):
        suite = s[m.end():]
        fin = suite.find(">")
        debut_suivant = suite.find("<")
        if fin < 0 or (debut_suivant >= 0 and debut_suivant < fin):
            ouvertes.append(s[:m.start()].count("\n") + 1)
    assert not ouvertes, f"balise(s) non fermée(s), ligne(s) {ouvertes}"


@pytest.mark.parametrize("nom", PAGES + PARTIELS)
def test_les_blocs_de_style_et_de_script_sont_refermes(nom):
    s = lire(nom)
    assert s.count("<style>") == s.count("</style>"), \
        f"<style> {s.count('<style>')} vs </style> {s.count('</style>')}"
    # ⚠️ `<script src=…>` COMPTE AUSSI : il se ferme par `</script>`, sans quoi le reste de la
    # page devient du code jamais exécuté.
    assert len(re.findall(r"<script\b", s)) == s.count("</script>"), \
        f"<script {len(re.findall(r'<script\\b', s))} vs </script> {s.count('</script>')}"


# ⚠️ `tpa.html` EST VOLONTAIREMENT AUTONOME. C'est la page ouverte par la comptable avec un
# jeton dans l'URL, hors login et hors coquille : elle ne charge ni la feuille commune ni le
# rail, pour qu'un visiteur muni d'un lien ne voie QUE la réconciliation. L'exclure ici est un
# choix, pas un oubli — et l'écrire évite qu'on « répare » un jour cette autonomie.
AUTONOMES = {"tpa.html"}


@pytest.mark.parametrize("nom", [n for n in PAGES if n not in AUTONOMES])
def test_chaque_page_charge_la_feuille_commune_et_la_ferme(nom):
    """
    ⚠️ SANS LA FEUILLE COMMUNE, LA PAGE SORT NUE. C'est déjà arrivé à `contabilidade.html`, qui
    portait sa propre palette d'avant l'identité Flux et affichait le rail en liste de liens.
    """
    s = lire(nom)
    assert '<link rel="stylesheet" href="/static/style.css?v={{ v }}">' in s, \
        "feuille commune absente ou mal fermée"


@pytest.mark.parametrize("nom", PAGES)
def test_le_style_de_page_ouvre_avant_de_fermer(nom):
    """
    ⚠️ LA DÉCOUPE AVAIT LAISSÉ UN `</style>` ORPHELIN. Les règles se retrouvaient dans le
    document au lieu d'une feuille — lues comme du texte, donc jamais appliquées.
    """
    s = lire(nom)
    if "</style>" not in s:
        return
    assert s.index("<style>") < s.index("</style>")


@pytest.mark.parametrize("nom", PAGES)
def test_le_document_a_une_tete_et_un_corps(nom):
    s = lire(nom)
    for balise in ("</head>", "<body>", "</body>", "</html>"):
        assert balise in s, balise


@pytest.mark.parametrize("nom", PAGES)
def test_les_guillemets_dattributs_sont_appaires(nom):
    """
    ⚠️ UN GUILLEMET IMPAIR DANS UNE BALISE EST LA MÊME BLESSURE, EN PLUS DISCRET. Il n'y a pas
    d'erreur : il y a une page qui s'arrête au milieu.
    """
    s = lire(nom)
    # Hors scripts et styles, où les guillemets appartiennent au code.
    corps = re.sub(r"<script\b.*?</script>", "", s, flags=re.S)
    corps = re.sub(r"<style>.*?</style>", "", corps, flags=re.S)
    corps = re.sub(r"<!--.*?-->", "", corps, flags=re.S)
    # ⚠️ ON COMPTE PAR BALISE, PAS PAR LIGNE. Un attribut peut s'étendre sur deux lignes ; y
    # voir un guillemet impair accuserait du code sain, et un test qui crie sur du correct
    # finit désactivé.
    impaires = []
    for m in re.finditer(r"<[a-zA-Z][^>]*>", corps, re.S):
        if m.group(0).count('"') % 2:
            impaires.append(corps[:m.start()].count("\n") + 1)
    assert not impaires, f"guillemet impair dans une balise, ligne(s) {impaires}"


def test_toutes_les_pages_compilent_et_se_rendent():
    """
    ⚠️ COMPILER N'EST PAS RENDRE. Jinja acceptait les cinq pages cassées sans broncher : le HTML
    abîmé lui est transparent. Ce test les MONTE, ce qui attrape en plus un `include` mort ou
    une variable exigée.
    """
    import app as flask_app
    import menu as _menu
    from flask import render_template
    contexte = {"v": "test", "role": "admin", "menu": _menu.construire(), "rail": True,
                # `tpa.html` attend son jeton : une page qui exige une variable doit la
                # recevoir, sinon le test échoue sur son propre montage et pas sur la page.
                "token": "jeton-de-test"}
    with flask_app.app.test_request_context("/"):
        for nom in PAGES:
            try:
                html = render_template(nom, **contexte)
            except Exception as e:
                pytest.fail(f"{nom} : {type(e).__name__} {e}")
            assert "</html>" in html, nom
            # ⚠️ ET LA FEUILLE DOIT SORTIR AVEC SA VERSION. Un `?v=` vide veut dire que le
            # `context_processor` n'a pas tourné — et un fichier sans version reste dans le
            # cache du navigateur après un déploiement.
            if nom not in AUTONOMES:
                assert "/static/style.css?v=test" in html, nom
