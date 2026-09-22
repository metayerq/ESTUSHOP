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


def test_les_couleurs_en_dur_qui_restent_suivent_la_charte():
    """
    ⚠️ UNE EXEMPTION MUETTE DEVIENT UNE PORTE. Deux couleurs ne peuvent pas être des jetons ;
    plutôt que de les exclure sans rien dire, on vérifie qu'elles valent exactement ce que la
    charte déclare — recopiées à la main, elles se périmeraient sans bruit, et le graphique
    garderait l'ancienne palette le temps d'un clignement, puis à chaque échec de lecture.
    """
    css = _lire("static/dashboard.css")
    clair = css[css.index(':root[data-theme="light"] .db {'):]
    clair = clair[:clair.index("}")]
    attendu = {k: v.upper() for k, v in
               re.findall(r"(--db-[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{6})", clair)}

    js = _lire("static/dashboard.js")
    i = js.index("function jetons(")
    bloc = js[i:js.index("\n}", i)]
    replis = re.findall(r"v\('(--db-[a-z-]+)'\)\s*\|\|\s*'(#[0-9A-Fa-f]{6})'", bloc)
    assert replis, "les replis ont disparu — les graphiques se dessineraient en transparent"
    for jeton, valeur in replis:
        assert jeton in attendu, f"{jeton} n'est pas déclaré dans la charte"
        assert valeur.upper() == attendu[jeton], \
            f"{jeton} : repli {valeur}, charte {attendu[jeton]}"

    html = _lire("templates/index.html")
    m = re.search(r'name="theme-color" content="(#[0-9A-Fa-f]{6})"', html)
    assert m and m.group(1).upper() == attendu["--db-bg"], \
        f"theme-color {m and m.group(1)} ≠ --db-bg {attendu.get('--db-bg')}"


def test_la_charte_declare_bien_les_jetons_quon_emploie():
    """
    ⚠️ UN JETON ABSENT DE LA FEUILLE REND UNE CHAÎNE VIDE, PAS UNE ERREUR. `var(--db-turquoise)`
    ne casse rien : la propriété est simplement ignorée, et l'élément hérite d'une couleur qui
    n'a pas été choisie.
    """
    css = _lire("static/dashboard.css")
    declares = set(re.findall(r"(--db-[a-z0-9-]+)\s*:", css))
    employes = set()
    for rel in ("templates/index.html", "static/dashboard.js", "static/dashboard.css"):
        for _, l in _lignes(rel):
            employes |= set(re.findall(r"var\((--db-[a-z0-9-]+)", l))
    inconnus = sorted(employes - declares)
    assert not inconnus, inconnus


def test_aucun_jeton_declare_ne_reste_inemploye():
    """
    ⚠️ UN JETON MORT SE LIT COMME UNE COULEUR DISPONIBLE. Le prochain qui cherche un gris en
    trouve quatre, dont un que personne n'utilise, et le choisit — c'est ainsi qu'une palette
    de six couleurs en compte onze.
    """
    css = _lire("static/dashboard.css")
    declares = set(re.findall(r"(--db-[a-z0-9-]+)\s*:", css))
    employes = set()
    for rel in SOUS_CHARTE:
        for _, l in _lignes(rel):
            employes |= set(re.findall(r"var\((--db-[a-z0-9-]+)", l))
    morts = sorted(declares - employes)
    assert not morts, morts


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


def test_chaque_jeton_est_declare_dans_les_trois_themes():
    """
    ⚠️ UN JETON DÉCLARÉ EN CLAIR SEULEMENT RESTE CLAIR EN SOMBRE. C'est pire qu'une couleur en
    dur : celle-ci se voit à la relecture, tandis qu'un jeton a l'air correct partout.
    """
    css = _lire("static/dashboard.css")
    def bloc(sel):
        i = css.index(sel) + len(sel)
        return set(re.findall(r"(--db-[a-z0-9-]+)\s*:", css[i:css.index("}", i)]))
    # ⚠️ LES RAYONS ET LES OMBRES N'ONT PAS DE VARIANTE CLAIRE OU SOMBRE — un `8px` vaut 8px
    # dans les deux. Seules les COULEURS doivent être redéclarées ; les exiger toutes ferait
    # échouer ce test sur des jetons qui n'ont aucune raison de changer.
    base = {j for j in bloc(".db {") if not j.startswith(("--db-r", "--db-sh"))}
    for sel in (':root[data-theme="dark"] .db {', ':root[data-theme="light"] .db {'):
        couleurs = {j for j in bloc(sel) if not j.startswith(("--db-r", "--db-sh"))}
        manquants = sorted(base - couleurs)
        assert not manquants, f"{sel} ne déclare pas {manquants}"
        # ⚠️ ET DANS L'AUTRE SENS. Un jeton qui ne vit QUE dans les surcharges est absent du
        # cas par défaut — celui où ni `data-theme` ni la préférence système ne s'appliquent.
        # Le contrôle à sens unique laissait passer exactement ça.
        orphelins = sorted(couleurs - base)
        assert not orphelins, f"{sel} déclare {orphelins}, absents de la base"
