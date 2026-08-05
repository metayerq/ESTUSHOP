#!/usr/bin/env python3
"""
Café Estudantina — Dashboard Vendus
Usage:
    pip install flask requests
    VENDUS_API_KEY=votre_cle python app.py
    → ouvre http://localhost:8080
"""

import os
import json
import hmac
import time
import hashlib
from datetime import date, timedelta, datetime, timezone
from concurrent.futures import ThreadPoolExecutor

# « Aujourd'hui » et « maintenant » au sens du café (Europe/Lisbon), jamais
# l'horloge UTC du serveur Vercel. Voir config.py pour le pourquoi.
from config import today_lisbon, now_lisbon

from flask import Flask, jsonify, render_template, request, redirect, make_response, g
from vendus import (
    get_documents, get_documents_with_items, get_catalog, get_categories,
    calc_stats, hourly_breakdown, payment_breakdown, top_products, recent_docs,
    rush_detector, unsold_today, product_stats_from_docs,
    tva_breakdown, service_tempo, upsell_rate, category_mix, ticket_median,
    daily_economics, cumulative_curve, ticket_distribution,
    daily_breakdown, create_category,
)

# ── Cache des docs du jour : mémoire 45s + Supabase (rempli par le cron) ──────
# Les items du jour coûtent ~1 appel Vendus PAR ticket. Sur Vercel serverless,
# chaque cold start repart d'un cache mémoire vide → chargement lent. Un cron
# externe (toutes les 5 min) rafraîchit une ligne Supabase `live_docs_cache`,
# que les requêtes lisent instantanément au lieu de refaire N appels Vendus.
_TODAY_DOCS_CACHE = {"ts": 0.0, "day": None, "docs": None}
_TODAY_TTL      = 45      # mémoire (même instance lambda)
_SUPA_CACHE_MAX = 600     # fraîcheur acceptée de la ligne Supabase (10 min)

def _utc_iso():
    """Horodatage TECHNIQUE : l'instant courant en UTC explicite, suffixe Z.

    Réservé à ce qui est écrit en base pour mesurer une ancienneté ou ordonner
    (fraîcheur d'un cache, `updated_at`, `done_at`). Ces valeurs ne sont pas des
    dates métier : les convertir en heure locale les rendrait ambiguës deux fois
    par an, à la bascule d'heure. Tout ce qui répond à « quel jour est-on ? » ou
    « quelle heure affiche-t-on ? » passe au contraire par today_lisbon/now_lisbon.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _iso_age_seconds(iso):
    """Âge en secondes d'un timestamp ISO Supabase ; +inf si illisible."""
    if not iso:
        return float("inf")
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        # Timestamp sans fuseau : il vient forcément d'une écriture UTC (c'est
        # l'invariant de _utc_iso), donc on le compare à une horloge UTC — pas
        # à l'horloge locale du process, qui n'est UTC que par accident.
        now = (datetime.now(timezone.utc) if dt.tzinfo
               else datetime.now(timezone.utc).replace(tzinfo=None))
        return (now - dt).total_seconds()
    except Exception:
        return float("inf")

def _refresh_today_cache():
    """Fetch live des docs du jour + écriture mémoire ET Supabase. Appelé par
    le cron et en dernier recours par une requête si le cache est périmé."""
    today_iso = today_lisbon().isoformat()
    docs = get_documents_with_items(today_iso, today_iso)
    _TODAY_DOCS_CACHE.update(ts=time.time(), day=today_iso, docs=docs)
    try:
        _supa_upsert("live_docs_cache", {
            "day": today_iso, "docs": docs, "updated_at": _utc_iso(),
        })
    except Exception:
        pass   # l'écriture cache ne doit jamais casser la requête
    return docs

def _get_today_docs_cached(force=False):
    today_iso = today_lisbon().isoformat()
    c = _TODAY_DOCS_CACHE
    # 1) mémoire fraîche (même instance)
    if (not force and c["docs"] is not None and c["day"] == today_iso
            and time.time() - c["ts"] < _TODAY_TTL):
        return c["docs"]
    # 2) cache Supabase rempli par le cron — évite les N appels Vendus
    if not force:
        try:
            rows = _supa_get("live_docs_cache", {"day": f"eq.{today_iso}", "limit": "1"})
            if rows and _iso_age_seconds(rows[0].get("updated_at")) < _SUPA_CACHE_MAX:
                docs = rows[0].get("docs") or []
                c.update(ts=time.time(), day=today_iso, docs=docs)
                return docs
        except Exception:
            pass
    # 3) fallback : fetch live (et réécrit les deux caches)
    return _refresh_today_cache()

SEUIL_TRANSACTIONS = 40
OPENING_DAY = "2026-05-27"     # ouverture du café — borne basse des historiques


# ── Cache heatmap 28 jours (Supabase + mémoire) ──────────────────────────────
# C'était l'appel Vendus le plus lourd du dashboard (~6 s) pour un widget quasi
# statique. On persiste le RÉSULTAT CALCULÉ (quelques Ko) dans Supabase — pas
# les ~650 documents bruts — pour que les cold starts serverless (mémoire vide)
# le lisent en ~50 ms. Le cron le réchauffe pour qu'il ne soit jamais froid.
HEATMAP_TTL = 3600

def _heatmap_build(today_real):
    docs = get_documents((today_real - timedelta(27)).isoformat(),
                         today_real.isoformat())
    return {"heatmap": _heatmap_from_docs(docs),
            "rush":    _rush_concentration(docs)}

def _heatmap_payload_cached(today_real, force=False):
    from vendus import _ttl_get
    key = f"heatmap28:{today_real.isoformat()}"

    def _build():
        if not force:
            try:
                rows = _supa_get("kv_cache", {"key": f"eq.{key}", "limit": "1"})
                if rows and _iso_age_seconds(rows[0].get("updated_at")) < HEATMAP_TTL:
                    return rows[0].get("value")
            except Exception:
                pass
        try:
            payload = _heatmap_build(today_real)
        except Exception:
            return None
        try:
            _supa_upsert("kv_cache", {
                "key": key, "value": payload,
                "updated_at": _utc_iso(),
            })
        except Exception:
            pass   # l'écriture cache ne doit jamais casser la requête
        return payload

    if force:
        _TTL_CACHE_KEY = ("heatmap28p", today_real.isoformat())
        from vendus import _TTL_CACHE
        _TTL_CACHE.pop(_TTL_CACHE_KEY, None)
    return _ttl_get(("heatmap28p", today_real.isoformat()), HEATMAP_TTL, _build,
                    cacheable=lambda v: v is not None)

def _warm_heatmap_cache():
    """Appelé par le cron : recalcule et persiste la heatmap du jour."""
    return _heatmap_payload_cached(today_lisbon(), force=True) is not None


# ── Insights helpers (visuels dashboard) ─────────────────────────────────────

def _heatmap_from_docs(docs):
    """CA par (jour de semaine × heure) — docs document-level, 28 derniers jours."""
    hours = list(range(8, 17))   # ouverture 8h30–16h
    grid  = {}   # (weekday, hour) -> ca
    for doc in docs:
        lt = doc.get("local_time") or ""
        try:
            day = date.fromisoformat(lt[:10])
            h   = int(lt[11:13])
        except (ValueError, IndexError):
            continue
        if h not in hours:
            continue
        key = (day.weekday(), h)
        grid[key] = grid.get(key, 0.0) + float(doc.get("amount_gross", 0))
    cells = [{"d": d, "h": h, "v": round(grid[(d, h)], 2)}
             for d in range(7) for h in hours if grid.get((d, h))]
    return {"hours": hours, "cells": cells,
            "max": max((c["v"] for c in cells), default=0)}


def _day_margin(row, fallback_rate):
    """Marge brute HT d'une journée depuis son summary (taux réel du jour)."""
    ca_ht   = float(row.get("ca_ht") or 0)
    covered = float(row.get("covered_ht") or 0)
    cogs    = float(row.get("cogs_ht") or 0)
    if covered > 0:
        return ca_ht * (covered - cogs) / covered
    return ca_ht * fallback_rate


def _month_fallback_rate(rows_month):
    """
    Taux de marge à appliquer aux jours du mois dont les lignes ne sont pas chiffrées.

    ⚠️ IL SE MESURE SUR LE MOIS, JAMAIS SUR LA PÉRIODE AFFICHÉE. L'appelant passait
    auparavant `eco["marge_brute_ht_pct"]`, l'économie du preset sélectionné — alors que le
    bloc s'annonce « indépendant du preset ». Changer le filtre au-dessus déplaçait donc le
    cumul et la projection du mois, des chiffres qui ne parlent que du mois.

    Le même défaut existait dans Mesa, où il a été mesuré : ~510 € d'écart (8 %) sur le point
    mort mensuel selon le filtre choisi. Ici, 150 € contre 200 € de cumul sur le même mois.

    Sans couverture (aucune ligne chiffrée), on retombe sur l'hypothèse du BP — assumée comme
    telle, et elle aussi indépendante du filtre.
    """
    from config import MARGE_BP_GLOBALE
    covered = sum(float(r.get("covered_ht") or 0) for r in rows_month)
    cogs    = sum(float(r.get("cogs_ht")    or 0) for r in rows_month)
    return ((covered - cogs) / covered) if covered > 0 else MARGE_BP_GLOBALE


def _month_series(rows_month, cout_jour, fallback_rate, today_real):
    """Série EBITDA/jour du mois + cumul + projection fin de mois."""
    import calendar as _cal
    from config import count_open_days_raw
    month_start = today_real.replace(day=1)
    month_end   = date(today_real.year, today_real.month,
                       _cal.monthrange(today_real.year, today_real.month)[1])
    by_day = {r["day"]: r for r in rows_month}
    days, cum, cross = [], 0.0, None
    cur = month_start
    while cur <= today_real:
        iso  = cur.isoformat()
        row  = by_day.get(iso)
        is_open = count_open_days_raw(cur, cur) == 1 or bool(row and (row.get("nb") or 0) > 0)
        if is_open:
            ebitda = round(_day_margin(row or {}, fallback_rate) - cout_jour, 2)
            was_negative = cum < 0
            cum += ebitda
            if cross is None and was_negative and cum >= 0:
                cross = iso   # jour où le mois passe dans le vert
        else:
            ebitda = None
        days.append({"date": iso, "ebitda": ebitda, "cum": round(cum, 2), "open": is_open})
        cur += timedelta(1)
    # Projection : moyenne des 7 derniers jours ouvrés × jours ouvrés restants
    opened = [d["ebitda"] for d in days if d["ebitda"] is not None]
    avg7   = sum(opened[-7:]) / len(opened[-7:]) if opened else 0
    remaining = count_open_days_raw(today_real + timedelta(1), month_end)
    proj = round(cum + avg7 * remaining, 2)
    return {"days": days, "cum_now": round(cum, 2), "proj_end": proj,
            "cross_date": cross, "month_end": month_end.isoformat()}


SEATS_TERRACE = 10
SEATS_INSIDE  = 6
SEATS_TOTAL   = SEATS_TERRACE + SEATS_INSIDE   # 16

def _rush_concentration(docs):
    """Part du CA réalisée sur les 3 heures les plus fortes (28 jours)."""
    by_hour = {}
    for d in docs:
        lt = d.get("local_time") or ""
        try:
            h = int(lt[11:13])
        except (ValueError, IndexError):
            continue
        by_hour[h] = by_hour.get(h, 0.0) + float(d.get("amount_gross", 0))
    total = sum(by_hour.values())
    if total <= 0:
        return None
    top = sorted(by_hour.items(), key=lambda x: -x[1])[:3]
    return {"top_share": round(sum(v for _, v in top) / total * 100),
            "hours": sorted(h for h, _ in top),
            "peak_hour": max(by_hour, key=by_hour.get)}


def _movers(cur_merged, prev_merged, min_rev=10.0, n=3):
    """Produits en plus forte hausse/baisse de CA semaine vs semaine."""
    changes = []
    for name in set(cur_merged) | set(prev_merged):
        if name.lower().startswith("vendas"):   # artefacts de saisie groupée
            continue
        cur  = float(cur_merged.get(name, {}).get("rev_ttc", 0))
        prev = float(prev_merged.get(name, {}).get("rev_ttc", 0))
        if max(cur, prev) < min_rev:
            continue
        if prev > 0:
            pct = round((cur - prev) / prev * 100)
        elif cur > 0:
            pct = None   # nouveau produit (pas de base de comparaison)
        else:
            continue
        changes.append({"name": name, "cur": round(cur, 2), "prev": round(prev, 2), "pct": pct})
    ups   = sorted([c for c in changes if c["pct"] is None or c["pct"] > 0],
                   key=lambda c: -(c["pct"] if c["pct"] is not None else 999))[:n]
    downs = sorted([c for c in changes if c["pct"] is not None and c["pct"] < 0],
                   key=lambda c: c["pct"])[:n]
    return {"up": ups, "down": downs}


# ── Presets de période ────────────────────────────────────────────────────────
def _week_start(d):
    """Lundi de la semaine en cours."""
    return d - timedelta(days=d.weekday())

PRESET_RANGES = {
    "today":      lambda d: (d, d),
    "yesterday":  lambda d: (d - timedelta(1), d - timedelta(1)),
    "week":       lambda d: (_week_start(d), d),
    "lastweek":   lambda d: (_week_start(d) - timedelta(7), _week_start(d) - timedelta(1)),
    "month":      lambda d: (d.replace(day=1), d),
    "all":        lambda d: (date(2026, 5, 27), d),  # date d'ouverture Estudantina
}
PRESET_LABELS = {
    "today":     "Today",
    "yesterday": "Yesterday",
    "week":      "This week",
    "lastweek":  "Last week",
    "month":     "This month",
    "all":       "Since opening",
}
# Le détail articles des jours passés vient du cache daily_summary (Supabase) ;
# seul le jour courant est détaillé en live via l'API Vendus.

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300   # statiques : 5 min de cache max

# Version des assets — bump à chaque changement de dashboard.js/style.css
ASSET_VERSION = "20260725g"

@app.context_processor
def _inject_asset_version():
    return {"v": ASSET_VERSION}


# ── Authentification ──────────────────────────────────────────────────────────
# DASHBOARD_PASSWORD non défini → auth désactivée (dev local).
# INVESTOR_PASSWORD (optionnel) → accès lecture seule (GET uniquement).
# STAFF_PASSWORD    (optionnel) → accès limité à la page COGS (recettes).
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
INVESTOR_PASSWORD  = os.environ.get("INVESTOR_PASSWORD", "")
STAFF_PASSWORD     = os.environ.get("STAFF_PASSWORD", "")
AUTH_SECRET        = os.environ.get("AUTH_SECRET", DASHBOARD_PASSWORD)

# Chemins autorisés pour le rôle staff : COGS et Stock (recettes + appro).
STAFF_ALLOWED_PREFIXES = (
    "/cogs", "/api/cogs", "/api/ingredients", "/api/preparations",
    "/api/recipe", "/api/product", "/stock", "/api/supplies", "/logout",
    "/sop", "/api/sop",
    "/events", "/api/events",
)

# Chemins fermés au rôle investisseur : détail dépenses, congés staff,
# réconciliation (montre l'écart de caisse). Le reste (dashboard, COGS,
# stock, coûts) reste accessible en lecture seule.
INVESTOR_BLOCKED_PREFIXES = (
    "/expenses", "/api/expenses",
    "/holidays", "/api/time_off",
    "/reconciliation", "/api/reconciliation", "/api/cash",
    "/api/cashflow",
)

def _auth_token(role):
    return hmac.new(AUTH_SECRET.encode(), f"estushop-auth-v1:{role}".encode(),
                    hashlib.sha256).hexdigest()

def _current_role():
    """'admin', 'investor', 'staff' ou None."""
    cookie = request.cookies.get("estu_auth", "")
    if not cookie:
        return None
    if hmac.compare_digest(cookie, _auth_token("admin")):
        return "admin"
    if INVESTOR_PASSWORD and hmac.compare_digest(cookie, _auth_token("investor")):
        return "investor"
    if STAFF_PASSWORD and hmac.compare_digest(cookie, _auth_token("staff")):
        return "staff"
    return None

@app.before_request
def _require_auth():
    if not DASHBOARD_PASSWORD:
        return
    if request.path == "/login" or request.path.startswith("/static/"):
        return
    # Endpoints cron : protégés par CRON_SECRET, pas par le login dashboard.
    if request.path.startswith("/api/cron/"):
        return
    role = _current_role()
    if role is None:
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect("/login")
    # Investisseur : lecture seule, et onglets sensibles fermés
    if role == "investor":
        if request.method not in ("GET", "HEAD"):
            return jsonify({"error": "read-only — investor access"}), 403
        if request.path.startswith(INVESTOR_BLOCKED_PREFIXES):
            if request.path.startswith("/api/"):
                return jsonify({"error": "restricted — not available for investor"}), 403
            return redirect("/")
    # Staff : accès limité à la page COGS (recettes) et ses APIs
    if role == "staff" and not request.path.startswith(STAFF_ALLOWED_PREFIXES):
        if request.path.startswith("/api/"):
            return jsonify({"error": "restricted — recipes only"}), 403
        return redirect("/cogs")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        pw = request.form.get("password", "")
        role = None
        if hmac.compare_digest(pw, DASHBOARD_PASSWORD):
            role = "admin"
        elif INVESTOR_PASSWORD and hmac.compare_digest(pw, INVESTOR_PASSWORD):
            role = "investor"
        elif STAFF_PASSWORD and hmac.compare_digest(pw, STAFF_PASSWORD):
            role = "staff"
        if role:
            dest = "/cogs" if role == "staff" else "/"
            resp = make_response(redirect(dest))
            resp.set_cookie("estu_auth", _auth_token(role),
                            max_age=30*24*3600, httponly=True,
                            secure=True, samesite="Lax")
            return resp
        error = "Incorrect password"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estudantina — Sign in</title>
<meta name="theme-color" content="#EDEAE3">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --canvas:#EDEAE3; --ink:#26241E; --muted:#6E6A5E; --faint:#A29D8F;
         --spec:#2554C7; --border:#DBD7CB; --card:#fff;
         --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace; }}
* {{ box-sizing:border-box; }}
body {{ font-family:'Inter',-apple-system,sans-serif; background:var(--canvas); color:var(--ink);
       margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
       padding:24px; -webkit-font-smoothing:antialiased; }}
.wrap {{ width:100%; max-width:420px; }}
.eyebrow {{ font-family:var(--mono); font-size:11px; letter-spacing:.14em; text-transform:uppercase;
            color:var(--muted); display:flex; align-items:center; gap:9px; margin-bottom:18px; }}
.eyebrow b {{ color:var(--spec); font-weight:600; }}
h1 {{ font-size:26px; font-weight:700; letter-spacing:-.02em; line-height:1.1; margin:0 0 8px; }}
.sub {{ font-size:15px; color:var(--muted); margin:0 0 26px; line-height:1.5; }}
label {{ font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase;
         color:var(--muted); display:block; margin-bottom:7px; }}
input {{ width:100%; padding:12px 14px; border:1px solid var(--border); border-radius:10px;
         font-family:inherit; font-size:15px; background:var(--card); color:var(--ink); }}
input:focus {{ outline:none; border-color:var(--spec); box-shadow:0 0 0 3px rgba(37,84,199,.10); }}
button {{ width:100%; margin-top:12px; padding:13px; background:var(--spec); color:#fff; border:none;
          border-radius:10px; font-family:inherit; font-size:15px; font-weight:600; cursor:pointer; }}
button:hover {{ opacity:.9; }}
.err {{ color:#c4554d; font-size:13px; margin-bottom:12px; }}
.note {{ background:rgba(38,36,30,.05); border-radius:10px; padding:14px 16px; margin-top:20px;
         font-size:12.5px; color:var(--muted); line-height:1.5; }}
.note b {{ color:var(--ink); }}
</style></head><body>
<div class="wrap">
  <div class="eyebrow"><b>◳ ESTUDANTINA</b> · SIGN IN</div>
  <h1>Your numbers, in clear.</h1>
  <p class="sub">Private dashboard for Estudantina — enter your password to continue.</p>
  {f'<div class="err">{error}</div>' if error else ''}
  <form method="POST">
    <label for="pw">Password</label>
    <input id="pw" type="password" name="password" placeholder="••••••••" autofocus>
    <button type="submit">Sign in →</button>
  </form>
  <div class="note"><b>Private.</b> Access is role-based (owner, staff, investor). Your session stays signed in on this device for 30 days.</div>
</div>
</body></html>"""


@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.set_cookie("estu_auth", "", max_age=0)
    return resp


@app.route("/")
def index():
    return render_template("index.html", seuil=SEUIL_TRANSACTIONS,
                           role=_current_role() or "admin")


@app.route("/api/data")
def api_data():
    preset = request.args.get("preset", "today")
    start_arg = request.args.get("start_date", "")
    end_arg   = request.args.get("end_date", "")

    today_real = today_lisbon()

    from_date = to_date = None
    if preset == "custom" and start_arg and end_arg:
        try:
            from_date = date.fromisoformat(start_arg)
            to_date   = date.fromisoformat(end_arg)
            if from_date > to_date:
                from_date, to_date = to_date, from_date
            from_date = min(from_date, today_real)
            to_date   = min(to_date, today_real)
        except ValueError:
            preset, from_date, to_date = "today", None, None
    if from_date is None:
        if preset not in PRESET_RANGES:
            preset = "today"
        from_date, to_date = PRESET_RANGES[preset](today_real)

    is_single             = (from_date == to_date)
    n_days                = (to_date - from_date).days + 1

    comp_to   = from_date - timedelta(1)
    comp_from = comp_to   - timedelta(n_days - 1)

    # Fenêtres de comparaison alignées sur la saisonnalité hebdo (un café ne se
    # compare pas lundi-mardi vs samedi-dimanche) :
    #  · aujourd'hui (live)   → même jour semaine passée, filtré à l'heure courante
    #  · jour passé unique    → même jour de la semaine précédente
    #  · this/last week       → mêmes jours décalés de 7 jours
    #  · this month           → mêmes jours écoulés du mois précédent
    #  · custom / since open  → période précédente de même longueur (défaut)
    comp_is_sofar = False
    comp_label    = None
    if is_single and from_date == today_real:
        prev = today_real - timedelta(7)
        comp_from = comp_to = prev
        comp_is_sofar = True
        comp_label = "vs last " + prev.strftime("%a") + " same time"
    elif is_single:
        prev = from_date - timedelta(7)
        comp_from = comp_to = prev
        comp_label = "vs " + prev.strftime("%a %d %b")
    elif preset in ("week", "lastweek"):
        comp_from, comp_to = from_date - timedelta(7), to_date - timedelta(7)
        comp_label = "vs same days last week"
    elif preset == "month":
        # ⚠️ ALIGNÉ SUR LES JOURS DE SEMAINE, PAS SUR LE QUANTIÈME.
        #
        # L'ancienne version comparait le 1er-5 août au 1er-5 juillet. Or le café ouvre lundi,
        # jeudi, vendredi, samedi, dimanche : au 5 août 2026 cela opposait sam/dim/lun (3 jours
        # ouvrés) à mer/jeu/ven/sam/dim (4 jours ouvrés). Ni les mêmes jours, ni le même nombre.
        # Le commentaire juste au-dessus affirme pourtant que ces fenêtres sont « alignées sur
        # la saisonnalité hebdo » — c'était vrai des autres branches, pas de celle-ci.
        #
        # Reculer de 4 semaines pleines préserve exactement le jour de semaine de chaque date,
        # et retombe dans le mois précédent dans tous les cas utiles. On ne recule PAS d'un mois
        # calendaire : c'est ce décalage-là qui produisait la comparaison bancale.
        comp_from, comp_to = from_date - timedelta(28), to_date - timedelta(28)
        comp_label = "vs same weekdays, 4 weeks earlier"
    else:
        comp_label = f"vs previous {n_days} days"

    # ── Stratégie de chargement ──────────────────────────────────────────────
    # Aujourd'hui : items live avec micro-cache 45s (partagé entre les vues).
    # Jour passé unique : items live (peu de tickets).
    # Multi-jours : documents légers + cache daily_summary pour les jours passés.
    # Sparkline / WoW / meilleur jour : dérivés du cache — zéro appel Vendus.
    is_today_single = is_single and from_date == today_real
    force_fresh     = request.args.get("fresh") == "1"

    def _load_docs_main():
        if is_today_single:
            return _get_today_docs_cached(force=force_fresh)
        if is_single:
            return get_documents_with_items(from_date.isoformat(), to_date.isoformat())
        return get_documents(from_date.isoformat(), to_date.isoformat())

    def _load_today_docs():
        """Docs du jour (micro-cache) — pour le live des périodes et la sparkline."""
        if is_today_single:
            return None   # déjà chargés par docs_main
        return _get_today_docs_cached(force=force_fresh)

    def _load_comp():
        try:
            return get_documents(comp_from.isoformat(), comp_to.isoformat())
        except Exception:
            return None   # échec ≠ zéro vente

    def _load_heatmap_payload():
        return _heatmap_payload_cached(today_real)

    # Bandeau "Today" des vues multi-jours : il se compare au MÊME JOUR DE LA
    # SEMAINE précédente (un samedi se compare à un samedi), à heure égale —
    # comme la zone période. Appel léger d'une journée, en parallèle.
    strip_needs_comp = (not is_single) and to_date == today_real

    def _load_today_lastweek():
        if not strip_needs_comp:
            return None
        prev = today_real - timedelta(7)
        try:
            docs = get_documents(prev.isoformat(), prev.isoformat()) or []
        except Exception:
            return None
        # `local_time` Vendus est en heure de Lisbonne : couper à une heure UTC
        # offrirait une heure de ventes en plus au jour de comparaison.
        now_hms = now_lisbon().strftime("%H:%M:%S")
        docs = [d for d in docs if (d.get("local_time", "") or "")[11:19] <= now_hms]
        return {"date": prev.isoformat(), **calc_stats(docs)}

    # Appels indépendants en parallèle avec le fetch principal
    with ThreadPoolExecutor(max_workers=6) as pool:
        fut_docs    = pool.submit(_load_docs_main)
        fut_today   = pool.submit(_load_today_docs)
        fut_comp    = pool.submit(_load_comp)
        fut_catalog = pool.submit(get_catalog)
        fut_hm      = pool.submit(_load_heatmap_payload)
        fut_tlw     = pool.submit(_load_today_lastweek)

        try:
            docs_main = fut_docs.result(timeout=55)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        warnings = []

        try:
            today_docs = fut_today.result(timeout=30)
        except Exception:
            today_docs = None
            warnings.append("Today's detail unavailable — today's COGS estimated")
        if is_today_single:
            today_docs = docs_main

        docs_comp = fut_comp.result(timeout=5)
        if docs_comp is None:
            warnings.append("Previous-period comparison unavailable")
            docs_comp = []
        # Vue "aujourd'hui" : ne garder du jour de comparaison que ce qui a été
        # vendu avant l'heure courante → comparaison à périmètre horaire égal.
        if comp_is_sofar and docs_comp:
            now_hms = now_lisbon().strftime("%H:%M:%S")   # cf. local_time Vendus
            docs_comp = [d for d in docs_comp
                         if (d.get("local_time", "") or "")[11:19] <= now_hms]

        catalog = fut_catalog.result(timeout=10) or {}
        if not catalog:
            warnings.append("Product catalog unavailable — margins and COGS not computed")

        try:
            today_lastweek = fut_tlw.result(timeout=15)
        except Exception:
            today_lastweek = None

        try:
            heatmap_payload = fut_hm.result(timeout=15)
        except Exception:
            heatmap_payload = None

    today_iso = today_real.isoformat()
    today_sum = _summarize_docs_items(today_docs or [], catalog)
    ts        = calc_stats(today_docs or [])   # CA/nb du jour — sparkline & WoW

    # ── Agrégats item-level : cache pour les jours passés + live aujourd'hui ──
    if is_single:
        day_summary = today_sum if is_today_single else _summarize_docs_items(docs_main, catalog)
        # Cache opportuniste : une journée passée consultée = summary persisté
        if to_date < today_real and catalog:
            _upsert_summary(to_date.isoformat(), day_summary)
        period_rows = [{"day": to_date.isoformat(), **day_summary}]
    else:
        past_to     = min(to_date, today_real - timedelta(1))
        period_rows = _ensure_summaries(from_date, past_to, catalog) if from_date <= past_to else []
        if today_docs and from_date <= today_real <= to_date:
            period_rows = period_rows + [{"day": today_iso, **today_sum}]

    cogs_agg = (
        round(sum(r.get("cogs_ht",    0) for r in period_rows), 2),
        round(sum(r.get("covered_ht", 0) for r in period_rows), 2),
        round(sum(r.get("items_ht",   0) for r in period_rows), 2),
    )
    merged_products = _merge_products(period_rows)

    # ── Séries dérivées du cache daily_summary (zéro appel Vendus) ───────────
    rows_hist = _ensure_summaries(today_real - timedelta(14), today_real - timedelta(1), catalog)
    iso_7   = (today_real - timedelta(6)).isoformat()
    rows_7d = [r for r in rows_hist if r["day"] >= iso_7]

    today_has_data = bool(today_docs)
    merged_7d = _merge_products(rows_7d + ([{"day": today_iso, **today_sum}] if today_has_data else []))

    # Sparkline 7 derniers jours
    week_data = []
    for i in range(7):
        d7  = today_real - timedelta(days=6 - i)
        iso = d7.isoformat()
        if d7 == today_real:
            ca, nb = ts["ca"], ts["nb"]
        else:
            row = next((r for r in rows_7d if r["day"] == iso), None)
            ca, nb = (float(row["ca_ttc"]), row["nb"]) if row else (0.0, 0)
        week_data.append({"date": iso, "label": d7.strftime("%a"), "ca": round(ca, 2), "nb": nb})

    # Croissance 7 jours PLEINS vs 7 jours pleins précédents.
    # Aujourd'hui (partiel) est exclu : l'inclure biaisait le % à la baisse
    # toute la matinée. Fenêtres : J-7..J-1 vs J-14..J-8.
    iso_full7 = (today_real - timedelta(7)).isoformat()
    wow_cur   = [r for r in rows_hist if r["day"] >= iso_full7]
    wow_prev  = [r for r in rows_hist if r["day"] <  iso_full7]
    cur_ca  = round(sum(float(r["ca_ttc"]) for r in wow_cur), 2)
    cur_nb  = sum(r["nb"] for r in wow_cur)
    prev_ca = round(sum(float(r["ca_ttc"]) for r in wow_prev), 2)
    prev_nb = sum(r["nb"] for r in wow_prev)
    wow_data = {
        "cur_ca": cur_ca, "prev_ca": prev_ca, "cur_nb": cur_nb, "prev_nb": prev_nb,
        "growth_ca": round((cur_ca - prev_ca) / prev_ca * 100) if prev_ca else None,
        "growth_nb": round((cur_nb - prev_nb) / prev_nb * 100) if prev_nb else None,
    }
    # Fenêtre de comparaison des movers (7 jours pleins avant rows_7d) — inchangée
    prev = [r for r in rows_hist
            if (today_real - timedelta(13)).isoformat() <= r["day"] < iso_7]

    # Meilleur jour de la semaine — historique complet depuis le cache
    older = _get_summaries(OPENING_DAY, (today_real - timedelta(15)).isoformat())
    wd_rows = (older if isinstance(older, list) else []) + rows_hist
    if ts["nb"]:
        wd_rows = wd_rows + [{"day": today_iso, "ca_ttc": ts["ca"], "nb": ts["nb"]}]
    by_wd = {}
    for r in wd_rows:
        if (r.get("nb") or 0) <= 0:
            continue
        wd  = date.fromisoformat(r["day"]).strftime("%A")
        acc = by_wd.setdefault(wd, {"ca": 0.0, "n": 0})
        acc["ca"] += float(r.get("ca_ttc") or 0)
        acc["n"]  += 1
    weekday_data = sorted(
        [{"day": wd, "avg_ca": round(v["ca"] / v["n"], 2), "n_days": v["n"]}
         for wd, v in by_wd.items()],
        key=lambda x: -x["avg_ca"]) or None

    result = {
        # Méta
        "preset":        preset,
        "period_label":  (f"{from_date.strftime('%d %b')} – {to_date.strftime('%d %b')}"
                          if preset == "custom" else PRESET_LABELS.get(preset, preset)),
        "from_date":     from_date.isoformat(),
        "to_date":       to_date.isoformat(),
        "n_days":        n_days,
        "is_single_day": is_single,
        "has_items":     True,
        "date":          to_date.isoformat(),
        "updated_at":    now_lisbon().strftime("%H:%M"),   # lu par un humain à Lisbonne
        "is_today":      (preset == "today"),
        # Comparaison : libellé + mode "à la même heure" (vue aujourd'hui live)
        "comp_label":    comp_label,
        "comp_sofar":    comp_is_sofar,
        # Stats globales
        "today":         calc_stats(docs_main),
        "yesterday":     calc_stats(docs_comp),
        "seuil":         SEUIL_TRANSACTIONS,
        # Graphe temporel
        "daily":         daily_breakdown(docs_main),
        # Paiements & TVA (données document-level — toujours disponibles)
        "payments":      payment_breakdown(docs_main),
        "tva":           tva_breakdown(docs_main),
        # Tendance (résultats pré-calculés en parallèle)
        "week":          week_data,
        # Comparaison du bandeau "Today" : même jour de la semaine, semaine
        # précédente, filtré à l'heure courante (None hors vues multi-jours).
        "today_lastweek": today_lastweek,
        "wow":           wow_data,
        "weekdays":      weekday_data,
        # Perf commerciale
        "median":        ticket_median(docs_main),
        "upsell":        _upsell_from_rows(period_rows),
        "ticket_dist":   ticket_distribution(docs_main),
        # Produits sur 7j glissants — depuis le cache + aujourd'hui live
        "products_7d":   _products_list(merged_7d, catalog, n=None),
        # Transactions récentes
        "recent":        recent_docs(docs_main, n=(None if is_single else 10)),
    }

    # ── Économie : COGS depuis le cache (multi-jours) ou les items (jour) ─────
    result["economics"] = daily_economics(docs_main, catalog, n_days,
                                           from_date=from_date, to_date=to_date,
                                           cogs_agg=cogs_agg)
    if result["economics"].get("charges_source") == "indisponible":
        warnings.append("Supabase costs unreachable — costs and break-even not computed")

    # ── Break-even de la période de comparaison (point mort/jour ouvré) ───────
    # Permet de suivre l'évolution du point mort d'une période à l'autre.
    # NB : les charges sont lues en direct (mêmes valeurs pour les 2 périodes),
    # donc cette évolution reflète surtout les changements de MARGE (mix/prix).
    try:
        comp_days = (comp_to - comp_from).days + 1
        comp_rows = _ensure_summaries(comp_from, comp_to, catalog) if comp_from <= comp_to else []
        if comp_rows:
            comp_cogs_agg = (
                round(sum(r.get("cogs_ht",    0) for r in comp_rows), 2),
                round(sum(r.get("covered_ht", 0) for r in comp_rows), 2),
                round(sum(r.get("items_ht",   0) for r in comp_rows), 2),
            )
            comp_eco = daily_economics([], catalog, comp_days,
                                       from_date=comp_from, to_date=comp_to,
                                       cogs_agg=comp_cogs_agg)
            result["economics"]["seuil_jour_prev"] = comp_eco.get("seuil_ca_ttc_jour")
    except Exception:
        pass
    result["warnings"] = warnings

    # ── Insights visuels (indépendants du preset sélectionné) ─────────────────
    # Jamais bloquant : une erreur ici ne doit pas casser le dashboard.
    try:
        eco = result["economics"]
        # `cout_jour` reste tiré d'`eco` à dessein : c'est charges Supabase ÷ JOURS_OUVERTS_MOIS
        # (vendus.py:699), sans lien avec la période affichée. L'autre entrée du bloc, elle,
        # descendait bien du preset — voir plus bas.
        cout_jour = eco.get("cout_jour") or 0

        # 1. Jauge du jour vs seuil
        if is_today_single:
            today_seuil = eco.get("seuil_ca_ttc")
        else:
            eco_today = daily_economics(today_docs or [], catalog, 1,
                                        from_date=today_real, to_date=today_real,
                                        cogs_agg=(today_sum["cogs_ht"], today_sum["covered_ht"],
                                                  today_sum["items_ht"]))
            today_seuil = eco_today.get("seuil_ca_ttc")

        # 3+4. Série EBITDA du mois (cumul, projection, calendrier)
        month_start = today_real.replace(day=1)
        rows_month  = _ensure_summaries(month_start, today_real - timedelta(1), catalog) \
                      if month_start < today_real else []
        if ts["nb"]:
            rows_month = rows_month + [{"day": today_iso, **today_sum}]

        # ⚠️ Le taux de repli vient du MOIS, pas de la période sélectionnée.
        #
        # Ce bloc s'annonce « indépendant du preset sélectionné » (voir plus haut) et ne l'était
        # pas : `fallback_rate` dérivait de `eco["marge_brute_ht_pct"]`, l'économie de la période
        # affichée. Changer le filtre au-dessus déplaçait donc le cumul et la projection du mois
        # — des chiffres qui ne parlent que du mois. Mesuré : 150 € contre 200 € de cumul sur le
        # même mois selon le filtre, et ~510 € d'écart sur le point mort mensuel côté Mesa, où le
        # même défaut a été trouvé puis corrigé (tests/test_month_series.py).
        #
        # Le taux du mois se mesure sur ses propres lignes : marge réelle si la couverture le
        # permet, sinon l'hypothèse du BP. Les deux entrées sont indépendantes du filtre, donc la
        # zone répond la même chose quel que soit le preset.
        month = _month_series(rows_month, cout_jour,
                              _month_fallback_rate(rows_month), today_real) \
                if cout_jour else None

        # 6. Top movers : 7 derniers jours vs 7 précédents
        movers = _movers(merged_7d, _merge_products(prev))

        # ── Médiane CA par jour de semaine (jours pleins, hors aujourd'hui) ──
        # Référence "jour typique" : comparer ce lundi aux lundis passés, pas à
        # dimanche. Médiane (pas moyenne) → robuste aux jours exceptionnels.
        _wd_vals = {}
        for r in wd_rows:
            if r["day"] == today_iso or (r.get("nb") or 0) <= 0:
                continue
            _wd_vals.setdefault(date.fromisoformat(r["day"]).weekday(), []) \
                    .append(float(r.get("ca_ttc") or 0))
        med_by_wd = {}
        for wd, vals in _wd_vals.items():
            vals.sort()
            mid = len(vals) // 2
            med_by_wd[wd] = round(vals[mid] if len(vals) % 2 else
                                  (vals[mid - 1] + vals[mid]) / 2, 2)

        # ── Verdict du jour : la journée en une phrase ────────────────────────
        # Heure de franchissement du break-even (cumul des tickets du jour)
        seuil_time = None
        if today_seuil and today_docs:
            _cum = 0.0
            for dd in sorted(today_docs, key=lambda x: x.get("local_time") or ""):
                _cum += float(dd.get("amount_gross") or 0)
                if _cum >= today_seuil:
                    seuil_time = (dd.get("local_time") or "")[11:16]
                    break
        _typical = med_by_wd.get(today_real.weekday())
        verdict = {
            "ca": ts["ca"], "nb": ts["nb"],
            "weekday": today_real.strftime("%A"),
            "typical_ca": _typical,          # médiane des mêmes jours (journées PLEINES)
            "pct_of_typical": round(ts["ca"] / _typical * 100) if _typical else None,
            "seuil": today_seuil,
            "seuil_time": seuil_time,        # None = pas encore atteint
        }

        # ── Projection CA fin de mois vs break-even mensuel ──────────────────
        if month:
            from config import count_open_days_raw as _odays
            _mend   = date.fromisoformat(month["month_end"])
            _mstart = today_real.replace(day=1)
            ca_mtd  = round(sum(float(r.get("ca_ttc") or 0) for r in rows_month), 2)
            _open_ca = [float(r.get("ca_ttc") or 0) for r in rows_month
                        if (r.get("nb") or 0) > 0]
            _avg7   = sum(_open_ca[-7:]) / len(_open_ca[-7:]) if _open_ca else 0
            _remain = _odays(today_real + timedelta(1), _mend)
            _sj     = eco.get("seuil_ca_ttc_jour")
            month["ca_mtd"]        = ca_mtd
            month["proj_ca_end"]   = round(ca_mtd + _avg7 * _remain, 2)
            month["seuil_ca_month"] = (round(_sj * _odays(_mstart, _mend), 2)
                                       if _sj else None)

        # Articles par ticket + taux multi-articles (période sélectionnée)
        total_units = sum(p["qty"] for p in merged_products.values())
        total_tx    = sum(r.get("nb", 0) for r in period_rows)
        up          = _upsell_from_rows(period_rows)
        basket = {
            "items_per_ticket": round(total_units / total_tx, 2) if total_tx else None,
            "attach_pct":       up["rate"],
            **_tx_per_open_day(period_rows, from_date, to_date, today_real),
        }

        # CA par place assise (période) — 16 places (10 terrasse + 6 intérieur)
        ca_ttc_p  = eco.get("ca_ttc") or 0
        open_days = eco.get("open_days") or 1
        seat = {
            "seats": SEATS_TOTAL, "terrace": SEATS_TERRACE, "inside": SEATS_INSIDE,
            "per_seat_day": round(ca_ttc_p / SEATS_TOTAL / open_days, 2) if ca_ttc_p else None,
            "per_seat_period": round(ca_ttc_p / SEATS_TOTAL, 2) if ca_ttc_p else None,
        }

        result["insights"] = {
            "today_gauge": {"ca": ts["ca"], "seuil": today_seuil},
            "heatmap":     (heatmap_payload or {}).get("heatmap"),
            "rush":        (heatmap_payload or {}).get("rush"),
            "month":       month,
            "movers":      movers,
            "basket":      basket,
            "seat":        seat,
            "verdict":     verdict,
        }
    except Exception as e:
        result["insights"] = None
        warnings.append(f"Insights unavailable ({type(e).__name__})")

    # ── Produits et mix — depuis les agrégats fusionnés ───────────────────────
    result["products"] = _products_list(merged_products, catalog, n=None)
    result["mix"]      = _mix_from_merged(merged_products, catalog)

    # ── Sections disponibles uniquement pour un jour unique ───────────────────
    if is_single:
        result["hourly"] = hourly_breakdown(docs_main)
        result["curve"]  = cumulative_curve(docs_main)
        result["rush"]   = rush_detector(docs_main)
        result["tempo"]  = service_tempo(docs_main)
        result["unsold"] = unsold_today(docs_main, catalog)
        # Référence : même jour de la semaine précédente (docs_comp est déjà
        # aligné dessus, et filtré à l'heure courante sur la vue "aujourd'hui").
        # Sert de repère sur les barres horaires et de courbe fantôme sur le cumul.
        result["hourly_prev"] = hourly_breakdown(docs_comp) if docs_comp else None
        result["curve_prev"]  = cumulative_curve(docs_comp) if docs_comp else None
    else:
        result["hourly"] = None
        result["curve"]  = None
        result["hourly_prev"] = None
        result["curve_prev"]  = None
        result["rush"]   = []
        result["tempo"]  = None
        result["unsold"] = []

    return jsonify(result)


@app.route("/api/cron/refresh")
def api_cron_refresh():
    """Rafraîchit le cache serverside des docs du jour. Appelé toutes les 5 min
    par un cron externe (GitHub Actions / Vercel cron). Protégé par CRON_SECRET
    (query ?key= ou header Authorization: Bearer)."""
    secret = os.environ.get("CRON_SECRET", "")
    if secret:
        given = request.args.get("key") or ""
        auth  = request.headers.get("Authorization", "")
        if given != secret and auth != f"Bearer {secret}":
            return jsonify({"error": "unauthorized"}), 401
    try:
        docs = _refresh_today_cache()
        # Réchauffe aussi le catalogue et la heatmap (autres appels Vendus lourds),
        # pour qu'aucune requête utilisateur ne paie leur recalcul.
        try:
            get_catalog()
        except Exception:
            pass
        hm_warm = False
        try:
            hm_warm = _warm_heatmap_cache()
        except Exception:
            pass
        return jsonify({"ok": True, "day": today_lisbon().isoformat(),
                        "docs_cached": len(docs), "heatmap_warm": hm_warm,
                        "at": _utc_iso()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/summary/audit")
def api_summary_audit():
    """
    Rapproche le cache `daily_summary` et Vendus, jour par jour. LECTURE SEULE — n'écrit rien.

    Sert à retrouver les journées figées à mi-parcours par l'ancien défaut de /api/cashflow.
    À ouvrir dans le navigateur ; la liste `days_to_rebuild` se recolle telle quelle dans
    /api/summary/rebuild.

    On interroge Vendus en vue LISTE (2 pages depuis l'ouverture) et non en vue détaillée
    (~1250 appels) : le rapprochement porte sur `ca_ttc` et `nb`, qui suffisent à démasquer un
    jour partiel, et que la vue liste donne déjà avec la bonne sémantique — `get_documents`
    négative les avoirs.
    """
    from vendus import get_documents
    from_iso = request.args.get("from", OPENING_DAY)
    to_iso   = request.args.get("to", (date.today() - timedelta(1)).isoformat())
    try:
        from_date, to_date = date.fromisoformat(from_iso), date.fromisoformat(to_iso)
    except ValueError:
        return jsonify({"ok": False, "error": "dates attendues au format YYYY-MM-DD"}), 400
    # Jamais le jour courant : il est partiel par nature, l'y inclure signalerait un faux écart.
    to_date = min(to_date, date.today() - timedelta(1))
    if from_date > to_date:
        return jsonify({"ok": False, "error": "aucun jour plein dans la plage"}), 400

    try:
        docs = get_documents(from_date.isoformat(), to_date.isoformat())
    except Exception as e:
        return jsonify({"ok": False, "error": f"Vendus indisponible : {e}"}), 502

    vendus_by_day = {}
    for d in docs:
        day = (d.get("date") or d.get("local_time", ""))[:10]
        if not day:
            continue
        v = vendus_by_day.setdefault(day, {"ca_ttc": 0.0, "nb": 0})
        v["ca_ttc"] += float(d.get("amount_gross") or 0)
        if not d.get("_refund"):
            v["nb"] += 1

    cache_rows = _get_summaries(from_date.isoformat(), to_date.isoformat())
    ecarts = _audit_summaries(cache_rows, vendus_by_day, from_date, to_date)

    manque = round(sum(e["ecart_ca"] for e in ecarts if e["ecart_ca"] > 0), 2)
    return jsonify({
        "ok": True,
        "from": from_date.isoformat(), "to": to_date.isoformat(),
        "jours_controles": (to_date - from_date).days + 1,
        "jours_en_ecart": len(ecarts),
        "ca_manquant_dans_le_cache": manque,
        "par_verdict": {v: sum(1 for e in ecarts if e["verdict"] == v)
                        for v in ("partiel", "excedentaire", "manquant", "fantome")},
        "days_to_rebuild": [e["day"] for e in ecarts],
        "ecarts": ecarts,
    })


@app.route("/api/summary/rebuild", methods=["POST"])
def api_summary_rebuild():
    """Recalcule le cache daily_summary (après changement de prix d'achat/recettes).
    Body optionnel : {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} — défaut : tout l'historique."""
    from vendus import get_documents_with_items, get_catalog as _gc
    data      = request.get_json(silent=True) or {}
    from_iso  = data.get("from", OPENING_DAY)
    to_iso    = data.get("to", (today_lisbon() - timedelta(1)).isoformat())
    catalog   = _gc()
    if not catalog:
        return jsonify({"ok": False, "error": "catalogue Vendus indisponible"}), 502
    docs = get_documents_with_items(from_iso, to_iso)
    by_day = {}
    for doc in docs:
        day = (doc.get("date") or doc.get("local_time", ""))[:10]
        by_day.setdefault(day, []).append(doc)
    cur, end, count = date.fromisoformat(from_iso), date.fromisoformat(to_iso), 0
    while cur <= end:
        iso = cur.isoformat()
        _upsert_summary(iso, _summarize_docs_items(by_day.get(iso, []), catalog))
        count += 1
        cur += timedelta(1)
    return jsonify({"ok": True, "days_rebuilt": count})


@app.route("/api/cashflow")
def api_cashflow():
    """Trésorerie réelle par mois : CA encaissé (Vendus) vs dépenses sorties
    (Expenses, données bancaires réelles) — depuis l'ouverture. N'utilise
    jamais les charges théoriques de la page Costs (évite le double compte)."""
    OPEN_DATE = date(2026, 5, 27)
    to_date   = date.today()

    catalog = get_catalog() or {}
    rows    = _ensure_summaries(OPEN_DATE, to_date, catalog)

    # Le jour courant est ajouté EN MÉMOIRE, jamais écrit : _ensure_summaries refuse désormais
    # de le figer (voir sa docstring). Sans cet ajout, la trésorerie du mois en cours perdrait
    # la journée d'aujourd'hui — un manque silencieux, alors que le but de la garde est
    # justement de ne pas laisser un chiffre partiel passer pour définitif.
    today_docs = _get_today_docs_cached()
    if today_docs:
        rows = rows + [{"day": date.today().isoformat(),
                        **_summarize_docs_items(today_docs, catalog)}]

    rev_by_month = {}
    for r in rows:
        mk = r["day"][:7]
        rev_by_month[mk] = rev_by_month.get(mk, 0.0) + float(r.get("ca_ttc") or 0)

    exp_rows = _supa_get("expenses", {
        "date": f"gte.{OPEN_DATE.isoformat()}",
        "active": "eq.true",
    })
    exp_by_month      = {}
    exp_by_month_excl = {}
    for e in exp_rows if isinstance(exp_rows, list) else []:
        mk  = (e.get("date") or "")[:7]
        amt = float(e.get("amount") or 0)
        exp_by_month[mk] = exp_by_month.get(mk, 0.0) + amt
        if e.get("category") != "works":
            exp_by_month_excl[mk] = exp_by_month_excl.get(mk, 0.0) + amt

    months = sorted(set(rev_by_month) | set(exp_by_month))
    cum = cum_excl = 0.0
    out = []
    for mk in months:
        rev      = round(rev_by_month.get(mk, 0.0), 2)
        exp      = round(exp_by_month.get(mk, 0.0), 2)
        exp_excl = round(exp_by_month_excl.get(mk, 0.0), 2)
        net      = round(rev - exp, 2)
        net_excl = round(rev - exp_excl, 2)
        cum      += net
        cum_excl += net_excl
        out.append({
            "month": mk, "revenue": rev,
            "expenses": exp, "expenses_excl_capex": exp_excl,
            "net": net, "net_excl_capex": net_excl,
            "cum_net": round(cum, 2), "cum_net_excl_capex": round(cum_excl, 2),
        })
    return jsonify({"months": out, "from_date": OPEN_DATE.isoformat(), "to_date": to_date.isoformat()})


@app.route("/cogs")
def cogs_page():
    return render_template("cogs.html", role=_current_role() or "admin")


@app.route("/charges")
def charges_page():
    return render_template("charges.html", role=_current_role() or "admin")


@app.route("/expenses")
def expenses_page():
    return render_template("expenses.html")


def _is_admin():
    """Admin réel (ou dev local sans mot de passe)."""
    return not DASHBOARD_PASSWORD or _current_role() == "admin"

@app.route("/stock")
def stock_page():
    role = _current_role() or "admin"
    return render_template("stock.html", role=role)


# ── Supplies / Stock CRUD ─────────────────────────────────────────────────────

@app.route("/api/supplies", methods=["GET"])
def api_supplies_get():
    rows = _supa_get("supplies", {"order": "category.asc,name.asc"})
    return jsonify(rows)

@app.route("/api/supplies", methods=["POST"])
def api_supplies_post():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    row = {
        "name":     name,
        "category": (data.get("category") or "").strip(),
        "status":   data.get("status", "ok"),
        "alert":    bool(data.get("alert", False)),
        "notes":    (data.get("notes") or "").strip(),
        "active":   data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("supplies", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/supplies/<string:sid>", methods=["PATCH"])
def api_supplies_patch(sid):
    data = request.get_json() or {}
    data["updated_at"] = _utc_iso()
    r = _req.patch(f"{SUPA_URL}/rest/v1/supplies", json=data,
                   headers=_supa_headers(), params={"id": f"eq.{sid}"})
    return jsonify({"ok": r.ok})

@app.route("/api/supplies/<string:sid>", methods=["DELETE"])
def api_supplies_delete(sid):
    ok = _supa_delete("supplies", "id", sid)
    return jsonify({"ok": ok})

SUPPLIES_SEED = [
    ("Coffee El Tambo","Coffee & tea"),("Coffee Guitare","Coffee & tea"),("Matcha","Coffee & tea"),
    ("Cacao","Coffee & tea"),("Caxemira tea","Coffee & tea"),("Darjeeling tea","Coffee & tea"),
    ("Toranja & manjericão tea","Coffee & tea"),("Houjicha tea","Coffee & tea"),
    ("Vigor milk","Milk & dairy"),("Oat milk","Milk & dairy"),("Milk","Milk & dairy"),
    ("Cream 35%","Milk & dairy"),("Greek yogurt","Milk & dairy"),("Cheese","Milk & dairy"),
    ("Butter","Milk & dairy"),("Feta","Milk & dairy"),
    ("Oranges","Fresh produce"),("Lemons","Fresh produce"),("Banana","Fresh produce"),
    ("Blueberries","Fresh produce"),("Cherry","Fresh produce"),("Yuzu","Fresh produce"),
    ("Verbena (verveine)","Fresh produce"),
    ("Ham","Meat & fish"),("Bacon","Meat & fish"),("Anchovy","Meat & fish"),
    ("Flour T55 National","Dry goods & baking"),("Flour Caputo T0","Dry goods & baking"),
    ("Baking powder","Dry goods & baking"),("Baking soda","Dry goods & baking"),
    ("Active dry yeast","Dry goods & baking"),("Egg","Dry goods & baking"),
    ("Cornstarch (maizena)","Dry goods & baking"),("Sugar","Dry goods & baking"),
    ("Brown sugar (Silver Spoon)","Dry goods & baking"),("Flor de Sal","Dry goods & baking"),
    ("Honey","Dry goods & baking"),("Cardamom","Dry goods & baking"),("Cinnamon","Dry goods & baking"),
    ("Oats","Dry goods & baking"),("Pecans","Dry goods & baking"),("Hazelnuts","Dry goods & baking"),
    ("Pumpkin seeds","Dry goods & baking"),("Chocolate 70% Pantagruel","Dry goods & baking"),
    ("Pollen","Dry goods & baking"),
    ("Salt","Spices & condiments"),("Pepper","Spices & condiments"),("Paprika","Spices & condiments"),
    ("Nutmeg","Spices & condiments"),("Dijon mustard","Spices & condiments"),
    ("Olive oil","Spices & condiments"),("Sunflower oil","Spices & condiments"),("Vinegar","Spices & condiments"),
    ("Sparkling water","Drinks"),
    ("Coffee cup large","Packaging & takeaway"),("Coffee cup small","Packaging & takeaway"),
    ("Plastic cup","Packaging & takeaway"),("Small square food box","Packaging & takeaway"),
    ("Medium food box","Packaging & takeaway"),("Large food box","Packaging & takeaway"),
    ("Takeaway paper bag","Packaging & takeaway"),("Napkins","Packaging & takeaway"),
    ("Takeaway lid","Packaging & takeaway"),("Plastic takeaway lid","Packaging & takeaway"),
    ("Straw","Packaging & takeaway"),("Stickers Estudantina","Packaging & takeaway"),
    ("Validation date stickers","Packaging & takeaway"),
    ("V60 filters size 02","Coffee equipment"),("Moccamaster filters size 04","Coffee equipment"),
    ("Ethyl alcohol 70% (machine cleaning)","Coffee equipment"),("Puly Caff machine detergent","Coffee equipment"),
    ("Baking paper","Kitchen wrap & storage"),("Cling film","Kitchen wrap & storage"),
    ("Aluminium foil","Kitchen wrap & storage"),("Ziplock bag 3l","Kitchen wrap & storage"),
    ("Ziplock bag 5l","Kitchen wrap & storage"),("Vacuum bag","Kitchen wrap & storage"),
    ("Paper","Cleaning"),("Toilet paper","Cleaning"),("Hand tissue","Cleaning"),
    ("Cleaning cream","Cleaning"),("Dishwasher detergent","Cleaning"),("Manual dishwashing liquid","Cleaning"),
    ("Household vinegar","Cleaning"),("Floor cleaner","Cleaning"),("Trash bag 10l","Cleaning"),
    ("Trash bag 30l","Cleaning"),("Trash bag 50l","Cleaning"),("Sponges","Cleaning"),
    ("Cleaning gloves","Cleaning"),("Oven cleaner","Cleaning"),("Hand soap","Cleaning"),
    ("WC gel","Cleaning"),("Window cleaner","Cleaning"),
]

@app.route("/api/supplies/restock-all", methods=["POST"])
def api_supplies_restock_all():
    """Remet tous les articles à commander (low/out/flaggés) au niveau neutre.
    Réservé admin — après une session d'achats."""
    if not _is_admin():
        return jsonify({"ok": False, "error": "admin only"}), 403
    rows = _supa_get("supplies")
    n = 0
    for r in rows if isinstance(rows, list) else []:
        if r.get("status") in ("low", "out") or r.get("alert"):
            _req.patch(f"{SUPA_URL}/rest/v1/supplies",
                       json={"status": "ok", "alert": False,
                             "updated_at": _utc_iso()},
                       headers=_supa_headers(), params={"id": f"eq.{r['id']}"})
            n += 1
    return jsonify({"ok": True, "reset": n})


@app.route("/api/supplies/seed", methods=["POST"])
def api_supplies_seed():
    """Charge la liste de départ (94 articles) — uniquement si la table est vide."""
    existing = _supa_get("supplies")
    if isinstance(existing, list) and existing:
        return jsonify({"ok": False, "error": "already has items", "count": len(existing)}), 409
    rows = [{"name": n, "category": c, "status": "ok"} for n, c in SUPPLIES_SEED]
    ok, err = _supa_upsert("supplies", rows)   # bulk insert (PostgREST accepte un tableau)
    return jsonify({"ok": ok, "error": err, "count": len(rows) if ok else 0})


# ── Charges fixes CRUD ────────────────────────────────────────────────────────

@app.route("/api/charges", methods=["GET"])
def api_charges_get():
    charges   = _supa_get("charges_fixes",  {"order": "category.asc,name.asc"})
    employees = _supa_get("employees",       {"order": "name.asc"})
    return jsonify({"charges": charges, "employees": employees})

@app.route("/api/charges", methods=["POST"])
def api_charges_post():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    row = {
        "name":      name,
        "amount":    round(float(data.get("amount", 0)), 2),
        "frequency": data.get("frequency", "monthly"),
        "category":  (data.get("category") or "").strip(),
        "notes":     (data.get("notes") or "").strip(),
        "active":    data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("charges_fixes", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/charges/<string:charge_id>", methods=["PATCH"])
def api_charges_patch(charge_id):
    data = request.get_json()
    r = _req.patch(
        f"{SUPA_URL}/rest/v1/charges_fixes",
        json=data,
        headers=_supa_headers(),
        params={"id": f"eq.{charge_id}"},
    )
    return jsonify({"ok": r.ok})

@app.route("/api/charges/<string:charge_id>", methods=["DELETE"])
def api_charges_delete(charge_id):
    ok = _supa_delete("charges_fixes", "id", charge_id)
    return jsonify({"ok": ok})


# ── Employees CRUD ────────────────────────────────────────────────────────────

@app.route("/api/employees", methods=["GET"])
def api_employees_get():
    employees = _supa_get("employees", {"order": "name.asc"})
    return jsonify(employees)

@app.route("/api/employees", methods=["POST"])
def api_employees_post():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    row = {
        "name":             name,
        "type":             data.get("type", "full_time"),
        "gross_monthly":    round(float(data.get("gross_monthly", 0)), 2),
        "hours_week":       float(data.get("hours_week", 40)),
        "tsu_exempt":       bool(data.get("tsu_exempt", False)),
        "meal_card_daily":  round(float(data.get("meal_card_daily", 10.20)), 2),
        "days_per_month":   float(data.get("days_per_month", 21.25)),
        "notes":            (data.get("notes") or "").strip(),
        "active":           data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("employees", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/employees/<string:emp_id>", methods=["PATCH"])
def api_employees_patch(emp_id):
    data = request.get_json()
    r = _req.patch(
        f"{SUPA_URL}/rest/v1/employees",
        json=data,
        headers=_supa_headers(),
        params={"id": f"eq.{emp_id}"},
    )
    return jsonify({"ok": r.ok})

@app.route("/api/employees/<string:emp_id>", methods=["DELETE"])
def api_employees_delete(emp_id):
    ok = _supa_delete("employees", "id", emp_id)
    return jsonify({"ok": ok})


# ── Jours fériés + congés du personnel ────────────────────────────────────────
# Une seule table : employee_id NULL = jour férié (toute l'entreprise),
# employee_id rempli = congé d'un staff précis. type garde l'intention lisible.

@app.route("/holidays")
def holidays_page():
    return render_template("holidays.html")

@app.route("/api/time_off", methods=["GET"])
def api_time_off_get():
    rows = _supa_get("time_off", {"order": "date_from.asc"})
    return jsonify(rows)

@app.route("/api/time_off", methods=["POST"])
def api_time_off_post():
    data = request.get_json()
    date_from = data.get("date_from", "")
    date_to   = data.get("date_to") or date_from
    if not date_from:
        return jsonify({"ok": False, "error": "date_from required"}), 400
    employee_id = data.get("employee_id") or None
    row = {
        "employee_id": employee_id,
        "date_from":   date_from,
        "date_to":     date_to,
        "label":       (data.get("label") or "").strip(),
        "type":        "leave" if employee_id else "holiday",
        "active":      data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("time_off", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/time_off/<string:row_id>", methods=["DELETE"])
def api_time_off_delete(row_id):
    ok = _supa_delete("time_off", "id", row_id)
    return jsonify({"ok": ok})


# ── SOP : procédures & checklists opérationnelles (+ registre HACCP) ───────────
# sop_tasks = définition des tâches (titre, catégorie, fréquence, type).
# sop_log   = complétions (qui, quand, valeur pour les relevés de température).

@app.route("/sop")
def sop_page():
    return render_template("sop.html")

@app.route("/api/sop/tasks", methods=["GET"])
def api_sop_tasks_get():
    rows = _supa_get("sop_tasks", {"order": "sort_order.asc"})
    return jsonify(rows if isinstance(rows, list) else [])

@app.route("/api/sop/tasks", methods=["POST"])
def api_sop_tasks_post():
    data  = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title required"}), 400
    freq = data.get("frequency", "daily")
    if freq not in ("opening", "closing", "daily", "weekly", "monthly"):
        freq = "daily"
    ttype = "temperature" if data.get("type") == "temperature" else "check"
    row = {
        "title":       title,
        "category":    (data.get("category") or "Général").strip(),
        "frequency":   freq,
        "type":        ttype,
        "target_min":  data.get("target_min"),
        "target_max":  data.get("target_max"),
        "unit":        (data.get("unit") or ("°C" if ttype == "temperature" else "")).strip(),
        "sort_order":  int(data.get("sort_order", 100)),
        "notes":       (data.get("notes") or "").strip(),
        "active":      data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("sop_tasks", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/sop/tasks/<string:task_id>", methods=["PATCH"])
def api_sop_tasks_patch(task_id):
    r = _req.patch(f"{SUPA_URL}/rest/v1/sop_tasks", json=request.get_json() or {},
                   headers=_supa_headers(), params={"id": f"eq.{task_id}"})
    return jsonify({"ok": r.ok})

@app.route("/api/sop/tasks/<string:task_id>", methods=["DELETE"])
def api_sop_tasks_delete(task_id):
    ok = _supa_delete("sop_tasks", "id", task_id)
    return jsonify({"ok": ok})

@app.route("/api/sop/log", methods=["GET"])
def api_sop_log_get():
    # ?since=YYYY-MM-DD (défaut : 30 derniers jours) pour l'historique/export
    since = request.args.get("since") or (today_lisbon() - timedelta(30)).isoformat()
    rows = _supa_get("sop_log", {"date": f"gte.{since}", "order": "done_at.desc"})
    return jsonify(rows if isinstance(rows, list) else [])

@app.route("/api/sop/log", methods=["POST"])
def api_sop_log_post():
    data    = request.get_json() or {}
    task_id = data.get("task_id")
    if not task_id:
        return jsonify({"ok": False, "error": "task_id required"}), 400
    row = {
        "task_id": task_id,
        "date":    data.get("date") or today_lisbon().isoformat(),
        "done_by": (data.get("done_by") or "").strip(),
        "value":   data.get("value"),
        "done_at": _utc_iso(),
        "active":  True,
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("sop_log", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/sop/log/<string:log_id>", methods=["DELETE"])
def api_sop_log_delete(log_id):
    ok = _supa_delete("sop_log", "id", log_id)
    return jsonify({"ok": ok})


# ── Events / pop-ups (calendrier, tâches, notes) ─────────────────────────────
@app.route("/events")
def events_page():
    return render_template("events.html")

@app.route("/api/events", methods=["GET"])
def api_events_get():
    rows = _supa_get("events", {"active": "eq.true", "order": "date.asc"})
    return jsonify(rows if isinstance(rows, list) else [])

@app.route("/api/events", methods=["POST"])
def api_events_post():
    data  = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title required"}), 400
    if not data.get("date"):
        return jsonify({"ok": False, "error": "date required"}), 400
    status = data.get("status", "planned")
    if status not in ("planned", "confirmed", "done", "cancelled"):
        status = "planned"
    row = {
        "title":       title,
        "date":        data["date"],
        "end_date":    data.get("end_date") or None,
        "start_time":  (data.get("start_time") or "").strip() or None,
        "end_time":    (data.get("end_time") or "").strip() or None,
        "location":    (data.get("location") or "").strip(),
        "status":      status,
        "description": (data.get("description") or "").strip(),
        "color":       (data.get("color") or "#2554C7").strip(),
        "series_id":   data.get("series_id"),
        "active":      data.get("active", True),
        "updated_at":  _utc_iso(),
    }
    if "notes" in data:
        row["notes"] = data["notes"]
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("events", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/events/<string:event_id>", methods=["PATCH"])
def api_events_patch(event_id):
    data = request.get_json() or {}
    data["updated_at"] = _utc_iso()
    r = _req.patch(f"{SUPA_URL}/rest/v1/events", json=data,
                   headers=_supa_headers(), params={"id": f"eq.{event_id}"})
    return jsonify({"ok": r.ok})

@app.route("/api/events/<string:event_id>", methods=["DELETE"])
def api_events_delete(event_id):
    ok = _supa_delete("events", "id", event_id)
    return jsonify({"ok": ok})

@app.route("/api/events/tasks", methods=["GET"])
def api_event_tasks_get():
    params = {"order": "sort_order.asc"}
    eid = request.args.get("event_id")
    if eid:
        params["event_id"] = f"eq.{eid}"
    rows = _supa_get("event_tasks", params)
    return jsonify(rows if isinstance(rows, list) else [])

@app.route("/api/events/tasks", methods=["POST"])
def api_event_tasks_post():
    data = request.get_json() or {}
    if not data.get("event_id") or not (data.get("label") or "").strip():
        return jsonify({"ok": False, "error": "event_id + label required"}), 400
    row = {
        "event_id":   data["event_id"],
        "label":      data["label"].strip(),
        "done":       bool(data.get("done", False)),
        "done_at":    data.get("done_at"),
        "sort_order": int(data.get("sort_order", 100)),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("event_tasks", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/events/tasks/<string:task_id>", methods=["PATCH"])
def api_event_tasks_patch(task_id):
    r = _req.patch(f"{SUPA_URL}/rest/v1/event_tasks", json=request.get_json() or {},
                   headers=_supa_headers(), params={"id": f"eq.{task_id}"})
    return jsonify({"ok": r.ok})

@app.route("/api/events/tasks/<string:task_id>", methods=["DELETE"])
def api_event_tasks_delete(task_id):
    ok = _supa_delete("event_tasks", "id", task_id)
    return jsonify({"ok": ok})


# ── Réconciliation Revolut ↔ Vendus ──────────────────────────────────────────
# Le terminal Revolut encaisse brut + tips − fees ; Vendus facture le montant
# certifié AT sans tips. Cet endpoint fournit le côté Vendus par jour (total +
# répartition par moyen de paiement) ; le relevé Revolut est parsé côté client.

@app.route("/reconciliation")
def reconciliation_page():
    return render_template("reconciliation.html")

@app.route("/api/reconciliation")
def api_reconciliation():
    month = request.args.get("month", "")
    try:
        y, m = month.split("-")
        y, m = int(y), int(m)
        from_d = date(y, m, 1)
    except Exception:
        return jsonify({"error": "month must be YYYY-MM"}), 400
    last = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(1)
    to_d = min(last, today_lisbon())
    if from_d > today_lisbon():
        return jsonify({"month": month, "days": [], "payment_titles": []})

    # Relevés Revolut pré-injectés (historique figé mai→juillet) — évite de
    # recoller le CSV à chaque fois. Écrasé par un collage manuel si présent.
    revolut = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "revolut_data.json")) as f:
            revolut = json.load(f).get(month, {})
    except Exception:
        pass

    docs = get_documents(from_d.isoformat(), to_d.isoformat(), detailed=True)
    days, titles = {}, set()
    for d in docs:
        day = (d.get("date") or d.get("local_time", ""))[:10]
        if not day:
            continue
        rec = days.setdefault(day, {"total": 0.0, "payments": {}})
        rec["total"] += float(d.get("amount_gross") or 0)
        for p in d.get("payments", []):
            t = p.get("title") or "Autre"
            titles.add(t)
            rec["payments"][t] = rec["payments"].get(t, 0.0) + float(p.get("amount") or 0)

    out = [{"date": k,
            "total": round(v["total"], 2),
            "payments": {t: round(a, 2) for t, a in v["payments"].items()}}
           for k, v in sorted(days.items())]
    return jsonify({"month": month, "days": out, "payment_titles": sorted(titles),
                    "revolut": revolut})

@app.route("/api/cash")
def api_cash():
    """Espèces (Dinheiro) facturées dans Vendus, par jour depuis l'ouverture.
    = cash théorique en caisse, avant sorties/dépôts (que Vendus ne voit pas)."""
    OPEN_DATE = date(2026, 5, 27)
    docs = get_documents(OPEN_DATE.isoformat(), today_lisbon().isoformat(), detailed=True)
    days = {}
    for d in docs:
        day = (d.get("date") or d.get("local_time", ""))[:10]
        if not day:
            continue
        for p in d.get("payments", []):
            title = (p.get("title") or "").lower()
            if "dinheiro" in title or "cash" in title:
                days[day] = days.get(day, 0.0) + float(p.get("amount") or 0)
    out = [{"date": k, "cash": round(v, 2)} for k, v in sorted(days.items()) if abs(v) >= 0.005]
    return jsonify({"since": OPEN_DATE.isoformat(),
                    "days": out,
                    "total": round(sum(d["cash"] for d in out), 2)})


# ── Expenses (dépenses réelles, avec justificatif Google Drive) ───────────────

@app.route("/api/expenses", methods=["GET"])
def api_expenses_get():
    rows = _supa_get("expenses", {"order": "date.desc"})
    return jsonify(rows if isinstance(rows, list) else [])

@app.route("/api/expenses", methods=["POST"])
def api_expenses_post():
    data     = request.get_json() or {}
    supplier = (data.get("supplier") or "").strip()
    if not supplier:
        return jsonify({"ok": False, "error": "supplier required"}), 400
    if not data.get("date"):
        return jsonify({"ok": False, "error": "date required"}), 400
    row = {
        "date":        data["date"],
        "supplier":    supplier,
        "label":       (data.get("label") or "").strip(),
        "amount":      round(float(data.get("amount", 0)), 2),
        "category":    data.get("category", "other"),
        "account":     data.get("account", "Revolut Business"),
        "has_invoice": bool(data.get("has_invoice", False)),
        "notes":       (data.get("notes") or "").strip(),
        "active":      data.get("active", True),
    }
    if data.get("id"):
        row["id"] = data["id"]
    ok, err = _supa_upsert("expenses", row)
    return jsonify({"ok": ok, "error": err})

@app.route("/api/expenses/<string:eid>", methods=["PATCH"])
def api_expenses_patch(eid):
    data = request.get_json() or {}
    r = _req.patch(f"{SUPA_URL}/rest/v1/expenses", json=data,
                   headers=_supa_headers(), params={"id": f"eq.{eid}"})
    return jsonify({"ok": r.ok})

@app.route("/api/expenses/<string:eid>", methods=["DELETE"])
def api_expenses_delete(eid):
    ok = _supa_delete("expenses", "id", eid)
    return jsonify({"ok": ok})

@app.route("/api/expenses/bulk", methods=["POST"])
def api_expenses_bulk():
    """Import en masse (relevé bancaire collé/parsé côté client).
    Body: {"rows": [{date, supplier, amount, category, has_invoice, label}, ...]}"""
    data = request.get_json() or {}
    raw_rows = data.get("rows") or []
    if not isinstance(raw_rows, list) or not raw_rows:
        return jsonify({"ok": False, "error": "rows required"}), 400
    rows = []
    for r in raw_rows:
        supplier = (r.get("supplier") or "").strip()
        if not supplier or not r.get("date"):
            continue
        rows.append({
            "date":        r["date"],
            "supplier":    supplier,
            "label":       (r.get("label") or "").strip(),
            "amount":      round(abs(float(r.get("amount", 0))), 2),
            "category":    r.get("category", "other"),
            "account":     r.get("account", "Revolut Business"),
            "has_invoice": bool(r.get("has_invoice", False)),
            "active":      True,
        })
    if not rows:
        return jsonify({"ok": False, "error": "no valid rows"}), 400
    ok, err = _supa_upsert("expenses", rows)   # POST avec tableau = insert en masse
    return jsonify({"ok": ok, "error": err, "count": len(rows) if ok else 0})


# ── Supabase ──────────────────────────────────────────────────────────────────
import requests as _req

SUPA_URL = os.environ.get("SUPABASE_URL", "")
SUPA_KEY = os.environ.get("SUPABASE_KEY", "")

def _supa_headers(prefer=None):
    h = {
        "apikey":        SUPA_KEY,
        "Authorization": f"Bearer {SUPA_KEY}",
        "Content-Type":  "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h

def _supa_get(table, params=None):
    r = _req.get(f"{SUPA_URL}/rest/v1/{table}", headers=_supa_headers(), params=params)
    return r.json() if r.ok else []

def _supa_upsert(table, data):
    r = _req.post(f"{SUPA_URL}/rest/v1/{table}", json=data,
                  headers=_supa_headers("resolution=merge-duplicates"))
    if r.ok:
        return True, None
    try:
        msg = r.json().get("message") or r.json().get("error") or r.text
    except Exception:
        msg = r.text
    return False, msg

def _supa_delete(table, col, val):
    r = _req.delete(f"{SUPA_URL}/rest/v1/{table}",
                    headers=_supa_headers(),
                    params={col: f"eq.{val}"})
    return r.ok

# ── Helpers lecture / écriture (abstraction Supabase) ─────────────────────────
def _load_ingredients():
    rows = _supa_get("ingredients")
    return {r["name"]: {k: v for k, v in r.items() if k != "name"} for r in rows}

def _load_recipes():
    rows = _supa_get("recipes")
    # Strip trailing/leading spaces from keys so Vendus title mismatches (e.g. "Croissant ") still match
    return {r["product_title"].strip(): {"ingredients": r["ingredients"],
                                         "notes": r.get("notes", ""),
                                         "waste_pct": r.get("waste_pct") or 0}
            for r in rows}

def _save_ingredient(name, data):
    # Historique des prix : trace un changement de prix avant l'upsert (best-effort,
    # jamais bloquant). Table ingredient_price_history — voir /tmp/cogs_p3_setup.sql.
    try:
        new_price = data.get("price")
        if new_price is not None:
            existing = _supa_get("ingredients", {"name": f"eq.{name}", "select": "price,unit_ref"})
            old = existing[0] if isinstance(existing, list) and existing else None
            if not old or abs(float(old.get("price") or 0) - float(new_price)) > 1e-9:
                _supa_upsert("ingredient_price_history", {
                    "name": name, "price": round(float(new_price), 4),
                    "unit_ref": data.get("unit_ref") or (old or {}).get("unit_ref") or "",
                })
    except Exception:
        pass
    row = {"name": name, **data}
    ok, err = _supa_upsert("ingredients", row)
    # Tolérance migration : colonne 'supplier' pas encore créée → réessaie sans.
    if not ok and err and "supplier" in str(err):
        row.pop("supplier", None)
        ok, _ = _supa_upsert("ingredients", row)
    return ok

def _save_recipe(title, ingredients, notes, waste_pct=0):
    row = {"product_title": title, "ingredients": ingredients, "notes": notes,
           "waste_pct": round(float(waste_pct or 0), 2)}
    ok, err = _supa_upsert("recipes", row)
    # Tolérance migration : si la colonne waste_pct n'existe pas encore côté
    # Supabase (SQL non exécuté), on réessaie sans elle plutôt que de perdre la
    # sauvegarde de la recette.
    if not ok and err and "waste_pct" in str(err):
        row.pop("waste_pct", None)
        ok, _ = _supa_upsert("recipes", row)
    return ok

# ── Cache daily_summary ───────────────────────────────────────────────────────
# Les journées passées ne changent plus : leurs agrégats item-level (COGS,
# produits, upsell) sont calculés une fois et stockés dans Supabase.
# Seul aujourd'hui est recalculé en live.

def _fetch_summaries(from_iso, to_iso):
    rows = _req.get(f"{SUPA_URL}/rest/v1/daily_summary", headers=_supa_headers(),
                    params=[("day", f"gte.{from_iso}"), ("day", f"lte.{to_iso}"),
                            ("order", "day.asc")])
    return rows.json() if rows.ok else []

def _get_summaries(from_iso, to_iso):
    """Lecture du cache journalier, mutualisée sur la durée de la requête HTTP.

    /api/data lit daily_summary 5 fois sur des plages qui se recoupent (période,
    14 jours, mois, comparaison, historique). Comme tout l'historique tient en
    quelques dizaines de lignes, on le charge UNE fois par requête puis on
    découpe en mémoire — 5 allers-retours Supabase séquentiels → 1.
    """
    try:
        store = g._summaries_all
    except (AttributeError, RuntimeError):
        store = None
        try:
            store = {r["day"]: r for r in _fetch_summaries(OPENING_DAY, today_lisbon().isoformat())}
            g._summaries_all = store
        except RuntimeError:
            pass          # hors contexte de requête (cron, script) → pas de mémo
    if store is None:
        return _fetch_summaries(from_iso, to_iso)
    return [store[d] for d in sorted(store) if from_iso <= d <= to_iso]

def _summaries_cache_put(day_iso, row):
    """Garde le mémo de requête cohérent après construction d'un jour manquant."""
    try:
        g._summaries_all[day_iso] = row
    except (AttributeError, RuntimeError):
        pass

def _summarize_docs_items(docs, catalog):
    """Agrégats item-level d'une liste de docs avec items (1 journée)."""
    cogs = covered = items_ht = 0.0
    multi = 0
    products = {}
    for d in docs:
        its = d.get("items", [])
        if len(its) >= 2 and not d.get("_refund"):
            multi += 1
        for item in its:
            name = item.get("title", "").strip()
            qty  = float(item.get("qty", 0))
            am   = item.get("amounts", {})
            net  = float(am.get("net_total", 0))
            grs  = float(am.get("gross_total", 0))
            items_ht += net
            p = products.setdefault(name, {"qty": 0, "rev_ttc": 0.0, "rev_ht": 0.0})
            p["qty"]     += qty
            p["rev_ttc"] += grs
            p["rev_ht"]  += net
            c = catalog.get(name, {})
            if c.get("cost"):
                cogs    += c["cost"] * qty
                covered += net
    return {
        "nb":          sum(1 for d in docs if not d.get("_refund")),   # avoirs ≠ ventes
        "ca_ttc":      round(sum(float(d.get("amount_gross", 0)) for d in docs), 2),
        "ca_ht":       round(sum(float(d.get("amount_net",   0)) for d in docs), 2),
        "cogs_ht":     round(cogs, 2),
        "covered_ht":  round(covered, 2),
        "items_ht":    round(items_ht, 2),
        "multi_count": multi,
        "products":    {k: {"qty": v["qty"], "rev_ttc": round(v["rev_ttc"], 2),
                            "rev_ht": round(v["rev_ht"], 2)} for k, v in products.items()},
    }

def _upsert_summary(day_iso, summary):
    _supa_upsert("daily_summary", {"day": day_iso, **summary})

def _audit_summaries(cache_rows, vendus_by_day, from_date, to_date, tol=0.01):
    """
    Rapproche le cache `daily_summary` et Vendus, jour par jour. NE MODIFIE RIEN.

    Sert à retrouver les journées figées à mi-parcours par l'ancien défaut de `/api/cashflow`,
    qui écrivait le jour courant dans le cache — définitivement, puisqu'on ne reconstruit que
    les jours manquants.

    `vendus_by_day` : {jour_iso: {"ca_ttc": float, "nb": int}}, calculé avec EXACTEMENT la même
    sémantique que `_summarize_docs_items` — les avoirs sont négativés dans le CA et exclus du
    compte de tickets. Sans quoi le rapprochement signalerait des écarts qui n'en sont pas.

    Quatre verdicts, parce que quatre causes distinctes :
      · `partiel`      cache < Vendus — la signature du jour figé en cours de journée ;
      · `excedentaire` cache > Vendus — un avoir émis après coup, ou une reconstruction ratée ;
      · `manquant`     Vendus a des ventes, le cache n'a pas de ligne ;
      · `fantome`      le cache a des ventes, Vendus n'en a aucune.
    Un jour sans vente des deux côtés n'est pas un écart et n'apparaît pas.
    """
    by_day = {r["day"]: r for r in cache_rows if r.get("day")}
    ecarts = []
    cur = from_date
    while cur <= to_date:
        iso = cur.isoformat()
        cur += timedelta(1)
        v = vendus_by_day.get(iso)
        c = by_day.get(iso)
        v_ca, v_nb = (float(v["ca_ttc"]), int(v["nb"])) if v else (0.0, 0)
        if c is None:
            if v_nb or abs(v_ca) > tol:
                ecarts.append({"day": iso, "verdict": "manquant", "cache_ca_ttc": None,
                               "vendus_ca_ttc": round(v_ca, 2), "ecart_ca": round(v_ca, 2),
                               "cache_nb": None, "vendus_nb": v_nb})
            continue
        c_ca, c_nb = float(c.get("ca_ttc") or 0), int(c.get("nb") or 0)
        d_ca = round(v_ca - c_ca, 2)
        if abs(d_ca) <= tol and c_nb == v_nb:
            continue
        if c_nb == 0 and abs(c_ca) <= tol:
            verdict = "manquant"
        elif v_nb == 0 and abs(v_ca) <= tol:
            verdict = "fantome"
        else:
            verdict = "partiel" if d_ca > 0 else "excedentaire"
        ecarts.append({"day": iso, "verdict": verdict,
                       "cache_ca_ttc": round(c_ca, 2), "vendus_ca_ttc": round(v_ca, 2),
                       "ecart_ca": d_ca, "cache_nb": c_nb, "vendus_nb": v_nb})
    return ecarts


def _tx_per_open_day(period_rows, from_date, to_date, today_real):
    """
    Tickets par JOUR OUVRÉ sur la période — sur les jours PLEINS uniquement.

    ⚠️ LE JOUR COURANT EST EXCLU DES DEUX CÔTÉS. La version précédente (côté client) divisait
    un total incluant aujourd'hui par un nombre de jours ouvrés incluant aussi aujourd'hui.
    Consulté un vendredi matin sur « cette semaine », le dénominateur comptait un jour entier
    face à trois tickets : la moyenne tombait d'environ un tiers, et remontait toute seule au
    fil de la journée. Un chiffre qui bouge sans que rien ne se passe n'est pas une moyenne.

    ⚠️ ON N'UTILISE PAS `economics.open_days`. Celui-là inclut aujourd'hui et surtout il est
    plafonné à ≥ 1 (`count_open_days`, config.py) pour éviter les divisions par zéro — ce qui
    transformerait « aucun jour ouvré plein » en « un jour ». Ici on veut pouvoir répondre
    « on ne sait pas » : `count_open_days_raw` peut rendre 0, et on renvoie alors None.

    Les jours ouverts hors calendrier (un mardi d'événement privé) sont comptés au dénominateur
    dès qu'ils portent des tickets : sinon leur chiffre d'affaires gonflerait le numérateur sans
    que personne ne les compte comme journée travaillée.
    """
    from config import count_open_days_raw, OPEN_WEEKDAYS

    full_end = min(to_date, today_real - timedelta(1))
    if from_date > full_end:
        return {"tx_per_open_day": None, "tx_basis_days": 0,
                "tx_basis_reason": "aucun jour plein dans la période"}

    today_iso = today_real.isoformat()
    full_rows = [r for r in period_rows
                 if r.get("day") and r["day"] != today_iso and r["day"] <= full_end.isoformat()]

    basis = count_open_days_raw(from_date, full_end)
    for r in full_rows:
        d = date.fromisoformat(r["day"])
        if float(r.get("nb") or 0) > 0 and d.weekday() not in OPEN_WEEKDAYS:
            basis += 1                      # journée travaillée hors calendrier

    if basis <= 0:
        return {"tx_per_open_day": None, "tx_basis_days": 0,
                "tx_basis_reason": "aucun jour ouvré plein dans la période"}

    total = sum(float(r.get("nb") or 0) for r in full_rows)
    return {"tx_per_open_day": round(total / basis, 1),
            "tx_basis_days": basis, "tx_basis_reason": None}


def _ensure_summaries(from_date, to_date, catalog):
    """
    Retourne les summaries [from..to] (JOURS PASSÉS), en construisant les manquants.

    ⚠️ NE FIGE JAMAIS LE JOUR COURANT. La docstring l'a toujours dit, rien ne le garantissait :
    seul `/api/data` se bornait lui-même à hier. `/api/cashflow` passait `date.today()`, si bien
    qu'ouvrir l'onglet Trésorerie à 9h30 écrivait une ligne `daily_summary` figée à 9h30 — et
    comme on ne reconstruit que les jours MANQUANTS, elle n'était plus jamais corrigée.

    Un tel jour partiel contamine ensuite tout ce qui lit le cache : comparaison hebdomadaire,
    sparkline, série EBITDA du mois, meilleur jour de la semaine. La garde vit ici, au niveau
    de l'écriture, et pas chez les appelants — c'est la seule place où elle ne peut pas être
    oubliée par le prochain.

    Les appelants qui ont besoin du jour courant l'ajoutent en mémoire, sans l'écrire.
    """
    from vendus import get_documents_with_items
    to_date = min(to_date, date.today() - timedelta(1))
    if from_date > to_date:
        return []
    from_iso, to_iso = from_date.isoformat(), to_date.isoformat()
    rows = _get_summaries(from_iso, to_iso)
    have = {r["day"] for r in rows}
    all_days = []
    cur = from_date
    while cur <= to_date:
        all_days.append(cur.isoformat())
        cur += timedelta(1)
    missing = [d for d in all_days if d not in have]
    if missing and catalog:   # sans catalogue, on ne fige pas de COGS à zéro
        docs = get_documents_with_items(min(missing), max(missing))
        by_day = {}
        for doc in docs:
            day = (doc.get("date") or doc.get("local_time", ""))[:10]
            by_day.setdefault(day, []).append(doc)
        for day in missing:
            s = _summarize_docs_items(by_day.get(day, []), catalog)
            _upsert_summary(day, s)
            row = {"day": day, **s}
            rows.append(row)
            _summaries_cache_put(day, row)   # cohérence du mémo de requête
    rows.sort(key=lambda r: r["day"])
    return rows

def _merge_products(summary_rows):
    """Fusionne les dicts products de plusieurs jours → {name: {qty, rev, days}}."""
    merged = {}
    for r in summary_rows:
        for name, p in (r.get("products") or {}).items():
            m = merged.setdefault(name, {"qty": 0, "rev_ttc": 0.0, "rev_ht": 0.0, "days": 0})
            m["qty"]     += p["qty"]
            m["rev_ttc"] += p["rev_ttc"]
            m["rev_ht"]  += p["rev_ht"]
            if p["qty"]:
                m["days"] += 1
    return merged

def _products_list(merged, catalog, n=10):
    """Format top_products depuis un dict fusionné."""
    rows = []
    for name, s in merged.items():
        cost = catalog.get(name, {}).get("cost")
        cost_ht = round(cost * s["qty"], 2) if cost else None
        rev_ht  = round(s["rev_ht"], 2)
        margin  = round((rev_ht - cost_ht) / rev_ht * 100, 1) if rev_ht and cost_ht else None
        rows.append({
            "name": name, "qty": int(s["qty"]),
            "revenue": round(s["rev_ttc"], 2), "rev_ht": rev_ht,
            "avg": round(s["rev_ttc"] / s["qty"], 2) if s["qty"] else 0,
            "cost_ht": cost_ht, "margin_pct": margin,
            "days_sold": s.get("days", 0),
            "avg_day": round(s["rev_ttc"] / s["days"], 2) if s.get("days") else 0,
        })
    rows.sort(key=lambda x: x["qty"], reverse=True)
    return rows[:n] if n else rows

def _upsell_from_rows(rows):
    total = sum(r.get("nb", 0) for r in rows)
    multi = sum(r.get("multi_count", 0) for r in rows)
    return {"rate": round(multi / total * 100) if total else 0,
            "multi": multi, "single": total - multi, "total": total}

# Mots-clés de nom de catégorie → groupe du mix. Résolu par NOM (pas par id) :
# les ids Vendus changent dès qu'une catégorie est supprimée/recréée ou que
# les catégories sont réorganisées (ex. fusion de toute la nourriture en une
# seule catégorie "FOOD"). Ordre = du plus spécifique au plus générique.
_MIX_KEYWORDS = [
    ("Retail",       ("retail", "livre", "book", "papeterie", "paper", "stationery")),
    ("Viennoiserie", ("viennoiserie", "pastry bought", "boulangerie")),
    ("Food",         ("food", "pâtisserie", "patisserie", "brunch", "sandwich",
                       "granola", "extra", "snack")),
    ("Drinks",       ("boisson", "drink", "coffee", "café", "espresso", "tea",
                       "thé", "matcha", "cold", "iced", "filter", "filtre", "non-coffee")),
]

def _group_for_category(cat_name):
    low = (cat_name or "").strip().lower()
    for label, keywords in _MIX_KEYWORDS:
        if any(k in low for k in keywords):
            return label
    return "Retail"   # non catégorisé / catégorie inconnue


def _mix_from_merged(merged, catalog):
    """Mix CA + rentabilité par groupe (Drinks / Food / Viennoiserie / Retail).
    Viennoiserie (achetée) séparée du Food — marges très différentes.
    Retail = Livres, Papeterie, café en sac et tout produit non catégorisé.
    Groupe résolu par NOM de catégorie Vendus (voir _group_for_category) —
    robuste aux changements de catégories, contrairement à un mapping par id.
    Marge calculée sur les produits dont le coût est connu (couverture affichée)."""
    # Viennoiserie achetée identifiée par NOM DE PRODUIT (prioritaire sur la
    # catégorie — ex. rangée dans "Food" à côté des cookies/clafoutis maison).
    VIENNOISERIE_NAMES = ("croissant", "pain au chocolat", "pain au choco")
    # Overrides par nom : la catégorie Vendus "POPUP" mélange food et boissons,
    # non reconnue par les mots-clés (tombait en Retail par défaut). Reclassé ici.
    NAME_TO_GROUP = {"madeleine": "Food"}
    NAME_PREFIX_TO_GROUP = {"mus": "Drinks", "rou": "Drinks", "sov": "Drinks", "pro": "Drinks"}

    def _bucket_for(name, cat_name):
        low = name.lower()
        if any(k in low for k in VIENNOISERIE_NAMES):
            return "Viennoiserie"
        for key, grp in NAME_TO_GROUP.items():
            if key in low:
                return grp
        first = low.split()[0] if low.split() else low
        first = first.split("-")[0]                 # "SOV-1" → "sov"
        if first in NAME_PREFIX_TO_GROUP:
            return NAME_PREFIX_TO_GROUP[first]
        return _group_for_category(cat_name)

    groups = {k: {"rev_ht": 0.0, "rev_ttc": 0.0, "cogs": 0.0, "covered": 0.0}
              for k in ("Drinks", "Food", "Viennoiserie", "Retail")}
    for name, s in merged.items():
        cat_name = catalog.get(name, {}).get("category_name")
        g = groups[_bucket_for(name, cat_name)]
        g["rev_ht"]  += s["rev_ht"]
        g["rev_ttc"] += s["rev_ttc"]
        cost = catalog.get(name, {}).get("cost")
        if cost:
            g["cogs"]    += cost * s["qty"]
            g["covered"] += s["rev_ht"]
    grand = sum(g["rev_ht"] for g in groups.values()) or 1
    out = []
    for label, g in groups.items():
        if g["rev_ht"] <= 0:
            continue
        marge_pct = round((g["covered"] - g["cogs"]) / g["covered"] * 100, 1) if g["covered"] > 0 else None
        out.append({
            "label":      label,
            "amount":     round(g["rev_ht"], 2),
            "amount_ttc": round(g["rev_ttc"], 2),
            "pct":        round(g["rev_ht"] / grand * 100, 1),
            "cogs":       round(g["cogs"], 2),
            "marge_pct":  marge_pct,
            "marge_eur":  round(g["rev_ht"] * marge_pct / 100, 2) if marge_pct is not None else None,
            "coverage":   round(g["covered"] / g["rev_ht"] * 100) if g["rev_ht"] else None,
        })
    return out


def _load_preparations():
    rows = _supa_get("preparations")
    return {r["name"]: r for r in rows}

def _save_preparation(name, ingredients, yield_qty, yield_unit, notes, category=""):
    row = {
        "name": name, "ingredients": ingredients,
        "yield_qty": yield_qty, "yield_unit": yield_unit, "notes": notes,
        "category": category,
    }
    ok, err = _supa_upsert("preparations", row)
    # Tolérance migration : colonne 'category' pas encore créée → réessaie sans.
    if not ok and err and "category" in str(err):
        row.pop("category", None)
        ok, err = _supa_upsert("preparations", row)
    return ok, err

# ── Calcul COGS depuis une recette ────────────────────────────────────────────
UNIT_CONVERSIONS = {
    # (unit, unit_ref) → factor pour obtenir le coût
    ("g",    "kg"):   0.001,
    ("mg",   "kg"):   0.000001,
    ("kg",   "kg"):   1.0,
    ("ml",   "l"):    0.001,
    ("cl",   "l"):    0.01,
    ("dl",   "l"):    0.1,
    ("l",    "l"):    1.0,
    ("unit", "unit"): 1.0,
}

# ── Ligne de recette → RENDEMENT d'une préparation ────────────────────────────
#
# UNIT_CONVERSIONS ci-dessus ne sert qu'à ramener une ligne vers l'unité de RÉFÉRENCE d'un
# ingrédient (kg / l / unit). Elle ne connaît ni ml→ml, ni g→g, et n'était de toute façon
# jamais consultée quand la ligne désigne une PRÉPARATION : la quantité était divisée telle
# quelle par yield_qty. Une recette consommant « 200 ml » d'une préparation qui rend « 1 l »
# donnait donc 200 batches au lieu de 0,2 — un facteur 1000 sur le coût.
#
# Le même défaut existait aux trois endroits qui divisent par un rendement : le moteur de coût
# ci-dessous, la consommation théorique (/api/inventory/usage) et l'aperçu d'impact prix côté
# client. Ils étaient donc d'accord entre eux, et faux ensemble.
#
# ⚠️ ON NE DEVINE PAS. Quand les deux unités ne sont pas comparables (« portion » face à
# « ml »), le comportement historique est CONSERVÉ — facteur 1 — et signalé. Deviner ferait
# bouger des coûts que personne n'a demandé à voir bouger ; se taire laisserait le nombre
# passer pour exact.
_UNIT_BASE = {
    "mg": ("masse",  0.001), "g":  ("masse",  1.0), "kg": ("masse", 1000.0),
    "ml": ("volume", 1.0),   "cl": ("volume", 10.0),
    "dl": ("volume", 100.0), "l":  ("volume", 1000.0),
    "unit": ("compte", 1.0), "portion": ("compte", 1.0),
}

def prep_yield_factor(line_unit, yield_unit):
    """
    Combien d'unités de rendement vaut UNE unité de ligne. Renvoie (facteur, alerte|None).

    ⚠️ Les deux `.get` sont testés séparément. Dans Mesa, la même fonction comparait les
    dimensions de deux unités inconnues, trouvait `undefined == undefined`, et produisait des
    NaN qui se sont affichés comme coûts sur des recettes réelles.
    """
    lu = (line_unit  or "").strip().lower()
    yu = (yield_unit or "").strip().lower()
    if lu and lu == yu:
        return 1.0, None
    a, b = _UNIT_BASE.get(lu), _UNIT_BASE.get(yu)
    if a is not None and b is not None and a[0] == b[0]:
        return a[1] / b[1], None
    return 1.0, (f"conversion {line_unit or '?'} → {yield_unit or '?'} inconnue "
                 f"— quantité prise telle quelle")


def calc_recipe_cogs(ingredients, ingr_lib, prep_lib=None, waste_pct=0):
    """Calcule le COGS total d'une recette.
    Supporte les préparations (sous-recettes) : si un ingrédient n'est pas dans
    ingr_lib mais dans prep_lib, son coût est calculé en cascade depuis sa propre
    recette (1 niveau de profondeur — pas de nesting infini).

    waste_pct : coulage/perte (%) appliqué au coût matière total (marc, mousse
    jetée, chutes, casse). Le total renvoyé l'inclut ; le breakdown reste au
    coût matière brut par ligne.
    """
    total = 0.0
    breakdown = []
    for ing in ingredients:
        name = ing["name"]
        qty  = float(ing["qty"])
        unit = ing["unit"]

        # ── Cas 1 : ingrédient classique ──────────────────────────────────────
        lib_item = ingr_lib.get(name)
        if lib_item:
            price    = float(lib_item["price"])
            unit_ref = lib_item["unit_ref"]
            factor   = UNIT_CONVERSIONS.get((unit, unit_ref))
            if factor is None:
                breakdown.append({**ing, "cost": None, "error": f"conversion {unit}→{unit_ref} inconnue"})
                continue
            cost = round(qty * factor * price, 5)
            total += cost
            breakdown.append({"name": name, "qty": qty, "unit": unit,
                               "price_ref": price, "unit_ref": unit_ref,
                               "cost": round(cost, 4), "type": "ingredient"})
            continue

        # ── Cas 2 : préparation (sous-recette) ────────────────────────────────
        prep = (prep_lib or {}).get(name)
        if prep:
            prep_total, prep_bd = calc_recipe_cogs(
                prep["ingredients"], ingr_lib, prep_lib=None)  # pas de nesting infini
            yield_qty  = float(prep.get("yield_qty") or 1)
            yield_unit = prep.get("yield_unit", "portion")
            # La ligne peut être libellée dans une autre unité que le rendement (200 ml d'une
            # préparation qui rend 1 l). Sans ce facteur, on payait 1000 fois trop.
            yf, yf_warn = prep_yield_factor(unit, yield_unit)
            cost_per_unit = prep_total / yield_qty if yield_qty else 0
            cost = round(qty * yf * cost_per_unit, 5)
            total += cost
            breakdown.append({
                "name": name, "qty": qty, "unit": unit,
                "cost": round(cost, 4), "type": "preparation",
                "yield_factor": yf,
                **({"warning": yf_warn} if yf_warn else {}),
                "prep_total": round(prep_total, 4),
                "yield_qty": yield_qty,
                "yield_unit": yield_unit,
                "cost_per_unit": round(cost_per_unit, 4),
                "prep_breakdown": prep_bd,
            })
            continue

        # ── Cas 3 : inconnu ───────────────────────────────────────────────────
        breakdown.append({**ing, "cost": None, "error": "ingrédient inconnu"})

    try:
        w = float(waste_pct or 0)
    except (TypeError, ValueError):
        w = 0
    total = total * (1 + w / 100.0)
    return round(total, 4), breakdown

# Fallback si l'API Vendus est injoignable — ne pas utiliser comme source de
# vérité. Les vraies catégories (et leurs ids) sont lues en direct via
# get_categories() : un id supprimé/recréé côté Vendus casse ce mapping figé
# (erreur P005 à la création de produit), d'où la résolution dynamique.
CATEGORY_NAMES_FALLBACK = {
    "343052000": "Espresso",
    "343053226": "Iced drinks",
    "343046110": "Matcha & Tea",
    "343053550": "Filter coffee",
    "343054458": "Viennoiseries",
    "343042919": "Pâtisserie",
    "343055376": "Cold drinks",
    "343055566": "Brunch",
    "343065085": "Sandwiches",
    "343071668": "Livres",
    "343077316": "Papeterie",
    "343052198": "Extras",
    "343079649": "Granola",
    "344420338": "Café retail",
}

CATEGORY_ORDER = [
    "343052000", "343053226", "343053550", "343046110",
    "343054458", "343042919", "343055566", "343065085", "343052198",
    "343055376", "344420338", "343071668", "343077316", "343079649",
]

TAX_RATES = {"NOR": 0.23, "INT": 0.13, "RED": 0.06}


@app.route("/api/debug/categories")
def api_debug_categories():
    """Diagnostic admin : catégories live Vendus + le groupe de mix résolu
    pour chacune. Sert à vérifier/ajuster _group_for_category sans avoir
    besoin de la clé API en dehors de l'app."""
    if not _is_admin():
        return jsonify({"error": "admin only"}), 403
    import vendus as _v
    cats = get_categories()
    rows = [{"id": cid, "name": name, "mix_group": _group_for_category(name)}
            for cid, name in sorted(cats.items(), key=lambda x: x[1])]
    return jsonify({"count": len(rows), "categories": rows,
                     "fetch_error": _v.LAST_CATEGORIES_ERROR})


# ── Usage & variance : consommation théorique d'ingrédients vs achats réels ──
# Théorique = ventes (daily_summary, zéro appel Vendus pour le passé) × recettes
# (préparations développées, coulage inclus). Réel = achats saisis à la main.
# L'écart = sur-dosage / casse / offert / vol — le "theoretical vs actual" F&B.

@app.route("/api/inventory/usage")
def api_inventory_usage():
    today = today_lisbon()
    try:
        from_date = date.fromisoformat(request.args.get("from", ""))
        to_date   = date.fromisoformat(request.args.get("to", ""))
    except ValueError:
        from_date, to_date = today.replace(day=1), today
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    to_date = min(to_date, today)

    catalog = get_catalog() or {}
    past_to = min(to_date, today - timedelta(1))
    rows = _ensure_summaries(from_date, past_to, catalog) if from_date <= past_to else []
    if from_date <= today <= to_date:
        today_docs = _get_today_docs_cached()
        if today_docs:
            rows = rows + [{"day": today.isoformat(), **_summarize_docs_items(today_docs, catalog)}]

    sold = {}
    for r in rows:
        for name, p in (r.get("products") or {}).items():
            sold[name] = sold.get(name, 0) + float(p.get("qty") or 0)

    recipes  = _load_recipes()
    preps    = _load_preparations()
    ingr_lib = _load_ingredients()

    usage      = {}   # name → {qty (unit_ref), cost, sources {product: qty_ref}}
    issues     = []   # lignes non converties / composants inconnus
    uncovered  = []   # produits vendus sans recette

    def _add(ing_name, qty_ref, src_title):
        lib = ingr_lib[ing_name]
        u = usage.setdefault(ing_name, {"unit_ref": lib["unit_ref"], "qty": 0.0,
                                        "cost": 0.0, "sources": {}})
        u["qty"]  += qty_ref
        u["cost"] += qty_ref * float(lib["price"])
        u["sources"][src_title] = u["sources"].get(src_title, 0.0) + qty_ref

    def _expand(line, mult, src_title):
        """mult = nombre de fois que cette ligne est consommée."""
        name = line.get("name"); unit = line.get("unit")
        try:
            lqty = float(line.get("qty") or 0)
        except (TypeError, ValueError):
            return
        if not name or lqty <= 0:
            return
        if name in ingr_lib:
            f = UNIT_CONVERSIONS.get((unit, ingr_lib[name]["unit_ref"]))
            if f is None:
                issues.append(f"{src_title}: {name} — conversion {unit}→{ingr_lib[name]['unit_ref']} inconnue")
                return
            _add(name, lqty * f * mult, src_title)
        elif name in preps:
            p = preps[name]
            yq = float(p.get("yield_qty") or 1) or 1
            # Même conversion que dans le moteur de coût : la ligne peut être libellée dans une
            # autre unité que le rendement. Sans elle, « 200 ml » d'une prep rendant « 1 l »
            # consommait 200 batches d'ingrédients au lieu de 0,2.
            yf, yf_warn = prep_yield_factor(unit, p.get("yield_unit"))
            if yf_warn:
                issues.append(f"{src_title}: {name} — {yf_warn}")
            batch_frac = (lqty * yf * mult) / yq     # fraction de batch consommée
            for l2 in (p.get("ingredients") or []):
                _expand(l2, batch_frac, src_title)
        else:
            issues.append(f"{src_title}: {name} — composant inconnu")

    for title, q in sold.items():
        rec = recipes.get(title)
        if not rec or not rec.get("ingredients"):
            uncovered.append({"title": title, "qty": q})
            continue
        waste_f = 1 + float(rec.get("waste_pct") or 0) / 100.0
        for line in rec["ingredients"]:
            _expand(line, q * waste_f, title)

    out = []
    for name, u in usage.items():
        top = sorted(u["sources"].items(), key=lambda kv: -kv[1])[:5]
        out.append({
            "name": name, "unit_ref": u["unit_ref"],
            "qty":  round(u["qty"], 3), "cost": round(u["cost"], 2),
            "top_sources": [{"title": t, "qty": round(v, 3)} for t, v in top],
        })
    out.sort(key=lambda x: -x["cost"])
    uncovered.sort(key=lambda x: -x["qty"])
    return jsonify({
        "from": from_date.isoformat(), "to": to_date.isoformat(),
        "ingredients": out,
        "uncovered": uncovered[:20],
        "issues": sorted(set(issues))[:20],
    })


@app.route("/api/inventory/purchases", methods=["GET"])
def api_purchases_get():
    params = {"order": "date.desc,id.desc"}
    if request.args.get("from"):
        params["date"] = f"gte.{request.args['from']}"
    rows = _supa_get("inventory_purchases", params)
    rows = rows if isinstance(rows, list) else []
    if request.args.get("to"):
        rows = [r for r in rows if (r.get("date") or "") <= request.args["to"]]
    return jsonify(rows)


@app.route("/api/inventory/purchases", methods=["POST"])
def api_purchases_post():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    try:
        qty = float(data.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    if not name or qty <= 0:
        return jsonify({"ok": False, "error": "name and qty required"}), 400
    row = {
        "name": name, "qty": qty,
        "unit": (data.get("unit") or "unit").strip(),
        "date": data.get("date") or today_lisbon().isoformat(),
        "cost": round(float(data.get("cost") or 0), 2) or None,
        "note": (data.get("note") or "").strip(),
    }
    ok, err = _supa_upsert("inventory_purchases", row)
    return (jsonify({"ok": True}) if ok
            else (jsonify({"ok": False, "error": err}), 502))


@app.route("/api/inventory/purchases/<int:pid>", methods=["DELETE"])
def api_purchases_delete(pid):
    ok = _supa_delete("inventory_purchases", "id", str(pid))
    return jsonify({"ok": ok})


@app.route("/api/cogs")
def api_cogs():
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    BASE     = "https://www.vendus.pt/ws/v1.1"
    r        = req.get(f"{BASE}/products/", auth=(VENDUS_API_KEY, ""), params={"per_page": 200})
    raw      = r.json() if r.ok else []
    recipes  = _load_recipes()
    ingr_lib = _load_ingredients()
    prep_lib = _load_preparations()

    # Catégories réelles depuis Vendus (source de vérité) ; fallback si l'API
    # est injoignable. Ne jamais mélanger les deux : un id supprimé côté
    # Vendus doit disparaître des noms, pas persister via le fallback.
    live_categories = get_categories()
    category_names  = live_categories if live_categories else CATEGORY_NAMES_FALLBACK

    products = []
    for p in raw:
        title     = p.get("title", "")
        cat_id    = str(p.get("category_id") or "")
        tax_id    = p.get("tax_id") or "INT"
        rate      = TAX_RATES.get(tax_id, 0.13)
        prices    = p.get("prices") or []
        price_ttc = float(prices[0].get("price", prices[0].get("gross_price", 0))) if isinstance(prices, list) and prices else 0.0
        price_ht  = round(price_ttc / (1 + rate), 4) if price_ttc else float(p.get("price_without_tax") or 0)
        supply    = float(p.get("supply_price") or 0)

        recipe_data  = recipes.get(title.strip())
        has_recipe   = bool(recipe_data and recipe_data.get("ingredients"))
        recipe_total = None
        breakdown    = []
        waste_pct    = (recipe_data or {}).get("waste_pct") or 0
        if has_recipe:
            recipe_total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib,
                                                       prep_lib, waste_pct=waste_pct)

        effective_cogs = recipe_total if recipe_total is not None else supply
        marge_ht_eff   = round(price_ht - effective_cogs, 4) if price_ht else None
        marge_pct_eff  = round((marge_ht_eff / price_ht * 100), 1) if (marge_ht_eff is not None and price_ht) else None

        products.append({
            "id":           p.get("id"),
            "title":        title,
            "category_id":  cat_id,
            "category":     category_names.get(cat_id, cat_id),
            "tax_rate":     int(rate * 100),
            "price_ttc":    price_ttc,
            "price_ht":     price_ht,
            "supply_price": supply,
            "recipe_total": recipe_total,
            "marge_ht":     marge_ht_eff,
            "marge_pct":    marge_pct_eff,
            "recipe":       breakdown,
            "recipe_notes": (recipe_data or {}).get("notes", ""),
            "waste_pct":    waste_pct,
            "has_recipe":   has_recipe,
        })

    # Ordre d'affichage : ids connus dans l'ordre habituel, puis les catégories
    # live restantes (nouvelles/renommées) triées par nom, en fin de liste.
    known_ids   = [c for c in CATEGORY_ORDER if c in category_names]
    extra_ids   = sorted((c for c in category_names if c not in known_ids),
                         key=lambda c: category_names[c])
    category_order = known_ids + extra_ids

    order_map = {cat: i for i, cat in enumerate(category_order)}
    products.sort(key=lambda p: (order_map.get(p["category_id"], 99), p["title"]))
    preps = _load_preparations()
    ingr_lib2 = ingr_lib  # déjà chargé
    prep_summary = {}
    for pname, p in preps.items():
        total, _ = calc_recipe_cogs(p["ingredients"], ingr_lib2)
        yq = float(p.get("yield_qty") or 1)
        prep_summary[pname] = {
            "yield_qty":   yq,
            "yield_unit":  p.get("yield_unit", "portion"),
            "cost_per_unit": round(total / yq, 4) if yq else 0,
            "notes":       p.get("notes", ""),
            "category":    p.get("category") or "",
        }
    return jsonify({"products": products, "category_order": category_order,
                    "category_names": category_names, "preparations": prep_summary})


@app.route("/api/ingredients", methods=["GET"])
def api_ingredients_get():
    return jsonify(_load_ingredients())


# ── Préparations CRUD ─────────────────────────────────────────────────────────

@app.route("/api/preparations", methods=["GET"])
def api_preparations_get():
    preps    = _load_preparations()
    ingr_lib = _load_ingredients()
    result   = {}
    for name, p in preps.items():
        total, breakdown = calc_recipe_cogs(p["ingredients"], ingr_lib)
        yq = float(p.get("yield_qty") or 1)
        result[name] = {
            **p,
            "total_cogs":    total,
            "cost_per_unit": round(total / yq, 4) if yq else None,
            "breakdown":     breakdown,
        }
    return jsonify(result)

@app.route("/api/preparations", methods=["POST"])
def api_preparations_post():
    data        = request.get_json()
    name        = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    ingredients = data.get("ingredients", [])
    yield_qty   = float(data.get("yield_qty") or 1)
    yield_unit  = (data.get("yield_unit") or "portion").strip()
    notes       = (data.get("notes") or "").strip()
    category    = (data.get("category") or "").strip()
    ingr_lib    = _load_ingredients()
    total, breakdown = calc_recipe_cogs(ingredients, ingr_lib)
    ok, err = _save_preparation(name, ingredients, yield_qty, yield_unit, notes, category)
    return jsonify({"ok": ok, "error": err, "total_cogs": total,
                    "cost_per_unit": round(total / yield_qty, 4) if yield_qty else None,
                    "breakdown": breakdown})

@app.route("/api/preparations/<path:name>", methods=["DELETE"])
def api_preparations_delete(name):
    # Garde-fou : refuser si la préparation est utilisée dans des recettes
    # (sauf si ?force=1) — sinon les recettes afficheraient "ingrédient inconnu"
    if request.args.get("force") != "1":
        used_in = [title for title, r in _load_recipes().items()
                   if any(ing.get("name") == name for ing in r.get("ingredients", []))]
        if used_in:
            return jsonify({"ok": False, "error": "used_in_recipes",
                            "used_in": used_in}), 409
    ok = _supa_delete("preparations", "name", name)
    return jsonify({"ok": ok})


@app.route("/api/ingredients", methods=["POST"])
def api_ingredients_post():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    ingr = {
        "price":    round(float(data.get("price", 0)), 4),
        "unit_ref": data.get("unit_ref", "unit"),
        "category": data.get("category", ""),
        "note":     data.get("note", ""),
        "supplier": data.get("supplier", ""),
    }
    _save_ingredient(name, ingr)
    return jsonify({"ok": True, "ingredient": {name: ingr}})


@app.route("/api/ingredients/<path:name>/history", methods=["GET"])
def api_ingredient_history(name):
    rows = _supa_get("ingredient_price_history",
                     {"name": f"eq.{name}", "order": "changed_at.desc", "limit": "50"})
    return jsonify(rows if isinstance(rows, list) else [])


@app.route("/api/ingredients/<path:name>/rename", methods=["POST"])
def api_ingredient_rename(name):
    """Renomme un ingrédient en cascade : crée la nouvelle clé, met à jour
    toutes les recettes et préparations qui le référencent, puis supprime
    l'ancienne. Le nom est la clé partout — d'où la propagation."""
    data     = request.get_json() or {}
    new_name = (data.get("new_name") or "").strip()
    if not new_name:
        return jsonify({"ok": False, "error": "new_name required"}), 400
    ingr = _load_ingredients()
    if name not in ingr:
        return jsonify({"ok": False, "error": "not found"}), 404
    if new_name == name:
        return jsonify({"ok": True, "recipes": 0, "preparations": 0})
    if new_name in ingr:
        return jsonify({"ok": False, "error": "name_exists"}), 409

    # 1. Nouvelle ligne ingrédient (mêmes données)
    _save_ingredient(new_name, dict(ingr[name]))

    # 2. Recettes qui le référencent
    n_rec = 0
    for title, r in _load_recipes().items():
        ings = r.get("ingredients") or []
        if any(i.get("name") == name for i in ings):
            for i in ings:
                if i.get("name") == name:
                    i["name"] = new_name
            _save_recipe(title, ings, r.get("notes", ""), r.get("waste_pct", 0))
            n_rec += 1

    # 3. Préparations qui le référencent
    n_prep = 0
    for pname, p in _load_preparations().items():
        ings = p.get("ingredients") or []
        if any(i.get("name") == name for i in ings):
            for i in ings:
                if i.get("name") == name:
                    i["name"] = new_name
            _save_preparation(pname, ings, p.get("yield_qty", 1),
                              p.get("yield_unit", "portion"), p.get("notes", ""),
                              p.get("category", ""))
            n_prep += 1

    # 4. Historique prix + achats (best-effort, jamais bloquant)
    for tbl in ("ingredient_price_history", "inventory_purchases"):
        try:
            _req.patch(f"{SUPA_URL}/rest/v1/{tbl}", headers=_supa_headers(),
                       params={"name": f"eq.{name}"}, json={"name": new_name})
        except Exception:
            pass

    # 5. Supprimer l'ancienne clé
    _supa_delete("ingredients", "name", name)
    return jsonify({"ok": True, "recipes": n_rec, "preparations": n_prep})


@app.route("/api/ingredients/<path:name>", methods=["DELETE"])
def api_ingredients_delete(name):
    # Garde-fou : refuser si l'ingrédient est utilisé dans des recettes OU des
    # préparations (sauf ?force=1) — même mécanique que les préparations.
    if request.args.get("force") != "1":
        used_recipes = [title for title, r in _load_recipes().items()
                        if any(i.get("name") == name for i in r.get("ingredients", []))]
        used_preps   = [pname for pname, p in _load_preparations().items()
                        if any(i.get("name") == name for i in p.get("ingredients", []))]
        if used_recipes or used_preps:
            return jsonify({"ok": False, "error": "in_use",
                            "used_in_recipes": used_recipes,
                            "used_in_preparations": used_preps}), 409
    ok = _supa_delete("ingredients", "name", name)
    if not ok:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/recipe/<int:product_id>", methods=["GET"])
def api_recipe_get(product_id):
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    r = req.get(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/", auth=(VENDUS_API_KEY, ""))
    if not r.ok:
        return jsonify({"ok": False, "error": "product not found"}), 404
    title       = r.json().get("title", "").strip()
    recipes     = _load_recipes()
    ingr_lib    = _load_ingredients()
    recipe_data = recipes.get(title, {"ingredients": [], "notes": "", "waste_pct": 0})
    waste = recipe_data.get("waste_pct") or 0
    total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib,
                                        _load_preparations(), waste_pct=waste)
    return jsonify({
        "ok": True, "title": title, "product_id": product_id,
        "ingredients": recipe_data["ingredients"],
        "breakdown":   breakdown,
        "notes":       recipe_data.get("notes", ""),
        "waste_pct":   waste,
        "total_cogs":  total,
    })


@app.route("/api/recipe/<int:product_id>", methods=["POST"])
def api_recipe_post(product_id):
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    data = request.get_json()
    r = req.get(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/", auth=(VENDUS_API_KEY, ""))
    if not r.ok:
        return jsonify({"ok": False, "error": "product not found"}), 404
    title       = r.json().get("title", "").strip()
    ingr_lib    = _load_ingredients()
    ingredients = data.get("ingredients", [])
    notes       = data.get("notes", "")
    waste_pct   = data.get("waste_pct") or 0
    total, breakdown = calc_recipe_cogs(ingredients, ingr_lib, _load_preparations(),
                                        waste_pct=waste_pct)
    _save_recipe(title, ingredients, notes, waste_pct)
    patch_r = req.patch(
        f"https://www.vendus.pt/ws/v1.1/products/{product_id}/",
        auth=(VENDUS_API_KEY, ""),
        json={"supply_price": round(total, 4)},
    )
    return jsonify({
        "ok": True, "title": title, "total_cogs": total,
        "breakdown": breakdown, "vendus_patched": patch_r.ok,
    })


@app.route("/api/recipe/<int:product_id>", methods=["DELETE"])
def api_recipe_delete(product_id):
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    # Récupérer le titre pour trouver la ligne Supabase
    r = req.get(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/", auth=(VENDUS_API_KEY, ""))
    if not r.ok:
        return jsonify({"ok": False, "error": "product not found"}), 404
    title = r.json().get("title", "").strip()
    ok = _supa_delete("recipes", "product_title", title)
    # Remettre supply_price à 0 dans Vendus
    req.patch(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/",
              auth=(VENDUS_API_KEY, ""), json={"supply_price": 0})
    return jsonify({"ok": ok})


@app.route("/api/recipe/recalculate-all", methods=["POST"])
def api_recipe_recalculate_all():
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    recipes  = _load_recipes()
    ingr_lib = _load_ingredients()
    BASE     = "https://www.vendus.pt/ws/v1.1"
    r        = req.get(f"{BASE}/products/", auth=(VENDUS_API_KEY, ""), params={"per_page": 200})
    products = r.json() if r.ok else []
    by_title = {p["title"].strip(): p for p in products}
    results  = []
    for title, recipe_data in recipes.items():
        if not recipe_data.get("ingredients"):
            continue
        prod = by_title.get(title)
        if not prod:
            results.append({"title": title, "status": "not_found_in_vendus"})
            continue
        total, _ = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib, _load_preparations(),
                                    waste_pct=recipe_data.get("waste_pct") or 0)
        pr = req.patch(f"{BASE}/products/{prod['id']}/", auth=(VENDUS_API_KEY, ""),
                       json={"supply_price": round(total, 4)})
        results.append({"title": title, "cogs": total, "status": "ok" if pr.ok else "error"})
    return jsonify({"ok": True, "results": results, "count": len(results)})


@app.route("/api/product/create", methods=["POST"])
def api_product_create():
    """Crée un produit dans Vendus ET sauvegarde sa recette dans Supabase."""
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    data        = request.get_json()
    title       = (data.get("title") or "").strip()
    price_ttc   = float(data.get("price_ttc") or 0)
    tax_id      = data.get("tax_id", "INT")
    category_id = data.get("category_id")
    ingredients = data.get("ingredients", [])
    notes       = data.get("notes", "")
    waste_pct   = data.get("waste_pct") or 0

    if not title or not price_ttc:
        return jsonify({"ok": False, "error": "title et price_ttc requis"}), 400

    ingr_lib          = _load_ingredients()
    total, breakdown  = calc_recipe_cogs(ingredients, ingr_lib, _load_preparations(),
                                         waste_pct=waste_pct)

    # Créer dans Vendus
    payload = {
        "title":       title,
        "prices":      [{"gross_price": str(round(price_ttc, 2))}],
        "tax_id":      tax_id,
        "unit_id":     342853231,   # Uni (défaut)
        "supply_price": round(total, 4),
    }
    if category_id:
        payload["category_id"] = int(category_id)

    r = req.post("https://www.vendus.pt/ws/v1.1/products/",
                 auth=(VENDUS_API_KEY, ""), json=payload)
    if not r.ok:
        return jsonify({"ok": False, "error": r.text}), 502

    product_id = r.json().get("id")

    # Sauvegarder recette dans Supabase
    if ingredients:
        _save_recipe(title, ingredients, notes, waste_pct)

    return jsonify({
        "ok":        True,
        "product_id": product_id,
        "title":     title,
        "total_cogs": total,
        "breakdown": breakdown,
    })


@app.route("/api/product/<int:product_id>/update", methods=["POST"])
def api_product_update(product_id):
    """Met à jour prix TTC et/ou nom d'un produit Vendus."""
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    data    = request.get_json()
    payload = {}
    if "gross_price" in data:
        payload["gross_price"] = str(round(float(data["gross_price"]), 2))
    if "title" in data:
        payload["title"] = data["title"].strip()
    if data.get("category_id"):
        payload["category_id"] = int(data["category_id"])
    if not payload:
        return jsonify({"ok": False, "error": "nothing to update"}), 400
    r = req.patch(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/",
                  auth=(VENDUS_API_KEY, ""), json=payload)
    if r.ok:
        return jsonify({"ok": True, "updated": payload})
    return jsonify({"ok": False, "error": r.text}), 502


@app.route("/api/categories", methods=["POST"])
def api_categories_create():
    """Crée une catégorie produit dans Vendus (source de vérité)."""
    data  = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title required"}), 400
    cat, err = create_category(title)
    if err:
        return jsonify({"ok": False, "error": err}), 502
    return jsonify({"ok": True, "category": cat})


@app.route("/api/update_supply_price/<int:product_id>", methods=["POST"])
def update_supply_price(product_id):
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    data = request.get_json()
    val  = data.get("supply_price")
    if val is None:
        return jsonify({"ok": False, "error": "missing supply_price"}), 400
    r = req.patch(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/",
                  auth=(VENDUS_API_KEY, ""),
                  json={"supply_price": round(float(val), 4)})
    if r.ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": r.text}), 502


if __name__ == "__main__":
    api_key = os.environ.get("VENDUS_API_KEY", "")
    if not api_key:
        print("⚠️  Attention : VENDUS_API_KEY non définie.")
        print("   Lance avec : VENDUS_API_KEY=ta_cle python app.py")
    print("🚀 Dashboard Estudantina → http://localhost:8080")
    app.run(debug=False, host="0.0.0.0", port=8080)
