"""
LA CHARTE, SUR LES SEIZE PAGES.

⚠️ ELLE NE VIVAIT QUE SUR LE TABLEAU DE BORD, et le reste de la plateforme gardait l'ancienne
palette : un accent vert qui servait à la fois d'interactif ET de « bon état », des tables en
chasse fixe, huit rayons différents. Passer d'un écran à l'autre donnait l'impression de changer
de logiciel.

⚠️ LA PALETTE A DONC ÉTÉ PROMUE, ET LES ANCIENS NOMS REPOINTÉS. Quinze gabarits écrivent
`var(--text)`, `var(--border)`, `var(--muted)` : les renommer aurait demandé de tous les réécrire
le même jour, donc de tous les relire le même jour. En repointant les noms, la plateforme change
d'apparence sans qu'une ligne de gabarit bouge.

⚠️ CE CONTRÔLE GARDE CE QUI VIENT D'ÊTRE GAGNÉ. Sans lui, la prochaine page ajoutée arrivera avec
ses propres verts Material — c'est exactement ainsi que 180 couleurs en dur se sont accumulées.
"""

import html as H
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "templates")
PAGES = sorted(n for n in os.listdir(DOSSIER) if n.endswith(".html"))


def _lire(nom):
    return open(os.path.join(DOSSIER, nom), encoding="utf-8").read()


def _charge_la_feuille(nom):
    s = _lire(nom)
    return bool(re.search(r"""<link[^>]+href=["'][^"']*style\.css""", s)) or "{% extends" in s


def _sans_commentaires(s):
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    return re.sub(r"\{#.*?#\}", " ", s, flags=re.S)


@pytest.mark.parametrize("nom", PAGES)
def test_aucune_couleur_en_dur(nom):
    """
    ⚠️ UNE COULEUR EN DUR NE CONNAÎT PAS LE MODE SOMBRE. `#2e7d32` sur fond noir passe du vert
    sourd au vert criard, et `#e8f5e9` reste un fond blanc cassé sur lequel plus rien ne se lit.
    La page s'affiche ; le texte a disparu.
    """
    s = _sans_commentaires(_lire(nom))
    # ⚠️ UNE PAGE AUTONOME NE PEUT PAS ÉCRIRE `var()`. /tpa ne charge pas style.css : la
    # substitution y a d'abord produit `--border: var(--border)`, qui ne résout rien — bordures
    # et couleurs d'état effacées sur la seule page qu'un tiers consulte. Elle garde donc ses
    # valeurs littérales, et c'est `test_la_page_autonome_copie_la_charte` qui les tient.
    # ⚠️ ON CHERCHE LA BALISE, PAS LE MOT. Le premier jet testait `"style.css" not in source` —
    # et le commentaire qui, DANS tpa.html, explique qu'elle ne charge pas style.css contenait
    # ces mots-là. Le détecteur reconnaissait sa propre explication.
    autonome = not _charge_la_feuille(nom)
    if autonome:
        pytest.skip("page autonome : ses littéraux sont vérifiés contre la palette")
    fautifs = []
    for i, l in enumerate(s.split("\n"), 1):
        # ⚠️ `theme-color` EST LA SEULE EXCEPTION, et elle est éprouvée plus bas : la barre
        # système du téléphone la lit AVANT tout CSS.
        if "theme-color" in l:
            continue
        for m in re.finditer(r"#[0-9a-fA-F]{6}\b", l):
            fautifs.append(f"{nom}:{i} {m.group(0)}")
    assert not fautifs, fautifs[:10]


@pytest.mark.parametrize("nom", PAGES)
def test_la_barre_systeme_reprend_le_fond_de_la_page(nom):
    """
    ⚠️ ELLE PEINT LE HAUT DE L'ÉCRAN SUR TÉLÉPHONE. Restée à la crème de l'avant-avant-charte,
    elle encadrait la page d'un bandeau d'une autre époque — visible seulement sur le mobile du
    comptoir, c'est-à-dire là où personne ne va chercher un défaut de thème.
    """
    s = _lire(nom)
    m = re.search(r'name="theme-color" content="(#[0-9A-Fa-f]{6})"', s)
    if not m:
        pytest.skip("page sans barre système déclarée")
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index(":root {")
    fond = re.search(r"--bg-page:\s*(#[0-9A-Fa-f]{6})", css[i:css.index("\n}", i)]).group(1)
    assert m.group(1).upper() == fond.upper(), f"{m.group(1)} ≠ --bg-page {fond}"


def test_la_palette_declare_ses_trois_familles():
    """
    ⚠️ TROIS FAMILLES, TROIS RÔLES. L'ÉTAT dit si c'est bon ou mauvais ; les CATÉGORIES
    distinguent des types sans les juger ; la RAMPE dit « plus ou moins ». Les confondre fait
    lire « problème » là où une page ne dit que « fournitures ».

    ⚠️ ET LES CATÉGORIES NE DOIVENT PAS RESSEMBLER À UN ÉTAT. C'est pourquoi aucune n'est verte
    ni rouge : une catégorie qui ressemble à une alerte se lit comme une alerte.
    """
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index(":root {")
    bloc = css[i:css.index("\n}", i)]
    for famille, combien in (("--cat-", 12), ("--ramp-", 6)):
        n = len(re.findall(rf"{re.escape(famille)}\d[a-z-]*\s*:", bloc))
        assert n >= combien, f"{famille} : {n} déclarés, {combien} attendus"
    for etat in ("--green", "--red", "--amber", "--green-soft", "--red-soft", "--amber-soft"):
        assert f"{etat}:" in bloc.replace(" ", ""), etat


def test_les_tables_ne_sont_plus_en_chasse_fixe():
    """
    ⚠️ ALIGNER LES CHIFFRES EST JUSTE ; LE FAIRE EN CHANGEANT DE POLICE NE L'EST PAS.
    `tabular-nums` aligne les colonnes sans toucher aux libellés — le mono rendait les noms de
    produits plus larges et moins lisibles, et donnait à chaque page l'air d'un journal de
    serveur.
    """
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index("\ntable {")
    bloc = css[i:css.index("}", i)]
    assert "font-family" not in bloc, "les tables imposent encore une police"
    assert "tabular-nums" in bloc, "les chiffres ne s'alignent plus"


def test_lechelle_des_rayons_tient_en_trois_valeurs():
    """
    ⚠️ LA FEUILLE EN COMPTAIT HUIT. Aucun n'est faux seul ; ensemble ils donnent une page dont
    on ne sait pas dire ce qui cloche — et c'est précisément ce qui la fait paraître mal finie.
    """
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index("L'ÉCHELLE DES RAYONS")
    bloc = css[i:]
    assert "--r: 8px" in bloc and "--r-sm: 6px" in bloc
    assert "border-radius: 999px" in bloc, "les pastilles n'ont pas de rayon rond"


def _palette():
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index(":root {")
    return dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", css[i:css.index("\n}", i)]))


def test_la_page_autonome_copie_la_charte():
    """
    ⚠️ LA PAGE COMPTABLE VIT SEULE, derrière un jeton, sans la feuille de la plateforme. Elle ne
    peut donc pas hériter de la palette : elle la recopie. Et ce qui est recopié dérive — c'est
    la raison même pour laquelle elle portait encore les beiges de l'avant-charte.

    ⚠️ CE CONTRÔLE COMPARE CHAQUE LITTÉRAL AU JETON DONT IL EST LA COPIE. Un `var()` y serait
    pire que le littéral : il ne résout rien, et la déclaration disparaît sans erreur.
    """
    src = _lire("tpa.html")
    pal = _palette()
    bloc = src[src.index(":root{"):src.index("}", src.index(":root{"))]
    locales = dict(re.findall(r"(--[a-z-]+):\s*(#[0-9A-Fa-f]{6})", bloc))
    attendu = {"--bg": "--bg-page", "--card": "--bg-card", "--border": "--border",
               "--text": "--text", "--muted": "--muted", "--faint": "--faint",
               "--green": "--green", "--red": "--red", "--spec": "--accent",
               "--amber": "--amber", "--amber-soft": "--amber-soft"}
    for local, jeton in attendu.items():
        assert local in locales, f"{local} n'est plus déclaré sur la page autonome"
        assert locales[local].upper() == pal[jeton].upper(), (
            f"{local} = {locales[local]} mais la charte dit {jeton} = {pal[jeton]}")
    # ⚠️ ET TOUT `var()` UTILISÉ DOIT ÊTRE DÉCLARÉ ICI. Rien ne le signale à l'écran : la
    # règle est simplement ignorée, et la page s'affiche sans bordures.
    declares = set(re.findall(r"(--[a-z-]+)\s*:", bloc))
    for u in set(re.findall(r"var\((--[a-z-]+)\)", src)):
        assert u in declares, f"{u} est utilisé mais jamais déclaré sur la page autonome"
