# -*- coding: utf-8 -*-
"""
CE QU'UN PRODUIT RAPPORTE, JOUR DE SEMAINE PAR JOUR DE SEMAINE.

⚠️ CE MODULE EXISTE POUR UNE DÉCISION, PAS POUR UN TABLEAU DE BORD. « Garde-t-on le brunch en
semaine ? » se tranche sur ce qu'un lundi rapporte RÉELLEMENT, pas sur une moyenne mensuelle qui
mélange les samedis et les mardis.

⚠️ ON DIVISE PAR LES JOURS OÙ LE CAFÉ ÉTAIT OUVERT, PAS PAR LES JOURS OÙ LE PRODUIT S'EST VENDU.
Un sourdough vendu deux lundis sur quatre a une moyenne du lundi de la MOITIÉ de ce qu'il fait
quand il part — et c'est bien cette moitié-là qui entre dans la décision. Diviser par deux
donnerait la performance d'un bon lundi, qui n'est pas la question posée.

⚠️ ET LES TITRES TROUVÉS SONT RENDUS. Chercher « granola » dans un catalogue où l'article
s'appelle « Bowl granola maison » doit pouvoir se vérifier d'un coup d'œil : une recherche qui
ne trouve rien renverrait des zéros, et des zéros se lisent « ça ne se vend pas » — la réponse
exactement inverse de la vérité.
"""
from collections import defaultdict
from datetime import date

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def _sans_accent(s):
    """Pour que « crème » se trouve en tapant « creme »."""
    paires = (("à", "a"), ("â", "a"), ("ä", "a"), ("é", "e"), ("è", "e"), ("ê", "e"),
              ("ë", "e"), ("î", "i"), ("ï", "i"), ("ô", "o"), ("ö", "o"), ("ù", "u"),
              ("û", "u"), ("ü", "u"), ("ç", "c"))
    out = str(s or "").lower()
    for a, b in paires:
        out = out.replace(a, b)
    return out


def _jour(iso):
    try:
        return date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def par_jour_de_semaine(docs, termes):
    """
    Pour chaque terme cherché, ce qu'il fait chaque jour de la semaine.

    `docs` : des documents Vendus détaillés (`date`, `items[{title, qty, amounts}]`).
    `termes` : les mots à chercher dans les titres, sans casse ni accent.

    Rend `{"correspondances", "jours_ouverts", "par_jour"}`.
    """
    cherches = [t for t in (_sans_accent(t).strip() for t in termes or []) if t]
    correspondances = {t: set() for t in cherches}
    jours_ouverts = defaultdict(set)
    brut = defaultdict(lambda: defaultdict(
        lambda: {"qty": 0.0, "rev_ht": 0.0, "dates": set(),
                 # ⚠️ LES QUANTITÉS PAR TITRE, PAS SEULEMENT PAR TERME. « granola » peut
                 # attraper deux articles aux recettes différentes ; un coût de revient
                 # appliqué à la somme des deux serait faux de l'écart entre eux.
                 "par_titre": defaultdict(float)}))

    for d in docs or []:
        j = _jour((d or {}).get("date"))
        if j is None:
            continue
        # ⚠️ UN JOUR COMPTE DÈS QU'UN DOCUMENT EXISTE, même si aucun produit cherché n'y figure.
        # C'est précisément ce qu'on veut : un lundi ouvert sans un seul sourdough est un lundi
        # qui tire la moyenne vers le bas, et c'est l'information qu'on vient chercher.
        jours_ouverts[j.weekday()].add(j.isoformat())
        for it in (d.get("items") or []):
            titre = str(it.get("title") or "").strip()
            plat = _sans_accent(titre)
            for t in cherches:
                if t not in plat:
                    continue
                correspondances[t].add(titre)
                montants = it.get("amounts") or {}
                c = brut[j.weekday()][t]
                try:
                    c["qty"] += float(it.get("qty") or 0)
                    c["rev_ht"] += float(montants.get("net_total")
                                         or it.get("net_total") or 0)
                    c["par_titre"][titre] += float(it.get("qty") or 0)
                except (TypeError, ValueError):
                    continue
                c["dates"].add(j.isoformat())

    par_jour = {}
    for wd in range(7):
        ouverts = len(jours_ouverts.get(wd, ()))
        lignes = {}
        for t in cherches:
            c = brut.get(wd, {}).get(t)
            if c is None:
                lignes[t] = {"qty": 0.0, "rev_ht": 0.0, "jours_vendu": 0, "par_titre": {},
                             "qty_par_jour": 0.0 if ouverts else None,
                             "rev_ht_par_jour": 0.0 if ouverts else None}
                continue
            lignes[t] = {
                "qty": round(c["qty"], 2),
                "rev_ht": round(c["rev_ht"], 2),
                "jours_vendu": len(c["dates"]),
                "par_titre": {t2: round(q, 2) for t2, q in sorted(c["par_titre"].items())},
                # ⚠️ `None` ET NON ZÉRO QUAND LE CAFÉ N'A JAMAIS OUVERT CE JOUR-LÀ. « 0 € le
                # mardi » se lirait « ça ne se vend pas le mardi » alors que le café était fermé.
                "qty_par_jour": round(c["qty"] / ouverts, 2) if ouverts else None,
                "rev_ht_par_jour": round(c["rev_ht"] / ouverts, 2) if ouverts else None,
            }
        par_jour[wd] = {"nom": JOURS[wd], "jours_ouverts": ouverts, "produits": lignes}

    return {
        "correspondances": {t: sorted(v) for t, v in correspondances.items()},
        "jours_ouverts": {wd: len(v) for wd, v in jours_ouverts.items()},
        "par_jour": par_jour,
    }
