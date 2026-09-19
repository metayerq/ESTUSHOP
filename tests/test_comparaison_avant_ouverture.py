"""
La fenêtre de comparaison ne peut pas précéder l'ouverture du café.

⚠️ CE QUE FAISAIT L'ANCIENNE VERSION. « Depuis l'ouverture » couvre 84 jours au 18 août ; la
fenêtre précédente de même longueur remontait donc au 4 mars, soit 84 jours pendant lesquels le
café n'existait pas. Trois conséquences, aucune visible à l'écran :

 1. une ligne `daily_summary` À ZÉRO écrite pour chacun de ces jours — et comme la période
    s'allonge d'un jour par jour, la fenêtre RECULE indéfiniment ;
 2. une lecture Vendus détaillée sur une plage où il n'y a rien à lire ;
 3. surtout, une comparaison affichée contre le NÉANT : `calc_stats([])` rend des zéros, donc
    l'écran montrait une progression contre une base inexistante.

⚠️ ET TRONQUER SERAIT PIRE QUE S'ABSTENIR. Borner la fenêtre à l'ouverture donnerait 84 jours
opposés à 12 : une chute spectaculaire qui ne serait qu'une différence de durée.
"""
import sys
sys.path.insert(0, ".")

from datetime import date, timedelta

import app


OUVERTURE = date.fromisoformat(app.OPENING_DAY)


def _fenetre(from_date, to_date):
    """
    La fenêtre par défaut de `/api/data`, passée à la VRAIE garde.

    ⚠️ PREMIÈRE VERSION DE CE FICHIER : la garde était recopiée ici. Deux mutations d'`app.py`
    survivaient donc — dont « tronquer au lieu de s'abstenir », c'est-à-dire le défaut le plus
    coûteux du lot. Un test qui rejoue la règle ne teste que lui-même.
    """
    n = (to_date - from_date).days + 1
    comp_to = from_date - timedelta(1)
    comp_from = comp_to - timedelta(n - 1)
    return app._usable_comparison(comp_from, comp_to)


def test_depuis_l_ouverture_n_a_aucune_periode_precedente():
    """C'est le cas qui écrivait le cache à l'infini."""
    _, _, existe = _fenetre(OUVERTURE, date(2026, 8, 18))
    assert existe is False


def test_une_fenetre_qui_chevauche_l_ouverture_est_ecartee_aussi():
    """
    ⚠️ LE CAS SUBTIL. Elle n'est pas vide — elle est PLUS COURTE. La comparer ferait lire une
    différence de durée comme un effondrement du chiffre.
    """
    debut = OUVERTURE + timedelta(10)
    comp_from, comp_to, existe = _fenetre(debut, debut + timedelta(20))
    assert comp_from < OUVERTURE, "le test ne couvre pas le cas visé"
    assert comp_to >= OUVERTURE, "la fenêtre devait chevaucher, pas précéder entièrement"
    assert existe is False


def test_une_fenetre_entierement_posterieure_reste_comparable():
    """La garde ne doit pas emporter les comparaisons légitimes — l'essentiel des presets."""
    debut = OUVERTURE + timedelta(60)
    _, _, existe = _fenetre(debut, debut + timedelta(6))
    assert existe is True


def test_la_garde_est_branchee_dans_app():
    """
    ⚠️ VÉRIFIE LE BRANCHEMENT, PAS LA RÈGLE. Les tests ci-dessus rejouent le calcul ; celui-ci
    s'assure que `/api/data` le porte réellement — sinon la règle serait juste et personne pour
    l'appliquer, le trou classique de ce dépôt.
    """
    import ast
    import inspect
    import textwrap

    src = inspect.getsource(app.api_data)
    assert "comp_exists" in src, "la garde a disparu de /api/data"

    # Elle doit conditionner l'ÉCRITURE du cache, pas seulement l'affichage.
    #
    # ⚠️ ON INTERROGE L'ARBRE, PAS LE TEXTE. La première version exigeait la ligne exacte
    # `_ensure_summaries(comp_from, comp_to, catalog) if comp_exists`. Une fusion a déplacé cet
    # appel vers une variable réutilisée — la garde était toujours là, correcte, et le test
    # tombait quand même. Un test qui impose une FORMULATION plutôt qu'une PROPRIÉTÉ finit par
    # être « réparé » en recopiant la formulation, ce qui le vide de son sens.
    arbre = ast.parse(textwrap.dedent(src))

    def porte_la_garde(noeud):
        return any(isinstance(n, ast.Name) and n.id == "comp_exists"
                   for n in ast.walk(noeud))

    # Chaque ternaire et chaque `if` du corps, avec ce qu'ils gardent.
    gardes = [n for n in ast.walk(arbre)
              if isinstance(n, (ast.IfExp, ast.If)) and porte_la_garde(n.test)]

    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "_ensure_summaries"
              and [getattr(a, "id", None) for a in n.args[:2]] == ["comp_from", "comp_to"]]

    assert appels, "plus aucun appel `_ensure_summaries(comp_from, comp_to, …)` dans /api/data"
    for appel in appels:
        assert any(appel in ast.walk(g) for g in gardes), (
            f"l'appel `_ensure_summaries` de la ligne {appel.lineno} de /api/data n'est plus "
            "gardé par `comp_exists` : il figera des journées antérieures à l'ouverture du café"
        )
    # Et la lecture Vendus. ⚠️ On cible `_load_comp` NOMMÉMENT : chercher « if not comp_exists »
    # dans toute la fonction passait aussi sur la ligne qui efface le libellé, si bien que
    # débrancher la lecture laissait le test vert. Une assertion qui ne peut pas tomber ne
    # protège rien.
    assert "_usable_comparison(comp_from, comp_to)" in src, "la garde n'est plus appelée"
    # Le LIBELLÉ doit tomber avec la comparaison. Sans ça, l'écran affiche « vs previous
    # 84 days » sous des chiffres qui ne sont comparés à rien — la pire des trois issues, parce
    # que c'est la seule que le lecteur croit.
    assert "comp_label = None" in src, "le libellé survit à une comparaison inexistante"
    corps = src[src.index("def _load_comp():"):]
    corps = corps[:corps.index("def _load_heatmap_payload")]
    assert "if not comp_exists:" in corps, "la lecture Vendus n'est plus gardée"
    assert "return None" in corps
