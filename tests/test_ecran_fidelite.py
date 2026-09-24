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
    # ⚠️ LA DÉCOUPE PARTAIT D'UN `style` EN LIGNE. Le titre est passé à l'en-tête de la charte
    # (`db-title`) et l'ancre a disparu avec lui : `index` aurait levé, ce qui est le bon
    # comportement — mais une ancre attachée à une taille de police en pixels ne pouvait pas
    # survivre à une refonte. Elle porte maintenant sur la structure.
    g = _gabarit()
    i = g.index('<div class="db-head">')
    return g[i:g.index("</div><!-- /apercu -->")]


# ── La forme ─────────────────────────────────────────────────────────────────────────────────

def test_la_page_ouvre_sur_une_reponse_pas_sur_une_grille():
    """
    ⚠️ LA QUESTION EST ÉCRITE, ET LA RÉPONSE EST UN CHIFFRE. C'est ce qui distingue un tableau
    de bord d'une liste de mesures : sans la question, six nombres corrects ne disent pas
    lequel regarder.
    """
    a = _apercu()
    assert a.index('id="fd-lead"') < a.index('id="kpis"'), \
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

    ⚠️ ET CE CONTRÔLE A CHANGÉ DE SENS AVEC LA CHARTE, CE QUI EST UN PIÈGE. Il EXIGEAIT la
    présence de `tx-chip-down` — la variante GRISE de l'ancienne feuille. Dans la charte,
    `down` est la variante ROUGE. Reporter l'assertion telle quelle sur le nouveau nom aurait
    donc exigé exactement ce qu'elle existe pour interdire, et le test serait resté vert en
    protégeant le contraire de ce qu'il dit.
    """
    r = _reponse({**H, "delta_pts": -6.0})
    assert "db-badge" in r["delta"], "la pastille n'est plus celle de la charte"
    assert "down" not in r["delta"], "la variante rouge de la charte est revenue"
    assert "red" not in r["delta"]
    assert "▼" in r["delta"] and "6,0" in r["delta"], "la direction n'est plus lisible"


# ── Ce qu'on ne sait pas encore ──────────────────────────────────────────────────────────────

def test_sans_recul_on_ne_compare_pas_et_on_dit_pourquoi():
    """Comparer contre la première semaine opposerait un régime à un démarrage."""
    r = _reponse({**H, "delta_pts": None, "prev": None, "reason": "not-enough-weeks"})
    # L'ambre dit « il manque quelque chose pour conclure », pas « c'est mauvais ».
    assert "db-badge plain warn" in r["delta"] and "pas de recul" in r["delta"]
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

    ⚠️ LA FORME A CHANGÉ DE MAISON, PAS DE NATURE. Elle vivait en `.tx-*` dans `style.css`, un
    vocabulaire inventé pour ces deux pages ; elle vit maintenant dans la charte, sous des noms
    communs à tout le produit. Le contrôle est le même — UN seul endroit la déclare — et il
    porte désormais sur les composants qui la portent réellement.
    """
    charte = open(os.path.join(RACINE, "static", "dashboard.css"), encoding="utf-8").read()
    for regle in (".db-card", ".db-lead", ".db-v", ".db-badge", ".db-fold", ".db-fine"):
        assert f"{regle} " in charte or f"{regle}{{" in charte or f"{regle}," in charte, regle
        for page in ("transactions.html", "fidelidade.html"):
            src = _gabarit(page)
            # Les deux pages ont un bloc de style chacune ; aucun ne doit redéclarer la forme.
            for a in [i for i, _ in enumerate(src) if src.startswith("<style>", i)]:
                bloc = src[a:src.index("</style>", a)]
                assert f"\n{regle} " not in bloc and f"\n{regle}{{" not in bloc, (
                    f"{regle} recopié dans {page}")

    # ⚠️ ET L'ANCIEN VOCABULAIRE NE DOIT PAS REPOUSSER. Une règle `.tx-*` qui réapparaîtrait
    # donnerait deux façons d'écrire la même carte, et la page écrite ensuite prendrait celle
    # qu'elle a sous les yeux.
    commun = open(os.path.join(RACINE, "static", "style.css"), encoding="utf-8").read()
    commun = re.sub(r"/\*.*?\*/", " ", commun, flags=re.S)
    assert not re.search(r"^\s*\.tx-", commun, re.M), re.findall(r"^\s*\.tx-[a-z-]+", commun, re.M)


def test_les_deux_pages_portent_la_meme_forme():
    """Ce que « le même UI/UX » veut dire concrètement : la question, le chiffre, l'écart, le n,
    la règle de lecture, et les limites repliées.

    ⚠️ CE CONTRÔLE NOMMAIT DES CLASSES, ET AFFLUENCE VIENT D'EN CHANGER. Elle est passée à la
    charte Stripe (`db-card`, `db-v`, `db-fold`), Fidélité porte encore `tx-*` : une refonte se
    fait page par page, et pendant ce temps les deux vocabulaires cohabitent. Un test attaché
    aux noms aurait obligé à refaire les deux le même jour, ou à le supprimer.

    ⚠️ IL TIENT DONC LA FORME, PAS L'HABILLAGE. La question, le chiffre, l'écart, le n, la règle
    et le repli sont ce que « même UI/UX » voulait dire ; ils sont repérés par leurs ANCRES, qui
    survivent au changement de charte. Le jour où Fidélité passera à son tour, ce test ne
    bougera pas — et c'est la preuve qu'il regardait la bonne chose.
    """
    # Chaque page préfixe ses ancres — `hl-` pour l'affluence, `fd-` pour la fidélité. C'est le
    # RÔLE de chacune qui doit se retrouver des deux côtés, pas son identifiant.
    for page, prefixe in (("transactions.html", "hl-"), ("fidelidade.html", "fd-")):
        g = _gabarit(page)
        for role in ("lead", "value", "delta", "n", "rule"):
            assert f'id="{prefixe}{role}"' in g, f"{page} : {prefixe}{role} manquant"
        assert "<details" in g and "</details>" in g, f"{page} : les limites ne sont plus repliées"
        assert " open" not in g[g.index("<details"):g.index(">", g.index("<details"))], (
            f"{page} : les limites sont dépliées par défaut")


# ⚠️ LA RÉSERVE AFFICHÉE À CÔTÉ DU CHIFFRE A ÉTÉ RETIRÉE : elle se déclenchait pour deux
# cartes, parce que son seuil était relatif à un effectif qui vaut un ou deux au démarrage.
# Ce qu'elle disait reste vrai et reste compté — par `/api/loyalty/diag`, qu'on ouvre quand le
# chiffre surprend.

# ── Le relevé doit savoir dire ce qui lui arrive ─────────────────────────────────────────────
#
# ⚠️ UN DIAGNOSTIC QUI TOMBE SANS DIRE POURQUOI NE SERT À RIEN. La première version rendait une
# page d'erreur générique : on apprenait qu'il y avait un problème, pas lequel — et on en était
# réduit à deviner une deuxième fois, sur le diagnostic cette fois.

import app as flask_app


@pytest.fixture
def admin_diag(monkeypatch):
    monkeypatch.setattr(flask_app, "_current_role", lambda: "admin")
    monkeypatch.setattr(flask_app, "DASHBOARD_PASSWORD", "")
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


VISITES = [{"fp": "a", "ts": "2026-09-20T10:00:00Z"}, {"fp": "a", "ts": "2026-09-21T10:00:00Z"},
           {"fp": "b", "ts": "2026-09-21T11:00:00Z"}]
LIENS = [{"fp": "a", "phone": "+351900", "linked_at": "2026-09-21T10:00:00Z"},
         {"fp": "b", "phone": "+351901", "linked_at": "2026-09-21T11:00:00Z"}]
FICHES = [{"phone": "+351900", "consent_at": "2026-09-21T10:00:00Z"},
          {"phone": "+351901", "consent_at": "2026-09-21T11:00:00Z"}]


def _sert(monkeypatch, **remplace):
    table = {"card_visits": (VISITES, False), "card_links": (LIENS, False),
             "customers": (FICHES, False)}
    table.update(remplace)

    def faux(t, p, **k):
        v = table[t]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(flask_app, "_supa_all", faux)
    monkeypatch.setattr(flask_app, "today_lisbon", lambda: __import__("datetime").date(2026, 9, 21))


def test_le_releve_distingue_la_carte_vue_une_fois_de_celle_vue_deux(admin_diag, monkeypatch):
    """
    ⚠️ C'EST LA LIGNE QUI EXPLIQUE TOUT. Un rattachement dont la carte n'a qu'un passage
    enregistré n'entre NI au numérateur NI au dénominateur du taux : dix inscrits dans la
    journée peuvent ne déplacer le chiffre d'aucun point.
    """
    _sert(monkeypatch)
    d = admin_diag.get("/api/loyalty/diag").get_json()
    assert d["ok"] is True
    assert d["rattachements_carte_vue_2_fois"] == 1    # « a » a deux passages
    assert d["rattachements_carte_vue_1_fois"] == 1    # « b » n'en a qu'un
    assert d["rattachements_aujourd_hui"] == 2


def test_une_lecture_qui_echoue_est_rapportee_pas_masquee(admin_diag, monkeypatch):
    _sert(monkeypatch, card_links=RuntimeError("colonne absente"))
    r = admin_diag.get("/api/loyalty/diag")
    assert r.status_code == 200, "le relevé rend une page d'erreur au lieu de se décrire"
    d = r.get_json()
    assert d["ok"] is False
    assert "card_links" in d["echecs"] and "colonne absente" in d["echecs"]["card_links"]
    # ⚠️ ET LE RESTE EST QUAND MÊME RENDU : une table illisible ne doit pas emporter les deux
    # autres, qui portent peut-être déjà la réponse.
    assert d["cartes_vues"] == 2


def test_une_lecture_tronquee_est_annoncee(admin_diag, monkeypatch):
    """
    ⚠️ UNE TRONCATURE MUETTE FAUSSE LE RELEVÉ LUI-MÊME. On compterait « 300 cartes vues une
    fois » sur un échantillon, et on conclurait sur le mauvais chiffre — avec l'assurance que
    donne un diagnostic.
    """
    _sert(monkeypatch, card_visits=(VISITES, True))
    d = admin_diag.get("/api/loyalty/diag").get_json()
    assert d["ok"] is False and "tronqué" in d["echecs"]["card_visits"]


def test_le_releve_reste_ferme_aux_autres_roles(monkeypatch):
    """Il énumère des empreintes de cartes et des numéros : c'est un fichier clients."""
    for role in (None, "investor", "staff", "accountant"):
        monkeypatch.setattr(flask_app, "_current_role", lambda r=role: r)
        flask_app.app.config["TESTING"] = True
        assert flask_app.app.test_client().get("/api/loyalty/diag").status_code in (401, 403)


# ── Le graphique des semaines, exécuté ───────────────────────────────────────────────────────
#
# ⚠️ IL N'AVAIT AUCUNE COUVERTURE DE RENDU. Les tests lisaient le modèle de la réponse et le
# gabarit ; entre les deux, la fonction qui dessine huit colonnes n'était vue par personne. La
# migration vers la charte a réécrit chacune de ces colonnes — et rien n'aurait rougi si une
# semaine sans mesure s'était mise à ressembler à une semaine à zéro.


def _rendu(nom, appel, socle_sup=""):
    """Extrait une fonction du gabarit et l'exécute sur un DOM minimal."""
    js = _js()
    i = js.index(f"  function {nom}(")
    fonction = js[i:js.index("\n  }", i) + 4]
    return _node("""
const champs = {};
function E(id){ return champs[id] || (champs[id] = {textContent:'',innerHTML:'',style:{}}); }
function reponse(){}
function eur(c){ return (c/100).toFixed(2).replace('.',',') + ' \u20ac'; }
function nb(n){ return (n===null||n===undefined) ? '\u2014' : n; }
""" + socle_sup + fonction + appel + """
console.log(JSON.stringify(Object.keys(champs).reduce(function(o,k){
  o[k] = champs[k].innerHTML || champs[k].textContent; return o; }, {})));
""")


SEMAINES = {
    "weeks": [
        {"start": "2026-08-10", "rate_pct": 30,   "linked": 3,  "returning": 10, "new_customers": 5},
        {"start": "2026-08-17", "rate_pct": None, "linked": 0,  "returning": 0,  "new_customers": 0},
        {"start": "2026-08-24", "rate_pct": 38,   "linked": 8,  "returning": 21, "new_customers": 3},
        {"start": "2026-09-14", "rate_pct": 42,   "linked": 11, "returning": 26, "new_customers": 4},
    ],
    "customers_total": 63, "this_week_customers": 4, "undated_links": 2, "opted_out": 1,
}


def _colonnes(cle="conv-graph"):
    """
    ⚠️ `conversion()` APPELLE `rythme()` DEPUIS LE 24/09/2026. Le harnais n'extrait que la fonction
    nommée : sans fournir l'autre, l'appel lève une `ReferenceError` et `conv-graph` reste vide —
    cinq contrôles rougissaient alors pour une raison qui n'avait rien à voir avec ce qu'ils
    éprouvent.
    """
    js = _js()
    i = js.index("  function rythme(")
    rythme = js[i:js.index("\n  }", i) + 4]
    r = _rendu("conversion", f"conversion({json.dumps(SEMAINES)});", socle_sup=rythme)
    return r[cle]


def test_une_semaine_sans_revenant_nest_pas_une_semaine_a_zero():
    """
    ⚠️ ELLE N'A RIEN MESURÉ, ET C'EST TOUT AUTRE CHOSE QU'UN ÉCHEC. Lui donner une barre à zéro
    — ou pire, la peindre comme les autres — fabriquerait un effondrement au démarrage du
    programme, au moment précis où l'on regarde si l'idée prend.
    """
    g = _colonnes()
    assert g.count("db-hbar") == 4, "les quatre semaines ne sont plus dessinées"
    assert "db-hbar absent" in g, "la semaine sans mesure ne se distingue plus"
    assert '<span class="sous">\u2014</span>' in g, "elle affiche un taux au lieu d'un tiret"
    # La colonne garde sa piste : on voit qu'il y avait une place, et qu'elle est vide.
    assert g.count('class="piste"') == 4


def test_la_semaine_en_cours_est_marquee_parce_quelle_nest_pas_finie():
    """Une semaine en cours comparée aux précédentes est un tronçon comparé à des semaines."""
    g = _colonnes()
    assert "db-hbar partiel" in g
    assert g.count("partiel") == 1, "plus d'une semaine se dit en cours"
    # Et c'est la DERNIÈRE, pas une autre.
    assert g.rindex("partiel") > g.rindex("db-hbar absent")


def test_les_deux_mesures_ne_partagent_jamais_un_axe():
    """
    ⚠️ DEUX ÉCHELLES SUR UN MÊME GRAPHIQUE NE SE COMPARENT PAS, ELLES SE CONFONDENT. Ce contrôle
    interdisait donc toute seconde barre, et les inscrits de la semaine restaient un nombre écrit.
    La règle est juste ; c'est sa portée qui était trop large.

    ⚠️ CE QUI A CHANGÉ LE 24/09/2026 : les inscrits ont leur PROPRE RANGÉE, avec son propre axe et
    sa propre échelle — relative au maximum de la série, puisqu'un compte n'a pas d'échelle absolue.
    Deux rangées qui partagent le temps et rien d'autre ne se confondent pas ; c'était le fait de
    poser un compte sur l'axe d'un pourcentage qui les confondait.

    ⚠️ ET LE NOMBRE RESTE ÉCRIT SOUS SA BARRE. Une hauteur relative ne se lit pas en valeur : sans
    le chiffre, « deux fois plus haut » ne dirait pas combien.
    """
    taux = _colonnes()
    rythme = _colonnes("conv-rythme")

    # Une seule hauteur par colonne, DANS CHAQUE RANGÉE : c'est ça, ne pas partager un axe.
    assert taux.count('style="height:') == 4, "la rangée du taux porte plus d'une hauteur"
    assert rythme.count('style="height:') == 4, "la rangée du rythme porte plus d'une hauteur"

    # Le rythme écrit ses nombres, et une semaine sans inscrit porte un tiret, pas un zéro.
    assert "+5" in rythme and "+3" in rythme
    assert '<span class="sous">\u2014</span>' in rythme, "une semaine sans inscrit affiche 0"

    # ⚠️ ET LA RANGÉE DU TAUX NE PORTE PLUS LES « +N » : les y laisser aurait mis la même mesure à
    # deux endroits, et c'est comme ça que deux chiffres finissent par ne plus être d'accord.
    assert '<span class="v' not in taux, "les inscrits sont écrits deux fois"


def test_les_colonnes_portent_le_composant_de_la_charte():
    """
    ⚠️ CE CONTRÔLE EXISTE PARCE QUE LA MIGRATION A RÉÉCRIT CES COLONNES. Elles avaient leur
    propre jeu de règles (`sem`, `sem-piste`, `sem-barre`) ; elles empruntent maintenant celui
    d'Affluence. Deux formes identiques sous deux noms, c'est une forme qui diverge.
    """
    g = _colonnes()
    for mort in ("sem-piste", "sem-barre", "sem-taux", "sem-neufs"):
        assert mort not in g, f"{mort} : l'ancien vocabulaire est revenu"
    # ⚠️ ON CHERCHE UN SÉLECTEUR, PAS UNE SOUS-CHAÎNE. Le premier jet testait `".db-hbar .piste"
    # in charte` — et `.db-hbar .pisteX` le contient. Renommer la règle laissait le contrôle
    # vert pendant que les colonnes perdaient leur piste.
    charte = open(os.path.join(RACINE, "static", "dashboard.css"), encoding="utf-8").read()
    charte = re.sub(r"/\*.*?\*/", " ", charte, flags=re.S)
    regles = set()
    for bloc in re.findall(r"([^{}]+)\{", charte):
        regles |= {x.strip() for x in bloc.split(",")}
    for vivant in (".db-hbar", ".db-hbar .piste", ".db-hbar.absent .f", ".db-hbar.partiel .f"):
        assert vivant in regles, f"{vivant} : la charte ne porte pas ce que la page pose"


def test_la_serie_de_conversion_porte_laccent_et_labsence_reste_grise():
    """
    ⚠️ DEUX RÈGLES QUI SE BATTENT À SPÉCIFICITÉ ÉGALE, ET L'ORDRE TRANCHE. La charte peint ces
    colonnes en gris — Affluence en aligne quatorze et n'en met que trois en avant. Cette page
    n'a qu'une mesure, et la laisser grise la ferait passer pour du décor : le bloc du gabarit
    la repeint en accent.

    ⚠️ MAIS `.conv-graph .db-hbar .f` ET `.db-hbar.absent .f` PÈSENT PAREIL (0,3,0). Le bloc du
    gabarit étant chargé après la charte, il gagne — et le talon de 2 px d'une semaine sans
    revenant se peindrait en accent, c'est-à-dire comme une toute petite mesure au lieu d'une
    absence. La seconde règle est la seule chose qui l'en empêche.
    """
    bloc = _gabarit()
    bloc = bloc[bloc.index(".conv-graph .db-hbar"):]
    i = bloc.index(".conv-graph .db-hbar .f")
    j = bloc.index(".conv-graph .db-hbar.absent .f")
    assert "var(--db-iris)" in bloc[i:bloc.index("}", i)], "la série n'est plus à l'accent"
    assert "var(--db-line)" in bloc[j:bloc.index("}", j)], "l'absence n'est plus grise"
    assert j > i, "la règle d'absence passe avant celle qu'elle doit corriger"


def test_le_filtre_des_clients_annonce_lequel_est_choisi():
    """
    ⚠️ LE SEGMENTÉ DE LA CHARTE SE PEINT SUR `aria-pressed`, pas sur une classe. L'ancien
    marquait sa sélection avec `.on` ; reprendre le composant sans reprendre l'attribut aurait
    donné quatre boutons dont aucun ne paraît choisi — et l'on ne saurait plus ce qu'on regarde.
    """
    g = _gabarit()
    barre = g[g.index('id="filtres"'):g.index("</div>", g.index('id="filtres"'))]
    assert barre.count("aria-pressed") == 4, barre
    assert barre.count('aria-pressed="true"') == 1, "aucun filtre choisi au chargement, ou deux"
    js = _js()
    i = js.index("E('filtres').children")
    assert "aria-pressed" in js[i - 200:i + 200], "le clic ne déplace plus la sélection"


def test_les_cellules_de_contexte_sont_des_cartes_de_la_charte():
    """Trois cellules, et chacune porte son unité — un nombre nu ne décide de rien."""
    s = {"points_outstanding": 1840, "liability_cents": 36800, "rewards_due": 3,
         "regulars": 9, "at_risk": [{}, {}]}
    r = _rendu("kpis", f"kpis({json.dumps(s)});")
    k = r["kpis"]
    assert k.count("db-card db-compact") == 3, k[:120]
    assert "368,00" in k, "la contrepartie en euros des points a disparu"
    assert "kpi-v" not in k and "kpi-l" not in k, "l'ancien vocabulaire est revenu"


# ── LES TROIS VUES AJOUTÉES LE 24/09/2026 ───────────────────────────────────────────────────
#
# ⚠️ AUCUNE NE CORRIGE UN CALCUL, ELLES CORRIGENT UN SILENCE. La page ne bougeait pas d'un jour à
# l'autre — sa réponse est cumulative ; le parrainage n'était visible nulle part ; la colonne des
# langues était remplie et jamais lue. Retirer l'un de ces appels ne casse RIEN : la page s'affiche,
# simplement un bloc reste vide. C'est pourquoi ces contrôles existent.


def test_les_trois_vues_sont_appelees_au_rendu():
    js = _js()
    for appel in ("bandeDuJour(d.journee)", "parrainage(d.parrainage)", "langues(d.langues)"):
        assert appel in js, f"{appel} ne se fait plus : le bloc resterait vide, sans erreur"


def test_la_bande_du_jour_distingue_un_zero_d_un_chiffre():
    """
    ⚠️ « 0 PARRAINAGE » EST UNE INFORMATION, PAS UN VIDE. C'est le seul chiffre qui dira si le lien
    WhatsApp sert — le partage se fait dans WhatsApp et nous n'en voyons rien. Le peindre comme les
    autres le ferait lire comme un résultat ; l'effacer le ferait disparaître.
    """
    js = _js()
    i = js.index("  function bandeDuJour(")
    r = _node("""
const champs = {};
function E(id){ return champs[id] || (champs[id] = {textContent:'',innerHTML:'',style:{}}); }
""" + js[i:js.index("\n  }", i) + 4] + """
bandeDuJour({date:'2026-09-24', cards:7, customers:2, rewards:0, referrals:0});
console.log(JSON.stringify({h: champs['jour'].innerHTML}));
""")
    h = r["h"]
    assert 'class="n rien">0' in h, "un zéro se lit comme un résultat"
    assert 'class="n bon">+2' in h, "les numéros pris ne ressortent plus"
    assert "cartes aujourd'hui" in h


def test_le_rythme_se_cale_sur_le_maximum_de_la_serie():
    """
    ⚠️ UN COMPTE N'A PAS D'ÉCHELLE ABSOLUE. Caler six inscriptions sur 100 % donnerait douze barres
    de six pixels — un graphique plat qui raconterait qu'il ne se passe rien. L'échelle est donc
    relative au maximum de la série, et le nombre reste écrit sous la barre parce qu'une hauteur
    relative ne se lit pas en valeur.
    """
    g = _colonnes("conv-rythme")
    # 5 est le maximum de SEMAINES : sa barre est pleine, celle de 3 vaut 60 %.
    assert 'style="height:100%"' in g, "la plus grosse semaine n'est plus à fond"
    assert 'style="height:60%"' in g, "l'échelle n'est plus relative au maximum"
