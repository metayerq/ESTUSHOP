"""
LA VARIANCE — L'ÉCART ENTRE CE QU'ON A CONSOMMÉ ET CE QU'ON AURAIT DÛ.

    réelle    = stock d'ouverture + achats de la période − stock de clôture
    théorique = Σ (quantités vendues × quantité de la recette)
    variance  = réelle − théorique

⚠️ CE MODULE EST LE MIROIR EXACT DE `calc_recipe_cogs`, EN QUANTITÉS AU LIEU DE COÛTS. Même
table de conversions, même traitement des préparations sur un seul niveau, même facteur de
rendement. Toute divergence entre les deux ferait dire au COGS et à la variance deux choses
différentes sur la même recette — et il serait impossible de savoir laquelle a tort.

⚠️ ET UNE VARIANCE NE SE CALCULE QUE SUR CE QUI A ÉTÉ COMPTÉ DEUX FOIS. Un ingrédient compté à
l'ouverture mais oublié à la clôture n'a pas « tout été consommé » : il n'a pas été regardé.
L'inclure produirait une variance énorme sur exactement les lignes qu'on n'a pas vérifiées.
"""

from collections import defaultdict


def quantites_recette(ingredients, ingr_lib, prep_lib=None, _profondeur=0):
    """
    Ce qu'une portion d'un produit consomme, par ingrédient, dans l'unité de RÉFÉRENCE.

    Rend `(quantites, avertissements)`. Une conversion inconnue n'est pas silencieuse : elle
    remonte, parce qu'une ligne ignorée sous-estime la consommation théorique et gonfle donc
    la variance — c'est-à-dire qu'elle accuse la cuisine d'un gaspillage qui n'existe pas.
    """
    from app import UNIT_CONVERSIONS, prep_yield_factor

    qtes = defaultdict(float)
    avertissements = []

    for ing in ingredients or []:
        nom = ing.get("name")
        try:
            qty = float(ing.get("qty") or 0)
        except (TypeError, ValueError):
            avertissements.append(f"{nom} : quantité illisible")
            continue
        unit = ing.get("unit")

        # ── Cas 1 : ingrédient du référentiel ────────────────────────────────
        item = (ingr_lib or {}).get(nom)
        if item:
            unit_ref = item.get("unit_ref")
            facteur = UNIT_CONVERSIONS.get((unit, unit_ref))
            if facteur is None:
                avertissements.append(f"{nom} : conversion {unit}→{unit_ref} inconnue")
                continue
            qtes[nom] += qty * facteur
            continue

        # ── Cas 2 : préparation, un seul niveau ──────────────────────────────
        prep = (prep_lib or {}).get(nom)
        if prep and _profondeur == 0:
            interne, avert_int = quantites_recette(
                prep.get("ingredients"), ingr_lib, prep_lib=None, _profondeur=1)
            avertissements.extend(avert_int)
            try:
                rendement = float(prep.get("yield_qty") or 1)
            except (TypeError, ValueError):
                rendement = 1
            if rendement == 0:
                avertissements.append(f"{nom} : rendement nul")
                continue
            # ⚠️ LE FACTEUR DE RENDEMENT, SANS QUOI C'EST UN FACTEUR 1000. Une ligne en « 200 ml »
            # d'une préparation qui rend « 1 l » vaut 0,2 lot, pas 200. Le moteur de coût s'est
            # déjà fait piéger ici ; on appelle donc la MÊME fonction, jamais une copie.
            yf, avert = prep_yield_factor(unit, prep.get("yield_unit", "portion"))
            if avert:
                avertissements.append(f"{nom} : {avert}")
            lots = qty * yf / rendement
            for k, v in interne.items():
                qtes[k] += v * lots
            continue

        avertissements.append(f"{nom} : ni ingrédient ni préparation connus")

    return dict(qtes), avertissements


def consommation_theorique(ventes, recipes, ingr_lib, prep_lib=None):
    """
    `ventes` : {titre du produit Vendus → quantité vendue}.
    Rend `(par_ingredient, sans_recette, avertissements)`.

    ⚠️ LES PRODUITS SANS RECETTE SONT RENDUS À PART, PAS IGNORÉS. Vendre cent cafés dont la
    recette n'est pas écrite ferait apparaître tout le café consommé comme du gaspillage. Il faut
    pouvoir dire « la variance ne couvre que 62 % du chiffre d'affaires » plutôt que d'afficher
    un écart qui accuse à tort.
    """
    par_ingredient = defaultdict(float)
    sans_recette = []
    avertissements = []

    for titre, qty in (ventes or {}).items():
        recette = (recipes or {}).get((titre or "").strip())
        if not recette or not recette.get("ingredients"):
            sans_recette.append(titre)
            continue
        unitaire, avert = quantites_recette(recette["ingredients"], ingr_lib, prep_lib)
        for nom, q in unitaire.items():
            par_ingredient[nom] += q * float(qty or 0)
        avertissements.extend(f"{titre} → {a}" for a in avert)

    return dict(par_ingredient), sans_recette, avertissements


def _prix(ingr_lib, nom):
    """Le prix de l'unité de référence, ou `None` s'il est inconnu ou absurde."""
    item = (ingr_lib or {}).get(nom) or {}
    try:
        prix = float(item.get("price"))
    except (TypeError, ValueError):
        return None
    return prix if prix > 0 else None


def valoriser(lignes, theorique, ingr_lib):
    """
    MET DES EUROS SUR LES ÉCARTS — sans quoi la variance n'est pas exploitable.

    ⚠️ UN POURCENTAGE SUR DEUX JOURS MENT PAR CONSTRUCTION. Compter trois fois par semaine rend
    les quantités petites, donc les pourcentages énormes : +12 % sur le persil, c'est 40
    centimes ; +3 % sur le café, c'est 15 €. Un tableau classé par pourcentage envoie le
    comptoir courir après le persil trois fois par semaine.

    ⚠️ ET LE CLASSEMENT EN QUANTITÉ COMPARE DES CHOSES INCOMPARABLES. « 2 » de farine (kg) et
    « 2 » de lait (l) et « 2 » de citrons (unités) n'ont pas le même poids dans une marge. Seul
    l'euro met tous les ingrédients sur la même échelle.

    ⚠️ ON VALORISE AUX MÊMES QUANTITÉS QUE LA VARIANCE, PAS AVEC `calc_recipe_cogs`. Ce dernier
    applique le `waste_pct` des recettes — une perte SUPPOSÉE. L'additionner à une perte MESURÉE
    compterait le gaspillage deux fois. Ici le théorique est le pur besoin des recettes, et
    l'écart est ce que la réalité ajoute par-dessus.

    Rend `(lignes, totaux)`. Une ligne sans prix connu garde ses quantités et porte
    `cout_ecart: None` — jamais zéro : « gratuit » et « on ne sait pas » sont deux faits opposés.
    """
    valorisees = []
    cout_ecart = 0.0
    cout_theorique_couvert = 0.0
    sans_prix = []

    for l in lignes or []:
        prix = _prix(ingr_lib, l["ingredient"])
        if prix is None:
            sans_prix.append(l["ingredient"])
            valorisees.append({**l, "prix_ref": None, "cout_ecart": None, "cout_theorique": None})
            continue
        ce = l["ecart"] * prix
        ct = l["theorique"] * prix
        cout_ecart += ce
        cout_theorique_couvert += ct
        valorisees.append({**l, "prix_ref": round(prix, 4),
                           "cout_ecart": round(ce, 2), "cout_theorique": round(ct, 2)})

    # Le besoin théorique de TOUS les ingrédients, comptés ou non : c'est le dénominateur de la
    # couverture, et le socle du COGS réel.
    cout_theorique_total = 0.0
    theorique_sans_prix = []
    for nom, q in (theorique or {}).items():
        prix = _prix(ingr_lib, nom)
        if prix is None:
            theorique_sans_prix.append(nom)
            continue
        cout_theorique_total += q * prix

    # ⚠️ ON TRIE PAR EUROS DÈS QU'ON LE PEUT. Le tri par quantité mettait « 2 kg de farine » et
    # « 2 unités de citron » sur la même ligne d'importance ; seul l'euro les compare.
    valorisees.sort(
        key=lambda l: (l["cout_ecart"] is None, -abs(l["cout_ecart"] or 0), -abs(l["ecart"])))

    totaux = {
        # Ce que les recettes exigeaient, tous ingrédients confondus.
        "cogs_theorique": round(cout_theorique_total, 2),
        # La part de ce besoin qui a été RÉELLEMENT mesurée par deux comptages.
        "cogs_theorique_couvert": round(cout_theorique_couvert, 2),
        "couverture_pct": (round(cout_theorique_couvert / cout_theorique_total * 100, 1)
                           if cout_theorique_total else None),
        # Le coût de l'écart : positif = consommé au-delà des recettes.
        "cout_ecart": round(cout_ecart, 2),
        # ⚠️ UN PLANCHER, PAS UNE VÉRITÉ. L'écart n'est mesuré que sur les ingrédients comptés
        # deux fois ; ce qui n'a pas été compté ne peut pas avoir d'écart, donc le coût réel est
        # au MOINS celui-ci. C'est pour ça que la couverture s'affiche à côté du chiffre.
        "cogs_reel": round(cout_theorique_total + cout_ecart, 2),
        "sans_prix": sorted(set(sans_prix)),
        "theorique_sans_prix": sorted(set(theorique_sans_prix)),
    }
    return valorisees, totaux


def marge_reelle(ca_ht, totaux):
    """
    La marge que les recettes promettaient, et celle qu'on a vraiment faite.

    ⚠️ LE CHIFFRE D'AFFAIRES EST HORS TAXES, PARCE QUE LE COGS L'EST. Comparer un coût HT à un
    encaissement TTC gonfle la marge de la TVA — 13 % sur la restauration au Portugal, soit
    exactement l'ordre de grandeur de la casse qu'on cherche à mesurer.
    """
    try:
        ca = float(ca_ht or 0)
    except (TypeError, ValueError):
        ca = 0.0
    if ca <= 0:
        return {"ca_ht": 0.0, "marge_theorique_pct": None, "marge_reelle_pct": None,
                "perte_pct_ca": None}
    th = totaux.get("cogs_theorique") or 0.0
    re_ = totaux.get("cogs_reel") or 0.0
    ec = totaux.get("cout_ecart") or 0.0
    return {
        "ca_ht": round(ca, 2),
        "marge_theorique_pct": round((ca - th) / ca * 100, 1),
        "marge_reelle_pct": round((ca - re_) / ca * 100, 1),
        # Ce que la casse coûte, rapporté au chiffre : le chiffre qu'on suit dans le temps.
        "perte_pct_ca": round(ec / ca * 100, 2),
    }


def variance(reelle, theorique):
    """
    `reelle` : {ingrédient → quantité}, issu des deux comptages et des achats.
    Rend une liste triée par écart décroissant, en valeur absolue.

    ⚠️ ON NE COMPARE QUE LES INGRÉDIENTS PRÉSENTS DANS `reelle`. Un ingrédient théoriquement
    consommé mais absent des comptages n'a pas de réel à lui opposer : l'afficher avec un écart
    négatif ferait croire à un stock qui se remplit tout seul.
    """
    lignes = []
    for nom, r in (reelle or {}).items():
        t = float((theorique or {}).get(nom, 0.0))
        ecart = r - t
        lignes.append({
            "ingredient": nom,
            "reelle": round(r, 4),
            "theorique": round(t, 4),
            "ecart": round(ecart, 4),
            # Le pourcentage n'a de sens que rapporté au théorique : +2 kg sur 4 kg attendus est
            # un problème, +2 kg sur 400 est du bruit.
            "ecart_pct": round(ecart / t * 100, 1) if t else None,
        })
    return sorted(lignes, key=lambda x: abs(x["ecart"]), reverse=True)
