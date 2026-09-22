"""
LA CHARTE DU TABLEAU DE BORD EST-ELLE SUIVIE ?

⚠️ UNE PAGE À MOITIÉ REFAITE EST PIRE QU'UNE PAGE PAS REFAITE. Deux gris à deux pixels
d'écart, deux rayons, deux graisses — chacun passe inaperçu seul, et ensemble ils font une page
qui semble mal chargée. On ne sait pas dire ce qui cloche, on sait seulement qu'on n'y croit pas.

⚠️ ET CE N'EST PAS UNE AFFAIRE DE PROPRETÉ. La charte `--db-*` porte le mode sombre : une
couleur écrite en dur reste claire sur fond noir. Ce qui se voit comme une négligence en clair
devient illisible en sombre.

⚠️ LE RESTE DE LA PLATEFORME GARDE L'ANCIENNE CHARTE, et c'est voulu — la refonte va page par
page. Ce contrôle ne porte donc QUE sur le tableau de bord.
"""

import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Les fichiers qui portent le nouveau langage.
SOUS_CHARTE = ("templates/index.html", "static/dashboard.js", "static/dashboard.css")


def _lire(rel):
    return open(os.path.join(RACINE, rel), encoding="utf-8").read()


def _sans_commentaires(s, html):
    if html:
        s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
        s = re.sub(r"\{#.*?#\}", " ", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    return re.sub(r"//[^\n]*", " ", s)


def _lignes(rel):
    """Le contenu utile, ligne par ligne, sans les commentaires."""
    brut = _lire(rel)
    html = rel.endswith(".html")
    propre = _sans_commentaires(brut, html)
    return [(i + 1, l) for i, l in enumerate(propre.split("\n"))]


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucun_ancien_jeton_ne_subsiste(rel):
    """
    ⚠️ `var(--text)` ET `var(--db-ink)` SONT DEUX NOIRS DIFFÉRENTS. Mélangés sur le même écran,
    ils donnent deux encres — visible surtout en mode sombre, où l'ancienne palette n'a pas les
    mêmes contrastes.
    """
    fautifs = []
    for n, l in _lignes(rel):
        for m in re.finditer(r"var\(--(?!db-)([a-z0-9-]+)", l):
            fautifs.append(f"{rel}:{n} var(--{m.group(1)})")
    assert not fautifs, fautifs[:12]


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucune_couleur_nest_ecrite_en_dur(rel):
    """
    ⚠️ UNE COULEUR EN DUR NE CONNAÎT PAS LE MODE SOMBRE. `#1A1F36` sur fond noir est illisible,
    et rien ne le signale : la page s'affiche, le texte a disparu.
    """
    fautifs = []
    for n, l in _lignes(rel):
        for m in re.finditer(r"#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b|rgba?\([\d.,\s]+\)", l):
            # ⚠️ UNE ANCRE HTML N'EST PAS UNE COULEUR. `href="#reglages"` et les entités
            # (`&#9888;`) portent un dièse sans être une teinte.
            avant = l[max(0, m.start() - 2):m.start()]
            if avant.endswith(("&", "=", '"#', "'#")) or "&#" in l[max(0, m.start()-2):m.end()]:
                continue
            # ⚠️ DEUX EXEMPTIONS, ET ELLES SONT ÉPROUVÉES PLUS BAS. La barre système du
            # téléphone lit `theme-color` AVANT tout CSS ; et les replis de `jetons()` évitent
            # un graphique dessiné en transparent si `getComputedStyle` répond vide. Exempter
            # sans vérifier les laisserait se périmer en silence.
            if "theme-color" in l or "||" in l:
                continue
            fautifs.append(f"{rel}:{n} {m.group(0)}")
    assert not fautifs, fautifs[:12]


def _palette(bloc):
    """Les couleurs déclarées dans un bloc de `style.css`."""
    css = _lire("static/style.css")
    i = css.index(bloc) + len(bloc)
    fin = css.index("\n}", i) if not bloc.startswith("@media") else css.index("\n  }", i)
    return {k: v.upper() for k, v in
            re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{6})", css[i:fin])}


def test_les_couleurs_en_dur_qui_restent_suivent_la_palette():
    """
    ⚠️ UNE EXEMPTION MUETTE DEVIENT UNE PORTE. Deux couleurs ne peuvent pas être des jetons ;
    plutôt que de les exclure sans rien dire, on vérifie qu'elles valent exactement ce que la
    palette déclare.

    · `<meta name="theme-color">` — la barre système du téléphone la lit AVANT tout CSS.
    · les replis de `jetons()` — `getComputedStyle` peut rendre une chaîne vide avant que la
      feuille soit appliquée ; sans repli, les graphiques se dessineraient en transparent.

    ⚠️ ET LA SOURCE A CHANGÉ. Ces valeurs étaient comparées à `dashboard.css`, qui déclarait sa
    propre palette ; celle-ci vit désormais dans `style.css` et sert toute la plateforme. Un
    test qui interroge une source périmée passe au vert sur des valeurs fausses.
    """
    clair = _palette(":root {")
    correspondance = {
        "--db-iris": "--accent", "--db-slate": "--flux-leave", "--db-line-soft": "--bar-bg",
        "--db-faint": "--faint", "--db-ink": "--text", "--db-green": "--green",
        "--db-red": "--red", "--db-amber": "--amber", "--db-iris-soft": "--spec-soft",
        "--db-green-soft": "--green-soft", "--db-red-soft": "--red-soft",
        "--db-amber-soft": "--amber-soft",
        "--db-alt": "--bar-bg",
    }
    js = _lire("static/dashboard.js")
    i = js.index("function jetons(")
    bloc = js[i:js.index("\n}", i)]
    replis = re.findall(r"v\('(--db-[a-z-]+)'\)\s*\|\|\s*'(#[0-9A-Fa-f]{6})'", bloc)
    assert replis, "les replis ont disparu — les graphiques se dessineraient en transparent"
    for jeton, valeur in replis:
        racine = correspondance.get(jeton)
        if racine is None or racine not in clair:
            continue      # jeton sans équivalent direct : rien à comparer
        assert valeur.upper() == clair[racine], \
            f"{jeton} : repli {valeur}, palette {clair[racine]} ({racine})"

    html = _lire("templates/index.html")
    m = re.search(r'name="theme-color" content="(#[0-9A-Fa-f]{6})"', html)
    assert m and m.group(1).upper() == clair["--bg-page"], \
        f"theme-color {m and m.group(1)} ≠ --bg-page {clair.get('--bg-page')}"


def test_la_palette_est_declaree_dans_les_deux_themes():
    """
    ⚠️ UN JETON DÉCLARÉ EN CLAIR SEULEMENT RESTE CLAIR EN SOMBRE. C'est pire qu'une couleur en
    dur : celle-ci se voit à la relecture, tandis qu'un jeton a l'air correct partout.

    ⚠️ ET CE CONTRÔLE COUVRE MAINTENANT TOUTE LA PLATEFORME, pas seulement le tableau de bord —
    la palette a été promue, les quinze pages en dépendent.
    """
    clair = set(_palette(":root {"))
    for bloc in ("@media (prefers-color-scheme: dark) {\n  :root {",
                 ':root[data-theme="dark"] {'):
        manquants = sorted(clair - set(_palette(bloc)))
        assert not manquants, f"{bloc.strip()} ne déclare pas {manquants}"


def test_le_tableau_de_bord_ne_redeclare_pas_la_palette():
    """
    ⚠️ DEUX SOURCES POUR UNE SEULE VÉRITÉ, C'EST CELLE QU'ON CORRIGE ET CELLE QU'ON OUBLIE. La
    charte du tableau de bord déclarait ses propres couleurs ; elle référence désormais la
    palette commune. Y remettre un hex rouvrirait la divergence sans que rien ne le signale.
    """
    css = _lire("static/dashboard.css")
    i = css.index(".db {")
    bloc = css[i:css.index("\n}", i)]
    durs = re.findall(r"--db-[a-z-]+\s*:\s*(#[0-9A-Fa-f]{3,6})", bloc)
    assert not durs, f"la charte redéclare des couleurs : {durs}"


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucune_famille_de_police_nest_imposee(rel):
    """
    ⚠️ LA CHARTE N'A QU'UNE FAMILLE, ET ELLE EST SUR `body`. Imposer une chasse fixe ici ou là
    pour « faire technique » produit deux typographies sur le même écran — et les chiffres
    s'alignent déjà par `tabular-nums`, sans changer de police.
    """
    fautifs = [f"{rel}:{n}" for n, l in _lignes(rel)
               if re.search(r"font-family\s*:", l)]
    assert not fautifs, fautifs


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucun_rayon_hors_charte(rel):
    """
    ⚠️ LA CHARTE A TROIS RAYONS : 8 px pour une carte, 6 px à l'intérieur, 999 px pour une
    pastille. Un quatrième — 10, 12, 14 — se voit à côté des trois autres sans qu'on sache
    lequel est le bon.
    """
    permis = {"8px", "6px", "999px", "50%", "2px", "3px", "0"}
    fautifs = []
    for n, l in _lignes(rel):
        for m in re.finditer(r"border-radius\s*:\s*([^;\"'}]+)", l):
            for v in m.group(1).split():
                if v.strip() and v.strip() not in permis and "var(--db-" not in v:
                    fautifs.append(f"{rel}:{n} border-radius:{m.group(1).strip()}")
                    break
    assert not fautifs, fautifs[:12]


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucune_ombre_inventee(rel):
    """
    ⚠️ LA CHARTE N'A QU'UNE OMBRE, `--db-sh`, et elle est presque invisible — c'est le propre de
    ce langage. Une ombre portée ajoutée à la main fait flotter une carte au milieu de cartes
    posées à plat.
    """
    fautifs = [f"{rel}:{n}" for n, l in _lignes(rel)
               if re.search(r"box-shadow\s*:", l) and "--db-sh" not in l
               # ⚠️ UNE OMBRE `inset` N'EST PAS UNE ÉLÉVATION, C'EST UN FILET. Celle de
               # l'en-tête collant remplace une bordure que `position:sticky` ferait disparaître
               # au défilement — elle ne fait flotter aucune carte.
               and "inset" not in l]
    assert not fautifs, fautifs


# ── Les corrections tiennent-elles, ou seulement l'absence de fautes ? ───────────────────────
#
# ⚠️ CINQ MUTANTS ONT SURVÉCU À LA PREMIÈRE BATTERIE. Le contrôle cherchait des anciens jetons et
# des couleurs en dur — or remettre `class="delta-up"` n'en introduit aucun : la classe est
# neutre, c'est `style.css` qui la peint en chasse fixe. Vérifier l'absence d'une faute ne
# vérifie pas la présence de sa correction.

ANCIENS_COMPOSANTS = ("delta-up", "delta-down", "kpi-cell", "kpi-label", "kpi-value",
                      "kpi-delta", "kpi-grid", "seuil-marque", "seuil-wrap", "tx-answer",
                      "maillon", "view-tab", "pay-compact")


@pytest.mark.parametrize("rel", ["templates/index.html", "static/dashboard.js"])
def test_aucun_composant_de_lancienne_charte(rel):
    """
    ⚠️ CES CLASSES SONT PEINTES PAR `style.css` — chasse fixe, fonds en dur, rayons d'avant. Les
    employer ici ramène l'ancien thème sans écrire une seule couleur : rien ne le signale, et la
    page a simplement l'air mal chargée par endroits.
    """
    fautifs = []
    for n, l in _lignes(rel):
        for c in ANCIENS_COMPOSANTS:
            if re.search(rf'class="[^"]*\b{c}\b', l) or f"'{c}'" in l:
                fautifs.append(f"{rel}:{n} {c}")
    assert not fautifs, fautifs[:10]


def test_les_trois_reparations_de_portee_sont_en_place():
    """
    ⚠️ `style.css` RESTE CHARGÉ SOUS LA CHARTE, et trois de ses règles traversaient : la chasse
    fixe des tables, et deux filets de bordure qui s'ajoutaient aux nôtres. Chacune est
    invisible seule ; ensemble elles font une page qui ne ressemble à rien de précis.
    """
    css = _lire("static/dashboard.css")
    for regle, pourquoi in [
        (".db table, .db th, .db td { font-family: inherit; }",
         "les tableaux repasseraient en chasse fixe"),
        (".db tbody tr { border-bottom: 0; }",
         "chaque ligne porterait deux filets de deux gris"),
        (".db thead th { border-bottom: 0; }",
         "l'en-tête porterait deux filets"),
    ]:
        assert regle in css, pourquoi


def test_les_surcouches_sont_dans_la_portee_des_jetons():
    """
    ⚠️ ELLES VIVENT HORS DE `.page`, donc `var(--db-…)` n'y résout rien — la propriété est
    ignorée, pas signalée, et l'élément hérite d'une couleur que personne n'a choisie. C'est ce
    qui expliquait la bannière jaune pâle et la modale à l'ancien rayon.
    """
    html = _lire("templates/index.html")
    # ⚠️ SEULS LES ÉLÉMENTS DE PREMIER NIVEAU. Un enfant hérite de la portée de son parent :
    # exiger `class="db"` sur `#popup-error`, qui vit DANS `#popup-modal.db`, accuserait du
    # balisage sain — et un test qui crie sur du correct finit désactivé.
    apres = html[html.index("<!-- /page -->"):]
    manquantes = []
    profondeur = 0
    for m in re.finditer(r'<div\b([^>]*)>|</div>', apres):
        if m.group(0) == "</div>":
            profondeur = max(0, profondeur - 1)
            continue
        attrs = m.group(1)
        if profondeur == 0:
            ident = (re.findall(r'id="([\w-]+)"', attrs) or [""])[0]
            classes = (re.findall(r'class="([^"]*)"', attrs) or [""])[0].split()
            if ident and "db" not in classes:
                manquantes.append(ident)
        profondeur += 1
    assert not manquantes, f"hors portée des jetons : {manquantes}"


# ⚠️ CE CONTRÔLE A DÉMÉNAGÉ AVEC LA PALETTE. Il vérifiait que `dashboard.css` déclarait ses
# jetons dans ses trois blocs de thème ; la charte ne déclare plus de couleurs — elle
# référence `style.css`. La garantie vit désormais dans
# `test_la_palette_est_declaree_dans_les_deux_themes`, et elle couvre les quinze pages.
