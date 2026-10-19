import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"data"/"raw"/"resources.json"
payload={
 "schema_version":"4.5","generated_at":datetime.now(timezone.utc).isoformat(),
 "layers":{
   "energy":{"commodities":["Crude oil","LPG / propane","Natural gas / LNG","Coal","Electricity"],
             "metrics":["production","consumption","imports","exports","net imports","import dependency","proven reserves","strategic stocks","refining"],
             "status":"Framework ready. Detailed physical balance feeds remain pending where official keyless sources are not yet wired."},
   "agriculture":{"commodities":["Wheat","Rice","Corn / maize","Soybeans","Sugar","Cotton","Vegetable oils"],
             "metrics":["production","consumption","imports","exports","ending stocks","stocks-to-use","1Y/5Y"],
             "status":"FAOSTAT / USDA integration staged."},
   "dairy":{"commodities":["Milk","Butter","Cheese","Skim milk powder","Whole milk powder"],
             "metrics":["production","consumption","imports","exports"],"status":"FAOSTAT / USDA integration staged."},
   "metals":{"commodities":["Gold","Copper","Iron ore","Aluminium","Nickel","Lithium","Cobalt","Rare earths"],
             "metrics":["production","imports","exports","reserves where reliable"],"status":"Price series are separate from physical balance data."},
   "shipping":{"metrics":["container port traffic","Baltic Dry / freight benchmarks","container rates","port throughput"],
             "status":"World Bank annual container traffic is used where available; richer freight connectors remain staged."}
 },
 "principle":"Unavailable physical-balance data stays pending and is never inferred from commodity prices."
}
OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print("Saved",OUT)
