#!/usr/bin/env python3
"""
Café Estudantina — Dashboard Vendus
Usage:
    pip install flask requests
    VENDUS_API_KEY=votre_cle python app.py
    → ouvre http://localhost:8080
"""

import os
import hmac
import hashlib
from datetime import date, timedelta, datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request, redirect, make_response
from vendus import (
    get_documents, get_documents_with_items, get_balance, get_catalog,
    calc_stats, hourly_breakdown, payment_breakdown, top_products, recent_docs,
    weekly_sparkline, rush_detector, unsold_today, product_stats_from_docs,
    tva_breakdown, service_tempo, upsell_rate, category_mix, ticket_median,
    best_weekday, wow_growth, daily_economics, cumulative_curve, ticket_distribution,
    daily_breakdown,
)

SEUIL_TRANSACTIONS = 40

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
    "today":     "Aujourd'hui",
    "yesterday": "Hier",
    "week":      "Cette semaine",
    "lastweek":  "Semaine dernière",
    "month":     "Ce mois-ci",
    "all":       "Depuis l'ouverture",
}
# Le détail articles des jours passés vient du cache daily_summary (Supabase) ;
# seul le jour courant est détaillé en live via l'API Vendus.

app = Flask(__name__)


# ── Authentification ──────────────────────────────────────────────────────────
# DASHBOARD_PASSWORD non défini → auth désactivée (dev local).
# INVESTOR_PASSWORD (optionnel) → accès lecture seule (GET uniquement).
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
INVESTOR_PASSWORD  = os.environ.get("INVESTOR_PASSWORD", "")
AUTH_SECRET        = os.environ.get("AUTH_SECRET", DASHBOARD_PASSWORD)

def _auth_token(role):
    return hmac.new(AUTH_SECRET.encode(), f"estushop-auth-v1:{role}".encode(),
                    hashlib.sha256).hexdigest()

def _current_role():
    """'admin', 'investor' ou None."""
    cookie = request.cookies.get("estu_auth", "")
    if not cookie:
        return None
    if hmac.compare_digest(cookie, _auth_token("admin")):
        return "admin"
    if INVESTOR_PASSWORD and hmac.compare_digest(cookie, _auth_token("investor")):
        return "investor"
    return None

@app.before_request
def _require_auth():
    if not DASHBOARD_PASSWORD:
        return
    if request.path == "/login" or request.path.startswith("/static/"):
        return
    role = _current_role()
    if role is None:
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect("/login")
    # Investisseur : lecture seule — toute écriture est bloquée
    if role == "investor" and request.method not in ("GET", "HEAD"):
        return jsonify({"error": "lecture seule — accès investisseur"}), 403

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
        if role:
            resp = make_response(redirect("/"))
            resp.set_cookie("estu_auth", _auth_token(role),
                            max_age=30*24*3600, httponly=True,
                            secure=True, samesite="Lax")
            return resp
        error = "Mot de passe incorrect"
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estudantina — Connexion</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
body {{ font-family:'Inter',sans-serif; background:#faf9f5; display:flex; align-items:center;
       justify-content:center; height:100vh; margin:0; color:#37352f; }}
.box {{ background:#fff; border:1px solid #e8e6e0; border-radius:12px; padding:40px;
        width:320px; box-shadow:0 4px 24px rgba(0,0,0,.06); }}
h1 {{ font-size:18px; margin:0 0 4px; }}
p {{ font-size:13px; color:#78776f; margin:0 0 24px; }}
input {{ width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid #e8e6e0;
         border-radius:6px; font-family:inherit; font-size:14px; margin-bottom:12px; }}
button {{ width:100%; padding:10px; background:#37352f; color:#fff; border:none;
          border-radius:6px; font-family:inherit; font-size:14px; font-weight:500; cursor:pointer; }}
.err {{ color:#d33; font-size:12px; margin-bottom:12px; }}
</style></head><body>
<div class="box">
  <h1>Estudantina</h1>
  <p>Dashboard privé — entrez le mot de passe</p>
  {f'<div class="err">{error}</div>' if error else ''}
  <form method="POST">
    <input type="password" name="password" placeholder="Mot de passe" autofocus>
    <button type="submit">Se connecter</button>
  </form>
</div>
</body></html>"""


@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.set_cookie("estu_auth", "", max_age=0)
    return resp


@app.route("/")
def index():
    return render_template("index.html", seuil=SEUIL_TRANSACTIONS)


@app.route("/api/data")
def api_data():
    preset = request.args.get("preset", "today")
    if preset not in PRESET_RANGES:
        preset = "today"

    today_real            = date.today()
    from_date, to_date    = PRESET_RANGES[preset](today_real)
    is_single             = (from_date == to_date)
    n_days                = (to_date - from_date).days + 1

    comp_to   = from_date - timedelta(1)
    comp_from = comp_to   - timedelta(n_days - 1)

    # ── Stratégie de chargement ──────────────────────────────────────────────
    # Jour unique : items en live (peu de tickets).
    # Multi-jours : documents légers (1-2 appels) + cache daily_summary pour
    # les agrégats item-level des jours passés ; seul aujourd'hui est détaillé.
    def _load_docs_main():
        if is_single:
            return get_documents_with_items(from_date.isoformat(), to_date.isoformat())
        return get_documents(from_date.isoformat(), to_date.isoformat())

    def _load_today_items():
        """Items du jour courant (si inclus dans une période multi-jours)."""
        if not is_single and from_date <= today_real <= to_date:
            return get_documents_with_items(today_real.isoformat(), today_real.isoformat())
        return []

    def _load_comp():
        try:
            return get_documents(comp_from.isoformat(), comp_to.isoformat())
        except Exception:
            return None   # échec ≠ zéro vente

    # Appels indépendants en parallèle avec le fetch principal
    with ThreadPoolExecutor(max_workers=7) as pool:
        fut_docs    = pool.submit(_load_docs_main)
        fut_today   = pool.submit(_load_today_items)
        fut_comp    = pool.submit(_load_comp)
        fut_balance = pool.submit(get_balance)
        fut_catalog = pool.submit(get_catalog)
        fut_week    = pool.submit(weekly_sparkline, 7)
        fut_wow     = pool.submit(wow_growth)
        fut_weekday = pool.submit(best_weekday)

        try:
            docs_main = fut_docs.result(timeout=55)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        warnings = []

        try:
            today_docs = fut_today.result(timeout=30)
        except Exception:
            today_docs = []
            warnings.append("Détail du jour indisponible — COGS du jour estimé")

        docs_comp = fut_comp.result(timeout=5)
        if docs_comp is None:
            warnings.append("Comparaison période précédente indisponible")
            docs_comp = []

        balance = fut_balance.result(timeout=5)
        if balance is None:
            warnings.append("Solde caisse indisponible (API Vendus)")

        catalog = fut_catalog.result(timeout=10) or {}
        if not catalog:
            warnings.append("Catalogue produits indisponible — marges et COGS non calculés")

        week_data = fut_week.result(timeout=5)
        if week_data is None:
            warnings.append("Historique 7 jours indisponible")
            week_data = []

        wow_data     = fut_wow.result(timeout=5)
        weekday_data = fut_weekday.result(timeout=5)

    # ── Agrégats item-level : cache pour les jours passés + live aujourd'hui ──
    if is_single:
        day_summary = _summarize_docs_items(docs_main, catalog)
        # Cache opportuniste : une journée passée consultée = summary persisté
        if to_date < today_real and catalog:
            _upsert_summary(to_date.isoformat(), day_summary)
        period_rows = [{"day": to_date.isoformat(), **day_summary}]
    else:
        past_to     = min(to_date, today_real - timedelta(1))
        period_rows = _ensure_summaries(from_date, past_to, catalog) if from_date <= past_to else []
        if today_docs:
            period_rows = period_rows + [{"day": today_real.isoformat(),
                                          **_summarize_docs_items(today_docs, catalog)}]

    cogs_agg = (
        round(sum(r.get("cogs_ht",    0) for r in period_rows), 2),
        round(sum(r.get("covered_ht", 0) for r in period_rows), 2),
        round(sum(r.get("items_ht",   0) for r in period_rows), 2),
    )
    merged_products = _merge_products(period_rows)

    # Produits 7 jours glissants : summaries des 6 derniers jours + aujourd'hui
    rows_7d = _ensure_summaries(today_real - timedelta(6), today_real - timedelta(1), catalog)
    today_row_7d = ([{"day": today_real.isoformat(),
                      **(_summarize_docs_items(docs_main if (is_single and to_date == today_real) else today_docs, catalog))}]
                    if (is_single and to_date == today_real) or today_docs else [])
    merged_7d = _merge_products(rows_7d + today_row_7d)

    result = {
        # Méta
        "preset":        preset,
        "period_label":  PRESET_LABELS.get(preset, preset),
        "from_date":     from_date.isoformat(),
        "to_date":       to_date.isoformat(),
        "n_days":        n_days,
        "is_single_day": is_single,
        "has_items":     True,
        "date":          to_date.isoformat(),
        "updated_at":    datetime.now().strftime("%H:%M"),
        "is_today":      (preset == "today"),
        # Stats globales
        "today":         calc_stats(docs_main),
        "yesterday":     calc_stats(docs_comp),
        "balance":       balance,
        "seuil":         SEUIL_TRANSACTIONS,
        # Graphe temporel
        "daily":         daily_breakdown(docs_main),
        # Paiements & TVA (données document-level — toujours disponibles)
        "payments":      payment_breakdown(docs_main),
        "tva":           tva_breakdown(docs_main),
        # Tendance (résultats pré-calculés en parallèle)
        "week":          week_data,
        "wow":           wow_data,
        "weekdays":      weekday_data,
        # Perf commerciale
        "median":        ticket_median(docs_main),
        "upsell":        _upsell_from_rows(period_rows),
        "ticket_dist":   ticket_distribution(docs_main),
        # Produits sur 7j glissants — depuis le cache + aujourd'hui live
        "products_7d":   _products_list(merged_7d, catalog, n=None),
        # Transactions récentes
        "recent":        recent_docs(docs_main),
    }

    # ── Économie : COGS depuis le cache (multi-jours) ou les items (jour) ─────
    result["economics"] = daily_economics(docs_main, catalog, n_days,
                                           from_date=from_date, to_date=to_date,
                                           cogs_agg=cogs_agg)
    if result["economics"].get("charges_source") == "indisponible":
        warnings.append("Charges Supabase injoignables — charges et seuil non calculés")
    result["warnings"] = warnings

    # ── Produits et mix — depuis les agrégats fusionnés ───────────────────────
    result["products"] = _products_list(merged_products, catalog, n=10)
    result["mix"]      = _mix_from_merged(merged_products, catalog)

    # ── Sections disponibles uniquement pour un jour unique ───────────────────
    if is_single:
        result["hourly"] = hourly_breakdown(docs_main)
        result["curve"]  = cumulative_curve(docs_main)
        result["rush"]   = rush_detector(docs_main)
        result["tempo"]  = service_tempo(docs_main)
        result["unsold"] = unsold_today(docs_main, catalog)
    else:
        result["hourly"] = None
        result["curve"]  = None
        result["rush"]   = []
        result["tempo"]  = None
        result["unsold"] = []

    return jsonify(result)


@app.route("/api/summary/rebuild", methods=["POST"])
def api_summary_rebuild():
    """Recalcule le cache daily_summary (après changement de prix d'achat/recettes).
    Body optionnel : {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"} — défaut : tout l'historique."""
    from vendus import get_documents_with_items, get_catalog as _gc
    data      = request.get_json(silent=True) or {}
    from_iso  = data.get("from", "2026-05-27")
    to_iso    = data.get("to", (date.today() - timedelta(1)).isoformat())
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


@app.route("/cogs")
def cogs_page():
    return render_template("cogs.html")


@app.route("/charges")
def charges_page():
    return render_template("charges.html")


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
    return {r["product_title"].strip(): {"ingredients": r["ingredients"], "notes": r.get("notes", "")}
            for r in rows}

def _save_ingredient(name, data):
    ok, _ = _supa_upsert("ingredients", {"name": name, **data})
    return ok

def _save_recipe(title, ingredients, notes):
    ok, _ = _supa_upsert("recipes", {"product_title": title,
                                      "ingredients": ingredients, "notes": notes})
    return ok

# ── Cache daily_summary ───────────────────────────────────────────────────────
# Les journées passées ne changent plus : leurs agrégats item-level (COGS,
# produits, upsell) sont calculés une fois et stockés dans Supabase.
# Seul aujourd'hui est recalculé en live.

def _get_summaries(from_iso, to_iso):
    rows = _req.get(f"{SUPA_URL}/rest/v1/daily_summary", headers=_supa_headers(),
                    params=[("day", f"gte.{from_iso}"), ("day", f"lte.{to_iso}"),
                            ("order", "day.asc")])
    return rows.json() if rows.ok else []

def _summarize_docs_items(docs, catalog):
    """Agrégats item-level d'une liste de docs avec items (1 journée)."""
    cogs = covered = items_ht = 0.0
    multi = 0
    products = {}
    for d in docs:
        its = d.get("items", [])
        if len(its) >= 2:
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
        "nb":          len(docs),
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

def _ensure_summaries(from_date, to_date, catalog):
    """Retourne les summaries [from..to] (jours passés), en construisant les manquants."""
    from vendus import get_documents_with_items
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
            rows.append({"day": day, **s})
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

def _mix_from_merged(merged, catalog):
    """Mix CA + rentabilité par groupe (Boissons / Food maison / Viennoiseries / Retail).
    Viennoiseries (achetées) séparées du Food maison — marges très différentes.
    Retail = Livres, Papeterie, café en sac et tout produit non catégorisé.
    Marge calculée sur les produits dont le coût est connu (couverture affichée)."""
    from vendus import DRINK_CAT_IDS, FOOD_CAT_IDS, VIENNOISERIE_CAT_IDS
    groups = {k: {"rev_ht": 0.0, "cogs": 0.0, "covered": 0.0}
              for k in ("Boissons", "Food maison", "Viennoiseries", "Retail")}
    for name, s in merged.items():
        cid = catalog.get(name, {}).get("category_id")
        if cid in DRINK_CAT_IDS:            g = groups["Boissons"]
        elif cid in FOOD_CAT_IDS:           g = groups["Food maison"]
        elif cid in VIENNOISERIE_CAT_IDS:   g = groups["Viennoiseries"]
        else:                               g = groups["Retail"]
        g["rev_ht"] += s["rev_ht"]
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
            "pct":        round(g["rev_ht"] / grand * 100),
            "cogs":       round(g["cogs"], 2),
            "marge_pct":  marge_pct,
            "marge_eur":  round(g["rev_ht"] * marge_pct / 100, 2) if marge_pct is not None else None,
            "coverage":   round(g["covered"] / g["rev_ht"] * 100) if g["rev_ht"] else None,
        })
    return out


def _load_preparations():
    rows = _supa_get("preparations")
    return {r["name"]: r for r in rows}

def _save_preparation(name, ingredients, yield_qty, yield_unit, notes):
    ok, err = _supa_upsert("preparations", {
        "name": name, "ingredients": ingredients,
        "yield_qty": yield_qty, "yield_unit": yield_unit, "notes": notes,
    })
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

def calc_recipe_cogs(ingredients, ingr_lib, prep_lib=None):
    """Calcule le COGS total d'une recette.
    Supporte les préparations (sous-recettes) : si un ingrédient n'est pas dans
    ingr_lib mais dans prep_lib, son coût est calculé en cascade depuis sa propre
    recette (1 niveau de profondeur — pas de nesting infini).
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
            yield_qty = float(prep.get("yield_qty") or 1)
            cost_per_unit = prep_total / yield_qty if yield_qty else 0
            cost = round(qty * cost_per_unit, 5)
            total += cost
            breakdown.append({
                "name": name, "qty": qty, "unit": unit,
                "cost": round(cost, 4), "type": "preparation",
                "prep_total": round(prep_total, 4),
                "yield_qty": yield_qty,
                "yield_unit": prep.get("yield_unit", "portion"),
                "cost_per_unit": round(cost_per_unit, 4),
                "prep_breakdown": prep_bd,
            })
            continue

        # ── Cas 3 : inconnu ───────────────────────────────────────────────────
        breakdown.append({**ing, "cost": None, "error": "ingrédient inconnu"})

    return round(total, 4), breakdown

CATEGORY_NAMES = {
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
        if has_recipe:
            recipe_total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib, prep_lib)

        effective_cogs = recipe_total if recipe_total is not None else supply
        marge_ht_eff   = round(price_ht - effective_cogs, 4) if price_ht else None
        marge_pct_eff  = round((marge_ht_eff / price_ht * 100), 1) if (marge_ht_eff is not None and price_ht) else None

        products.append({
            "id":           p.get("id"),
            "title":        title,
            "category_id":  cat_id,
            "category":     CATEGORY_NAMES.get(cat_id, cat_id),
            "tax_rate":     int(rate * 100),
            "price_ttc":    price_ttc,
            "price_ht":     price_ht,
            "supply_price": supply,
            "recipe_total": recipe_total,
            "marge_ht":     marge_ht_eff,
            "marge_pct":    marge_pct_eff,
            "recipe":       breakdown,
            "recipe_notes": (recipe_data or {}).get("notes", ""),
            "has_recipe":   has_recipe,
        })

    order_map = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
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
        }
    return jsonify({"products": products, "category_order": CATEGORY_ORDER,
                    "category_names": CATEGORY_NAMES, "preparations": prep_summary})


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
    ingr_lib    = _load_ingredients()
    total, breakdown = calc_recipe_cogs(ingredients, ingr_lib)
    ok, err = _save_preparation(name, ingredients, yield_qty, yield_unit, notes)
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
    }
    _save_ingredient(name, ingr)
    return jsonify({"ok": True, "ingredient": {name: ingr}})


@app.route("/api/ingredients/<path:name>", methods=["DELETE"])
def api_ingredients_delete(name):
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
    recipe_data = recipes.get(title, {"ingredients": [], "notes": ""})
    total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib, _load_preparations())
    return jsonify({
        "ok": True, "title": title, "product_id": product_id,
        "ingredients": recipe_data["ingredients"],
        "breakdown":   breakdown,
        "notes":       recipe_data.get("notes", ""),
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
    total, breakdown = calc_recipe_cogs(ingredients, ingr_lib, _load_preparations())
    _save_recipe(title, ingredients, notes)
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
        total, _ = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib, _load_preparations())
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

    if not title or not price_ttc:
        return jsonify({"ok": False, "error": "title et price_ttc requis"}), 400

    ingr_lib          = _load_ingredients()
    total, breakdown  = calc_recipe_cogs(ingredients, ingr_lib, _load_preparations())

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
        _save_recipe(title, ingredients, notes)

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
    if not payload:
        return jsonify({"ok": False, "error": "nothing to update"}), 400
    r = req.patch(f"https://www.vendus.pt/ws/v1.1/products/{product_id}/",
                  auth=(VENDUS_API_KEY, ""), json=payload)
    if r.ok:
        return jsonify({"ok": True, "updated": payload})
    return jsonify({"ok": False, "error": r.text}), 502


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
