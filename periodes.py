"""
LES PÉRIODES D'UN CAFÉ OUVERT CINQ JOURS SUR SEPT.

⚠️ « HIER » N'EST PAS UN JOUR D'OUVERTURE. Le café ouvre lundi, jeudi, vendredi, samedi,
dimanche. Chaque jeudi, « hier » tombe sur un mercredi fermé : la page s'affichait vide, avec
des zéros partout, et rien ne disait que le café n'avait tout simplement pas ouvert. Un écran
vide se lit « on n'a rien vendu », jamais « on n'était pas là ».

⚠️ ET « LA SEMAINE DERNIÈRE » EST AMBIGUË. Sept jours calendaires, ou cinq jours de service ?
Les deux réponses existent et donnent des chiffres différents ; tant que l'écran ne dit pas
laquelle il applique, on lit un total sans savoir sur quoi il porte. Chaque période annonce
donc son NOMBRE DE JOURS OUVERTS, et c'est cette unité-là qui compare.

⚠️ COMPARER DEUX PÉRIODES, C'EST COMPARER DES JOURS DE SERVICE. « Cette semaine » un jeudi
contient deux jours ouverts ; « la semaine dernière » en contient cinq. Les opposer sans le
dire fait conclure à un effondrement de 60 % qui n'est qu'un décalage de calendrier.
"""

from datetime import date, timedelta

from config import count_open_days_raw


def est_ouvert(jour):
    """Ce jour-là, le café a-t-il ouvert ?"""
    return count_open_days_raw(jour, jour) > 0


def dernier_jour_ouvert(avant, limite=30):
    """
    Le dernier jour d'ouverture STRICTEMENT avant `avant`, ou `None`.

    ⚠️ C'EST CE QUE « HIER » VOULAIT DIRE. Personne ne demande « le 23 septembre » ; on demande
    « la dernière fois qu'on a ouvert ». La veille calendaire n'en est qu'une approximation, et
    elle est fausse un jour sur deux dans un café qui ferme deux jours par semaine.
    """
    j = avant - timedelta(1)
    for _ in range(limite):
        if est_ouvert(j):
            return j
        j -= timedelta(1)
    return None


def derniers_jours_ouverts(jusqu_a, combien, limite=90):
    """
    Les `combien` derniers jours d'ouverture, borne haute INCLUSE, du plus ancien au plus récent.

    ⚠️ C'EST LA SEULE FENÊTRE VRAIMENT COMPARABLE. Cinq jours de service contre cinq jours de
    service, quel que soit le calendrier — pas « sept jours » dont le nombre de services varie
    avec les fériés, les fermetures exceptionnelles et la période de lancement.
    """
    out, j = [], jusqu_a
    for _ in range(limite):
        if len(out) >= combien:
            break
        if est_ouvert(j):
            out.append(j)
        j -= timedelta(1)
    return list(reversed(out))


def fenetre_precedente(debut, fin, limite=180):
    """
    La fenêtre d'avant, de MÊME NOMBRE DE JOURS OUVERTS, finissant la veille de `debut`.

    ⚠️ RECULER DE SEPT JOURS N'ÉQUILIBRE RIEN QUAND LE CALENDRIER BOUGE. Un férié, une fermeture
    exceptionnelle, ou simplement le début de l'historique, et l'on oppose quatre services à
    cinq. Ici, la référence a exactement le même nombre de services — ou n'existe pas, et on le
    dit plutôt que de comparer ce qui ne se compare pas.
    """
    n = count_open_days_raw(debut, fin)
    if n <= 0:
        return None, None, 0
    jours = derniers_jours_ouverts(debut - timedelta(1), n, limite)
    if len(jours) < n:
        # ⚠️ PAS ASSEZ D'HISTORIQUE : on ne compare pas. Une référence amputée ferait conclure
        # à une progression qui n'est qu'un manque de passé.
        return None, None, len(jours)
    return jours[0], jours[-1], n


def decrire(debut, fin, aujourd_hui):
    """
    Ce que la période contient, en jours de service — et si elle est en cours.

    ⚠️ UNE PÉRIODE QUI CONTIENT AUJOURD'HUI N'EST PAS FINIE. La comparer à une période close
    fait lire un recul tous les matins et une reprise tous les soirs : un cycle entièrement
    fabriqué par l'heure à laquelle on regarde.
    """
    return {
        "jours_ouverts": count_open_days_raw(debut, fin),
        "jours_calendaires": (fin - debut).days + 1,
        "en_cours": debut <= aujourd_hui <= fin,
    }
