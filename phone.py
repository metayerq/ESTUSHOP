"""
LE NUMÉRO DE TÉLÉPHONE — UNE CLÉ, PAS UN LIBELLÉ.

⚠️ CE FICHIER EST UNE TRADUCTION, PAS UNE INVENTION. L'original est `mesa/apps/pos/lib/phone.ts`,
qui range les numéros au comptoir. Ici on ne fait que corriger une saisie depuis le backoffice —
mais si les deux normalisations divergent, ne serait-ce que d'un zéro de tête, la MÊME personne
obtient DEUX comptes : deux soldes de points, dont un invisible, et un client qui ne comprendra
jamais où sont passés les siens. `phone` est la clé primaire de `card_customers`.

La traduction est vérifiée : `tests/test_phone.py` rejoue les vecteurs produits par
l'implémentation TypeScript, dans le même fichier figé que le barème.
"""

import re

# Indicatif par défaut : le café est à Lisbonne, ses clients tapent un numéro portugais.
DEFAULT_COUNTRY_CODE = "351"

# Ce que le message d'erreur doit dire à quelqu'un qui tape vite.
PHONE_MESSAGE = {
    "empty": "Saisis un numéro de téléphone.",
    "too-short": "Trop court pour un mobile portugais — neuf chiffres après l'indicatif.",
    "too-long": "Trop long — vérifie le numéro.",
    "not-a-number": "Des chiffres uniquement, avec un + au début si besoin.",
    "not-mobile": "Les mobiles portugais commencent par 9 — un fixe ne reçoit pas le SMS.",
}

_BRUIT = re.compile(r"[\s.\-()/]")
_CHIFFRES = re.compile(r"^\+\d+$")


def normalise_phone(brut, country_code=DEFAULT_COUNTRY_CODE):
    """
    Range un numéro en E.164. Renvoie `(True, "+351912345678")` ou `(False, "raison")`.

    ⚠️ LES ESPACES, POINTS ET TIRETS SONT DU BRUIT DE SAISIE, pas de l'information. Les garder
    ferait diverger « 912 345 678 » de « 912345678 » — deux clés, deux comptes.
    """
    nettoye = _BRUIT.sub("", brut or "")
    if nettoye == "":
        return False, "empty"

    # `00` est la forme internationale composée depuis un poste fixe — même chose que `+`.
    s = "+" + nettoye[2:] if nettoye.startswith("00") else nettoye
    if not s.startswith("+"):
        # ⚠️ UN ZÉRO DE TÊTE EST UN PRÉFIXE NATIONAL, pas un chiffre du numéro. Le garder
        # produirait « +3510912… », qui n'existe pas.
        s = "+" + country_code + s.lstrip("0")

    if not _CHIFFRES.match(s):
        return False, "not-a-number"
    chiffres = s[1:]
    if len(chiffres) < 8:
        return False, "too-short"
    if len(chiffres) > 15:          # borne E.164
        return False, "too-long"

    # ⚠️ UN FIXE NE REÇOIT PAS DE SMS. Au Portugal, les mobiles commencent par 9 ; un 21… est un
    # fixe de Lisbonne. L'accepter créerait un compte à qui aucun message n'arrivera jamais, et
    # le client attendrait un SMS qui ne viendra pas.
    if chiffres.startswith(DEFAULT_COUNTRY_CODE):
        national = chiffres[len(DEFAULT_COUNTRY_CODE):]
        if len(national) != 9:
            return False, "too-short" if len(national) < 9 else "too-long"
        if not national.startswith("9"):
            return False, "not-mobile"

    return True, s


def mask_phone(e164):
    """
    Le numéro tel qu'on l'AFFICHE. ⚠️ JAMAIS EN ENTIER hors du rôle admin : quatre chiffres
    suffisent à reconnaître la bonne fiche.
    """
    s = (e164 or "").strip()
    return "•••" if len(s) < 4 else "••• " + s[-4:]
