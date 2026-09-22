"""
UNE SEULE LANGUE PAR ÉCRAN.

⚠️ LE TABLEAU DE BORD EN PARLAIT DEUX. Mes sections neuves étaient en français — « La chaîne »,
« Où on en est », « Commandes » — au milieu de l'anglais d'origine : « Revenue by hour »,
« Product mix », « Best day », « Break-even reached ». Sur un même écran, deux langues ne
signalent pas deux origines : elles donnent l'impression que la page est à moitié finie, et on
cesse de faire confiance au reste.

⚠️ ET CE N'EST PAS UNE QUESTION DE GOÛT. « Costs (day) » et « Charges (jour) » désignent la
même chose ; lus côte à côte, ils font chercher la différence. Le doute coûte plus cher que la
traduction.

⚠️ « PRIME COST » RESTE, ET C'EST UN CHOIX. C'est le terme du métier — matière + personnel
rapportés au chiffre d'affaires — et le traduire en « coût primaire » le rendrait introuvable
dans toute la littérature de la restauration. Une exception assumée vaut mieux qu'une règle
appliquée contre son objet.
"""

import html as H
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Les termes admis en anglais, et pourquoi.
TOLERES = {
    "prime cost",   # terme du métier, intraduisible sans se rendre introuvable
    "cogs",         # idem — et c'est le nom de la page qui les édite
    "ebitda",       # terme comptable
    "sop",          # nom de la page
    "sms", "tva", "tpa", "mb way", "estushop", "estudantina", "vendus", "revolut", "mesa",
}

# Des mots qui n'existent qu'en anglais, et qu'aucun nom propre ne porte ici.
ANGLAIS = re.compile(
    r"\b(today|yesterday|revenue|costs?|gross|margin|break-even|open day|latest|best day|"
    r"products? sold|transactions?|this month|last week|average|ticket average|loading|"
    r"apply|cancel|save|custom|payment methods|product mix|sales evolution|patterns|"
    r"recent|items|payment|no movements|week|month|day)\b", re.I)


def _visible(nom):
    s = open(os.path.join(RACINE, "templates", nom), encoding="utf-8").read()
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"\{#.*?#\}", " ", s, flags=re.S)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S)
    s = re.sub(r"<style>.*?</style>", " ", s, flags=re.S)
    s = s[s.index('<div class="page">'):] if '<div class="page">' in s else s
    infobulles = " ".join(re.findall(r'data-tip="([^"]+)"', s))
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))) + " " + H.unescape(infobulles)


def _fautifs(texte):
    out = []
    for m in ANGLAIS.finditer(texte):
        mot = m.group(0).lower()
        contexte = texte[max(0, m.start() - 30):m.end() + 20].lower()
        if any(t in contexte for t in TOLERES):
            continue
        out.append(texte[max(0, m.start() - 25):m.end() + 15].strip())
    return out


def test_le_tableau_de_bord_ne_parle_que_francais():
    """⚠️ DEUX LANGUES SUR UN ÉCRAN donnent l'impression qu'il est à moitié fini."""
    fautifs = _fautifs(_visible("index.html"))
    assert not fautifs, fautifs[:8]


def test_les_infobulles_aussi():
    """Elles portent le texte le plus long de la page — et celui qu'on lit quand on doute."""
    s = open(os.path.join(RACINE, "templates", "index.html"), encoding="utf-8").read()
    for m in re.finditer(r'data-tip="([^"]+)"', s):
        t = H.unescape(m.group(1))
        assert not re.search(r"\b(the|and|of|is|are|with|which|from|that)\b", t), t[:70]


# Des mots qui n'existent qu'en anglais et qu'aucun identifiant du dépôt ne porte. Ils sont
# cherchés ENTOURÉS D'ESPACES, donc dans une phrase — jamais dans `open_days` ni `chargesSub`.
# ⚠️ AVEC DES LIMITES DE MOTS. Cherché en sous-chaîne nue, « rest » attrapait « reste » et
# « more » attraperait « amorce » : le test criait alors sur du français parfaitement correct.
# Des ÉTIQUETTES d'un seul mot. Séparées des mots de liaison parce qu'un mutant qui remettait
# « Gross margin » survivait : deux mots anglais côte à côte, et aucun n'était une conjonction.
#
# ⚠️ ON N'Y MET NI `today`, NI `custom`, NI `week`. Ce sont des CLÉS DE PÉRIODE envoyées au
# serveur (`?preset=today`), pas du texte affiché : les compter ferait échouer le test sur le
# mécanisme même des boutons.
ETIQUETTES = re.compile(
    r"\b(gross|margin|revenue|costs?|average|loading|apply|cancel|save|evolution|"
    r"methods|break-even|estimated|labour|basket|footfall)\b", re.I)

MOTS_ANGLAIS = re.compile(
    r"\b(of|the|and|with|from|applied|measured|sales|staff|fixed|open days|per day|rest|"
    r"each|than|were|yet|enough|busiest|darker|more|reached|short|seats?|seat|inside|"
    r"terrace|above|below|items?|latest)\b", re.I)


def test_le_script_du_tableau_de_bord_ne_pose_pas_danglais():
    """
    ⚠️ LA MOITIÉ DU TEXTE DE CETTE PAGE EST ÉCRITE PAR LE SCRIPT. Ne vérifier que le gabarit
    laisserait « Break-even reached » s'afficher sans qu'aucun test ne rougisse.

    ⚠️ ET ON CHERCHE DES PHRASES DANS LE FICHIER ENTIER, PAS DANS DES CHAÎNES DÉCOUPÉES. La
    version d'avant capturait le texte entre guillemets — et une chaîne HTML porte des
    guillemets INTERNES : `` `<span style="color:${c}">measured on ${n}% of sales</span>` ``
    était coupée en morceaux dont chacun passait le contrôle. Trois phrases anglaises sont
    restées affichées derrière ce test vert. Un découpage qui suit la syntaxe du code rate le
    texte ; un balayage du fichier, non.
    """
    js = open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()
    js = re.sub(r"//[^\n]*", "", js)
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    # ⚠️ UNE BALISE COMMENCE PAR UNE LETTRE OU UNE BARRE. `<[^>]*>` attrapait aussi un « < »
    # de comparaison — `if (a < b) … >` — et avalait tout le texte jusqu'au « > » suivant, y
    # compris les phrases anglaises qu'on cherche. Un mutant en a profité : le contrôle était
    # vert parce qu'il ne LISAIT PLUS la ligne fautive.
    js = re.sub(r"</?[a-zA-Z][^>]*>", " ", js)
    js = re.sub(r"\$\{[^}]*\}", " ", js)     # les interpolations sont du code
    # ⚠️ `for (const c of xs)` EST DU CODE : « of » y est un mot-clé JavaScript, pas un mot de
    # phrase. Le compter ferait échouer le test sur une boucle parfaitement saine — et un test
    # qui crie sur du correct finit désactivé.
    js = re.sub(r"\bfor\s*\([^)]*\)", " ", js)
    # ⚠️ LES OPTIONS DE FORMAT ET LES IDENTIFIANTS SONT DU CODE. `{ weekday: 'short', day:
    # 'numeric' }` et `const above = …` portent des mots anglais que personne ne lit. Un test
    # qui les compte crie sur du code sain, et un test qui crie sur du correct finit désactivé.
    # ⚠️ UN OBJET D'OPTIONS TIENT SUR UNE LIGNE ET NE CONTIENT QUE `clé: valeur`. Le motif
    # large `\{[^{}]*:[^{}]*\}` avalait n'importe quel bloc contenant un ternaire — donc des
    # pages entières de code, et les phrases anglaises avec. Un mutant en a profité : le test
    # était vert parce qu'il ne LISAIT PLUS la ligne fautive. Un filtre trop large ne fait pas
    # moins de bruit, il fait moins de travail.
    js = re.sub(r"\{\s*(?:\w+\s*:\s*'[^']*'\s*,?\s*)+\}", " ", js)
    js = re.sub(r"\b(const|let|var)\s+\w+", " ", js)              # déclarations
    # ⚠️ LES DEUX LISTES, PAS UNE. `MOTS_ANGLAIS` attrape les mots de liaison — donc les
    # phrases ; `ANGLAIS` attrape les étiquettes d'un seul mot. Un mutant qui remettait
    # « Gross margin » a survécu parce que le balayage du script n'utilisait que la première :
    # deux mots anglais côte à côte, et aucun n'était une conjonction.
    import itertools
    fautifs = []
    for m in itertools.chain(MOTS_ANGLAIS.finditer(js), ETIQUETTES.finditer(js)):
        # ⚠️ `ins-seat` ET `st.per_seat` SONT DES IDENTIFIANTS. `\b` s'ouvre après un tiret ou un
        # point : sans cette garde, le test accusait des noms d'éléments et d'attributs, jamais
        # lus par personne. Une phrase n'est ni précédée ni suivie d'un tiret, d'un point ou
        # d'un souligné.
        avant = js[m.start() - 1:m.start()]
        apres = js[m.end():m.end() + 1]
        # ⚠️ `t.items.map(item => …)` EST DU CODE. Un identifiant est collé à un point, une
        # parenthèse, un tiret ou un souligné ; une phrase affichée est entourée d'espaces ou
        # de ponctuation de lecture.
        if avant in "-_.(" or apres in "-_.(":
            continue
        # ⚠️ LES TERMES DU MÉTIER SONT ADMIS, ET LEUR LISTE EST UNIQUE. « Prime cost » contient
        # « cost » : le refuser au mot près obligerait à le réécrire, et la note qui explique
        # pourquoi il reste vivrait à deux endroits.
        entourage = js[max(0, m.start() - 12):m.end() + 12].lower()
        if any(t in entourage for t in TOLERES):
            continue
        extrait = js[max(0, m.start() - 35):m.end() + 25].strip().replace("\n", " ")
        if extrait not in fautifs:
            fautifs.append(extrait)
    assert not fautifs, fautifs[:6]


def test_les_dates_sont_formatees_en_francais():
    """
    ⚠️ `toLocaleDateString('en-GB')` REND « 24 Sept », PAS « 24 sept. ». C'est du texte affiché,
    produit par le navigateur : aucune chaîne du fichier ne le trahit, et la traduction la plus
    soignée laisse passer les dates — qui sont partout sur cette page.
    """
    js = open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()
    assert "'en-GB'" not in js and '"en-GB"' not in js, "des dates sont formatées en anglais"
    assert "'fr-FR'" in js


@pytest.mark.parametrize("terme", ["Prime cost", "COGS"])
def test_les_termes_du_metier_sont_conserves(terme):
    """
    ⚠️ UNE EXCEPTION ASSUMÉE VAUT MIEUX QU'UNE RÈGLE APPLIQUÉE CONTRE SON OBJET. « Coût
    primaire » rendrait la notion introuvable dans toute la littérature de la restauration.

    ⚠️ ET ON LE CHERCHE DANS LE GABARIT, PAS DANS LA SOMME DES DEUX FICHIERS. Un mutant qui
    traduisait l'étiquette de la page survivait parce que le terme subsistait dans un
    commentaire du script : chercher partout revient à ne chercher nulle part.
    """
    js = open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()
    # ⚠️ C'EST LE SCRIPT QUI ÉCRIT CETTE ÉTIQUETTE, pas le gabarit : celui-ci ne porte qu'un
    # remplissage écrasé au premier rendu. Chercher dans les deux, ou dans les commentaires,
    # revient à ne chercher nulle part — un mutant qui traduisait la ligne affichée survivait.
    pose = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", js, flags=re.S))
    pose = "\n".join(l for l in pose.split("\n") if "textContent" in l or "innerHTML" in l)
    assert terme.lower() in pose.lower(), f"{terme} n'est plus écrit à l'écran"
