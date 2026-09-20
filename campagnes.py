"""
CE QUE LES CAMPAGNES ONT COÛTÉ.

⚠️ CE FICHIER A PORTÉ UNE ANALYSE D'EFFET — venues et encaissements des destinataires dans la
semaine suivant l'envoi, comparés à la semaine précédente. RETIRÉE LE 20/09/2026 À LA DEMANDE DE
QUENTIN, et noté ici pour que personne ne la reconstruise en croyant combler un manque.

Ce qui reste est mesuré, pas inféré : le coût vient des segments réellement facturés, et ne
suppose rien sur le comportement de personne.
"""

from points import parse_ts

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
