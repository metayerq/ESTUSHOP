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
    "all":       lambda d: (date(2026, 5, 27), d),  # date d'ouverture Estudantina
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
    result["economics"] = daily_economics(docs_main, catalog, n_days,
                                           from_date=from_date, to_date=to_date)

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


# ── Supabase ──────────────────────────────────────────────────────────────────
import requests as _req

SUPA_URL = os.environ.get("SUPABASE_URL", "https://llbxrkyufegrhxbzkowf.supabase.co")
SUPA_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_gZTNLYcOW5OisN-k-RoHCw_SMjfz6CO")

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
    return r.ok

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
    return _supa_upsert("ingredients", {"name": name, **data})

def _save_recipe(title, ingredients, notes):
    return _supa_upsert("recipes", {"product_title": title,
                                     "ingredients": ingredients, "notes": notes})

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

def calc_recipe_cogs(ingredients, ingr_lib):
    """Calcule le COGS total d'une recette depuis la bibliothèque d'ingrédients."""
    total = 0.0
    breakdown = []
    for ing in ingredients:
        name     = ing["name"]
        qty      = float(ing["qty"])
        unit     = ing["unit"]
        lib_item = ingr_lib.get(name)
        if not lib_item:
            breakdown.append({**ing, "cost": None, "error": "ingrédient inconnu"})
            continue
        price    = float(lib_item["price"])
        unit_ref = lib_item["unit_ref"]
        factor   = UNIT_CONVERSIONS.get((unit, unit_ref))
        if factor is None:
            breakdown.append({**ing, "cost": None, "error": f"conversion {unit}→{unit_ref} inconnue"})
            continue
        cost = round(qty * factor * price, 5)
        total += cost
        breakdown.append({
            "name": name, "qty": qty, "unit": unit,
            "price_ref": price, "unit_ref": unit_ref,
            "cost": round(cost, 4),
        })
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
    BASE     = "https://www.vendus.pt/ws/v1.1"
    r        = req.get(f"{BASE}/products/", auth=(VENDUS_API_KEY, ""), params={"per_page": 200})
    raw      = r.json() if r.ok else []
    recipes  = _load_recipes()
    ingr_lib = _load_ingredients()

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
            recipe_total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib)

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
    return jsonify({"products": products, "category_order": CATEGORY_ORDER, "category_names": CATEGORY_NAMES})


@app.route("/api/ingredients", methods=["GET"])
def api_ingredients_get():
    return jsonify(_load_ingredients())


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
    title       = r.json().get("title", "")
    recipes     = _load_recipes()
    ingr_lib    = _load_ingredients()
    recipe_data = recipes.get(title, {"ingredients": [], "notes": ""})
    total, breakdown = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib)
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
    title       = r.json().get("title", "")
    ingr_lib    = _load_ingredients()
    ingredients = data.get("ingredients", [])
    notes       = data.get("notes", "")
    total, breakdown = calc_recipe_cogs(ingredients, ingr_lib)
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


@app.route("/api/recipe/recalculate-all", methods=["POST"])
def api_recipe_recalculate_all():
    import requests as req
    from vendus import API_KEY as VENDUS_API_KEY
    recipes  = _load_recipes()
    ingr_lib = _load_ingredients()
    BASE     = "https://www.vendus.pt/ws/v1.1"
    r        = req.get(f"{BASE}/products/", auth=(VENDUS_API_KEY, ""), params={"per_page": 200})
    products = r.json() if r.ok else []
    by_title = {p["title"]: p for p in products}
    results  = []
    for title, recipe_data in recipes.items():
        if not recipe_data.get("ingredients"):
            continue
        prod = by_title.get(title)
        if not prod:
            results.append({"title": title, "status": "not_found_in_vendus"})
            continue
        total, _ = calc_recipe_cogs(recipe_data["ingredients"], ingr_lib)
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
    total, breakdown  = calc_recipe_cogs(ingredients, ingr_lib)

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
