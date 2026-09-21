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


def test_le_script_du_tableau_de_bord_ne_pose_pas_danglais():
    """
    ⚠️ LA MOITIÉ DU TEXTE DE CETTE PAGE EST ÉCRITE PAR LE SCRIPT. Ne vérifier que le gabarit
    laisserait « Break-even reached » et « Best day » s'afficher sans qu'aucun test ne rougisse.
    """
    js = open(os.path.join(RACINE, "static", "dashboard.js"), encoding="utf-8").read()
    js = re.sub(r"//[^\n]*", "", js)
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    chaines = [m.group(1) for m in re.finditer(r"['\"`]([^'\"`\n]{4,120})['\"`]", js)]

    def phrase_affichee(c):
        """
        ⚠️ MON FILTRE S'EMPILAIT EN CAS PARTICULIERS — URL, options de format, opérateurs — et
        chaque exception en cachait une autre : écarter toute chaîne contenant « ? » laissait
        passer « Break-even reached${x ? », le point d'interrogation d'un ternaire. Une seule
        règle vaut mieux qu'une liste qui grandit.

        ⚠️ CE QUI EST CAPTURÉ ENTRE DEUX LITTÉRAUX N'EST PAS DU TEXTE. `'a' + d.week[i] + 'b'`
        fait ressortir le code du milieu. Une phrase affichée n'a ni « ; », ni « = », ni accès
        indexé — et elle porte au moins deux mots de lettres séparés par une espace.
        """
        c = re.sub(r"\$\{.*$", " ", re.sub(r"\$\{[^}]*\}", " ", c))   # interpolations, ouvertes ou non
        c = re.sub(r"<[^>]*>", " ", c)                                   # balises
        if re.search(r"[;=\[\]]|\.\w+\(|\bstyle\b", c):
            return None
        # ⚠️ UN IDENTIFIANT N'EST PAS UNE PHRASE. « custom-range-bar » porte deux mots, mais
        # aucune espace : c'est un `id`, jamais lu par personne. La séparation par espace est
        # ce qui distingue une phrase d'un nom.
        if len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", c)) < 2 or " " not in c.strip():
            return None
        return c

    fautifs = []
    for c in chaines:
        t = phrase_affichee(H.unescape(c))
        if t:
            fautifs += _fautifs(t)
    assert not fautifs, fautifs[:8]


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
