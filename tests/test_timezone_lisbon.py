"""
Le fuseau du café — pourquoi le serveur ne doit jamais dire « aujourd'hui » tout seul.

L'app tourne sur Vercel, horloge système en UTC. Lisbonne est à UTC+1 l'été. Entre minuit et
1 h du matin heure locale, `date.today()` renvoie donc LA VEILLE. Trois dégâts mesurés :

 1. Un lundi à 00h30 locale, le serveur se croit dimanche : `_week_start` retombe sur le lundi
    précédent, et le preset "lastweek" désigne l'AVANT-dernière semaine. Une semaine entière
    d'écart, signalée par l'utilisateur.
 2. `now_hms` coupe le jour de comparaison « à la même heure ». Il était en UTC alors que les
    `local_time` de Vendus sont en heure de Lisbonne : le jour de référence recevait une heure
    de ventes gratuite, TOUTE la journée — chaque « vs samedi dernier même heure » était flatté.
 3. `updated_at` affichait une heure fausse d'une heure en permanence.

CE QUE CES TESTS COUVRENT, ET CE QU'ILS NE COUVRENT PAS.
Les fonctions pures (`to_lisbon`, `_lisbon_offset_hours`, `PRESET_RANGES`) sont exercées pour
de vrai, avec une horloge GELÉE — jamais l'horloge réelle, sinon le test ne dirait quelque
chose qu'entre minuit et 1 h. Que les sites d'appel utilisent bien ces fonctions est vérifié en
LISANT le source (app.py/vendus.py), comme test_month_series.py : exercer /api/data demanderait
Vendus et Supabase. Le fuseau réel du runtime Vercel, lui, n'est vérifiable par aucun test
d'ici — c'est précisément pourquoi le code ne le suppose plus.
"""
import inspect
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, ".")

import app
import config
import vendus
from config import today_lisbon, now_lisbon, to_lisbon, _lisbon_offset_hours


def _clock(monkeypatch, iso_utc):
    """Gèle l'horloge UTC du process à un instant donné (l'horloge de Vercel)."""
    fixed = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)
    monkeypatch.setattr(config, "utc_now", lambda: fixed)
    return fixed


@pytest.fixture(params=["zoneinfo", "repli"])
def moteur_tz(request, monkeypatch):
    """Fait tourner le même test avec zoneinfo, PUIS avec le repli arithmétique.

    Le repli ne se déclenche qu'au cas où le runtime Vercel n'aurait pas de base de fuseaux —
    autant dire un chemin qu'aucune exécution de production ne prendra probablement jamais.
    C'est exactement pour ça qu'il doit être testé aussi durement que l'autre : un filet qu'on
    ne tend jamais est un filet qu'on ne sait pas troué.
    """
    if request.param == "repli":
        monkeypatch.setattr(config, "_lisbon_zoneinfo", lambda: None)
    return request.param


# ── 1. Le décalage lui-même ──────────────────────────────────────────────────

def test_today_lisbon_suit_l_horloge_locale_quand_le_serveur_est_en_utc(monkeypatch, moteur_tz):
    """
    Le cœur du défaut : 23h30 UTC un 5 août, il est déjà le 6 à Lisbonne.
    `date.today()` sur un serveur UTC dirait le 5.
    """
    _clock(monkeypatch, "2026-08-05T23:30:00")
    assert today_lisbon() == date(2026, 8, 6)
    assert now_lisbon().strftime("%H:%M") == "00:30"


def test_en_hiver_lisbonne_est_sur_utc_et_rien_ne_bouge(monkeypatch, moteur_tz):
    """WET = UTC+0 : la conversion doit être neutre, pas « toujours +1 »."""
    _clock(monkeypatch, "2026-01-15T23:30:00")
    assert today_lisbon() == date(2026, 1, 15)
    assert now_lisbon().strftime("%H:%M") == "23:30"


def test_l_heure_murale_affichee_est_celle_de_lisbonne(monkeypatch):
    """`updated_at` est lu par quelqu'un debout dans le café, pas par un serveur."""
    _clock(monkeypatch, "2026-08-05T14:07:00")
    assert now_lisbon().strftime("%H:%M") == "15:07"


# ── 2. Le preset "lastweek" autour de minuit ─────────────────────────────────

@pytest.mark.parametrize("instant_utc, attendu", [
    # Lundi 10 août 2026, 00h30 à Lisbonne = dimanche 9 août 23h30 UTC.
    # Semaine dernière = lundi 3 → dimanche 9 août.
    ("2026-08-09T23:30:00", (date(2026, 8, 3), date(2026, 8, 9))),
    # Le même lundi, en pleine journée : même réponse, évidemment.
    ("2026-08-10T09:00:00", (date(2026, 8, 3), date(2026, 8, 9))),
])
def test_lastweek_ne_decale_pas_d_une_semaine_a_minuit(monkeypatch, moteur_tz, instant_utc, attendu):
    _clock(monkeypatch, instant_utc)
    assert app.PRESET_RANGES["lastweek"](today_lisbon()) == attendu


def test_l_ancien_comportement_utc_donnait_bien_l_avant_derniere_semaine():
    """
    Le témoin du bug, figé pour qu'on n'oublie pas ce qui était réparé.

    À 23h30 UTC le dimanche 9 août, un serveur UTC calcule "lastweek" sur le 9 août : sa
    semaine courante commence le 3, donc « la semaine dernière » remonte au 27 juillet —
    l'avant-dernière semaine vue du café, où il est déjà lundi.
    """
    utc_view = app.PRESET_RANGES["lastweek"](date(2026, 8, 9))
    lisbon_view = app.PRESET_RANGES["lastweek"](date(2026, 8, 10))
    assert utc_view == (date(2026, 7, 27), date(2026, 8, 2))
    assert (lisbon_view[0] - utc_view[0]).days == 7, "l'écart constaté était bien d'une semaine"


def test_les_autres_presets_glissent_aussi_du_bon_jour(monkeypatch):
    """"today" et "yesterday" doivent suivre le jour du café, pas celui du serveur."""
    _clock(monkeypatch, "2026-08-09T23:30:00")   # lundi 10 à Lisbonne
    d = today_lisbon()
    assert app.PRESET_RANGES["today"](d) == (date(2026, 8, 10), date(2026, 8, 10))
    assert app.PRESET_RANGES["yesterday"](d) == (date(2026, 8, 9), date(2026, 8, 9))


# ── 3. Les bascules d'heure ──────────────────────────────────────────────────

@pytest.mark.parametrize("instant_utc, hhmm_local, jour_local, offset", [
    # Dernier dimanche d'octobre 2026 = le 25. Bascule à 01:00 UTC.
    ("2026-10-24T23:30:00", "00:30", date(2026, 10, 25), 1),   # encore WEST
    ("2026-10-25T00:59:00", "01:59", date(2026, 10, 25), 1),   # dernière minute d'été
    ("2026-10-25T01:00:00", "01:00", date(2026, 10, 25), 0),   # 02:00 → 01:00, WET
    ("2026-10-25T23:30:00", "23:30", date(2026, 10, 25), 0),   # plus de décalage
    # Dernier dimanche de mars 2026 = le 29. Bascule à 01:00 UTC.
    ("2026-03-29T00:59:00", "00:59", date(2026, 3, 29), 0),
    ("2026-03-29T01:00:00", "02:00", date(2026, 3, 29), 1),    # 01:00 → 02:00
])
def test_les_bascules_ete_hiver_ne_cassent_rien(monkeypatch, moteur_tz, instant_utc,
                                                hhmm_local, jour_local, offset):
    _clock(monkeypatch, instant_utc)
    n = now_lisbon()
    assert n.strftime("%H:%M") == hhmm_local
    assert n.date() == jour_local
    assert n.utcoffset() == timedelta(hours=offset)


def test_l_heure_repetee_de_la_bascule_d_octobre_ne_change_pas_le_jour(monkeypatch, moteur_tz):
    """
    01:30 locale existe DEUX fois le 25 octobre. Les deux instants tombent le même jour :
    aucun preset ne doit sauter au passage.
    """
    for utc in ("2026-10-25T00:30:00", "2026-10-25T01:30:00"):
        _clock(monkeypatch, utc)
        assert now_lisbon().strftime("%H:%M") == "01:30"
        assert today_lisbon() == date(2026, 10, 25)


def test_le_repli_sans_base_tz_dit_exactement_la_meme_chose_que_zoneinfo():
    """
    Si le runtime Vercel n'a pas de base de fuseaux, ZoneInfo lèverait au premier appel —
    donc un 500 sur TOUTES les routes. Le repli arithmétique (règle UE) doit donc être exact,
    pas approximatif : on le confronte à zoneinfo heure par heure sur trois ans, bascules
    comprises. S'il divergeait, le repli serait un second bug déguisé en filet.
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Lisbon")
    t = datetime(2025, 1, 1, tzinfo=timezone.utc)
    fin = datetime(2028, 1, 1, tzinfo=timezone.utc)
    while t < fin:
        attendu = int(t.astimezone(tz).utcoffset().total_seconds() // 3600)
        assert _lisbon_offset_hours(t) == attendu, f"repli faux à {t.isoformat()}"
        t += timedelta(hours=1)


def test_le_repli_est_reellement_emprunte_quand_zoneinfo_manque(monkeypatch):
    """Le filet doit être branché, pas seulement écrit : on coupe zoneinfo et on vérifie."""
    monkeypatch.setattr(config, "_lisbon_zoneinfo", lambda: None)
    n = to_lisbon(datetime(2026, 8, 5, 23, 30, tzinfo=timezone.utc))
    assert n.date() == date(2026, 8, 6) and n.strftime("%H:%M") == "00:30"


# ── 4. Les sites d'appel : lus dans le source, faute de pouvoir les exercer ──

_NU = re.compile(r"(?<![\w.])(date\.today\(\)|datetime\.now\(\)|datetime\.utcnow\(\))")

# Seul rescapé toléré : la route api_cashflow est modifiée en parallèle par quelqu'un d'autre,
# on n'y touche pas pour ne pas créer de conflit. Elle agrège par MOIS, donc l'heure de bascule
# ne peut décaler qu'un jour de bord, jamais une semaine. À reprendre après la fusion.
_EXCEPTIONS_CONNUES = {("app.py", "api_cashflow")}


def _appels_nus(module):
    """Les appels d'horloge sans fuseau restants, par fonction porteuse."""
    fichier = module.__file__.split("/")[-1]
    src = inspect.getsource(module).splitlines()
    porteuse, trouves = "<module>", []
    for ligne in src:
        m = re.match(r"\s*def\s+(\w+)", ligne)
        if m and not ligne.startswith(" " * 4):
            porteuse = m.group(1)
        if _NU.search(ligne) and "timezone.utc" not in ligne:
            trouves.append((fichier, porteuse))
    return set(trouves)


@pytest.mark.parametrize("module", [app, vendus], ids=["app.py", "vendus.py"])
def test_plus_aucune_horloge_sans_fuseau_ne_traine(module):
    """
    La garde qui empêche la régression : un `date.today()` réintroduit demain dans une route
    rouvre exactement le défaut du preset "lastweek", sans qu'aucun test de valeur ne bronche.
    """
    restants = _appels_nus(module) - _EXCEPTIONS_CONNUES
    assert not restants, (
        f"horloge sans fuseau dans {sorted(restants)} — utiliser today_lisbon()/now_lisbon() "
        "pour une date métier, ou datetime.now(timezone.utc) pour un horodatage technique"
    )


def test_api_data_date_son_aujourd_hui_sur_lisbonne():
    """`today_real` alimente TOUS les presets et toutes les fenêtres de comparaison."""
    src = inspect.getsource(app.api_data)
    assert "today_real = today_lisbon()" in src


def test_les_coupes_a_la_meme_heure_se_comparent_a_l_heure_de_lisbonne():
    """
    Les deux filtres `now_hms` comparent une heure murale aux `local_time` de Vendus, qui sont
    en heure de Lisbonne. En UTC, ils laissaient passer une heure de ventes en trop côté
    référence : la comparaison était flattée toute la journée, pas seulement la nuit.
    """
    src = inspect.getsource(app.api_data)
    coupes = re.findall(r"now_hms\s*=\s*(\S+)", src)
    assert len(coupes) == 2, f"attendu 2 coupes horaires, trouvé {len(coupes)}"
    assert all(c.startswith("now_lisbon()") for c in coupes), coupes


def test_l_horodatage_technique_reste_en_utc_explicite():
    """
    Le critère de tri, gardé par un test : ce qui mesure une ancienneté ou ordonne des lignes
    en base reste un instant UTC explicite. Le convertir en heure locale le rendrait ambigu
    deux fois par an — 01:30 existe deux fois le dernier dimanche d'octobre.
    """
    assert "datetime.now(timezone.utc)" in inspect.getsource(app._utc_iso)
    assert app._utc_iso().endswith("Z")
    # et il reste relisable par le calculateur d'âge de cache
    assert app._iso_age_seconds(app._utc_iso()) < 5
