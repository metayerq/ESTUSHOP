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


@app.route("/cogs")
def cogs_page():
    return render_template("cogs.html")


# ── Recettes détaillées par produit ───────────────────────────────────────────
CAFE_G  = 28.70 / 1000   # €/g
LAIT_ML = 1.09  / 1000   # €/ml
OAT_ML  = 1.90  / 1000   # €/ml

def _r(name, qty, cost):
    return {"name": name, "qty": qty, "cost": round(qty * cost, 4)}

RECIPES = {
    # ── Espresso ──────────────────────────────────────────────────────────────
    "Espresso":            [_r("Café", 18, CAFE_G)],
    "Doppio":              [_r("Café", 18, CAFE_G)],
    "Americano":           [_r("Café", 18, CAFE_G)],
    "Iced Americano":      [_r("Café", 18, CAFE_G)],
    # ── Cortado ───────────────────────────────────────────────────────────────
    "Cortado":             [_r("Café", 18, CAFE_G), _r("Lait frais", 60, LAIT_ML)],
    "Cortado Oat":         [_r("Café", 18, CAFE_G), _r("Lait avoine", 60, OAT_ML)],
    # ── Flat White ────────────────────────────────────────────────────────────
    "Flat White":          [_r("Café", 18, CAFE_G), _r("Lait frais", 130, LAIT_ML)],
    "Flat White Oat":      [_r("Café", 18, CAFE_G), _r("Lait avoine", 130, OAT_ML)],
    "Iced Flat White":     [_r("Café", 18, CAFE_G), _r("Lait frais", 130, LAIT_ML)],
    "Iced Flat White Oat": [_r("Café", 18, CAFE_G), _r("Lait avoine", 130, OAT_ML)],
    # ── Cappuccino ────────────────────────────────────────────────────────────
    "Cappuccino":          [_r("Café", 18, CAFE_G), _r("Lait frais", 150, LAIT_ML)],
    "Cappuccino Oat":      [_r("Café", 18, CAFE_G), _r("Lait avoine", 150, OAT_ML)],
    # ── Latte ─────────────────────────────────────────────────────────────────
    "Latte":               [_r("Café", 18, CAFE_G), _r("Lait frais", 220, LAIT_ML)],
    "Latte Oat":           [_r("Café", 18, CAFE_G), _r("Lait avoine", 220, OAT_ML)],
    "Iced Latte":          [_r("Café", 18, CAFE_G), _r("Lait frais", 200, LAIT_ML)],
    "Iced Latte Oat":      [_r("Café", 18, CAFE_G), _r("Lait avoine", 200, OAT_ML)],
    # ── Signatures ────────────────────────────────────────────────────────────
    "Banana Bread Iced Latte":     [_r("Café", 18, CAFE_G), _r("Lait frais", 200, LAIT_ML)],
    "Banana Bread Iced Latte Oat": [_r("Café", 18, CAFE_G), _r("Lait avoine", 200, OAT_ML)],
    "Cold Brew":           [_r("Café", 25, CAFE_G)],
    # ── Filter ────────────────────────────────────────────────────────────────
    "V60":                 [_r("Café (filtre)", 20, CAFE_G)],
    "Batch Brew":          [_r("Café (filtre)", 17, CAFE_G)],
    # ── Matcha / Tea ──────────────────────────────────────────────────────────
    "Matcha Latte":        [_r("Matcha", 5, 0.048), _r("Lait frais", 220, LAIT_ML)],
    "Matcha Latte Oat":    [_r("Matcha", 5, 0.048), _r("Lait avoine", 220, OAT_ML)],
    "Iced Matcha Latte":   [_r("Matcha", 5, 0.048), _r("Lait frais", 220, LAIT_ML)],
    "Iced Matcha Latte Oat": [_r("Matcha", 5, 0.048), _r("Lait avoine", 220, OAT_ML)],
    # ── Babyccino ─────────────────────────────────────────────────────────────
    "Babyccino":           [_r("Lait frais", 120, LAIT_ML)],
    "Babyccino Oat":       [_r("Lait avoine", 110, OAT_ML)],
}

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
}

CATEGORY_ORDER = [
    "343052000", "343053226", "343053550", "343046110",
    "343054458", "343042919", "343055566", "343065085", "343052198",
    "343055376", "343071668", "343077316", "343079649",
]

TAX_RATES = {"NOR": 0.23, "INT": 0.13, "RED": 0.06}


@app.route("/api/cogs")
def api_cogs():
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    BASE = "https://www.vendus.pt/ws/v1.1"
    r = req.get(f"{BASE}/products/", auth=(VENDUS_API_KEY, ""), params={"per_page": 200})
    raw = r.json() if r.ok else []

    products = []
    for p in raw:
        title   = p.get("title", "")
        cat_id  = str(p.get("category_id") or "")
        tax_id  = p.get("tax_id") or "INT"
        rate    = TAX_RATES.get(tax_id, 0.13)
        prices  = p.get("prices") or []
        price_ttc = float(prices[0].get("price", prices[0].get("gross_price", 0))) if isinstance(prices, list) and prices else 0.0
        price_ht  = round(price_ttc / (1 + rate), 4) if price_ttc else float(p.get("price_without_tax") or 0)
        supply    = float(p.get("supply_price") or 0)
        marge_ht  = round(price_ht - supply, 4)
        marge_pct = round((marge_ht / price_ht * 100), 1) if price_ht else None
        recipe       = RECIPES.get(title, [])
        recipe_total = round(sum(ing["cost"] for ing in recipe), 4) if recipe else None
        # Effective COGS: recipe si dispo, sinon supply_price Vendus
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
            "recipe":       recipe,
            "has_recipe":   bool(recipe),
        })

    # Trier par catégorie puis par titre
    order_map = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    products.sort(key=lambda p: (order_map.get(p["category_id"], 99), p["title"]))

    return jsonify({"products": products, "category_order": CATEGORY_ORDER, "category_names": CATEGORY_NAMES})


@app.route("/api/update_supply_price/<int:product_id>", methods=["POST"])
def update_supply_price(product_id):
    import requests as req
    from flask import request as freq
    from vendus import API_KEY as VENDUS_API_KEY
    data = freq.get_json()
    val  = data.get("supply_price")
    if val is None:
        return jsonify({"ok": False, "error": "missing supply_price"}), 400
    BASE = "https://www.vendus.pt/ws/v1.1"
    r = req.patch(f"{BASE}/products/{product_id}/", auth=(VENDUS_API_KEY, ""),
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
