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
    assert ".est { color:var(--db-muted); }" in html


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


def test_les_intitules_du_bandeau_restent_courts():
    """
    ⚠️ UN CONTRÔLE A DISPARU ICI, ET SON REMPLAÇANT EST PLUS DIRECT. La bande soudée réservait
    24 px de hauteur à CHAQUE intitulé pour que les valeurs restent alignées malgré un libellé
    sur deux lignes — un contournement, pas une garantie. La grille de cartes l'a emporté ; le
    problème, lui, existe toujours : dans une grille, un intitulé qui passe à la ligne descend
    SA valeur et pas celle de sa voisine. Ce qui protège vraiment, c'est que les intitulés
    tiennent sur une ligne, et c'est ce qui est vérifié.

    ⚠️ ET CE CONTRÔLE VENAIT DE DEVENIR VERT À VIDE. Il cherchait `class="sum-label">`, qui
    n'existe plus depuis le passage à la charte : zéro intitulé trouvé, zéro assertion jouée,
    test vert. Il compte donc ce qu'il a trouvé avant de le juger.
    """
    html = _gabarit()
    # ⚠️ LA DÉCOUPE S'ARRÊTE À L'ÉLÉMENT SUIVANT, pas au premier `</div>` venu. Elle coupait au
    # `</div>` qui suit `id="i-delta"` — celui de son propre intitulé — et perdait la septième
    # carte : six trouvées, et un contrôle qui aurait pu se croire complet.
    bande = html[html.index('id="summary"'):html.index('id="inconnus"')]
    labels = re.findall(r'class="db-l">([^<]+)<', bande)
    assert len(labels) == 7, f"{len(labels)} intitulés trouvés, 7 attendus : {labels}"
    for label in labels:
        # Les entités HTML comptent pour un caractère à l'affichage.
        visible = re.sub(r"&[a-z]+;", "x", label).strip()
        assert len(visible) <= 12, f"intitulé trop long pour la carte : {label}"


# ── Le verdict et les lignes, exécutés ───────────────────────────────────────────────────────
#
# ⚠️ LE CLASSEMENT ÉTAIT TESTÉ, SON AFFICHAGE NON. `classe()` rend « ok », « doute » ou
# « alerte » depuis le début ; ce que la page en FAIT — un fond teinté hier, une bande d'accent
# et une pastille aujourd'hui — n'était vu par personne. Le passage à la charte a réécrit
# exactement cette partie-là.


def _verdict(*jours_):
    """Exécute `verdict()` sur un DOM minimal et rend ce qu'il pose."""
    prog = (_extraire("classe") + _extraire("causes") + _extraire("verdict") + """
const champs = {};
function faire(id) {
  const o = { _t: '', innerHTML: '', className: '', attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; } };
  Object.defineProperty(o, 'textContent', { get() { return this._t; },
                                            set(v) { this._t = String(v); } });
  return o;
}
const document = { getElementById: id => champs[id] || (champs[id] = faire(id)) };
const jourCourt = d => d;
""" + f"const jours = {json.dumps(list(jours_))};\n" + """
verdict();
console.log(JSON.stringify({
  html: champs['verdict'].innerHTML,
  classe: champs['verdict'].className,
  etat: champs['verdict'].attrs['data-etat'] || null,
}));""")
    return _node(prog)


def test_le_verdict_porte_son_etat_en_attribut_pas_en_fond_plein():
    """
    ⚠️ IL ÉTAIT PEINT EN PLEIN — vert, ambre ou rouge sur toute la largeur. Le bloc le plus
    important de l'écran était aussi le plus criard, et en mode sombre les trois teintes pâles
    passaient mal. La carte de la charte porte son état par une bande d'accent.

    ⚠️ ET LA CLASSE NE DOIT PLUS LE PORTER. `verdict ok` peignait le fond ; si la classe
    revenait pendant que l'attribut existe, on aurait les deux — une bande d'accent SUR un fond
    teinté, c'est-à-dire l'ancien défaut avec une décoration de plus.
    """
    r = _verdict(jour(ecart_cents=0))
    assert r["etat"] == "ok", r
    assert "db-card" in r["classe"], r["classe"]
    assert r["classe"].split() == ["db-card", "db-card-p", "verdict", "db-mb"], r["classe"]


@pytest.mark.parametrize("cents,etat", [(0, "ok"), (2000, "doute"), (-2000, "alerte")])
def test_chaque_classement_devient_un_etat_de_carte(cents, etat):
    assert _verdict(jour(ecart_cents=cents))["etat"] == etat


def test_sans_aucune_journee_close_la_carte_ne_porte_aucun_etat():
    """
    ⚠️ RIEN À JUGER N'EST PAS « TOUT VA BIEN ». Une carte verte sur un écran sans données dirait
    que la caisse tombe juste ; elle dit seulement qu'on n'a rien reconstruit. L'attribut est
    donc RETIRÉ, pas posé à une valeur neutre.
    """
    r = _verdict(jour(aujourdhui=True))
    assert r["etat"] is None, r
    assert "Reconstruire" in r["html"], "la marche à suivre n'est plus proposée"


def _ligne(j):
    """Le fragment de ligne produit pour une journée."""
    js = _gabarit()
    i = js.index("const TON = {")
    bloc = js[i:js.index("`;", js.index("const pastille", i)) + 2]
    return _node(_extraire("classe") + f"""
const j = {json.dumps(j)};
const c = classe(j);
{bloc}
console.log(JSON.stringify({{ pastille }}));""")


def test_une_journee_en_cours_ne_porte_pas_la_pastille_des_journees_vides():
    """
    ⚠️ « EN COURS » EST L'ABSENCE DE JUGEMENT, PAS UN JUGEMENT NEUTRE. Une journée qui n'est pas
    finie sera jugée ce soir ; une journée sans donnée ne le sera jamais. Leur donner la même
    pastille grise revient à dire la même chose de deux situations opposées.
    """
    r = _ligne(jour(aujourdhui=True))
    assert "db-badge iris" in r["pastille"], r["pastille"]
    assert "flat" not in r["pastille"]


@pytest.mark.parametrize("cents,ton", [(0, "up"), (2000, "warn"), (-2000, "down")])
def test_la_pastille_de_ligne_suit_le_classement(cents, ton):
    r = _ligne(jour(ecart_cents=cents))
    assert f"db-badge {ton}" in r["pastille"], r["pastille"]


def test_un_ecart_positif_et_un_ecart_negatif_ne_se_peignent_pas_pareil():
    """
    ⚠️ POSITIF ET NÉGATIF NE DEMANDENT PAS LE MÊME GESTE. Positif = une facture manque dans
    Vendus, le tiroir est juste ; négatif = de l'argent encaissé sans facture en face. Le second
    se répare aujourd'hui, le premier se rattrape. Les peindre du même rouge les confondait.
    """
    assert _ligne(jour(ecart_cents=2000))["pastille"] != _ligne(jour(ecart_cents=-2000))["pastille"]


def test_la_page_porte_la_charte():
    html = _gabarit()
    assert 'class="page db"' in html, "la classe qui définit les jetons `--db-*` est absente"
    assert "/static/dashboard.css?v=" in html, "la feuille de charte n'est pas chargée"


def _bande(cents_par_jour):
    """Exécute le calcul d'état de la carte « Écart » du bandeau."""
    js = _gabarit()
    i = js.index("const dTot = jours.reduce")
    bloc = js[i:js.index("carteEcart.setAttribute('data-etat', etatEcart);", i) + 48]
    return _node("""
const champs = {};
const document = { getElementById: id => champs[id] || (champs[id] = {
  _t: '', innerHTML: '', attrs: {},
  set textContent(v) { this._t = String(v); }, get textContent() { return this._t; },
  setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } }) };
""" + f"const jours = {json.dumps([{'ecart_cents': c} for c in cents_par_jour])};\n" + bloc + """
console.log(JSON.stringify({ valeur: champs['s-delta'].textContent,
                             etat: champs['i-delta'].attrs['data-etat'] || null }));""")


@pytest.mark.parametrize("cents,etat", [
    ([0, 0], "ok"),
    ([40, -30], "ok"),          # sous l'euro cumulé : des arrondis, pas un écart
    ([5000, 0], "attention"),   # positif : une facture manque, le tiroir est juste
    ([-5000, 0], "alerte"),     # négatif : encaissé sans facture en face
])
def test_la_carte_ecart_du_bandeau_porte_son_etat(cents, etat):
    """
    ⚠️ LE CHIFFRE ÉTAIT PEINT, PAS LA CARTE. Sur une bande où six voisins portent déjà des
    montants, une septième couleur ne ressort plus. La bande d'accent le dit sans toucher au
    nombre, qui reste lisible en encre.

    ⚠️ ET C'EST LA SEULE DES SEPT À PORTER UN ÉTAT. Les six autres sont des constats : colorer
    les sept ne hiérarchiserait rien.
    """
    assert _bande(cents)["etat"] == etat


def test_les_sept_cartes_du_bandeau_sont_toutes_rendues():
    """Une carte retirée ou masquée ferait disparaître un terme de l'addition sans le dire."""
    html = _gabarit()
    bande = html[html.index('id="summary"'):html.index('id="inconnus"')]
    for ancre in ("s-gross", "s-tips", "s-fees", "s-net", "s-vendus", "s-cash", "s-delta"):
        assert f'id="{ancre}"' in bande, ancre
    assert "hidden" not in bande and "display:none" not in bande.replace(
        'id="summary" style="display:none;"', ""), "une carte du bandeau est masquée"
