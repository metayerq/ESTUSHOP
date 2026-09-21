"""
LE MENU DE GAUCHE, ET QUI DÉCIDE DE SON ORDRE.

⚠️ LE RANGEMENT ÉTAIT ÉCRIT EN DUR, ET IL AVAIT TORT. « Dépenses » vivait sous « Caisse » alors
que ce sont des achats datés qui alimentent le P&L mensuel, à côté du chiffre d'affaires et des
commissions — rien à voir avec ce que le terminal a encaissé. Une catégorie fausse ne se corrige
pas toute seule : elle apprend à chercher au mauvais endroit, et on finit par ne plus ouvrir la
page du tout.

⚠️ LE CATALOGUE VIENT DU CODE, L'ORGANISATION VIENT DE LA BASE. On ne peut pas inventer une page
depuis les réglages — elle n'existerait pas. On peut en revanche la renommer, la déplacer, la
masquer : c'est le rangement qui est affaire de goût, pas l'inventaire.

⚠️ ET UNE PAGE ABSENTE DE LA CONFIGURATION DOIT APPARAÎTRE QUAND MÊME. C'est le piège de tout
menu configurable : on ajoute une page dans le code, elle n'est dans aucun réglage enregistré,
et elle reste invisible pour toujours. Personne ne cherche un écran dont il ignore l'existence.
Ce module fait donc l'inverse du réflexe : le catalogue est la vérité, la configuration ne fait
que le réordonner.
"""

# ── Le catalogue : tout ce qui existe vraiment ───────────────────────────────────────────────
#
# ⚠️ CES CHEMINS DOIVENT EXISTER DANS `app.py`. Un chemin mort ici, c'est une entrée de menu qui
# mène à une page 404 — `tests/test_menu.py` le vérifie contre la table des routes.
#
# Le libellé et le groupe ne sont que des DÉFAUTS : ils s'appliquent tant que personne n'a rien
# changé, et servent de point de chute aux pages ajoutées plus tard.
CATALOGUE = [
    # Ce que l'affaire a fait.
    {"chemin": "/",               "libelle": "Dashboard",        "groupe": "Pilotage"},
    {"chemin": "/transactions",   "libelle": "Affluence",        "groupe": "Pilotage"},
    {"chemin": "/reconciliation", "libelle": "Réconciliation",   "groupe": "Pilotage"},
    {"chemin": "/contabilidade",  "libelle": "Comptabilité",     "groupe": "Pilotage"},
    {"chemin": "/cashflow",       "libelle": "Trésorerie",       "groupe": "Pilotage"},

    # Ce que l'affaire dépense. ⚠️ « ACHATS » N'EST PAS DE LA CAISSE : ce sont des dépenses
    # datées — fournitures, petit matériel, travaux — qui pèsent sur le mois, pas sur le tiroir.
    {"chemin": "/cogs",           "libelle": "COGS & recettes",  "groupe": "Coûts"},
    {"chemin": "/expenses",       "libelle": "Achats",           "groupe": "Coûts"},
    {"chemin": "/charges",        "libelle": "Charges fixes",    "groupe": "Coûts"},
    {"chemin": "/stock",          "libelle": "Stock",            "groupe": "Coûts"},

    # Qui vient, et à qui l'on parle.
    {"chemin": "/loyalty",        "libelle": "Fidélité",         "groupe": "Clients"},
    {"chemin": "/marketing",      "libelle": "Marketing SMS",    "groupe": "Clients"},
    {"chemin": "/clientes",       "libelle": "Clients Vendus",   "groupe": "Clients"},

    # Faire tourner la maison.
    {"chemin": "/sop",            "libelle": "SOP — checklists", "groupe": "Exploitation"},
    {"chemin": "/holidays",       "libelle": "Congés",           "groupe": "Exploitation"},
    {"chemin": "/events",         "libelle": "Événements",       "groupe": "Exploitation"},
    {"chemin": "/parametres",     "libelle": "Réglages",         "groupe": "Exploitation"},
]

# ⚠️ CETTE PAGE NE PEUT PAS ÊTRE MASQUÉE. C'est celle qui contient le réglage du menu : la
# masquer fermerait la porte de l'intérieur, avec la clé restée dedans.
INDISPENSABLES = {"/parametres"}

# Les pages qui portent une pastille d'alerte. Le rail les connaît par leur chemin, pas par
# leur libellé — un poste renommé garde donc son compteur.
PASTILLES = {"/reconciliation": "rail-ecarts"}


def _propre(v, defaut=""):
    v = (v or "").strip() if isinstance(v, str) else ""
    return v or defaut


def construire(config=None):
    """
    Le menu tel qu'il doit s'afficher : une liste de groupes, chacun avec ses entrées.

    `config` est ce qui a été enregistré — une liste d'entrées `{chemin, libelle, groupe,
    masque}` dans l'ordre voulu, et rien d'autre. Tout ce qui n'y est pas retombe sur le
    catalogue ; tout ce qui n'est plus dans le catalogue est ignoré.
    """
    par_chemin = {e["chemin"]: e for e in CATALOGUE}
    vus = set()
    entrees = []

    for e in config or []:
        chemin = _propre(e.get("chemin") if isinstance(e, dict) else None)
        # ⚠️ UN CHEMIN INCONNU EST IGNORÉ, PAS AFFICHÉ. Une page retirée du code laisserait
        # sinon une entrée qui mène à un 404 — et on chercherait la panne dans la page absente
        # plutôt que dans le réglage qui la nomme encore.
        if chemin not in par_chemin or chemin in vus:
            continue
        socle = par_chemin[chemin]
        vus.add(chemin)
        masque = bool(e.get("masque")) and chemin not in INDISPENSABLES
        entrees.append({
            "chemin":  chemin,
            "libelle": _propre(e.get("libelle"), socle["libelle"]),
            "groupe":  _propre(e.get("groupe"), socle["groupe"]),
            "masque":  masque,
            "pastille": PASTILLES.get(chemin),
        })

    # ⚠️ LE RESTE DU CATALOGUE SUIT, VISIBLE. C'est le garde-fou central : une page ajoutée au
    # code apparaît sans qu'on ait à toucher aux réglages. L'oubli inverse — ajouter la page et
    # oublier le réglage — donnerait un écran que personne ne trouve jamais.
    for socle in CATALOGUE:
        if socle["chemin"] not in vus:
            entrees.append({**socle, "masque": False,
                            "pastille": PASTILLES.get(socle["chemin"])})

    # Les groupes prennent l'ordre de leur première entrée visible.
    groupes, ordre = {}, []
    for e in entrees:
        if e["masque"]:
            continue
        if e["groupe"] not in groupes:
            groupes[e["groupe"]] = []
            ordre.append(e["groupe"])
        groupes[e["groupe"]].append(e)
    # ⚠️ UN GROUPE NE PEUT PAS ÊTRE VIDE, ET C'EST VOULU : il n'existe que s'il a une entrée
    # visible, puisqu'il est créé PAR elle. Un filtre « si non vide » traînait ici ; il ne
    # pouvait jamais se déclencher, et la mutation qui le retirait ne cassait rien — un
    # garde-fou qu'aucun chemin n'atteint donne l'illusion d'une protection.
    return [{"titre": t, "entrees": groupes[t]} for t in ordre]


def a_plat(config=None):
    """Toutes les entrées, masquées comprises, dans l'ordre — ce que l'écran de réglage édite."""
    connues = {e["chemin"]: e for e in CATALOGUE}
    out, vus = [], set()
    for e in config or []:
        c = _propre(e.get("chemin") if isinstance(e, dict) else None)
        if c not in connues or c in vus:
            continue
        vus.add(c)
        out.append({
            "chemin":  c,
            "libelle": _propre(e.get("libelle"), connues[c]["libelle"]),
            "groupe":  _propre(e.get("groupe"), connues[c]["groupe"]),
            "masque":  bool(e.get("masque")) and c not in INDISPENSABLES,
            "verrouille": c in INDISPENSABLES,
        })
    for socle in CATALOGUE:
        if socle["chemin"] not in vus:
            out.append({**socle, "masque": False,
                        "verrouille": socle["chemin"] in INDISPENSABLES})
    return out
