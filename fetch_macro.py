from __future__ import annotations

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "raw" / "macro.json"
CACHE = ROOT / "data" / "raw" / "macro_last_good.json"
OUT.parent.mkdir(exist_ok=True)

COUNTRIES = {
    "USA": "United States",
    "IND": "India",
    "CHN": "China",
    "JPN": "Japan",
    "DEU": "Germany",
    "GBR": "United Kingdom",
    "FRA": "France",
    "BRA": "Brazil",
    "CHE": "Switzerland",
    "RUS": "Russia",
    "SAU": "Saudi Arabia",
    "KOR": "South Korea",
    "TUR": "Turkey",
    "POL": "Poland",
}

INDICATORS = {
    "inflation": ("FP.CPI.TOTL.ZG", "CPI inflation", "%"),
    "gdp_growth": ("NY.GDP.MKTP.KD.ZG", "Real GDP growth", "%"),
    "gdp_usd": ("NY.GDP.MKTP.CD", "Nominal GDP", "USD"),
    "gdp_per_capita": ("NY.GDP.PCAP.CD", "GDP per capita", "USD"),
    "unemployment": ("SL.UEM.TOTL.ZS", "Unemployment", "%"),
    "reserves_usd": ("FI.RES.TOTL.CD", "Total reserves incl. gold", "USD"),
    "import_cover": ("FI.RES.TOTL.MO", "Reserves in months of imports", "months"),
    "exports_usd": ("NE.EXP.GNFS.CD", "Exports of goods & services", "USD"),
    "exports_gdp": ("NE.EXP.GNFS.ZS", "Exports / GDP", "%"),
    "imports_usd": ("NE.IMP.GNFS.CD", "Imports of goods & services", "USD"),
    "imports_gdp": ("NE.IMP.GNFS.ZS", "Imports / GDP", "%"),
    "trade_balance": ("NE.RSB.GNFS.ZS", "External balance goods & services / GDP", "%"),
    "current_account_usd": ("BN.CAB.XOKA.CD", "Current account", "USD"),
    "current_account_gdp": ("BN.CAB.XOKA.GD.ZS", "Current account / GDP", "%"),
    "gov_debt_gdp": ("GC.DOD.TOTL.GD.ZS", "Central government debt / GDP", "%"),
    "fiscal_balance_gdp": ("GC.BAL.CASH.GD.ZS", "Cash surplus/deficit / GDP", "%"),
    "external_debt_gni": ("DT.DOD.DECT.GN.ZS", "External debt stocks / GNI", "%"),
    "fdi_usd": ("BX.KLT.DINV.CD.WD", "FDI net inflows", "USD"),
    "energy_imports_pct": ("EG.IMP.CONS.ZS", "Net energy imports / energy use", "%"),
    "energy_use_pc": ("EG.USE.PCAP.KG.OE", "Energy use per capita", "kg oil eq"),
    "electricity_pc": ("EG.USE.ELEC.KH.PC", "Electricity consumption per capita", "kWh"),
    "agriculture_gdp": ("NV.AGR.TOTL.ZS", "Agriculture / GDP", "%"),
    "food_exports_pct": ("TX.VAL.FOOD.ZS.UN", "Food exports / merchandise exports", "%"),
    "food_imports_pct": ("TM.VAL.FOOD.ZS.UN", "Food imports / merchandise imports", "%"),
    "ores_metals_exports_pct": ("TX.VAL.MMTL.ZS.UN", "Ores & metals exports share", "%"),
    "fuel_exports_pct": ("TX.VAL.FUEL.ZS.UN", "Fuel exports share", "%"),
    "fuel_imports_pct": ("TM.VAL.FUEL.ZS.UN", "Fuel imports share", "%"),
    "container_port_teu": ("IS.SHP.GOOD.TU", "Container port traffic", "TEU"),
}

CODE_TO_KEY = {v[0]: k for k, v in INDICATORS.items()}
UA = "Mozilla/5.0 GlobalMarketsMacro/4.5.2"
TIMEOUT_SECONDS = 12
RETRIES = 2
CHUNK_SIZE = 6
FALLBACK_WORKERS = 3

GOLD_RESERVES = [
    {"country": "United States", "iso": "USA", "tonnes": 8133.5, "gold_share_pct": 83.3, "as_of": "2026-03", "ytd_change_t": None},
    {"country": "Germany", "iso": "DEU", "tonnes": 3350.3, "gold_share_pct": 83.0, "as_of": "2026-03", "ytd_change_t": None},
    {"country": "China", "iso": "CHN", "tonnes": 2366.0, "gold_share_pct": 8.0, "as_of": "2026-07", "ytd_change_t": 60.0},
    {"country": "Russia", "iso": "RUS", "tonnes": 2277.0, "gold_share_pct": None, "as_of": "2026-07", "ytd_change_t": -50.0},
    {"country": "Switzerland", "iso": "CHE", "tonnes": 1039.9, "gold_share_pct": 14.4, "as_of": "2026-03", "ytd_change_t": None},
    {"country": "India", "iso": "IND", "tonnes": 880.5, "gold_share_pct": 18.4, "as_of": "2026-04", "ytd_change_t": None},
    {"country": "Japan", "iso": "JPN", "tonnes": 846.0, "gold_share_pct": 9.1, "as_of": "2026-04", "ytd_change_t": None},
    {"country": "Poland", "iso": "POL", "tonnes": 632.0, "gold_share_pct": None, "as_of": "2026-06", "ytd_change_t": 82.0},
    {"country": "Turkey", "iso": "TUR", "tonnes": None, "gold_share_pct": None, "as_of": "2026-07", "ytd_change_t": -85.0},
]

POLICY = [
    {"economy": "United States", "rate_name": "Effective federal funds rate", "value": "3.88%", "effective": "2026-10-15", "source": "Federal Reserve H.15", "note": "Effective rate, not the FOMC target range."},
    {"economy": "Euro area", "rate_name": "ECB deposit facility", "value": "2.50%", "effective": "2026-09-16", "source": "ECB"},
]

CALENDAR = [
    {"date": "2026-10-28", "event": "Federal Reserve FOMC decision", "region": "US", "importance": "High", "why": "Rates, USD, global liquidity and risk assets."},
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Refresh World Bank macro indicators. By default only indicators "
            "that were not successful on the previous run are fetched."
        )
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Ignore previous success state and refresh every indicator.",
    )
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        metavar="KEY",
        help=(
            "Explicitly refresh one indicator key even if it succeeded previously. "
            "May be repeated or supplied as a comma-separated list."
        ),
    )
    return parser.parse_args()


def expand_force_keys(values):
    keys = set()
    for value in values:
        for key in value.split(","):
            key = key.strip()
            if key:
                keys.add(key)
    unknown = sorted(keys - set(INDICATORS))
    if unknown:
        raise SystemExit(
            "Unknown --force indicator key(s): "
            + ", ".join(unknown)
            + "\nValid keys: "
            + ", ".join(INDICATORS)
        )
    return keys


def get_json(url: str, timeout: int = TIMEOUT_SECONDS):
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json",
                    "Connection": "close",
                },
            )
            with urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            if attempt < RETRIES:
                time.sleep(1.25 * attempt)
    raise last_error


def blank_country_map():
    return {
        iso: {"country": name, "history": [], "latest": None}
        for iso, name in COUNTRIES.items()
    }


def rows_from_response(raw):
    if isinstance(raw, list) and len(raw) > 1 and raw[1]:
        return raw[1]
    return []


def parse_rows(rows, requested_keys):
    output = {key: blank_country_map() for key in requested_keys}

    for row in rows:
        indicator = row.get("indicator") or {}
        code = indicator.get("id") if isinstance(indicator, dict) else None
        key = CODE_TO_KEY.get(code)
        if key not in output:
            continue

        iso = (row.get("countryiso3code") or "").upper()
        if iso not in output[key] or row.get("value") is None:
            continue

        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue

        output[key][iso]["history"].append(
            {"date": str(row.get("date") or ""), "value": value}
        )

    for key in output:
        for obj in output[key].values():
            obj["history"].sort(
                key=lambda x: int(x["date"]) if str(x["date"]).isdigit() else -1
            )
            obj["latest"] = obj["history"][-1] if obj["history"] else None

    return output


def wb_multi(keys):
    country_codes = ";".join(COUNTRIES)
    indicator_codes = ";".join(INDICATORS[key][0] for key in keys)
    url = (
        "https://api.worldbank.org/v2/country/"
        f"{country_codes}/indicator/{indicator_codes}"
        "?source=2&format=json&per_page=5000&mrv=8"
    )
    return parse_rows(rows_from_response(get_json(url)), keys)


def wb_single(key):
    country_codes = ";".join(COUNTRIES)
    code = INDICATORS[key][0]
    url = (
        "https://api.worldbank.org/v2/country/"
        f"{country_codes}/indicator/{quote(code)}"
        "?source=2&format=json&per_page=1000&mrv=8"
    )
    return parse_rows(rows_from_response(get_json(url)), [key])[key]


def load_previous():
    for path in (OUT, CACHE):
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data.get("indicators"), dict):
                    return data
        except Exception:
            pass
    return {"indicators": {}}


def previous_indicator(previous, key):
    item = (previous.get("indicators") or {}).get(key)
    if not isinstance(item, dict):
        return None
    countries = item.get("countries")
    if not isinstance(countries, dict) or not countries:
        return None
    if not any(
        isinstance(v, dict) and (v.get("latest") or v.get("history"))
        for v in countries.values()
    ):
        return None
    return item


def previous_succeeded(previous, key):
    """True only when this indicator succeeded on the prior run.

    failed/stale/unavailable indicators are deliberately retried next run.
    Old V4.5 files that have useful country data but no fetch_status are
    treated as successful, so upgrading does not re-fetch everything.
    """
    item = previous_indicator(previous, key)
    if item is None:
        return False

    status = (item.get("meta") or {}).get("fetch_status")
    if status in {"stale-cache", "unavailable", "failed"}:
        return False
    if status in {
        "fresh",
        "previous-success",
        "skipped-success",
        "cached-success",
        None,
        "",
    }:
        return True
    return True


def build_indicator(key, countries, status, last_successful_fetch_at=None):
    code, label, unit = INDICATORS[key]
    meta = {
        "code": code,
        "label": label,
        "unit": unit,
        "frequency": "annual / latest World Bank observation",
        "fetch_status": status,
    }
    if last_successful_fetch_at:
        meta["last_successful_fetch_at"] = last_successful_fetch_at
    return {"meta": meta, "countries": countries}


def clone_previous_as_skipped(previous, key):
    item = json.loads(json.dumps(previous_indicator(previous, key)))
    meta = item.setdefault("meta", {})
    if "last_successful_fetch_at" not in meta:
        meta["last_successful_fetch_at"] = previous.get("generated_at")
    meta["fetch_status"] = "skipped-success"
    return item


def main():
    args = parse_args()
    forced_keys = expand_force_keys(args.force)

    previous = load_previous()
    all_keys = list(INDICATORS)

    if args.force_all:
        fetch_keys = all_keys[:]
        skip_keys = []
        mode = "FORCE ALL"
    else:
        fetch_keys = [
            key
            for key in all_keys
            if (key in forced_keys) or (not previous_succeeded(previous, key))
        ]
        skip_keys = [key for key in all_keys if key not in fetch_keys]
        mode = "RESUME / FAILED ONLY"

    print("Macro collector v4.5.2")
    print(f"Mode: {mode}")
    print(
        f"Previous successful indicators skipped: {len(skip_keys)} · "
        f"indicators to fetch: {len(fetch_keys)}"
    )
    if forced_keys:
        print("Explicitly forced:", ", ".join(sorted(forced_keys)))
    print(
        f"Timeout {TIMEOUT_SECONDS}s · {RETRIES} attempts · "
        "automatic single-indicator fallback"
    )
    print("=" * 78)

    indicators = {}
    failures = []
    collected = {}
    now = datetime.now(timezone.utc).isoformat()

    # Carry forward successful indicators immediately.
    for key in skip_keys:
        indicators[key] = clone_previous_as_skipped(previous, key)
        print(f"SKIP  {INDICATORS[key][1]:44} previous run successful")

    if fetch_keys:
        chunks = [
            fetch_keys[i : i + CHUNK_SIZE]
            for i in range(0, len(fetch_keys), CHUNK_SIZE)
        ]
        failed_chunk_keys = []

        for index, chunk in enumerate(chunks, start=1):
            labels = ", ".join(INDICATORS[k][1] for k in chunk)
            print(f"[chunk {index}/{len(chunks)}] {labels[:64]}")
            try:
                result = wb_multi(chunk)
                collected.update(result)
                covered = sum(
                    sum(1 for v in result[k].values() if v.get("latest"))
                    for k in chunk
                )
                print(
                    f"  OK · {covered}/{len(chunk) * len(COUNTRIES)} "
                    "country-indicator series populated"
                )
            except Exception as exc:
                print(f"  MULTI FAIL · {exc}")
                failed_chunk_keys.extend(chunk)

        if failed_chunk_keys:
            print()
            print(
                f"Fallback: retrying {len(failed_chunk_keys)} indicators "
                f"with {FALLBACK_WORKERS} workers..."
            )
            with ThreadPoolExecutor(max_workers=FALLBACK_WORKERS) as pool:
                futures = {
                    pool.submit(wb_single, key): key
                    for key in failed_chunk_keys
                }
                for future in as_completed(futures):
                    key = futures[future]
                    label = INDICATORS[key][1]
                    try:
                        collected[key] = future.result()
                        coverage = sum(
                            1
                            for obj in collected[key].values()
                            if obj.get("latest")
                        )
                        print(
                            f"  {label[:44]:44} OK "
                            f"{coverage}/{len(COUNTRIES)}"
                        )
                    except Exception as exc:
                        failures.append(
                            {
                                "key": key,
                                "code": INDICATORS[key][0],
                                "error": str(exc),
                            }
                        )
                        print(f"  {label[:44]:44} FAIL {exc}")

        for key in fetch_keys:
            label = INDICATORS[key][1]
            countries = collected.get(key)

            if countries is not None:
                coverage = sum(
                    1 for obj in countries.values() if obj.get("latest")
                )
                indicators[key] = build_indicator(
                    key,
                    countries,
                    "fresh",
                    last_successful_fetch_at=now,
                )
                print(
                    f"DONE  {label[:44]:44} "
                    f"{coverage}/{len(COUNTRIES)} fresh"
                )
                continue

            old = previous_indicator(previous, key)
            if old is not None:
                item = json.loads(json.dumps(old))
                meta = item.setdefault("meta", {})
                if "last_successful_fetch_at" not in meta:
                    meta["last_successful_fetch_at"] = previous.get(
                        "generated_at"
                    )
                meta["fetch_status"] = "stale-cache"
                indicators[key] = item
                coverage = sum(
                    1
                    for obj in (item.get("countries") or {}).values()
                    if isinstance(obj, dict) and obj.get("latest")
                )
                print(
                    f"KEEP  {label[:44]:44} "
                    f"{coverage}/{len(COUNTRIES)} stale cache"
                )
            else:
                indicators[key] = build_indicator(
                    key, blank_country_map(), "unavailable"
                )
                print(
                    f"MISS  {label[:44]:44} "
                    "0/14 unavailable — will retry next run"
                )
    else:
        print(
            "Nothing to fetch. Every indicator succeeded previously.\n"
            "Use --force-all for a complete refresh, or "
            "--force inflation (etc.) for a specific indicator."
        )

    # Restore canonical indicator ordering.
    indicators = {key: indicators[key] for key in all_keys}

    stale_keys = [
        key
        for key, item in indicators.items()
        if (item.get("meta") or {}).get("fetch_status") == "stale-cache"
    ]
    unavailable_keys = [
        key
        for key, item in indicators.items()
        if (item.get("meta") or {}).get("fetch_status") == "unavailable"
    ]
    skipped_keys = [
        key
        for key, item in indicators.items()
        if (item.get("meta") or {}).get("fetch_status") == "skipped-success"
    ]
    fresh_keys = [
        key
        for key, item in indicators.items()
        if (item.get("meta") or {}).get("fetch_status") == "fresh"
    ]

    payload = {
        "schema_version": "4.5.2",
        "generated_at": now,
        "refresh_mode": (
            "force-all" if args.force_all
            else "resume-failed-only"
        ),
        "indicators": indicators,
        "policy_rates": POLICY,
        "calendar": CALENDAR,
        "gold_reserves": GOLD_RESERVES,
        "failures": failures,
        "fresh_indicators": fresh_keys,
        "skipped_success_indicators": skipped_keys,
        "stale_indicators": stale_keys,
        "unavailable_indicators": unavailable_keys,
        "notes": [
            "Default mode fetches only indicators that did not succeed previously.",
            "Use --force-all to refresh every World Bank indicator.",
            "Use --force KEY to refresh one successful indicator explicitly.",
            "World Bank indicators have different reporting lags by country and indicator.",
            "If World Bank is temporarily unavailable, the previous good per-indicator data is preserved.",
            "Gold-reserve snapshots are dated; no 1Y/5Y gold history is fabricated.",
        ],
    }

    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            if old.get("indicators"):
                shutil.copy2(OUT, CACHE)
        except Exception:
            pass

    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("-" * 78)
    print(f"Saved {OUT}")
    print(
        f"Fresh this run: {len(fresh_keys)} · "
        f"skipped previous success: {len(skipped_keys)} · "
        f"stale retry-next-run: {len(stale_keys)} · "
        f"unavailable retry-next-run: {len(unavailable_keys)}"
    )


if __name__ == "__main__":
    main()
