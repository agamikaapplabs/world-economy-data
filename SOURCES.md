# V4.5.3 Data Sources

Seed values included in `data/india_activity.json` are dated and source-labelled.

- GST / taxpayer / cumulative e-way bill snapshot: Press Information Bureau / GST Council
- FASTag: NPCI NETC Product Statistics
- UPI: NPCI UPI Product Statistics
- Automobile: SIAM public press releases and FY2025-26 annual report
- Housing: National Housing Bank NHB RESIDEX
- Rail freight: Indian Railways / Press Information Bureau
- Trade: Ministry of Commerce & Industry / Press Information Bureau
- Labour: PLFS / MoSPI / Press Information Bureau
- Power: Central Electricity Authority (source-ready)
- IIP: MoSPI (source-ready)

The URLs used by the collector are editable in `config/india_activity_sources.json`.


## In-dashboard provenance

V4.5.3 adds a **Glossary & Sources** tab. It dynamically lists the World Bank indicator codes loaded from `macro.json` and links each indicator to its World Bank definition/data page. India activity cards use the source URLs embedded in `india_activity.json`.

Market cards identify Yahoo Finance or Frankfurter and expose a provider/source link.
