# -*- coding: utf-8 -*-
"""
LE CONTRASTE DES JETONS DE TEXTE — MESURÉ, PAS SUPPOSÉ.

⚠️ CE TEST EXISTE PARCE QUE J'AI EU TORT À L'ŒIL. `--faint` avait l'air d'un gris moyen
acceptable ; mesuré, il valait 2,78:1 sur `--bar-bg` et 3,22:1 sur `--spec-soft`, contre les
4,5:1 que demande le niveau AA. Il portait 65 usages de texte à 11 et 12 px — des montants,
des taux, des dates. `--muted` n'était pas mieux (3,83:1 sur `--bar-bg`).

⚠️ ET IL VÉRIFIE AUSSI QUE LES BLOCS NE DIVERGENT PAS. Ces trois couleurs vivent à SEPT
endroits : deux blocs clairs et deux blocs sombres dans `style.css`, une copie en dur dans
`tpa.html`, une autre dans la page de connexion servie par `app.py`, et les replis de
`dashboard.js`. Corriger six sur sept laisse une page derrière — c'est exactement la faute
qui a rendu `marketing.html` illisible sans qu'aucun test ne rougisse.

Ce fichier couvre les cinq premiers. Les deux derniers sont tenus par
`test_charte_plateforme.py` et `test_charte_dashboard.py`, qui comparent déjà les valeurs en
dur à la charte — et qui ont tous les deux mordu quand j'ai corrigé les jetons sans eux.

Ce qui n'est PAS vérifié ici : les couleurs de sens (vert, rouge, ambre) et les échelles
catégorielles. Elles sont mesurées à part quand elles bougent ; les mêler ici rendrait le
message de l'échec illisible.
"""
import io
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ⚠️ LE SEUIL EST CELUI DU TEXTE NORMAL. Les jetons testés habillent du 11-13 px : la
# tolérance « grand texte » à 3:1 ne s'applique à aucun d'eux.
AA = 4.5


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hexa):
    h = hexa.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contraste(a, b):
    la, lb = _luminance(a), _luminance(b)
    haut, bas = max(la, lb), min(la, lb)
    return (haut + 0.05) / (bas + 0.05)


def sur(fond, dessus, alpha):
    """Aplatit une couche translucide — `--bg-hover` en est une, et l'ignorer flatte le calcul."""
    f = [int(fond.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    d = [int(dessus.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02X%02X%02X" % tuple(round(d[i] * alpha + f[i] * (1 - alpha)) for i in range(3))


def _jetons(texte):
    """Tous les `--nom: #RRGGBB` d'un texte, dans l'ordre, avec les doublons conservés."""
    return re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", texte)


def test_les_cinq_declarations_de_jetons_ne_divergent_pas():
    """
    ⚠️ SEPT ENDROITS POUR TROIS COULEURS. Ce test en tient cinq ; les deux autres sont tenus
    par les gardes de charte. Tant qu'ils sont sept, c'est la seule chose qui empêche une page
    de garder l'ancienne palette après une correction.
    """
    css = io.open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    tpa = io.open(os.path.join(RACINE, "templates", "tpa.html"), encoding="utf-8").read()

    par_nom = {}
    for nom, valeur in _jetons(css) + _jetons(tpa):
        if nom in ("text", "muted", "faint"):
            par_nom.setdefault(nom, []).append(valeur.upper())

    for nom in ("text", "muted", "faint"):
        valeurs = par_nom.get(nom, [])
        assert len(valeurs) >= 2, f"--{nom} : une seule déclaration trouvée, le fichier a bougé"
        # Deux valeurs distinctes attendues et pas plus : une pour le thème clair, une pour le
        # sombre. Une troisième veut dire qu'un bloc est resté en arrière.
        distinctes = sorted(set(valeurs))
        assert len(distinctes) == 2, (
            f"--{nom} porte {len(distinctes)} valeurs différentes : {distinctes}. "
            "Un bloc n'a pas suivi la correction.")


# Les fonds sur lesquels ces jetons posent réellement du texte, relevés dans style.css,
# dashboard.css et les gabarits. `--bar-bg` en porte (style.css : .hbar), `--spec-soft` aussi.
CLAIRS = {
    "bg-card":   "#FFFFFF",
    "bg-page":   "#F7FAFC",
    "bg-hover":  sur("#FFFFFF", "#0A0F28", 0.04),
    "bar-bg":    "#EDF1F6",
    "spec-soft": "#F1F0FE",
    "green-soft": "#ECFDF3",
    "red-soft":  "#FEF3F2",
    "amber-soft": "#FFFAEB",
}
SOMBRES = {
    "bg-page":   "#0C111D",
    "bg-card":   "#141B2A",
    "bg-hover":  sur("#141B2A", "#FFFFFF", 0.05),
    "bar-bg":    "#1C2331",
    "spec-soft": "#1C2542",
    "green-soft": "#0E2A1E",
    "red-soft":  "#2C1614",
    "amber-soft": "#2A2012",
}


def _palette(theme):
    """Les trois jetons de texte du thème demandé, lus dans la feuille servie."""
    css = io.open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    if theme == "sombre":
        bloc = css[css.index(':root[data-theme="dark"]'):]
    else:
        bloc = css[css.index(":root"):css.index("@media (prefers-color-scheme: dark)")]
    trouve = {}
    for nom, valeur in _jetons(bloc):
        if nom in ("text", "muted", "faint"):
            trouve.setdefault(nom, valeur.upper())
    assert set(trouve) == {"text", "muted", "faint"}, f"{theme} : jetons manquants — {trouve}"
    return trouve


@pytest.mark.parametrize("theme,fonds", [("clair", CLAIRS), ("sombre", SOMBRES)])
@pytest.mark.parametrize("jeton", ["text", "muted", "faint"])
def test_un_jeton_de_texte_passe_l_AA_sur_tous_ses_fonds(theme, fonds, jeton):
    couleur = _palette(theme)[jeton]
    pires = sorted((contraste(couleur, f), nom) for nom, f in fonds.items())
    r, ou = pires[0]
    assert r >= AA, (
        f"thème {theme} : --{jeton} ({couleur}) ne vaut que {r:.2f}:1 sur --{ou}, "
        f"il faut {AA}:1. Ce jeton habille du texte de 11 à 13 px.")


@pytest.mark.parametrize("theme", ["clair", "sombre"])
def test_les_trois_jetons_restent_trois_crans_distincts(theme):
    """
    ⚠️ CORRIGER `--faint` SEUL LE COLLAIT SUR `--muted` : 1,08:1 entre les deux, soit une seule
    couleur à l'œil, et un niveau de hiérarchie perdu sur toute l'application. Les deux ont
    bougé ensemble pour cette raison — ce test est ce qui empêche de les recoller.
    """
    p = _palette(theme)
    assert contraste(p["faint"], p["muted"]) >= 1.25, (
        f"thème {theme} : --faint {p['faint']} et --muted {p['muted']} ne se distinguent plus "
        f"({contraste(p['faint'], p['muted']):.2f}:1). Trois crans qui se lisent pareil n'en font qu'un.")
    assert contraste(p["muted"], p["text"]) >= 1.25, (
        f"thème {theme} : --muted et --text ne se distinguent plus")
