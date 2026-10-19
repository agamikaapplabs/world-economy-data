from __future__ import annotations
import html, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"data"/"raw"/"india_activity.json"
CONFIG=ROOT/"config"/"india_activity_sources.json"
UA="Mozilla/5.0 GlobalMarketsIndiaActivity/5.0"

def fetch_text(url, timeout=25):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,*/*"})
    with urlopen(req,timeout=timeout) as r:
        raw=r.read().decode("utf-8","ignore")
    raw=re.sub(r"<script\b[^>]*>.*?</script>"," ",raw,flags=re.I|re.S)
    raw=re.sub(r"<style\b[^>]*>.*?</style>"," ",raw,flags=re.I|re.S)
    raw=re.sub(r"<[^>]+>"," ",raw)
    return re.sub(r"\s+"," ",html.unescape(raw)).strip()

def num(x): return float(x.replace(",",""))

def seed():
    if OUT.exists():
        try:return json.loads(OUT.read_text(encoding="utf-8"))
        except:pass
    return {"schema_version":"4.5","generated_at":None,"headline":{},"refresh_log":[]}

def update_npci(data, url, kind):
    txt=fetch_text(url)
    if kind=="fastag":
        pat=re.compile(r"([A-Za-z]+-\d{4})\s+(\d+)\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)")
        rows=[]
        for m in pat.finditer(txt):
            rows.append({"period":m.group(1).replace("-"," "),"volume_mn":num(m.group(4)),"amount_cr":num(m.group(5))})
        if rows:
            # Page is newest-first.
            data.setdefault("fastag",{})["series"]=list(reversed(rows[:18]))
            latest=rows[0]
            data.setdefault("headline",{}).setdefault("fastag",{}).update(
                {"value":latest["amount_cr"],"unit":"₹ crore","period":latest["period"],"source":"NPCI NETC","url":url,"status":"live-refreshed"})
            return f"FASTag {latest['period']}"
    else:
        pat=re.compile(r"([A-Za-z]+-\d{4})\s+(\d+)\s+([\d,.]+)\s+([\d,.]+)")
        rows=[]
        for m in pat.finditer(txt):
            rows.append({"period":m.group(1).replace("-"," "),"volume_mn":num(m.group(3)),"value_cr":num(m.group(4))})
        if rows:
            data.setdefault("upi",{})["series"]=list(reversed(rows[:18]))
            return f"UPI {rows[0]['period']}"
    raise RuntimeError("No table rows recognized")

def update_siam(data,url):
    txt=fetch_text(url)
    found={}
    patterns={
      "passenger_vehicles":r"Passenger Vehicles.*?sales were\s+([\d,]+)\s+units in\s+([A-Za-z]+)\s+(\d{4})",
      "three_wheelers":r"Three[- ]wheeler sales were\s+([\d,]+)\s+units in\s+([A-Za-z]+)\s+(\d{4})",
      "two_wheelers":r"Two[- ]wheeler sales were\s+([\d,]+)\s+units in\s+([A-Za-z]+)\s+(\d{4})"
    }
    latest_period=None
    for key,pat in patterns.items():
        m=re.search(pat,txt,re.I|re.S)
        if m:
            found[key]=int(m.group(1).replace(",",""))
            latest_period=f"{m.group(2)} {m.group(3)}"
    if not found: raise RuntimeError("No public monthly SIAM figures recognized")
    a=data.setdefault("automobile",{})
    a["latest_month"]=latest_period;a.setdefault("monthly",{}).update(found)
    if "passenger_vehicles" in found:
        data.setdefault("headline",{}).setdefault("passenger_vehicles",{}).update(
          {"value":found["passenger_vehicles"],"unit":"units","period":latest_period,"source":"SIAM","url":url,"status":"live-refreshed"})
    return f"SIAM {latest_period}"

def update_nhb(data,url):
    txt=fetch_text(url)
    rows=[]
    for m in re.finditer(r"(Jun|Sep|Dec|Mar)\s+(20\d{2})\s+(\d{2,3}(?:\.\d+)?)",txt,re.I):
        rows.append({"period":f"{m.group(1).title()} {m.group(2)}","value":float(m.group(3))})
    # Deduplicate period+value and keep plausible composite sequence.
    uniq=[]
    seen=set()
    for r in rows:
        k=(r["period"],r["value"])
        if k not in seen and 50<r["value"]<200:
            seen.add(k);uniq.append(r)
    # The page also includes city values; prefer known consecutive composite values if recognized.
    wanted={"Jun 2025":None,"Sep 2025":None,"Dec 2025":None,"Mar 2026":None,"Jun 2026":None}
    for r in uniq:
        if r["period"] in wanted and wanted[r["period"]] is None:
            # Composite values are the first values after the composite heading on current page,
            # but parsing generic page text can mingle city rows. Only accept a tight 90-115 band.
            if 90 <= r["value"] <= 115: wanted[r["period"]]=r["value"]
    if all(v is not None for v in wanted.values()):
        series=[{"period":k,"value":v} for k,v in wanted.items()]
        data.setdefault("housing",{})["composite_hpi_assessment"]=series
        latest=series[-1]
        yoy=(latest["value"]/series[0]["value"]-1)*100
        data.setdefault("headline",{}).setdefault("housing",{}).update(
          {"value":latest["value"],"unit":"index","period":latest["period"],"yoy_pct":round(yoy,2),"source":"NHB RESIDEX","url":url,"status":"live-refreshed"})
        return f"NHB {latest['period']}"
    raise RuntimeError("Composite HPI series not safely recognized")

def update_static_snapshot(data, url, kind):
    txt=fetch_text(url)
    if kind=="gst":
        m=re.search(r"Gross GST collections reached\s*~?₹\s*([\d.]+)\s*lakh crore.*?April-September 2026.*?([\d.]+)%\s*Y-o-Y",txt,re.I|re.S)
        if m:
            g=data.setdefault("gst",{});g["gross_collection_lakh_crore"]=float(m.group(1));g["gross_collection_yoy_pct"]=float(m.group(2))
            data.setdefault("headline",{}).setdefault("gst",{}).update({"value":float(m.group(1)),"yoy_pct":float(m.group(2)),"status":"live-refreshed"})
            return "GST Apr-Sep 2026"
    elif kind=="rail":
        m=re.search(r"loaded\s+([\d.]+)\s+million tonnes.*?compared to\s+([\d.]+)\s+million tonnes.*?([\d.]+)\s+per cent",txt,re.I|re.S)
        if m:
            x=data.setdefault("rail_freight",{}).setdefault("latest",{})
            x.update({"period":"Sep 2026","million_tonnes":float(m.group(1)),"prior_year_million_tonnes":float(m.group(2)),"yoy_pct":float(m.group(3))})
            data.setdefault("headline",{}).setdefault("rail_freight",{}).update({"value":float(m.group(1)),"yoy_pct":float(m.group(3)),"status":"live-refreshed"})
            return "Rail freight Sep 2026"
    elif kind=="plfs":
        u=re.search(r"Overall UR.*?stood.*?at\s+([\d.]+)%",txt,re.I|re.S)
        lf=re.search(r"Overall LFPR.*?stood at\s+([\d.]+)%",txt,re.I|re.S)
        wp=re.search(r"Overall WPR.*?increased.*?to\s+([\d.]+)%",txt,re.I|re.S)
        if u:
            latest=data.setdefault("labour",{}).setdefault("latest",{})
            latest.update({"period":"Sep 2026","unemployment_pct":float(u.group(1))})
            if lf:latest["lfpr_pct"]=float(lf.group(1))
            if wp:latest["wpr_pct"]=float(wp.group(1))
            data.setdefault("headline",{}).setdefault("unemployment",{}).update({"value":float(u.group(1)),"status":"live-refreshed"})
            return "PLFS Sep 2026"
    raise RuntimeError("Expected snapshot pattern not recognized")


def _append_headline_history(data, key, rows):
    item=data.setdefault("headline",{}).setdefault(key,{})
    existing=item.get("history") if isinstance(item.get("history"),list) else []
    merged={}
    for r in [*existing,*rows]:
        try:
            period=str(r.get("period") or r.get("date") or "").strip()
            value=float(r.get("value"))
        except Exception:
            continue
        if period:
            merged[period]={"period":period,"value":value}
    item["history"]=[merged[k] for k in merged]

def refresh_headline_history(data):
    # Reuse locally stored series. Older observations are not re-downloaded on every run.
    f=(data.get("fastag") or {}).get("series") or []
    _append_headline_history(data,"fastag",[{"period":x.get("period"),"value":x.get("amount_cr")} for x in f])
    h=(data.get("housing") or {}).get("composite_hpi_assessment") or []
    _append_headline_history(data,"housing",[{"period":x.get("period"),"value":x.get("value")} for x in h])
    t=(data.get("trade") or {}).get("series") or []
    _append_headline_history(data,"trade_balance",[{"period":x.get("period"),"value":x.get("merch_balance_usd_bn")} for x in t])

    # For indicators where the public source exposes only a latest snapshot, append the
    # new observation to the local history cache. History therefore grows over time without
    # repeatedly scraping old releases.
    for key,item in (data.get("headline") or {}).items():
        if not isinstance(item,dict):
            continue
        if item.get("period") and item.get("value") is not None:
            _append_headline_history(data,key,[{"period":item.get("period"),"value":item.get("value")}])

def main():
    data=seed()
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    log=[]
    jobs=[
      ("FASTag",lambda:update_npci(data,cfg["npci_fastag"],"fastag")),
      ("UPI",lambda:update_npci(data,cfg["npci_upi"],"upi")),
      ("SIAM",lambda:update_siam(data,cfg["siam_press_releases"])),
      ("NHB",lambda:update_nhb(data,cfg["nhb_residex"])),
      ("GST",lambda:update_static_snapshot(data,cfg["gst_pib_snapshot"],"gst")),
      ("Rail",lambda:update_static_snapshot(data,cfg["rail_pib_snapshot"],"rail")),
      ("PLFS",lambda:update_static_snapshot(data,cfg["plfs_pib_snapshot"],"plfs")),
    ]
    print("India Activity Monitor collector")
    print("="*66)
    for name,fn in jobs:
        try:
            detail=fn();print(f"{name:10} OK   {detail}");log.append({"source":name,"status":"ok","detail":detail})
        except Exception as e:
            print(f"{name:10} KEEP {e}");log.append({"source":name,"status":"seed-kept","detail":str(e)})
    refresh_headline_history(data)
    data["schema_version"]="5.0"
    data["generated_at"]=datetime.now(timezone.utc).isoformat()
    data["refresh_log"]=log
    OUT.write_text(json.dumps(data,indent=2),encoding="utf-8")
    print("Saved",OUT)
    print("Note: seed values are retained when a public page changes structure; nothing is fabricated.")

if __name__=="__main__":main()
