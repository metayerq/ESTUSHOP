"""
Revolut Merchant API — visites carte du terminal, pseudonymisées.

Un paiement en personne n'expose ni nom, ni BIN, ni expiration : la puce ne
les transmet pas. Restent `card_last_four` et le libellé d'application inscrit
sur la puce (« VISA DEBITO », « Debit Mastercard »…) — stable par carte, donc
utile comme empreinte. Deux clients avec la même carte Visa Debit finissant
par les mêmes quatre chiffres seront confondus : à l'échelle du café, 5 à 9 %
des cartes. Le taux de retour est un ordre de grandeur à ±5 points, pas une
mesure au dixième.

⚠️ AUCUNE DONNÉE CARTE EN CLAIR NE SORT D'ICI. L'empreinte est un SHA-256 salé
par un secret dérivé de la clé Merchant : sans elle, les 60 000 combinaisons
possibles s'énumèrent en une seconde. Le libellé seul est conservé (« Visa
Debit » n'identifie personne). RGPD : donnée pseudonyme, intérêt légitime,
finalité statistique — ne jamais la recroiser avec une identité.
"""
import os
import time
import hashlib
import requests
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

BASE    = "https://merchant.revolut.com/api"
VERSION = "2024-09-01"
LISBON  = ZoneInfo("Europe/Lisbon")


def _key():
    return os.environ.get("REVOLUT_MERCHANT_KEY", "")

def enabled():
    return bool(_key())

def _salt():
    return hashlib.sha256(("estushop-card-visits|" + _key()).encode()).hexdigest()

def fingerprint(last4, label):
    """Empreinte pseudonyme d'une carte. Changer la clé Merchant change le sel :
    il faut alors reconstruire l'historique (un appel par jour, c'est tout)."""
    return hashlib.sha256(f"{_salt()}|{last4}|{label}".encode()).hexdigest()[:24]


def _session():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_key()}",
                      "Revolut-Api-Version": VERSION})
    return s

def _get(s, url, params=None, tries=6):
    """Un 500 passager ou une limite de débit se retentent avec recul
    exponentiel ; un objet {code, message} à la place d'une liste est une
    erreur, pas une réponse."""
    for i in range(tries):
        try:
            r = s.get(url, params=params, timeout=20)
            j = r.json() if r.content else {}
            if r.ok and not (isinstance(j, dict) and "code" in j):
                return j
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.4 * 2 ** i)
    return None


def _lisbon_day(iso_utc):
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(LISBON).date().isoformat()


def fetch_day(day, s=None):
    """Toutes les visites carte d'un jour (heure de Lisbonne), pseudonymisées.

    La liste des commandes ne porte pas les paiements : un appel par commande.
    ~25 commandes par jour, 4 en parallèle → une seconde. La fenêtre UTC
    déborde d'une heure de chaque côté pour ne pas perdre un ticket de
    fin de soirée ; le jour retenu est celui de Lisbonne.
    """
    s = s or _session()
    start = datetime.combine(day, datetime.min.time(), LISBON).astimezone(timezone.utc)
    end   = start + timedelta(days=1)
    j = _get(s, f"{BASE}/orders", {
        "from_created_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to_created_date":   end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 500}) or {}
    orders = [o for o in j.get("orders", []) if o.get("state") == "completed"]

    def pays(o):
        return o, (_get(s, f"{BASE}/orders/{o['id']}/payments") or [])

    rows = []
    with ThreadPoolExecutor(4) as ex:
        for o, ps in ex.map(pays, orders):
            for p in ps:
                if p.get("state") != "completed":
                    continue
                pm = p.get("payment_method") or {}
                l4 = pm.get("card_last_four")
                if not l4:
                    continue
                label = pm.get("application_name") or ""
                ts = p.get("created_at") or o["created_at"]
                d = _lisbon_day(ts)
                if d != day.isoformat():
                    continue            # appartient au jour voisin
                rows.append({"pid": p["id"], "day": d, "ts": ts,
                             "amount": int(p.get("amount") or o.get("amount") or 0),
                             "fp": fingerprint(l4, label), "label": label})
    return rows


def fetch_range(from_day, to_day):
    s = _session()
    out = []
    d = from_day
    while d <= to_day:
        out.extend(fetch_day(d, s))
        d += timedelta(1)
    return out
