"""Test de faisabilité : tirer les orders Revolut Merchant de juillet
et inspecter les champs carte disponibles (last4, expiry, fingerprint ?).

Usage : python3 scripts/test_revolut_orders.py
Lit REVOLUT_MERCHANT_API_KEY depuis .env (jamais dans le code).
"""
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Charge .env
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("REVOLUT_MERCHANT_API_KEY")
if not API_KEY:
    sys.exit("REVOLUT_MERCHANT_API_KEY manquante dans .env")

BASE = "https://merchant.revolut.com"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Revolut-Api-Version": "2024-09-01",
}


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def fetch_orders(from_date, to_date, limit_pages=50):
    """Pagine les orders entre deux dates ISO."""
    orders = []
    created_before = None
    for _ in range(limit_pages):
        params = {
            "limit": 100,
            "from_created_date": from_date,
            "to_created_date": to_date,
        }
        if created_before:
            params["created_before"] = created_before
        batch = get("/api/orders", params)
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 100:
            break
        created_before = batch[-1]["created_at"]
    return orders


def main():
    orders = fetch_orders("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z")
    print(f"{len(orders)} orders récupérés pour juillet")
    states = Counter(o.get("state") for o in orders)
    print("États :", dict(states))

    # Inspecte le détail d'un order complété pour voir les champs carte
    completed = [o for o in orders if o.get("state") == "completed"]
    if not completed:
        print("Aucun order 'completed' — rien à inspecter")
        return

    sample = get(f"/api/orders/{completed[0]['id']}")
    print("\n--- Order complet (échantillon) ---")
    print(json.dumps(sample, indent=2, ensure_ascii=False))

    # Résume les clés carte trouvées sur les 10 premiers complétés
    print("\n--- Champs payment_method vus (10 premiers orders) ---")
    keys_seen = Counter()
    for o in completed[:10]:
        detail = get(f"/api/orders/{o['id']}")
        for p in detail.get("payments", []):
            pm = p.get("payment_method", {})
            for k in pm:
                keys_seen[k] += 1
            cd = pm.get("card") or pm
            print(
                f"  {o['id'][:8]}… brand={cd.get('card_brand') or cd.get('brand')} "
                f"last4={cd.get('card_last_four') or cd.get('last_four')} "
                f"expiry={cd.get('card_expiry') or (str(cd.get('expiry_month')) + '/' + str(cd.get('expiry_year')) if cd.get('expiry_month') else '?')} "
                f"fingerprint={'OUI' if cd.get('fingerprint') else 'non'}"
            )
    print("\nClés présentes :", dict(keys_seen))


if __name__ == "__main__":
    main()
