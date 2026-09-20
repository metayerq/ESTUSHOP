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


def test_un_echec_nomme_la_date_de_reprise():
    """Sans elle, il faut tout refaire ou deviner."""
    js = _script()
    i = js.index("Arrêté sur")
    bloc = js[i:i + 400]
    assert "Du = ${a}" in bloc
    assert "précédentes sont enregistrées" in bloc


def test_le_bouton_se_verrouille_pendant_le_travail():
    js = _script()
    assert "btn.disabled = true" in js
    # Et il se déverrouille sur les DEUX sorties — succès comme échec.
    assert js.count("btn.disabled = false") >= 2


def test_le_decoupage_couvre_la_plage_sans_trou_ni_recouvrement():
    """
    Le découpage est en JavaScript ; on le rejoue ici en Python sur la même règle — dix jours
    de J à J+9, bornes incluses — parce qu'un trou d'un jour ne se verrait jamais à l'écran.
    """
    from datetime import date, timedelta

    def tranches(debut, fin):
        out, d = [], debut
        while d <= fin:
            bout = min(d + timedelta(9), fin)
            out.append((d, bout))
            d = bout + timedelta(1)
        return out

    debut, fin = date(2026, 5, 27), date(2026, 9, 19)
    lots = tranches(debut, fin)
    assert lots[0][0] == debut and lots[-1][1] == fin
    for (a, b), (c, _) in zip(lots, lots[1:]):
        assert (b - a).days <= 9, "une tranche dépasse dix jours"
        assert c == b + timedelta(1), "trou ou recouvrement entre deux tranches"
    couverts = sum((b - a).days + 1 for a, b in lots)
    assert couverts == (fin - debut).days + 1
