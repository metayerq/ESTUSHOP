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
