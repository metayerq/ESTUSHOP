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


# ── Les traductions ─────────────────────────────────────────────────────────────────────────
#
# ⚠️ PAS DE COLONNE `_PT` : `title`, `description` et `link_label` SONT le portugais. En ajouter une
# aurait obligé à recopier des centaines de lignes, et à trancher le jour où les deux diffèrent.


def test_les_traductions_ne_sont_pas_inventees_a_la_mise_a_jour():
    """⚠️ MÊME GARDE QUE LES AUTRES CHAMPS PUBLICS. Un écran qui n'a pas la ligne anglaise ne doit
    pas supprimer la traduction anglaise en enregistrant une correction d'horaire — l'écriture est un
    upsert `merge-duplicates`, donc tout champ présent écrase."""
    row = app._build_event_row({"id": "e1", "title": "Fado", "date": "2026-10-03"}, "planned")
    for champ in ("title_en", "title_fr", "description_en", "description_fr",
                  "link_label_en", "link_label_fr"):
        assert champ not in row, f"{champ} a été inventé sur une mise à jour"


def test_une_traduction_vide_devient_nulle():
    """Une chaîne vide se lirait comme « traduit en rien » : le repli ne se déclencherait pas et le
    client verrait un titre vide là où le portugais existe."""
    row = app._build_event_row(
        {"id": "e1", "title": "x", "date": "2026-10-03", "title_en": "  ", "description_fr": ""},
        "planned",
    )
    assert row["title_en"] is None and row["description_fr"] is None


def test_l_apercu_replie_comme_la_page_client():
    """
    ⚠️ DEUX CASCADES DE REPLI ÉCRITES SÉPARÉMENT FINIRAIENT PAR DIVERGER, et l'aperçu affirmerait
    quelque chose que le client ne verra pas — le seul défaut qu'un aperçu ne peut pas se permettre.
    L'ordre est fixe : demandée, portugais, anglais, français ; une chaîne d'espaces ne compte pas.
    """
    s = _page_events()
    i = s.index("function selonLangue(pt, en, fr, l)")
    corps = s[i:s.index("\n}", i)]
    assert "propre(pt) || propre(en) || propre(fr)" in corps, "l'ordre de repli a changé"
    assert ".trim()" in corps, "une chaîne d'espaces compterait comme un texte"


def test_l_apercu_annonce_les_traductions_manquantes():
    """
    ⚠️ SANS ÇA, ON CROIT AVOIR TRADUIT. L'aperçu montre un texte anglais parfaitement lisible… qui
    est le portugais. C'est précisément l'illusion que le sélecteur de langue existe pour dissiper.
    """
    s = _page_events()
    # ⚠️ ON VÉRIFIE LA CONDITION, PAS LA PHRASE. `if(false) avis.push('Pas de traduction …')` garde la
    # phrase dans le fichier et ne l'affiche jamais : un contrôle qui cherche le texte passe au vert
    # sur l'avertissement définitivement muet.
    assert "if(manque.length) avis.push('Pas de traduction '" in s, (
        "l'avertissement de repli ne dépend plus de ce qui manque"
    )
    assert "le portugais sera affiché" in s
    # Et `manque` se remplit bien à partir des trois champs traduits.
    i = s.index("const manque = []")
    bloc = s[i:s.index("if(manque.length)", i)]
    for champ in ("m-title-en", "m-desc-en", "m-link-label-en"):
        assert champ in bloc, f"{champ} n'est plus surveillé par l'avertissement"


def test_la_propagation_emporte_les_traductions():
    """Les propager séparément — ou pas du tout — laisserait douze occurrences avec un portugais à
    jour et un anglais périmé : le client anglophone lirait l'ancienne version sans un signal."""
    s = _page_events()
    i = s.index("if (id && $('m-serie').checked)")
    bloc = s[i:s.index("showToast(", i)]
    for champ in ("title_en", "description_en", "link_label_fr"):
        assert f"{champ}: base.{champ}" in bloc, f"{champ} ne se propage pas à la série"


def test_l_apercu_dit_aujourd_hui_le_jour_meme():
    """
    ⚠️ MÊME RÈGLE QUE LA PAGE CLIENT, et le jour courant se lit À LISBONNE. Le navigateur du bureau
    peut être dans un autre fuseau ; l'aperçu doit dire ce que verra un CLIENT, pas ce que voit la
    machine qui saisit.
    """
    s = _page_events()
    i = s.index("function quandFr")
    corps = s[i:s.index("\n}", i)]
    assert "Aujourd'hui" in corps, "l'aperçu n'annonce plus le jour même"
    assert "Europe/Lisbon" in corps, "le jour courant est lu sur l'horloge du bureau"
    assert "JOURS_FR[d.getUTCDay()]" in corps, "le jour de semaine a disparu des autres jours"


def test_l_apercu_refuse_une_date_hors_plage():
    """
    ⚠️ `new Date("2026-02-30")` NE LÈVE PAS, ELLE SE DÉCALE au 2 mars : on afficherait « lundi
    30 février », un jour de semaine juste pour une date qui n'existe pas. Un jour de semaine ne se
    vérifie pas, on le croit — quelqu'un serait venu le lundi. La comparaison aller-retour est le
    seul contrôle qui l'attrape.
    """
    s = _page_events()
    i = s.index("function quandFr")
    corps = s[i:s.index("\n}", i)]
    assert "d.toISOString().slice(0,10) !== j" in corps, (
        "une date hors plage produirait un jour de semaine faux mais plausible"
    )


def test_chaque_identifiant_lu_par_le_script_existe_dans_la_page():
    """
    ⚠️ CE CONTRÔLE EXISTE À CAUSE D'UNE PANNE QUI A BLOQUÉ LE BACKOFFICE. Les lignes de traduction du
    TITRE n'avaient jamais été ajoutées — la substitution qui devait les insérer n'a pas trouvé son
    motif et n'a rien fait, en silence. Le JavaScript, lui, lisait déjà `m-title-en` :
    `$('m-title-en').value` lève une TypeError, `openModal` meurt, et la fenêtre d'édition ne s'ouvre
    JAMAIS. Cliquer un événement ne faisait plus rien.

    ⚠️ ET MES TESTS L'AVAIENT LAISSÉ PASSER pour une raison qu'il faut retenir : ils vérifiaient que
    `'m-title-en'` figurait dans le FICHIER. Il y figurait — dans le script qui le lit. Vérifier
    qu'un nom est écrit quelque part ne dit rien sur l'existence de ce qu'il désigne. C'est la même
    erreur que d'avoir lu une règle CSS en production et conclu qu'elle s'appliquait.

    ⚠️ IL EST GÉNÉRAL EXPRÈS. Cette page lit une soixantaine d'identifiants ; le prochain champ ajouté
    au script sans son HTML tombera ici, et non chez le propriétaire un soir de service.
    """
    import re

    s = _page_events()
    html = s[: s.index("<script")]
    ids = set(re.findall(r'id="([^"]+)"', html))
    js = s[s.index("<script>") :]
    # ⚠️ ON NE DÉPOUILLE PAS LES COMMENTAIRES ICI : un identifiant cité dans un commentaire mais
    # jamais lu ne casse rien, alors qu'un identifiant lu et absent casse tout. Le faux positif est
    # sans danger, le faux négatif bloque la page.
    lus = set(re.findall(r"\$\('([^']+)'\)", js))
    absents = sorted(lus - ids)
    assert not absents, (
        f"lus par le script mais absents du HTML — `openModal` lèvera et la fenêtre "
        f"d'édition ne s'ouvrira plus : {absents}"
    )
