"""
L'ÉCRAN COGS & RECETTES — la charte, et le produit dont on ne connaît pas le coût.

⚠️ CET ÉCRAN N'AVAIT AUCUN TEST DE RENDU. Trois vues, un tiroir de recette, quatre surcouches,
trois mille lignes de script : la seule chose gardée était le moteur de coût côté serveur. Tout
ce qui s'affiche — les alertes comprises — vivait sans filet.

⚠️ ET L'ALERTE AJOUTÉE ICI RÉPOND À UNE ABSENCE QUI SE LIT COMME UN SUCCÈS. Un produit sans
recette et sans prix d'achat a un coût effectif de zéro côté serveur : sa marge tombe à 100 %,
il se range en tête des meilleures marges, et rien ne dit que le chiffre est une absence
déguisée. Un blanc se lit comme un blanc ; un 100 % se lit comme un résultat.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GABARIT = os.path.join(RACINE, "templates", "cogs.html")


def _source():
    return open(GABARIT, encoding="utf-8").read()


def _script():
    s = _source()
    return s[s.rindex("<script>") + 8:s.rindex("</script>")]


def _fonction(nom):
    js = _script()
    i = js.index(f"function {nom}(")
    return js[i:js.index("\n}", i) + 2]


# ⚠️ LE BANCAL RESTE PLUS PAUVRE QUE LA PAGE, JAMAIS PLUS PERMISSIF. `marquerEtat` pose et
# RETIRE l'attribut : un faux élément qui ne saurait que le poser rendrait vert un mutant
# supprimant le cas « rien à signaler ».
# ⚠️ `textContent` CONVERTIT EN CHAÎNE, COMME LE FAIT UN VRAI NŒUD. Le premier bancal gardait
# le nombre tel quel : la page écrit `el.textContent = sans.length`, et le test lisait `1` là où
# un navigateur affiche `"1"`. Un faux élément qui ne convertit pas laisse passer un nombre là
# où du texte est attendu — exactement le genre d'écart qu'on ne voit qu'à l'écran.
SOCLE = """
const champs = {};
function faire(id) {
  const o = { _t: '', innerHTML: '', attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; } };
  Object.defineProperty(o, 'textContent', {
    get() { return this._t; }, set(v) { this._t = String(v); },
  });
  return o;
}
const document = { getElementById: id => champs[id] || (champs[id] = faire(id)) };
function fmt(v) { return (Number(v) || 0).toFixed(2) + ' \\u20ac'; }
function marquerEtat(id, v) {
  const e = document.getElementById(id);
  if (v) e.setAttribute('data-etat', v); else e.removeAttribute('data-etat');
}
"""


def _rendre(produits):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    prog = (SOCLE + _fonction("productsWithoutCogs") + _fonction("renderNoCogsAlert")
            + f"renderNoCogsAlert({json.dumps(produits)});\n"
            + """console.log(JSON.stringify({
                 alerte: champs['no-cogs-alert'].innerHTML,
                 compte: champs['s-sanscout'].textContent,
                 sous:   champs['s-sanscout-sub'].textContent,
                 etat:   champs['i-sanscout'].attrs['data-etat'] || null,
               }));""")
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def P(titre, **kw):
    base = {"id": abs(hash(titre)) % 9999, "title": titre, "price_ht": 3.5, "price_ttc": 4.0,
            "tax_rate": 13, "supply_price": 0, "has_recipe": False, "recipe_total": None,
            "category": "Test", "commission_pct": None}
    base.update(kw)
    return base


# ── Ce qui compte comme « sans coût » ────────────────────────────────────────────────────────

def test_ni_recette_ni_prix_dachat_est_signale():
    r = _rendre([P("Superbock")])
    assert r["compte"] == "1"
    assert "sans coût connu" in r["alerte"]
    assert "100 %" in r["alerte"], "la conséquence — une marge parfaite affichée — n'est pas dite"


def test_un_prix_dachat_suffit_meme_sans_recette():
    """
    ⚠️ UN PRODUIT REVENDU TEL QUEL N'A AUCUNE RAISON D'AVOIR UNE RECETTE. Une bière, un soda :
    leur `supply_price` EST leur COGS. Exiger une recette de tout le catalogue signalerait
    cinquante produits parfaitement renseignés, et l'alerte cesserait d'être lue.
    """
    r = _rendre([P("Café", supply_price=0.18)])
    assert r["compte"] == "0"
    assert r["alerte"] == ""
    assert r["etat"] is None, "une alerte sans objet colore quand même la carte"


def test_une_recette_qui_chiffre_zero_compte_comme_absente():
    """
    ⚠️ ELLE EXISTE ET NE CHIFFRE RIEN, ce qui est le cas le plus trompeur : la colonne
    « recette » est remplie, la marge dit 100 %, et l'on croit le produit renseigné. La cause
    est ailleurs — des ingrédients à 0 € — et l'alerte le dit, parce que ça ne se répare pas au
    même endroit.
    """
    r = _rendre([P("Tarte", has_recipe=True, recipe_total=0)])
    assert r["compte"] == "1"
    assert "ne chiffre rien" in r["alerte"]


def test_une_recette_chiffree_nest_pas_signalee():
    r = _rendre([P("Croissant", has_recipe=True, recipe_total=0.42)])
    assert r["compte"] == "0" and r["alerte"] == ""


def test_un_partenaire_a_commission_na_pas_de_cout_matiere_et_cest_normal():
    """
    ⚠️ CE QU'ON REVERSE EST DÉJÀ RETIRÉ DE SA MARGE par `product_economics`. Le compter ici
    enverrait chercher une recette qui n'a aucune raison d'exister, sur des produits dont
    l'économie est déjà juste.
    """
    r = _rendre([P("Livre", commission_pct=30), P("Livre offert", commission_pct=0)])
    assert r["compte"] == "0", r["alerte"][:200]


# ── Ce que l'alerte dit, et comment elle le dit ──────────────────────────────────────────────

def test_le_plus_cher_dabord():
    """C'est là que les 100 % mentent le plus fort, en euros."""
    r = _rendre([P("Petit", price_ht=1.0), P("Gros", price_ht=12.0), P("Moyen", price_ht=4.0)])
    ordre = [m for m in re.findall(r">(Petit|Gros|Moyen)</a>", r["alerte"])]
    assert ordre == ["Gros", "Moyen", "Petit"], ordre


def test_chaque_nom_ouvre_le_tiroir_de_sa_recette():
    """
    ⚠️ UNE ALERTE QUI NOMME SANS OUVRIR OBLIGE À RETROUVER LE PRODUIT À LA MAIN, dans une liste
    filtrée par catégorie. Le premier jet appelait `openDrawerFor(id)`, qui n'existe pas : le
    lien se serait affiché, et le clic n'aurait rien fait.
    """
    r = _rendre([P("Superbock", price_ht=2.21, price_ttc=2.5, tax_rate=23)])
    assert "openDrawer(" in r["alerte"]
    # Le tiroir veut cinq arguments — id, titre, HT, TTC, taux.
    appel = re.search(r"openDrawer\(([^)]*)\)", r["alerte"]).group(1)
    assert len(appel.split(",")) == 5, appel
    assert "2.21" in appel and "2.5" in appel and "23" in appel, appel
    js = _script()
    assert "function openDrawer(" in js, "la fonction appelée par l'alerte n'existe pas"


def test_lalerte_est_appelee_au_chargement():
    """
    ⚠️ UNE FONCTION DE RENDU PARFAITE QUE PERSONNE N'APPELLE N'AFFICHE RIEN, et tous les
    contrôles ci-dessus resteraient verts : ils l'invoquent eux-mêmes. C'est exactement le
    défaut qui a laissé `tx-scope` vide pendant des mois sur Affluence — une ancre gardée,
    remplie par personne.

    ⚠️ ET ELLE REÇOIT `allProducts`, PAS LA LISTE FILTRÉE. Un produit sans coût ne cesse pas
    d'exister parce qu'on a tapé un mot dans la recherche.
    """
    js = _script()
    appels = re.findall(r"renderNoCogsAlert\(([a-zA-Z]+)\)", js)
    assert appels, "l'alerte n'est appelée nulle part"
    assert "allProducts" in appels, appels


def test_au_dela_dune_douzaine_le_reste_est_compte_pas_tu():
    """Une liste de soixante noms n'est plus une alerte, mais l'en cacher trois serait pire."""
    r = _rendre([P(f"P{i}", price_ht=i) for i in range(1, 21)])
    assert r["compte"] == "20"
    assert r["alerte"].count("openDrawer(") == 12
    assert "8 autre" in r["alerte"], "les huit restants disparaissent sans être comptés"


@pytest.mark.parametrize("combien,etat", [(0, None), (1, "attention"), (5, "attention"), (6, "alerte")])
def test_la_carte_passe_a_lalerte_au_dela_de_cinq(combien, etat):
    r = _rendre([P(f"P{i}") for i in range(combien)])
    assert r["etat"] == etat, f"{combien} produits → {r['etat']}"


def test_sans_aucun_produit_sans_cout_la_carte_le_dit_plutot_que_de_se_taire():
    """Un « 0 » nu ne distingue pas « tout est chiffré » de « rien n'a été regardé »."""
    r = _rendre([P("Café", supply_price=0.18)])
    assert "chiffré" in r["sous"]


# ── La charte ────────────────────────────────────────────────────────────────────────────────

def test_la_page_porte_la_charte():
    s = _source()
    assert 'class="page db"' in s, "la classe qui définit les jetons `--db-*` est absente"
    assert "/static/dashboard.css?v=" in s, "la feuille de charte n'est pas chargée, ou sans version"


def test_les_onglets_ne_sont_plus_une_troisieme_copie():
    """
    ⚠️ FIDÉLITÉ ET RÉGLAGES PARTAGENT `.nav-seg` DEPUIS LA REFONTE ; cette page avait gardé son
    propre jeu de règles et son propre marqueur d'actif (`.active` au lieu d'`aria-selected`).
    Trois copies d'une forme, c'est une forme qui diverge — on en corrige deux sur trois.
    """
    s = _source()
    assert 'class="nav-seg"' in s
    bloc = s[s.index("<style>"):s.index("</style>")]
    for mort in (".view-tabs", ".view-tab"):
        assert mort not in bloc, f"{mort} : l'ancien composant est revenu"
    assert s.count('aria-selected') >= 3
    assert "classList.toggle('active'" not in _script(), "le marqueur d'actif est resté sur une classe"


def test_usage_et_variance_a_bien_disparu_des_deux_cotes():
    """
    ⚠️ RETIRER L'ÉCRAN SANS RETIRER LES ROUTES LAISSE UNE API VIVANTE QUE PLUS RIEN N'APPELLE.
    Et retirer les routes sans retirer l'écran laisse des boutons qui échouent en silence : les
    deux vont ensemble, et le contrôle les tient ensemble.
    """
    s = _source()
    for mort in ('id="view-usage"', 'id="tab-usage"', "loadUsage", "rankUsageRows",
                 "openPurchaseModal", "savePurchase"):
        assert mort not in s, f"{mort} : reste de l'écran retiré"
    serveur = open(os.path.join(RACINE, "app.py"), encoding="utf-8").read()
    serveur = re.sub(r"^\s*#.*$", "", serveur, flags=re.M)
    for route in ("/api/inventory/usage", "/api/inventory/purchases"):
        assert route not in serveur, f"{route} : la route survit à son écran"
