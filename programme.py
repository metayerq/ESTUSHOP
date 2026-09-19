"""
LE PROGRAMME DE FIDÉLITÉ VU DU BUREAU — comptes, listes, et ce qu'il coûte.

`points.py` calcule le solde d'UN client, à l'identique de la caisse. Ce fichier-ci répond aux
questions qu'on ne se pose qu'assis : combien de clients, combien de points en circulation,
qui va bientôt réclamer sa boisson, qui n'est pas revenu.

⚠️ RIEN ICI NE TOUCHE À SUPABASE. Tout est fonction pure : on passe les lignes, on reçoit les
comptes. C'est ce qui permet de tester la règle « habitué à risque » sans base de données, et
donc de la tester vraiment.

── CE QU'EST UN « COMPTE », ET POURQUOI CE N'EST PAS ÉVIDENT ──────────────────────────────────

Un client est reconnu de deux façons, et elles ne se recouvrent pas :

  • par l'EMPREINTE de sa carte bancaire, dès le premier passage, sans rien lui demander ;
  • par son TÉLÉPHONE, s'il a accepté de le donner — et ce téléphone peut rassembler
    PLUSIEURS cartes (la physique, l'Apple Pay, celle de son conjoint).

Un compte est donc soit un téléphone avec ses cartes, soit une carte orpheline. ⚠️ ET LES
CARTES ORPHELINES SONT LA MAJORITÉ : les ignorer ferait croire que le programme compte trente
clients alors qu'il en voit trois cents. C'est la mesure qui dit si le programme progresse.
"""

from datetime import datetime, time, timedelta, timezone

from points import EXPIRY_MONTHS, absence_threshold_days, loyalty_state, parse_ts

# Nombre de passages à partir duquel une carte est un « habitué ». Règle d'ESTUSHOP, reprise
# telle quelle par la caisse : les deux doivent désigner les mêmes gens.
REGULAR_AFTER_VISITS = 4

# ⚠️ EN DESSOUS, ON NE PARLE PAS D'UN DÉPART. Une carte vue deux fois n'a pas d'habitude dont
# on puisse constater l'interruption ; l'annoncer « à risque » remplirait la liste de gens qui
# ne sont jamais venus qu'en passant, et une liste qu'on cesse de croire est une liste morte.
MIN_VISITS_FOR_RISK = REGULAR_AFTER_VISITS

# Points à partir desquels une récompense est « imminente » — de quoi prévoir le coût du mois,
# et de quoi relancer quelqu'un avec quelque chose de vrai à lui dire.
NEAR_REWARD_RATIO = 0.8

_MS_PAR_JOUR = 86_400_000


def _jour(ts):
    """Le jour civil d'un horodatage, en `AAAA-MM-JJ`. `None` s'il est illisible."""
    ms = parse_ts(ts)
    if ms is None:
        return None
    return ts[:10] if isinstance(ts, str) and len(ts) >= 10 else None


def build_accounts(visits, rewards, links, customers, threshold, now,
                   expiry_months=EXPIRY_MONTHS):
    """
    Regroupe les lignes brutes en comptes, chacun avec son solde et son état.

    `visits`    : {fp, ts, amount_cents}          — table `card_visits`
    `rewards`   : {fp, ts, points_spent, ...}     — table `card_rewards`
    `links`     : {fp, phone}                     — table `card_links`
    `customers` : {phone, name, token, consent_at, opted_out_at} — table `card_customers`

    ⚠️ UNE CARTE LIÉE À UN TÉLÉPHONE INCONNU RESTE UN COMPTE. Une ligne de `card_links` sans
    `card_customers` en face — migration à moitié passée, suppression partielle — ne doit pas
    faire disparaître les points de quelqu'un. Le compte existe, il est simplement sans nom.
    """
    par_phone = {}
    for l in links or []:
        fp, tel = l.get("fp"), l.get("phone")
        if fp and tel:
            par_phone[fp] = tel

    fiches = {}
    for c in customers or []:
        tel = c.get("phone")
        if tel:
            fiches[tel] = c

    # Chaque compte rassemble les empreintes qui lui appartiennent.
    groupes = {}

    def _cle(fp):
        tel = par_phone.get(fp)
        return ("phone", tel) if tel else ("card", fp)

    def _groupe(fp):
        k = _cle(fp)
        g = groupes.get(k)
        if g is None:
            g = {"kind": k[0], "id": k[1], "fps": set(), "visits": [], "rewards": []}
            groupes[k] = g
        g["fps"].add(fp)
        return g

    for v in visits or []:
        fp = v.get("fp")
        if fp:
            _groupe(fp)["visits"].append(v)

    for r in rewards or []:
        fp = r.get("fp")
        if fp:
            _groupe(fp)["rewards"].append(r)

    # ⚠️ UN CLIENT INSCRIT QUI N'A ENCORE RIEN PAYÉ DOIT EXISTER. Il a donné son numéro, reçu
    # son SMS de bienvenue : ne pas le lister le rendrait introuvable au comptoir le jour où il
    # demande où en est son compte.
    for fp, tel in par_phone.items():
        _groupe(fp)

    comptes = []
    for (kind, ident), g in groupes.items():
        etat = loyalty_state(g["visits"], g["rewards"], threshold, now, expiry_months)

        jours = sorted({j for j in (_jour(v.get("ts")) for v in g["visits"]) if j})
        seuil_absence = absence_threshold_days(jours)

        depuis = None
        dernier_ms = max(
            (ms for ms in (parse_ts(v.get("ts")) for v in g["visits"]) if ms is not None),
            default=None,
        )
        if dernier_ms is not None:
            maintenant_ms = int(now.astimezone(timezone.utc).timestamp() * 1000)
            depuis = max(0, (maintenant_ms - dernier_ms) // _MS_PAR_JOUR)

        fiche = fiches.get(ident) if kind == "phone" else None
        habitue = etat["visits"] >= REGULAR_AFTER_VISITS

        comptes.append({
            "key": f"{kind}:{ident}",
            "kind": kind,
            "phone": ident if kind == "phone" else None,
            "fps": sorted(g["fps"]),
            "name": (fiche or {}).get("name"),
            "token": (fiche or {}).get("token"),
            "consent_at": (fiche or {}).get("consent_at"),
            "opted_out": bool((fiche or {}).get("opted_out_at")),
            # ⚠️ UN TÉLÉPHONE SANS FICHE EST SIGNALÉ, PAS MASQUÉ. C'est une incohérence de base,
            # et la seule façon qu'elle se répare est que quelqu'un la voie.
            "orphan": kind == "phone" and fiche is None,
            "state": etat,
            "visit_days": jours,
            "distinct_days": len(jours),
            "absence_threshold_days": seuil_absence,
            "days_since_last": depuis,
            "regular": habitue,
            "at_risk": (
                etat["visits"] >= MIN_VISITS_FOR_RISK
                and depuis is not None
                and seuil_absence is not None
                and depuis > seuil_absence
            ),
        })

    # Les plus récents d'abord ; ceux qui ne sont jamais venus à la fin.
    comptes.sort(key=lambda c: (c["days_since_last"] is None, c["days_since_last"] or 0))
    return comptes


def programme_summary(comptes, threshold, reward_cost_cents):
    """
    Les chiffres qui décident quelque chose. Pas une galerie de graphiques.

    `reward_cost_cents` : ce que coûte RÉELLEMENT une boisson offerte (sa matière, pas son
    prix de vente). ⚠️ VALORISER LE PASSIF AU PRIX DE CARTE MULTIPLIERAIT LA DETTE PAR CINQ et
    ferait paraître effrayant un programme qui coûte quelques dizaines d'euros par mois.
    """
    liés = [c for c in comptes if c["kind"] == "phone"]
    cartes = [c for c in comptes if c["kind"] == "card"]

    # ⚠️ LE TAUX DE LIAISON SE MESURE SUR LES CARTES QUI REVIENNENT, PAS SUR TOUTES. Un passant
    # unique n'avait aucune raison de donner son numéro : le compter au dénominateur ferait
    # baisser le taux chaque fois qu'un touriste entre, et la mesure ne dirait plus rien de
    # l'effort fait au comptoir.
    revenants = [c for c in comptes if c["state"]["visits"] >= 2]
    revenants_liés = [c for c in revenants if c["kind"] == "phone"]

    points_en_circulation = sum(c["state"]["balance_points"] for c in comptes)
    points_périmés = sum(c["state"]["expired_points"] for c in comptes)
    points_consommés = sum(c["state"]["spent_points"] for c in comptes)
    dues = sum(c["state"]["rewards_due"] for c in comptes)

    proche = int(threshold * NEAR_REWARD_RATIO) if threshold > 0 else 0
    bientôt = [
        c for c in comptes
        if c["state"]["rewards_due"] == 0 and c["state"]["balance_points"] >= proche > 0
    ]

    # Le passif : ce que coûterait la totalité des soldes s'ils étaient tous réclamés demain.
    boissons_dues = (points_en_circulation // threshold) if threshold > 0 else 0

    émis = points_en_circulation + points_périmés + points_consommés
    return {
        "accounts": len(comptes),
        "linked": len(liés),
        "cards_unlinked": len(cartes),
        "returning": len(revenants),
        "returning_linked": len(revenants_liés),
        # ⚠️ `None` ET NON `0` QUAND IL N'Y A PERSONNE. Un taux de 0 % se lit comme un échec ;
        # l'absence de mesure se lit comme ce qu'elle est.
        "link_rate_pct": (
            round(len(revenants_liés) * 100.0 / len(revenants), 1) if revenants else None
        ),
        "opted_out": sum(1 for c in comptes if c["opted_out"]),
        "orphan_links": sum(1 for c in comptes if c["orphan"]),
        "points_outstanding": points_en_circulation,
        "points_expired": points_périmés,
        "points_spent": points_consommés,
        "points_issued": émis,
        # Combien de points émis ont fini dans un verre, plutôt qu'à la poubelle du calendrier.
        "redemption_rate_pct": round(points_consommés * 100.0 / émis, 1) if émis else None,
        "rewards_due_now": dues,
        "liability_cents": boissons_dues * reward_cost_cents,
        "at_risk": [c for c in comptes if c["at_risk"]],
        "near_reward": sorted(bientôt, key=lambda c: -c["state"]["balance_points"]),
        "regulars": sum(1 for c in comptes if c["regular"]),
    }


# ══════════════════════════════════════════════════════════════════════════════
# LE SUIVI DE CONVERSION — combien de clients ont donné leur numéro, semaine après semaine
# ══════════════════════════════════════════════════════════════════════════════
#
# ⚠️ UN TAUX SEUL NE DIT PAS SI ÇA MARCHE. « 18 % » ne répond pas à la question qu'on se pose
# vraiment quand on commence à demander les numéros au comptoir : est-ce que ça monte ? Un
# chiffre unique se lit comme un jugement ; une courbe se lit comme un résultat, et elle dit en
# plus quelle semaine a été bonne — donc quelle façon de demander a marché.
#
# ⚠️ ET LE DÉNOMINATEUR BOUGE AUSSI. Chaque semaine amène de nouveaux clients revenus, qui n'ont
# pas encore eu l'occasion de donner leur numéro. Calculer le taux passé avec le dénominateur
# d'aujourd'hui écraserait les débuts — on recalcule donc l'état du monde à la fin de CHAQUE
# semaine : qui était revenu, qui était déjà rattaché.


def _lundi(d):
    """Le lundi de la semaine de `d`."""
    return d - timedelta(days=d.weekday())


def _instant(jour, tz):
    """Minuit, ce jour-là, à l'heure du café — pas à celle du serveur."""
    return int(datetime.combine(jour, time(0, 0), tzinfo=tz).timestamp() * 1000)


def conversion_series(visits, links, customers, now, weeks=12):
    """
    La progression du rattachement, semaine par semaine.

    ⚠️ ON COMPTE LES CARTES QUI REVIENNENT, PAS TOUS LES PASSANTS. Un touriste venu une fois
    n'avait aucune raison de donner son numéro : au dénominateur, il ferait baisser le taux
    chaque fois qu'un inconnu entre, et la courbe mesurerait la fréquentation au lieu de
    l'effort fait au comptoir.

    ⚠️ UN RATTACHEMENT SANS DATE NE PEUT PAS ÊTRE PLACÉ SUR LA COURBE. `linked_at` peut manquer
    (ligne ancienne, migration). On se rabat sur la date de consentement du numéro ; s'il n'y en
    a pas non plus, la ligne est comptée dans `undated` et DITE, jamais rangée d'office au début
    — ce qui gonflerait les premières semaines et ferait croire à un départ en fanfare.
    """
    tz = now.tzinfo or timezone.utc
    maintenant = int(now.timestamp() * 1000)

    # Le deuxième passage de chaque carte : l'instant où elle devient « revenue ».
    passages = {}
    for v in visits or []:
        fp, ms = v.get("fp"), parse_ts(v.get("ts"))
        if fp and ms is not None:
            passages.setdefault(fp, []).append(ms)
    revenue_a = {fp: sorted(ms)[1] for fp, ms in passages.items() if len(ms) >= 2}

    consentement = {}
    for c in customers or []:
        tel, ms = c.get("phone"), parse_ts(c.get("consent_at"))
        if tel and ms is not None:
            consentement[tel] = ms

    # Quand chaque carte a été rattachée.
    rattache_a, undated = {}, 0
    for l in links or []:
        fp = l.get("fp")
        if not fp:
            continue
        ms = parse_ts(l.get("linked_at"))
        if ms is None:
            ms = consentement.get(l.get("phone"))
        if ms is None:
            undated += 1
            continue
        rattache_a[fp] = min(ms, rattache_a[fp]) if fp in rattache_a else ms

    # Les numéros, eux, se comptent en PERSONNES : deux cartes rattachées au même téléphone,
    # c'est un client convaincu, pas deux.
    inscrits = sorted(consentement.values())

    fin_semaine = _lundi(now.date()) + timedelta(days=7)
    lignes = []
    for i in range(weeks - 1, -1, -1):
        debut = _instant(fin_semaine - timedelta(days=7 * (i + 1)), tz)
        fin = min(_instant(fin_semaine - timedelta(days=7 * i), tz), maintenant)
        if fin <= debut:
            continue

        revenus = [fp for fp, ms in revenue_a.items() if ms <= fin]
        rattaches = [fp for fp in revenus if rattache_a.get(fp, maintenant + 1) <= fin]
        lignes.append({
            "start": datetime.fromtimestamp(debut / 1000, tz).date().isoformat(),
            "returning": len(revenus),
            "linked": len(rattaches),
            # ⚠️ `None` ET NON `0` QUAND PERSONNE N'EST ENCORE REVENU. Un taux de 0 % se lit
            # comme un échec ; l'absence de mesure se lit comme ce qu'elle est.
            "rate_pct": round(len(rattaches) * 100.0 / len(revenus), 1) if revenus else None,
            "new_links": sum(1 for ms in rattache_a.values() if debut <= ms < fin),
            "new_customers": sum(1 for ms in inscrits if debut <= ms < fin),
        })

    derniere = lignes[-1] if lignes else None
    return {
        "weeks": lignes,
        "undated_links": undated,
        "customers_total": len(inscrits),
        "opted_out": sum(1 for c in (customers or []) if c.get("opted_out_at")),
        "this_week_customers": derniere["new_customers"] if derniere else 0,
        "this_week_links": derniere["new_links"] if derniere else 0,
    }
