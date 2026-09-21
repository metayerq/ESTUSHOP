"""
LE MENU DE GAUCHE.

⚠️ LE RANGEMENT ÉTAIT ÉCRIT EN DUR, ET IL AVAIT TORT. « Dépenses » vivait sous « Caisse » alors
que ce sont des achats datés qui pèsent sur le mois, pas sur le tiroir. Une catégorie fausse
apprend à chercher au mauvais endroit, et on finit par ne plus ouvrir la page.

⚠️ LE PIÈGE DE TOUT MENU CONFIGURABLE : on ajoute une page au code, elle n'est dans aucun
réglage enregistré, et elle reste invisible pour toujours. Personne ne cherche un écran dont il
ignore l'existence.
"""

import pytest

import menu


def chemins(structure):
    return [e["chemin"] for g in structure for e in g["entrees"]]


# ── Le catalogue dit la vérité ───────────────────────────────────────────────────────────────

def test_chaque_entree_mene_a_une_page_qui_existe():
    """
    ⚠️ UN CHEMIN MORT DANS LE CATALOGUE EST UNE ENTRÉE DE MENU QUI MÈNE À UN 404. Le lien a l'air
    normal, la page n'existe pas, et on cherche la panne dans la page plutôt que dans la liste.
    """
    import app
    routes = {str(r.rule) for r in app.app.url_map.iter_rules()}
    for e in menu.CATALOGUE:
        assert e["chemin"] in routes, f"{e['chemin']} n'est pas une route"


def test_aucun_chemin_en_double():
    vus = [e["chemin"] for e in menu.CATALOGUE]
    assert len(vus) == len(set(vus))


def test_les_depenses_ne_sont_plus_dans_la_caisse():
    """
    ⚠️ C'EST LA CORRECTION QUI A DÉCLENCHÉ TOUT CECI. `/expenses` alimente le P&L mensuel à côté
    du chiffre d'affaires et des commissions : ce sont des achats, pas ce que le terminal a
    encaissé. Les ranger avec la réconciliation faisait chercher un ticket de caisse là où il
    n'y en a jamais eu.
    """
    g = {e["chemin"]: e["groupe"] for e in menu.CATALOGUE}
    assert g["/expenses"] == g["/charges"] == g["/cogs"]
    assert g["/expenses"] != g["/reconciliation"]


# ── Le garde-fou central ─────────────────────────────────────────────────────────────────────

def test_une_page_absente_de_la_configuration_apparait_quand_meme():
    """
    ⚠️ LE PIÈGE CENTRAL. Une configuration enregistrée en septembre ne connaît pas la page
    ajoutée en novembre. Si le menu se contentait de la suivre, la page neuve serait invisible —
    et personne ne cherche un écran dont il ignore l'existence.
    """
    config = [{"chemin": "/", "libelle": "Dashboard", "groupe": "Pilotage"}]
    assert set(chemins(menu.construire(config))) == {e["chemin"] for e in menu.CATALOGUE}


def test_une_page_retiree_du_code_nest_pas_affichee():
    """Sinon l'entrée reste et mène à un 404 — on chercherait la panne dans la page absente."""
    config = [{"chemin": "/ancienne-page", "libelle": "Fantôme", "groupe": "Pilotage"}]
    assert "/ancienne-page" not in chemins(menu.construire(config))


def test_un_doublon_dans_la_configuration_ne_dedouble_pas_lentree():
    config = [{"chemin": "/stock", "groupe": "A"}, {"chemin": "/stock", "groupe": "B"}]
    assert chemins(menu.construire(config)).count("/stock") == 1


@pytest.mark.parametrize("config", [None, [], [{}], [{"chemin": ""}], ["pas un objet"],
                                    [{"chemin": None}]])
def test_une_configuration_abimee_ne_vide_pas_le_menu(config):
    """
    ⚠️ UN MENU VIDE EST UN SITE PERDU. Quelle que soit la bêtise enregistrée en base, le
    catalogue reste le plancher : on peut toujours revenir aux réglages et réparer.
    """
    assert set(chemins(menu.construire(config))) == {e["chemin"] for e in menu.CATALOGUE}


# ── Ce que la configuration peut vraiment faire ──────────────────────────────────────────────

def test_lordre_enregistre_est_respecte_dans_un_groupe():
    config = [{"chemin": "/charges"}, {"chemin": "/stock"}, {"chemin": "/cogs"}]
    coûts = next(g for g in menu.construire(config) if g["titre"] == "Coûts")
    assert [e["chemin"] for e in coûts["entrees"]][:3] == ["/charges", "/stock", "/cogs"]


def test_un_groupe_prend_le_rang_de_sa_premiere_entree():
    """
    ⚠️ LES GROUPES N'ONT PAS D'ORDRE À EUX. Leur donner un rang séparé ferait deux listes à tenir
    d'accord : on déplacerait une entrée en tête sans que son groupe remonte, et le réglage
    paraîtrait ne pas marcher.
    """
    config = [{"chemin": "/stock"}]
    assert [g["titre"] for g in menu.construire(config)][0] == "Coûts"


def test_un_poste_peut_etre_renomme():
    config = [{"chemin": "/transactions", "libelle": "Fréquentation"}]
    e = next(e for e in menu.a_plat(config) if e["chemin"] == "/transactions")
    assert e["libelle"] == "Fréquentation"


@pytest.mark.parametrize("fonction", ["a_plat", "construire"])
def test_un_libelle_vide_retombe_sur_le_defaut(fonction):
    """
    Un champ effacé par mégarde ne doit pas donner une entrée sans nom, impossible à cliquer.

    ⚠️ LES DEUX FONCTIONS, PAS UNE. La version d'avant ne vérifiait que `a_plat`, celle de
    l'écran de réglage : le menu AFFICHÉ pouvait donc perdre son libellé sans qu'un test
    rougisse — et c'est celui-là qu'on clique tous les jours.
    """
    config = [{"chemin": "/stock", "libelle": "   "}]
    sortie = getattr(menu, fonction)(config)
    entrees = sortie if fonction == "a_plat" else [e for g in sortie for e in g["entrees"]]
    assert next(e for e in entrees if e["chemin"] == "/stock")["libelle"] == "Stock"


def test_un_groupe_vide_retombe_sur_le_defaut():
    config = [{"chemin": "/stock", "groupe": ""}]
    e = next(e for e in menu.a_plat(config) if e["chemin"] == "/stock")
    assert e["groupe"] == "Coûts"


def test_un_poste_peut_changer_de_groupe_et_le_groupe_apparait():
    config = [{"chemin": "/stock", "groupe": "Fournisseurs"}]
    titres = [g["titre"] for g in menu.construire(config)]
    assert titres[0] == "Fournisseurs"


def test_un_poste_masque_disparait_du_menu():
    config = [{"chemin": "/stock", "masque": True}]
    assert "/stock" not in chemins(menu.construire(config))


def test_un_groupe_dont_toutes_les_entrees_sont_masquees_nexiste_pas():
    """
    ⚠️ UN TITRE SEUL, SANS RIEN DESSOUS, SE LIT COMME UNE PAGE QUI N'A PAS CHARGÉ. Le groupe
    n'est pas filtré après coup : il n'est créé QUE par une entrée visible, ce qui rend le cas
    impossible plutôt que rattrapé.
    """
    config = [{"chemin": "/stock", "groupe": "Seul", "masque": True}]
    structure = menu.construire(config)
    assert "Seul" not in [g["titre"] for g in structure]
    assert all(g["entrees"] for g in structure)


# ── Ce que la configuration ne peut pas faire ────────────────────────────────────────────────

def test_les_reglages_ne_peuvent_pas_etre_masques():
    """
    ⚠️ C'EST LA PAGE QUI CONTIENT LE RÉGLAGE DU MENU. La masquer fermerait la porte de
    l'intérieur, la clé restée dedans : plus aucun écran pour la rouvrir.
    """
    config = [{"chemin": "/parametres", "masque": True}]
    assert "/parametres" in chemins(menu.construire(config))
    assert next(e for e in menu.a_plat(config) if e["chemin"] == "/parametres")["verrouille"]


def test_masquer_nest_pas_interdire():
    """
    ⚠️ CE RÉGLAGE EST COSMÉTIQUE, ET IL DOIT LE RESTER. Masquer une entrée range l'écran ; ça
    n'a jamais fermé une route. Les droits vivent dans `_require_auth`, un seul endroit — deux
    mécanismes de permission, c'est la garantie qu'un jour l'un des deux laisse passer.
    """
    import app
    assert "masque" not in open("app.py", encoding="utf-8").read().split("def _require_auth")[1][:2000]


# ── La pastille d'alerte ─────────────────────────────────────────────────────────────────────

def test_la_pastille_suit_le_chemin_et_pas_le_libelle():
    """Un poste renommé garde son compteur d'écarts — sinon l'alerte disparaît au premier
    renommage, et c'est justement l'alerte qu'on ne doit jamais perdre."""
    config = [{"chemin": "/reconciliation", "libelle": "Caisse du jour"}]
    e = next(e for g in menu.construire(config) for e in g["entrees"]
             if e["chemin"] == "/reconciliation")
    assert e["pastille"] == "rail-ecarts"


# ── Le chemin d'enregistrement ───────────────────────────────────────────────────────────────

import pytest as _pt


@_pt.fixture
def admin_menu(monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "_identite", lambda: ("admin", "quentin@x.pt"))
    monkeypatch.setattr(flask_app, "_journal_action", lambda *a: "écrit")
    flask_app._MENU_CACHE["v"] = None
    flask_app.app.config["TESTING"] = True
    return flask_app


def test_on_enregistre_ce_qui_a_ete_reconstruit_pas_ce_qui_a_ete_envoye(admin_menu, monkeypatch):
    """
    ⚠️ ÉCRIRE LE JSON BRUT LAISSERAIT ENTRER EN BASE CE QUE LE MODULE PASSE ENSUITE SON TEMPS À
    CORRIGER : un chemin inconnu, un libellé vide, des réglages masqués. Un jour quelqu'un lirait
    la table en croyant y voir la vérité.
    """
    ecrit = {}
    monkeypatch.setattr(admin_menu, "_supa_upsert",
                        lambda t, r: (ecrit.update(r), (True, None))[1])
    c = admin_menu.app.test_client()
    r = c.put("/api/parametres/menu", json={"entrees": [
        {"chemin": "/inexistante", "libelle": "Fantôme", "groupe": "X"},
        {"chemin": "/parametres", "masque": True},
        {"chemin": "/stock", "libelle": "  ", "groupe": "Achats"},
    ]})
    assert r.status_code == 200
    valeur = ecrit["valeur"]
    chemins_ = [e["chemin"] for e in valeur]
    assert "/inexistante" not in chemins_
    assert next(e for e in valeur if e["chemin"] == "/parametres")["masque"] is False
    assert next(e for e in valeur if e["chemin"] == "/stock")["libelle"] == "Stock"
    # ⚠️ TOUTES LES PAGES SONT ÉCRITES, PAS SEULEMENT CELLES REÇUES. Une configuration partielle
    # enregistrée telle quelle se relirait ensuite en complétant par le catalogue — et l'ordre
    # obtenu dépendrait de l'ordre du code, pas de celui qu'on vient de choisir.
    assert len(valeur) == len(menu.CATALOGUE)


def test_un_envoi_vide_est_refuse(admin_menu, monkeypatch):
    """⚠️ UN MENU VIDE EST UN SITE PERDU. Mieux vaut refuser que d'avoir à réparer en base."""
    ecrits = []
    monkeypatch.setattr(admin_menu, "_supa_upsert", lambda t, r: ecrits.append(r) or (True, None))
    c = admin_menu.app.test_client()
    assert c.put("/api/parametres/menu", json={"entrees": []}).status_code == 400
    assert c.put("/api/parametres/menu", json={}).status_code == 400
    assert not ecrits


def test_le_cache_du_menu_est_vide_apres_enregistrement(admin_menu, monkeypatch):
    """
    ⚠️ SANS ÇA, ON ENREGISTRE ET RIEN NE BOUGE PENDANT TRENTE SECONDES. On recommence, on croit
    que l'écran ne marche pas — et on finit par enregistrer trois fois le même réglage.
    """
    monkeypatch.setattr(admin_menu, "_supa_upsert", lambda t, r: (True, None))
    admin_menu._MENU_CACHE.update({"t": 9e9, "v": ["vieux"]})
    admin_menu.app.test_client().put("/api/parametres/menu",
                                     json={"entrees": [{"chemin": "/stock"}]})
    assert admin_menu._MENU_CACHE["v"] is None


def test_une_base_injoignable_ne_vide_pas_la_navigation(admin_menu, monkeypatch):
    """
    ⚠️ LE MENU S'AFFICHE SUR TOUTES LES PAGES. S'il dépendait d'une lecture Supabase réussie, un
    hoquet réseau viderait la navigation de tout le site — y compris la page qui sert à réparer.
    """
    def boum(*a, **k):
        raise RuntimeError("réseau")
    monkeypatch.setattr(admin_menu, "_supa_get", boum)
    admin_menu._MENU_CACHE["v"] = None
    structure = admin_menu._menu_courant()
    assert [e["chemin"] for g in structure for e in g["entrees"]] == \
        [e["chemin"] for e in menu.CATALOGUE]


@_pt.mark.parametrize("role", [None, "investor", "staff", "accountant"])
def test_seul_ladmin_reorganise_le_menu(monkeypatch, role):
    import app as flask_app
    monkeypatch.setattr(flask_app, "_current_role", lambda: role)
    flask_app.app.config["TESTING"] = True
    c = flask_app.app.test_client()
    assert c.get("/api/parametres/menu").status_code in (401, 403)
    assert c.put("/api/parametres/menu", json={"entrees": [{"chemin": "/"}]}).status_code in (401, 403)
    assert c.post("/api/parametres/menu/defaut").status_code in (401, 403)


def test_lecran_de_reglage_ne_recopie_pas_la_liste_des_pages():
    """
    ⚠️ DEUX INVENTAIRES À TENIR D'ACCORD, C'EST UN QUI SE PÉRIME. Une page ajoutée au code
    apparaîtrait dans le menu et manquerait dans l'écran qui sert à le ranger — ou l'inverse.
    """
    g = open("templates/parametres.html", encoding="utf-8").read()
    # ⚠️ ON N'INSPECTE QUE LE PANNEAU ET SON SCRIPT. La page entière contient des renvois
    # légitimes vers d'autres écrans (« Ouvrir Charges fixes → ») : les compter comme des
    # recopies du catalogue rendrait ce test faux pour la seule raison qu'un lien existe.
    zone = g[g.index('id="pa-menu"'):g.index("<!-- /menu -->")] \
        + g[g.index("var MENU = {"):]   # ⚠️ jusqu'à la fin : `activer(location.hash` apparaît
                                       # AUSSI plus haut, et la tranche se refermait avant
                                       # d'avoir commencé — un test vide passe toujours.
    assert "/api/parametres/menu" in zone, "l'écran n'obtient pas la liste du serveur"
    for e in menu.CATALOGUE:
        assert f'"{e["chemin"]}"' not in zone, \
            f"{e['chemin']} est recopié dans l'écran de réglage"
