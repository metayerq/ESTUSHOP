"""
CE QU'UNE CAMPAGNE A RÉELLEMENT PRODUIT — ET CE QU'ON NE PEUT PAS EN DIRE.

⚠️ UNE CAMPAGNE SMS N'ATTIRE PERSONNE DE NOUVEAU, PAR CONSTRUCTION. Pour recevoir un message, il
faut un numéro rattaché à une carte, donc être déjà client. Ce qu'une campagne peut faire, c'est
faire revenir quelqu'un PLUS TÔT qu'il ne serait revenu. Mesurer « combien de nouveaux clients »
n'a pas de sens ici, et un écran qui l'afficherait mentirait par sa seule existence.

⚠️ ET « 30 % SONT VENUS DANS LA SEMAINE » NE PROUVE RIEN. Ce sont des habitués : ils seraient
peut-être venus de toute façon. Le seul chiffre honnête est une COMPARAISON — les mêmes
personnes, la même durée, juste avant l'envoi. Ça ne démontre toujours pas la causalité (une
semaine ensoleillée suffit à tout expliquer), mais ça élimine la confusion la plus grossière :
prendre l'habitude d'un client pour l'effet d'un message.

La seule mesure qui prouverait quelque chose est un groupe témoin — retenir au hasard une part
des destinataires et comparer. À quarante destinataires, il faudrait des mois pour que l'écart
sorte du bruit ; c'est pourquoi ce module ne prétend pas le faire.
"""

from points import parse_ts

# La fenêtre de mesure, en jours.
#
# ⚠️ SEPT JOURS EXACTEMENT, ET PAS CINQ NI DIX. Le café ferme mardi et mercredi : seule une
# fenêtre d'une semaine pleine contient le même nombre de jours d'ouverture avant et après, quel
# que soit le jour d'envoi. Une fenêtre de cinq jours comparerait un week-end à deux jours de
# fermeture, et la campagne aurait l'air d'un triomphe ou d'un échec selon le jour du clic.
FENETRE_JOURS = 7
JOUR_MS = 86_400_000


def visites_par_telephone(visites, liens):
    """
    Regroupe les passages par personne. Une personne = un numéro, plusieurs cartes.

    ⚠️ COMPTER PAR CARTE FAUSSERAIT TOUT. Quelqu'un qui paie tantôt avec sa carte physique,
    tantôt avec son Apple Pay, compterait pour deux clients — et « deux clients sur quarante »
    au lieu d'« un sur quarante » double l'efficacité apparente de la campagne.
    """
    par_fp = {}
    for l in liens or []:
        fp, tel = l.get("fp"), l.get("phone")
        if fp and tel:
            par_fp[fp] = tel

    sortie = {}
    for v in visites or []:
        tel = par_fp.get(v.get("fp"))
        if not tel:
            continue
        ts = parse_ts(v.get("ts"))
        if ts is None:
            continue
        # ⚠️ LE JOUR EST TRANCHÉ DANS LA CHAÎNE D'ORIGINE, comme partout ailleurs dans ce projet.
        # Le recalculer depuis les millisecondes en heure locale ferait basculer d'un jour les
        # passages du soir pendant l'heure d'été — et « deux jours distincts » deviendrait « un ».
        jour = str(v.get("ts") or "")[:10]
        sortie.setdefault(tel, []).append((ts, int(v.get("amount") or 0), jour))
    for tel in sortie:
        sortie[tel].sort()
    return sortie


def _fenetre(passages, debut_ms, fin_ms):
    """Combien de passages et combien d'euros, entre deux instants. Borne haute exclue."""
    retenus = [p for p in passages if debut_ms <= p[0] < fin_ms]
    return {
        "visites": len(retenus),
        # ⚠️ LES JOURS DISTINCTS, PAS LES TICKETS. Deux cafés payés séparément le même matin sont
        # une venue, pas deux — et c'est « est-il venu » qu'on mesure.
        "jours": len({p[2] for p in retenus}),
        "cents": sum(p[1] for p in retenus),
    }


def effet_campagne(campagne, destinataires, passages_par_tel, fenetre_jours=FENETRE_JOURS):
    """
    Ce qui s'est passé après l'envoi, comparé à juste avant, sur LES MÊMES personnes.

    `destinataires` : les numéros qui ont reçu ce message (registre `card_notices`).
    `passages_par_tel` : la sortie de `visites_par_telephone`.

    ⚠️ LA COMPARAISON PORTE SUR LES MÊMES GENS, ET C'EST TOUT L'INTÉRÊT. Comparer les
    destinataires aux non-destinataires n'apprendrait rien : les seconds n'ont pas consenti au
    démarchage, ou ne remplissaient pas le critère — ils diffèrent déjà par ce qui a servi à les
    choisir.
    """
    envoi = parse_ts(campagne.get("sent_at"))
    if envoi is None or not destinataires:
        return None

    largeur = fenetre_jours * JOUR_MS
    avant = {"visites": 0, "jours": 0, "cents": 0}
    apres = {"visites": 0, "jours": 0, "cents": 0}
    venus_avant = venus_apres = 0
    # ⚠️ CEUX QUI N'ÉTAIENT PAS VENUS AVANT ET QUI REVIENNENT : le seul groupe où l'effet d'un
    # message est plausible. Un habitué qui vient chaque semaine serait venu sans nous.
    reveilles = 0

    for tel in destinataires:
        p = passages_par_tel.get(tel, [])
        a = _fenetre(p, envoi - largeur, envoi)
        b = _fenetre(p, envoi, envoi + largeur)
        for cle in avant:
            avant[cle] += a[cle]
            apres[cle] += b[cle]
        if a["visites"]:
            venus_avant += 1
        if b["visites"]:
            venus_apres += 1
        if not a["visites"] and b["visites"]:
            reveilles += 1

    # ⚠️ LA FENÊTRE PEUT ÊTRE INCOMPLÈTE, ET IL FAUT LE DIRE. Une campagne envoyée hier n'a pas
    # encore eu sa semaine : afficher « 2 venus » sans préciser que six jours manquent ferait
    # conclure à un échec le lendemain d'un envoi.
    return {
        "slug": campagne.get("slug"),
        "sent_at": campagne.get("sent_at"),
        "destinataires": len(destinataires),
        "fenetre_jours": fenetre_jours,
        "avant": avant,
        "apres": apres,
        "venus_avant": venus_avant,
        "venus_apres": venus_apres,
        "reveilles": reveilles,
        "delta_cents": apres["cents"] - avant["cents"],
        "cout_cents": campagne.get("cout_centimes") or 0,
    }


def complete(effet, maintenant):
    """
    La fenêtre est-elle écoulée ? Et sinon, combien de jours manquent.

    ⚠️ SANS CE DRAPEAU, TOUTE CAMPAGNE RÉCENTE PARAÎT RATÉE. On la lit le lendemain, on voit
    deux venues au lieu de douze, et on en tire une conclusion sur un message qui n'a pas encore
    eu le temps d'agir.
    """
    envoi = parse_ts(effet.get("sent_at")) if effet else None
    if envoi is None:
        return {"complete": False, "jours_restants": None}
    fin = envoi + effet["fenetre_jours"] * JOUR_MS
    # ⚠️ `maintenant` ARRIVE EN DATETIME, le reste du module en millisecondes. C'est le genre de
    # frontière où deux unités se rencontrent sans se le dire — et où un `>` compare un entier à
    # un objet, ou pire, deux entiers qui ne mesurent pas la même chose.
    maintenant_ms = parse_ts(maintenant)
    # ⚠️ UNE HORLOGE ILLISIBLE VEUT DIRE « JE NE SAIS PAS », JAMAIS « c'est fini ». Répondre
    # « complète » ferait lire une campagne d'hier comme un résultat définitif.
    if maintenant_ms is None:
        return {"complete": False, "jours_restants": None}
    if maintenant_ms >= fin:
        return {"complete": True, "jours_restants": 0}
    return {"complete": False, "jours_restants": max(1, -(-(fin - maintenant_ms) // JOUR_MS))}


def recap_depense(campagnes):
    """
    Ce que les campagnes ont coûté, par mois.

    ⚠️ CE N'EST PAS LA FACTURE TWILIO TOTALE, ET L'ÉCRAN DOIT LE DIRE. Les SMS de passage, de
    bienvenue et d'expiration partent de la caisse sans passer par ce journal : ils ne sont pas
    comptés ici. Présenter ce chiffre comme « la dépense SMS » ferait sous-estimer la facture
    d'un facteur dix, puisque le passage est de loin le plus fréquent.
    """
    par_mois = {}
    total_cents = total_messages = total_segments = 0
    for c in campagnes or []:
        ts = parse_ts(c.get("sent_at"))
        if ts is None:
            continue
        mois = str(c.get("sent_at"))[:7]
        cout = int(c.get("cout_centimes") or 0)
        envoyes = int(c.get("recipients") or 0)
        segments = int(c.get("segments") or 0)
        e = par_mois.setdefault(mois, {"mois": mois, "campagnes": 0, "messages": 0,
                                       "segments": 0, "cents": 0})
        e["campagnes"] += 1
        e["messages"] += envoyes
        e["segments"] += segments
        e["cents"] += cout
        total_cents += cout
        total_messages += envoyes
        total_segments += segments

    return {
        "mois": sorted(par_mois.values(), key=lambda m: m["mois"], reverse=True),
        "total_cents": total_cents,
        "messages": total_messages,
        "segments": total_segments,
        # ⚠️ LE COÛT PAR MESSAGE EST CE QUI SE COMPARE D'UNE CAMPAGNE À L'AUTRE. Un texte qui
        # passe à deux segments double cette ligne sans que le nombre de destinataires bouge.
        "cents_par_message": round(total_cents / total_messages, 1) if total_messages else 0,
    }
