"""
L'édition d'un pop-up détachait silencieusement l'occurrence de sa série.

L'écriture passe par un upsert PostgREST en `merge-duplicates` : tout champ présent dans la
ligne ÉCRASE la valeur en base. `series_id` et `active` y figuraient toujours — le premier à
`None` faute d'être envoyé par le formulaire d'édition, le second forcé à `True`.

Conséquence concrète : `deleteSeries` (templates/events.html) retrouve les occurrences sœurs
par `series_id`. Une occurrence éditée n'en avait plus, donc « Supprimer la série » la laissait
derrière. Le titre changeait bien à l'écran ; le lien disparaissait sans un mot.

`notes` était déjà protégé par le même garde depuis longtemps. Les deux autres avaient été
oubliés — c'est le garde qui manquait, pas l'intention.
"""
import sys
sys.path.insert(0, ".")

import app


def _edition(**extra):
    """Ce que le formulaire d'édition envoie réellement : pas de series_id, pas de active."""
    return {"id": "ev-1", "title": "Pop-up torréfacteur", "date": "2026-08-10", **extra}


def _creation(**extra):
    return {"title": "Pop-up torréfacteur", "date": "2026-08-10", **extra}


# ── Le défaut lui-même ───────────────────────────────────────────────────────

def test_une_edition_ne_touche_pas_au_series_id_qu_elle_n_a_pas_recu():
    row = app._build_event_row(_edition(), "planned")
    assert "series_id" not in row, (
        "series_id présent dans l'upsert : il écraserait la valeur en base à NULL")


def test_une_edition_ne_ressuscite_pas_un_evenement_desactive():
    row = app._build_event_row(_edition(), "planned")
    assert "active" not in row, "active forcé à True écraserait un événement désactivé"


def test_une_edition_qui_envoie_le_series_id_le_respecte():
    """Le garde protège l'omission, il n'interdit pas la mise à jour explicite."""
    row = app._build_event_row(_edition(series_id="ser-7"), "planned")
    assert row["series_id"] == "ser-7"


def test_une_edition_peut_detacher_volontairement_une_occurrence():
    """`series_id: None` ENVOYÉ est une intention, pas un oubli — elle doit passer."""
    row = app._build_event_row(_edition(series_id=None), "planned")
    assert "series_id" in row and row["series_id"] is None


# ── La création ne change pas ────────────────────────────────────────────────

def test_une_creation_isolee_porte_toujours_ses_valeurs_par_defaut():
    row = app._build_event_row(_creation(), "planned")
    assert row["series_id"] is None
    assert row["active"] is True
    assert "id" not in row


def test_une_creation_de_serie_conserve_son_series_id():
    row = app._build_event_row(_creation(series_id="ser-7"), "confirmed")
    assert row["series_id"] == "ser-7"
    assert row["status"] == "confirmed"


# ── Les notes gardent le comportement qu'elles avaient déjà ──────────────────

def test_les_notes_ne_sont_ecrites_que_si_elles_sont_envoyees():
    assert "notes" not in app._build_event_row(_edition(), "planned")
    assert "notes" not in app._build_event_row(_creation(), "planned")
    assert app._build_event_row(_edition(notes="rappeler le fournisseur"),
                                "planned")["notes"] == "rappeler le fournisseur"


# ── Les champs du formulaire, eux, sont toujours écrits ──────────────────────

def test_les_champs_du_formulaire_sont_ecrits_meme_vides():
    """
    Vider le lieu ou l'heure doit les effacer en base. Ces champs-là viennent TOUJOURS du
    formulaire : leur absence signifie « vide », pas « inchangé » — l'inverse de series_id.
    """
    row = app._build_event_row(_edition(location="", start_time=""), "planned")
    assert row["location"] == ""
    assert row["start_time"] is None
    assert row["id"] == "ev-1"


# ── Ce que les clients voient ───────────────────────────────────────────────────────────────
#
# ⚠️ CES QUATRE CHAMPS SONT LES SEULS DE CE FORMULAIRE QUI SORTENT DU CAFÉ. Les trois premiers
# atterrissent sur la page de points de chaque client ; le quatrième décide si l'événement y
# atterrit du tout. Aucune de leurs pannes ne se voit depuis le backoffice.


def test_les_champs_publics_ne_sont_pas_inventes_a_la_mise_a_jour():
    """⚠️ MÊME GARDE QUE `notes`, ET POUR UNE RAISON PLUS COÛTEUSE ENCORE.

    L'écriture est un upsert `merge-duplicates` : tout champ présent ÉCRASE la base. Un écran qui
    corrige un horaire sans porter le champ photo effacerait donc l'affiche — silencieusement, et
    sans que personne ne sache quand elle a disparu.
    """
    row = app._build_event_row({"id": "e1", "title": "Fado", "date": "2026-10-03"}, "planned")
    for champ in ("image_url", "link_url", "link_label", "show_on_card"):
        assert champ not in row, f"{champ} a été inventé sur une mise à jour"


def test_les_champs_publics_traversent_quand_ils_sont_envoyes():
    row = app._build_event_row(
        {
            "id": "e1",
            "title": "Fado",
            "date": "2026-10-03",
            "image_url": "https://x.pt/a.jpg",
            "link_url": "https://x.pt/bilhetes",
            "link_label": "Reservar",
            "show_on_card": False,
        },
        "planned",
    )
    assert row["image_url"] == "https://x.pt/a.jpg"
    assert row["link_url"] == "https://x.pt/bilhetes"
    assert row["link_label"] == "Reservar"
    assert row["show_on_card"] is False


def test_un_champ_public_vide_devient_nul_et_non_chaine_vide():
    """Une chaîne vide dans `image_url` donnerait un `<img src="">` : le navigateur recharge la
    page courante comme si c'était l'image, ce qui double la requête sans rien afficher."""
    row = app._build_event_row(
        {"id": "e1", "title": "x", "date": "2026-10-03", "image_url": "   ", "link_url": ""},
        "planned",
    )
    assert row["image_url"] is None
    assert row["link_url"] is None


def test_un_evenement_cree_est_visible_par_defaut():
    """⚠️ `True` À LA CRÉATION, pour ne rien changer à ce qui marchait : les événements
    s'affichaient déjà sur la page client avant l'existence de cette case."""
    row = app._build_event_row({"title": "Fado", "date": "2026-10-03"}, "planned")
    assert row["show_on_card"] is True


# ── Le silence d'un chargement raté ─────────────────────────────────────────────────────────
#
# ⚠️ UN CALENDRIER VIDE PARCE QU'IL N'Y A RIEN CE MOIS-CI ET UN CALENDRIER VIDE PARCE QUE LA BASE
# N'A PAS RÉPONDU SE RESSEMBLENT TRAIT POUR TRAIT. Ils se corrigent de façons opposées, et l'un des
# deux se décrit par « je ne peux pas cliquer sur mes événements » — ce qui envoie chercher dans le
# clic, pas dans la lecture.


def _page_events():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent.joinpath("templates/events.html").read_text()


def _page_events_sans_commentaires():
    """⚠️ LES COMMENTAIRES CITENT CE QU'ILS EXPLIQUENT. Le pavé qui justifie l'emploi du JETON
    plutôt que de la valeur écrit `#B42318` — et le contrôle qui cherchait cette valeur trouvait
    donc sa propre justification. C'est la HUITIÈME fois que ce piège se referme dans ce produit :
    un détecteur qui cite ce qu'il traque finit toujours par se reconnaître."""
    import re
    s = _page_events()
    s = re.sub(r"/\*[\s\S]*?\*/", " ", s)        # commentaires CSS et JS en bloc
    s = re.sub(r"<!--[\s\S]*?-->", " ", s)        # commentaires HTML
    s = re.sub(r"(?m)^\s*//.*$", " ", s)           # commentaires JS de ligne
    return s


def test_un_chargement_rate_ne_se_tait_pas():
    """⚠️ `events = er.ok ? … : []` AVALAIT TOUT : session expirée, erreur Supabase, 500. La page
    s'affichait normalement, le mois se dessinait, et il n'y avait aucun événement dessus."""
    s = _page_events()
    assert "signalerPanne('Les événements n" in s, "une lecture ratée est redevenue silencieuse"
    assert "session expirée" in s, "le cas le plus fréquent n'est plus nommé"


def test_une_panne_de_taches_nemporte_pas_les_evenements():
    """Les deux lectures étaient liées par un `catch` commun : une panne sur les tâches —
    accessoires — vidait le calendrier entier."""
    s = _page_events()
    i = s.index("async function loadAll")
    corps = s[i:s.index("\n}", i)]
    # Les tâches ont leur propre branche d'échec, distincte de celle des événements.
    assert corps.count("signalerPanne") >= 3, "les échecs ne sont plus distingués"
    assert "le calendrier reste utilisable" in corps


def test_les_pannes_javascript_sont_affichees_a_l_ecran():
    """⚠️ « Regarde la console » ne veut rien dire sur un iPad, et ce backoffice s'y ouvre."""
    s = _page_events_sans_commentaires()
    assert "window.addEventListener('error'" in s
    assert "unhandledrejection" in s, "une promesse rejetée resterait muette"
    # ⚠️ LE JETON, PAS LA VALEUR : un rouge en dur reste vif en mode sombre, où la charte
    # l'éclaircit. Un bandeau d'erreur illisible est un bandeau qu'on ignore.
    assert "var(--red)" in s and "#B42318" not in s


# ── La propagation aux occurrences d'une série ───────────────────────────────────────────────
#
# ⚠️ SANS ELLE, UN ÉVÉNEMENT HEBDOMADAIRE DEMANDE DE RETAPER SA DESCRIPTION DOUZE FOIS. Chaque
# occurrence est une LIGNE distincte avec sa propre description : remplir celle du 12 ne change rien
# pour celle du 19. Et c'est la page client qui le révèle — une vignette sans flèche, parce qu'elle
# n'a rien à ouvrir. C'est arrivé au Run Club.


def test_la_propagation_ne_touche_que_les_champs_publics():
    """
    ⚠️ LA DATE, L'HEURE ET LE STATUT RESTENT PROPRES À CHAQUE OCCURRENCE. Une séance déplacée ou
    annulée ne doit pas emporter ses sœurs — et le titre non plus : renommer une seule occurrence
    est un geste légitime.
    """
    s = _page_events()
    i = s.index("if (id && $('m-serie').checked)")
    bloc = s[i:s.index("showToast(", i)]
    for public in ("description:", "image_url:", "link_url:", "link_label:", "show_on_card:"):
        assert public in bloc, f"{public} ne se propage plus"
    for prive in ("start_time", "end_time", "status", "color"):
        assert prive not in bloc, f"{prive} se propage : une occurrence déplacée emporterait ses sœurs"


def test_la_propagation_renvoie_la_date_de_chaque_soeur():
    """
    ⚠️ LA ROUTE EXIGE UN TITRE ET UNE DATE. Envoyer les MIENS réécrirait la date de chaque sœur avec
    celle de l'occurrence ouverte — douze séances empilées le même jour, et la série détruite sans
    un message d'erreur.
    """
    s = _page_events()
    i = s.index("if (id && $('m-serie').checked)")
    bloc = s[i:s.index("showToast(", i)]
    assert "title: s2.title" in bloc and "date: s2.date" in bloc


def test_la_case_de_serie_n_apparait_que_sur_une_serie():
    """Une case « toute la série » sur un événement isolé ne veut rien dire — et une case qui ne
    veut rien dire se coche par réflexe."""
    s = _page_events()
    assert "$('m-serie-wrap').style.display = seriesCount>1 ? 'flex' : 'none';" in s
    # ⚠️ ET ELLE REPART DÉCOCHÉE, DANS LA BRANCHE OÙ ELLE EST VISIBLE. Le premier jet de ce contrôle
    # cherchait la remise à zéro n'importe où dans le fichier — or elle existe AUSSI dans la branche
    # « pas de série », là où la case est masquée et où elle ne sert donc à rien. La retirer de la
    # branche qui compte laissait la case cochée d'un événement au suivant : on propage à douze
    # occurrences sans l'avoir demandé.
    i = s.index("$('m-serie-wrap').style.display = seriesCount>1")
    branche = s[i:s.index("} else {", i)]
    assert "$('m-serie').checked = false;" in branche, (
        "la case reste cochée d'un événement à l'autre"
    )
