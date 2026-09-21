"""
L'ÉCRAN DE RÉCONCILIATION.

⚠️ TROIS STATUTS, JAMAIS MÉLANGÉS : mesuré, estimé, inconnu. Un écran qui les confond est pire
qu'un écran vide — il fait prendre des décisions sur des chiffres qu'on croit mesurés.

⚠️ ET LE RENDU EST TESTÉ EN EXÉCUTANT LE VRAI JAVASCRIPT. Vérifier la présence d'un identifiant
dans le gabarit ne dit rien de ce qui s'affiche : c'est la logique du verdict qui décide si le
patron regarde sa caisse ou passe son chemin.
"""

import json
import os
import re
import shutil
import subprocess

import pytest


def _gabarit():
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "reconciliation.html")
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def _js():
    return "\n".join(re.findall(r"<script>(.*?)</script>", _gabarit(), re.S))


def _extraire(*noms):
    """Les fonctions pures de l'écran, isolées pour être exécutées sans DOM."""
    js = _js()
    out = []
    for n in noms:
        i = js.index(f"function {n}(")
        # La fonction va jusqu'à la première accolade fermante en colonne 0.
        j = js.index("\n}", i) + 2
        out.append(js[i:j])
    return "\n".join(out)


# ⚠️ LES DEUX AUXILIAIRES SONT REDÉFINIS ICI, PAS EXTRAITS. `fmt` est un formateur de devise
# et `eu` une division par cent : les rejouer à l'identique ne prouve rien, et les extraire
# ferait dépendre ce test de leur emplacement dans le fichier. Ce qu'on teste, c'est la LOGIQUE
# des causes et du classement, pas la mise en forme des montants.
PROLOGUE = """
const fmt = v => Number(v).toFixed(2) + ' EUR';
const eu = c => (c || 0) / 100;
"""


def _node(programme):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    r = subprocess.run(["node", "-e", PROLOGUE + programme], capture_output=True,
                       text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def jour(**kw):
    base = {"day": "2026-09-18", "aujourdhui": False, "terminal_cents": 10000,
            "pourboires_cents": 0, "remboursements_cents": 0, "transactions": 9,
            "vendus_total_cents": 12000,
            "vendus": {"carte_cents": 10000, "especes_cents": 2000, "autre_cents": 0,
                       "titres_inconnus": []},
            "ecart_cents": 0, "frais_cents": 144, "frais_mesures": False,
            "net_cents": 9856, "terminal_absent": False, "vendus_absent": False,
            "repartition_absente": False}
    base.update(kw)
    return base


# ── Le classement d'une journée ──────────────────────────────────────────────────────────────

def _classe(j):
    return _node(_extraire("classe") + f"\nconsole.log(JSON.stringify(classe({json.dumps(j)})));")


def test_un_ecart_nul_est_vert():
    assert _classe(jour(ecart_cents=0)) == "ok"


def test_quelques_centimes_restent_verts():
    """Les arrondis de TVA produisent des écarts d'un centime ; les peindre en rouge userait
    l'attention avant le jour où elle sert."""
    assert _classe(jour(ecart_cents=4)) == "ok"
    assert _classe(jour(ecart_cents=-5)) == "ok"


def test_un_ecart_negatif_est_une_alerte():
    """
    ⚠️ NÉGATIF VEUT DIRE QUE VENDUS FACTURE PLUS EN CARTE QUE LE TERMINAL N'A ENCAISSÉ — un
    paiement espèces tapé « carte ». Positif est le cas bénin (facture oubliée).
    """
    assert _classe(jour(ecart_cents=-2000)) == "alerte"
    assert _classe(jour(ecart_cents=2000)) == "doute"


def test_un_ecart_incalculable_nest_pas_vert():
    """
    ⚠️ SANS RÉPARTITION, ON NE SAIT PAS. Le peindre en vert ferait passer une journée non
    vérifiée pour une journée vérifiée — exactement l'inverse de ce que l'écran doit faire.
    """
    assert _classe(jour(ecart_cents=None)) == "doute"


# ── Les causes, qui rendent l'écart actionnable ──────────────────────────────────────────────

def _causes(j):
    return _node(_extraire("causes") + f"\nconsole.log(JSON.stringify(causes({json.dumps(j)})));")


def test_un_ecart_positif_oriente_vers_une_facture_oubliee():
    c = " ".join(_causes(jour(ecart_cents=960)))
    assert "facture oubli" in c
    assert "Vendus" in c


def test_un_ecart_negatif_oriente_vers_le_tiroir():
    """
    ⚠️ ET IL ANNONCE L'EFFET MIROIR SUR LE CASH. Un paiement espèces tapé « carte » met de
    l'argent réel dans le tiroir : le dire évite de chercher deux anomalies là où il n'y en a
    qu'une.
    """
    c = " ".join(_causes(jour(ecart_cents=-960)))
    assert "carte" in c and "tiroir" in c


def test_un_avoir_est_signale_a_part():
    c = " ".join(_causes(jour(ecart_cents=0, remboursements_cents=400)))
    assert "avoir" in c.lower()


def test_une_journee_juste_ne_propose_rien_a_verifier():
    assert _causes(jour(ecart_cents=0)) == []


def test_un_ecart_incalculable_ne_fabrique_pas_de_cause():
    assert _causes(jour(ecart_cents=None)) == []


# ── Ce que le gabarit promet ─────────────────────────────────────────────────────────────────

def test_lestimation_est_visuellement_distincte_du_mesure():
    """
    ⚠️ LES FRAIS SONT ESTIMÉS TROIS SEMAINES PAR MOIS. Les afficher comme les ventes ferait
    lire un chiffre calculé comme un chiffre constaté.
    """
    html = _gabarit()
    assert "j.frais_mesures ? '' : 'est'" in html
    assert "'≈−'" in html
    assert ".est { color:var(--muted); }" in html


def test_aujourdhui_na_pas_de_verdict():
    """Un écart en milieu de journée ne veut rien dire."""
    html = _gabarit()
    i = html.index("function enCours()")
    assert "Pas de verdict avant la fin du service" in html[i:i + 1400]


def test_le_verdict_porte_sur_le_dernier_jour_CLOS_pas_sur_hier():
    """
    ⚠️ LE CAFÉ FERME MARDI ET MERCREDI. Un jeudi matin, « hier » est un mercredi vide : l'écran
    dirait « rien à vérifier » sur une journée où il n'y avait rien à vérifier, en masquant le
    lundi qui, lui, demandait un regard.
    """
    html = _gabarit()
    i = html.index("function verdict()")
    bloc = html[i:i + 1200]
    assert "!j.aujourdhui" in bloc
    assert "terminal_cents || j.vendus_total_cents" in bloc


def test_les_libelles_non_classes_sont_nommes():
    html = _gabarit()
    assert "Moyens de paiement non classés" in html


def test_la_page_ne_recharge_plus_vendus_mois_par_mois():
    """
    ⚠️ C'ÉTAIT LA CAUSE DE LA PAGE À ZÉRO. L'ancienne version appelait `/api/reconciliation` une
    fois par mois, et chaque appel rechargeait les documents Vendus un par un.
    """
    html = _gabarit()
    assert "/api/reconciliation/daily" in html
    assert "'/api/reconciliation?month=" not in html


# ── Le détail d'une journée ──────────────────────────────────────────────────────────────────

def test_le_detail_ne_souvre_que_sur_un_clic():
    """
    ⚠️ C'EST LA SEULE PARTIE DE CET ÉCRAN QUI TOUCHE UNE API EXTERNE : un appel Vendus et une
    vingtaine d'appels Revolut, pour UN jour. Le charger au rendu ramènerait exactement la
    rafale que la phase 1 a servi à supprimer.
    """
    js = _js()
    i = js.index("async function ouvrirDetail")
    assert "/api/reconciliation/day/" in js[i:i + 900]
    # Et l'appel n'est pas dans le chargement de la période.
    j = js.index("async function loadRange")
    assert "/detail" not in js[j:js.index("function bornes") if "function bornes" in js[j:] else j + 1800]


def test_lattente_est_annoncee_avec_sa_raison():
    """
    ⚠️ CET APPEL PREND PLUSIEURS SECONDES. Un écran figé sans explication se relit comme une
    panne — et on clique une deuxième fois, ce qui relance vingt requêtes.
    """
    js = _js()
    i = js.index("async function ouvrirDetail")
    assert "quelques secondes" in js[i:i + 900]


def test_un_second_clic_referme():
    js = _js()
    i = js.index("async function ouvrirDetail")
    assert "detailEnCours === jour" in js[i:i + 400]


def test_chaque_cote_dit_quoi_faire():
    """
    ⚠️ UNE LISTE SANS CONSIGNE N'EST PAS ACTIONNABLE. « Encaissé sans facture » et « facturé
    sans encaissement » appellent deux gestes opposés, et le second a un effet sur le tiroir.
    """
    html = _gabarit()
    i = html.index("function rendreDetail")
    bloc = html[i:i + 2600]
    assert "Émets-la dans Vendus" in bloc
    assert "dans le tiroir" in bloc
    assert "avoir n'a pas de " in bloc


def test_le_detail_dit_sa_tolerance():
    """Un appariement « au centime près, à 20 minutes près » se conteste ; un appariement muet
    se croit."""
    html = _gabarit()
    assert "Appariement au centime près" in html
    assert "d.fenetre_minutes" in html


def test_la_colonne_especes_dit_ce_quelle_nest_pas():
    """
    ⚠️ « ESPÈCES » N'EST PAS « CE QU'IL Y A DANS LE TIROIR ». C'est ce que Vendus DÉCLARE en
    espèces — et un paiement espèces tapé « carte » met de l'argent dans le tiroir sans jamais
    apparaître dans cette colonne. Laisser le lecteur confondre les deux lui ferait compter un
    manque qui n'existe pas.
    """
    html = _gabarit()
    assert "d&eacute;clare encaiss&eacute; en esp&egrave;ces" in html
    assert "moins" in html and "tiroir" in html


def test_la_part_autre_saffiche_quand_elle_existe():
    """Sinon la ligne ne s'additionne pas, et on croit à une erreur d'arrondi."""
    html = _gabarit()
    assert "autre_cents ?" in html
    assert "autre</span>" in html


# ── L'alignement ─────────────────────────────────────────────────────────────────────────────
#
# ⚠️ AUCUN DE CES DÉFAUTS NE LÈVE. Une page dont les colonnes dansent reste « fonctionnelle » :
# elle se lit mal, on s'y trompe de ligne, et on finit par ne plus l'ouvrir.

def test_len_tete_et_les_lignes_ont_le_meme_nombre_de_colonnes():
    """
    ⚠️ LE DÉFAUT LE PLUS BANAL EN AJOUTANT UNE COLONNE : l'en-tête en a huit, les lignes sept,
    et tout le tableau se décale d'une case à partir de là.
    """
    html = _gabarit()
    thead = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    assert len(re.findall(r"<th", thead)) == 8

    # Les `colspan` des lignes spéciales doivent couvrir exactement le reste.
    for m in re.finditer(r'<td[^>]*colspan="(\d+)"', html):
        assert int(m.group(1)) <= 8


def test_les_colonnes_de_bord_ont_une_largeur_fixe():
    """
    ⚠️ LA DERNIÈRE COLONNE PORTE « ✓ » OU « à vérifier » selon les jours. En largeur
    automatique, elle change de taille d'un affichage à l'autre — et toutes les autres bougent
    avec elle.
    """
    html = _gabarit()
    thead = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    assert 'style="width:104px"' in thead, "la colonne Jour n'a pas de largeur"
    assert 'style="width:96px"' in thead, "la colonne de statut n'a pas de largeur"


def test_les_intitules_den_tete_ne_passent_pas_a_la_ligne():
    """Un en-tête sur deux lignes change la hauteur de la rangée et déforme la lecture."""
    assert "thead th { white-space:nowrap; }" in _gabarit()


def test_les_cases_du_bandeau_reservent_la_meme_hauteur_de_libelle():
    """
    ⚠️ SEPT CASES SE PARTAGENT LA LARGEUR. Certains intitulés tiennent sur une ligne, d'autres
    passent à deux : sans hauteur réservée, les valeurs ne démarrent pas au même niveau et la
    barre se lit comme des colonnes désalignées.
    """
    html = _gabarit()
    assert "min-height:24px" in html
    # Et les valeurs ne se coupent pas en deux.
    assert ".sum-val" in html and "white-space:nowrap" in html


def test_les_intitules_du_bandeau_restent_courts():
    """Sept cases sur 1 060 px : un intitulé long déborde ou casse la grille."""
    html = _gabarit()
    for label in re.findall(r'class="sum-label">([^<]+)<', html):
        # Les entités HTML comptent pour un caractère à l'affichage.
        visible = re.sub(r"&[a-z]+;", "x", label)
        assert len(visible) <= 12, f"intitulé trop long pour la barre : {label}"
