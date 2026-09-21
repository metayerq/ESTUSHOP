"""
LE LANGAGE VISUEL DES INDICATEURS.

⚠️ DOUZE CHIFFRES DE TAILLE IDENTIQUE NE DISENT PAS LEQUEL REGARDER. Et un nombre coloré est
plus difficile à lire qu'un nombre en encre — sur douze indicateurs colorés, plus rien ne
ressort. La bande d'accent porte l'état, le chiffre reste lisible, et seuls ceux qui décident
quelque chose passent en vedette.

⚠️ AUCUNE DE CES RÈGLES NE LÈVE SI ON LA CASSE. L'écran reste « fonctionnel » : il se lit
simplement moins bien, et on finit par ne plus l'ouvrir.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


CSS = lire("static/style.css")
DASH = lire("static/dashboard.js")
COGS = lire("templates/cogs.html")


# ── La bande d'accent ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etat", ["ok", "attention", "alerte"])
def test_chaque_etat_a_sa_bande(etat):
    assert f'.kpi-cell[data-etat="{etat}"]::before' in CSS


def test_le_chiffre_nest_plus_colore():
    """
    ⚠️ LA RÉGRESSION À EMPÊCHER. Le prime cost peignait sa propre valeur en vert, ambre ou
    rouge ; avec la bande, la couleur du texte devient redondante et nuit à la lecture.
    """
    i = DASH.index("primeEl.textContent = prime.toFixed(1)")
    bloc = DASH[i:i + 600]
    assert "primeEl.style.color = ''" in bloc
    assert "prime <= 67 ? 'var(--green)'" not in bloc


def test_les_deux_indicateurs_qui_decident_sont_en_vedette():
    """
    La marge et le prime cost décident d'un geste ; le reste est du contexte. ⚠️ ET PAS PLUS DE
    DEUX : si tout est en vedette, plus rien ne l'est.
    """
    index = lire("templates/index.html")
    assert index.count("kpi-cell vedette") == 2
    assert ".kpi-cell.vedette .kpi-value" in CSS


def test_un_indicateur_sans_donnee_na_pas_detat():
    """
    ⚠️ « PAS DE DONNÉE » N'EST PAS « BON ». Poser une valeur neutre allumerait une bande verte
    sur une case vide.
    """
    i = DASH.index("function etat(el, valeur)")
    bloc = DASH[i:i + 400]
    assert "removeAttribute('data-etat')" in bloc


# ── Le repère de seuil ───────────────────────────────────────────────────────────────────────

def test_le_prime_cost_porte_son_repere_de_cible():
    """
    ⚠️ VOIR DE COMBIEN ON DÉPASSE VAUT MIEUX QUE SAVOIR QU'ON DÉPASSE. Une barre sans repère
    dit « c'est trop » ; avec le repère, elle dit « de deux points ».
    """
    assert "marquerSeuil(primeBar, 65" in DASH
    assert ".seuil-marque" in CSS


def test_le_repere_est_dans_la_barre_pas_a_cote():
    """Une légende sous le graphique oblige à convertir une largeur en pourcentage — c'est
    exactement le calcul que le repère évite."""
    i = DASH.index("function marquerSeuil")
    bloc = DASH[i:i + 700]
    assert "m.style.left" in bloc
    assert "appendChild(m)" in bloc


def test_le_repere_ne_sort_pas_de_la_barre():
    """Un seuil à 140 % placerait le trait hors du cadre, sans rien dire."""
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    # ⚠️ ON APPELLE LA VRAIE FONCTION, avec un DOM simulé. La première version de ce test
    # recopiait le bornage dans le programme node et vérifiait donc sa propre copie : le mutant
    # qui retirait le `Math.min` passait tranquillement.
    i = DASH.index("function marquerSeuil")
    fn = DASH[i:DASH.index("\n}", i) + 2]
    prog = fn + """
    function faireBarre(){
      var env = { classList: { add: function(){} }, enfants: [],
                  querySelector: function(){ return null; },
                  appendChild: function(x){ this.enfants.push(x); } };
      return { parentElement: env, env: env };
    }
    global.document = { createElement: function(){ return { style: {}, className: '' }; } };
    var pos = [-10, 0, 65, 100, 140].map(function(p){
      var b = faireBarre();
      marquerSeuil(b, p, 'x');
      return b.env.enfants[0].style.left;
    });
    console.log(JSON.stringify(pos));
    """
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["0%", "0%", "65%", "100%", "100%"]


# ── Les états vides ──────────────────────────────────────────────────────────────────────────

def test_une_case_vide_dit_ce_qui_la_remplira():
    """
    ⚠️ « NOT MEASURABLE » LAISSE DEVANT UN ÉCRAN MORT. Une case vide doit nommer le geste, et
    porter le lien qui y mène.
    """
    for morceau in ("Il manque les prix d", "Aucun prix d"):
        assert morceau in DASH, f"état vide sans consigne : {morceau}"
    assert DASH.count('href="/cogs"') >= 2


def test_les_anciens_libelles_morts_ont_disparu():
    assert "not measurable" not in DASH
    assert "no COGS set" not in DASH


# ── COGS parle la même langue ────────────────────────────────────────────────────────────────

def test_cogs_met_la_couverture_en_tete_et_en_vedette():
    """
    ⚠️ UNE MARGE MOYENNE DE 75 % SUR 96 % DU CATALOGUE ET LA MÊME SUR 55 % NE SONT PAS LA MÊME
    INFORMATION — et c'est la seconde qui appelle un geste. L'afficher à côté de la marge, à la
    même taille, laissait le lecteur décider lequel des deux compte.
    """
    assert 'id="s-couv"' in COGS
    assert 'id="i-couv"' in COGS and "sum-item vedette" in COGS
    assert COGS.index('id="i-couv"') < COGS.index('id="s-avg"')


def test_cogs_emploie_la_meme_grammaire_que_le_dashboard():
    """⚠️ DEUX GRAMMAIRES VISUELLES DANS UN MÊME OUTIL obligent à réapprendre à chaque page."""
    for etat in ("ok", "attention", "alerte"):
        assert f'.sum-item[data-etat="{etat}"]::before' in COGS


def test_une_marge_negative_alerte_meme_sans_ouvrir_la_liste():
    """Une perte à chaque vente doit trouver le lecteur."""
    i = COGS.index("marquerEtat('i-min'")
    assert "< 0 ? 'alerte'" in COGS[i:i + 200]


# ── Le langage des sections ──────────────────────────────────────────────────────────────────

def test_les_conteneurs_sont_plats():
    """
    ⚠️ LES COINS ARRONDIS ET LES OMBRES FONT « APPLICATION GRAND PUBLIC ». Un outil de gestion
    se lit mieux en surfaces franches séparées par des filets — c'est la moitié du changement
    de registre, et c'est ce qui manquait quand seul le menu avait changé.
    """
    for regle in (".card {", ".chart-block {", ".table-wrap {"):
        i = CSS.index(regle)
        bloc = CSS[i:i + 260]
        rayons = re.findall(r"border-radius:\s*(\d+)px", bloc)
        assert rayons, f"{regle} n'a plus de rayon déclaré"
        assert int(rayons[0]) <= 4, f"{regle} est encore arrondi à {rayons[0]}px"


def test_la_grille_dindicateurs_est_un_seul_bloc():
    """
    ⚠️ LES GOUTTIÈRES FAISAIENT LIRE DOUZE OBJETS INDÉPENDANTS. Les filets font lire un tableau
    de bord, et l'œil compare les colonnes au lieu de les parcourir une à une.
    """
    i = CSS.index(".kpi-grid {")
    bloc = CSS[i:CSS.index("}", i)]
    assert "gap: 0;" in bloc
    assert "border: 1px solid" in bloc
    assert "overflow: hidden" in bloc


def test_les_separateurs_survivent_a_nimporte_quel_nombre_de_colonnes():
    """
    ⚠️ LA GRILLE EST EN `auto-fit` : on ne sait pas à l'avance quelle cellule est en bout de
    ligne. Les deux anciennes règles `nth-child` rattrapaient ça à la main, et n'étaient justes
    que pour deux et quatre colonnes — pas trois. Une ombre interne coupée par le conteneur
    marche pour tous les cas.
    """
    i = CSS.index(".kpi-cell {")
    bloc = CSS[i:CSS.index("}", i)]
    assert "box-shadow:" in bloc
    assert ".kpi-cell:nth-child" not in CSS, "le rattrapage manuel est revenu"


def test_les_chiffres_salignent_verticalement():
    """Sans chasse tabulaire, deux montants superposés n'ont pas la même largeur — et une
    colonne de nombres cesse d'être comparable d'un coup d'œil."""
    # ⚠️ ANCRÉ EN DÉBUT DE LIGNE. `.kpi-cell.vedette .kpi-value {` CONTIENT la chaîne
    # `.kpi-value {` : chercher la sous-chaîne tombait sur la règle de vedette, qui ne porte
    # que la taille. Le test échouait sur du code correct.
    m = re.search(r"(?m)^\.kpi-value \{([^}]*)\}", CSS)
    assert m, "la règle .kpi-value a disparu"
    assert "tabular-nums" in m.group(1)


def test_le_tiret_decoratif_a_disparu():
    """
    ⚠️ UN SIGNE STRUCTUREL DOIT ENCODER QUELQUE CHOSE DE VRAI — un ordre, un niveau, un état.
    Le « — » devant chaque titre de section n'encodait rien : il ajoutait du bruit sur quinze
    pages.
    """
    assert '.section-label::before' not in CSS


def test_ce_quon_clique_garde_ses_arrondis():
    """
    ⚠️ TOUT APLATIR RENDRAIT UN BOUTON INDISCERNABLE D'UN CADRE. L'arrondi dit « ceci répond au
    doigt » ; il reste sur les contrôles et sur les surfaces flottantes.
    """
    i = CSS.index(".btn-refresh {")
    assert re.search(r"border-radius:\s*[6-9]px", CSS[i:i + 300])


def test_lancienne_navigation_ne_laisse_aucun_style_mort():
    """
    ⚠️ SOIXANTE-DIX RÈGLES MORTES DANS DIX FICHIERS. Du CSS qu'aucun balisage n'utilise ne se
    voit pas — il se recopie, se maintient, et finit par être modifié « au cas où ». La nav
    qu'il habillait n'existe plus.
    """
    import glob
    restes = []
    for chemin in glob.glob(os.path.join(RACINE, "templates", "*.html")):
        with open(chemin, encoding="utf-8") as f:
            if ".app-nav" in f.read():
                restes.append(os.path.basename(chemin))
    assert not restes, f"styles de l'ancienne navigation encore présents : {restes}"


# ── Densité et chasse fixe ───────────────────────────────────────────────────────────────────

def test_le_rail_descend_jusquen_bas():
    """
    ⚠️ LE DÉFAUT SIGNALÉ PAR QUENTIN. Avec `align-self: start` et une hauteur MAXIMALE, le rail
    ne fait que la taille de ses liens : son fond sombre s'arrête au milieu de l'écran et
    laisse une colonne vide en dessous. Une hauteur FIXE de 100vh le fait occuper toute la
    fenêtre — et `overflow-y` reprend la main si les entrées venaient à dépasser.
    """
    i = CSS.index(".rail {")
    bloc = CSS[i:CSS.index("}", i)]
    assert "height: 100vh" in bloc
    assert "max-height: 100vh" not in bloc, "la hauteur est redevenue un plafond"
    assert "overflow-y: auto" in bloc


def test_le_rail_replie_ne_garde_pas_la_hauteur():
    """Sur mobile il devient une barre horizontale : 100vh l'étirerait sur tout l'écran."""
    i = CSS.index("@media (max-width: 860px)")
    assert "height: auto" in CSS[i:i + 700]


def test_les_tableaux_sont_en_chasse_fixe():
    """
    ⚠️ SUR TOUT LE TABLEAU, PAS SEULEMENT SUR LES NOMBRES. C'est ce qui fait basculer le
    registre : les colonnes s'alignent d'une ligne à l'autre, même les libellés, et l'œil
    descend une colonne au lieu de la relire.
    """
    m = re.search(r"(?m)^table \{([^}]*)\}", CSS)
    assert m, "la règle `table` a disparu"
    assert "var(--mono)" in m.group(1)
    assert "tabular-nums" in m.group(1)


def test_aucun_tableau_nechappe_a_la_chasse_fixe():
    """
    ⚠️ UNE SEULE PAGE QUI GARDE SA POLICE PROPORTIONNELLE suffit à faire douter du reste : on
    ne sait plus si l'alignement est une règle ou un hasard.
    """
    import glob
    fautifs = []
    for chemin in sorted(glob.glob(os.path.join(RACINE, "templates", "*.html"))):
        with open(chemin, encoding="utf-8") as f:
            html = f.read()
        for style in re.findall(r"<style>(.*?)</style>", html, re.S):
            for sel, corps in re.findall(r"([^{}]+)\{([^{}]*)\}", style):
                s2 = " ".join(sel.split())
                vise = re.search(r"(^|[\s,>])(table|thead|tbody|th|td)\b", s2) or \
                    re.search(r"\.[\w-]*table\b", s2)
                if vise and "font-family" in corps and "var(--mono)" not in corps \
                        and "inherit" not in corps:
                    fautifs.append(f"{os.path.basename(chemin)} · {s2[:30]}")
    assert not fautifs, f"tableaux en police proportionnelle : {fautifs}"


def test_le_corps_des_tableaux_descend_avec_la_chasse_fixe():
    """
    ⚠️ UNE CHASSE FIXE OCCUPE PLUS DE LARGEUR À TAILLE ÉGALE. Garder 13px ferait déborder les
    tableaux les plus larges — réconciliation, COGS — précisément ceux qu'on consulte le plus.
    """
    m = re.search(r"(?m)^table \{([^}]*)\}", CSS)
    taille = re.search(r"font-size:\s*(\d+(?:\.\d)?)px", m.group(1))
    assert taille and float(taille.group(1)) <= 12


def test_la_densite_a_monte():
    """Les rembourrages des cellules et des indicateurs se sont resserrés."""
    assert "tbody td { padding: 6px 11px; }" in CSS
    i = CSS.index(".kpi-cell {")
    assert "padding: 12px 14px 12px 17px" in CSS[i:CSS.index("}", i)]
    assert ".app .page { max-width: none; margin: 0; padding: 20px 20px 64px; }" in CSS
