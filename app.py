#!/usr/bin/env python3
"""
Café Estudantina — Dashboard Vendus
Usage:
    pip install flask requests
    VENDUS_API_KEY=votre_cle python app.py
    → ouvre http://localhost:8080
"""

import os
from datetime import date, timedelta, datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request
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
PRESET_RANGES = {
    "today":     lambda d: (d, d),
    "yesterday": lambda d: (d - timedelta(1), d - timedelta(1)),
    "3d":        lambda d: (d - timedelta(2), d),
    "7d":        lambda d: (d - timedelta(6), d),
    "30d":       lambda d: (d - timedelta(29), d),
    "month":     lambda d: (d.replace(day=1), d),
    "year":      lambda d: (date(d.year, 1, 1), d),
    "all":       lambda d: (date(2025, 6, 1), d),   # ← ajuste la date d'ouverture
}
PRESET_LABELS = {
    "today":     "Aujourd'hui",
    "yesterday": "Hier",
    "3d":        "3 derniers jours",
    "7d":        "7 derniers jours",
    "30d":       "30 derniers jours",
    "month":     "Ce mois-ci",
    "year":      "Cette année",
    "all":       "Depuis l'ouverture",
}
# Presets pour lesquels on récupère le détail articles (COGS, produits, mix)
# Limité à today/yesterday pour rester sous le timeout Vercel (10s)
FETCH_ITEMS_PRESETS = {"today", "yesterday"}

app = Flask(__name__)


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
    fetch_items           = preset in FETCH_ITEMS_PRESETS

    since_7d  = (today_real - timedelta(days=6)).isoformat()
    comp_to   = from_date - timedelta(1)
    comp_from = comp_to   - timedelta(n_days - 1)

    # ── Tous les appels API en parallèle ────────────────────────────────────
    # docs_main + appels indépendants (balance, catalog, sparkline…) tournent
    # en même temps → temps total ≈ max(docs_main, others) au lieu de somme.
    def _load_docs_main():
        """Un seul fetch qui couvre docs_main ET docs_7d (si items requis)."""
        if fetch_items:
            # On charge 7j d'un coup — docs_main sera filtré côté Python
            return get_documents_with_items(since_7d, today_real.isoformat())
        return get_documents(from_date.isoformat(), to_date.isoformat())

    def _load_comp():
        try:
            return get_documents(comp_from.isoformat(), comp_to.isoformat())
        except Exception:
            return []

    # Appels indépendants en parallèle avec le fetch principal
    with ThreadPoolExecutor(max_workers=6) as pool:
        fut_docs    = pool.submit(_load_docs_main)
        fut_comp    = pool.submit(_load_comp)
        fut_balance = pool.submit(get_balance)
        fut_catalog = pool.submit(get_catalog if fetch_items else dict)
        fut_week    = pool.submit(weekly_sparkline, 7)
        fut_wow     = pool.submit(wow_growth)
        fut_weekday = pool.submit(best_weekday)

        try:
            docs_7d = fut_docs.result(timeout=20)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        docs_comp    = fut_comp.result(timeout=5) or []
        balance      = fut_balance.result(timeout=5) or 0.0
        catalog      = fut_catalog.result(timeout=10) or {}
        week_data    = fut_week.result(timeout=5) or []
        wow_data     = fut_wow.result(timeout=5)
        weekday_data = fut_weekday.result(timeout=5)

    # Filtrer docs_main depuis les 7j chargés (ou utiliser directement si pas d'items)
    if fetch_items:
        from_iso  = from_date.isoformat()
        to_iso    = to_date.isoformat()
        docs_main = [d for d in docs_7d
                     if from_iso <= (d.get("date") or d.get("local_time",""))[:10] <= to_iso]
    else:
        docs_main = docs_7d
        docs_7d   = []

    result = {
        # Méta
        "preset":        preset,
        "period_label":  PRESET_LABELS.get(preset, preset),
        "from_date":     from_date.isoformat(),
        "to_date":       to_date.isoformat(),
        "n_days":        n_days,
        "is_single_day": is_single,
        "has_items":     fetch_items,
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
        "upsell":        upsell_rate(docs_main),
        "ticket_dist":   ticket_distribution(docs_main),
        # Produits sur 7j glissants — dérivés des docs déjà chargés si dispo
        "products_7d":   product_stats_from_docs(docs_7d, catalog) if fetch_items else [],
        # Transactions récentes
        "recent":        recent_docs(docs_main),
    }

    # ── Économie : toujours calculée (marge réelle si articles, estimée sinon) ─
    result["economics"] = daily_economics(docs_main, catalog, n_days)

    # ── Produits et mix : uniquement si détail articles disponible ────────────
    if fetch_items:
        result["products"] = top_products(docs_main, catalog)
        result["mix"]      = category_mix(docs_main, catalog)
    else:
        result["products"] = []
        result["mix"]      = []

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


if __name__ == "__main__":
    api_key = os.environ.get("VENDUS_API_KEY", "")
    if not api_key:
        print("⚠️  Attention : VENDUS_API_KEY non définie.")
        print("   Lance avec : VENDUS_API_KEY=ta_cle python app.py")
    print("🚀 Dashboard Estudantina → http://localhost:8080")
    app.run(debug=False, host="0.0.0.0", port=8080)
