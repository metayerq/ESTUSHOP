"""
LE BOUTON DE RECONSTRUCTION DE L'HISTORIQUE.

⚠️ IL DÉCLENCHE DES CENTAINES D'APPELS À L'API REVOLUT. Trois façons de mal faire, toutes
silencieuses : des tranches trop longues (la fonction est tuée au milieu), des tranches en
parallèle (la limite de débit fait échouer au hasard celles qu'on croira reconstruites), et un
échec qui ne dit pas où reprendre.
"""

import os
import re

import pytest

import app as flask_app


def _gabarit():
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "templates", "reconciliation.html")
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def _script():
    return "\n".join(re.findall(r"<script>(.*?)</script>", _gabarit(), re.S))


def test_les_bornes_viennent_du_serveur(monkeypatch):
    """
    ⚠️ LE NAVIGATEUR CALCULE « HIER » EN HEURE LOCALE DE L'APPAREIL. Entre minuit et 1 h à
    Lisbonne, un iPad réglé sur un autre fuseau proposerait une plage décalée d'un jour, et la
    reconstruction manquerait une journée sans le dire — exactement le bug de fuseau qui a déjà
    frappé cette page.
    """
    html = _gabarit()
    assert 'id="rb-from" value="{{ open_date }}"' in html
    assert 'id="rb-to" value="{{ hier }}"' in html
    # Et la route les fournit.
    import inspect
    src = inspect.getsource(flask_app.reconciliation_page)
    assert "open_date=OPENING_DAY" in src
    assert "today_lisbon()" in src


def test_les_tranches_sont_enchainees_et_non_lancees_ensemble():
    """
    ⚠️ EN PARALLÈLE, LA LIMITE DE DÉBIT REVOLUT FAIT ÉCHOUER DES TRANCHES AU HASARD — celles-là
    même qu'on croirait reconstruites. La boucle doit attendre chaque appel.
    """
    js = _script()
    i = js.index("for (const [a, b] of lots)")
    bloc = js[i:js.index("etat.innerHTML = `<b>Terminé", i)]
    assert "await fetch(" in bloc, "les tranches ne sont pas attendues"
    assert "Promise.all" not in js, "des tranches partent en parallèle"


def test_un_echec_nomme_la_date_de_reprise_et_la_passe():
    """
    ⚠️ SANS LA DATE, IL FAUT TOUT REFAIRE OU DEVINER. Et sans la PASSE, on refait la
    reconstruction Revolut alors que c'est la reconstruction Vendus qui a échoué — dix minutes
    pour rien.
    """
    js = _script()
    i = js.index("Arrêté sur")
    bloc = js[i:i + 400]
    assert "Du = ${a}" in bloc
    assert "${libelle}" in bloc, "le message ne dit pas quelle passe a échoué"
    assert "${deja}" in bloc, "le message ne dit pas ce qui est déjà acquis"


def test_les_deux_passes_senchainent_dans_le_bon_ordre():
    """
    ⚠️ LE TERMINAL D'ABORD, VENDUS ENSUITE — et la seconde ne part que si la première a réussi.
    Reconstruire la répartition Vendus sans l'encaissement donnerait des écarts calculés contre
    un terminal vide : chaque journée afficherait « tout le chiffre manque ».
    """
    js = _script()
    i = js.index("/api/terminal-days/sync")
    j = js.index("/api/summary/rebuild")
    assert i < j
    assert "if (!await enchainer('/api/terminal-days/sync'" in js
    assert js[i:j].count("return;") >= 1, "la seconde passe part même si la première a échoué"


def test_chaque_passe_a_sa_propre_largeur_de_tranche():
    """
    Une journée de café coûte ~25 appels à Revolut ; côté Vendus c'est chaque document AVEC ses
    lignes. Les deux ne tiennent pas la même largeur dans les 60 secondes de la fonction.
    """
    js = _script()
    assert "tranches(from, to, 10)" in js
    assert "tranches(from, to, 7)" in js


def test_le_bouton_se_verrouille_pendant_le_travail():
    """
    ⚠️ ET SE DÉVERROUILLE SUR TOUTES LES SORTIES. Un `finally` couvre le succès, l'échec d'une
    passe et l'exception imprévue — trois `btn.disabled = false` dispersés en oublient toujours
    une, et l'écran reste bloqué sans rien dire.
    """
    js = _script()
    assert "btn.disabled = true" in js
    i = js.index("btn.disabled = true")
    bloc = js[i:]
    assert "finally" in bloc, "le déverrouillage n'est pas garanti sur toutes les sorties"
    assert "btn.disabled = false" in bloc[bloc.index("finally"):]


def test_le_decoupage_couvre_la_plage_sans_trou_ni_recouvrement():
    """
    ⚠️ CE TEST EXÉCUTE LE VRAI JAVASCRIPT, et c'est tout l'intérêt. Sa première version
    réimplémentait le découpage en Python et vérifiait donc sa propre copie : le mutant qui
    faisait se RECOUVRIR les tranches (`plus(d, largeur)` au lieu de `largeur - 1`) passait
    tranquillement. Un recouvrement ne casse rien de visible — il refait des jours déjà faits,
    et fait simplement durer la reconstruction deux fois plus longtemps.

    ⚠️ ET UN TROU, LUI, NE SE VERRAIT JAMAIS : une journée non reconstruite ressemble en tout
    point à une journée sans vente.
    """
    import json
    import shutil
    import subprocess

    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")

    js = _script()
    debut = js.index("  const iso = d =>")
    fin = js.index("  async function enchainer")
    programme = js[debut:fin] + """
    const lots = tranches('2026-05-27', '2026-09-19', 10);
    console.log(JSON.stringify(lots));
    """
    sortie = subprocess.run(["node", "-e", programme], capture_output=True, text=True,
                            timeout=20)
    assert sortie.returncode == 0, sortie.stderr
    lots = json.loads(sortie.stdout)

    from datetime import date, timedelta
    debut_d, fin_d = date(2026, 5, 27), date(2026, 9, 19)
    assert lots[0][0] == debut_d.isoformat()
    assert lots[-1][1] == fin_d.isoformat()
    couverts = []
    for a, b in lots:
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        assert (db - da).days <= 9, f"la tranche {a} → {b} dépasse dix jours"
        d = da
        while d <= db:
            couverts.append(d)
            d += timedelta(1)
    attendus = [debut_d + timedelta(n) for n in range((fin_d - debut_d).days + 1)]
    assert couverts == attendus, "trou ou recouvrement dans le découpage"


def test_la_largeur_demandee_est_respectee():
    """Sept jours côté Vendus, dix côté Revolut — les deux passes ne s'échangent pas."""
    import json
    import shutil
    import subprocess

    if not shutil.which("node"):
        pytest.skip("node absent — vérifié en local et à la revue")

    js = _script()
    programme = js[js.index("  const iso = d =>"):js.index("  async function enchainer")] + """
    console.log(JSON.stringify(tranches('2026-05-01', '2026-05-21', 7)));
    """
    lots = json.loads(subprocess.run(["node", "-e", programme], capture_output=True,
                                     text=True, timeout=20).stdout)
    assert lots == [["2026-05-01", "2026-05-07"], ["2026-05-08", "2026-05-14"],
                    ["2026-05-15", "2026-05-21"]]
