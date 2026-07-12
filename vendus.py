"""Vendus API helpers."""

import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ── Micro-cache TTL (survit tant que l'instance serverless est chaude) ───────
_TTL_CACHE = {}

def _ttl_get(key, ttl, loader, cacheable=lambda v: bool(v)):
    """Retourne la valeur en cache si fraîche, sinon recharge.
    Les échecs (valeur non `cacheable`) ne sont jamais mis en cache."""
    hit = _TTL_CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = loader()
    if cacheable(val):
        _TTL_CACHE[key] = (now, val)
    return val

API_KEY   = os.environ.get("VENDUS_API_KEY", "")
BASE_URL  = "https://www.vendus.pt/ws/v1.1"

SUPA_URL  = os.environ.get("SUPABASE_URL", "")
SUPA_KEY  = os.environ.get("SUPABASE_KEY", "")

def _supa_get_economics(table, params=None):
    """Lecture Supabase légère pour les calculs economics (indépendant de app.py).
    Micro-cache 60s : les charges/employés changent rarement."""
    def _load():
        h = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}
        r = requests.get(f"{SUPA_URL}/rest/v1/{table}", headers=h, params=params or {})
        return r.json() if r.ok else []
    return _ttl_get(("eco", table, str(params)), 60, _load)

PAYMENT_LABELS = {
    "NU":      "Cash",
    "CC":      "Credit card",
    "CD":      "Debit card",
    "MB":      "MB Ref",
    "MBWAY":   "MB WAY",
    "TB":      "Transfer",
    "TR":      "Meal voucher",
    "CO":      "Gift card",
    "TPASIBS": "TPA SIBS",
    "OU":      "Other",
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


SALE_TYPES   = {"FT", "FS", "FR", "FG"}
REFUND_TYPES = {"NC"}   # notas de crédito — soustraites du CA


def _negate_refund(d):
    """Négative tous les montants/quantités d'une nota de crédito pour qu'elle
    se soustraie naturellement du CA, du COGS, des quantités et des paiements."""
    d["_refund"] = True
    for k in ("amount_gross", "amount_net"):
        if d.get(k) is not None:
            d[k] = -abs(float(d[k]))
    for it in d.get("items", []):
        if it.get("qty") is not None:
            it["qty"] = -abs(float(it["qty"]))
        am = it.get("amounts", {})
        for k in ("net_total", "gross_total"):
            if am.get(k) is not None:
                am[k] = -abs(float(am[k]))
    for p in d.get("payments", []):
        if p.get("amount") is not None:
            p["amount"] = -abs(float(p["amount"]))
    return d


def get_documents(since: str, until: str, detailed: bool = False):
    """Récupère ventes + avoirs (NC) de la période (pagination complète).
    Les NC sont retournées avec montants négatifs → CA net automatique.
    detailed=True → view=detailed : la liste inclut alors les payments
    (non documenté officiellement mais vérifié) — utilisé par la réconciliation."""
    PER_PAGE = 200
    all_raw  = []
    page     = 1
    while True:
        params = {
            "since":    since,
            "until":    until,
            "per_page": PER_PAGE,
            "page":     page,
        }
        if detailed:
            params["view"] = "detailed"
        batch = vendus("/documents/", params)
        if isinstance(batch, list):
            raw = batch
        else:
            raw = batch.get("docs", batch.get("data", []))
        all_raw.extend(raw)
        if len(raw) < PER_PAGE:
            break   # dernière page
        page += 1
    out = []
    for d in all_raw:
        t = d.get("type")
        if t in SALE_TYPES:
            out.append(d)
        elif t in REFUND_TYPES:
            out.append(_negate_refund(d))
    return out


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
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(get_document_detail, d["id"]): d["id"] for d in docs}
        for future in as_completed(futures):
            doc_id = futures[future]
            detail = future.result()
            if detail:
                results[doc_id] = detail
    # Réassembler dans l'ordre original, enrichi des items.
    # Le détail brut (API) écrase la négation des NC → re-négativer.
    enriched = []
    for d in docs:
        detail = results.get(d["id"], d)
        if d.get("_refund") and not detail.get("_refund"):
            detail = _negate_refund(detail)
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
    """Retourne le solde caisse, ou None si l'API échoue (≠ 0 = vraie valeur).
    Micro-cache 60s."""
    return _ttl_get("balance", 60, _fetch_balance, cacheable=lambda v: v is not None)


def _fetch_balance():
    try:
        data = vendus("/registers/balance/")
        if isinstance(data, list) and data:
            return float(data[0].get("amount", 0))
        if isinstance(data, dict):
            return float(data.get("amount", 0))
        return 0.0
    except Exception:
        return None


def calc_stats(docs):
    ca_ttc = sum(float(d.get("amount_gross", 0)) for d in docs)   # NC négatives → net
    ca_ht  = sum(float(d.get("amount_net",   0)) for d in docs)
    nb     = sum(1 for d in docs if not d.get("_refund"))         # avoirs ≠ ventes
    return {
        "ca":         round(ca_ttc, 2),   # TTC net — affiché en principal
        "ca_ht":      round(ca_ht, 2),
        "nb":         nb,
        "ticket":     round(ca_ttc / nb, 2) if nb else 0.0,   # TTC
        "ticket_ht":  round(ca_ht  / nb, 2) if nb else 0.0,   # HT
    }


def hourly_breakdown(docs):
    from datetime import datetime
    by_hour = defaultdict(lambda: {"ca": 0.0, "nb": 0, "times": []})
    for d in docs:
        lt = d.get("local_time", "")
        try:
            hour = int(lt[11:13])
            by_hour[hour]["times"].append(lt)
        except (TypeError, ValueError, IndexError):
            hour = 0
        by_hour[hour]["ca"] += float(d.get("amount_gross", 0))
        by_hour[hour]["nb"] += 1

    hours = list(range(7, 23))
    ca_values, nb_values, avg_ticket, avg_gap = [], [], [], []

    for h in hours:
        slot = by_hour.get(h, {"ca": 0.0, "nb": 0, "times": []})
        ca  = round(slot["ca"], 2)
        nb  = slot["nb"]
        ca_values.append(ca)
        nb_values.append(nb)
        avg_ticket.append(round(ca / nb, 2) if nb else None)

        # Vitesse : gap moyen entre transactions consécutives dans l'heure
        times = sorted(slot["times"])
        if len(times) >= 2:
            gaps = []
            for i in range(len(times) - 1):
                try:
                    t1 = datetime.strptime(times[i],   "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(times[i+1], "%Y-%m-%d %H:%M:%S")
                    gaps.append((t2 - t1).seconds / 60)
                except ValueError:
                    pass
            avg_gap.append(round(sum(gaps) / len(gaps), 1) if gaps else None)
        else:
            avg_gap.append(None)

    return {
        "labels":     [f"{h}h" for h in hours],
        "values":     ca_values,
        "nb":         nb_values,
        "avg_ticket": avg_ticket,
        "avg_gap":    avg_gap,
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


LAST_CATEGORIES_ERROR = None  # diagnostic — dernière erreur/anomalie de _fetch_categories

def get_categories():
    """Retourne les catégories réelles du compte Vendus ({id: title}).
    Micro-cache 3 min — source de vérité, remplace tout mapping codé en dur
    (les IDs changent si une catégorie est supprimée/recréée côté Vendus)."""
    return _ttl_get("categories", 180, _fetch_categories)


def _fetch_categories():
    global LAST_CATEGORIES_ERROR
    LAST_CATEGORIES_ERROR = None
    try:
        all_cats = []
        page = 1
        while True:
            batch = vendus("/products/categories/", {"page": page, "per_page": 200})
            if not isinstance(batch, list):
                batch = batch.get("categories", batch.get("data", batch.get("items", [])))
            if not batch:
                break
            all_cats.extend(batch)
            if len(batch) < 200:
                break
            page += 1
        result = {}
        for c in all_cats:
            cid = c.get("id")
            if cid is None:
                continue
            name = c.get("title") or c.get("name") or c.get("description") or str(cid)
            result[str(cid)] = name
        if not result:
            LAST_CATEGORIES_ERROR = f"0 catégorie résolue, raw sample={all_cats[:3]!r}"
            print(f"[vendus] _fetch_categories: {LAST_CATEGORIES_ERROR}")
        return result
    except Exception as e:
        LAST_CATEGORIES_ERROR = f"{type(e).__name__}: {e}"
        print(f"[vendus] _fetch_categories a échoué: {LAST_CATEGORIES_ERROR}")
        return {}


def get_catalog():
    """Retourne tous les produits actifs avec coût. Micro-cache 3 min."""
    return _ttl_get("catalog", 180, _fetch_catalog)


def _fetch_catalog():
    try:
        all_products = []
        page = 1
        while True:
            batch = vendus("/products/", {"page": page, "per_page": 200})
            if not isinstance(batch, list):
                batch = batch.get("products", batch.get("data", []))
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < 200:
                break
            page += 1

        cat_names = get_categories()   # {id: title} — noms réels, jamais figés

        result = {}
        for p in all_products:
            if p.get("status") != "on":
                continue
            gross  = float(p.get("gross_price", 0))
            supply = float(p.get("supply_price", 0))
            margin_pct = round((gross - supply) / gross * 100, 1) if gross and supply else None
            cat_id = p.get("category_id")
            result[p["title"].strip()] = {
                "id":            p["id"],
                "name":          p["title"],
                "category":      p.get("class_name", ""),
                "category_id":   cat_id,
                "category_name": cat_names.get(str(cat_id), ""),
                "price":         gross,
                "cost":          supply,
                "margin_pct":    margin_pct,
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


# Mapping category_id → groupe (dérivé de l'exploration du catalogue)
# Food = fait maison (Pâtisserie, Brunch, Sandwiches, Granola, Extras)
# Viennoiseries = achetées (Meia Lua) — marge plus basse, suivies à part
# Retail = Livres + Papeterie + café en sac + non catégorisé
FOOD_CAT_IDS         = {343042919, 343065085, 343055566, 343079649, 343052198}
VIENNOISERIE_CAT_IDS = {343054458}
DRINK_CAT_IDS        = {343052000, 343053226, 343046110, 343053550, 343055376}
RETAIL_CAT_IDS       = {343071668, 343077316}   # Livres, Papeterie
EXTRA_CAT_IDS        = set()   # fusionné dans Food (conservé pour compat imports)


def upsell_rate(docs):
    """% de tickets avec 2+ articles distincts (boissons+food = upsell réel)."""
    if not docs:
        return {"rate": 0, "multi": 0, "single": 0, "total": 0}
    multi  = sum(1 for d in docs if len(d.get("items", [])) >= 2)
    single = len(docs) - multi
    return {
        "rate":   round(multi / len(docs) * 100) if docs else 0,
        "multi":  multi,
        "single": single,
        "total":  len(docs),
    }


def category_mix(docs, catalog):
    """Répartition CA HT entre Boissons, Food et Extras."""
    by_group = {"Boissons": 0.0, "Food": 0.0, "Extras": 0.0, "Autre": 0.0}
    for d in docs:
        for item in d.get("items", []):
            name  = item.get("title", "").strip()
            total = float(item.get("amounts", {}).get("net_total", 0))  # HT
            cat   = catalog.get(name, {})
            cid   = cat.get("category_id")
            if cid in DRINK_CAT_IDS:
                by_group["Boissons"] += total
            elif cid in FOOD_CAT_IDS:
                by_group["Food"] += total
            elif cid in EXTRA_CAT_IDS:
                by_group["Extras"] += total
            else:
                by_group["Autre"] += total
    grand = sum(by_group.values()) or 1
    return [
        {"label": k, "amount": round(v, 2), "pct": round(v / grand * 100)}
        for k, v in by_group.items() if v > 0
    ]


def ticket_median(docs):
    """Ticket médian TTC (robuste face aux valeurs extrêmes) — ventes seules."""
    amounts = sorted(float(d.get("amount_gross", 0)) for d in docs if not d.get("_refund"))
    if not amounts:
        return None
    n = len(amounts)
    mid = n // 2
    return round(amounts[mid] if n % 2 else (amounts[mid-1] + amounts[mid]) / 2, 2)


def best_weekday():
    """Meilleur jour de la semaine sur tout l'historique disponible (90j)."""
    from datetime import date, timedelta
    today = date.today()
    since = (today - timedelta(days=90)).isoformat()
    try:
        raw = vendus("/documents/", {"since": since, "until": today.isoformat(), "status": "N"})
        if not isinstance(raw, list):
            raw = raw.get("docs", raw.get("data", []))
    except Exception:
        return None

    from collections import defaultdict
    import datetime as dt
    by_weekday = defaultdict(lambda: {"ca": 0.0, "days": set()})
    for d in raw:
        if d.get("type") not in SALE_TYPES:
            continue
        day_str = d.get("date", "")
        try:
            day_obj = dt.date.fromisoformat(day_str)
            wd = day_obj.strftime("%A")  # Monday, Tuesday…
            by_weekday[wd]["ca"]   += float(d.get("amount_gross", 0))
            by_weekday[wd]["days"].add(day_str)
        except ValueError:
            pass

    if not by_weekday:
        return None

    WD_FR = {"Monday":"Lundi","Tuesday":"Mardi","Wednesday":"Mercredi",
              "Thursday":"Jeudi","Friday":"Vendredi","Saturday":"Samedi","Sunday":"Dimanche"}
    result = []
    for wd, stats in by_weekday.items():
        n = len(stats["days"])
        result.append({
            "day":     WD_FR.get(wd, wd),
            "avg_ca":  round(stats["ca"] / n, 2) if n else 0,
            "n_days":  n,
        })
    result.sort(key=lambda x: x["avg_ca"], reverse=True)
    return result


def wow_growth():
    """Croissance semaine en cours vs semaine précédente (même 7 jours)."""
    from datetime import date, timedelta
    today = date.today()
    # Semaine en cours : 7 derniers jours
    since_cur  = (today - timedelta(days=6)).isoformat()
    # Semaine précédente : les 7 jours avant ça
    since_prev = (today - timedelta(days=13)).isoformat()
    until_prev = (today - timedelta(days=7)).isoformat()
    try:
        raw = vendus("/documents/", {
            "since": since_prev, "until": today.isoformat(), "status": "N"
        })
        if not isinstance(raw, list):
            raw = raw.get("docs", raw.get("data", []))
    except Exception:
        return None

    cur_ca = prev_ca = 0.0
    cur_nb = prev_nb = 0
    for d in raw:
        if d.get("type") not in SALE_TYPES:
            continue
        day = d.get("date", "")
        ca  = float(d.get("amount_gross", 0))
        if day >= since_cur:
            cur_ca += ca; cur_nb += 1
        elif day <= until_prev:
            prev_ca += ca; prev_nb += 1

    growth_ca = round((cur_ca - prev_ca) / prev_ca * 100) if prev_ca else None
    growth_nb = round((cur_nb - prev_nb) / prev_nb * 100) if prev_nb else None
    return {
        "cur_ca":   round(cur_ca, 2),
        "prev_ca":  round(prev_ca, 2),
        "cur_nb":   cur_nb,
        "prev_nb":  prev_nb,
        "growth_ca": growth_ca,
        "growth_nb": growth_nb,
    }


def ticket_distribution(docs):
    """Répartition des tickets par tranche de montant TTC."""
    buckets = [
        ("0–5 €",   0,   5),
        ("5–10 €",  5,  10),
        ("10–20 €", 10, 20),
        ("20+ €",   20, float("inf")),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    for d in docs:
        amt = float(d.get("amount_gross", 0))
        for label, lo, hi in buckets:
            if lo <= amt < hi:
                counts[label] += 1
                break
    total = len(docs) or 1
    return [
        {"label": label, "count": counts[label], "pct": round(counts[label] / total * 100)}
        for label, _, _ in buckets
    ]


def cumulative_curve(docs):
    """Courbe cumulative du CA TTC transaction par transaction."""
    points = []
    for d in docs:
        lt = d.get("local_time", "")
        try:
            time_str = lt[11:16]  # "HH:MM"
        except (TypeError, IndexError):
            continue
        points.append({
            "time": time_str,
            "ca":   float(d.get("amount_gross", 0)),
            "nb":   d.get("number", ""),
        })

    # Trier par heure
    points.sort(key=lambda p: p["time"])

    # Construire la série cumulative
    cumul = 0.0
    result = [{"time": points[0]["time"][:2] + "h00", "ca_cum": 0.0, "ca_tx": 0.0, "nb": ""}] if points else []
    for p in points:
        cumul += p["ca"]
        result.append({
            "time":   p["time"].replace(":", "h"),
            "ca_cum": round(cumul, 2),
            "ca_tx":  p["ca"],
            "nb":     p["nb"],
        })
    return result


def daily_breakdown(docs):
    """Agrège les docs par date — pour le graphe CA journalier (périodes multi-jours)."""
    by_day = {}
    for doc in docs:
        raw = doc.get("local_time") or doc.get("date") or ""
        d = raw[:10]
        if not d:
            continue
        if d not in by_day:
            by_day[d] = {"ca_ht": 0.0, "ca_ttc": 0.0, "nb": 0}
        by_day[d]["ca_ht"]  += float(doc.get("amount_net",   0))
        by_day[d]["ca_ttc"] += float(doc.get("amount_gross", 0))
        by_day[d]["nb"]     += 1
    return [
        {"date": d, "ca_ht": round(v["ca_ht"], 2), "ca_ttc": round(v["ca_ttc"], 2), "nb": v["nb"]}
        for d, v in sorted(by_day.items())
    ]


def daily_economics(docs, catalog, n_days=1, from_date=None, to_date=None, cogs_agg=None,
                    open_days_override=None):
    """
    P&L entièrement en HT (hors taxes) — pour 1 jour ou une période.
    CA HT  = amount_net  (Vendus)
    COGS HT = supply_price × qty (prix d'achat HT dans catalogue Vendus)
    Charges = COUT_TOTAL_JOUR × jours_ouvrés_réels_dans_la_période
    → on compte les vrais jours d'ouverture (lun/jeu/ven/sam/dim) pour ne
      pas gonfler les charges sur des périodes incluant des jours calendaires
      hors ouverture.
    """
    from config import (
        TVA_MOYENNE_BLENDED, AMORTISSEMENT_MOIS,
        JOURS_OUVERTS_MOIS, count_open_days,
    )

    # Jours d'ouverture effectifs dans la période.
    # Priorité au réel observé (jours avec ventes, passé par l'appelant) —
    # robuste aux changements d'horaires ; fallback calendrier théorique.
    if open_days_override is not None:
        open_days = max(1, open_days_override)
    elif from_date is not None and to_date is not None:
        open_days = count_open_days(from_date, to_date)
    else:
        open_days = max(1, round(n_days * 5 / 7))

    # ── Charges live depuis Supabase ─────────────────────────────────────────
    # Appel léger (~15ms) — résultat utilisé pour les 4 KPIs économie
    try:
        charges_rows  = _supa_get_economics("charges_fixes", {"active": "eq.true"})
        employee_rows = _supa_get_economics("employees",     {"active": "eq.true"})
    except Exception:
        charges_rows  = []
        employee_rows = []

    # Total charges fixes mensuelles
    def _to_monthly(amount, freq):
        if freq == "quarterly": return amount / 3
        if freq == "annual":    return amount / 12
        return amount

    total_fixes_mois = sum(_to_monthly(float(c["amount"]), c.get("frequency","monthly"))
                           for c in charges_rows)

    # Total personnel lissé mensuel (TSU + 13e/14e + repas)
    TSU_RATE    = 0.2375
    REPAS_JOURS = 242   # ~11 mois × 22 jours
    total_perso_mois = 0.0
    for e in employee_rows:
        gross = float(e.get("gross_monthly", 0))
        if e.get("type") == "extra":
            total_perso_mois += gross
        else:
            meal    = float(e.get("meal_card_daily", 10.20))
            tsu     = 0.0 if e.get("tsu_exempt") else TSU_RATE
            monthly = (gross * 14 * (1 + tsu) + meal * REPAS_JOURS) / 12
            total_perso_mois += monthly

    total_charges_mois = total_fixes_mois + total_perso_mois

    # Source unique : Supabase. Pas de fallback BP — si vide/injoignable,
    # charges = 0 et le front affiche un warning (charges_source).
    charges_source = "supabase" if total_charges_mois > 0 else "indisponible"

    cout_jour        = total_charges_mois / JOURS_OUVERTS_MOIS
    cout_fixe_jour   = total_fixes_mois   / JOURS_OUVERTS_MOIS
    cout_perso_jour  = total_perso_mois   / JOURS_OUVERTS_MOIS
    amort_jour       = AMORTISSEMENT_MOIS / JOURS_OUVERTS_MOIS

    ca_ttc     = 0.0   # TTC  — affiché pour info
    ca_ht      = 0.0   # HT   — base des calculs de rentabilité
    cogs_ht    = 0.0   # COGS HT (supply_price × qty) — produits avec coût connu
    covered_ht = 0.0   # CA HT des items dont le coût est connu (couverture COGS)
    items_ht   = 0.0   # CA HT total des items (peut différer de ca_ht si remises doc)
    tva_col    = 0.0   # TVA collectée = ca_ttc - ca_ht

    for d in docs:
        # CA au niveau du document (net = HT, gross = TTC)
        ca_ttc += float(d.get("amount_gross", 0))
        ca_ht  += float(d.get("amount_net",   0))

        if cogs_agg is None:
            # COGS item par item (supply_price est HT dans Vendus)
            for item in d.get("items", []):
                qty    = float(item.get("qty", 0))
                name   = item.get("title", "").strip()   # strip: titres Vendus ont parfois des espaces
                net    = float(item.get("amounts", {}).get("net_total", 0))
                items_ht += net
                cat = catalog.get(name, {})
                if cat.get("cost"):
                    cogs_ht    += cat["cost"] * qty
                    covered_ht += net

    if cogs_agg is not None:
        # Agrégats pré-calculés (cache daily_summary) — pas besoin des items
        cogs_ht, covered_ht, items_ht = cogs_agg

    tva_col = round(ca_ttc - ca_ht, 2)

    # ── Couverture COGS : % du CA dont on connaît réellement le coût ─────────
    cogs_coverage_pct = round(covered_ht / items_ht * 100, 1) if items_ht else None

    # ── Taux de marge : uniquement le réel mesuré (aucune hypothèse BP) ──────
    # Marge réelle mesurée sur la partie couverte du CA.
    marge_rate_real = (covered_ht - cogs_ht) / covered_ht if covered_ht > 0 else None

    # Seuil calculable seulement si marge réelle mesurable ET charges connues
    if marge_rate_real is not None and 0 < marge_rate_real < 1 and cout_jour > 0:
        seuil_margin_rate = marge_rate_real
        seuil_margin_src  = "reelle"
        seuil_ca_jour     = cout_jour / seuil_margin_rate
        seuil_ca_jour_ttc = seuil_ca_jour * (1 + TVA_MOYENNE_BLENDED)
    else:
        # Pas de COGS mesurable ou charges absentes → pas de seuil affichable
        seuil_margin_rate = None
        seuil_margin_src  = "indisponible"
        seuil_ca_jour     = None
        seuil_ca_jour_ttc = None

    # Charges × jours_ouvrés_réels (live Supabase)
    cout_total   = round(cout_jour       * open_days, 2)
    cout_fixe    = round(cout_fixe_jour  * open_days, 2)
    cout_perso   = round(cout_perso_jour * open_days, 2)
    amort        = round(amort_jour      * open_days, 2)
    seuil_ca     = round(seuil_ca_jour     * open_days, 2) if seuil_ca_jour     is not None else None  # HT
    seuil_ca_ttc = round(seuil_ca_jour_ttc * open_days, 2) if seuil_ca_jour_ttc is not None else None  # TTC

    # Marge brute HT — 100 % basée sur le COGS réel mesuré.
    # Taux réel mesuré sur le CA couvert, extrapolé au CA total.
    # is_estimated_margin = true si la couverture est partielle (extrapolation).
    is_estimated_margin = False
    if marge_rate_real is not None and ca_ht:
        marge_ht     = round(ca_ht * marge_rate_real, 2)
        marge_ht_pct = round(marge_rate_real * 100, 1)
        is_estimated_margin = (cogs_coverage_pct or 0) < 95
    else:
        marge_ht = marge_ht_pct = None

    # EBITDA HT = marge brute HT − charges totales HT de la période
    ebitda_ht = round(marge_ht - cout_total, 2) if marge_ht is not None else None

    # Seuil rentabilité — comparaison TTC vs TTC (ce que tu vois en caisse)
    if seuil_ca_ttc is not None:
        manque_seuil = round(max(0, seuil_ca_ttc - ca_ttc), 2)
        pct_seuil    = round(ca_ttc / seuil_ca_ttc * 100) if seuil_ca_ttc else 0
    else:
        manque_seuil = None
        pct_seuil    = 0

    return {
        # CA
        "ca_ttc":          round(ca_ttc, 2),
        "ca_ht":           round(ca_ht, 2),
        "tva_collectee":   tva_col,
        # Coûts
        "cogs_ht":         round(cogs_ht, 2),
        # Marge brute HT
        "marge_brute_ht":          marge_ht,
        "marge_brute_ht_pct":      marge_ht_pct,
        "marge_is_estimated":       is_estimated_margin,
        # Charges HT/période
        "open_days":        open_days,           # vrais jours ouvrés dans la période
        "cout_fixe_periode":   cout_fixe,        # total fixes sur la période
        "cout_perso_periode":  cout_perso,       # total perso sur la période
        "cout_total_periode":  cout_total,       # total charges sur la période
        "cout_jour":           round(cout_jour, 2),        # coût par jour ouvré
        # Compatibilité anciens noms (dashboard.js)
        "cout_fixe_jour":   cout_fixe,
        "cout_perso_jour":  cout_perso,
        "cout_total_jour":  cout_total,
        "amort_jour":       amort,
        # EBITDA HT
        "ebitda_ht":        ebitda_ht,
        # Seuil (TTC en principal — ce qu'on lit sur la caisse)
        "seuil_ca_ttc":     seuil_ca_ttc,
        "seuil_ca_ht":      seuil_ca,       # HT gardé pour info
        "manque_seuil":     manque_seuil,   # en TTC
        "pct_seuil":        pct_seuil,      # basé sur TTC vs TTC
        "charges_source":   charges_source, # "supabase" ou "fallback_bp"
        # Fiabilité du COGS
        "cogs_coverage_pct": cogs_coverage_pct,   # % du CA avec coût connu
        "seuil_margin_src":  seuil_margin_src,    # "reelle" ou "bp"
        "seuil_margin_pct":  round(seuil_margin_rate * 100, 1) if seuil_margin_rate else None,
    }


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


def product_stats_from_docs(docs_with_items, catalog):
    """Dérive les stats produits depuis des docs déjà chargés (sans appel API)."""
    by_product = defaultdict(lambda: {"rev_ttc": 0.0, "rev_ht": 0.0, "qty": 0, "days": set()})
    for detail in docs_with_items:
        if not detail:
            continue
        day = detail.get("date", "")[:10]
        for item in detail.get("items", []):
            name    = item.get("title", "—").strip()
            qty     = float(item.get("qty", 0))
            amounts = item.get("amounts", {})
            by_product[name]["rev_ttc"] += float(amounts.get("gross_total", item.get("gross_total", 0)))
            by_product[name]["rev_ht"]  += float(amounts.get("net_total",   item.get("net_total",   0)))
            by_product[name]["qty"]     += qty
            by_product[name]["days"].add(day)

    result = []
    for name, stats in by_product.items():
        days_sold = len(stats["days"])
        rev_ttc   = round(stats["rev_ttc"], 2)
        rev_ht    = round(stats["rev_ht"],  2)
        cat_info  = catalog.get(name)
        cost_ht   = round(cat_info["cost"] * stats["qty"], 2) if cat_info and cat_info.get("cost") else None
        margin    = round((rev_ht - cost_ht) / rev_ht * 100, 1) if rev_ht and cost_ht else None
        result.append({
            "name": name, "revenue": rev_ttc, "rev_ht": rev_ht,
            "qty": int(stats["qty"]), "days_sold": days_sold,
            "avg_day": round(rev_ttc / days_sold, 2) if days_sold else 0,
            "cost_ht": cost_ht, "margin_pct": margin,
        })
    return sorted(result, key=lambda x: x["revenue"], reverse=True)


def product_stats_7d(since: str, until: str):
    """CA total et nb jours vendus par produit sur la période (fallback avec appels API)."""
    try:
        raw = vendus("/documents/", {"since": since, "until": until, "status": "N"})
        if not isinstance(raw, list):
            raw = raw.get("docs", raw.get("data", []))
        ft_ids = [d["id"] for d in raw if d.get("type") in SALE_TYPES]
    except Exception:
        return []

    by_product = defaultdict(lambda: {"rev_ttc": 0.0, "rev_ht": 0.0, "qty": 0, "days": set()})

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
            name    = item.get("title", "—").strip()
            qty     = float(item.get("qty", 0))
            amounts = item.get("amounts", {})
            by_product[name]["rev_ttc"] += float(amounts.get("gross_total", 0))
            by_product[name]["rev_ht"]  += float(amounts.get("net_total",   0))
            by_product[name]["qty"]     += qty
            by_product[name]["days"].add(day)

    catalog = get_catalog()
    result = []
    for name, stats in by_product.items():
        days_sold = len(stats["days"])
        rev_ttc   = round(stats["rev_ttc"], 2)
        rev_ht    = round(stats["rev_ht"],  2)
        cat_info  = catalog.get(name)
        cost_ht   = round(cat_info["cost"] * stats["qty"], 2) if cat_info and cat_info.get("cost") else None
        margin    = round((rev_ht - cost_ht) / rev_ht * 100, 1) if rev_ht and cost_ht else None
        result.append({
            "name":       name,
            "revenue":    rev_ttc,
            "rev_ht":     rev_ht,
            "qty":        int(stats["qty"]),
            "days_sold":  days_sold,
            "avg_day":    round(rev_ttc / days_sold, 2) if days_sold else 0,
            "cost_ht":    cost_ht,
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
        return None   # échec API ≠ zéro vente — le front affiche un warning

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
    """Top produits par quantité vendue.
    Display: TTC (prix client). Marge: HT vs HT (correct fiscalement)."""
    catalog = catalog or {}
    by_product = defaultdict(lambda: {"qty": 0, "rev_ttc": 0.0, "rev_ht": 0.0, "cost_ht": 0.0})
    for d in docs:
        for item in d.get("items", []):
            title = item.get("title", "—").strip()
            qty   = float(item.get("qty", 0))
            amounts = item.get("amounts", {})
            by_product[title]["qty"]     += qty
            by_product[title]["rev_ttc"] += float(amounts.get("gross_total", 0))
            by_product[title]["rev_ht"]  += float(amounts.get("net_total",   0))
            cat_info = catalog.get(title)
            if cat_info and cat_info.get("cost"):
                by_product[title]["cost_ht"] += cat_info["cost"] * qty

    ranked = sorted(by_product.items(), key=lambda x: x[1]["qty"], reverse=True)
    result = []
    for name, s in ranked[:n]:
        rev_ttc  = round(s["rev_ttc"], 2)
        rev_ht   = round(s["rev_ht"],  2)
        cost_ht  = round(s["cost_ht"], 2)
        avg_ttc  = round(rev_ttc / s["qty"], 2) if s["qty"] else 0
        # Marge brute HT = (CA HT - COGS HT) / CA HT
        margin   = round((rev_ht - cost_ht) / rev_ht * 100, 1) if rev_ht and cost_ht else None
        result.append({
            "name":       name,
            "qty":        int(s["qty"]),
            "revenue":    rev_ttc,   # TTC — affiché
            "rev_ht":     rev_ht,    # HT — pour vérif
            "avg":        avg_ttc,   # prix unit. TTC
            "cost_ht":    cost_ht,
            "margin_pct": margin,    # % HT
        })
    return result


def recent_docs(docs, n=10):
    """Liste des transactions, plus récente d'abord. n=None → toutes."""
    sorted_docs = sorted(
        docs,
        key=lambda d: d.get("local_time", d.get("date", "")),
        reverse=True,
    )
    if n is not None:
        sorted_docs = sorted_docs[:n]
    result = []
    for d in sorted_docs:
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
