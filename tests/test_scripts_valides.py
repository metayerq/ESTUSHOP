"""
LE JAVASCRIPT DES GABARITS DOIT AU MOINS SE PARSER.

⚠️ CE FICHIER EXISTE PARCE QU'UN COMMENTAIRE A FAILLI ÉTEINDRE UNE PAGE ENTIÈRE. En expliquant
un piège, j'ai cité une séquence de fermeture de commentaire À L'INTÉRIEUR d'un commentaire : le
bloc s'est refermé en avance, et tout le script de `/cogs` est devenu du JavaScript invalide.
Rien ne l'aurait dit — le gabarit rend, la page s'affiche, et pas une ligne de script ne tourne.
Les tests existants lisent le source avec des expressions régulières ; aucun ne demande jamais
« est-ce que ça se parse ? ».

⚠️ ET C'EST LA SEULE QUESTION QUI NE SE DEVINE PAS. Un détecteur maison peut se tromper sur un
gabarit de chaîne imbriqué ; un analyseur JavaScript, non. On délègue donc à `node --check`.

⚠️ LES GABARITS QUI MÊLENT JINJA AU SCRIPT SONT ÉCARTÉS, ET C'EST DIT. `{{ … }}` dans du
JavaScript n'est pas du JavaScript : le contrôle n'a rien à y dire tant que la valeur n'est pas
rendue. Le nombre de fichiers écartés est affiché, pour qu'une exception ne devienne pas la règle
sans que personne ne le remarque.
"""
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "templates")

SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
JINJA = re.compile(r"\{\{|\{%|\{#")

GABARITS = sorted(f for f in os.listdir(DOSSIER) if f.endswith(".html"))


def _script(nom):
    with open(os.path.join(DOSSIER, nom), encoding="utf-8") as f:
        return "\n".join(SCRIPT.findall(f.read()))


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent de cet environnement")
@pytest.mark.parametrize("nom", GABARITS)
def test_le_script_de_chaque_gabarit_se_parse(nom, tmp_path):
    src = _script(nom)
    if not src.strip():
        pytest.skip("aucun script en ligne")
    if JINJA.search(src):
        pytest.skip("script mêlé de Jinja — non analysable tel quel")

    chemin = tmp_path / "bloc.js"
    chemin.write_text(src, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(chemin)],
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        f"{nom} : le JavaScript en ligne ne se parse pas — la page rendra sans qu'une seule "
        f"ligne de script ne tourne.\n{r.stderr.strip()[:600]}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# LE HTML PRODUIT À L'EXÉCUTION — que `node --check` ne peut pas voir.
# ══════════════════════════════════════════════════════════════════════════════════════════

COMMENTAIRES = (
    re.compile(r"<!--[\s\S]*?-->"),
    re.compile(r"\{#[\s\S]*?#\}"),
    re.compile(r"/\*[\s\S]*?\*/"),
)

# Un gestionnaire en ligne : `onclick="…"`, `onchange="…"`, délimité par des guillemets doubles.
GESTIONNAIRE = re.compile(r'\bon[a-z]+\s*=\s*"([^"]*)"')


def _sans_prose(html):
    """
    ⚠️ ON RETIRE LES COMMENTAIRES AVANT DE LIRE. C'est la troisième fois de la soirée qu'un
    contrôle reconnaît sa propre explication : le commentaire qui décrit la panne CITE le motif
    fautif, c'est sa raison d'être. Un garde-fou qui ne fait pas la différence entre du code et
    de la prose crie sur les fichiers les mieux documentés.
    """
    for motif in COMMENTAIRES:
        html = motif.sub(" ", html)
    return html


@pytest.mark.parametrize("nom", GABARITS)
def test_aucun_gestionnaire_en_ligne_ne_serialise_en_json(nom):
    """
    ⚠️ `JSON.stringify` DANS UN ATTRIBUT EST TOUJOURS CASSÉ, SANS EXCEPTION. Il rend des
    guillemets DOUBLES ; l'attribut est délimité par des guillemets doubles. L'attribut se ferme
    donc au premier, le gestionnaire devient une expression tronquée, et le navigateur l'ignore
    EN SILENCE.

    ⚠️ VU EN PRODUCTION SUR LA PAGE D'INVENTAIRE : `onclick="basculer(${JSON.stringify(zone)})"`
    rendait `onclick="basculer("`. Les catégories ne s'ouvraient pas, les champs de quantité
    — câblés pareil — n'enregistraient rien. La page n'a jamais fonctionné, et rien ne pouvait
    le dire : le JavaScript du FICHIER se parse parfaitement ; c'est le HTML produit à
    l'exécution qui est cassé. `node --check` ne regarde pas là.

    ⚠️ LA PARADE N'EST PAS DE MIEUX ÉCHAPPER, C'EST DE NE PLUS CONCATÉNER DE CODE. La donnée
    voyage en `data-*` et un écouteur posé sur le conteneur la relit.

    ⚠️ CE CONTRÔLE NE COUVRE QUE LE CAS TOUJOURS FATAL. Une quarantaine de gestionnaires
    interpolent encore une chaîne entre apostrophes (`onclick="f('${x}')"`) : ceux-là cassent
    seulement si la valeur contient une apostrophe. C'est une dette réelle, pas une panne
    certaine — elle se solde en migrant vers `data-*`, pas en durcissant ce test aujourd'hui.
    """
    with open(os.path.join(DOSSIER, nom), encoding="utf-8") as f:
        html = _sans_prose(f.read())

    fautifs = [g for g in GESTIONNAIRE.findall(html) if "JSON.stringify" in g]
    assert not fautifs, (
        f"{nom} : {len(fautifs)} gestionnaire(s) en ligne sérialisent en JSON dans un attribut "
        f"— l'attribut se fermera au premier guillemet et le geste sera ignoré en silence.\n  "
        + "\n  ".join(g[:110] for g in fautifs)
    )
