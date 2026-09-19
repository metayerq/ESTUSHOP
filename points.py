"""
LES POINTS DE FIDÉLITÉ, CÔTÉ BACKOFFICE — 1 € DÉPENSÉ, 1 POINT ; 50 POINTS, UNE BOISSON.

⚠️ CE FICHIER EST UNE TRADUCTION, PAS UNE INVENTION. L'original vit dans Mesa
(`apps/pos/lib/loyalty.ts`) et c'est lui qui tourne au comptoir. Ici on rejoue exactement le
même calcul, parce que le backoffice doit annoncer le MÊME solde que la caisse et que la page
du client — sans quoi on se retrouve à expliquer à quelqu'un, devant sa tasse, pourquoi trois
écrans lui donnent trois chiffres.

⚠️ ET LA TRADUCTION EST VÉRIFIÉE, PAS PROMISE. `tests/test_points.py` rejoue les vecteurs
produits par l'implémentation TypeScript (`lib/loyalty.vectors.json`, copié à l'identique dans
`tests/vectors/`). Une divergence n'est pas un écart qu'on découvre au comptoir : c'est un test
rouge. C'est la seule chose qui empêche les deux moitiés du programme de dériver l'une de
l'autre — ce qui est précisément arrivé la première fois, en silence, pendant un mois.

── LES FAÇONS DE VOLER DES POINTS À UN CLIENT SANS QUE PERSONNE NE LE VOIE ──────────────────

1. ARRONDIR À CHAQUE TICKET. Un ticket moyen de 9,59 € arrondi à 9 points perd 0,59 € par
   passage : sur les cinq passages qui mènent à la récompense, 6 % des points disparaissent.
   On accumule donc les CENTIMES et on n'arrondit qu'à la lecture.
2. REMETTRE LE COMPTEUR À ZÉRO APRÈS UNE RÉCOMPENSE. Un client à 62 points qui en perd 12 est
   puni d'avoir trop dépensé. On RETRANCHE le seuil ; le reste lui appartient.
3. OUBLIER QU'UNE RÉCOMPENSE PEUT ÊTRE DUE DEUX FOIS. Si personne n'a vu le bandeau pendant un
   mois, une seule boisson accordée fait disparaître l'autre.
4. FAIRE EXPIRER LES MAUVAIS POINTS. Une récompense consomme les points LES PLUS ANCIENS
   d'abord : consommer les récents laisserait périmer ceux qui allaient mourir, et le client
   perdrait deux fois.
"""

import calendar
from datetime import datetime, timezone

# 1 € = 1 point. Le seuil s'exprime en points ; le calcul vit en centimes.
POINTS_PER_EURO = 1

# Les points valent douze mois. Décision de Quentin, 16/09/2026.
EXPIRY_MONTHS = 12

# Fenêtre pendant laquelle on prévient que des points vont périmer.
EXPIRY_WARNING_DAYS = 30

_MS_PAR_JOUR = 86_400_000


def parse_ts(brut):
    """
    Un horodatage ISO en millisecondes depuis l'époque, ou `None` s'il est illisible.

    ⚠️ ÉQUIVALENT DE `Date.parse` CÔTÉ MESA, Y COMPRIS DANS SON REFUS. Une ligne abîmée ne doit
    ni fabriquer de points, ni faire tomber la page : elle est ignorée, et le passage reste
    compté — il a bien eu lieu.

    ⚠️ UN HORODATAGE SANS FUSEAU EST LU EN UTC. Postgres renvoie toujours un `timestamptz`, donc
    le cas ne se présente pas sur nos données ; mais le supposer local ferait dériver les deux
    implémentations d'une à deux heures selon la saison, et l'expiration avec.
    """
    if isinstance(brut, datetime):
        d = brut
    else:
        if not isinstance(brut, str):
            return None
        t = brut.strip()
        if not t:
            return None
        # `fromisoformat` accepte « Z » depuis Python 3.11 ; on le remplace pour les versions
        # antérieures, où il ferait échouer une date pourtant parfaitement valide.
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        try:
            d = datetime.fromisoformat(t)
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def _from_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def to_iso(d):
    """
    Le format exact de `toISOString()` en JavaScript : UTC, millisecondes, « Z ».

    ⚠️ LE FORMAT N'EST PAS COSMÉTIQUE. Les dates d'expiration se comparent comme des CHAÎNES des
    deux côtés (`nextExpiry`) : un format différent, et la comparaison ne veut plus rien dire.
    """
    d = d.astimezone(timezone.utc)
    return f"{d.strftime('%Y-%m-%dT%H:%M:%S')}.{d.microsecond // 1000:03d}Z"


def expires_at(d, months=EXPIRY_MONTHS):
    """
    La date à laquelle des points acquis à l'instant `d` cessent de valoir.

    ⚠️ EN MOIS, PAS EN 365 JOURS. « Douze mois » est ce qu'on annonce au client et ce qu'il
    comprend ; une année bissextile ne doit pas lui retirer un jour. Le jour du mois est ramené
    au dernier jour valide quand il n'existe pas : le 29 février 2024 expire le 28 février 2025.

    ⚠️ LES MILLISECONDES TOMBENT, comme du côté Mesa où `Date.UTC(...)` n'en reçoit pas. Cela ne
    change rien au client, mais un port « amélioré » les garderait et les deux implémentations
    trancheraient différemment une expiration à la milliseconde près.
    """
    d = d.astimezone(timezone.utc)
    total = d.month - 1 + months
    an = d.year + total // 12
    mois = total % 12 + 1
    dernier_du_mois = calendar.monthrange(an, mois)[1]
    return datetime(an, mois, min(d.day, dernier_du_mois),
                    d.hour, d.minute, d.second, 0, tzinfo=timezone.utc)


def _expire_ms(at_ms, months):
    return int(expires_at(_from_ms(at_ms), months).timestamp() * 1000)


def loyalty_state(visits, rewards, threshold_points, now, expiry_months=EXPIRY_MONTHS):
    """
    L'état de fidélité d'un client, à une date donnée.

    `visits`  : dicts avec `ts` et `amount_cents`.
    `rewards` : dicts avec `ts` et `points_spent`.
    `now`     : datetime. ⚠️ C'EST UN PARAMÈTRE, JAMAIS UNE LECTURE D'HORLOGE — sinon
                l'expiration est intestable et un client perd ses points à une seconde près.

    ⚠️ LES CENTIMES S'ADDITIONNENT AVANT L'ARRONDI. Arrondir chaque ticket ferait perdre au
    client environ 6 % de ses points, sans qu'aucun écran ne le montre.
    """
    maintenant = int(now.astimezone(timezone.utc).timestamp() * 1000)

    # Les lots, dans l'ordre d'acquisition. Un montant absurde ne retire pas de points.
    lots = []
    last_seen = None
    for v in visits:
        ts = v.get("ts")
        at = parse_ts(ts)
        if at is None:
            continue
        cents = v.get("amount_cents")
        if isinstance(cents, (int, float)) and not isinstance(cents, bool) and cents > 0:
            lots.append([at, int(cents)])
        # ⚠️ COMPARAISON DE CHAÎNES, comme côté Mesa. Sur des ISO de même forme c'est l'ordre
        # chronologique ; le reproduire garantit le même `lastSeen` des deux côtés.
        if isinstance(ts, str) and (last_seen is None or ts > last_seen):
            last_seen = ts
    lots.sort(key=lambda l: l[0])

    expired_cents = 0
    spent_points = 0

    # ⚠️ ON REJOUE L'HISTOIRE DANS L'ORDRE. Une récompense prise en mars ne peut consommer que
    # des points acquis avant mars ET non encore périmés à cette date. Calculer l'expiration
    # seulement à la fin ferait consommer, rétroactivement, des points qui n'existaient plus.
    prises = []
    for r in rewards:
        at = parse_ts(r.get("ts"))
        pts = r.get("points_spent")
        if at is None or not isinstance(pts, (int, float)) or isinstance(pts, bool) or pts <= 0:
            continue
        prises.append((at, int(pts)))
    prises.sort(key=lambda p: p[0])

    i = 0  # tête de file
    # ⚠️ CE QUI N'A PAS PU ÊTRE CONSOMMÉ SUR LE MOMENT RESTE DÛ. Une récompense dont aucun lot
    # n'est antérieur — horloges décalées, ligne rejouée dans le désordre — ne doit pas être
    # silencieusement oubliée : la boisson serait offerte ET les points resteraient au compteur.
    dette = 0
    for at_r, pts in prises:
        # Ce qui avait déjà péri au moment de la récompense est perdu, pas consommé.
        while i < len(lots) and lots[i][0] <= at_r and _expire_ms(lots[i][0], expiry_months) <= at_r:
            expired_cents += lots[i][1]
            i += 1
        # ⚠️ LES PLUS ANCIENS D'ABORD.
        reste = pts * 100
        spent_points += pts
        while reste > 0 and i < len(lots) and lots[i][0] <= at_r:
            pris = min(reste, lots[i][1])
            lots[i][1] -= pris
            reste -= pris
            if lots[i][1] == 0:
                i += 1
        dette += reste

    # Le filet : ce qui restait dû se prélève sur les lots les plus anciens encore là.
    while dette > 0 and i < len(lots):
        pris = min(dette, lots[i][1])
        lots[i][1] -= pris
        dette -= pris
        if lots[i][1] == 0:
            i += 1

    # Puis l'expiration jusqu'à maintenant.
    spent_cents = 0
    expiring_soon_cents = 0
    next_expiry = None
    bientot = maintenant + EXPIRY_WARNING_DAYS * _MS_PAR_JOUR
    for j in range(i, len(lots)):
        at, cents = lots[j]
        if cents <= 0:
            continue
        fin = expires_at(_from_ms(at), expiry_months)
        fin_ms = int(fin.timestamp() * 1000)
        if fin_ms <= maintenant:
            expired_cents += cents
            continue
        spent_cents += cents
        if fin_ms <= bientot:
            expiring_soon_cents += cents
        iso = to_iso(fin)
        if next_expiry is None or iso < next_expiry:
            next_expiry = iso

    earned_points = int(spent_cents // 100) * POINTS_PER_EURO
    # ⚠️ CE `max(0, …)` NE TIENT RIEN, ET C'EST ASSUMÉ. `spent_cents` est une somme de restes de
    # lots, tous positifs : il ne peut pas être négatif, et remplacer cette ligne par
    # `earned_points` ne casse aucun test — le mutant survit. On le garde uniquement parce que
    # Mesa a la même ligne : une divergence cosmétique entre les deux fichiers est exactement ce
    # qui rend la prochaine comparaison pénible. Si l'un des deux la retire, que ce soit les deux.
    balance_points = max(0, earned_points)

    # ⚠️ UN SEUIL ABSURDE N'OFFRE RIEN. `0` et les négatifs échouent au test `> 0`, qui suffit.
    seuil = threshold_points if isinstance(threshold_points, int) else 0
    rewards_due = balance_points // seuil if seuil > 0 else 0

    return {
        "spent_cents": spent_cents,
        "earned_points": earned_points,
        "spent_points": spent_points,
        "expired_points": int(expired_cents // 100),
        "balance_points": balance_points,
        "rewards_due": rewards_due,
        # ⚠️ `0` quand une récompense est due : « il manque 50 points » serait faux et décourageant.
        "points_to_next": (0 if rewards_due > 0 else seuil - balance_points) if seuil > 0 else 0,
        "expiring_soon_points": int(expiring_soon_cents // 100),
        "next_expiry": next_expiry,
        "visits": len(visits),
        "last_seen": last_seen,
    }


def absence_threshold_days(days):
    """
    Le seuil d'absence personnel d'un client : `max(7, 3 × écart médian)`.

    ⚠️ PLANCHER À SEPT JOURS, ET CE N'EST PAS ARBITRAIRE. Le café ferme deux jours par semaine :
    un client quotidien absent un mardi n'est pas parti. Sans ce plancher, la liste des clients
    à relancer se remplit de faux positifs après chaque fermeture — et une liste qu'on cesse de
    croire est une liste qu'on cesse de regarder.

    `days` : jours distincts de visite au format `AAAA-MM-JJ`, triés ou non.
    Renvoie `None` quand il n'y a pas assez d'historique pour qu'un seuil ait un sens.
    """
    uniques = sorted(set(days or []))
    ecarts = []
    for a, b in zip(uniques, uniques[1:]):
        ms_a, ms_b = parse_ts(a + "T00:00:00Z"), parse_ts(b + "T00:00:00Z")
        if ms_a is not None and ms_b is not None:
            ecarts.append(round((ms_b - ms_a) / _MS_PAR_JOUR))
    if not ecarts:
        return None
    ecarts.sort()
    median = ecarts[len(ecarts) // 2]
    return max(7, 3 * median)
