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
# ⚠️ CETTE FORMULE EST RECOPIÉE DANS MESA (`lib/server/estushopCharges.ts`), ET LES DEUX ONT
# DIVERGÉ LE 04/10/2026, DÉLIBÉRÉMENT. Mesa ignore le planning du personnel et garde le diviseur
# constant de 21,25 jours ; ce fichier lit les services réels et le vrai calendrier. L'écran
# `CostScreen` de la caisse annonce donc un point mort qui n'est plus celui du bureau — il reste
# juste à l'ordre de grandeur, faux au détail, et il ne bouge pas quand on ajoute un extra.
#
# Le commentaire d'avant promettait l'inverse : « les deux doivent rester d'accord ». Décision de
# Quentin de ne pas porter le changement côté caisse ; la promesse est donc retirée plutôt que
# laissée à démentir par les chiffres. Le jour où quelqu'un voudra les réaccorder, il lui faut
# porter `services_du_jour`, `personnel_du_jour`, `jours_ouverts_du_mois` et la bascule.
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
    # ⚠️ SANS BORNES, `active` EST LA BORNE. Avant cette migration, une charge désactivée était
    # écartée de TOUS les calculs : c'était le seul moyen d'arrêter un poste. Retirer le filtre
    # `active=eq.true` sans honorer ce cas remettait en service tout ce que Quentin avait
    # éteint — un logiciel résilié qui recommence à coûter 120 € par mois, sans un mot.
    #
    # C'est aussi ce qui tient la promesse du déploiement : le jour de la migration, aucune
    # ligne n'a de bornes, et toutes se comportent donc exactement comme la veille.
    if debut is None and fin is None and ligne.get("active") is False:
        return False
    if debut is not None and jour < debut:
        return False
    if fin is not None and jour >= fin:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LES CHARGES SUR FACTURE — EAU ET ÉLECTRICITÉ
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ UNE FACTURE N'EST PAS UN CHANGEMENT, C'EST UNE OBSERVATION. La cérémonie — date d'effet au
# plus tôt demain, motif écrit — existe pour forcer quelqu'un à ARTICULER un changement. Une
# facture n'articule rien : son motif, c'est elle-même ; sa date, c'est son mois. On ne retire
# donc pas la discipline des lignes datées — une facture en est l'expression la plus pure, une
# ligne par mois, close par construction. On arrête seulement de poser deux questions dont la
# réponse est connue d'avance.
#
# ⚠️ ET LE SYSTÈME MENTAIT D'UN MOIS, EN PERMANENCE. `_date_effet` refuse toute date antérieure
# à demain : la facture d'électricité d'octobre, reçue le 5 novembre, ne pouvait s'appliquer
# qu'à partir de novembre. Octobre gardait donc à jamais le montant de septembre. Ce n'était pas
# une approximation — c'était un décalage systématique que rien n'annonçait.
#
# ⚠️ UNE LIGNE DE FACTURE S'OUVRE SANS BORNE HAUTE, et c'est le cœur du mécanisme. C'est la
# facture du mois SUIVANT qui la clôt. Tant qu'elle n'est pas arrivée, le mois courant porte la
# dernière facture connue — ESTIMÉE, et dite comme telle. L'alternative, clore chaque ligne à la
# fin de son mois, laisserait un trou : la charge disparaîtrait du point mort, qui paraîtrait
# plus bas qu'il n'est. Un trou est un pire mensonge qu'une estimation annoncée.


def est_facture(ligne):
    """Cette charge se saisit-elle facture par facture ?"""
    return str((ligne or {}).get("mode") or "stable") == "facture"


def mois_de(jour):
    """Le premier du mois de `jour` — la clé d'une facture."""
    return date(jour.year, jour.month, 1)


def mois_suivant(mois):
    return date(mois.year + 1, 1, 1) if mois.month == 12 else date(mois.year, mois.month + 1, 1)


def facture_estimee(ligne, jour):
    """
    Cette ligne de facture couvre-t-elle un mois ANTÉRIEUR à celui qu'on calcule ?

    ⚠️ C'EST LA SEULE DÉFINITION DE « ESTIMÉ », et elle doit rester unique. Une estimation n'est
    pas un état qu'on pose à la main : c'est le constat qu'on impute à un mois la facture d'un
    autre, faute de mieux. Un drapeau saisi séparément finirait par mentir.
    """
    if not est_facture(ligne):
        return False
    # ⚠️ AVEC UNE PÉRIODE, « ESTIMÉ » SE DIT AU JOUR PRÈS. Un jour postérieur à la fin de la
    # facture est couvert par prolongation de son taux, pas par une mesure — et une facture de
    # 60 jours finit le 18 du mois, pas le 30 : la question ne se pose plus par mois.
    fin = _jour(ligne.get("periode_fin"))
    if fin is not None:
        return jour > fin
    m = _jour(ligne.get("mois"))
    return m is not None and m < mois_de(jour)


def _fin_de_mois(mois):
    return mois_suivant(mois) - timedelta(1)


def taux_jour(ligne):
    """
    Le coût journalier d'une facture, ou `None` si elle ne couvre pas de période connue.

    ⚠️ UNE FACTURE NE COUVRE PAS UN MOIS, ELLE COUVRE UNE PÉRIODE. L'EPAL facture 60 jours à
    cheval sur trois mois civils : la facture du 21/07 au 18/09 vaut 176,14 €, soit 2,94 € par
    jour — et non 176,14 € par mois, ce que le modèle « une facture = un mois » en faisait. Sur
    cette seule facture, l'eau pesait 86,78 € de trop par mois dans le point mort.
    """
    debut, fin = _jour(ligne.get("periode_debut")), _jour(ligne.get("periode_fin"))
    if debut is None or fin is None or fin < debut:
        return None
    try:
        montant = float(ligne.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    return montant / ((fin - debut).days + 1)


def part_mensuelle(ligne, jour):
    """
    Ce que cette ligne pèse sur le mois de `jour`.

    ⚠️ UNE SEULE RÈGLE, ET ELLE COUVRE LES DEUX RÉGIMES : taux journalier × nombre de jours du
    mois où la ligne est EN VIGUEUR. Pour une facture close par la suivante, cela redonne
    exactement sa période. Pour la dernière, restée ouverte, cela prolonge son taux sur les
    jours qui suivent — c'est l'estimation d'aujourd'hui, inchangée, et c'est pourquoi il n'y a
    pas deux calculs à tenir d'accord.

    Une ligne sans période garde son équivalent mensuel : les charges stables, et les lignes
    d'avant cette migration, se comportent exactement comme hier.
    """
    taux = taux_jour(ligne)
    if taux is None:
        try:
            return _mensuel(float(ligne.get("amount") or 0), ligne.get("frequency", "monthly"))
        except (TypeError, ValueError):
            return 0.0
    debut_m, fin_m = mois_de(jour), _fin_de_mois(mois_de(jour))
    d, f = _jour(ligne.get("valid_from")), _jour(ligne.get("valid_to"))
    bas = max(debut_m, d) if d else debut_m
    # `valid_to` est EXCLUE : une ligne qui s'arrête le 1er octobre couvre le 30 septembre.
    haut = min(fin_m, f - timedelta(1)) if f else fin_m
    return taux * max(0, (haut - bas).days + 1)


def charges_mensuelles_detail(lignes, jour):
    """
    Le total mensuel en vigueur ce jour-là, ET ce qui dedans n'est qu'une estimation.

    Renvoie `(total, estimees)` où `estimees` est la liste des noms dont la facture du mois
    n'est pas encore arrivée. L'appelant doit pouvoir le DIRE : un point mort nourri d'une
    estimation se lit autrement qu'un point mort mesuré, et le taire déplacerait le mensonge
    au lieu de le supprimer.
    """
    total = 0.0
    estimees = []
    for c in lignes or []:
        if not applicable(c, jour):
            continue
        try:
            total += part_mensuelle(c, jour)
        except (TypeError, ValueError):
            continue    # une ligne abîmée ne doit pas faire tomber tout le calcul
        if facture_estimee(c, jour):
            estimees.append(str(c.get("name") or ""))
    return total, estimees


def charges_estimees(lignes, jours):
    """
    Les charges dont le montant imputé sur CES jours-là n'est qu'une estimation.

    ⚠️ C'EST L'INFORMATION QUI MANQUAIT AU POINT MORT. Le total était déjà juste au mieux de ce
    qu'on sait — un mois sans facture reprend la dernière connue — mais l'écran le présentait
    comme une mesure. Un seuil de rentabilité nourri d'une estimation et annoncé comme un fait
    est pire qu'un seuil absent : on arrête de chercher la facture.

    ⚠️ UN SEUL JOUR ESTIMÉ SUFFIT À QUALIFIER LA PÉRIODE. Une semaine à cheval sur deux mois
    dont un seul manque reste une semaine dont le point mort est en partie supposé ; arrondir
    au « la plupart des jours vont bien » reviendrait à taire ce qu'on sait.

    Renvoie les noms, triés, sans doublon — pour que l'écran puisse les nommer.
    """
    vus = set()
    for j in jours or []:
        for c in lignes or []:
            nom = str((c or {}).get("name") or "")
            if nom in vus or not applicable(c, j):
                continue
            if facture_estimee(c, j):
                vus.add(nom)
    return sorted(vus)


def debut_dune_ligne(ligne):
    """
    Le jour où cette ligne commence à couvrir.

    ⚠️ `valid_from` D'ABORD, ET C'EST LUI LA VÉRITÉ. J'avais mis `periode_debut` en tête ; aucun
    cas ne distinguait les deux — la route pose `valid_from = periode_debut` à l'insertion, et
    recouper une ligne ne touche que `valid_to`. Une priorité que rien ne peut contredire est
    une branche morte, et c'est précisément là que les fautes s'installent. Les deux replis
    servent aux lignes posées hors de la route, et à celles d'avant la migration.
    """
    return (_jour(ligne.get("valid_from")) or _jour(ligne.get("periode_debut"))
            or _jour(ligne.get("mois")))


def couvre(ligne, jour):
    """Cette ligne est-elle en vigueur ce jour-là ? (`valid_to` exclue, comme partout.)"""
    d, f = _jour(ligne.get("valid_from")), _jour(ligne.get("valid_to"))
    return (d is None or d <= jour) and (f is None or f > jour)


def bornes_dune_facture(lignes, nom, debut):
    """
    Où insérer une facture qui commence le `debut`, et quelles lignes recouper.

    Renvoie `(valid_from, valid_to, a_cloturer)` :
      · `valid_from` est le premier jour de la période facturée ;
      · `valid_to` est le début de la facture SUIVANTE si elle existe déjà, sinon `None` —
        la dernière reste ouverte, et c'est elle qui porte l'estimation des jours qui suivent.
        ⚠️ CE N'EST PAS LA FIN DE LA PÉRIODE. Fermer la ligne au dernier jour facturé laisserait
        les jours suivants SANS AUCUNE ligne : la charge disparaîtrait du point mort, qui
        paraîtrait plus bas qu'il n'est. Un trou ment plus qu'une estimation annoncée — c'est
        pourquoi cette fonction n'a pas besoin de connaître la fin de période, et pourquoi je
        lui ai retiré le paramètre que je lui avais donné sans jamais le lire ;
      · `a_cloturer` est la LISTE des lignes en vigueur ce jour-là, chacune avec sa date.

    ⚠️ ON RAISONNE EN DATES, PLUS EN MOIS. Une facture d'eau couvre du 21/07 au 18/09 : lui
    chercher « le mois précédent » n'a pas de sens, et le mois de son début n'est pas le mois
    qu'elle facture. La question n'a jamais été « quel mois » mais « quelle ligne était en
    vigueur le jour où celle-ci commence » — ce que `couvre` répond directement.

    ⚠️ LA SAISIE PEUT ARRIVER DANS LE DÉSORDRE, et rattraper une période ancienne après avoir
    saisi les suivantes doit poser la ligne entre ses voisines sans les écraser.

    ⚠️ ET LA LIGNE HÉRITÉE DE LA BASCULE N'A NI MOIS NI BORNES. Passer une charge en mode
    facture laisse son montant d'avant, ouvert : on ne regardait que les lignes portant un mois
    pour décider laquelle clôturer, elle ne l'était donc jamais et la charge comptait DOUBLE dès
    la première facture. `couvre` la voit comme n'importe quelle autre.
    """
    siennes = [f for f in (lignes or [])
               if est_facture(f) and str(f.get("name") or "") == nom]
    apres = sorted((d for d in (debut_dune_ligne(f) for f in siennes)
                    if d is not None and d > debut))
    fin = apres[0] if apres else None
    a_cloturer = [(f, debut) for f in siennes
                  if couvre(f, debut) and debut_dune_ligne(f) != debut]
    return debut, fin, a_cloturer


def couverture(lignes, nom, aujourdhui):
    """
    Jusqu'à quel jour cette charge est MESURÉE, et combien de jours restent à facturer.

    Renvoie `{"jusqua": date|None, "jours": int, "debut_suivant": date|None}` :
      · `jusqua` est le dernier jour couvert par une facture reçue ;
      · `jours` est le nombre de jours écoulés depuis, donc estimés ;
      · `debut_suivant` est le premier jour de la prochaine facture — le lendemain, celui que
        l'écran propose pour ne pas laisser de trou.

    ⚠️ CE QUI MANQUE NE SE COMPTE PLUS EN MOIS. `mois_en_attente` réclamait les mois clos sans
    facture ; une facture d'eau couvre du 21/07 au 18/09, donc aucun mois n'est jamais « sans
    facture » ni jamais complet. La question juste est : jusqu'à quand sait-on, et depuis
    combien de jours extrapole-t-on.

    ⚠️ ET UNE FACTURE SANS PÉRIODE NE DIT RIEN DE SA FIN. Les lignes d'avant cette migration
    portent un mois : on les lit comme couvrant leur mois entier, ce qu'elles prétendaient être.
    """
    fins = []
    for c in lignes or []:
        if not est_facture(c) or str(c.get("name") or "") != nom:
            continue
        f = _jour(c.get("periode_fin"))
        if f is None:
            m = _jour(c.get("mois"))
            f = _fin_de_mois(m) if m else None
        if f is not None:
            fins.append(f)
    if not fins:
        return {"jusqua": None, "jours": 0, "debut_suivant": None}
    jusqua = max(fins)
    return {"jusqua": jusqua,
            "jours": max(0, (aujourdhui - jusqua).days),
            "debut_suivant": jusqua + timedelta(1)}


def mois_en_attente(lignes, nom, aujourdhui):
    """
    Les mois clos dont la facture manque, du plus ancien au plus récent.

    ⚠️ LE MOIS COURANT N'EST JAMAIS EN ATTENTE. Il n'est pas fini : il n'y a rien à saisir, donc
    rien à signaler. Crier sur un mois en cours apprend à ignorer le signal, et c'est celui qui
    compte qu'on rate ensuite.
    """
    connus = {_jour(f.get("mois")) for f in (lignes or [])
              if est_facture(f) and str(f.get("name") or "") == nom and _jour(f.get("mois"))}
    if not connus:
        return []
    courant = mois_de(aujourdhui)
    m = mois_suivant(min(connus))
    manquants = []
    while m < courant:
        if m not in connus:
            manquants.append(m)
        m = mois_suivant(m)
    return manquants


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
            total += part_mensuelle(c, jour)
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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LE PLANNING — CE QUE COÛTE UN JOUR PARTICULIER
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ DEUX RÉGIMES, ET C'EST TOUT L'INTÉRÊT. Le barista fixe est payé pareil qu'il fasse trois
# jours ou cinq : faire dériver SON coût du planning rendrait un mois creux artificiellement
# bon marché, alors que la paie est identique. Sa paie reste donc lissée, et le planning ne dit
# de lui que « il est là ». L'extra, lui, coûte ses heures le jour où il les fait.
#
# ⚠️ ET LE TAUX SE RÉSOUT À LA DATE DU SHIFT. Une augmentation d'octobre ne doit pas réécrire
# un service de septembre : on cherche la version de la fiche en vigueur CE JOUR-LÀ, avec le
# même `applicable()` que les charges. La règle est écrite une fois.


def heures(debut, fin):
    """
    Les heures d'un shift, en décimal. Rend 0.0 sur une saisie illisible.

    ⚠️ ON REFUSE PLUTÔT QUE D'INVENTER. Une heure de fin avant l'heure de début n'est pas une
    nuit à cheval sur minuit — c'est une faute de frappe, et la traiter comme un service de
    vingt-trois heures gonflerait le coût du jour sans que personne ne comprenne pourquoi.
    """
    def _m(v):
        if v is None:
            return None
        t = str(v).strip()
        if not t:
            return None
        bouts = t.split(":")
        try:
            h = int(bouts[0])
            m = int(bouts[1]) if len(bouts) > 1 else 0
        except (ValueError, IndexError):
            return None
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h * 60 + m

    a, b = _m(debut), _m(fin)
    if a is None or b is None or b <= a:
        return 0.0
    return (b - a) / 60.0


def fiche_du_jour(employes, person_id, jour):
    """
    La version de la fiche de cette personne en vigueur ce jour-là, ou `None`.

    ⚠️ UNE PERSONNE A PLUSIEURS FICHES. Augmenter quelqu'un clôt la sienne et en ouvre une
    autre, avec un identifiant neuf : seule `person_id` les relie. Prendre « la » fiche par son
    `id` donnerait le bon nom et le mauvais taux dès la première augmentation.
    """
    if not person_id:
        return None
    for e in employes or []:
        if str(e.get("person_id") or "") != str(person_id):
            continue
        if applicable(e, jour):
            return e
    return None


def cout_shift(shift, employes):
    """Ce que coûte un shift : ses heures au taux de la personne, ce jour-là."""
    jour = _jour(shift.get("day"))
    if jour is None:
        return 0.0
    fiche = fiche_du_jour(employes, shift.get("person_id"), jour)
    if fiche is None:
        # ⚠️ UN SHIFT SANS FICHE APPLICABLE NE COÛTE RIEN, ET C'EST VOULU. Il reste visible au
        # planning — quelqu'un a bien travaillé — mais inventer un taux serait pire que zéro.
        # L'écran le signale ; le calcul ne devine pas.
        return 0.0
    try:
        taux = float(fiche.get("hourly_rate") or 0)
    except (TypeError, ValueError):
        return 0.0
    return heures(shift.get("start_time"), shift.get("end_time")) * taux


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LES RÈGLES DE RÉCURRENCE — « Ana tous les mercredis de 9 h à 17 h »
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ UNE RÈGLE EST VIVANTE : RIEN N'EST RECOPIÉ. Les services qu'elle produit n'existent pas en
# base ; ils sont calculés à la lecture. La contrepartie est assumée et choisie : corriger
# l'horaire d'une règle qui couvrait septembre change le coût de septembre. L'écran l'annonce au
# moment du geste — il n'interdit pas.
#
# ⚠️ ET UNE EXCEPTION N'EST PAS UN AUTRE CONCEPT. « Ana ne vient pas ce mercredi » et « Ana vient
# de 14 h à 20 h ce mercredi-là » sont le même geste : une ligne de `shifts` qui porte le
# `rule_id` et prend le dessus pour cette date. Une table de plus aurait fait trois endroits où
# chercher pourquoi quelqu'un apparaît — ou n'apparaît pas — au planning.


def services_du_jour(jour, regles, shifts):
    """
    Tout ce qui est prévu ce jour-là : les règles dépliées, leurs exceptions, et les ponctuels.

    Chaque service rendu porte `source` — « regle », « regle-modifiee » ou « ponctuel » — parce
    que l'écran doit pouvoir dire d'où vient une case, et qu'un service produit par une règle ne
    se supprime pas comme un service posé à la main.
    """
    out = []
    # Les exceptions, indexées par règle : une seule par règle et par jour.
    par_regle = {}
    for s in shifts or []:
        if s.get("rule_id") and _jour(s.get("day")) == jour:
            par_regle[str(s["rule_id"])] = s

    for r in regles or []:
        if r.get("weekday") is None or int(r["weekday"]) != jour.weekday():
            continue
        if not applicable(r, jour):
            continue
        ex = par_regle.get(str(r.get("id")))
        if ex is not None:
            # ⚠️ ANNULÉ VEUT DIRE ABSENT, PAS « ZÉRO HEURE ». Rendre un service de durée nulle
            # le ferait apparaître au planning comme une case vide inexplicable.
            if ex.get("annule"):
                continue
            out.append({**ex, "source": "regle-modifiee", "rule_id": r.get("id"),
                        "person_id": r.get("person_id")})
            continue
        out.append({"id": None, "rule_id": r.get("id"), "person_id": r.get("person_id"),
                    "day": jour.isoformat(), "start_time": r.get("start_time"),
                    "end_time": r.get("end_time"), "note": r.get("note"),
                    "source": "regle"})

    for s in shifts or []:
        if s.get("rule_id"):
            continue
        if _jour(s.get("day")) != jour:
            continue
        if s.get("annule"):
            continue
        out.append({**s, "source": "ponctuel"})

    out.sort(key=lambda x: str(x.get("start_time") or ""))
    return out


def _est_extra(e):
    return str(e.get("type") or "") == "extra"


def personnel_du_jour(employes, shifts, jour, jours_ouverts_mois, bascule=None, regles=None):
    """
    Le coût du personnel pour CE jour : permanents lissés, extras réels.

    `jours_ouverts_mois` est le nombre de jours réellement ouverts du mois de `jour` — pas une
    constante. `bascule` est la date à partir de laquelle les extras passent au planning ;
    avant elle, ils gardent leur montant mensuel lissé, et le passé ne bouge pas.

    ⚠️ SANS LA BASCULE, LE JOUR DE LA MISE EN SERVICE EFFACE LE COÛT DES EXTRAS DE TOUS LES MOIS
    CLOS. Septembre n'a aucun shift enregistré : son personnel paraîtrait soudain moins cher, et
    le point mort de septembre deviendrait faux après coup.
    """
    if not jours_ouverts_mois:
        return 0.0
    planning = bascule is not None and jour >= bascule

    total = 0.0
    for e in employes or []:
        if not applicable(e, jour):
            continue
        if planning and _est_extra(e):
            continue    # son coût vient de ses shifts, plus de son montant mensuel
        total += cout_employe_mensuel(e) / jours_ouverts_mois

    if not planning:
        return total

    # ⚠️ ON PASSE PAR `services_du_jour`, PAS PAR LA LISTE BRUTE. Une règle produit des services
    # qui n'existent pas en base : les ignorer ici ferait un planning qui affiche quelqu'un et
    # un point mort qui ne le compte pas — deux écrans d'accord sur l'horaire et en désaccord
    # sur le prix.
    for s in services_du_jour(jour, regles, shifts):
        fiche = fiche_du_jour(employes, s.get("person_id"), jour)
        # ⚠️ SEULS LES EXTRAS SONT FACTURÉS À L'HEURE. Un permanent inscrit au planning est déjà
        # compté dans sa paie lissée : ajouter ses heures le paierait deux fois.
        if fiche is not None and _est_extra(fiche):
            total += cout_shift(s, employes)
    return total


def jours_ouverts_du_mois(jour, est_ouvert):
    """
    Le nombre de jours réellement ouverts dans le mois de `jour`.

    ⚠️ C'EST LE DIVISEUR DE TOUTE PAIE LISSÉE, ET IL ÉTAIT UNE CONSTANTE. `JOURS_OUVERTS_MOIS`
    valait 21,25, saisi à la main depuis le business plan, alors que le calendrier d'ouverture
    est connu et donne ~21,7. Deux réglages qui décrivent la même chose finissent toujours par
    diverger — le fichier de config le disait déjà de lui-même.
    """
    premier = date(jour.year, jour.month, 1)
    dernier = (date(jour.year + 1, 1, 1) if jour.month == 12
               else date(jour.year, jour.month + 1, 1)) - timedelta(1)
    return len(jours_ouverts_entre(premier, dernier, est_ouvert))


def cout_periode_planning(charges, employes, shifts, jours_ouverts, est_ouvert, bascule,
                          regles=None):
    """
    Le coût d'une période, jour par jour, planning compris.

    ⚠️ CHAQUE JOUR A SON PROPRE DIVISEUR. Une période qui enjambe deux mois n'a pas un nombre
    de jours ouverts unique — février et mars n'en ont pas le même compte, et diviser tout par
    une moyenne ferait porter à février des charges de mars.

    Renvoie `(total_fixes, total_personnel, par_jour)` où `par_jour` donne, pour chaque date,
    le coût du jour — c'est lui que la courbe du dashboard trace, et sans lui la ligne de point
    mort resterait horizontale sur un coût qui ne l'est plus.
    """
    if not jours_ouverts:
        return 0.0, 0.0, {}
    fixes = perso = 0.0
    par_jour = {}
    ouverts_mois = {}
    for j in jours_ouverts:
        cle = (j.year, j.month)
        if cle not in ouverts_mois:
            ouverts_mois[cle] = jours_ouverts_du_mois(j, est_ouvert)
        n = ouverts_mois[cle]
        if not n:
            continue
        f = charges_mensuelles(charges, j) / n
        p = personnel_du_jour(employes, shifts, j, n, bascule, regles)
        fixes += f
        perso += p
        par_jour[j] = {"fixes": f, "personnel": p, "total": f + p}
    return fixes, perso, par_jour


def jours_ouverts_entre(debut, fin, est_ouvert):
    """Les dates réellement ouvertes d'une période, bornes incluses."""
    out, j = [], debut
    while j <= fin:
        if est_ouvert(j):
            out.append(j)
        j += timedelta(1)
    return out
