"""
LES CHARGES À UNE DATE DONNÉE.

⚠️ SANS DATE DE VALIDITÉ, CHANGER UN MONTANT RÉÉCRIT LE PASSÉ. `daily_economics` relit les
charges en direct à chaque calcul : augmenter le loyer en septembre change l'EBITDA de juin,
partout, et sans que rien ne le signale. C'est exactement ce que la page de réconciliation passe
son temps à combattre — un chiffre qui bouge sous les yeux de celui qui l'avait déjà lu.

⚠️ ET SUPPRIMER UN POSTE LE RETIRAIT DE TOUT L'HISTORIQUE. Le loyer effacé en septembre
disparaissait de mai, juin et juillet : trois mois qui devenaient soudain rentables.

Ce module ne fait qu'une chose : dire quelles lignes s'appliquent un jour donné. Il est pur —
aucune base, aucune horloge — pour que la règle soit vérifiable au cas limite.
"""

from datetime import date, timedelta

# Le taux de Sécurité sociale portugaise part patronale, et le nombre de jours de carte repas.
#
# ⚠️ CETTE FORMULE EST RECOPIÉE DANS MESA (`lib/server/estushopCharges.ts`), et les deux doivent
# rester d'accord : la caisse affiche le même point mort que le bureau. Une divergence ne casse
# rien — elle fait simplement dire deux chiffres différents à deux écrans, et c'est le comptoir
# qui a le dernier mot devant un client.
TSU_RATE = 0.2375
REPAS_JOURS = 242   # ~11 mois × 22 jours


def _jour(v):
    """Une date, quelle que soit la forme reçue de PostgREST. `None` reste `None`."""
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def applicable(ligne, jour):
    """
    Cette ligne s'applique-t-elle ce jour-là ?

    ⚠️ `valid_from` NUL VEUT DIRE « DEPUIS TOUJOURS », `valid_to` NUL « ENCORE EN VIGUEUR ».
    C'est la convention du dépôt : NULL n'est jamais zéro, il est « pas de borne ». Les lignes
    d'avant cette migration n'ont donc aucune borne, et continuent de s'appliquer partout —
    exactement leur comportement d'hier.

    ⚠️ ET LA BORNE HAUTE EST EXCLUE. « Valide jusqu'au 1er octobre » veut dire que le
    30 septembre est le dernier jour couvert : c'est ainsi qu'on clôt une ligne et qu'on en
    ouvre une autre le même jour sans compter le loyer deux fois.
    """
    debut = _jour(ligne.get("valid_from"))
    fin = _jour(ligne.get("valid_to"))
    if debut is not None and jour < debut:
        return False
    if fin is not None and jour >= fin:
        return False
    return True


def _mensuel(montant, frequence):
    """Ramène une charge à son équivalent mensuel."""
    if frequence == "quarterly":
        return montant / 3
    if frequence == "annual":
        return montant / 12
    return montant


def charges_mensuelles(lignes, jour):
    """Le total mensuel des charges fixes en vigueur ce jour-là."""
    total = 0.0
    for c in lignes or []:
        if not applicable(c, jour):
            continue
        try:
            total += _mensuel(float(c.get("amount") or 0), c.get("frequency", "monthly"))
        except (TypeError, ValueError):
            continue    # une ligne abîmée ne doit pas faire tomber tout le calcul
    return total


def cout_employe_mensuel(e):
    """
    Le coût mensuel lissé d'un salarié : brut × 14 mois, plus la TSU, plus la carte repas.

    ⚠️ LES EXTRAS SONT PAYÉS TELS QUELS. Un extra n'a ni treizième mois, ni carte repas : lui
    appliquer la formule salariale gonflerait son coût de 40 % et fausserait le point mort les
    mois de gros service, qui sont précisément ceux où l'on en emploie.
    """
    try:
        brut = float(e.get("gross_monthly") or 0)
    except (TypeError, ValueError):
        return 0.0
    if e.get("type") == "extra":
        return brut
    try:
        repas = float(e.get("meal_card_daily") or 10.20)
    except (TypeError, ValueError):
        repas = 10.20
    tsu = 0.0 if e.get("tsu_exempt") else TSU_RATE
    return (brut * 14 * (1 + tsu) + repas * REPAS_JOURS) / 12


def personnel_mensuel(lignes, jour):
    """Le total mensuel du personnel en poste ce jour-là."""
    return sum(cout_employe_mensuel(e) for e in (lignes or []) if applicable(e, jour))


def cout_periode(charges, employes, jours_ouverts, jours_ouverts_mois):
    """
    Le coût réel d'une période : la somme des coûts journaliers de CHAQUE jour ouvert.

    ⚠️ UN SEUL TOTAL MENSUEL NE SUFFIT PLUS. Si le loyer augmente le 1er octobre, une période
    qui enjambe septembre et octobre n'a pas un coût journalier unique. Multiplier un total par
    un nombre de jours donnerait le bon ordre de grandeur et le mauvais chiffre — et l'erreur
    serait maximale le mois où l'on vient justement voir l'effet du changement.

    `jours_ouverts` est la liste des dates réellement ouvertes. Renvoie
    `(total_fixes, total_personnel)` sur la période.
    """
    if not jours_ouverts or not jours_ouverts_mois:
        return 0.0, 0.0
    fixes = perso = 0.0
    # ⚠️ ON MET LES JOURS EN CACHE PAR DATE : sur trois mois, les mêmes bornes reviennent
    # quatre-vingt-dix fois, et recalculer la somme à chaque fois coûterait en O(jours × lignes)
    # pour un résultat qui ne change qu'aux dates de bascule.
    vu = {}
    for j in jours_ouverts:
        if j not in vu:
            vu[j] = (charges_mensuelles(charges, j) / jours_ouverts_mois,
                     personnel_mensuel(employes, j) / jours_ouverts_mois)
        a, b = vu[j]
        fixes += a
        perso += b
    return fixes, perso


def jours_ouverts_entre(debut, fin, est_ouvert):
    """Les dates réellement ouvertes d'une période, bornes incluses."""
    out, j = [], debut
    while j <= fin:
        if est_ouvert(j):
            out.append(j)
        j += timedelta(1)
    return out
