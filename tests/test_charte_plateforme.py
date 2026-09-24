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
    """
    ⚠️ LES TROIS FORMES, DONT CELLE DES FEUILLES DE STYLE. Cinquième fois de cette refonte
    qu'un détecteur reconnaît sa propre explication : le commentaire qui dit pourquoi `#111` a
    été remplacé contient `#111`. Les `/* */` d'un bloc `<style>` échappaient au nettoyage — et
    un contrôle qui punit le fait de s'expliquer apprend à ne plus s'expliquer.
    """
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"\{#.*?#\}", " ", s, flags=re.S)
    return re.sub(r"/\*.*?\*/", " ", s, flags=re.S)


@pytest.mark.parametrize("nom", PAGES)
def test_aucune_couleur_en_dur(nom):
    """
    ⚠️ UNE COULEUR EN DUR NE CONNAÎT PAS LE MODE SOMBRE. `#2e7d32` sur fond noir passe du vert
    sourd au vert criard, et `#e8f5e9` reste un fond blanc cassé sur lequel plus rien ne se lit.
    La page s'affiche ; le texte a disparu.
    """
    s = _sans_commentaires(_lire(nom))
    s = _sans_apercu_client(s)
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
        # ⚠️ `theme-color` EST UNE EXCEPTION, et elle est éprouvée plus bas : la barre
        # système du téléphone la lit AVANT tout CSS.
        if "theme-color" in l:
            continue

        # ⚠️ LA FORME COURTE COMPTE AUSSI. Le motif ne connaissait que six chiffres : `#888`,
        # `#555`, `#777` passaient sans être vus — et ce sont justement les gris qu'on écrit à
        # la main sans y penser, ceux qui ne suivent aucun thème.
        #
        # ⚠️ DEUX EXCEPTIONS, TOUTES DEUX ÉPROUVÉES AILLEURS. `#fff` est légitime sur l'accent,
        # qui reste sombre dans les deux thèmes — et le cas dangereux, du blanc sur une couleur
        # qui s'inverse, a son propre contrôle. Et `#acf-price` est un SÉLECTEUR D'ID, pas une
        # couleur : sans le garde-fou, le détecteur trouvait treize couleurs à COGS dont aucune
        # n'en était une.
        for m in re.finditer(r"#[0-9a-fA-F]{3}(?![0-9a-fA-F_-])|#[0-9a-fA-F]{6}\b", l):
            if m.group(0).lower() in ("#fff",):
                continue
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


# ── Une classe posée doit exister quelque part ───────────────────────────────────────────────

def _classes_posees(nom):
    """Les classes écrites en dur dans le balisage — hors style et hors script.

    ⚠️ LES TROIS EXCLUSIONS COMPTENT. Un `<style>` DÉCLARE, il ne pose pas ; dans un
    `<script>`, `class="' + variante + '"` fait passer le nom de la variable pour une classe ;
    et un commentaire qui cite une classe ne la pose pas. Sans elles, le contrôle invente des
    manques et on apprend à ne plus le croire.
    """
    s = _lire(nom)
    s = re.sub(r"<style>.*?</style>", " ", s, flags=re.S)
    s = re.sub(r"<script[^>]*>.*?</script>", " ", s, flags=re.S)
    # ⚠️ ET LES COMMENTAIRES, QUI NE POSENT RIEN. C'est la troisième fois de cette refonte qu'un
    # détecteur reconnaît sa propre explication : celle qui dit pourquoi `<main class="wrap">` a
    # été retiré contient les mots `class="wrap"`. Un contrôle qui punit le fait de s'expliquer
    # apprend à ne plus s'expliquer.
    s = _sans_commentaires(s)
    out = set()
    for m in re.finditer(r'class="([^"<>{}]*)"', s):
        out |= {c for c in m.group(1).split() if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", c)}
    return out


def _sans_commentaires_css(css):
    return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)


def _classes_declarees(nom):
    """
    ⚠️ LES COMMENTAIRES CSS SONT RETIRÉS AVANT LA LECTURE, et c'est la même erreur que du côté
    du balisage, commise une quatrième fois. Le commentaire qui explique pourquoi `.muted` a dû
    être déclarée contient `.muted` : supprimer la règle laissait le contrôle vert, puisqu'il
    trouvait la classe dans le texte qui raconte son absence.
    """
    decl = set()
    for f in sorted(os.listdir(os.path.join(RACINE, "static"))):
        if f.endswith(".css"):
            chemin = os.path.join(RACINE, "static", f)
            decl |= set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)",
                                   _sans_commentaires_css(open(chemin, encoding="utf-8").read())))
    for bloc in re.findall(r"<style>(.*?)</style>", _lire(nom), re.S):
        decl |= set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", _sans_commentaires_css(bloc)))
    return decl


# ⚠️ CE QUI RESTE À FAIRE, MESURÉ ET NOMMÉ PLUTÔT QUE TU. Ces pages posent des classes qu'aucune
# règle ne déclare : elles s'affichent sans le style qu'on croyait leur donner, et rien ne le
# signale — c'est exactement le défaut trouvé sur `.muted`, employée douze fois pour rien. Elles
# ne sont pas encore passées à la charte ; la liste rétrécit, elle ne grandit pas.
DETTE = {
    "cogs.html": {'btn-add', 'comm-preset'},
}


@pytest.mark.parametrize("nom", PAGES)
def test_une_classe_posee_a_une_regle_quelque_part(nom):
    """
    ⚠️ UNE CLASSE ABSENTE NE CASSE RIEN : ELLE NE FAIT RIEN. `.muted` était posée douze fois,
    sur les phrases secondaires de Fidélité et du mode opératoire, et déclarée nulle part — elles
    s'affichaient toutes en encre pleine, au même poids que le texte principal. Aucune erreur,
    aucune console, rien à voir en relisant le gabarit : juste une hiérarchie qui n'existe pas.
    """
    orphelines = _classes_posees(nom) - _classes_declarees(nom) - DETTE.get(nom, set())
    assert not orphelines, sorted(orphelines)


def test_la_dette_de_classes_ne_grandit_pas():
    """⚠️ ET LA LISTE DOIT RESTER EXACTE. Une entrée qui ne correspond plus à rien laisse passer
    une vraie classe orpheline le jour où quelqu'un réutilise ce nom."""
    for nom, connues in DETTE.items():
        reelles = _classes_posees(nom) - _classes_declarees(nom)
        assert reelles == connues, f"{nom} : attendu {sorted(connues)}, trouvé {sorted(reelles)}"


# ── L'encre s'inverse, le blanc non ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("nom", PAGES)
def test_pas_de_blanc_pose_sur_une_couleur_qui_sinverse(nom):
    """
    ⚠️ TROUVÉ DEUX FOIS, SUR DEUX PAGES, AVANT D'ÊTRE GARDÉ ICI. `background: var(--text)` avec
    `color: #fff` est juste en clair et illisible en sombre : l'encre passe au blanc cassé, le
    texte reste blanc, et l'élément disparaît. Les deux fois, c'était le message de confirmation
    — celui qu'on ne regarde qu'une seconde, et dont on ne se dit pas qu'il a disparu.

    ⚠️ CE QUI EST PERMIS : `#fff` sur l'accent. L'iris reste sombre dans les deux thèmes, c'est
    pour ça que la charte pose du blanc dessus et sur rien d'autre.

    ⚠️ LA PAIRE QUI TIENT DES DEUX CÔTÉS est encre / fond-de-carte : les deux s'inversent
    ensemble, donc le contraste ne bouge pas.
    """
    s = _lire(nom)
    fautifs = []
    for bloc in re.findall(r"<style>(.*?)</style>", s, re.S):
        bloc = _sans_commentaires_css(bloc)
        # Une déclaration : du `background` jusqu'au `}` de sa règle.
        for regle in re.findall(r"\{[^{}]*\}", bloc):
            fond = re.search(r"background(?:-color)?:\s*var\((--[a-z-]+)\)", regle)
            encre = re.search(r"(?<!-)color:\s*(#fff\b|#ffffff\b|white\b)", regle)
            if fond and encre and fond.group(1) in ("--text", "--db-ink", "--db-ink-2"):
                fautifs.append(regle.strip()[:90])
            # ⚠️ `accent-color` PEINT LA COCHE D'UNE CASE, et c'est le même piège : posée sur
            # l'encre, elle s'inverse avec le thème — case blanche, coche blanche, on ne voit
            # plus ce qui est coché. Sur la page des dépenses, c'était le geste principal.
            acc = re.search(r"accent-color:\s*var\((--[a-z-]+)\)", regle)
            if acc and acc.group(1) in ("--text", "--db-ink", "--db-ink-2"):
                fautifs.append(regle.strip()[:90])
    assert not fautifs, fautifs


# ── Le balisage se referme ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nom", PAGES)
def test_les_conteneurs_se_referment(nom):
    """
    ⚠️ DEUX `<div>` N'ÉTAIENT JAMAIS FERMÉS DANS `charges.html`, et personne ne l'a vu parce que
    le navigateur répare. La cellule « Notes » des deux modales restait ouverte : le bloc de
    versionnement se retrouvait NESTÉ DEDANS au lieu d'être un élément de la grille, et le
    `</div>` censé fermer la grille fermait autre chose.

    ⚠️ CE GENRE DE DÉFAUT NE CASSE RIEN, IL DÉPLACE. La page s'affiche, presque juste, et le
    jour où une règle de grille change, un bloc part où personne ne l'attend — sans qu'aucune
    ligne récente n'explique pourquoi.
    """
    # ⚠️ UN PARTIEL EST UN FRAGMENT, PAS UN DOCUMENT. `_pied.html` referme ce que `_rail.html`
    # ouvre : les compter séparément reviendrait à exiger qu'un demi-mot soit un mot. Leur
    # équilibre À DEUX est vérifié juste en dessous.
    if nom.startswith("_"):
        pytest.skip("partiel — son équilibre se compte avec sa paire")
    s = _sans_commentaires(_lire(nom))
    # Les gabarits Jinja ouvrent des balises dans des branches : on ne compte que les pages
    # dont le balisage est inconditionnel.
    if re.search(r"\{%\s*(if|for)\b", s):
        pytest.skip("balisage conditionnel — l'équilibre ne se compte pas statiquement")
    for balise in ("div", "table", "tbody", "thead", "section", "details", "nav", "main"):
        ouvrants = len(re.findall(r"<" + balise + r"[\s>]", s))
        fermants = len(re.findall(r"</" + balise + r"\s*>", s))
        assert ouvrants == fermants, (
            f"{nom} : {ouvrants} <{balise}> pour {fermants} </{balise}>")


def test_la_coquille_souvre_et_se_referme():
    """
    ⚠️ `_rail.html` OUVRE LA COQUILLE, `_pied.html` LA REFERME. Deux partiels plutôt qu'un
    parce que le contenu de chaque page va au milieu. Rien ne garantit qu'ils restent d'accord :
    une balise ajoutée d'un côté laisse toutes les pages du produit mal fermées d'un coup, et
    le navigateur répare en silence.
    """
    ensemble = _sans_commentaires(_lire("_rail.html") + "\n" + _lire("_pied.html"))
    for balise in ("div", "nav", "aside", "main"):
        ouvrants = len(re.findall(r"<" + balise + r"[\s>]", ensemble))
        fermants = len(re.findall(r"</" + balise + r"\s*>", ensemble))
        assert ouvrants == fermants, f"{balise} : {ouvrants} ouverts, {fermants} fermés"


# ── Ce qui flotte au-dessus de la page ───────────────────────────────────────────────────────

def _racines(extra=""):
    """
    Les noms déclarés sur `:root` — donc résolus n'importe où dans le document.

    ⚠️ LES GABARITS EN DÉCLARENT AUSSI. `clientes.html` pose ses quatre teintes de cohorte dans
    son propre `<style>` : ne lire que `static/*.css` les faisait passer pour introuvables, et
    le contrôle criait au loup sur du code juste.
    """
    css = extra
    for f in sorted(os.listdir(os.path.join(RACINE, "static"))):
        if f.endswith(".css"):
            css += open(os.path.join(RACINE, "static", f), encoding="utf-8").read()
    css = _sans_commentaires_css(css)
    noms = set()
    for m in re.finditer(r":root[^{]*\{([^{}]*)\}", css):
        noms |= set(re.findall(r"(--[a-z0-9-]+)\s*:", m.group(1)))
    return noms


def _jetons_accessibles_partout():
    return _racines()


@pytest.mark.parametrize("nom", PAGES)
def test_une_surcouche_resout_ses_jetons(nom):
    """
    ⚠️ UNE MODALE SE POSE PAR-DESSUS LA PAGE, donc hors de `.page` dans le DOM. Un jeton scopé
    à `.page.db` n'y existe pas : `background: var(--db-card)` se résout dans le VIDE, la
    déclaration est ignorée, et la modale s'affiche transparente — on lit la page à travers son
    texte. Aucune erreur, aucune console, rien.

    ⚠️ C'EST ARRIVÉ SUR TOUTE LA PLATEFORME, et le tableau de bord le contournait en collant
    `class="db"` sur chacune de ses surcouches. Un contournement qu'il faut penser à répéter
    n'est pas une solution : c'est un piège qui attend la page suivante. Les jetons sont
    remontés sur `:root` ; ce contrôle garde la propriété qui compte — ce qui flotte au-dessus
    de la page doit pouvoir se peindre.
    """
    # ⚠️ ON REPÈRE LA FERMETURE AVANT DE NETTOYER. Le marqueur EST un commentaire HTML
    # (`</div><!-- /page -->`) : nettoyer d'abord l'efface, et le contrôle se met à sauter les
    # dix-neuf pages en annonçant « rien à vérifier ». Un test qui skippe tout est plus
    # dangereux qu'un test absent — il occupe la place.
    brut = _lire(nom)
    i = brut.find("<!-- /page -->")
    if i == -1:
        pytest.skip("pas de fermeture de page repérable")
    partout = _jetons_accessibles_partout()
    employes = set(re.findall(r"var\((--[a-z0-9-]+)\)", _sans_commentaires(brut[i:])))
    hors_portee = sorted(employes - partout)
    assert not hors_portee, (
        f"{nom} : {hors_portee} employés au-dessus de la page mais déclarés plus bas")


@pytest.mark.parametrize("nom", PAGES)
def test_chaque_var_nomme_un_jeton_qui_existe(nom):
    """
    ⚠️ UN `var()` QUI NE TROUVE RIEN NE LÈVE PAS : la déclaration entière est ignorée, en
    silence. `background: var(--db-card)` sur une modale hors de portée donne une modale
    TRANSPARENTE — on lit la page à travers son texte, et aucune console ne dit pourquoi.

    ⚠️ C'EST LE MODE DE PANNE LE PLUS DISCRET DE CETTE CHARTE, et il s'est produit sur toute la
    plateforme : les jetons vivaient sous `.db`, les surcouches vivent hors de `.page`. Ce
    contrôle est plus large que le défaut — il exige que TOUT `var()` nomme quelque chose qui
    existe, sans se demander où l'élément se trouve dans le DOM.

    ⚠️ `var(--x, valeur)` EST PERMIS : la solution de repli EST la déclaration manquante, dite
    à l'endroit où elle sert.
    """
    brut = _lire(nom)
    src = _sans_commentaires(brut)
    locaux = set(re.findall(r"(--[a-z0-9-]+)\s*:", src))
    racines = _racines(extra="\n".join(re.findall(r"<style>(.*?)</style>", brut, re.S)))
    # Sans solution de repli : `var(--x)` et non `var(--x, …)`.
    employes = set(re.findall(r"var\(\s*(--[a-z0-9-]+)\s*\)", src))
    orphelins = sorted(employes - racines - locaux)
    assert not orphelins, f"{nom} : {orphelins} — la règle qui les emploie sera ignorée"


def test_une_categorie_nemprunte_ni_au_vert_ni_au_rouge():
    """
    ⚠️ UNE CATÉGORIE PEINTE COMME UN ÉTAT SE LIT COMME UN JUGEMENT. « Courses » était verte
    parmi six teintes catégorielles, et rien ne rend les courses plus vertueuses qu'un loyer.
    Sur la page des coûts, le CDI était vert et le temps partiel ambre : un temps partiel n'est
    pas un avertissement.

    ⚠️ L'ÉCHELLE CATÉGORIELLE EXISTE EXACTEMENT POUR ÇA. Elle n'emprunte ni au vert ni au rouge
    précisément pour qu'une nature ne se lise pas comme un verdict.
    """
    fautives = []
    for nom in PAGES:
        for bloc in re.findall(r"<style>(.*?)</style>", _lire(nom), re.S):
            bloc = _sans_commentaires_css(bloc)
            for m in re.finditer(r"\.badge-([a-z]+)\s*\{([^}]*)\}", bloc):
                famille, regle = m.group(1), m.group(2)
                # ⚠️ LA FRÉQUENCE GARDE SON AMBRE, ET C'EST JUSTE : « annuel » dit que le
                # montant affiché à côté est DÉRIVÉ. C'est une réserve sur un chiffre, pas une
                # catégorie — la seule famille qui a le droit d'emprunter à un état.
                if famille in ("annual", "quarterly", "monthly"):
                    continue
                if re.search(r"var\(--(db-)?(green|red)(-soft)?\)", regle):
                    fautives.append(f"{nom} .badge-{famille}")
    assert not fautives, fautives


# ── La page de connexion ─────────────────────────────────────────────────────────────────────

def _page_login():
    """Le HTML de la page de connexion, telle qu'`app.py` la compose."""
    src = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    i = src.index("def _page_login(")
    return src[i:src.index('\n@app.route("/logout")', i)]


def test_la_page_de_connexion_suit_la_charte():
    """
    ⚠️ ELLE ÉTAIT RESTÉE AU BEIGE D'AVANT, et c'est le premier écran que qui que ce soit voit.
    Aucun contrôle ne la regardait : elle n'est pas dans `templates/`, c'est une chaîne dans
    `app.py`. Un balayage qui ne lit qu'un dossier rate ce qui vit ailleurs.

    ⚠️ ET ELLE EST AUTONOME, DONC ELLE RECOPIE. Elle s'affiche avant toute session ; une feuille
    externe qui tarderait la montrerait nue. Ses littéraux doivent donc être ceux de la charte,
    et c'est ce qui est vérifié — comme pour /tpa.
    """
    page = _page_login()
    css = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    i = css.index(":root {")
    pal = dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", css[i:css.index("\n}", i)]))
    for local, jeton in (("--canvas", "--bg-page"), ("--ink", "--text"), ("--muted", "--muted"),
                         ("--faint", "--faint"), ("--spec", "--accent"), ("--border", "--border")):
        m = re.search(re.escape(local) + r":\s*(#[0-9A-Fa-f]{6})", page)
        assert m, f"{local} n'est plus déclaré sur la page de connexion"
        assert m.group(1).upper() == pal[jeton].upper(), (
            f"{local} = {m.group(1)} mais la charte dit {jeton} = {pal[jeton]}")
    m = re.search(r'theme-color" content="(#[0-9A-Fa-f]{6})"', page)
    assert m and m.group(1).upper() == pal["--bg-page"].upper(), "la barre système a dérivé"


def test_le_mot_de_passe_est_le_premier_champ():
    """
    ⚠️ L'ADRESSE ÉTAIT EN TÊTE, AVEC LE FOCUS, et présentée comme facultative. On la remplissait
    par réflexe — et un e-mail sans compte fait échouer la connexion AVANT même de regarder le
    mot de passe partagé, qui aurait marché. Un champ facultatif présenté en premier n'est pas
    facultatif.
    """
    page = _page_login()
    assert page.index('name="password"') < page.index('name="email"'), (
        "l'adresse repasse devant le mot de passe")
    assert 'name="password"' in page and "autofocus" in page
    bloc = page[page.index('name="password"'):page.index('name="email"')]
    assert "autofocus" in bloc, "le focus n'est pas sur le mot de passe"
    # ⚠️ LES COMPTES NOMINATIFS RESTENT : ils portent le nom dans les actions journalisées.
    assert 'name="email"' in page, "les comptes nominatifs ont disparu"


# ── L'APERÇU DE LA VIGNETTE CLIENT ──────────────────────────────────────────────────────────


def _sans_apercu_client(src):
    """
    Retire le bloc `.apercu { … }` avant de chercher des couleurs en dur.

    ⚠️ CE N'EST PAS UN ASSOUPLISSEMENT DE LA RÈGLE, C'EST LA RÈGLE APPLIQUÉE À L'ENVERS. Cet encart
    montre ce que verra un client sur `pontos.estudantina.com` — un autre site, une autre charte, un
    seul thème. Le peindre avec les jetons du tableau de bord, qui s'inversent en mode sombre, en
    ferait une jolie boîte qui ne ressemble à rien de ce qui est publié : l'aperçu mentirait, ce qui
    est pire qu'une absence d'aperçu.

    ⚠️ ET L'EXCEPTION PORTE SUR LE BLOC, PAS SUR LA LIGNE. Le premier jet sautait les lignes
    contenant « apercu » — or `background: #6e2e33;` est sur SA propre ligne, qui ne contient pas ce
    mot. Une exception qui ne couvre pas ce qu'elle prétend couvrir est le pire des deux mondes : le
    test rougit quand même, et on finit par élargir l'exception au lieu de la corriger.

    ⚠️ ELLE EST ÉTROITE EXPRÈS : le seul bloc `.apercu {`, pas ses voisins. Et
    `test_l_apercu_client_copie_la_charte_du_site` tient ce bloc contre la palette du site client.
    """
    i = src.find(".apercu {")
    if i == -1:
        return src
    j = src.find("}", i)
    return src[:i] + src[j + 1:] if j != -1 else src


def test_l_apercu_client_copie_la_charte_du_site():
    """
    ⚠️ IL ÉCHAPPE À LA RÈGLE DES JETONS, DONC IL DOIT ÊTRE TENU AUTREMENT. Ses couleurs sont
    littérales parce qu'elles appartiennent à un AUTRE site — celui des clients. Sans ce contrôle,
    l'exception deviendrait une porte ouverte à n'importe quelle couleur écrite à la main dans ce
    fichier, du moment qu'elle se trouve sur une ligne contenant « apercu ».

    Les trois valeurs viennent de `apps/pontos/app/globals.css` : `--bordeaux`, `--papier`. Le jour
    où la charte du café change, cet aperçu doit changer avec elle — et c'est ce test qui le dira.
    """
    src = _lire("events.html")
    i = src.index(".apercu {")
    regle = src[i:src.index("}", i)]
    assert "#6e2e33" in regle, "le bordeaux du site a changé ou disparu de l'aperçu"
    assert "#fdfcf8" in regle, "le papier crème du site a changé ou disparu de l'aperçu"
    # ⚠️ AUCUN JETON DU TABLEAU DE BORD ICI : ils s'inversent en mode sombre, l'aperçu non.
    assert "var(--bg-card)" not in regle and "var(--text)" not in regle


def test_l_apercu_dit_ce_qui_ne_s_affichera_pas():
    """
    ⚠️ C'EST LA MOITIÉ DE SON INTÉRÊT. Trois règles décident de ce que le client voit, et aucune
    n'était écrite nulle part : sans description la vignette ne s'OUVRE pas, un événement annulé est
    masqué même s'il est actif, et seuls les sept prochains jours sont montrés — deux au plus. On
    les a découvertes en les rencontrant, une par une, en production.
    """
    src = _lire("events.html")
    for phrase in ("ne s\\'ouvre pas", "Masqué aux clients", "jamais affiché aux clients",
                   "Deux vignettes au plus"):
        assert phrase in src, f"l'aperçu ne dit plus : {phrase}"


def test_le_jour_de_semaine_de_l_apercu_est_en_utc():
    """
    ⚠️ MÊME RÈGLE QUE SUR LA PAGE CLIENT, ET ELLE DOIT RESTER LA MÊME. `new Date("2026-10-02")` est
    minuit UTC : le lire en heure locale le ramène à la veille pour tout fuseau à l'ouest. Un aperçu
    qui annonce « vendredi » quand la page client dira « samedi » est pire qu'aucun aperçu.
    """
    src = _lire("events.html")
    i = src.index("function quandFr")
    corps = src[i:src.index("\n}", i)]
    assert "T12:00:00Z" in corps and "getUTCDay()" in corps
    assert ".getDay()" not in corps


def test_l_apercu_suit_chaque_champ_qu_il_montre():
    """
    ⚠️ UN APERÇU QUI NE BOUGE QU'À L'OUVERTURE EST PIRE QU'AUCUN APERÇU : il affirme quelque chose
    de faux pendant qu'on tape, et c'est justement au moment où l'on tape qu'on le regarde.

    ⚠️ ET `oninput` EN PROPRIÉTÉ, PAS `addEventListener`. Le formulaire est réinitialisé à chaque
    ouverture de la fenêtre : un écouteur ajouté s'empilerait, et l'aperçu se recalculerait cinq
    fois par frappe au cinquième événement ouvert.
    """
    src = _lire("events.html")
    assert "$(id).oninput = majApercu;" in src, "l'aperçu ne suit plus les frappes"
    for champ in ("m-title", "m-date", "m-start", "m-loc", "m-desc", "m-link"):
        assert f"'{champ}'" in src, f"{champ} ne déclenche plus l'aperçu"
    # Le statut et la visibilité changent ce que l'aperçu ANNONCE, pas seulement son contenu.
    assert "$('m-status').onchange = majApercu;" in src
    assert "$('m-oncard').onchange = majApercu;" in src


def test_le_chevron_de_l_apercu_ne_promet_rien_de_faux():
    """
    ⚠️ C'EST LA RÈGLE EXACTE DE LA PAGE CLIENT. Sans description, sans photo et sans lien, la
    vignette est INERTE : promettre « en savoir plus » pour ne rien apprendre de plus est la façon
    la plus rapide de faire cesser d'y toucher. L'aperçu doit donc être inerte lui aussi — sinon il
    affirme le contraire de ce que le client verra, ce qui est le seul défaut qu'un aperçu ne peut
    pas se permettre.
    """
    src = _lire("events.html")
    i = src.index("function majApercu")
    corps = src[i:src.index("\n}", i)]
    assert "const ouvrable = cliquable && Boolean(desc || img || lien)" in corps, (
        "le chevron de l'aperçu ne suit plus la règle d'ouverture de la page client"
    )
    # ⚠️ L'INTERRUPTEUR COUPE, IL N'AUTORISE PAS : `cliquable` seul ne suffit jamais à ouvrir une
    # vignette qui n'a rien à montrer, et une popup qui répète la carte est ce qu'on a écarté.
    assert "$('m-openable').checked" in src, "l'aperçu ignore l'interrupteur"
    assert "ouvrable ?" in corps, "le chevron s'affiche sans condition"


def _row(data, status="planned"):
    """⚠️ IMPORTÉ ICI ET NON EN TÊTE DE FICHIER : ce module de tests éprouve des GABARITS, il ne
    chargeait pas l'application. Un import global la ferait démarrer pour vérifier du CSS."""
    import app

    return app._build_event_row(data, status)


def test_l_interrupteur_d_ouverture_n_est_pas_invente_a_la_mise_a_jour():
    """⚠️ MÊME GARDE QUE `show_on_card` : décoché une fois, il ne doit pas réapparaître à la
    prochaine correction d'horaire — sinon une vignette qu'on a voulue inerte redevient cliquable
    sans que personne ne l'apprenne."""
    row = _row({"id": "e1", "title": "x", "date": "2026-10-03"})
    assert "openable" not in row


def test_un_evenement_cree_est_cliquable_par_defaut():
    """`True` à la création : ne rien changer à ce qui marche."""
    row = _row({"title": "x", "date": "2026-10-03"})
    assert row["openable"] is True


def test_l_apercu_dit_quand_la_vignette_n_est_pas_cliquable():
    """Sinon on décoche, l'aperçu montre un chevron en moins, et rien n'explique pourquoi."""
    s = _lire("events.html")
    assert "Vignette non cliquable" in s
