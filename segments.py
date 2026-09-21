"""
DÉCOUPER LA JOURNÉE : LE SERVICE DE JOUR, LE SERVICE DU SOIR.

⚠️ UN ÉVÉNEMENT DU SOIR FAUSSE LA COMPARAISON DES JOURS. Un concert un vendredi ajoute
quarante tickets à ce vendredi-là ; la médiane du vendredi monte, et l'on conclut que le
vendredi se tient mieux que le jeudi. C'est l'événement qu'on mesure, pas le café.

⚠️ LA MESURE PAR HEURE PORTE LES TICKETS, PAS L'ARGENT. Le cache compte les passages en caisse
heure par heure (`hours`), mais le chiffre d'affaires est stocké par JOUR. Tout ce qui dérive
du CA — panier, CA par personne — ne peut donc PAS être découpé. Les mêler à des tickets
filtrés donnerait « ils viennent moins en journée ET dépensent moins », une lecture que la
donnée ne porte pas : ces chiffres se taisent dans les vues filtrées, et disent pourquoi.

⚠️ ET UN JOUR SANS MESURE HORAIRE N'EST PAS UN JOUR SANS SOIRÉE. Les lignes de cache écrites
avant l'existence du champ `hours` n'ont pas « zéro ticket le soir », elles n'ont pas la
mesure. Les compter à zéro ferait chuter toutes les médianes du soir — et la chute serait
d'autant plus forte que l'historique est ancien, ce qui ressemblerait exactement à une
tendance. Ces jours sont ÉCARTÉS, et l'écran dit combien.
"""

# Les bornes sont celles de la répartition horaire de la page — une seule définition du
# « soir » dans tout le dépôt. Deux constantes qui dérivent, et le bloc « soir » du graphique
# cesserait de correspondre au filtre qui prétend l'exclure.
SOIR_DEBUT = 19
SOIR_FIN = 23

SEGMENTS = ("day", "evening", "all")
SEGMENT_DEFAUT = "day"


def normaliser(brut):
    """
    Le segment demandé, ou celui par défaut.

    ⚠️ LE DÉFAUT EXCLUT LE SOIR, ET C'EST UN CHOIX QUI SE DÉFEND. Comparer des jours entre eux
    est l'usage courant de la page ; les soirées d'événement sont l'exception qui la fausse.
    Un défaut qui inclut tout donnerait raison à l'exception.
    """
    return brut if brut in SEGMENTS else SEGMENT_DEFAUT


def _dans_segment(heure, segment):
    if segment == "all":
        return True
    soir = SOIR_DEBUT <= heure <= SOIR_FIN
    return not soir if segment == "day" else soir


def tickets_du_segment(heures, segment):
    """
    Les tickets d'un jour pour ce segment, ou `None` si le jour n'est pas instrumenté.

    ⚠️ `None` N'EST PAS `0`. Un jour sans dict `hours` n'a pas zéro ticket le soir : on ne sait
    pas. L'appelant doit l'ÉCARTER, pas l'additionner.
    """
    if segment == "all":
        return None            # rien à recalculer : le total du jour fait foi
    if not isinstance(heures, dict):
        return None
    total = 0
    for h, n in heures.items():
        try:
            hi = int(h)
        except (TypeError, ValueError):
            continue
        if 0 <= hi <= 23 and _dans_segment(hi, segment):
            total += int(n or 0)
    return total


def appliquer(records, segment):
    """
    Réécrit les jours pour ne garder que le segment demandé.

    Renvoie `(jours, ecartes)` : les jours retenus, et le nombre de jours écartés faute de
    mesure horaire. Un jour dont le segment est VIDE (aucun ticket le soir) est conservé à 0 —
    c'est une mesure, pas une absence : ce soir-là, personne n'est venu.

    ⚠️ LE CA ET LES PERSONNES PASSENT À `None`, ILS NE SONT PAS RECOPIÉS. Les laisser tels
    quels attacherait le CA de la JOURNÉE ENTIÈRE à un compte de tickets filtré — et le panier
    qu'on en tirerait serait faux d'un facteur deux, sans que rien ne le signale.
    """
    if segment == "all":
        return list(records), 0

    gardes, ecartes = [], 0
    for r in records:
        nb = tickets_du_segment(r.get("hours"), segment)
        if nb is None:
            ecartes += 1
            continue
        # ⚠️ `hours` DISPARAÎT AVEC LE RESTE, ET POUR LA MÊME RAISON QUE LE CA. C'est une
        # mesure de la JOURNÉE ENTIÈRE ; la laisser sur un jour filtré ferait dessiner la
        # répartition horaire complète à partir de jours qui prétendent ne contenir que le
        # matin. Tant qu'elle restait là, la règle « la répartition horaire n'est jamais
        # filtrée » était vraie par accident — les deux calculs tombaient sur le même
        # résultat, et la supprimer ne cassait rien. Un garde-fou qu'aucun chemin n'atteint
        # donne l'illusion d'une protection.
        gardes.append({**r, "nb": nb, "ca_ttc": None, "covers": None, "hours": None,
                       "covers_capped": 0, "covers_measured": 0, "covers_estimated": 0,
                       "multi_count": None, "segment": segment})
    return gardes, ecartes
