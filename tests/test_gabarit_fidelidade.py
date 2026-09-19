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


def test_un_champ_desactive_dit_pourquoi_et_ou_le_reparer():
    """
    ⚠️ UN CHAMP GRIS SANS EXPLICATION EST UN BOGUE, MÊME QUAND LE CODE A RAISON. Les réglages
    se désactivent tant que la table `card_settings` n'existe pas — c'est correct, écrire
    échouerait. Mais la première version disait pourquoi en petit, en gris, tout en bas du
    panneau : Quentin a simplement constaté qu'il ne pouvait « ni cliquer ni saisir ». Il avait
    raison, et l'écran ne l'aidait pas.

    Ce test exige que toute désactivation soit accompagnée, dans la même branche, d'un message
    VISIBLE et du geste qui la répare.
    """
    debut = SOURCE.index("if (st.missing) {")
    branche = SOURCE[debut:SOURCE.index("\n    }", debut)]

    assert "disabled = true" in branche, "la branche ne désactive plus rien — relire le gabarit"
    assert "r-manque" in branche, "la désactivation n'affiche aucun message visible"
    assert "style.display = 'block'" in branche, "le message reste caché"
    # Le geste exact, pas une plainte : où aller, quoi coller.
    for indice in ("Supabase", "SQL Editor", "card_settings.sql", "recharge"):
        assert indice in branche, f"le message n'explique pas « {indice} »"
    # Et l'élément qui le porte existe vraiment dans la page.
    assert 'id="r-manque"' in SOURCE


def test_le_message_de_reparation_est_en_HAUT_du_bloc_reglages():
    """En bas, sous le bouton, il n'aurait pas été lu — c'est exactement ce qui vient d'arriver."""
    bloc = SOURCE.index('<section class="bloc" id="reglages"')
    manque = SOURCE.index('id="r-manque"', bloc)
    champs = SOURCE.index('id="r-start"', bloc)
    assert manque < champs, "le message doit précéder les champs qu'il explique"
