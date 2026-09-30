# -*- coding: utf-8 -*-
"""
FACTURER UN TIERS — LA RÈGLE, PAS L'ÉCRAN.

Porté depuis `apps/pos/lib/invoice.ts` le 30/09/2026, en même temps que l'écran quittait la
caisse. ⚠️ CHAQUE RÈGLE CI-DESSOUS A ÉTÉ PAYÉE UNE FOIS ; les commentaires disent par quoi.

Le geste est rare — UNE facture à tiers en 72 jours, un FR de 136,50 € le 08/09/2026 — donc la
vitesse n'est pas le critère, la justesse l'est. Une facture ne se corrige pas : elle se répare
par note de crédit.
"""
from datetime import date, timedelta

# Les identifiants de taux tels que Vendus les nomme.
TAX_IDS = {0: "ISE", 6: "RED", 13: "INT", 23: "NOR"}
TAUX_VALIDES = (0, 6, 13, 23)


def nif_valide(nif):
    """
    Le NIF portugais porte une clé de contrôle modulo 11.

    ⚠️ NEUF CHIFFRES NE SUFFISENT PAS. Une transposition — 332457389 tapé 332457839 — passe un
    contrôle de longueur, atterrit sur un document fiscal au nom de personne, et ne se répare
    que par note de crédit. Dix lignes l'attrapent avant l'émission.

    Vérifié sur les deux NIF réels du dossier : 332457389 (l'acquéreur de la facture du
    08/09/2026) et 519091647 (Quiet Frequency, l'émetteur).
    """
    n = (nif or "").strip()
    if len(n) != 9 or not n.isdigit():
        return False
    # Les premiers chiffres attribués au Portugal. Un préfixe inconnu n'est pas un NIF.
    if n[0] not in "125689" and n[:2] not in ("30", "31", "32", "33", "34", "35", "36",
                                              "37", "38", "39", "45", "70", "71", "72",
                                              "74", "75", "77", "78", "79", "90", "91",
                                              "98", "99"):
        return False
    total = sum(int(n[i]) * (9 - i) for i in range(8))
    cle = 11 - (total % 11)
    if cle >= 10:
        cle = 0
    return cle == int(n[8])


def montant_cents_strict(texte):
    """
    Un montant lu au clavier, ou `None`.

    ⚠️ `parseFloat` AVALE EN SILENCE. « 1.365,00 » — le format portugais avec séparateur de
    milliers — devient 1,37 € au lieu de 1 365,00 €. « 13,650 » devient 13,65 €. « 1a36 »
    devient 1 €. Chacun de ces trois produit un document irréversible d'un montant que personne
    n'a voulu. On exige donc une forme, et on refuse tout le reste au lieu de l'interpréter.
    """
    t = (texte or "").strip().replace(" ", "").replace("\u00a0", "")
    if not t:
        return None
    # Séparateur de milliers portugais : on ne l'accepte QUE bien formé, jamais au hasard.
    if t.count(".") == 1 and t.count(",") == 1 and t.index(".") < t.index(","):
        t = t.replace(".", "")
    t = t.replace(",", ".")
    import re as _re
    if not _re.fullmatch(r"\d{1,9}(\.\d{1,2})?", t):
        return None
    return round(float(t) * 100)


def _rempli(v):
    """Une chaîne vide, ou faite d'espaces, n'est pas une donnée."""
    return isinstance(v, str) and v.strip() != ""


def ligne_ttc_unitaire(ligne):
    """
    Le TTC unitaire d'une ligne, en centimes — ce qui part réellement chez Vendus.

    ⚠️ UN MONTANT SAISI TTC EST RENVOYÉ TEL QUEL. « J'ai reçu 136,50 € » doit produire une
    facture de 136,50 €, pas de 136,51 €. Le document réel du 08/09/2026 le montre : 136,50 €
    TTC à 23 % donnent 110,98 € HT, qui redonneraient 136,51 € — un centime de plus, sur un
    document irréversible. Mesuré sur les montants de 0,01 € à 20 000 € : 18,7 % des TTC à 23 %
    ne survivent pas cet aller-retour (11,5 % à 13 %, 5,7 % à 6 %).

    ⚠️ ET LA CONVERSION HT → TTC EST LE SEUL SENS SANS PERTE. Zéro divergence sur les mêmes
    200 000 montants. On ne convertit donc que dans ce sens.
    """
    c = int(ligne["montant_cents"])
    if ligne.get("ttc"):
        return c
    return round(c * (1 + int(ligne["taux"]) / 100))


def totaux(lignes):
    """
    Les totaux d'un brouillon.

    ⚠️ LA TVA SE CALCULE PAR TAUX, JAMAIS SUR LA SOMME. Une facture qui mélange un catering à
    13 % et une commission à 23 % n'a pas « un » taux : appliquer celui de la première ligne au
    total, ou une moyenne, produit une TVA fausse — donc une facture fausse, déclarée telle
    quelle.

    ⚠️ ET ON PART DU TTC, parce que c'est lui qui est envoyé. La base et la TVA se DÉDUISENT du
    total, exactement comme Vendus les déduit. La TVA est le RESTE, jamais un second arrondi :
    base + TVA doit retomber sur le total au centime, sans quoi la facture ne s'additionne pas
    elle-même.
    """
    par_taux = {}
    for l in lignes:
        brut = ligne_ttc_unitaire(l) * int(l["qty"])
        t = int(l["taux"])
        par_taux[t] = par_taux.get(t, 0) + brut

    detail = []
    for taux in sorted(par_taux):
        brut = par_taux[taux]
        net = round(brut / (1 + taux / 100))
        detail.append({"taux": taux, "net_cents": net, "tva_cents": brut - net})

    net = sum(d["net_cents"] for d in detail)
    tva = sum(d["tva_cents"] for d in detail)
    return {"net_cents": net, "tva_cents": tva, "ttc_cents": net + tva, "par_taux": detail}


def manques(brouillon):
    """
    Tout ce qui manque pour émettre, nommé — jamais un simple booléen.

    ⚠️ ON RENVOIE LA LISTE ENTIÈRE, PAS LE PREMIER MANQUE. Un écran qui révèle les défauts un
    par un fait remplir un champ, refuse, en fait remplir un autre, refuse encore.
    """
    m = []
    c = brouillon.get("client")
    if not c:
        m.append("client")
    else:
        # ⚠️ LE NOM EST EXIGÉ ICI, PAS SEULEMENT PAR VENDUS. Une vingtaine de fiches du compte
        # portent un NIF et un nom VIDE — créées par les NIF tapés au comptoir. Reprendre l'une
        # d'elles telle quelle produirait une facture sans acquéreur nommé.
        if not _rempli(c.get("nom")):
            m.append("client-nom")
        if not nif_valide(c.get("nif")):
            m.append("client-nif")
        if not _rempli(c.get("adresse")) or not _rempli(c.get("ville")):
            m.append("client-adresse")

    lignes = brouillon.get("lignes") or []
    if not lignes:
        m.append("lignes")
    # ⚠️ UNE SEULE LIGNE FAUTIVE SUFFIT À BLOQUER. Émettre les lignes valides et taire les
    # autres produirait une facture d'un montant inférieur à celui qui a été relu.
    if any(not _rempli(l.get("libelle")) for l in lignes):
        m.append("ligne-libelle")
    if any(not isinstance(l.get("montant_cents"), int) or l["montant_cents"] <= 0 for l in lignes):
        m.append("ligne-montant")
    # ⚠️ SANS FICHE DE PRESTATION, VENDUS CRÉE UN PRODUIT dans le catalogue de production.
    # Quelques factures suffiraient à le remplir de fiches fantômes portant le libellé d'une
    # facture et le prix d'un jour.
    if any(not isinstance(l.get("service_id"), int) or l["service_id"] <= 0 for l in lignes):
        m.append("ligne-prestation")
    if any(int(l.get("taux", -1)) not in TAUX_VALIDES for l in lignes):
        m.append("ligne-taux")
    if any(not isinstance(l.get("qty"), int) or l["qty"] <= 0 for l in lignes):
        m.append("ligne-qty")

    # ⚠️ UNE FT SANS ÉCHÉANCE EST UNE CRÉANCE SANS DATE. Elle n'apparaîtrait jamais comme en
    # retard, donc jamais dans une relance. Une FR n'en a pas : elle est déjà payée.
    if brouillon.get("type") == "FT":
        j = brouillon.get("delai_jours")
        if not isinstance(j, int) or j <= 0:
            m.append("delai")
    elif brouillon.get("type") != "FR":
        m.append("type")
    return m


def emettable(brouillon):
    return not manques(brouillon)


def date_echeance(aujourdhui, jours):
    """
    ⚠️ VENDUS VEUT UNE DATE, PAS UN DÉLAI. `date_due: "+30 days"` est refusé — « P006, O campo
    date_due não tem um valor válido para date ». Le délai est ce que l'utilisateur choisit ; la
    date est ce qui part.

    ⚠️ ET LE JOUR D'ÉMISSION EST UN PARAMÈTRE, jamais l'horloge lue ici : une facture émise à
    23 h 55 le 31 pourrait dater du mois suivant selon le fuseau.
    """
    return (aujourdhui + timedelta(days=int(jours))).isoformat()


def corps_facture(brouillon, register_id, mode, moyen_paiement_id=None, aujourdhui=None):
    """
    Le corps du `POST /documents/`.

    ⚠️ LÈVE PLUTÔT QUE D'ÉMETTRE UN DOCUMENT DÉGRADÉ. Un brouillon incomplet ne doit pas
    produire une facture « au mieux ». Lever se produit avant tout appel réseau — rien n'est
    parti, rien n'est à annuler.
    """
    m = manques(brouillon)
    if m:
        raise ValueError("facture incomplète : " + ", ".join(m))

    t = brouillon["type"]
    if t == "FR" and not isinstance(moyen_paiement_id, int):
        # Une FR est une facture ET un reçu : sans règlement, elle affirmerait un encaissement
        # dont elle ne sait rien.
        raise ValueError("une facture-reçu (FR) exige le moyen de règlement")
    if t == "FT" and not isinstance(aujourdhui, date):
        # Laisser Vendus dater l'échéance produirait une créance exigible le jour même,
        # invisible à toute relance.
        raise ValueError("une facture (FT) exige le jour d'émission pour son échéance")
    if not isinstance(register_id, int) or register_id <= 0:
        raise ValueError("caisse d'émission absente")
    if mode not in ("normal", "tests"):
        raise ValueError("mode fiscal invalide")

    c = brouillon["client"]
    client = {
        "fiscal_id": c["nif"].strip(),
        "name": c["nom"].strip(),
        "address": (c.get("adresse") or "").strip(),
        "postalcode": (c.get("code_postal") or "").strip(),
        "city": (c.get("ville") or "").strip(),
        "country": "PT",
    }
    if _rempli(c.get("email")):
        client["email"] = c["email"].strip()
        # ⚠️ L'ENVOI SE DEMANDE, IL NE SE DÉDUIT PLUS. Remplir le champ email posait
        # `send_email: yes` : le client recevait la facture sans que rien à l'écran ne l'annonce,
        # et reprendre une fiche connue qui portait un email suffisait à déclencher l'envoi.
        # Un effet de bord invisible sur un document fiscal est une décision prise à la place de
        # quelqu'un.
        if brouillon.get("envoyer_email"):
            client["send_email"] = "yes"

    corps = {
        "type": t,
        "mode": mode,
        "register_id": register_id,
        "return_qrcode": 1,
        "client": client,
        "items": [{
            "id": l["service_id"],
            "qty": int(l["qty"]),
            # Le libellé de CETTE facture — la fiche catalogue n'est pas touchée.
            "title": l["libelle"].strip(),
            # ⚠️ TTC, PARCE QUE VENDUS N'ACCEPTE PAS AUTRE CHOSE. Envoyer le HT sous-facturerait
            # de tout le montant de la TVA, sans qu'aucune erreur ne remonte.
            "gross_price": ligne_ttc_unitaire(l) / 100,
            "tax_id": TAX_IDS[int(l["taux"])],
        } for l in brouillon["lignes"]],
    }
    if t == "FT":
        corps["date_due"] = date_echeance(aujourdhui, brouillon["delai_jours"])
    else:
        corps["payments"] = [{"id": moyen_paiement_id}]
    return corps


# ══════════════════════════════════════════════════════════════════════════════════════════
# LES ACCÈS VENDUS
#
# ⚠️ SÉPARÉS DES RÈGLES CI-DESSUS, QUI RESTENT PURES. Tout ce qui précède se teste sans réseau
# et c'est ce qui a rendu le portage acceptable : réécrire des règles fiscales dans un autre
# langage sans tests aurait été un pari sur un document irréversible.
# ══════════════════════════════════════════════════════════════════════════════════════════

import os

BASE_VENDUS = "https://www.vendus.pt/ws/v1.1"
TAUX_PAR_ID = {"ISE": 0, "RED": 6, "INT": 13, "NOR": 23}


def caisse_et_mode(env=None):
    """
    La caisse d'émission et le mode fiscal.

    ⚠️ TOUT CE QUI N'EST PAS EXACTEMENT « normal » VAUT « tests ». Une variable absente, mal
    orthographiée ou vide ne doit pas produire de vrais documents fiscaux : c'est la seule
    erreur dont on se relève.

    ⚠️ ET SANS CAISSE, ON LÈVE. Laisser Vendus choisir émettrait sur une série qu'on ne croit
    pas — la facture réelle du 08/09/2026 est sur la caisse 342853246, en série FR 01P2026.
    """
    e = env if env is not None else os.environ
    brut = (e.get("VENDUS_REGISTER_ID") or "").strip()
    if not brut.isdigit() or int(brut) <= 0:
        raise ValueError("VENDUS_REGISTER_ID absente — aucune caisse d'émission")
    mode = "normal" if (e.get("VENDUS_MODE") or "").strip() == "normal" else "tests"
    return int(brut), mode


def _auth(env=None):
    e = env if env is not None else os.environ
    cle = (e.get("VENDUS_API_KEY") or "").strip()
    if not cle:
        raise ValueError("VENDUS_API_KEY absente")
    return (cle, "")


def _pages(req, chemin, champ, env=None, par_page=100, max_pages=20):
    """
    ⚠️ TOUTES LES PAGES, PAS LA PREMIÈRE. Le catalogue du café compte 112 produits et une page
    en rend 100 : lire une seule page rendait 12 fiches invisibles, dont pouvait faire partie
    celle qu'on venait de créer. L'écran disait « aucune prestation » à quelqu'un qui venait
    d'en créer une — un cul-de-sac silencieux.
    """
    out, page = [], 1
    while page <= max_pages:
        r = req.get(f"{BASE_VENDUS}{chemin}", auth=_auth(env),
                    params={"per_page": par_page, "page": page}, timeout=20)
        if r.status_code == 404:
            break
        r.raise_for_status()
        lot = r.json() or []
        if not isinstance(lot, list):
            break
        out.extend(lot)
        if len(lot) < par_page:
            break
        page += 1
    return out


def articles(req, env=None):
    """
    TOUT le catalogue actif, avec sa catégorie — et aucun filtre deviné.

    ⚠️ LE MARQUEUR « SANS CATÉGORIE » ÉTAIT FAUX, ET C'EST L'ÉCRAN QUI L'A DIT. Porté depuis la
    caisse, il devait distinguer les prestations facturables des produits vendus au comptoir :
    « les 112 produits actifs appartiennent tous à l'une des sept catégories ». En vrai, la
    liste ne rendait qu'un seul article — « sticks » — et la fiche de commission qui avait servi
    à la facture du 08/09/2026 n'y était pas. Le café n'a donc pas de fiches « service »
    séparées : la commission est une fiche ordinaire, avec une catégorie.

    ⚠️ ON NE REMPLACE PAS UN MARQUEUR FAUX PAR UN AUTRE. Rendre tout le catalogue et laisser
    choisir est la seule forme qui ne peut pas se tromper. Facturer une fiche vendable est
    d'ailleurs légitime — un sac de café facturé à une entreprise est une vente comme une autre.
    Les fiches sans catégorie sont simplement remontées en tête : ce sont les plus probables.
    """
    out = []
    for p in _pages(req, "/products/", "products", env):
        if p.get("status") == "off":
            continue
        out.append({
            "id": p.get("id"),
            "titre": (p.get("title") or "").strip(),
            "reference": (p.get("reference") or "").strip(),
            "categorie": p.get("category_id") or None,
            "taux": TAUX_PAR_ID.get(p.get("tax_id") or "", 23),
        })
    # Sans catégorie d'abord, puis par titre : un ordre stable, et les plus probables en tête.
    out.sort(key=lambda a: (a["categorie"] is not None, a["titre"].lower()))
    return out


def categories(req, env=None):
    """Le nom des catégories, pour que la liste dise « Coffee » et non « 342853712 »."""
    try:
        return {c.get("id"): (c.get("title") or "").strip()
                for c in _pages(req, "/products/categories/", "categories", env)}
    except Exception:
        # ⚠️ UN NOM DE CATÉGORIE MANQUANT NE DOIT PAS VIDER LA LISTE D'ARTICLES. C'est un
        # confort de lecture, pas une donnée dont dépend la facture.
        return {}


def moyens_paiement(req, env=None):
    r = req.get(f"{BASE_VENDUS}/documents/payments/", auth=_auth(env), timeout=20)
    r.raise_for_status()
    return [{"id": p.get("id"), "titre": p.get("title") or ""}
            for p in (r.json() or []) if p.get("status") != "off"]


def clients_connus(req, env=None):
    """
    Les fiches clients porteuses d'un NIF.

    ⚠️ CELLES QUI SONT INCOMPLÈTES SONT MARQUÉES, PAS CACHÉES. Une vingtaine de fiches du compte
    portent un NIF et un nom vide — créées par les NIF tapés au comptoir. Les masquer ferait
    ressaisir un client déjà connu ; les servir sans le dire produirait une facture sans
    acquéreur nommé.
    """
    out = []
    for c in _pages(req, "/clients/", "clients", env):
        nif = (c.get("fiscal_id") or "").strip()
        if not nif:
            continue
        fiche = {"id": c.get("id"), "nom": (c.get("name") or "").strip(), "nif": nif,
                 "adresse": (c.get("address") or "").strip(),
                 "code_postal": (c.get("postalcode") or "").strip(),
                 "ville": (c.get("city") or "").strip(),
                 "email": (c.get("email") or "").strip()}
        fiche["incomplet"] = not (fiche["nom"] and fiche["adresse"] and fiche["ville"])
        out.append(fiche)
    return out


def emettre(req, brouillon, env=None, aujourdhui=None):
    """
    Émet la facture et RELIT le document.

    ⚠️ AUCUNE RÉÉMISSION AUTOMATIQUE. Une requête qui échoue au réseau après le POST peut avoir
    abouti : réessayer facturerait deux fois le même client. On rend ce que Vendus a répondu, et
    l'écran décide quoi en dire — jamais un second essai silencieux.
    """
    register_id, mode = caisse_et_mode(env)
    corps = corps_facture(brouillon, register_id, mode,
                          moyen_paiement_id=brouillon.get("moyen_paiement_id"),
                          aujourdhui=aujourdhui or date.today())
    r = req.post(f"{BASE_VENDUS}/documents/", auth=_auth(env), json=corps, timeout=30)
    if not r.ok:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(f"Vendus a refusé (HTTP {r.status_code}) : {detail}")
    return r.json()


def derniere_facture(lignes_cache):
    """
    La dernière facture à tiers, rendue comme un brouillon prêt à reprendre.

    ⚠️ C'EST LA FONCTION LA PLUS UTILE DE CET ÉCRAN, ET ELLE VIENT DE L'USAGE. Une facture tous
    les deux mois : entre deux, personne ne se souvient du client, de la fiche, du taux ni du
    moyen de règlement. Retrouver tout ça à la main est exactement là où l'on se trompe — et se
    tromper produit un document qu'on ne peut plus retirer.

    ⚠️ ET ELLE LIT LE CACHE, PAS VENDUS. `live_docs_cache` porte déjà chaque journée avec ses
    documents complets : une question de plus à Vendus ajouterait une dépendance réseau et une
    incertitude d'API pour une donnée qu'on a sous la main.

    `lignes_cache` : les lignes {day, docs} du plus récent au plus ancien.
    """
    for r in lignes_cache or []:
        for doc in reversed(r.get("docs") or []):
            if doc.get("type") not in ("FT", "FR"):
                continue
            c = doc.get("client") or {}
            items = doc.get("items") or []
            paiements = doc.get("payments") or []
            return {
                "jour": r.get("day"),
                "numero": doc.get("number"),
                "type": doc.get("type"),
                "client": {"nom": (c.get("name") or "").strip(),
                           "nif": (c.get("fiscal_id") or "").strip(),
                           "adresse": (c.get("address") or "").strip(),
                           "code_postal": (c.get("postalcode") or "").strip(),
                           "ville": (c.get("city") or "").strip(),
                           "email": (c.get("email") or "").strip()},
                # ⚠️ LE MONTANT EST REPRIS EN TTC, parce que c'est ce qui avait été saisi et ce
                # qui est imprimé. Reprendre le HT ferait dériver d'un centime à la réémission.
                "lignes": [{"libelle": (it.get("title") or "").strip(),
                            "montant_cents": round(float(
                                (it.get("amounts") or {}).get("gross_unit") or 0) * 100),
                            "ttc": True,
                            "taux": int((it.get("tax") or {}).get("rate") or 23),
                            "qty": int(it.get("qty") or 1),
                            # ⚠️ L'IDENTIFIANT DU DOCUMENT EST CELUI DE LA LIGNE, PAS DU
                            # PRODUIT : le proposer ferait viser une fiche qui n'existe pas.
                            # C'est `resoudre_articles` qui le retrouve — voir ses quatre
                            # replis. La RÉFÉRENCE, elle, est le seul fil que Vendus laisse
                            # vers la fiche : « VCOM141-26090821 » porte « VCOM141 » devant.
                            "reference": (it.get("reference") or "").strip(),
                            "service_id": 0}
                           for it in items],
                "moyen_paiement": (paiements[0].get("title") if paiements else None),
            }
    return None


def pdf_document(req, doc_id, env=None):
    """
    Le PDF d'un document émis, en octets.

    `GET /documents/{id}/?output=pdf` répond 200 avec le PDF COMPLET encodé en base64 dans le
    champ `output` — chemin éprouvé par la caisse, repris tel quel.

    ⚠️ ON VÉRIFIE L'EN-TÊTE `%PDF-`. Le décodage base64 de Python est permissif : il ignore les
    caractères invalides au lieu d'échouer, et rendrait volontiers quelques octets de rien du
    tout sous le nom d'une facture.
    """
    import base64
    _, mode = caisse_et_mode(env)
    r = req.get(f"{BASE_VENDUS}/documents/{int(doc_id)}/", auth=_auth(env),
                params={"output": "pdf", "mode": mode}, timeout=30)
    r.raise_for_status()
    data = r.json()
    d = data[0] if isinstance(data, list) and data else data
    brut = (d or {}).get("output") or ""
    if not isinstance(brut, str) or not brut.strip():
        raise RuntimeError("Vendus n'a pas rendu de PDF pour ce document")
    b64 = brut.split(",", 1)[-1] if brut.startswith("data:") else brut
    octets = base64.b64decode("".join(b64.split()), validate=False)
    if not octets.startswith(b"%PDF-"):
        raise RuntimeError("la réponse de Vendus n'est pas un PDF")
    return octets


# ══════════════════════════════════════════════════════════════════════════════════════════
# RETROUVER L'ARTICLE D'UNE FACTURE REPRISE
#
# ⚠️ VENDUS NE REND PAS L'IDENTIFIANT DE LA FICHE. Ses lignes de document portent leur propre
# id ; le catalogue est ailleurs. Une reprise laissait donc un trou à combler à la main — sur le
# seul champ dont dépend la TVA et l'absence de fiche fantôme dans le catalogue de production.
#
# On enregistre donc désormais nos émissions (`faturas_emitidas`), ce qui rend le cas courant
# exact. Les quatre replis servent aux factures émises AVANT ce registre — dont la seule qui
# existe, FR 01P2026/1 du 08/09/2026.
# ══════════════════════════════════════════════════════════════════════════════════════════

def _prefixe_reference(ref):
    """
    « VCOM141-26090821 » → « vcom141 ».

    ⚠️ C'EST LE SEUL FIL QUE VENDUS LAISSE. La référence d'une ligne de document commence par
    celle de la fiche, suivie d'un tiret et d'un horodatage — motif observé sur la facture réelle
    et sur les ventes du comptoir (« VICE10-2606012 » pour l'Iced Americano). Si le motif ne tient
    pas, la comparaison échoue simplement et le repli suivant prend la main : rien n'est deviné.
    """
    t = (ref or "").strip().split("-")[0].strip().lower()
    return t or None


def resoudre_articles(brouillon, articles, registre=None, emissions=None):
    """
    Remplit `service_id` sur chaque ligne, et dit d'où vient la réponse.

    Dans l'ordre, du plus sûr au plus faible :

    0. `registre` — la ligne telle qu'on l'a émise. Exact, et c'est le cas courant désormais.
    1. le préfixe de référence rapproché du catalogue. Déterministe.
    2. la dernière émission portant le MÊME LIBELLÉ.
    3. la dernière émission pour le MÊME CLIENT.
    4. rien — le champ reste vide et la ligne le signale.

    ⚠️ ON NE DEVINE JAMAIS PAR RESSEMBLANCE DE TITRE. Un libellé surchargé — « Comissão sobre
    venda popup 15 agosto » — ne correspond à aucune fiche du catalogue, et le rapprocher « au
    plus proche » choisirait une fiche au hasard, donc un taux de TVA au hasard, sur un document
    irréversible. Mieux vaut un champ vide signalé.
    """
    par_ref = {}
    for a in articles or []:
        p = _prefixe_reference(a.get("reference"))
        if p and p not in par_ref:
            par_ref[p] = a["id"]
    connus = {a["id"] for a in articles or []}

    # Les émissions passées, de la plus récente à la plus ancienne.
    passees = sorted(emissions or [], key=lambda e: (e.get("dia") or "", e.get("criado_em") or ""),
                     reverse=True)
    par_libelle, par_client = {}, {}
    for e in passees:
        for l in e.get("linhas") or []:
            sid = l.get("service_id")
            if not sid or sid not in connus:
                continue
            lib = (l.get("libelle") or "").strip().lower()
            if lib and lib not in par_libelle:
                par_libelle[lib] = sid
            nif = (e.get("cliente_nif") or "").strip()
            if nif and nif not in par_client:
                par_client[nif] = sid

    du_registre = {}
    for l in (registre or {}).get("linhas") or []:
        lib = (l.get("libelle") or "").strip().lower()
        if lib and l.get("service_id"):
            du_registre[lib] = l["service_id"]

    nif_client = ((brouillon.get("client") or {}).get("nif") or "").strip()
    for l in brouillon.get("lignes") or []:
        lib = (l.get("libelle") or "").strip().lower()
        for sid, source in (
            (du_registre.get(lib), "registre"),
            (par_ref.get(_prefixe_reference(l.get("reference")) or ""), "reference"),
            (par_libelle.get(lib), "libelle"),
            (par_client.get(nif_client), "client"),
        ):
            if sid and sid in connus:
                l["service_id"], l["source_article"] = sid, source
                break
        else:
            l["service_id"], l["source_article"] = 0, "introuvable"
    return brouillon
