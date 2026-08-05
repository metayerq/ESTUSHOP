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

# ── Charges fixes opérationnelles / mois (€) ────────────────────────────────
# Source : feuille 4_Charges_fixes, mois stabilisés (Juil 26+)
CHARGES_FIXES = {
    "Loyer (Rua da Indústria 32)":      700.00,
    "EPAL (eau)":                         50.00,
    "EDP (électricité)":                 150.00,
    "Comptabilité Filomencor":           200.00,
    "Assurance multirisques":             80.00,
    "Licence musique (SPA)":               7.46,
    "Internet & téléphone":               15.00,
    "Logiciel POS & SaaS":                32.00,
    "Banque":                             18.00,
    "Maintenance équipements":            50.00,
    "Divers":                             50.00,
    "Assurance accident travail (AT)":    11.50,
    "Pest control":                       20.00,
    "Maintenance machine café":           40.00,
    "Licença esplanada CML":              17.00,
}
TOTAL_CHARGES_FIXES_MOIS = sum(CHARGES_FIXES.values())  # ≈ 1 440.96 €

# ── Personnel / mois (€) ────────────────────────────────────────────────────
# Source : feuille 5_Personnel — salaires lissés 14 mois + TSU + carte repas
PERSONNEL = {
    "Julie (salaire brut lissé)":      1_000.00,   # TSU exonérée (1er emploi)
    "André (brut lissé + TSU + repas)": 1_746.875,
}
TOTAL_PERSONNEL_MOIS = sum(PERSONNEL.values())  # = 2 746.875 €

# ── Total charges opérationnelles / mois ────────────────────────────────────
TOTAL_CHARGES_MOIS = TOTAL_CHARGES_FIXES_MOIS + TOTAL_PERSONNEL_MOIS  # ≈ 4 187.84 €

# ── Amortissements / mois ────────────────────────────────────────────────────
# CAPEX 60 000 € sur 8 ans
AMORTISSEMENT_MOIS = 625.00

# ── Jours d'ouverture moyens / mois ─────────────────────────────────────────
# Source : feuille 1_Hypothèses — 255 jours / 12 mois
JOURS_OUVERTS_MOIS = 21.25

# ── Coût journalier (base de calcul dashboard) ───────────────────────────────
COUT_FIXE_JOUR     = round(TOTAL_CHARGES_FIXES_MOIS / JOURS_OUVERTS_MOIS, 2)   # ≈ 67.81 €
COUT_PERSONNEL_JOUR = round(TOTAL_PERSONNEL_MOIS   / JOURS_OUVERTS_MOIS, 2)   # ≈ 129.27 €
COUT_TOTAL_JOUR    = round(TOTAL_CHARGES_MOIS       / JOURS_OUVERTS_MOIS, 2)   # ≈ 197.08 €
AMORT_JOUR         = round(AMORTISSEMENT_MOIS       / JOURS_OUVERTS_MOIS, 2)   # ≈ 29.41 €

# ── Marges brutes théoriques BP ──────────────────────────────────────────────
MARGE_BP_BOISSONS    = 0.80    # 80 %
MARGE_BP_PATISSERIES = 0.638   # 63.8 %
MARGE_BP_LIVRES      = 0.40    # 40 %
MARGE_BP_GLOBALE     = 0.703   # 70.3 % (pondérée)

# ── TVA moyenne pondérée (blended) ──────────────────────────────────────────
# Taux dominant sur boissons/food (INT = 13%).
TVA_MOYENNE_BLENDED = 0.13

# ── Seuil de rentabilité CA ──────────────────────────────────────────────────
# CA minimum pour couvrir toutes les charges opérationnelles (hors amort.)
SEUIL_CA_JOUR     = round(COUT_TOTAL_JOUR / MARGE_BP_GLOBALE, 2)          # ≈ 280 €/jour HT
SEUIL_CA_JOUR_TTC = round(SEUIL_CA_JOUR * (1 + TVA_MOYENNE_BLENDED), 2)  # ≈ 312 €/jour TTC
