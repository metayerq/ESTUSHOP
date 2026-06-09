"""
Hypothèses BP Estudantina — BP_Estudantina_v3.xlsx
À mettre à jour manuellement quand les charges changent.
"""

from datetime import date, timedelta

# ── Calendrier d'ouverture ───────────────────────────────────────────────────
# weekday() : 0=lun, 1=mar, 2=mer, 3=jeu, 4=ven, 5=sam, 6=dim
OPEN_WEEKDAYS = frozenset({0, 3, 4, 5, 6})   # lun, jeu, ven, sam, dim

def count_open_days(from_date: date, to_date: date) -> int:
    """Nombre de jours d'ouverture effectifs entre deux dates incluses."""
    n = 0
    cur = from_date
    while cur <= to_date:
        if cur.weekday() in OPEN_WEEKDAYS:
            n += 1
        cur += timedelta(1)
    return max(n, 1)   # au moins 1 pour éviter la division par zéro

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
