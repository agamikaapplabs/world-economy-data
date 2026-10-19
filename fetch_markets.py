from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "raw" / "markets.json"
OUT.parent.mkdir(exist_ok=True)

YAHOO = [
    ("gold", "Gold", "GC=F", "metals", "USD"),
    ("silver", "Silver", "SI=F", "metals", "USD"),
    ("sp500", "S&P 500", "^GSPC", "indices", "index"),
    ("nasdaq", "NASDAQ Composite", "^IXIC", "indices", "index"),
    ("nifty50", "NIFTY 50", "^NSEI", "indices", "index"),
    ("ftse100", "FTSE 100", "^FTSE", "indices", "index"),
    ("nikkei", "Nikkei 225", "^N225", "indices", "index"),
    ("hangseng", "Hang Seng", "^HSI", "indices", "index"),

    ("apple", "Apple", "AAPL", "us_tech", "USD"),
    ("microsoft", "Microsoft", "MSFT", "us_tech", "USD"),
    ("nvidia", "NVIDIA", "NVDA", "us_tech", "USD"),
    ("alphabet", "Alphabet", "GOOGL", "us_tech", "USD"),
    ("amazon", "Amazon", "AMZN", "us_tech", "USD"),
    ("meta", "Meta", "META", "us_tech", "USD"),
    ("broadcom", "Broadcom", "AVGO", "us_tech", "USD"),
    ("tesla", "Tesla", "TSLA", "us_tech", "USD"),

    ("reliance", "Reliance Industries", "RELIANCE.NS", "india_stocks", "INR"),
    ("tcs", "TCS", "TCS.NS", "india_stocks", "INR"),
    ("hdfcbank", "HDFC Bank", "HDFCBANK.NS", "india_stocks", "INR"),
    ("bharti", "Bharti Airtel", "BHARTIARTL.NS", "india_stocks", "INR"),
    ("icicibank", "ICICI Bank", "ICICIBANK.NS", "india_stocks", "INR"),
    ("infosys", "Infosys", "INFY.NS", "india_stocks", "INR"),
    ("lt", "Larsen & Toubro", "LT.NS", "india_stocks", "INR"),
    ("sbi", "State Bank of India", "SBIN.NS", "india_stocks", "INR"),

    ("asml", "ASML", "ASML.AS", "europe_stocks", "EUR"),
    ("sap", "SAP", "SAP.DE", "europe_stocks", "EUR"),
    ("siemens_eu", "Siemens", "SIE.DE", "europe_stocks", "EUR"),
    ("schneider", "Schneider Electric", "SU.PA", "europe_stocks", "EUR"),
    ("airbus", "Airbus", "AIR.PA", "europe_stocks", "EUR"),
    ("lvmh", "LVMH", "MC.PA", "europe_stocks", "EUR"),
    ("novo", "Novo Nordisk", "NOVO-B.CO", "europe_stocks", "DKK"),
    ("shell", "Shell", "SHEL.L", "europe_stocks", "GBp"),

    ("caterpillar", "Caterpillar", "CAT", "heavy_industry", "USD"),
    ("deere", "Deere", "DE", "heavy_industry", "USD"),
    ("gevernova", "GE Vernova", "GEV", "heavy_industry", "USD"),
    ("siemens_heavy", "Siemens", "SIE.DE", "heavy_industry", "EUR"),
    ("abb", "ABB", "ABBN.SW", "heavy_industry", "CHF"),
    ("honeywell", "Honeywell", "HON", "heavy_industry", "USD"),
    ("lt_heavy", "Larsen & Toubro", "LT.NS", "heavy_industry", "INR"),
    ("mhi", "Mitsubishi Heavy Industries", "7011.T", "heavy_industry", "JPY"),

    ("lockheed", "Lockheed Martin", "LMT", "defence", "USD"),
    ("rtx", "RTX", "RTX", "defence", "USD"),
    ("northrop", "Northrop Grumman", "NOC", "defence", "USD"),
    ("generaldynamics", "General Dynamics", "GD", "defence", "USD"),
    ("bae", "BAE Systems", "BA.L", "defence", "GBp"),
    ("rheinmetall", "Rheinmetall", "RHM.DE", "defence", "EUR"),
    ("leonardo", "Leonardo", "LDO.MI", "defence", "EUR"),
    ("thales", "Thales", "HO.PA", "defence", "EUR"),

    ("us3m", "US Treasury 3M", "^IRX", "bond_yields", "%"),
    ("us5y", "US Treasury 5Y", "^FVX", "bond_yields", "%"),
    ("us10y", "US Treasury 10Y", "^TNX", "bond_yields", "%"),
    ("us30y", "US Treasury 30Y", "^TYX", "bond_yields", "%"),

    ("brent", "Brent Crude", "BZ=F", "commodities", "USD"),
    ("wti", "WTI Crude", "CL=F", "commodities", "USD"),
    ("natgas", "Natural Gas", "NG=F", "commodities", "USD"),
    ("copper", "Copper", "HG=F", "commodities", "USD"),
    ("wheat", "Wheat", "ZW=F", "commodities", "USD"),
    ("corn", "Corn", "ZC=F", "commodities", "USD"),

    ("vix", "VIX", "^VIX", "risk", "index"),
]

FX = [
    ("usd_inr", "USD/INR", "INR", "INR per USD"),
    ("usd_eur", "USD/EUR", "EUR", "EUR per USD"),
    ("usd_gbp", "USD/GBP", "GBP", "GBP per USD"),
    ("usd_jpy", "USD/JPY", "JPY", "JPY per USD"),
    ("usd_chf", "USD/CHF", "CHF", "CHF per USD"),
]

UA = "Mozilla/5.0 GlobalMarketsCollector/5.0"
OVERLAP_DAYS = 10


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Update market data incrementally. Existing historical observations are kept; "
            "only a short overlap window is fetched on normal runs."
        )
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Explicitly rebuild five years of market history instead of fetching only the recent delta.",
    )
    return parser.parse_args()


def get_json(url, timeout=25):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Connection": "close"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def load_previous():
    try:
        if OUT.exists():
            raw = json.loads(OUT.read_text(encoding="utf-8"))
            if isinstance(raw.get("instruments"), dict):
                return raw
    except Exception:
        pass
    return {"instruments": {}}


def old_instrument(previous, iid):
    x = (previous.get("instruments") or {}).get(iid)
    return x if isinstance(x, dict) else None


def clean_history(items):
    by_date = {}
    for p in items or []:
        try:
            d = str(p["date"])
            v = float(p["value"])
            if math.isfinite(v):
                by_date[d] = {"date": d, "value": round(v, 6)}
        except Exception:
            continue
    return [by_date[k] for k in sorted(by_date)]


def merge_history(old_history, new_history):
    return clean_history([*(old_history or []), *(new_history or [])])


def perf(history, days):
    if len(history) < 2:
        return None
    end = date.fromisoformat(history[-1]["date"])
    target = end - timedelta(days=days)
    base = history[0]
    for p in history:
        if date.fromisoformat(p["date"]) <= target:
            base = p
        else:
            break
    if not base["value"]:
        return None
    return (history[-1]["value"] / base["value"] - 1) * 100


def yahoo_url(symbol, old, full_history):
    base = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    common = "interval=1d&includePrePost=false&events=div%2Csplits"
    old_history = clean_history((old or {}).get("history") or [])
    if full_history or not old_history:
        return f"{base}?range=5y&{common}", "full"

    last = date.fromisoformat(old_history[-1]["date"])
    start = last - timedelta(days=OVERLAP_DAYS)
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    period2 = int(tomorrow.timestamp())
    return f"{base}?period1={period1}&period2={period2}&{common}", "incremental"


def yahoo_one(row, old, full_history):
    iid, name, symbol, group, unit = row
    url, mode = yahoo_url(symbol, old, full_history)
    raw = get_json(url)
    result = raw["chart"]["result"][0]
    ts = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote_data.get("close") or []
    fresh = []
    for t, v in zip(ts, closes):
        if v is None or not math.isfinite(float(v)):
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        fresh.append({"date": d, "value": round(float(v), 6)})
    fresh = clean_history(fresh)
    if not fresh:
        raise RuntimeError("No valid closes")

    old_history = [] if full_history else clean_history((old or {}).get("history") or [])
    history = merge_history(old_history, fresh)
    latest = history[-1]["value"]
    previous_close = history[-2]["value"] if len(history) > 1 else None
    change = latest - previous_close if previous_close is not None else None
    change_pct = change / previous_close * 100 if previous_close else None
    meta = result.get("meta", {})
    market_ts = meta.get("regularMarketTime") or (ts[-1] if ts else None)

    old_dates = {p["date"] for p in old_history}
    added = sum(1 for p in history if p["date"] not in old_dates)
    return {
        "id": iid,
        "name": name,
        "symbol": symbol,
        "group": group,
        "unit": unit,
        "latest": latest,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "day_change_pct": change_pct,
        "market_time": datetime.fromtimestamp(market_ts, tz=timezone.utc).isoformat() if market_ts else history[-1]["date"],
        "currency": meta.get("currency") or (old or {}).get("currency"),
        "exchange": meta.get("exchangeName") or (old or {}).get("exchange"),
        "source": "Yahoo Finance chart",
        "history": history,
        "history_fetch": mode,
        "history_points_added": added,
        "performance_pct": {
            "1W": perf(history, 7),
            "1M": perf(history, 30),
            "3M": perf(history, 91),
            "6M": perf(history, 182),
            "1Y": perf(history, 365),
            "3Y": perf(history, 1095),
            "5Y": perf(history, 1826),
        },
    }


def fx_start(old, full_history):
    end = datetime.now(timezone.utc).date()
    old_history = clean_history((old or {}).get("history") or [])
    if full_history or not old_history:
        try:
            return end.replace(year=end.year - 5), "full"
        except ValueError:
            return end - timedelta(days=1826), "full"
    last = date.fromisoformat(old_history[-1]["date"])
    return last - timedelta(days=OVERLAP_DAYS), "incremental"


def fx_one(row, old, full_history):
    iid, name, currency, unit = row
    end = datetime.now(timezone.utc).date()
    start, mode = fx_start(old, full_history)
    url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?from=USD&to={currency}"
    try:
        raw = get_json(url)
    except Exception:
        if mode == "full":
            start = end - timedelta(days=370)
            url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?from=USD&to={currency}"
            raw = get_json(url)
        else:
            raise

    fresh = []
    for d, rates in sorted(raw.get("rates", {}).items()):
        v = rates.get(currency)
        if v is not None:
            fresh.append({"date": d, "value": float(v)})
    fresh = clean_history(fresh)
    if not fresh:
        raise RuntimeError("No FX history")

    old_history = [] if full_history else clean_history((old or {}).get("history") or [])
    history = merge_history(old_history, fresh)
    latest = history[-1]["value"]
    previous_close = history[-2]["value"] if len(history) > 1 else None
    change_pct = (latest / previous_close - 1) * 100 if previous_close else None
    old_dates = {p["date"] for p in old_history}
    added = sum(1 for p in history if p["date"] not in old_dates)

    return {
        "id": iid,
        "name": name,
        "symbol": name,
        "group": "currencies",
        "unit": unit,
        "latest": latest,
        "previous_close": previous_close,
        "change": latest - previous_close if previous_close is not None else None,
        "change_pct": change_pct,
        "day_change_pct": change_pct,
        "market_time": history[-1]["date"],
        "currency": currency,
        "exchange": "Frankfurter",
        "source": "Frankfurter",
        "history": history,
        "history_fetch": mode,
        "history_points_added": added,
        "performance_pct": {
            "1W": perf(history, 7),
            "1M": perf(history, 30),
            "3M": perf(history, 91),
            "6M": perf(history, 182),
            "1Y": perf(history, 365),
            "3Y": perf(history, 1095),
            "5Y": perf(history, 1826),
        },
    }


def stale_copy(old, error):
    x = json.loads(json.dumps(old))
    x["fetch_status"] = "stale-cache"
    x["last_fetch_error"] = str(error)
    x["history_points_added"] = 0
    return x


def main():
    args = parse_args()
    previous = load_previous()
    instruments = {}
    failures = []
    stale = []

    mode = "FULL HISTORY" if args.full_history else "INCREMENTAL HISTORY"
    print(f"Global Markets Collector v5.0 · {mode}")
    if not args.full_history:
        print(f"Existing history is retained; only the last ~{OVERLAP_DAYS} days are re-fetched and merged.")
    print("=" * 78)

    for row in YAHOO:
        iid, name, *_ = row
        old = old_instrument(previous, iid)
        try:
            x = yahoo_one(row, old, args.full_history)
            instruments[iid] = x
            print(
                f"{name[:27]:27} OK  {x['latest']:>12,.2f}  "
                f"day {(x['day_change_pct'] or 0):+6.2f}%  "
                f"history={x['history_fetch']} +{x['history_points_added']}"
            )
        except Exception as e:
            failures.append({"id": iid, "name": name, "error": str(e)})
            if old and old.get("history"):
                instruments[iid] = stale_copy(old, e)
                stale.append(iid)
                print(f"{name[:27]:27} KEEP previous history · {e}")
            else:
                print(f"{name[:27]:27} FAIL {e}")
        time.sleep(0.04)

    for row in FX:
        iid, name, *_ = row
        old = old_instrument(previous, iid)
        try:
            x = fx_one(row, old, args.full_history)
            instruments[iid] = x
            print(
                f"{name[:27]:27} OK  {x['latest']:>12,.4f}  "
                f"day {(x['day_change_pct'] or 0):+6.2f}%  "
                f"history={x['history_fetch']} +{x['history_points_added']}"
            )
        except Exception as e:
            failures.append({"id": iid, "name": name, "error": str(e)})
            if old and old.get("history"):
                instruments[iid] = stale_copy(old, e)
                stale.append(iid)
                print(f"{name[:27]:27} KEEP previous history · {e}")
            else:
                print(f"{name[:27]:27} FAIL {e}")

    payload = {
        "schema_version": "5.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history_mode": "full" if args.full_history else "incremental",
        "history_overlap_days": OVERLAP_DAYS,
        "instruments": instruments,
        "status": {
            "successful": len(instruments),
            "failed": len(failures),
            "stale_kept": len(stale),
            "failures": failures,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("-" * 78)
    print(f"Saved {OUT}")
    print(
        f"Loaded/kept: {len(instruments)} · fetch failures: {len(failures)} · "
        f"previous history preserved after failure: {len(stale)}"
    )


if __name__ == "__main__":
    main()
