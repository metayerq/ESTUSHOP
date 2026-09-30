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
        nif = (c.get("nif") or "").strip()
        if not (len(nif) == 9 and nif.isdigit()):
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


def prestations(req, env=None):
    """
    Les fiches facturables.

    ⚠️ « SANS CATÉGORIE » EST LE MARQUEUR, ET IL A ÉTÉ MESURÉ. Les 112 produits actifs du compte
    appartiennent tous à l'une des sept catégories : aucun ne serait pris à tort pour une
    prestation. Et la grille de vente du comptoir filtre sur une catégorie active — une fiche
    sans catégorie n'y est donc pas atteignable, elle ne peut pas être vendue par erreur.
    """
    return [{"id": p.get("id"), "titre": p.get("title") or "",
             "taux": TAUX_PAR_ID.get(p.get("tax_id") or "", 23)}
            for p in _pages(req, "/products/", "products", env)
            if not p.get("category_id") and p.get("status") != "off"]


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
