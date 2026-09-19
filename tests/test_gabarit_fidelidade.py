"""
CE QUE LE GABARIT PROMET À L'ÉCRAN — et que Python ne voit jamais.

⚠️ AUCUN TEST DE CE DÉPÔT NE MET EN PAGE QUOI QUE CE SOIT. Il n'y a pas de navigateur ici : une
règle CSS qui en annule une autre passe toutes les suites au vert et ne se découvre qu'en
ouvrant la page. C'est arrivé le 19/09/2026 — le panneau de fiche client restait affiché en
permanence, une bande blanche collée à droite par-dessus le tableau. Le JavaScript le masquait
correctement ; le CSS l'ignorait.

On ne peut pas tester le rendu. On peut tester la CONTRADICTION.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GABARIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "templates", "fidelidade.html")

with open(GABARIT, encoding="utf-8") as f:
    SOURCE = f.read()


def test_un_element_hidden_n_est_pas_rouvert_par_son_display():
    """
    ⚠️ LE PIÈGE EXACT, ET IL NE PRÉVIENT PAS. Le navigateur cache un élément portant `hidden`
    grâce à un `display:none` de sa feuille PAR DÉFAUT. Or n'importe quelle règle d'auteur passe
    devant celle-là, quelle que soit sa spécificité : il suffit d'écrire `display:flex` sur la
    classe de l'élément pour que `hidden` cesse de vouloir dire quoi que ce soit.

    Rien ne casse, rien n'avertit. L'élément est simplement toujours là.
    """
    fautifs = []
    for balise in re.findall(r"<[a-z]+[^>]*\bhidden\b[^>]*>", SOURCE):
        classes = re.search(r'class="([^"]+)"', balise)
        if not classes:
            continue
        for cls in classes.group(1).split():
            # La classe déclare-t-elle un `display` qui n'est pas `none` ?
            regles = re.findall(rf"^\.{re.escape(cls)}\s*\{{([^}}]*)\}}", SOURCE, re.M)
            declare = [d for r in regles for d in re.findall(r"display\s*:\s*([a-z-]+)", r)
                       if d != "none"]
            if not declare:
                continue
            # Alors il FAUT une règle qui le referme quand `hidden` est posé.
            referme = re.search(
                rf"\.{re.escape(cls)}\[hidden\]\s*\{{[^}}]*display\s*:\s*none", SOURCE)
            if not referme:
                fautifs.append(f".{cls} (display:{declare[0]}) sans `.{cls}[hidden]{{display:none}}`")

    assert not fautifs, (
        "des éléments `hidden` restent affichés à cause de leur propre CSS : "
        + " · ".join(fautifs)
    )


def test_le_panneau_de_fiche_est_bien_ferme_au_chargement():
    """L'attribut doit être dans le HTML servi, pas posé par le JavaScript après coup : sinon la
    bande blanche clignote à chaque chargement, avant que le script ne tourne."""
    panneau = re.search(r'<div id="fiche-fond"[^>]*>', SOURCE)
    assert panneau, "le panneau de fiche a changé de forme"
    assert "hidden" in panneau.group(0)


def test_ce_que_le_script_ouvre_il_sait_le_refermer():
    """
    Une boîte qui s'ouvre sans se fermer bloque l'écran derrière elle. On exige les deux gestes
    ET une sortie au clavier — un écran tactile de comptoir n'a pas toujours de souris.
    """
    assert "hidden = false" in SOURCE
    assert "hidden = true" in SOURCE
    assert "Escape" in SOURCE


def test_aucun_marqueur_de_conflit_ne_traine_dans_le_gabarit():
    """Un `<<<<<<<` dans un gabarit s'affiche tel quel au client : le rendu ne le rejette pas."""
    for marqueur in ("<<<<<<<", ">>>>>>>", "\n=======\n"):
        assert marqueur not in SOURCE
