from __future__ import annotations
import copy, hashlib, json, math, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; RAW=DATA/"raw"; CURRENT=DATA/"current"; HISTORY=DATA/"history"; REPORTS=DATA/"reports"; METADATA=DATA/"metadata"
IST=timezone(timedelta(hours=5,minutes=30))
SCHEMA_VERSION="5.0"
RECENT_MARKET_POINTS=400
RECENT_ACTIVITY_POINTS=12

INDIA_SERIES={
 "gst":("india.gst.gross","GST gross collections"),
 "rail_freight":("india.rail.freight_mt","Rail freight"),
 "passenger_vehicles":("india.auto.passenger_vehicles","Passenger vehicle sales"),
 "commercial_vehicles":("india.auto.commercial_vehicles","Commercial vehicle sales"),
 "fastag":("india.fastag.value","FASTag toll value"),
 "housing":("india.housing.hpi","Housing price index"),
 "trade_balance":("india.trade.merchandise_balance","Merchandise trade balance"),
 "unemployment":("india.labour.unemployment","Unemployment rate"),
}
SOURCE_URLS={
 "Yahoo Finance chart":"https://finance.yahoo.com/",
 "Frankfurter":"https://frankfurter.dev/",
 "World Bank WDI":"https://data.worldbank.org/",
 "NPCI NETC":"https://www.npci.org.in/what-we-do/netc/product-statistics",
 "NPCI UPI":"https://www.npci.org.in/what-we-do/upi/product-statistics",
 "SIAM":"https://www.siam.in/press-release.aspx",
 "NHB RESIDEX":"https://residex.nhbonline.org.in/",
 "Indian Railways / PIB":"https://indianrailways.gov.in/",
 "PLFS / MoSPI / PIB":"https://www.mospi.gov.in/",
 "Ministry of Commerce & Industry / PIB":"https://www.commerce.gov.in/",
}

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return copy.deepcopy(default)

def write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(payload,indent=2,ensure_ascii=False)
    path.write_text(text,encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()

def slug(series_id):
    return Path(*[re.sub(r"[^a-zA-Z0-9_-]+","_",x) for x in series_id.split(".")])

def sid(source):
    return re.sub(r"[^a-z0-9]+","-",source.lower()).strip("-") or "unknown"

def year_of(period):
    m=re.search(r"(19|20)\d{2}",str(period))
    return m.group(0) if m else "undated"

def obs(period,value,source,source_url,collected_at,released_at=None,status="observed"):
    try:
        v=float(value)
        if not math.isfinite(v):return None
    except Exception:return None
    return {"period":str(period),"value":v,"released_at":released_at,"collected_at":collected_at,
            "source_id":sid(source),"source":source,"source_url":source_url or SOURCE_URLS.get(source,""),"status":status}

def merge_series(series_id,meta,incoming):
    incoming=[x for x in incoming if x and x.get("period")]
    by_year={}
    for x in incoming:by_year.setdefault(year_of(x["period"]),[]).append(x)
    for year,rows in by_year.items():
        path=HISTORY/slug(series_id)/f"{year}.json"
        doc=load(path,{"schema_version":SCHEMA_VERSION,"series_id":series_id,"metadata":meta,"observations":[]})
        existing=list(doc.get("observations") or [])
        for row in rows:
            same=[x for x in existing if str(x.get("period"))==str(row["period"])]
            duplicate=any(
                isinstance(x.get("value"),(int,float)) and abs(float(x["value"])-float(row["value"]))<1e-12
                for x in same
            )
            if duplicate:continue
            row=dict(row);row["revision_no"]=len(same);row["is_revision"]=bool(same)
            existing.append(row)
        existing.sort(key=lambda x:(str(x.get("period","")),str(x.get("collected_at",""))))
        doc.update({"schema_version":SCHEMA_VERSION,"series_id":series_id,"metadata":meta,"observations":existing})
        write(path,doc)

def files_for(series_id):
    d=HISTORY/slug(series_id)
    return sorted(p.relative_to(DATA).as_posix() for p in d.glob("*.json"))

def latest_vintages(files):
    by={}
    for rel in files:
        for x in load(DATA/rel,{}).get("observations") or []:
            p=str(x.get("period",""))
            if not p:continue
            old=by.get(p)
            if old is None or str(x.get("collected_at",""))>=str(old.get("collected_at","")):by[p]=x
    return [by[k] for k in sorted(by)]

def markets(raw,pub,catalog):
    out=copy.deepcopy(raw);out["schema_version"]=SCHEMA_VERSION;out["architecture"]="V5 current materialized view"
    for iid,item in (out.get("instruments") or {}).items():
        series_id=f"market.{iid}.close"
        source=item.get("source") or "Market source"
        source_url=(f"https://finance.yahoo.com/quote/{item.get('symbol')}" if "Yahoo" in source and item.get("symbol") else SOURCE_URLS.get(source,""))
        meta={"name":item.get("name") or iid,"unit":item.get("unit") or item.get("currency") or "",
              "frequency":"daily","domain":"market","country":"IND" if item.get("group")=="india_stocks" else None,
              "source":source,"source_url":source_url}
        merge_series(series_id,meta,[obs(p.get("date"),p.get("value"),source,source_url,pub,p.get("date")) for p in item.get("history") or []])
        catalog[series_id]={**meta,"history_files":files_for(series_id)}
        item["series_id"]=series_id
        item["history"]=(item.get("history") or [])[-RECENT_MARKET_POINTS:]
        item["history_scope"]=f"recent {RECENT_MARKET_POINTS} points; full series in canonical history"
    return out

def macro(raw,pub,catalog):
    out=copy.deepcopy(raw);out["schema_version"]=SCHEMA_VERSION
    for key,indicator in (out.get("indicators") or {}).items():
        m=indicator.get("meta") or {}
        for iso,country in (indicator.get("countries") or {}).items():
            series_id=f"macro.{iso.lower()}.{key}"
            code=m.get("code") or ""; url=f"https://data.worldbank.org/indicator/{code}" if code else SOURCE_URLS["World Bank WDI"]
            meta={"name":f"{country.get('country') or iso} · {m.get('label') or key}","unit":m.get("unit") or "",
                  "frequency":"annual","domain":"macro","country":iso,"source":"World Bank WDI","source_url":url,"indicator_code":code}
            merge_series(series_id,meta,[obs(p.get("date"),p.get("value"),"World Bank WDI",url,pub) for p in country.get("history") or []])
            catalog[series_id]={**meta,"history_files":files_for(series_id)}
            country["series_id"]=series_id
            country["history"]=(country.get("history") or [])[-8:]
    return out

def india(raw,pub,catalog):
    out=copy.deepcopy(raw);out["schema_version"]=SCHEMA_VERSION
    for key,item in (out.get("headline") or {}).items():
        series_id,name=INDIA_SERIES.get(key,(f"india.activity.{key}",item.get("label") or key))
        source=item.get("source") or "India official source";url=item.get("url") or SOURCE_URLS.get(source,"")
        meta={"name":item.get("label") or name,"unit":item.get("unit") or "","frequency":item.get("frequency") or "release-based",
              "domain":"india","country":"IND","source":source,"source_url":url}
        rows=list(item.get("history") or [])
        if item.get("period") and item.get("value") is not None:rows.append({"period":item.get("period"),"value":item.get("value")})
        merge_series(series_id,meta,[obs(p.get("period") or p.get("date"),p.get("value"),source,url,pub) for p in rows])
        catalog[series_id]={**meta,"history_files":files_for(series_id)}
        item["series_id"]=series_id
        item["history"]=(item.get("history") or [])[-RECENT_ACTIVITY_POINTS:]

    extras=[]
    fastag=out.get("fastag") or {}
    for p in fastag.get("series") or []:
        extras.extend([
          ("india.fastag.value","FASTag toll value","₹ crore","monthly",p.get("period"),p.get("amount_cr"),"NPCI NETC",fastag.get("url","")),
          ("india.fastag.volume","FASTag transaction volume","million","monthly",p.get("period"),p.get("volume_mn"),"NPCI NETC",fastag.get("url","")),
        ])
    upi=out.get("upi") or {}
    for p in upi.get("series") or []:
        extras.extend([
          ("india.upi.value","UPI transaction value","₹ crore","monthly",p.get("period"),p.get("value_cr"),"NPCI UPI",upi.get("url","")),
          ("india.upi.volume","UPI transaction volume","million","monthly",p.get("period"),p.get("volume_mn"),"NPCI UPI",upi.get("url","")),
        ])
    housing=out.get("housing") or {}
    for p in housing.get("composite_hpi_assessment") or []:
        extras.append(("india.housing.hpi","NHB 50-city housing price index","index","quarterly",p.get("period"),p.get("value"),"NHB RESIDEX",housing.get("url","")))
    trade=out.get("trade") or {};tsrc=trade.get("source") or "Ministry of Commerce & Industry / PIB";turl=trade.get("url","")
    fields=[("merchandise_exports","Merchandise exports","merch_exports_usd_bn"),("merchandise_imports","Merchandise imports","merch_imports_usd_bn"),
            ("merchandise_balance","Merchandise trade balance","merch_balance_usd_bn"),("services_exports","Services exports","services_exports_usd_bn"),
            ("services_imports","Services imports","services_imports_usd_bn"),("services_balance","Services trade balance","services_balance_usd_bn"),
            ("total_exports","Total exports","total_exports_usd_bn"),("total_imports","Total imports","total_imports_usd_bn"),("total_balance","Total trade balance","total_balance_usd_bn")]
    for p in trade.get("series") or []:
        for suffix,name,field in fields:extras.append((f"india.trade.{suffix}",name,"US$ bn","monthly",p.get("period"),p.get(field),tsrc,turl))
    grouped={}
    for series_id,name,unit,freq,period,value,source,url in extras:
        meta={"name":name,"unit":unit,"frequency":freq,"domain":"india","country":"IND","source":source,"source_url":url}
        grouped.setdefault(series_id,{"meta":meta,"rows":[]})["rows"].append(obs(period,value,source,url,pub))
    for series_id,o in grouped.items():
        merge_series(series_id,o["meta"],o["rows"]);catalog[series_id]={**o["meta"],"history_files":files_for(series_id)}
    return out

def source_doc(catalog):
    d={}
    for meta in catalog.values():
        name=meta.get("source") or "Unknown";key=sid(name)
        e=d.setdefault(key,{"source_id":key,"name":name,"url":meta.get("source_url") or "","series_count":0})
        e["series_count"]+=1
    return {"schema_version":SCHEMA_VERSION,"sources":sorted(d.values(),key=lambda x:x["name"])}

def main():
    for d in (RAW,CURRENT,HISTORY,REPORTS,METADATA):d.mkdir(parents=True,exist_ok=True)
    pub=datetime.now(IST).isoformat();report_date=datetime.now(IST).date().isoformat()
    rm=load(RAW/"markets.json",{"instruments":{},"status":{}})
    rma=load(RAW/"macro.json",{"indicators":{}})
    rr=load(RAW/"resources.json",{})
    ri=load(RAW/"india_activity.json",{"headline":{}})
    catalog={}
    cm=markets(rm,pub,catalog);cma=macro(rma,pub,catalog);ci=india(ri,pub,catalog);cr=copy.deepcopy(rr);cr["schema_version"]=SCHEMA_VERSION
    hashes={
      "markets":write(CURRENT/"markets.json",cm),
      "macro":write(CURRENT/"macro.json",cma),
      "resources":write(CURRENT/"resources.json",cr),
      "india_activity":write(CURRENT/"india_activity.json",ci),
    }
    cat={"schema_version":SCHEMA_VERSION,"generated_at":pub,"series_count":len(catalog),"series":dict(sorted(catalog.items()))}
    cath=write(METADATA/"series_catalog.json",cat);sh=write(METADATA/"sources.json",source_doc(catalog))
    latest={}
    for series_id,meta in catalog.items():
        rows=latest_vintages(meta.get("history_files") or [])
        if rows:
            x=rows[-1];latest[series_id]={"period":x.get("period"),"value":x.get("value"),"collected_at":x.get("collected_at"),"source_id":x.get("source_id")}
    yyyy,mm,dd=report_date.split("-");report_rel=f"reports/{yyyy}/{mm}/{dd}.json"
    rh=write(DATA/report_rel,{"schema_version":SCHEMA_VERSION,"report_date":report_date,"as_of":pub,"series_latest":latest,
                              "india_diagnostics":ci.get("diagnostics") or [],"market_status":cm.get("status") or {},
                              "note":"As-known snapshot. Canonical history preserves revisions/vintages."})
    manifest={"schema_version":SCHEMA_VERSION,"architecture":"canonical-history + materialized-current + daily-report","published_at":pub,
              "datasets":{"markets":{"path":"current/markets.json","sha256":hashes["markets"]},
                          "macro":{"path":"current/macro.json","sha256":hashes["macro"]},
                          "resources":{"path":"current/resources.json","sha256":hashes["resources"]},
                          "india_activity":{"path":"current/india_activity.json","sha256":hashes["india_activity"]}},
              "metadata":{"series_catalog":{"path":"metadata/series_catalog.json","sha256":cath},
                          "sources":{"path":"metadata/sources.json","sha256":sh}},
              "latest_report":{"path":report_rel,"sha256":rh},"series_count":len(catalog),
              "client_contract":{"current_is_materialized_view":True,"history_is_append_only_with_vintages":True,"clients_may_lazy_load_history":True}}
    write(DATA/"manifest.json",manifest)
    print("V5 publisher complete")
    print("Published:",pub)
    print("Series:",len(catalog))
    print("Latest report:",report_rel)
if __name__=="__main__":main()
