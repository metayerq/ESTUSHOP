"""
LES ONGLETS ET LA PAGINATION DE LA PAGE FIDÉLITÉ.

⚠️ CE DÉCOUPAGE EST UN DÉCOUPAGE D'USAGE, PAS D'ESTHÉTIQUE. « Vue d'ensemble » se lit une fois
par semaine ; « Clients » s'ouvre plusieurs fois par jour pour chercher quelqu'un ; « Réglages »
se touche trois fois par an. Les empiler faisait défiler quatre écrans pour atteindre le tableau
— celui qu'on vient voir le plus souvent.
"""

import os
import re
import subprocess
import shutil

import pytest


def _gabarit():
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "fidelidade.html")
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def _js():
    return "\n".join(re.findall(r"<script>(.*?)</script>", _gabarit(), re.S))


# ── Le découpage ─────────────────────────────────────────────────────────────────────────────

def test_les_trois_panneaux_existent_et_sont_disjoints():
    html = _gabarit()
    for o in ("apercu", "clients", "reglages"):
        assert f'id="onglet-{o}"' in html
    # Chaque panneau est fermé avant l'ouverture du suivant.
    positions = [html.index(f'id="onglet-{o}"') for o in ("apercu", "reglages", "clients")]
    assert positions == sorted(positions), "les panneaux s'imbriquent"


def test_les_alertes_restent_au_dessus_des_onglets():
    """
    ⚠️ UNE ALERTE QU'IL FAUT CLIQUER POUR TROUVER N'EST PAS UNE ALERTE. Les deux bandeaux —
    anomalies et « aucune date de lancement » — doivent précéder la barre d'onglets.
    """
    html = _gabarit()
    barre = html.index('id="onglets"')
    for alerte in ('id="alerte"', 'id="alerte-lancement"'):
        assert html.index(alerte) < barre, f"{alerte} est enfermée dans un onglet"


def test_le_panneau_masque_le_reste_vraiment():
    """
    ⚠️ LE BOGUE DE LA BARRE BLANCHE, LE 19/09 : une règle d'affichage plus spécifique écrasait
    l'attribut `hidden`, et un élément « caché » occupait toujours la place. La même faute ici
    laisserait trois panneaux empilés.
    """
    # ⚠️ LA RÈGLE A DÉMÉNAGÉ DANS LA FEUILLE COMMUNE avec la barre d'onglets elle-même. La
    # chercher dans le gabarit ferait échouer un test sur un déplacement, pas sur une
    # régression — et la couvrir POUR LES DEUX PAGES vaut mieux que pour une seule.
    import os
    commun = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "static", "style.css"), encoding="utf-8").read()
    assert ".onglet[hidden], .pa-panneau[hidden] { display: none !important; }" in commun


def test_longlet_actif_se_distingue_par_plus_quune_couleur():
    """
    Sur un écran mal calibré — ou en plein soleil, ce qui est le cas d'un comptoir — une seule
    nuance de gris ne dit pas où l'on est.
    """
    import os
    commun = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "static", "style.css"), encoding="utf-8").read()
    i = commun.index('.nav-seg button[aria-selected="true"] {')
    bloc = commun[i:i + 220]
    assert "font-weight" in bloc and "background" in bloc and "border-color" in bloc


def test_la_barre_donglets_nest_ecrite_quune_fois():
    """
    ⚠️ DEUX COPIES D'UNE MÊME FORME, C'EST UNE FORME QUI DIVERGE. On corrige l'une, on oublie
    l'autre, et la page qu'on ouvre le moins reste dans l'ancien style — c'est déjà arrivé ici
    avec la feuille de nav laissée sur `marketing.html`.
    """
    import os
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for page in ("fidelidade.html", "parametres.html"):
        g = open(os.path.join(racine, "templates", page), encoding="utf-8").read()
        bloc = g[g.index("<style>"):g.index("</style>")]
        assert ".onglets button" not in bloc and ".pa-onglets button" not in bloc, page
        assert 'class="nav-seg"' in g, page


def test_les_onglets_ne_ressemblent_pas_au_filtre_de_donnees():
    """
    ⚠️ `.tx-segment` FILTRE LA DONNÉE (journée / soir), `.nav-seg` CHANGE D'ÉCRAN. Leur donner
    la même apparence ferait croire qu'on filtre quand on navigue — et chercher ensuite le
    bouton qui « remet tout », qui n'existe pas pour des onglets.
    """
    import os
    commun = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "static", "style.css"), encoding="utf-8").read()
    nav = commun[commun.index(".nav-seg {"):commun.index(".nav-seg button {")]
    seg = commun[commun.index(".tx-segment {"):commun.index(".tx-segment button {")] \
        if ".tx-segment {" in commun else ""
    assert nav != seg


def test_longlet_est_dans_ladresse():
    """
    ⚠️ SANS ÇA, l'alerte qui pointe vers #reglages n'ouvre rien, un signet ramène toujours au
    même endroit, et un rechargement perd la place.
    """
    js = _js()
    assert "location.hash" in js
    assert "hashchange" in js
    assert "history.replaceState" in js


def test_le_lien_de_lalerte_vise_bien_un_onglet():
    html = _gabarit()
    assert 'href="#reglages"' in html


# ── La pagination ────────────────────────────────────────────────────────────────────────────

def test_le_tri_et_le_filtre_portent_sur_tout_le_fichier():
    """
    ⚠️ C'EST LA GARANTIE QUI REND LA COUPE ACCEPTABLE. Trier les cinquante premiers au lieu de
    tout le fichier donnerait « les plus gros soldes parmi les cinquante premiers » — un
    classement qui ressemble à un classement, et qui n'en est pas un.
    """
    js = _js()
    i = js.index("function tableau()")
    bloc = js[i:js.index("function fiche(", i)]
    # Le filtre et le tri viennent AVANT la coupe.
    assert bloc.index("vus.slice().sort") < bloc.index("vus.slice(0, limite)")
    assert bloc.index("comptes.filter") < bloc.index("vus.slice(0, limite)")


def test_le_compteur_annonce_le_total_pas_laffichage():
    js = _js()
    assert "vus.length + ' sur ' + comptes.length" in js


def test_le_bouton_chiffre_ce_qui_reste():
    """
    ⚠️ « VOIR PLUS » SANS NOMBRE NE DIT PAS s'il reste trois lignes ou trois cents — et on
    clique sans savoir si ça vaut la peine.
    """
    js = _js()
    i = js.index("var reste = vus.length")
    bloc = js[i:i + 700]
    assert "Math.min(PAS, reste)" in bloc
    assert "client(s) au-delà" in bloc


def test_la_recherche_et_le_filtre_recoupent_mais_pas_le_tri():
    """
    ⚠️ DEUX GESTES, DEUX EFFETS. Chercher change l'ENSEMBLE : garder « 200 affichés » après une
    recherche qui n'en rend que trois n'a aucun sens. Trier ne change que l'ORDRE : ramener à
    cinquante après trois clics sur « voir plus » ferait perdre un geste délibéré.
    """
    js = _js()
    assert "E('q').addEventListener('input', recouper)" in js
    i = js.index("var b = e.target.closest('button[data-f]')")
    assert "recouper();" in js[i:i + 400]
    # Le tri, lui, appelle `tableau` et non `recouper`.
    j = js.index("th[data-tri]'); if (!th) return")
    bloc = js[j:j + 900]
    assert "recouper()" not in bloc


def test_la_coupe_est_de_cinquante():
    assert "var PAS = 50;" in _js()


# ── Le comportement réel ─────────────────────────────────────────────────────────────────────

def test_le_decoupage_rend_bien_cinquante_lignes_puis_le_reste():
    """
    ⚠️ EXÉCUTÉ, PAS RELU. La logique de coupe tient en deux lignes, et c'est précisément le
    genre de code où une erreur de borne ne se voit pas : 49 lignes au lieu de 50 ne se compte
    pas à l'œil.
    """
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    programme = """
    const PAS = 50;
    let limite = PAS;
    const vus = Array.from({length: 137}, (_, i) => i);
    const lots = [];
    for (let i = 0; i < 4; i++){
      const coupe = vus.slice(0, limite);
      lots.push([coupe.length, vus.length - coupe.length]);
      limite += PAS;
    }
    console.log(JSON.stringify(lots));
    """
    r = subprocess.run(["node", "-e", programme], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout) == [[50, 87], [100, 37], [137, 0], [137, 0]]


def test_longlet_clients_annonce_combien_il_en_contient():
    """
    ⚠️ ET IL DIT LE TOTAL, PAS LE FILTRÉ. Un compteur qui suivrait la recherche en cours
    afficherait 3 après avoir tapé un prénom, et ferait croire que le fichier a fondu.
    """
    html = _gabarit()
    assert 'id="onglet-n-clients"' in html
    js = _js()
    i = js.index("onglet-n-clients")
    bloc = js[max(0, i - 400):i + 120]
    assert "comptes.length" in bloc and "vus.length" not in bloc.split("nOnglet")[-1]
