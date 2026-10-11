# -*- coding: utf-8 -*-
"""
LA MARGE D'UN CAFÉ, AU GRAIN QU'ON A VRAIMENT SERVI CE JOUR-LÀ.

⚠️ ON NE REMPLACE PAS LA RECETTE, ON REMPLACE LE PRIX DU GRAIN. Une recette dit « un espresso,
c'est 18 g de café » — ça ne change pas selon le lot. Ce qui change, c'est ce que ces 18 g
coûtent : 24,50 €/kg un jour, 31 € le lendemain. Toucher aux quantités reviendrait à réécrire
la recette pour une raison de prix.

⚠️ ET LE PRIX EST CELUI FIGÉ LE JOUR DU CHOIX, pas celui d'aujourd'hui. Relire le prix courant
ferait bouger la marge d'une journée déjà close chaque fois qu'un lot renchérit — exactement ce
que le versionnement des charges existe pour empêcher.

⚠️ LE RATTACHEMENT VENTE → MÉTHODE SE FAIT SUR LE TITRE, ET IL EST FAILLIBLE. « Flat white »
relève de l'espresso, « V60 » du V60, mais aucun catalogue ne le dit formellement. On rend donc
TOUJOURS la liste de ce qui a été rattaché et de ce qui ne l'a pas été : un produit tombé dans
le mauvais panier déplace une marge sans que rien ne le signale, et un produit oublié la fait
simplement disparaître.
"""
from collections import defaultdict

#: Les mots qui rattachent un produit vendu à une méthode d'extraction.
#:
#: ⚠️ CE SONT DES INDICES, PAS UNE VÉRITÉ. Ils viennent du vocabulaire d'un comptoir, pas d'un
#: champ de la base. C'est pourquoi le résultat les expose : on doit pouvoir constater qu'un
#: « cortado » a bien été compté en espresso — ou corriger la liste.
MOTS = {
    "espresso": ("espresso", "latte", "cappuccino", "flat white", "americano",
                 "cortado", "macchiato", "mocha", "piccolo"),
    "batch": ("batch", "filter coffee", "cafe filtre", "café filtre"),
    "v60": ("v60", "v 60", "pour over", "pour-over"),
}

METHODES = tuple(MOTS)


def _sans_accent(s):
    paires = (("à", "a"), ("â", "a"), ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
              ("î", "i"), ("ï", "i"), ("ô", "o"), ("ù", "u"), ("û", "u"), ("ç", "c"))
    out = str(s or "").lower()
    for a, b in paires:
        out = out.replace(a, b)
    return out


def methode_du_produit(titre):
    """La méthode qu'un titre de produit désigne, ou `None` si rien ne la nomme."""
    plat = _sans_accent(titre)
    for methode, mots in MOTS.items():
        for m in mots:
            if _sans_accent(m) in plat:
                return methode
    return None


def repartir(ventes):
    """
    Les ventes rangées par méthode, et celles qu'aucun mot ne rattache.

    ⚠️ LES NON RATTACHÉES SONT RENDUES, PAS IGNORÉES. Un produit café oublié ici verrait son
    grain facturé au prix courant de l'ingrédient au lieu de celui du jour — un écart petit,
    permanent, et invisible.
    """
    par_methode = {m: {} for m in METHODES}
    hors = {}
    for titre, qty in (ventes or {}).items():
        m = methode_du_produit(titre)
        if m is None:
            hors[titre] = qty
        else:
            par_methode[m][titre] = qty
    return par_methode, hors


def est_un_cafe(nom, ingr_lib):
    """Un ingrédient est un café si sa catégorie le dit — même règle que l'écran de la caisse."""
    cat = _sans_accent(((ingr_lib or {}).get(nom) or {}).get("category"))
    return "cafe" in cat or "coffee" in cat or "grain" in cat


def cout_du_grain(quantites, ingr_lib, prix_du_jour):
    """
    Ce que le café a coûté dans cette consommation, au prix du jour ET au prix courant.

    `quantites` : {ingrédient → quantité consommée}, déjà dépliée par `consommation_theorique`.
    `prix_du_jour` : le prix figé du grain choisi, ou `None` s'il n'y en a pas.

    Rend `(au_jour, au_courant, grains)` — `au_jour` vaut `None` quand aucun prix du jour n'est
    connu : zéro se lirait « le café n'a rien coûté ».
    """
    grains = {n: q for n, q in (quantites or {}).items() if est_un_cafe(n, ingr_lib)}
    if not grains:
        return None, 0.0, {}

    courant = 0.0
    for nom, q in grains.items():
        try:
            courant += float(((ingr_lib or {}).get(nom) or {}).get("price") or 0) * float(q)
        except (TypeError, ValueError):
            continue
    if prix_du_jour is None:
        return None, round(courant, 4), grains
    total_q = 0.0
    for q in grains.values():
        try:
            total_q += float(q)
        except (TypeError, ValueError):
            continue
    return round(float(prix_du_jour) * total_q, 4), round(courant, 4), grains


def journee(ventes, choix, consommation, ingr_lib):
    """
    Ce que le café a coûté ce jour-là, méthode par méthode.

    `choix` : {méthode → {"ingredient", "prix"}} — le grain posé sur la caisse ce matin-là.
    `consommation` : une fonction `{titre → qty} → {ingrédient → quantité}`, c'est-à-dire
    `consommation_theorique` déjà liée à ses recettes. L'injecter évite à ce module de
    connaître les recettes, et permet de l'éprouver sans base.
    """
    par_methode, hors = repartir(ventes)
    lignes = {}
    for m in METHODES:
        v = par_methode[m]
        c = (choix or {}).get(m) or {}
        quantites = consommation(v) if v else {}
        au_jour, au_courant, grains = cout_du_grain(quantites, ingr_lib, c.get("prix"))
        lignes[m] = {
            "grain": c.get("ingredient"),
            "prix_du_jour": c.get("prix"),
            "produits": sorted(v),
            "unites": round(sum(float(q or 0) for q in v.values()), 2),
            "grammes": {n: round(float(q), 4) for n, q in grains.items()},
            "cout_au_jour": au_jour,
            "cout_au_prix_courant": au_courant,
            # ⚠️ L'ÉCART EST CE QU'ON VIENT CHERCHER : ce que le grain du jour coûte DE PLUS
            # (ou de moins) que le prix de référence de l'ingrédient.
            "ecart": (None if au_jour is None else round(au_jour - au_courant, 4)),
        }
    return {"methodes": lignes, "hors_methode": sorted(hors)}
