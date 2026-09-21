"""
L'ÉCRAN FIDÉLITÉ — même forme que la page Affluence.

⚠️ LA PAGE OUVRAIT SUR SIX CHIFFRES DE MÊME POIDS — comptes, taux de liaison, points en
circulation, boissons dues, points consommés, habitués — dont un seul répond à la question qu'on
se pose en l'ouvrant : est-ce que demander le numéro marche ? Une grille où tout a le même poids
ne hiérarchise rien, et on finit par ne plus en lire aucun.

⚠️ ET LA SIMPLIFICATION N'EST PAS UN RACCOURCISSEMENT DES AVERTISSEMENTS. Ce qui descend dans le
bloc replié y reste ÉCRIT : chacune de ces limites répond à une question qu'on se poserait
autrement avec un chiffre inventé.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _gabarit(nom="fidelidade.html"):
    return open(os.path.join(RACINE, "templates", nom), encoding="utf-8").read()


def _js(nom="fidelidade.html"):
    return "\n".join(re.findall(r"<script>(.*?)</script>", _gabarit(nom), re.S))


def _sans_commentaires(x):
    x = re.sub(r"<!--.*?-->", " ", x, flags=re.S)
    return re.sub(r"\{#.*?#\}", " ", x, flags=re.S)


def _mots(x):
    return len(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _sans_commentaires(x))).strip().split())


def _apercu():
    g = _gabarit()
    i = g.index('<h1 style="font-size:22px')
    return g[i:g.index("</div><!-- /apercu -->")]


# ── La forme ─────────────────────────────────────────────────────────────────────────────────

def test_la_page_ouvre_sur_une_reponse_pas_sur_une_grille():
    """
    ⚠️ LA QUESTION EST ÉCRITE, ET LA RÉPONSE EST UN CHIFFRE. C'est ce qui distingue un tableau
    de bord d'une liste de mesures : sans la question, six nombres corrects ne disent pas
    lequel regarder.
    """
    a = _apercu()
    assert a.index('tx-card tx-answer') < a.index('id="kpis"'), \
        "la grille de chiffres passe avant la réponse"
    assert "Le programme prend-il" in a
    for champ in ("fd-lead", "fd-value", "fd-delta", "fd-n", "fd-rule", "fd-note"):
        assert f'id="{champ}"' in a, champ


def test_la_vue_densemble_tient_en_moins_de_soixante_mots():
    """
    ⚠️ SANS CHIFFRE, UNE PAGE SE REMPLIT À NOUVEAU UNE EXPLICATION À LA FOIS, et chacune
    paraîtra justifiée. 169 mots avant, dont le barème et la garantie de calcul — vrais, et
    qu'on ne relit pas chaque semaine.
    """
    a = _apercu()
    ouvert = a[:a.index("<details")] + a[a.index("</details>"):]
    assert _mots(ouvert) < 60, _mots(ouvert)


def test_les_six_cellules_sont_devenues_trois_qui_engagent_quelque_chose():
    """
    « Comptes » se déduit des deux autres ; « Points consommés » est une curiosité dont aucune
    décision n'est jamais sortie ; « Taux de liaison » est monté dans la réponse.
    """
    js = _js()
    bloc = js[js.index("function kpis("):js.index("function reponse(")]
    for parti in ("'Comptes'", "'Points consommés'", "'Taux de liaison'"):
        assert parti not in bloc, parti
    for reste in ("'Boissons dues'", "'Points en circulation'", "'Habitués'"):
        assert reste in bloc, reste


def test_les_points_en_circulation_gardent_leur_contrepartie_en_euros():
    """Un nombre de points ne dit rien tant qu'on ne sait pas ce qu'il coûte si tout est
    réclamé le même mois."""
    js = _js()
    bloc = js[js.index("'Points en circulation'"):js.index("'Habitués'")]
    assert "liability_cents" in bloc


# ── Le bloc replié ───────────────────────────────────────────────────────────────────────────

def test_les_limites_sont_repliees_pas_supprimees():
    a = _apercu()
    d = a[a.index("<details"):a.index("</details>")]
    assert not re.search(r'<details class="tx-limites"[^>]*\sopen', a)
    assert "1&nbsp;&euro; d&eacute;pens&eacute; = 1 point" in d, "le barème a disparu"
    assert "m&ecirc;me code" in d, "la garantie de calcul commun a disparu"
    assert "au moins deux fois" in d, "la définition du dénominateur a disparu"
    assert "points" in d and "+3 points" in d, "la règle de lecture de l'écart a disparu"
    assert "sans date" in d, "les rattachements non datés ont disparu"


def test_le_bareme_en_vigueur_reste_en_haut_de_page():
    """
    ⚠️ CE N'EST PAS UN RAPPEL, C'EST UN ÉTAT. Le barème peut avoir été changé dans l'onglet
    Réglages : le ranger avec la règle générale ferait lire une page sans savoir sous quel
    régime elle a été calculée.
    """
    assert 'id="regle-active"' in _apercu()


# ── L'écart en points ────────────────────────────────────────────────────────────────────────

def _node(prog):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ⚠️ `fd-note` DÉMARRE CACHÉ, COMME DANS LE GABARIT (`style="display:none"`). Le faux élément
# le faisait naître visible : un mutant qui supprimait `style.display = ''` survivait, puisque
# la note « apparaissait » sans qu'on l'ait montrée. Un bancal plus permissif que la page rend
# vert un test qui ne vérifie rien.
SOCLE = """
const champs = {};
function E(id){
  return champs[id] || (champs[id] = {
    textContent: '', innerHTML: '',
    style: { display: id === 'fd-note' ? 'none' : '' },
  });
}
"""


def _reponse(headline):
    js = _js()
    i = js.index("  function reponse(")
    fonction = js[i:js.index("\n  }", i) + 4]
    # ⚠️ LA FONCTION REÇOIT LA SÉRIE, PAS LA RÉPONSE. Lui passer le headline nu la faisait
    # retomber sur « rien à lire » — et huit tests échouaient en décrivant correctement une
    # page qui, elle, marchait.
    return _node(SOCLE + fonction + f"""
        reponse({json.dumps({"headline": headline} if headline else headline)});
        console.log(JSON.stringify({{
          lead: champs['fd-lead'].textContent,
          value: champs['fd-value'].textContent,
          delta: champs['fd-delta'].innerHTML,
          n: champs['fd-n'].innerHTML,
          rule: champs['fd-rule'].innerHTML,
          note: champs['fd-note'].textContent,
          noteVisible: champs['fd-note'].style.display !== 'none',
        }}));
    """)


H = {"ok": True, "rate_pct": 42.3, "n": 26, "linked": 11, "week": "2026-08-03",
     "delta_pts": 6.0, "prev": 36.3, "prev_week": "2026-07-06", "prev_n": 10,
     "weeks_between": 4, "reason": None}


def test_lecart_saffiche_en_points_et_le_dit():
    """
    ⚠️ LA SÉRIE EST CUMULATIVE. Sans le mot « points », on lit l'écart comme une variation
    relative — et un taux cumulé qui gagne six points paraît stagner.
    """
    r = _reponse(H)
    assert "6,0 pts" in r["delta"]
    assert "points de pourcentage" in r["rule"]
    assert "cumul" in r["rule"]


def test_les_deux_bouts_sont_nommes_avec_leur_effectif():
    r = _reponse(H)
    assert "36.3 %" in r["delta"] and "sur 10" in r["delta"]
    assert "11" in r["n"] and "26" in r["n"]


@pytest.mark.parametrize("pts,mot", [(6.0, "progresse"), (-6.0, "recule"), (0.0, "stable")])
def test_le_sens_est_dit_en_toutes_lettres(pts, mot):
    r = _reponse({**H, "delta_pts": pts})
    assert mot in r["lead"], r["lead"]


def test_une_baisse_nest_pas_peinte_en_rouge():
    """
    ⚠️ RIEN ICI N'EST UN SOLDE. Un rattachement qui recule est une mesure à regarder, pas une
    alarme : la direction est portée par la flèche et le signe.
    """
    r = _reponse({**H, "delta_pts": -6.0})
    assert "tx-chip-down" in r["delta"] and "red" not in r["delta"]


# ── Ce qu'on ne sait pas encore ──────────────────────────────────────────────────────────────

def test_sans_recul_on_ne_compare_pas_et_on_dit_pourquoi():
    """Comparer contre la première semaine opposerait un régime à un démarrage."""
    r = _reponse({**H, "delta_pts": None, "prev": None, "reason": "not-enough-weeks"})
    assert "tx-chip-none" in r["delta"] and "pas de recul" in r["delta"]
    assert r["noteVisible"] and "démarrage" in r["note"]
    assert r["value"] == "42.3 %", "le taux mesuré disparaît alors qu'il est connu"


def test_sans_semaine_complete_la_page_dit_quelle_ne_sait_pas():
    """⚠️ ET ELLE N'AFFICHE PAS 0 %. « Aucune semaine finie » et « personne ne s'inscrit » sont
    deux constats opposés."""
    r = _reponse({"ok": False, "rate_pct": None})
    assert r["value"] == "—"
    assert r["delta"] == ""
    assert r["noteVisible"] and "pas terminée" in r["note"]


@pytest.mark.parametrize("cv", [None, {}, {"headline": None}, {"headline": {}}])
def test_un_payload_abime_ne_casse_pas_la_page(cv):
    js = _js()
    i = js.index("  function reponse(")
    fonction = js[i:js.index("\n  }", i) + 4]
    r = _node(SOCLE + fonction + f"""
        reponse({json.dumps(cv)});
        console.log(JSON.stringify({{ v: champs['fd-value'].textContent }}));
    """)
    assert r["v"] == "—"


# ── La forme est partagée, pas recopiée ──────────────────────────────────────────────────────

def test_le_bandeau_reponse_nest_defini_quune_fois():
    """
    ⚠️ DEUX JEUX DE RÈGLES À TENIR D'ACCORD, ET CELUI QU'ON OUVRE LE MOINS VIEILLIT EN SILENCE.
    C'est déjà arrivé dans ce dépôt : la feuille de style de la nav laissée derrière sur
    `marketing.html` a rendu la page illisible sans qu'aucun test ne rougisse.
    """
    commun = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    for regle in (".tx-answer", ".tx-value", ".tx-chip", ".tx-limites", ".tx-card"):
        assert f"{regle} " in commun or f"{regle}{{" in commun or f"{regle}," in commun, regle
        for page in ("transactions.html", "fidelidade.html"):
            bloc = _gabarit(page)
            bloc = bloc[bloc.index("<style>"):bloc.index("</style>")]
            assert f"\n{regle} " not in bloc and f"\n{regle}{{" not in bloc, f"{regle} recopié dans {page}"


def test_les_deux_pages_portent_la_meme_forme():
    """Ce que « le même UI/UX » veut dire concrètement : la question, le chiffre, l'écart, le n,
    la règle de lecture, et les limites repliées."""
    for page in ("transactions.html", "fidelidade.html"):
        g = _gabarit(page)
        assert 'class="tx-card tx-answer"' in g, page
        assert 'class="tx-q"' in g, page
        assert 'class="tx-value"' in g, page
        assert 'class="tx-limites"' in g, page
