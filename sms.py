"""
CE QU'UN MESSAGE COÛTE — LA MÊME RÈGLE QUE LA CAISSE, OU RIEN.

⚠️ CE FICHIER EST UNE TRADUCTION, PAS UNE INVENTION. L'original est `mesa/apps/pos/lib/sms.ts`,
qui décide ce qui part vraiment. Ici on ne fait que compter pendant que le patron tape — mais si
les deux comptages divergent, l'écran annonce « 1 segment » là où il y en a deux, et la facture
double sur TOUTE la campagne. L'erreur ne se produit que sur les caractères rares : jamais
pendant les essais, toujours le jour de l'envoi réel.

La traduction est vérifiée : `tests/test_sms.py` rejoue les vecteurs produits par
l'implémentation TypeScript, dans le même fichier figé que le barème et les phrases de
consentement.

⚠️ ET LE CHIFFRE QUI ENGAGE RESTE CELUI DE LA CAISSE. Cet écran compte en direct ; l'aperçu
avant envoi, lui, est demandé à l'expéditeur, qui répond avec le message réel. Deux comptages
d'accord valent mieux qu'un, mais c'est le second qui fait foi.
"""

# L'alphabet GSM-7 (3GPP 23.038), et son extension.
# ⚠️ LE PIÈGE PORTUGAIS EST DEDANS : « Ç » MAJUSCULE Y EST, « ç » MINUSCULE NON. « começar »,
# « serviço » et « obrigação » font donc basculer le message entier en UCS-2 — la limite tombe de
# 160 à 70 caractères. « ã », « õ », « ó » et « á » non plus n'y sont pas ; « é », « à », « è »,
# « ò », « ù », « ì », « ñ » et « ü » y sont.
GSM7 = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# Ces caractères comptent DOUBLE : ils s'écrivent sur deux septets.
GSM7_ETENDU = "^{}\\[~]|€"


def is_gsm7(texte):
    return all(c in GSM7 or c in GSM7_ETENDU for c in texte or "")


def sms_cost(texte):
    """
    Renvoie `{gsm7, length, segments}`.

    ⚠️ UN MESSAGE LONG N'EST PAS COUPÉ EN DEUX AU MILIEU : il est facturé en segments, et les
    segments d'un message concaténé perdent 7 caractères chacun pour l'en-tête. 161 caractères
    coûtent donc DEUX fois le prix de 160, pas une fois et demie.
    """
    texte = texte or ""
    gsm7 = is_gsm7(texte)
    if gsm7:
        longueur = sum(2 if c in GSM7_ETENDU else 1 for c in texte)
    else:
        # ⚠️ EN UNITÉS UTF-16, COMME LA CAISSE. Un emoji compte pour deux : Python le compte pour
        # un, et l'écart ne se verrait que sur un message déjà long.
        longueur = sum(2 if ord(c) > 0xFFFF else 1 for c in texte)
    simple = 160 if gsm7 else 70
    concatene = 153 if gsm7 else 67
    segments = 1 if longueur <= simple else -(-longueur // concatene)
    return {"gsm7": gsm7, "length": longueur, "segments": segments}


# Ce que le code de la caisse ajoute autour du texte, et que le patron ne peut pas retirer.
# ⚠️ RECOPIÉ ICI POUR COMPTER, PAS POUR ENVOYER. Le message réel est construit par Mesa ;
# `tests/test_sms.py` vérifie que ces deux morceaux sont bien les siens.
CAMPAGNE_PREFIXE = "Estudantina: "
CAMPAGNE_SORTIE = " STOP para sair"

# Un lien de page client, à la longueur réelle — c'est elle qui mange le budget.
LIEN_EXEMPLE = "https://pontos.estudantina.com/c/" + "A" * 22


def campagne_apercu(texte):
    """
    Ce que ce brouillon coûterait, enveloppe comprise.

    ⚠️ « 160 CARACTÈRES » EST FAUX ICI, ET LE DIRE COÛTERAIT DE L'ARGENT. Préfixe, lien et
    mention de sortie prennent une bonne moitié du budget avant le premier mot. Un écran qui
    annonce 160 laisse écrire soixante caractères de trop, puis facture deux segments à tout le
    monde.
    """
    corps = " ".join((texte or "").split())
    message = f"{CAMPAGNE_PREFIXE}{corps} {LIEN_EXEMPLE}{CAMPAGNE_SORTIE}"
    cout = sms_cost(message)
    enveloppe = sms_cost(f"{CAMPAGNE_PREFIXE} {LIEN_EXEMPLE}{CAMPAGNE_SORTIE}")["length"]
    return {**cout, "message": message, "budget": max(0, 160 - enveloppe)}
