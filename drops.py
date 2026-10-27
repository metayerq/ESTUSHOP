"""
LES PRÉCOMMANDES DES CHEFS EN RÉSIDENCE — CE QUE LE BUREAU EN DÉCIDE.

Une OPÉRATION = un chef, un menu, une période (un soir, tous les jeudis d'un mois, une semaine
d'affilée). Elle a des SOIRÉES, et pour chaque soirée et chaque plat deux stocks : en
précommande, et sur place. Les tables sont dans `docs/sql/drop_precommandes.sql` (dépôt Mesa).

⚠️ DEUX ENDROITS, DEUX MÉTIERS, AUCUNE RÈGLE EN DOUBLE. La caisse Mesa VEND : créneaux, stock
restant, panier, paiement, facture (`lib/drop/regles.ts`, `lib/server/dropMoteur.ts`). Ce module
PRÉPARE ET COMPTE : les dates des soirées, ce qui empêche d'ouvrir, le bilan du chef. Aucune
fonction ici n'existe là-bas, et inversement — deux copies d'une règle finissent toujours par
dire deux choses.

⚠️ ESTUDANTINA VEND, LE CHEF FACTURE SA PART. Toute vente — en ligne ou au comptoir — part sur
une facture Vendus d'Estudantina ; le chef facture ensuite l'encaissé moins la commission,
prise sur le TTC.

⚠️ TOUT EST EN CENTIMES. 4,5 × 3 en flottants donne 13,499999…, et une commission arrondie sur
ce nombre-là ne tombe pas juste au centime près du chef.
"""

import re
import unicodedata
from datetime import date, timedelta

ETABLISSEMENT = "estudantina"

# Au-delà, c'est une faute de frappe (2027 au lieu de 2026), pas une résidence.
MAX_SOIREES = 62

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

_SLUG = re.compile(r"^[a-z0-9-]{3,60}$")
_HEURE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DropInvalide(ValueError):
    """Ce qui a été saisi ne décrit pas une opération valable : on le dit, on n'écrit rien."""


def slug(texte, maxi=60):
    """« Salmon & shiso onigiri » → « salmon-shiso-onigiri »."""
    t = unicodedata.normalize("NFD", texte or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:maxi].strip("-")


def identifiant_valide(op):
    return bool(_SLUG.match(op or ""))


def _jour(v):
    try:
        return date.fromisoformat(str(v or ""))
    except ValueError:
        raise DropInvalide(f"date illisible : {v!r}")


def jours_de_l_operation(duree):
    """
    Les dates des soirées, dans l'ordre.

    `duree` : {"kind": "unique", "jour"} · {"kind": "hebdo", "debut", "fin", "jours": [0..6]}
    · {"kind": "plage", "debut", "fin"}. 0 = lundi, comme `weekday()`.
    """
    kind = (duree or {}).get("kind")
    if kind == "unique":
        return [_jour(duree.get("jour"))]
    if kind not in ("hebdo", "plage"):
        raise DropInvalide("durée illisible")
    debut, fin = _jour(duree.get("debut")), _jour(duree.get("fin"))
    if fin < debut:
        raise DropInvalide("la fin précède le début")
    semaine = None
    if kind == "hebdo":
        try:
            semaine = {int(j) for j in duree.get("jours") or []}
        except (TypeError, ValueError):
            raise DropInvalide("jours de la semaine illisibles")
        if not semaine or not semaine <= set(range(7)):
            raise DropInvalide("choisis au moins un jour de la semaine")
    out, j = [], debut
    while j <= fin:
        if semaine is None or j.weekday() in semaine:
            out.append(j)
            if len(out) > MAX_SOIREES:
                raise DropInvalide(f"plus de {MAX_SOIREES} soirées — vérifie les dates")
        j += timedelta(1)
    if not out:
        raise DropInvalide("aucune soirée dans cette période")
    return out


# Les heures par défaut d'une soirée : le chef a le shop de 18 h à 23 h.
SOIREE_DEFAUT = {
    "ouvre": "18:00", "ferme": "23:00",
    "retrait_debut": "18:30", "retrait_fin": "22:30",
    "pas_minutes": 15, "capacite_creneau": 6,
    "limite": "16:00", "bascule_sur_place": True,
}


def soiree_propre(brut):
    """
    Les réglages d'une soirée, vérifiés. Les champs absents prennent leur valeur par défaut.

    ⚠️ LES MÊMES CONTRAINTES QUE LA BASE, DITES EN FRANÇAIS. La base refuserait de toute façon
    un retrait qui finit avant de commencer ; mais elle le dirait en anglais technique, et
    l'écran afficherait « violates check constraint » à la place d'une phrase.
    """
    s = {**SOIREE_DEFAUT, **{k: v for k, v in (brut or {}).items() if k in SOIREE_DEFAUT}}
    for k in ("ouvre", "ferme", "retrait_debut", "retrait_fin", "limite"):
        s[k] = str(s[k] or "")[:5]
        if not _HEURE.match(s[k]):
            raise DropInvalide(f"heure illisible : {s[k]!r}")
    if s["ouvre"] >= s["ferme"]:
        raise DropInvalide("le shop doit ouvrir avant de fermer")
    if s["retrait_debut"] >= s["retrait_fin"]:
        raise DropInvalide("le retrait doit commencer avant de finir")
    try:
        s["pas_minutes"] = int(s["pas_minutes"])
        s["capacite_creneau"] = int(s["capacite_creneau"])
    except (TypeError, ValueError):
        raise DropInvalide("pas ou capacité illisible")
    if s["pas_minutes"] not in (10, 15, 20, 30):
        raise DropInvalide("un créneau dure 10, 15, 20 ou 30 minutes")
    if s["capacite_creneau"] < 1:
        raise DropInvalide("un créneau prend au moins une commande")
    s["bascule_sur_place"] = bool(s["bascule_sur_place"])
    return s


def empechements(plats, prix_vendus, soirees):
    """
    Ce qui empêche d'ouvrir les précommandes. Vide = on peut ouvrir.

    `prix_vendus` : {id produit Vendus: prix TTC en euros}.

    ⚠️ LE PRIX DU MENU ET CELUI DE VENDUS DOIVENT ÊTRE LE MÊME. Le client paie le prix du menu ;
    la facture part au prix Vendus. Un centime d'écart, et le document fiscal ne correspond plus
    à l'argent encaissé.
    """
    out = []
    actifs = [p for p in plats if p.get("actif", True)]
    if not actifs:
        out.append("Le menu est vide")
    if not soirees:
        out.append("Aucune soirée prévue")
    for p in actifs:
        pid = p.get("vendus_product_id")
        if pid in (None, ""):
            out.append(f"{p['nom']} : pas de produit Vendus")
            continue
        prix = prix_vendus.get(int(pid))
        if prix is None:
            out.append(f"{p['nom']} : produit Vendus {pid} introuvable")
        elif round(float(prix) * 100) != int(p["prix_cents"]):
            out.append(f"{p['nom']} : prix du menu {int(p['prix_cents']) / 100:.2f} € "
                       f"≠ prix Vendus {float(prix):.2f} €")
    return out


ENCAISSEES = {"payee", "prete", "retiree"}


def bilan(commandes, ventes_sur_place, commission_pct):
    """
    Le bilan d'une opération, en centimes.

    ⚠️ LA COMMISSION SE PREND SUR LE TTC — un choix d'Estudantina, pas une règle fiscale. Une
    commande remboursée, refusée ou jamais payée n'a rien rapporté et n'entre nulle part.

    ⚠️ ARRONDIE AU CENTIME, ET LA PART DU CHEF EST LE RESTE. Arrondir les deux séparément peut
    créer ou perdre un centime ; leur somme doit retomber exactement sur l'encaissé.
    """
    en_ligne = sum(int(c["total_cents"]) for c in commandes if c.get("statut") in ENCAISSEES)
    sur_place = sum(int(q) * int(p) for q, p in ventes_sur_place)
    encaisse = en_ligne + sur_place
    # En entiers, au plus proche, demi vers le haut : ni l'arrondi bancaire de `round()`, ni
    # le 1206,4999… d'un produit de flottants. Le taux est en centièmes de pour cent.
    taux = int(round(float(commission_pct) * 100))
    commission = (encaisse * taux + 5000) // 10000
    return {
        "en_ligne_cents": en_ligne,
        "sur_place_cents": sur_place,
        "encaisse_cents": encaisse,
        "commission_cents": commission,
        "part_chef_cents": encaisse - commission,
    }
