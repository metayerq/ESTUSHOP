#!/usr/bin/env python3
"""
Café Estudantina — Dashboard Vendus
Usage:
    pip install flask requests
    VENDUS_API_KEY=votre_cle python app.py
    → ouvre http://localhost:5000
"""

import os
from datetime import date, timedelta, datetime

from flask import Flask, jsonify, render_template, request
from vendus import (
    get_documents, get_documents_with_items, get_balance, get_catalog,
    calc_stats, hourly_breakdown, payment_breakdown, top_products, recent_docs,
    weekly_sparkline, rush_detector, unsold_today, product_stats_7d,
    tva_breakdown, service_tempo, upsell_rate, category_mix, ticket_median,
    best_weekday, wow_growth, daily_economics,
)

SEUIL_TRANSACTIONS = 40

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", seuil=SEUIL_TRANSACTIONS)


@app.route("/api/data")
def api_data():
    raw_date  = request.args.get("date", "")
    try:
        selected = date.fromisoformat(raw_date)
    except ValueError:
        selected = date.today()
    today     = selected.isoformat()
    yesterday = (selected - timedelta(days=1)).isoformat()

    try:
        docs_today = get_documents_with_items(today, today)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    try:
        docs_yesterday = get_documents(yesterday, yesterday)
    except Exception:
        docs_yesterday = []

    balance = get_balance()
    catalog = get_catalog()

    since_7d = (selected - timedelta(days=6)).isoformat()

    return jsonify({
        "date":        today,
        "updated_at":  datetime.now().strftime("%H:%M"),
        "is_today":    selected == date.today(),
        "today":       calc_stats(docs_today),
        "yesterday":   calc_stats(docs_yesterday),
        "balance":     balance,
        "seuil":       SEUIL_TRANSACTIONS,
        "week":        weekly_sparkline(7),
        "hourly":      hourly_breakdown(docs_today),
        "payments":    payment_breakdown(docs_today),
        "products":    top_products(docs_today, catalog),
        "rush":        rush_detector(docs_today),
        "economics":   daily_economics(docs_today, catalog),
        "tva":         tva_breakdown(docs_today),
        "tempo":       service_tempo(docs_today),
        "upsell":      upsell_rate(docs_today),
        "mix":         category_mix(docs_today, catalog),
        "median":      ticket_median(docs_today),
        "weekdays":    best_weekday(),
        "wow":         wow_growth(),
        "unsold":      unsold_today(docs_today, catalog),
        "products_7d": product_stats_7d(since_7d, today),
        "recent":      recent_docs(docs_today),
    })


if __name__ == "__main__":
    api_key = os.environ.get("VENDUS_API_KEY", "")
    if not api_key:
        print("⚠️  Attention : VENDUS_API_KEY non définie.")
        print("   Lance avec : VENDUS_API_KEY=ta_cle python app.py")
    print("🚀 Dashboard Estudantina → http://localhost:8080")
    app.run(debug=False, host="0.0.0.0", port=8080)
