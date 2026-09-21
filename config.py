"""
Hypothèses BP Estudantina — BP_Estudantina_v3.xlsx
À mettre à jour manuellement quand les charges changent.
"""

from datetime import date, datetime, timedelta, timezone

# ── Fuseau horaire du café ───────────────────────────────────────────────────
# L'app tourne sur Vercel, dont l'horloge système est en UTC. Lisbonne est à
# UTC+1 l'été (WEST) et UTC+0 l'hiver (WET). Sans conversion, entre minuit et
# 1 h du matin heure locale le serveur croit qu'on est encore la veille : tout
# ce qui dépend de « quel jour est-on » se décale — le preset "lastweek" d'une
# semaine ENTIÈRE quand ça tombe un lundi — et toute comparaison « à la même
# heure » contre les `local_time` de Vendus (heure de Lisbonne) est flattée
# d'une heure de ventes.
#
# Ces deux fonctions sont le seul point d'entrée autorisé pour « aujourd'hui »
# et « maintenant » côté métier. Elles vivent ici parce que `config` ne dépend
# de rien : `app.py` comme `vendus.py` peuvent l'importer sans cycle.
LISBON_TZ_NAME = "Europe/Lisbon"

_LISBON_TZ = None          # ZoneInfo, ou None si la base tz est absente
_LISBON_TZ_RESOLVED = False


def _lisbon_zoneinfo():
    """La ZoneInfo Europe/Lisbon, ou None si le runtime n'a pas de base tz.

    Vercel (@vercel/python, image Amazon Linux) embarque normalement
    /usr/share/zoneinfo, et `tzdata` est de toute façon épinglé dans
    requirements.txt. Mais un ZoneInfo manquant lèverait ZoneInfoNotFoundError
    au premier appel, c'est-à-dire un 500 sur TOUTES les routes : on préfère un
    repli explicite (voir _lisbon_offset_hours) à une panne totale.
    """
    global _LISBON_TZ, _LISBON_TZ_RESOLVED
    if not _LISBON_TZ_RESOLVED:
        try:
            from zoneinfo import ZoneInfo
            _LISBON_TZ = ZoneInfo(LISBON_TZ_NAME)
        except Exception:
            _LISBON_TZ = None
        _LISBON_TZ_RESOLVED = True
    return _LISBON_TZ


def _last_sunday(year: int, month: int) -> date:
    """Dernier dimanche du mois — les bascules d'heure de l'UE tombent dessus."""
    d = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d -= timedelta(1)                       # dernier jour du mois
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _lisbon_offset_hours(utc_dt: datetime) -> int:
    """Décalage de Lisbonne, en heures, pour un instant donné en UTC.

    Règle UE (directive 2000/84/CE), que le Portugal continental suit : heure
    d'été du dernier dimanche de mars 01:00 UTC au dernier dimanche d'octobre
    01:00 UTC. Les deux bornes sont en UTC, donc la comparaison ci-dessous est
    exacte sans avoir à raisonner sur l'heure locale ambiguë de la bascule.

    Utilisé UNIQUEMENT en repli quand la base tz manque ; c'est aussi une
    fonction pure, donc testable face à zoneinfo.
    """
    naive = utc_dt.replace(tzinfo=None)
    y = naive.year
    start = datetime(y, 3, _last_sunday(y, 3).day, 1, 0)
    end = datetime(y, 10, _last_sunday(y, 10).day, 1, 0)
    return 1 if start <= naive < end else 0


def utc_now() -> datetime:
    """Instant courant en UTC (aware). Point d'injection unique pour les tests."""
    return datetime.now(timezone.utc)


def to_lisbon(utc_dt: datetime) -> datetime:
    """Convertit un instant (aware, ou naïf supposé UTC) en heure de Lisbonne."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    tz = _lisbon_zoneinfo()
    if tz is not None:
        return utc_dt.astimezone(tz)
    off = timedelta(hours=_lisbon_offset_hours(utc_dt.astimezone(timezone.utc)))
    return utc_dt.astimezone(timezone(off, "WEST" if off else "WET"))


def now_lisbon() -> datetime:
    """« Maintenant » tel que le lit quelqu'un debout dans le café (aware)."""
    return to_lisbon(utc_now())


def today_lisbon() -> date:
    """« Aujourd'hui » au sens du café — PAS le jour UTC du serveur."""
    return now_lisbon().date()


# ── Calendrier d'ouverture ───────────────────────────────────────────────────
# weekday() : 0=lun, 1=mar, 2=mer, 3=jeu, 4=ven, 5=sam, 6=dim
# Depuis le 12 juin 2026 : fermé mardi et mercredi.
OPEN_WEEKDAYS = frozenset({0, 3, 4, 5, 6})   # lun, jeu, ven, sam, dim

# Période de lancement (horaires irréguliers, saisie manuelle) — jours réels
# d'ouverture confirmés par Quentin. Avant le cutover, seuls ces jours comptent.
LAUNCH_OPEN_DAYS = {
    date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29),
    date(2026, 5, 30), date(2026, 5, 31),
    date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5),
    date(2026, 6, 6), date(2026, 6, 7), date(2026, 6, 8),
    date(2026, 6, 10), date(2026, 6, 11),
}
SCHEDULE_CUTOVER = date(2026, 6, 12)   # à partir d'ici : calendrier OPEN_WEEKDAYS

def count_open_days_raw(from_date: date, to_date: date) -> int:
    """Nombre de jours d'ouverture effectifs entre deux dates incluses (peut être 0)."""
    n = 0
    cur = from_date
    while cur <= to_date:
        if cur < SCHEDULE_CUTOVER:
            if cur in LAUNCH_OPEN_DAYS:
                n += 1
        elif cur.weekday() in OPEN_WEEKDAYS:
            n += 1
        cur += timedelta(1)
    return n

def count_open_days(from_date: date, to_date: date) -> int:
    """Comme count_open_days_raw mais ≥ 1 (évite les divisions par zéro)."""
    return max(count_open_days_raw(from_date, to_date), 1)

# ══════════════════════════════════════════════════════════════════════════════
# CE QUI N'EST PLUS ICI — ET OÙ LE CHERCHER
# ══════════════════════════════════════════════════════════════════════════════
#
# ⚠️ LES CHARGES ET LES SALAIRES VIVENT EN BASE, PAS DANS CE FICHIER. Tables Supabase
# `charges_fixes` et `employees`, éditées sur la page `/charges`, lues en direct par
# `daily_economics` (vendus.py) et par la caisse Mesa (`lib/server/estushopCharges.ts`).
#
# ⚠️ CE FICHIER EN PORTAIT ENCORE UNE COPIE, ET ELLE MENTAIT. Quinze postes de charges et deux
# salaires y étaient écrits en dur — loyer à 700 €, Julie à 1 000 € — et plus personne ne les
# importait. Les modifier ne changeait RIEN au tableau de bord : ni la marge, ni le point mort,
# ni l'EBITDA. Un fichier de configuration qu'on peut éditer sans effet est pire qu'un fichier
# absent : il donne la sensation d'avoir agi.
#
# Retirés le 21/09/2026 avec toute leur descendance, morte de la même façon :
#   CHARGES_FIXES · PERSONNEL · TOTAL_CHARGES_FIXES_MOIS · TOTAL_PERSONNEL_MOIS ·
#   TOTAL_CHARGES_MOIS · COUT_FIXE_JOUR · COUT_PERSONNEL_JOUR · COUT_TOTAL_JOUR ·
#   AMORT_JOUR · SEUIL_CA_JOUR · SEUIL_CA_JOUR_TTC · MARGE_BP_BOISSONS ·
#   MARGE_BP_PATISSERIES · MARGE_BP_LIVRES
#
# ⚠️ CHACUNE NE SERVAIT QU'À LA SUIVANTE. La chaîne partait de `CHARGES_FIXES` et finissait sur
# `SEUIL_CA_JOUR_TTC`, que personne ne lisait : quatorze constantes dont aucune n'atteignait un
# écran. C'est ce qui rend ce genre de code si durable — il ne casse jamais.

# ── Amortissements / mois ────────────────────────────────────────────────────
# CAPEX 60 000 € sur 8 ans. ⚠️ ENCORE EN DUR, ET ENCORE LU : `daily_economics` s'en sert pour
# l'amortissement journalier. À faire passer en base avec les autres réglages.
AMORTISSEMENT_MOIS = 625.00

# ── Jours d'ouverture moyens / mois ─────────────────────────────────────────
# Source : feuille 1_Hypothèses — 255 jours / 12 mois.
# ⚠️ CE NOMBRE DEVRAIT SE DÉDUIRE DU CALENDRIER `OPEN_WEEKDAYS` ci-dessus, pas être saisi. Deux
# réglages qui décrivent la même chose finissent toujours par diverger — et c'est le diviseur
# de tout le compte de résultat journalier.
JOURS_OUVERTS_MOIS = 21.25

# ── Marge brute théorique du business plan ───────────────────────────────────
# ⚠️ UN REPLI, PAS UNE VÉRITÉ. La marge MESURÉE l'emporte dès qu'elle existe (vendus.py) ;
# celle-ci ne sert qu'aux périodes sans données de coût.
MARGE_BP_GLOBALE = 0.703   # 70,3 % (pondérée)

# ── TVA moyenne pondérée (blended) ──────────────────────────────────────────
# Taux dominant sur boissons/food (INT = 13 %).
TVA_MOYENNE_BLENDED = 0.13
