"""Vendus API helpers."""

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API_KEY  = os.environ.get("VENDUS_API_KEY", "")
BASE_URL = "https://www.vendus.pt/ws/v1.1"

PAYMENT_LABELS = {
    "NU":      "Espèces",
    "CC":      "Carte crédit",
    "CD":      "Carte débit",
    "MB":      "MB Ref",
    "MBWAY":   "MB WAY",
    "TB":      "Virement",
    "TR":      "Ticket repas",
    "CO":      "Carte cadeau",
    "TPASIBS": "TPA SIBS",
    "OU":      "Autre",
}


def vendus(endpoint, params=None):
    if not API_KEY:
        raise ValueError("VENDUS_API_KEY non définie")
    r = requests.get(
        f"{BASE_URL}{endpoint}",
        auth=(API_KEY, ""),
        params=params or {},
        timeout=10,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


SALE_TYPES = {"FT", "FS", "FR", "FG"}


def get_documents(since: str, until: str):
    docs = vendus("/documents/", {
        "since":  since,
        "until":  until,
        "status": "N",
        "view":   "detailed",
    })
    if isinstance(docs, list):
        raw = docs
    else:
        raw = docs.get("docs", docs.get("data", []))
    # Exclure les RG (reçus globaux) qui doublonnent les FT
    return [d for d in raw if d.get("type") in SALE_TYPES]


def get_document_detail(doc_id: int):
    """Récupère un document avec ses items (lignes produits)."""
    try:
        return vendus(f"/documents/{doc_id}/")
    except Exception:
        return None


def get_documents_with_items(since: str, until: str):
    """Récupère les documents de vente avec leurs lignes produits (appels parallèles)."""
    docs = get_documents(since, until)
    if not docs:
        return []
    # Appels parallèles pour récupérer les items de chaque document
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(get_document_detail, d["id"]): d["id"] for d in docs}
        for future in as_completed(futures):
            doc_id = futures[future]
            detail = future.result()
            if detail:
                results[doc_id] = detail
    # Réassembler dans l'ordre original, enrichi des items
    enriched = []
    for d in docs:
        detail = results.get(d["id"], d)
        enriched.append(detail)
    return enriched


def get_register_movements(since: str, until: str):
    try:
        registers = vendus("/registers/")
        if isinstance(registers, list) and registers:
            reg_id = registers[0]["id"]
        elif isinstance(registers, dict):
            items = registers.get("registers", registers.get("data", []))
            reg_id = items[0]["id"] if items else None
        else:
            return []
        if not reg_id:
            return []
        mvts = vendus(f"/registers/{reg_id}/movements/", {
            "since":  since,
            "until":  until,
            "return": "list",
        })
        if isinstance(mvts, list):
            return mvts
        return mvts.get("movements", mvts.get("data", []))
    except Exception:
        return []


def get_balance():
    try:
        data = vendus("/registers/balance/")
        if isinstance(data, list) and data:
            return float(data[0].get("amount", 0))
        if isinstance(data, dict):
            return float(data.get("amount", 0))
        return 0.0
    except Exception:
        return 0.0


def calc_stats(docs):
    ca     = sum(float(d.get("amount_gross", 0)) for d in docs)
    nb     = len(docs)
    ticket = round(ca / nb, 2) if nb else 0.0
    return {"ca": round(ca, 2), "nb": nb, "ticket": ticket}


def hourly_breakdown(docs):
    by_hour = defaultdict(float)
    for d in docs:
        lt = d.get("local_time", "")
        try:
            hour = int(lt[11:13])
        except (TypeError, ValueError, IndexError):
            hour = 0
        by_hour[hour] += float(d.get("amount_gross", 0))
    hours = list(range(7, 23))
    return {
        "labels": [f"{h}h" for h in hours],
        "values": [round(by_hour.get(h, 0), 2) for h in hours],
    }


def payment_breakdown(docs):
    """Répartition des paiements dérivée directement des documents (fiable, sans doublon caisse)."""
    by_label = defaultdict(float)
    for d in docs:
        for p in d.get("payments", []):
            label = p.get("title") or "Autre"
            by_label[label] += float(p.get("amount", 0))
    # Trier par montant décroissant
    sorted_items = sorted(by_label.items(), key=lambda x: x[1], reverse=True)
    filtered = [(k, round(v, 2)) for k, v in sorted_items if v > 0]
    return {
        "labels": [k for k, _ in filtered],
        "values": [v for _, v in filtered],
    }


def get_catalog():
    """Retourne tous les produits actifs avec coût (toutes pages)."""
    try:
        all_products = []
        page = 1
        while True:
            batch = vendus("/products/", {"page": page})
            if not isinstance(batch, list):
                batch = batch.get("products", batch.get("data", []))
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < 20:
                break
            page += 1

        result = {}
        for p in all_products:
            if p.get("status") != "on":
                continue
            gross  = float(p.get("gross_price", 0))
            supply = float(p.get("supply_price", 0))
            margin_pct = round((gross - supply) / gross * 100, 1) if gross and supply else None
            result[p["title"]] = {
                "id":         p["id"],
                "name":       p["title"],
                "category":   p.get("class_name", ""),
                "price":      gross,
                "cost":       supply,
                "margin_pct": margin_pct,
            }
        return result
    except Exception:
        return {}


def unsold_today(docs, catalog):
    """Produits Alimentar du catalogue absents des tickets du jour."""
    sold_names = {item["title"] for d in docs for item in d.get("items", [])}
    return [
        p for p in catalog.values()
        if p["name"] not in sold_names and p.get("category") == "Alimentar"
    ]


def tva_breakdown(docs):
    """Ventilation TVA par taux : base HT, montant TVA, total TTC."""
    by_rate = defaultdict(lambda: {"base": 0.0, "tva": 0.0, "total": 0.0})
    for d in docs:
        for t in d.get("taxes", []):
            rate = t.get("rate", 0)
            by_rate[rate]["base"]  += float(t.get("base", 0))
            by_rate[rate]["tva"]   += float(t.get("amount", 0))
            by_rate[rate]["total"] += float(t.get("total", 0))
    result = []
    for rate in sorted(by_rate):
        s = by_rate[rate]
        result.append({
            "rate":  rate,
            "base":  round(s["base"], 2),
            "tva":   round(s["tva"], 2),
            "total": round(s["total"], 2),
        })
    totals = {
        "base":  round(sum(r["base"]  for r in result), 2),
        "tva":   round(sum(r["tva"]   for r in result), 2),
        "total": round(sum(r["total"] for r in result), 2),
    }
    return {"rows": result, "totals": totals}


def service_tempo(docs):
    """Temps moyen entre transactions et vélocité par heure."""
    from datetime import datetime
    times = []
    for d in docs:
        lt = d.get("local_time", "")
        try:
            times.append(datetime.strptime(lt, "%Y-%m-%d %H:%M:%S"))
        except (ValueError, TypeError):
            pass
    if len(times) < 2:
        return {"avg_gap_min": None, "tx_per_hour": None, "busiest": None}

    times.sort()
    gaps = [(times[i+1] - times[i]).seconds / 60 for i in range(len(times) - 1)]
    avg_gap = round(sum(gaps) / len(gaps), 1)

    # Vélocité par heure (nb transactions)
    by_hour = defaultdict(int)
    for t in times:
        by_hour[t.hour] += 1
    busiest_hour = max(by_hour, key=lambda h: by_hour[h])

    duration_hours = (times[-1] - times[0]).seconds / 3600 or 1
    tx_per_hour = round(len(times) / duration_hours, 1)

    return {
        "avg_gap_min":  avg_gap,
        "tx_per_hour":  tx_per_hour,
        "busiest":      f"{busiest_hour}h ({by_hour[busiest_hour]} tx)",
        "first_tx":     times[0].strftime("%Hh%M"),
        "last_tx":      times[-1].strftime("%Hh%M"),
        "duration_h":   round(duration_hours, 1),
    }


def rush_detector(docs, window_minutes=60, threshold=5):
    """Détecte les créneaux où les transactions dépassent `threshold` en `window_minutes`."""
    from datetime import datetime, timedelta
    times = []
    for d in docs:
        lt = d.get("local_time", "")
        try:
            times.append(datetime.strptime(lt, "%Y-%m-%d %H:%M:%S"))
        except (ValueError, TypeError):
            pass
    if not times:
        return []

    times.sort()
    rushes = []
    window = timedelta(minutes=window_minutes)
    i = 0
    while i < len(times):
        j = i
        while j < len(times) and times[j] - times[i] <= window:
            j += 1
        count = j - i
        if count >= threshold:
            rushes.append({
                "start": times[i].strftime("%Hh%M"),
                "end":   times[j - 1].strftime("%Hh%M"),
                "count": count,
            })
            i = j  # sauter la fenêtre
        else:
            i += 1
    return rushes


def product_stats_7d(since: str, until: str):
    """CA total et nb jours vendus par produit sur la période."""
    try:
        raw = vendus("/documents/", {"since": since, "until": until, "status": "N"})
        if not isinstance(raw, list):
            raw = raw.get("docs", raw.get("data", []))
        ft_ids = [d["id"] for d in raw if d.get("type") in SALE_TYPES]
    except Exception:
        return []

    by_product = defaultdict(lambda: {"revenue": 0.0, "qty": 0, "days": set()})

    def fetch(doc_id):
        try:
            return vendus(f"/documents/{doc_id}/")
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(fetch, ft_ids))

    for detail in details:
        if not detail:
            continue
        day = detail.get("date", "")
        for item in detail.get("items", []):
            name = item.get("title", "—")
            by_product[name]["revenue"] += float(item.get("amounts", {}).get("gross_total", 0))
            by_product[name]["qty"]     += float(item.get("qty", 0))
            by_product[name]["days"].add(day)

    n_days = max(1, len({d.get("date","") for d in (details or []) if d}))
    result = []
    # Récupérer le catalogue pour la marge
    catalog = get_catalog()
    for name, stats in by_product.items():
        days_sold = len(stats["days"])
        revenue   = round(stats["revenue"], 2)
        cat_info  = catalog.get(name)
        cost      = round(cat_info["cost"] * stats["qty"], 2) if cat_info else None
        margin    = round((revenue - cost) / revenue * 100, 1) if revenue and cost else None
        result.append({
            "name":       name,
            "revenue":    revenue,
            "qty":        int(stats["qty"]),
            "days_sold":  days_sold,
            "avg_day":    round(revenue / days_sold, 2) if days_sold else 0,
            "cost":       cost,
            "margin_pct": margin,
        })
    return sorted(result, key=lambda x: x["revenue"], reverse=True)


def weekly_sparkline(days=7):
    """CA et nb transactions par jour sur les `days` derniers jours."""
    from datetime import date, timedelta
    today = date.today()
    since = (today - timedelta(days=days - 1)).isoformat()
    until = today.isoformat()
    try:
        raw = vendus("/documents/", {"since": since, "until": until, "status": "N"})
        if not isinstance(raw, list):
            raw = raw.get("docs", raw.get("data", []))
    except Exception:
        raw = []

    by_day = defaultdict(lambda: {"ca": 0.0, "nb": 0})
    for d in raw:
        if d.get("type") in SALE_TYPES:
            day = d.get("date", "")
            by_day[day]["ca"] += float(d.get("amount_gross", 0))
            by_day[day]["nb"] += 1

    result = []
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        result.append({
            "date": day,
            "label": (today - timedelta(days=days - 1 - i)).strftime("%a"),
            "ca": round(by_day[day]["ca"], 2),
            "nb": by_day[day]["nb"],
        })
    return result


def top_products(docs, catalog=None, n=10):
    """Top produits par quantité vendue, avec CA, coût et marge."""
    catalog = catalog or {}
    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "cost": 0.0})
    for d in docs:
        for item in d.get("items", []):
            title = item.get("title", "—")
            qty   = float(item.get("qty", 0))
            by_product[title]["qty"]     += qty
            by_product[title]["revenue"] += float(item.get("amounts", {}).get("gross_total", 0))
            cat_info = catalog.get(title)
            if cat_info:
                by_product[title]["cost"] += cat_info["cost"] * qty
    ranked = sorted(by_product.items(), key=lambda x: x[1]["qty"], reverse=True)
    result = []
    for name, stats in ranked[:n]:
        revenue = round(stats["revenue"], 2)
        cost    = round(stats["cost"], 2)
        margin  = round((revenue - cost) / revenue * 100, 1) if revenue and cost else None
        result.append({
            "name":       name,
            "qty":        int(stats["qty"]),
            "revenue":    revenue,
            "avg":        round(revenue / stats["qty"], 2) if stats["qty"] else 0,
            "cost":       cost,
            "margin_pct": margin,
        })
    return result


def recent_docs(docs, n=10):
    sorted_docs = sorted(
        docs,
        key=lambda d: d.get("local_time", d.get("date", "")),
        reverse=True,
    )
    result = []
    for d in sorted_docs[:n]:
        payments = d.get("payments", [])
        items    = d.get("items", [])
        result.append({
            "id":      d.get("id"),
            "number":  d.get("number", "—"),
            "time":    (d.get("local_time", "") or "")[-8:-3],
            "amount":  float(d.get("amount_gross", 0)),
            "type":    d.get("type", ""),
            "client":  d.get("client", {}).get("name", "Consumidor Final"),
            "payments": [
                {"label": p.get("title", "—"), "amount": float(p.get("amount", 0))}
                for p in payments
            ],
            "items": [
                {
                    "name":  item.get("title", "—"),
                    "qty":   float(item.get("qty", 1)),
                    "unit":  float(item.get("amounts", {}).get("gross_unit", 0)),
                    "total": float(item.get("amounts", {}).get("gross_total", 0)),
                }
                for item in items
            ],
        })
    return result
