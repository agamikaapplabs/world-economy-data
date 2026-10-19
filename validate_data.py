import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;DATA=ROOT/"data";errors=[]
def load(rel):
    try:return json.loads((DATA/rel).read_text(encoding="utf-8"))
    except Exception as e:errors.append(f"{rel}: {e}");return {}
m=load("manifest.json")
if m.get("schema_version")!="5.0":errors.append("manifest schema_version != 5.0")
for k,x in (m.get("datasets") or {}).items():
    if not x.get("path") or not (DATA/x["path"]).exists():errors.append(f"missing dataset {k}")
cat=load("metadata/series_catalog.json");series=cat.get("series") or {}
for sid,meta in series.items():
    for rel in meta.get("history_files") or []:
        doc=load(rel)
        if doc.get("series_id")!=sid:errors.append(f"{rel}: series id mismatch")
        seen=set()
        for o in doc.get("observations") or []:
            if o.get("period") is None or o.get("value") is None:errors.append(f"{rel}: invalid observation")
            key=(str(o.get("period")),str(o.get("collected_at")),str(o.get("value")))
            if key in seen:errors.append(f"{rel}: duplicate {key}")
            seen.add(key)
if errors:
    print("V5 VALIDATION FAILED")
    [print(" -",e) for e in errors[:100]]
    sys.exit(1)
print("V5 VALIDATION OK")
print("Series:",len(series))
print("Latest report:",(m.get("latest_report") or {}).get("path"))
