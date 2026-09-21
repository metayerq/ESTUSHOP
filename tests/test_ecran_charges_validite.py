"""
L'ÉCRAN DES CHARGES — LA DATE D'EFFET.

⚠️ LE SERVEUR REFUSE UN CHANGEMENT DE MONTANT SANS DATE NI MOTIF. Si la fenêtre ne montre pas
ces champs, le refus arrive sans dire quoi saisir : un garde correct, et un écran dans lequel on
ne peut plus changer un loyer.

⚠️ ET LE BLOC DOIT RESTER CACHÉ POUR UNE CORRECTION DE LIBELLÉ. Un formulaire qui réclame une
justification pour remettre un accent finit par être contourné — et c'est ainsi qu'on retrouve
les vrais changements saisis dans le champ « notes ».

⚠️ LE RENDU EST TESTÉ EN EXÉCUTANT LE VRAI JAVASCRIPT DE LA PAGE. Chercher un identifiant dans
le gabarit ne dit rien de ce qui s'affiche.
"""

import json
import os
import re
import shutil
import subprocess

import pytest


def _gabarit():
    return open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "templates", "charges.html"), encoding="utf-8").read()


def _js():
    return "\n".join(re.findall(r"<script>(.*?)</script>", _gabarit(), re.S))


def _extraire(*noms):
    """
    Les fonctions et constantes de l'écran, isolées pour être exécutées sans DOM.

    ⚠️ `VER_CHAMPS` EST EXTRAIT, PAS RECOPIÉ. C'est la liste des champs qui touchent au coût :
    la recopier ici prouverait que ma copie est d'accord avec elle-même, et laisserait passer
    le jour où quelqu'un retire `meal_card_daily` de la vraie.
    """
    js = _js()
    out = []
    for n in noms:
        if n.isupper():
            i = js.index(f"const {n} = ")
            fin = js.index("\n};", i) + 3 if js[i:].startswith(f"const {n} = {{") \
                else js.index("\n", i) + 1
            out.append(js[i:fin])
            continue
        i = js.index(f"function {n}(")
        out.append(js[i:js.index("\n}", i) + 2])
    return "\n".join(out)


# ⚠️ `toMonthly` ET `calcEmpCost` SONT EXTRAITS, PAS RECOPIÉS : c'est précisément le coût
# qu'on veut voir converti en écart journalier. Les rejouer ici prouverait que ma copie est
# d'accord avec elle-même.
def _node(programme):
    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")
    r = subprocess.run(["node", "-e", programme], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


SOCLE = """
const JOURS_MOIS = 21.25;
let VER_ORIG = { charge: null, emp: null };
const champs = {};
const document = {
  getElementById: id => champs[id] || (champs[id] = { value: '', checked: false,
                                                      hidden: true, innerHTML: '', focus(){} }),
};
const fmt = v => Number(v).toFixed(2);
function showToast(){}
"""


def _prog(corps, *fns):
    return SOCLE + _extraire(*fns) + "\n" + corps


# ── Le bloc apparaît quand le coût change, et seulement là ───────────────────────────────────

@pytest.mark.parametrize("champ,valeur,attendu", [
    ("charge-amount",    "750", True),
    ("charge-amount",    "700", False),   # le même montant n'est pas un changement
    ("charge-frequency", "annual", True),
])
def test_le_bloc_suit_le_cout_et_pas_le_reste(champ, valeur, attendu):
    r = _node(_prog(f"""
        VER_ORIG.charge = {{ amount: 700, frequency: 'monthly' }};
        champs['charge-amount'] = {{ value: '700' }};
        champs['charge-frequency'] = {{ value: 'monthly' }};
        champs['{champ}'].value = '{valeur}';
        console.log(JSON.stringify({{ change: coutChange('charge') }}));
    """, "VER_CHAMPS", "coutChange", "lireFormulaire"))
    assert r["change"] is attendu


def test_creer_une_charge_nouvre_jamais_le_bloc():
    """Un poste neuf n'a rien à clôturer — il n'a pas à se justifier."""
    r = _node(_prog("""
        VER_ORIG.charge = null;
        champs['charge-amount'] = { value: '40' };
        champs['charge-frequency'] = { value: 'monthly' };
        console.log(JSON.stringify({ change: coutChange('charge') }));
    """, "VER_CHAMPS", "coutChange", "lireFormulaire"))
    assert r["change"] is False


def test_un_centime_dinteret_compte_comme_un_changement():
    r = _node(_prog("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'] = { value: '700.01' };
        champs['charge-frequency'] = { value: 'monthly' };
        console.log(JSON.stringify({ change: coutChange('charge') }));
    """, "VER_CHAMPS", "coutChange", "lireFormulaire"))
    assert r["change"] is True


def test_un_ecart_sous_le_centime_nen_est_pas_un():
    """
    ⚠️ LE SERVEUR ARRONDIT À DEUX DÉCIMALES AVANT DE COMPARER. Si l'écran était plus strict, il
    réclamerait un motif pour un changement que le serveur jugerait nul — et refuserait ensuite
    d'enregistrer en disant « rien à modifier ».
    """
    r = _node(_prog("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'] = { value: '700.004' };
        champs['charge-frequency'] = { value: 'monthly' };
        console.log(JSON.stringify({ change: coutChange('charge') }));
    """, "VER_CHAMPS", "coutChange", "lireFormulaire"))
    assert r["change"] is False


# ── Les salariés ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("champ,valeur,attendu", [
    ("emp-gross",       ("value", "1000"), True),
    ("emp-type",        ("value", "extra"), True),
    ("emp-tsu-exempt",  ("checked", "true"), True),
    ("emp-meal",        ("value", "12"), True),
])
def test_ce_qui_touche_la_paie_ouvre_le_bloc(champ, valeur, attendu):
    cle, val = valeur
    r = _node(_prog(f"""
        VER_ORIG.emp = {{ gross_monthly: 900, type: 'full_time',
                          tsu_exempt: false, meal_card_daily: 10.20 }};
        champs['emp-gross'] = {{ value: '900' }};
        champs['emp-type'] = {{ value: 'full_time' }};
        champs['emp-tsu-exempt'] = {{ checked: false }};
        champs['emp-meal'] = {{ value: '10.20' }};
        champs['{champ}'].{cle} = {val if cle == 'checked' else f"'{val}'"};
        console.log(JSON.stringify({{ change: coutChange('emp') }}));
    """, "VER_CHAMPS", "coutChange", "lireFormulaire"))
    assert r["change"] is attendu


def test_un_horaire_indicatif_ne_touche_pas_la_paie():
    """
    ⚠️ `hours_week` N'ENTRE PAS DANS LE COÛT MENSUEL — ni côté serveur, ni dans `calcEmpCost`.
    Ouvrir le bloc pour lui ferait réclamer un motif là où il n'y a rien à justifier, et cette
    liste doit rester d'accord avec `VERSIONNE` dans `app.py`.
    """
    js = _js()
    assert "'gross_monthly', 'type', 'tsu_exempt', 'meal_card_daily'" in js
    assert "hours_week" not in js[js.index("const VER_CHAMPS"):js.index("function premierDuMoisProchain")]


def test_la_liste_des_champs_versionnes_est_la_meme_des_deux_cotes():
    """
    ⚠️ DEUX LISTES QUI DIVERGENT, C'EST UN BLOC QUI NE S'OUVRE PAS SUR UN CHANGEMENT QUE LE
    SERVEUR REFUSERA — ou l'inverse : un motif réclamé pour rien.
    """
    import app
    js = _js()
    bloc = js[js.index("const VER_CHAMPS"):js.index("function premierDuMoisProchain")]
    for table, cle in (("charges_fixes", "charge"), ("employees", "emp")):
        for champ in app.VERSIONNE[table]:
            assert f"'{champ}'" in bloc, f"{champ} manque côté écran"
        assert len(re.findall(r"'(\w+)'", bloc.split(cle + ":")[1].split("]")[0])) == \
            len(app.VERSIONNE[table]), f"{table} : les deux listes n'ont pas la même longueur"


# ── L'avant/après ────────────────────────────────────────────────────────────────────────────

def test_lecart_journalier_est_montre_car_cest_lui_qui_deplace_le_point_mort():
    """
    ⚠️ QUENTIN LIT SA JOURNÉE EN EUROS PAR JOUR. Un loyer qui passe de 700 à 750 € se lit
    « +50 € par mois » — vrai et inutile ; ce qui compte au comptoir, c'est +2,35 € sur le point
    mort quotidien.
    """
    r = _node(_prog("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'] = { value: '750' };
        champs['charge-frequency'] = { value: 'monthly' };
        const avant = coutMensuel('charge', VER_ORIG.charge);
        const apres = coutMensuel('charge', lireFormulaire('charge'));
        console.log(JSON.stringify({ jour: (apres - avant) / JOURS_MOIS }));
    """, "coutMensuel", "lireFormulaire", "toMonthly", "calcEmpCost"))
    assert round(r["jour"], 2) == 2.35


def test_une_charge_annuelle_est_ramenee_au_mois_avant_comparaison():
    """1 200 € par an et 100 € par mois sont le même coût — passer de l'un à l'autre ne change rien."""
    r = _node(_prog("""
        VER_ORIG.charge = { amount: 100, frequency: 'monthly' };
        console.log(JSON.stringify({
          m: coutMensuel('charge', { amount: 1200, frequency: 'annual' }),
          t: coutMensuel('charge', { amount: 300, frequency: 'quarterly' }),
        }));
    """, "coutMensuel", "lireFormulaire", "toMonthly", "calcEmpCost"))
    assert round(r["m"], 2) == 100.0
    assert round(r["t"], 2) == 100.0


# ── L'historique d'un poste ──────────────────────────────────────────────────────────────────

# ── Ce que les boutons promettent ────────────────────────────────────────────────────────────

def test_aucun_bouton_ne_promet_plus_une_suppression():
    """
    ⚠️ « DELETE » MENTAIT. Le poste n'est pas effacé : il est borné au jour où il cesse, sinon il
    disparaîtrait des mois où il a réellement été payé. Le bouton doit dire ce qui se passe.
    """
    g = _gabarit()
    assert "Delete this cost" not in g and "Delete this employee" not in g
    assert g.count(">Stop…<") == 2


def test_la_bascule_muette_a_disparu():
    """
    ⚠️ « DISABLE » ENVOYAIT UN PATCH SUR `active`, QUI N'EST PLUS NI VERSIONNÉ NI DESCRIPTIF :
    le serveur répondait « ok » sans rien écrire et le bouton restait figé sous le doigt. Le pire
    des états — une commande qui dit oui et ne fait rien.
    """
    g = _gabarit()
    assert "toggleChargeActive" not in g and "toggleEmpActive" not in g
    assert g.count("Reopen…") == 2


# ── Ce que le bloc fait vraiment ─────────────────────────────────────────────────────────────
#
# ⚠️ TESTER `coutChange` NE TESTAIT QUE LA DÉTECTION. Trois mutants ont survécu à la première
# batterie : un bloc toujours ouvert, un motif devenu facultatif, un avant/après qui oubliait la
# TSU. Tous dans les deux fonctions que rien n'appelait ici.

FENETRE = SOCLE + """
champs['charge-ver'] = { hidden: true };
champs['charge-effet'] = { value: '' };
champs['charge-motif'] = { value: '', focus(){} };
champs['charge-apercu'] = { innerHTML: '' };
champs['charge-amount'] = { value: '700' };
champs['charge-frequency'] = { value: 'monthly' };
"""


def _fenetre(corps, *fns):
    return FENETRE + _extraire("VER_CHAMPS", "coutChange", "lireFormulaire", "coutMensuel",
                               "toMonthly", "calcEmpCost", "premierDuMoisProchain", "TSU_EMPLOYER", "JOURS_REPAS_AN",
                               "majApercu", "appliquerVersionnement", *fns) + "\n" + corps


def test_le_bloc_reste_ferme_quand_on_corrige_un_libelle():
    """
    ⚠️ UN BLOC TOUJOURS OUVERT RÉCLAMERAIT UNE JUSTIFICATION POUR REMETTRE UN ACCENT. C'est
    ainsi qu'on retrouve les vrais changements saisis dans le champ « notes ».
    """
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        majApercu('charge');
        console.log(JSON.stringify({ cache: champs['charge-ver'].hidden,
                                     apercu: champs['charge-apercu'].innerHTML }));
    """))
    assert r["cache"] is True
    assert r["apercu"] == ""


def test_le_bloc_souvre_et_propose_le_premier_du_mois_prochain():
    """Les charges se pensent en mois — un loyer ne change pas un 17."""
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'].value = '750';
        majApercu('charge');
        console.log(JSON.stringify({ cache: champs['charge-ver'].hidden,
                                     effet: champs['charge-effet'].value,
                                     apercu: champs['charge-apercu'].innerHTML }));
    """))
    assert r["cache"] is False
    assert r["effet"].endswith("-01")
    assert "700.00" in r["apercu"] and "750.00" in r["apercu"]
    # L'écart journalier, celui qui déplace le point mort.
    assert "2.35" in r["apercu"]


def test_une_date_choisie_nest_pas_ecrasee():
    """⚠️ REPROPOSER LE DÉFAUT À CHAQUE FRAPPE effacerait la date que Quentin vient de saisir."""
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-effet'].value = '2027-01-01';
        champs['charge-amount'].value = '750';
        majApercu('charge');
        console.log(JSON.stringify({ effet: champs['charge-effet'].value }));
    """))
    assert r["effet"] == "2027-01-01"


def test_une_baisse_se_lit_comme_une_baisse():
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'].value = '650';
        majApercu('charge');
        console.log(JSON.stringify({ apercu: champs['charge-apercu'].innerHTML }));
    """))
    assert "baisse" in r["apercu"] and "hausse" not in r["apercu"]
    assert "−" in r["apercu"]


# ── L'envoi ──────────────────────────────────────────────────────────────────────────────────

def test_sans_motif_rien_ne_part():
    """
    ⚠️ LE SERVEUR REFUSE DÉJÀ. Ce contrôle évite un aller-retour pour afficher un message que la
    fenêtre peut donner tout de suite, le curseur dans le bon champ.
    """
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'].value = '750';
        const body = { name: 'Loyer', amount: 750 };
        const ok = appliquerVersionnement('charge', body);
        console.log(JSON.stringify({ ok, body }));
    """))
    assert r["ok"] is False
    assert "reason" not in r["body"]


def test_un_motif_trop_court_nen_est_pas_un():
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'].value = '750';
        champs['charge-motif'].value = 'ok';
        console.log(JSON.stringify({ ok: appliquerVersionnement('charge', {}) }));
    """))
    assert r["ok"] is False


def test_la_date_et_le_motif_partent_avec_le_reste():
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        champs['charge-amount'].value = '750';
        champs['charge-motif'].value = '  hausse annuelle  ';
        champs['charge-effet'].value = '2026-11-01';
        const body = { name: 'Loyer', amount: 750 };
        console.log(JSON.stringify({ ok: appliquerVersionnement('charge', body), body }));
    """))
    assert r["ok"] is True
    assert r["body"]["reason"] == "hausse annuelle"
    assert r["body"]["effective_from"] == "2026-11-01"


def test_une_correction_de_libelle_part_sans_ceremonie():
    r = _node(_fenetre("""
        VER_ORIG.charge = { amount: 700, frequency: 'monthly' };
        const body = { name: 'Loyer (Rua da Indústria)' };
        console.log(JSON.stringify({ ok: appliquerVersionnement('charge', body), body }));
    """))
    assert r["ok"] is True
    assert "reason" not in r["body"] and "effective_from" not in r["body"]


# ── L'avant/après d'un salaire ───────────────────────────────────────────────────────────────

def test_lavant_apres_dun_salaire_compte_la_tsu_et_la_carte_repas():
    """
    ⚠️ MONTRER LE BRUT SERAIT MENTIR DE 40 %. Un salarié coûte son brut × 14 mois, plus 23,75 %
    de TSU, plus la carte repas : c'est ce total qui entre dans le point mort, et c'est l'écart
    de CE total qu'il faut lire avant de valider une augmentation.
    """
    r = _node(_fenetre("""
        const av = coutMensuel('emp', { gross_monthly: 900, type: 'full_time',
                                        tsu_exempt: false, meal_card_daily: 10.20 });
        const ap = coutMensuel('emp', { gross_monthly: 1000, type: 'full_time',
                                        tsu_exempt: false, meal_card_daily: 10.20 });
        console.log(JSON.stringify({ av, ap }));
    """))
    # 900 × 14 × 1,2375 / 12 = 1 299,38 €, plus la carte repas.
    assert r["av"] > 900 * 1.35
    # Un centime près : l'ordre des opérations diffère, la règle non.
    assert abs((r["ap"] - r["av"]) - 100 * 14 * 1.2375 / 12) < 0.02


def test_un_extra_est_paye_tel_quel():
    """Un extra n'a ni 14e mois ni carte repas — lui appliquer la formule salariale gonflerait
    son coût de 40 % les mois de gros service, précisément ceux où l'on en emploie."""
    r = _node(_fenetre("""
        console.log(JSON.stringify({ c: coutMensuel('emp', { gross_monthly: 600, type: 'extra',
                                     tsu_exempt: false, meal_card_daily: 10.20 }) }));
    """))
    assert r["c"] == 600


# ── Ce qui est décidé mais pas encore en vigueur ─────────────────────────────────────────────
#
# ⚠️ UNE MODIFICATION VALIDÉE NE SE VOYAIT NULLE PART. Quentin a arrêté Julie au 1er octobre ; le
# coût du jour n'a pas bougé — c'est juste, elle est payée jusque-là. Mais rien à l'écran ne le
# disait, et la ligne affichait « ended » dès la validation. On lit « c'est fait » devant un
# chiffre inchangé : la seule conclusion possible est que le bouton n'a pas marché.

HORLOGE = """
const AUJ = new Date(2026, 8, 21);   // 21 septembre 2026
function aujourdhui() { return AUJ; }
let chargesData = [], employeesData = [];
"""


def _monde(corps, *fns):
    return SOCLE + HORLOGE + _extraire("TSU_EMPLOYER", "JOURS_REPAS_AN", "toMonthly",
                                       "calcEmpCost", "applicableLe", "totalLe",
                                       "prochainChangement", "histoLigne", *fns) + "\n" + corps


@pytest.mark.parametrize("ligne,attendu", [
    ({"valid_to": "2026-10-01"}, "ends 1 Oct 2026"),
    ({"valid_to": "2026-09-21"}, "ended 21 Sept 2026"),    # aujourd'hui : la borne est atteinte
    ({"valid_to": "2026-09-01"}, "ended 1 Sept 2026"),
    ({"valid_from": "2026-05-01", "valid_to": "2026-10-01"}, "1 May 2026 → ends 1 Oct 2026"),
    ({"valid_from": "2026-10-01"}, "since 1 Oct 2026"),
    ({}, ""),    # une ligne sans bornes n'a rien à raconter
])
def test_la_periode_se_lit_sur_la_ligne(ligne, attendu):
    r = _node(_monde(f"console.log(JSON.stringify({{ t: histoLigne({json.dumps(ligne)}) }}));"))
    assert r["t"] == attendu


def test_un_arret_programme_est_annonce_avec_sa_date():
    """C'est la seule chose qui distingue « validé » de « sans effet »."""
    r = _node(_monde("""
        employeesData = [
          { name: 'Ana',   gross_monthly: 900, type: 'full_time', tsu_exempt: false,
            meal_card_daily: 10.20, active: true },
          { name: 'Julie', gross_monthly: 600, type: 'extra', tsu_exempt: false,
            meal_card_daily: 0, active: true, valid_to: '2026-10-01' },
        ];
        const p = prochainChangement();
        console.log(JSON.stringify({ quand: p.quand.toISOString().slice(0,10),
                                     avant: p.avant, apres: p.apres }));
    """))
    assert r["quand"] == "2026-10-01"
    assert round(r["avant"] - r["apres"], 2) == 600.0   # l'extra est payé tel quel


def test_le_cout_du_jour_ignore_ce_qui_nest_pas_encore_en_vigueur():
    """
    ⚠️ ET C'EST TOUT L'INTÉRÊT. Julie est payée jusqu'au 1er octobre : la retirer du coût dès la
    validation ferait mentir le point mort de ce soir.
    """
    r = _node(_monde("""
        employeesData = [{ name: 'Julie', gross_monthly: 600, type: 'extra', tsu_exempt: false,
                           meal_card_daily: 0, active: true, valid_to: '2026-10-01' }];
        console.log(JSON.stringify({ auj: totalLe(aujourdhui()),
                                     apres: totalLe(new Date(2026, 9, 1)) }));
    """))
    assert r["auj"] == 600
    assert r["apres"] == 0


def test_rien_a_annoncer_quand_rien_nest_programme():
    r = _node(_monde("""
        chargesData = [{ amount: 700, frequency: 'monthly', active: true }];
        console.log(JSON.stringify({ p: prochainChangement() }));
    """))
    assert r["p"] is None


def test_une_bascule_sans_effet_sur_le_total_ne_sannonce_pas():
    """
    ⚠️ UNE CLÔTURE SUIVIE D'UN REMPLACEMENT AU MÊME MONTANT NE CHANGE RIEN. Annoncer « à partir
    du 1er octobre : 700 € » alors qu'on est déjà à 700 € ferait chercher un changement qui
    n'existe pas — et userait l'attention qu'on veut garder pour les vrais.
    """
    r = _node(_monde("""
        chargesData = [
          { amount: 700, frequency: 'monthly', active: true, valid_to: '2026-10-01' },
          { amount: 700, frequency: 'monthly', active: false, valid_from: '2026-10-01' },
        ];
        console.log(JSON.stringify({ p: prochainChangement() }));
    """))
    assert r["p"] is None


def test_cest_la_plus_proche_des_dates_qui_est_annoncee():
    r = _node(_monde("""
        chargesData = [
          { amount: 700, frequency: 'monthly', active: true, valid_to: '2026-12-01' },
          { amount: 200, frequency: 'monthly', active: true, valid_to: '2026-10-01' },
        ];
        console.log(JSON.stringify({ q: prochainChangement().quand.toISOString().slice(0,10) }));
    """))
    assert r["q"] == "2026-10-01"


def test_une_ligne_eteinte_a_la_main_ne_compte_pas_a_lecran_non_plus():
    """
    ⚠️ LA MÊME RÈGLE QUE `charges.py` : sans bornes, `active` est la borne. Si l'écran en
    décidait autrement, il afficherait un coût du jour que le serveur ne calcule pas — et c'est
    l'écran que Quentin regarde pour décider.
    """
    r = _node(_monde("""
        chargesData = [{ amount: 120, frequency: 'monthly', active: false }];
        console.log(JSON.stringify({ t: totalLe(aujourdhui()) }));
    """))
    assert r["t"] == 0


def test_un_changement_deja_passe_nest_pas_annonce_comme_a_venir():
    """
    ⚠️ « À PARTIR DU 1er MAI » LU EN SEPTEMBRE EST UN BANDEAU QU'ON APPREND À IGNORER. Le loyer
    a changé au 1er mai : c'est dans le chiffre du haut depuis quatre mois, il n'y a rien à
    attendre. Un avis permanent sur un événement révolu use l'attention qu'on veut garder pour
    le jour où quelque chose est vraiment programmé.
    """
    r = _node(_monde("""
        chargesData = [
          { amount: 700, frequency: 'monthly', active: false, valid_to: '2026-05-01' },
          { amount: 750, frequency: 'monthly', active: true,  valid_from: '2026-05-01' },
        ];
        console.log(JSON.stringify({ p: prochainChangement() }));
    """))
    assert r["p"] is None


def test_seules_les_dates_a_venir_sont_retenues():
    """Une ligne peut porter une borne passée ET une borne à venir — c'est la seconde qui compte."""
    r = _node(_monde("""
        chargesData = [{ amount: 700, frequency: 'monthly', active: true,
                         valid_from: '2026-05-01', valid_to: '2026-11-01' }];
        console.log(JSON.stringify({ q: prochainChangement().quand.toISOString().slice(0,10) }));
    """))
    assert r["q"] == "2026-11-01"


# ── Ce que la suppression efface, dit avant de confirmer ─────────────────────────────────────
#
# ⚠️ LE CHOIX ENTRE « STOP » ET « DELETE » SE PREND EN VOYANT CE QUE CHACUN FAIT. Effacer une
# fiche d'essai ne change rien ; effacer quelqu'un qui a été payé de mai à septembre retire son
# coût de ces cinq mois, et ces mois-là ont déjà servi à décider quelque chose. Les deux gestes
# sont le même clic — seule la conséquence diffère, donc c'est elle qu'il faut montrer.

def _effet(ligne, mensuel):
    return _node(_monde(f"""
        console.log(JSON.stringify(effetSuppression({json.dumps(ligne)}, {mensuel})));
    """, "effetSuppression", "arretAVenir"))


def test_effacer_une_fiche_qui_ne_coute_rien_ne_change_rien():
    """Une ligne d'essai à 0 € n'a aucun passé à préserver — et l'écran doit le dire, pas
    brandir un avertissement qui ferait hésiter sur le bon geste."""
    e = _effet({"valid_from": "2026-05-01"}, 0)
    assert e["mois"] == 0
    assert "changes no figure" in e["texte"]


def test_effacer_un_poste_paye_depuis_mai_annonce_les_cinq_mois():
    e = _effet({"valid_from": "2026-05-01"}, 1200)
    assert e["mois"] == 5                       # mai, juin, juillet, août, septembre
    assert "May 2026 to September 2026" in e["texte"]
    assert "1200.00" in e["texte"]
    assert "Stop" in e["texte"], "l'autre porte n'est pas proposée"


def test_une_ligne_sans_date_de_debut_a_compte_partout():
    """
    ⚠️ `valid_from` NUL VEUT DIRE « DEPUIS TOUJOURS ». Annoncer « 1 mois » pour une ligne sans
    borne ferait croire l'effacement anodin alors qu'il touche tout l'historique.
    """
    e = _effet({}, 700)
    assert e["mois"] is None
    assert "every month on record" in e["texte"]


def test_un_poste_deja_arrete_ne_compte_que_jusqua_son_arret():
    e = _effet({"valid_from": "2026-05-01", "valid_to": "2026-07-01"}, 900)
    assert e["mois"] == 3                       # mai, juin, juillet
    assert "July 2026" in e["texte"]


def test_un_poste_qui_na_pas_encore_commence_nefface_aucun_passe():
    """La ligne de remplacement créée ce matin pour le 1er octobre : rien à réécrire."""
    e = _effet({"valid_from": "2026-11-01"}, 750)
    assert e["mois"] == 0
    assert "not started yet" in e["texte"]


def test_un_seul_mois_se_dit_au_singulier():
    e = _effet({"valid_from": "2026-09-01"}, 300)
    assert e["mois"] == 1
    assert "(1 month)" in e["texte"] and "(1 months)" not in e["texte"]


# ── Annuler un arrêt, ou rouvrir : deux gestes différents ────────────────────────────────────

@pytest.mark.parametrize("ligne,attendu", [
    ({"valid_to": "2026-10-01"}, True),     # programmé, pas encore pris
    ({"valid_to": "2026-09-21"}, False),    # aujourd'hui : la borne est franchie
    ({"valid_to": "2026-08-01"}, False),    # déjà pris
    ({}, False),
])
def test_on_nannule_que_ce_qui_nest_pas_encore_arrive(ligne, attendu):
    """
    ⚠️ RETIRER UNE BORNE DÉJÀ FRANCHIE REMETTRAIT LE POSTE EN SERVICE SUR TOUTE L'INTERRUPTION.
    Après la date, la bonne porte est « Reopen… », qui ouvre une ligne neuve et laisse
    l'interruption dans l'historique.
    """
    r = _node(_monde(f"console.log(JSON.stringify({{ a: arretAVenir({json.dumps(ligne)}) }}));",
                     "arretAVenir"))
    assert r["a"] is attendu


def test_les_trois_boutons_existent_et_ne_se_confondent_pas():
    g = _gabarit()
    # ⚠️ ON COMPTE DES BOUTONS, PAS DES OCCURRENCES. « Stop… » apparaît aussi dans le texte qui
    # explique la suppression — chercher la chaîne nue comptait ce libellé-là et passait au vert
    # même si le bouton avait disparu.
    assert g.count(">Cancel stop<") == 2    # un arrêt programmé s'annule
    assert g.count(">Reopen…<") == 2        # un arrêt pris se reprend par une ligne neuve
    assert g.count(">Stop…<") == 2          # un poste en cours s'arrête à une date
    assert g.count("supprimerDefinitivement(") == 3   # deux boutons + la définition
