"""
LES JOURS ET LES HEURES D'OUVERTURE, DATÉS.

⚠️ UN CALENDRIER QUI CHANGE NE RÉÉCRIT PAS LE PASSÉ. Le café ouvre le mardi à partir du
27/10/2026 ; les mardis de juin à octobre, eux, sont restés fermés. Remplacer simplement la
liste des jours ouverts ferait compter vingt mardis de plus dans l'historique : les charges de
chaque mois passé seraient redivisées, le coût par jour baisserait partout, et le planning
afficherait des journées « ouvertes » où personne n'est venu. D'où des RÉGIMES, chacun en
vigueur à partir d'une date, comme les charges ont leurs dates de validité.

⚠️ CE MODULE NE LIT RIEN. Il valide et interprète ce qui est enregistré dans `reglages`
(clé `calendrier`) ; `config.py` s'en sert pour `count_open_days_raw`, par où passent les
charges, le planning, les périodes et les moyennes par jour ouvert.

⚠️ ET UNE VALEUR ABÎMÉE N'EST PAS UNE VALEUR PARTIELLE. Un régime illisible ne doit pas en
laisser passer un autre à moitié : le calendrier entier retombe sur celui du code. Un mardi
compté fermé à tort se voit tout de suite au planning ; un calendrier à moitié appliqué, non.
"""

import re
from datetime import date

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

_HEURE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class CalendrierInvalide(ValueError):
    """Ce qui a été envoyé ne décrit pas un calendrier : on le dit, on n'enregistre rien."""


def _heure(v):
    if v in (None, ""):
        return None
    if not isinstance(v, str) or not _HEURE.match(v):
        raise CalendrierInvalide(f"heure illisible : {v!r} (attendu HH:MM)")
    return v


def _regime(brut, bascule):
    if not isinstance(brut, dict):
        raise CalendrierInvalide("régime illisible")
    try:
        depuis = date.fromisoformat(str(brut.get("depuis") or ""))
    except ValueError:
        raise CalendrierInvalide(f"date de début illisible : {brut.get('depuis')!r}")
    if depuis < bascule:
        # Avant la bascule, les jours sont listés un par un (`LAUNCH_OPEN_DAYS`) : un régime
        # hebdomadaire n'y a pas de sens.
        raise CalendrierInvalide(f"un régime ne peut pas commencer avant le {bascule.isoformat()}")
    jours_bruts = brut.get("jours")
    if not isinstance(jours_bruts, dict):
        raise CalendrierInvalide("jours illisibles")
    jours = {}
    for cle, h in jours_bruts.items():
        try:
            wd = int(cle)
        except (TypeError, ValueError):
            raise CalendrierInvalide(f"jour illisible : {cle!r}")
        if not 0 <= wd <= 6:
            raise CalendrierInvalide(f"jour illisible : {cle!r}")
        h = h if isinstance(h, dict) else {}
        ouvre, ferme = _heure(h.get("ouvre")), _heure(h.get("ferme"))
        if ouvre and ferme and ouvre >= ferme:
            raise CalendrierInvalide(f"{JOURS[wd]} : l'ouverture doit précéder la fermeture")
        jours[wd] = {"ouvre": ouvre, "ferme": ferme}
    return {"depuis": depuis, "jours": jours}


def valider(valeur, base):
    """
    Les régimes envoyés, vérifiés et triés. Lève `CalendrierInvalide` sinon.

    `base` est le régime du code (celui qui démarre à la bascule) ; s'il manque un régime à
    cette date, il est remis en tête.

    ⚠️ SANS LUI, LE PREMIER RÉGIME SAISI REMONTERAIT DANS LE PASSÉ. « Mardi ouvert à partir du
    27/10 », enregistré seul, serait le seul régime connu : il s'appliquerait faute de mieux à
    juin, juillet, août… C'est le piège de la première valeur traitée comme si elle avait
    toujours été vraie.
    """
    if not isinstance(valeur, dict) or not isinstance(valeur.get("regimes"), list):
        raise CalendrierInvalide("calendrier illisible")
    regimes = [_regime(r, base["depuis"]) for r in valeur["regimes"]]
    dates = [r["depuis"] for r in regimes]
    if len(set(dates)) != len(dates):
        raise CalendrierInvalide("deux régimes commencent le même jour")
    if base["depuis"] not in dates:
        regimes.append(base)
    return sorted(regimes, key=lambda r: r["depuis"])


def construire(valeur, base):
    """
    Les régimes à appliquer : ceux enregistrés, ou le seul régime du code.

    ⚠️ ABSENT OU ABÎMÉ, C'EST LE CODE QUI FAIT FOI. Même promesse que le menu : un réglage
    absent n'est jamais une panne, et l'on répare une configuration cassée en effaçant sa ligne.
    """
    if valeur is None:
        return [base]
    try:
        return valider(valeur, base)
    except CalendrierInvalide:
        return [base]


def regime_du(jour, regimes):
    """Le régime en vigueur ce jour-là : le dernier commencé, `None` avant le premier."""
    courant = None
    for r in regimes:
        if r["depuis"] <= jour:
            courant = r
        else:
            break
    return courant


def ouvert_selon(jour, regimes):
    r = regime_du(jour, regimes)
    return bool(r) and jour.weekday() in r["jours"]


def horaires_du(jour, regimes):
    """`{"ouvre", "ferme"}` du jour, `None` s'il est fermé. Une heure inconnue vaut `None`."""
    r = regime_du(jour, regimes)
    return r["jours"].get(jour.weekday()) if r else None


def a_plat(regimes):
    """La forme JSON, celle qui s'enregistre et que l'écran affiche."""
    return {"regimes": [
        {"depuis": r["depuis"].isoformat(),
         "jours": {str(wd): dict(h) for wd, h in sorted(r["jours"].items())}}
        for r in regimes]}


def jours_changes(avant, apres, debut, fin):
    """Les dates entre `debut` et `fin` dont l'ouverture diffère d'un calendrier à l'autre."""
    from datetime import timedelta
    out, j = [], debut
    while j <= fin:
        if ouvert_selon(j, avant) != ouvert_selon(j, apres):
            out.append(j)
        j += timedelta(1)
    return out
