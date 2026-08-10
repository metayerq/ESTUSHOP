"""
Rapprochement cache ↔ Vendus : retrouver les journées figées à mi-parcours.

`/api/cashflow` écrivait le jour courant dans `daily_summary`. Comme on ne reconstruit que les
jours MANQUANTS, une journée figée à 9h30 le restait pour toujours et contaminait ensuite tout
ce qui lit le cache. La garde est posée ; ces tests couvrent l'outil qui retrouve les dégâts
déjà commis.

⚠️ La sémantique doit coller EXACTEMENT à `_summarize_docs_items` : les avoirs se soustraient
du CA et ne comptent pas comme tickets. Un rapprochement qui compterait autrement signalerait
des écarts qui n'en sont pas — et ferait reconstruire des jours sains.
"""
import sys
from datetime import date
sys.path.insert(0, ".")

import pytest

import app


def _cache(rows):
    return [{"day": d, "ca_ttc": ca, "nb": nb} for d, (ca, nb) in rows.items()]


def _vendus(rows):
    return {d: {"ca_ttc": ca, "nb": nb} for d, (ca, nb) in rows.items()}


D1, D3 = date(2026, 7, 1), date(2026, 7, 3)


def test_un_cache_conforme_ne_signale_rien():
    r = app._audit_summaries(
        _cache({"2026-07-01": (300.0, 30), "2026-07-02": (250.0, 25), "2026-07-03": (0.0, 0)}),
        _vendus({"2026-07-01": (300.0, 30), "2026-07-02": (250.0, 25)}), D1, D3)
    assert r == [], r


def test_le_jour_fige_a_mi_parcours_est_reconnu_comme_partiel():
    """La signature du bug : le cache a moins que Vendus, sur le CA comme sur les tickets."""
    r = app._audit_summaries(
        _cache({"2026-07-02": (45.0, 3)}),
        _vendus({"2026-07-02": (412.30, 38)}), date(2026, 7, 2), date(2026, 7, 2))
    assert len(r) == 1
    assert r[0]["verdict"] == "partiel"
    assert r[0]["ecart_ca"] == 367.30
    assert (r[0]["cache_nb"], r[0]["vendus_nb"]) == (3, 38)


def test_une_journee_absente_du_cache_est_signalee():
    r = app._audit_summaries([], _vendus({"2026-07-02": (412.30, 38)}),
                             date(2026, 7, 2), date(2026, 7, 2))
    assert r[0]["verdict"] == "manquant"
    assert r[0]["cache_ca_ttc"] is None, "on n'invente pas un 0 pour une ligne qui n'existe pas"


def test_un_jour_sans_vente_des_deux_cotes_n_est_pas_un_ecart():
    """Mardi fermé : ni ligne de cache, ni document Vendus. Ce n'est pas un problème."""
    assert app._audit_summaries([], {}, date(2026, 7, 7), date(2026, 7, 8)) == []


def test_un_cache_superieur_a_vendus_est_distingue():
    """
    Cache > Vendus n'a pas la même cause qu'un jour partiel — typiquement un avoir émis après
    la mise en cache. Les confondre enverrait reconstruire en croyant réparer autre chose.
    """
    r = app._audit_summaries(_cache({"2026-07-02": (412.30, 38)}),
                             _vendus({"2026-07-02": (390.00, 37)}),
                             date(2026, 7, 2), date(2026, 7, 2))
    assert r[0]["verdict"] == "excedentaire"
    assert r[0]["ecart_ca"] == -22.30


def test_une_ligne_de_cache_sans_contrepartie_vendus_est_un_fantome():
    r = app._audit_summaries(_cache({"2026-07-02": (412.30, 38)}), {},
                             date(2026, 7, 2), date(2026, 7, 2))
    assert r[0]["verdict"] == "fantome"


def test_un_ecart_au_centime_ne_declenche_rien():
    """Les arrondis de Vendus ne doivent pas produire une liste de reconstruction inutile."""
    r = app._audit_summaries(_cache({"2026-07-02": (412.30, 38)}),
                             _vendus({"2026-07-02": (412.305, 38)}),
                             date(2026, 7, 2), date(2026, 7, 2))
    assert r == []


def test_un_ecart_de_tickets_seul_est_relevé():
    """
    Même CA, un ticket de moins : deux ventes fusionnées, ou un avoir mal compté. Le CA seul
    ne suffit pas à démasquer le cas, d'où la comparaison sur les deux grandeurs.
    """
    r = app._audit_summaries(_cache({"2026-07-02": (412.30, 37)}),
                             _vendus({"2026-07-02": (412.30, 38)}),
                             date(2026, 7, 2), date(2026, 7, 2))
    assert len(r) == 1 and r[0]["ecart_ca"] == 0.0


# ── Une table absente doit crier, pas se taire ───────────────────────────────

class _Reponse:
    def __init__(self, code, payload=None):
        self.status_code = code
        self.ok = 200 <= code < 300
        self._p = payload if payload is not None else []
    def json(self):
        return self._p


def test_une_table_absente_leve_au_lieu_de_repondre_vide(monkeypatch):
    """
    LE DÉFAUT QUI A COÛTÉ DEUX MOIS. `daily_summary` n'existait dans aucun schéma du projet.
    `_supa_get` renvoyait [], indiscernable de « aucune ligne » : l'app concluait que le cache
    était vide, rappelait Vendus sur tout l'historique — un appel de détail par document — puis
    échouait à écrire, également en silence. Les chiffres restaient justes, le coût était
    multiplié, et rien ne l'a jamais signalé.

    Une table absente est un déploiement incomplet, pas un état des données.
    """
    monkeypatch.setattr(app._req, "get", lambda *a, **k: _Reponse(404, {"message": "not found"}))
    with pytest.raises(app.SupabaseSchemaError) as e:
        app._supa_get("daily_summary")
    assert "daily_summary" in str(e.value)


def test_une_panne_passagere_garde_le_repli_sur_vide(monkeypatch):
    """
    Le durcissement est CIBLÉ. Un 5xx ou une coupure réseau sont transitoires : rendre un écran
    vide vaut mieux que rendre une page en erreur. Seul le 404 — le schéma — remonte.
    """
    monkeypatch.setattr(app._req, "get", lambda *a, **k: _Reponse(503))
    assert app._supa_get("daily_summary") == []


def test_une_lecture_normale_est_inchangee(monkeypatch):
    monkeypatch.setattr(app._req, "get",
                        lambda *a, **k: _Reponse(200, [{"day": "2026-07-10", "nb": 20}]))
    assert app._supa_get("daily_summary") == [{"day": "2026-07-10", "nb": 20}]
