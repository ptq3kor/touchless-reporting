# Touchless Reporting — Management Dashboard: Full Implementation Specification

> **Purpose of this document:** Self-contained build specification for the Touchless Reporting management dashboard (Bosch Use Case 6, GS). It contains everything needed to generate the back-end and front-end code without access to the original conversation: data-model semantics, complete API contracts, AI-agent specifications, UI design spec, and verification values. It is written to be consumed by an LLM or developer directly.

---

## 1. Business Context

Monthly business reporting at Bosch is fragmented across systems, formats, and languages. Controllers (OBR1) spend days compiling spreadsheets/slides before Monthly Business Reviews (MBR); General Managers consume the reports. **Touchless Reporting** generates one consolidated management report for all entities automatically from live P&L data, historical inputs, and prior controller comments, with AI providing narrative generation, anomaly detection / sanity checks before MBR submission, and natural-language Q&A.

Deliverable: a one-page, landscape, executive finance dashboard (Power BI / SAC look-and-feel, Bosch corporate identity) over an existing SQLite database, plus an AI assistant layer.

**Technology decisions (already made — do not revisit):**
| Layer | Choice |
|---|---|
| Backend API | Python **FastAPI** (read-only over SQLite) |
| Frontend | **React + Vite**, charts with **Recharts** |
| AI layer | **Microsoft Agent Framework (MAF)** (`agent-framework` Python package) with **Azure-hosted models** (Azure AI Foundry / Azure OpenAI). Model deployment name env-configurable (e.g. a Claude Sonnet 4.6 deployment in Foundry, or any Azure OpenAI chat deployment). Designed so the model can be swapped later via env var only. |

---

## 2. Data Layer (existing — DO NOT modify)

**File:** `touchless_reporting.db` (SQLite) in the project root. All financial values in **millions**. Reporting currency EUR. Deterministic data (seed 42; regenerable via `generate_db.py`). Companion docs: `DATA_DICTIONARY.md`, `schema.sql`.

### 2.1 Star schema

```
dim_period (24 months: 202301..202412)   dim_scenario (ACT/CF/BP)   dim_measure (15 KPIs)
dim_business_sector ──┐
dim_division ─────────┼── fact_financials (62,730 rows)
dim_legal_entity ─────┼── fact_headcount  (4,182 rows)
   └─ dim_country (area/subregion/local currency)
fx_rates (monthly avg + frozen plan rates)
AI layer: controller_comments (283) · anomaly_flags (44) · mbr_submissions (75)
```

### 2.2 Key tables and columns

- `fact_financials(period_id, scenario_code, entity_id, sector_code, division_code, measure_code, currency_code, value_lc, value_eur_nom, value_eur_real)` — grain: period × scenario × entity × sector × division × measure. Indexes exist on `(period_id, scenario_code, sector_code, measure_code)` and `(entity_id, division_code)`.
- `fact_headcount(period_id, scenario_code, entity_id, sector_code, division_code, hc_state_direct, hc_state_indirect, hc_avg_direct, hc_avg_indirect, pc_fte_direct, pc_fte_indirect)` — state = month-end headcount, avg = monthly average, pc_fte = Personnel Capacity in FTE (≈93% of avg HC).
- `dim_business_sector(sector_code, sector_name, sort_order)` — BBM Mobility Solutions, BBI Industrial Technology, BBG Consumer Goods, BBE Energy and Building Technology.
- `dim_country(country_code, country_name, subregion, area, currency_code)` — 11 countries; areas: Europe / Americas / Asia Pacific; 8 subregions.
- `dim_legal_entity(entity_id, entity_code, entity_name, country_code)` — 15 entities.
- `dim_division(division_code, division_name, sector_code)` — 13 divisions, each mapped to a sector.
- `dim_period(period_id YYYYMM, year, month, month_name, quarter, period_start, period_end)`.
- `dim_scenario(scenario_code)` — `ACT`, `CF` (Current Forecast), `BP` (Business Plan).
- `dim_measure(measure_code, measure_name, category, sub_category, unit, is_cost, is_balance, sort_order)`.
- `fx_rates(currency_code, period_id, rate_to_eur, plan_rate_to_eur)`.
- `controller_comments(comment_id, period_id, entity_id, sector_code, measure_code, comment_text, author, language, created_at)`.
- `anomaly_flags(anomaly_id, period_id, entity_id, sector_code, measure_code, rule_code, severity INFO|WARNING|CRITICAL, message, status OPEN|REVIEWED|RESOLVED, detected_at)`.
- `mbr_submissions(submission_id, period_id, entity_id, status DRAFT|SUBMITTED|APPROVED, submitted_by, submitted_at, approved_by, approved_at, sanity_check_passed, ai_summary)`.

### 2.3 Measure catalog (`dim_measure`)

| Code | Section | category | sub_category | is_cost | is_balance |
|---|---|---|---|---|---|
| TGS, TNS, INT_SALES, STP_REGION | Sales Performance | SALES | — | 0 | 0 |
| EBIT | P&L Highlights | PNL | — | 0 | 0 |
| SGA_RD, SGA_SALES, SGA_ADMIN | SG&A (Fixed) | SGA | FIXED | 1 | 0 |
| SGA_VAR | SG&A (Variable) | SGA | VARIABLE | 1 | 0 |
| OTHER_OPINC | SG&A (Other Op Inc/Exp, signed) | SGA | OTHER | 0 | 0 |
| AR, AP, INVENTORY | NWC (month-end balances) | NWC | — | 0 | 1 |
| CAPEX | NWC (flow) | NWC | — | 1 | 0 |
| IFCF | NWC (flow, signed, can be negative) | NWC | — | 0 | 0 |

Costs (`is_cost=1`) are stored as **positive expense amounts**.

### 2.4 Non-negotiable query semantics

1. **vs PY (prior year)** is NOT a scenario. Compute by self-joining ACT rows at `period_id - 100` (same month, prior year), matching on entity, sector, division, measure.
2. **vs CF / vs BP**: scenario codes `CF` and `BP` exist for all of 2024. CF Jan–May ≈ ACT (locked); Jun–Dec is forecast.
3. **YTD**: `period_id BETWEEN <year>01 AND <selected period>` — **flows** (sales, costs, CAPEX, IFCF) are SUMmed; **balances** (`is_balance=1`: AR/AP/INVENTORY) take the **latest selected month only, never summed over time**.
4. **EBIT % of TNS** is a ratio of two measures computed at query time (`SUM(EBIT)/SUM(TNS)*100`), never pre-aggregated.
5. **Currency toggle**: `value_lc` (local) vs `value_eur_nom` (EUR at actual monthly FX). **Only aggregate `value_lc` when the filter pins a single local currency** (single entity, or single country). Otherwise force EUR and tell the client.
6. **View toggle**: `value_eur_nom` = Nominal (actual FX); `value_eur_real` = Real / "woc" (without currency effect; translated at frozen plan FX rates).
7. **Consolidation**: "Group" / Legal Entity total = BBM+BBI+BBG+BBE = simply omit the sector filter and SUM.
8. **Data availability**: ACT exists 202301–202405; CF and BP exist 202401–202412. Current reporting month = **May 2024 (202405)**. The frontend must not offer ACT months beyond 202405.

### 2.5 Verified benchmark values (use for testing)

Group level (no filters), May 2024, EUR nominal:
| Metric | Value |
|---|---|
| TNS current month | **7,847.7** (+4.0% vs PY 7,548.2) |
| TGS | 8,211.2 (+4.0%) · INT_SALES 363.6 (+4.4%) · STP_REGION 4,895.1 (+4.0%) |
| TNS by sector | BBM 4,974.5 · BBG 1,672.9 · BBE 632.3 · BBI 568.1 |
| EBIT month (ACT) | **411.0** = 5.24% of TNS; CF 405.5 (5.17%); BP 408.7 (5.20%) |
| EBIT YTD (ACT) | 2,088.9 |
| SG&A YTD (ACT/PY) | RD 3,104.0/2,954.4 · Sales 2,497.3/2,425.4 · Admin 1,197.4/1,157.1 · Var 1,678.3/1,618.1 · OtherOpInc 76.5/81.4 |
| Headcount (state/avg/PC FTE) | 409,205 / 407,979 / 379,420; direct 60.3%; PY state 406,822 |
| NWC May-24 | AR 11,576.3 · AP 9,811.0 · INVENTORY 14,671.7 · CAPEX month 432.8 (YTD 2,079.9) · IFCF month 274.1 (YTD 1,778.2) |
| Real vs Nominal (Group TNS) | 7,828.3 vs 7,847.7 |
| AI layer (202405) | Open anomalies: 1 CRITICAL, 3 WARNING, 1 INFO; MBR statuses: 8 APPROVED, 3 SUBMITTED, 4 DRAFT |

Sector storylines (for sanity): BBM ≈ +6.5% vs PY (growth), BBI ≈ −5.5% (downturn), BBG ≈ −1.5%, BBE ≈ +3%; EBIT margins: BBI highest ≈8.8%, BBM ≈4.8%. Seasonality: August trough, March/October peaks, CAPEX loaded into Q4.

---

## 3. Project Layout

```
AI Usecase/
├── touchless_reporting.db          (existing)
├── DATA_DICTIONARY.md, schema.sql, generate_db.py, query.py   (existing)
├── backend/
│   ├── main.py            FastAPI app: CORS (allow http://localhost:5173), include routers
│   ├── db.py              get_conn() → sqlite3 read-only ("file:...?mode=ro", uri=True), row_factory=Row
│   ├── filters.py         FilterParams model + SQL WHERE builder + value-column resolver
│   ├── queries.py         reusable query functions shared by routers and agent tools
│   ├── routers/
│   │   ├── meta.py        GET /api/meta/filters
│   │   ├── sales.py       GET /api/sales
│   │   ├── pnl.py         GET /api/pnl
│   │   ├── sga.py         GET /api/sga
│   │   ├── headcount.py   GET /api/headcount
│   │   ├── nwc.py         GET /api/nwc
│   │   ├── summary.py     GET /api/summary
│   │   └── assistant.py   POST /api/assistant/chat · POST /api/assistant/generate-summary
│   ├── agents/
│   │   ├── config.py      Azure env config + MAF chat client factory
│   │   ├── tools.py       function tools over the db
│   │   ├── prompts.py     agent instruction strings
│   │   └── orchestrator.py agents + sequential workflow + chat routing
│   └── requirements.txt   fastapi, uvicorn[standard], agent-framework, azure-identity, pydantic
└── frontend/
    ├── index.html, package.json, vite.config.js   (dev proxy: /api → http://localhost:8000)
    └── src/
        ├── main.jsx, App.jsx, api.js, styles.css
        └── components/  Header.jsx, SectorTabs.jsx, FilterBar.jsx, KpiCard.jsx,
                         SalesSection.jsx, PnlSection.jsx, SgaSection.jsx,
                         HeadcountSection.jsx, NwcSection.jsx, SummarySection.jsx,
                         Assistant.jsx, Sparkline.jsx, TrendArrow.jsx
```

---

## 4. Backend Specification

### 4.1 Shared filter contract (`filters.py`)

Every section endpoint accepts these query params (all optional unless noted):

| Param | Type / values | Default | Meaning |
|---|---|---|---|
| `year` | int (2023/2024) | 2024 | reporting year |
| `month` | int 1–12 | 5 | reporting month (ACT capped at 202405) |
| `sector` | BBM\|BBI\|BBG\|BBE\|ALL | ALL | sector tab; ALL = consolidated Group |
| `area` | e.g. Europe | — | geography filter via dim_country |
| `subregion` | e.g. Western Europe | — | " |
| `country` | ISO-2 e.g. DE | — | " |
| `entity_id` | int | — | single legal entity |
| `division` | division_code | — | single division |
| `currency` | EUR\|LOCAL | EUR | value column choice |
| `view` | NOM\|REAL | NOM | nominal vs real (woc) |
| `cmp` | CF\|BP | CF | which plan scenario the "vs forecast" columns compare to |

Implementation:
- `period_id = year*100 + month`; `py_period_id = period_id - 100`; YTD range `(year*100+1) .. period_id`; PY YTD range `((year-1)*100+1) .. py_period_id`.
- Geography filters resolve to a set of `entity_id`s via `dim_legal_entity JOIN dim_country` and are applied as `f.entity_id IN (...)`.
- Value column resolver: `EUR+NOM → value_eur_nom`; `EUR+REAL → value_eur_real`; `LOCAL` allowed **only if** the filtered entity set spans exactly one `currency_code` → `value_lc`; otherwise fall back to `value_eur_nom` and set `"currency_note": "Local currency requires a single-currency selection; showing EUR."` in the response meta.
- Every response includes a `meta` object echoing the resolved filters: `{"period_id": 202405, "sector": "ALL", "currency_used": "EUR", "view": "NOM", "cmp": "CF", "currency_note": null}`.

### 4.2 Canonical SQL patterns (reuse everywhere)

vs PY self-join (current month, one measure-set):
```sql
SELECT f.measure_code,
       SUM(f.{val})              AS cur,
       SUM(py.{val})             AS py,
       SUM(f.value_eur_nom)      AS cur_nom,     -- always also return the nom/real pair
       SUM(f.value_eur_real)     AS cur_real
FROM fact_financials f
LEFT JOIN fact_financials py
       ON py.scenario_code='ACT' AND py.period_id = f.period_id - 100
      AND py.entity_id=f.entity_id AND py.sector_code=f.sector_code
      AND py.division_code=f.division_code AND py.measure_code=f.measure_code
WHERE f.scenario_code='ACT' AND f.period_id=:pid
  AND f.measure_code IN (...) {extra_filters}
GROUP BY f.measure_code;
```
vs CF/BP: same WHERE but `scenario_code=:cmp` on a second aggregate (or `GROUP BY scenario_code` over `IN ('ACT', :cmp)`).
YTD flows: `WHERE period_id BETWEEN :ytd_start AND :pid` and SUM. YTD balances: just the selected month.
Variance helpers (Python): `pct(cur, base) = (cur/base - 1) * 100` guarded for base≈0/NULL; round values to 1 decimal, percentages to 1 decimal.

### 4.3 Endpoint contracts

#### GET `/api/meta/filters`
Returns all dimension values for the UI:
```json
{
  "sectors": [{"code":"BBM","name":"Mobility Solutions"}, ...],
  "areas": ["Europe","Americas","Asia Pacific"],
  "subregions": [{"name":"Western Europe","area":"Europe"}, ...],
  "countries": [{"code":"DE","name":"Germany","subregion":"Western Europe","area":"Europe","currency":"EUR"}, ...],
  "entities": [{"id":1,"code":"RBDE","name":"Robert Bosch GmbH","country":"DE"}, ...],
  "divisions": [{"code":"PS","name":"...","sector":"BBM"}, ...],
  "periods": {"act_max": 202405, "years":[2023,2024], "months_by_year": {"2023":[1..12],"2024":[1..5]}},
  "scenarios": ["ACT","CF","BP"]
}
```

#### GET `/api/sales`
```json
{
  "meta": {...},
  "kpis": [
    {"measure":"TGS","label":"TGS","month":{"value":8211.2,"vs_py_pct":4.0,"vs_cmp_pct":1.2},
     "ytd":{"value":40123.4,"vs_py_pct":3.1,"vs_cmp_pct":0.8},
     "real_nominal":{"nom":8211.2,"real":8190.1}},
    ... TNS, INT_SALES, STP_REGION ...
  ],
  "sector_breakdown": [
    {"sector":"BBM","name":"Mobility Solutions","tns":4974.5,"vs_py_pct":6.5},
    ... BBI, BBG, BBE ...
  ]
}
```
`sector_breakdown` is always computed without the sector filter (it powers the under-cards business-sector chart) but respects geography/division filters.

#### GET `/api/pnl`
```json
{
  "meta": {...},
  "ebit": {
    "month": {"act":411.0,"py":390.2,"cf":405.5,"bp":408.7,
              "vs_py_pct":5.3,"vs_cf_pct":1.4,"vs_bp_pct":0.6},
    "ytd":   {"act":2088.9,"py":..., "cf":..., "bp":..., "vs_py_pct":..., "vs_cf_pct":..., "vs_bp_pct":...},
    "pct_of_tns": {"month_act":5.24,"month_py":...,"month_cf":5.17,"month_bp":5.20,
                   "ytd_act":...,"ytd_py":...,
                   "vs_py_pp":0.1,"vs_cf_pp":0.07,"vs_bp_pp":0.04}
  }
}
```
Percentage-point deltas (`_pp`) for the margin rows; percent deltas for absolute EBIT.

#### GET `/api/sga`
```json
{
  "meta": {...},
  "rows": [
    {"group":"FIXED","measure":"SGA_RD","label":"R&D Cost","is_cost":true,
     "month":{"value":..., "vs_py_pct":...,"vs_cmp_pct":...},
     "ytd":{"value":3104.0,"py":2954.4,"vs_py_pct":5.1,"vs_cmp_pct":...}},
    ... SGA_SALES, SGA_ADMIN, SGA_VAR, OTHER_OPINC ...
  ],
  "totals": {"fixed_ytd":6798.7,"variable_ytd":1678.3,"sga_total_ytd":8477.0, "vs_py_pct":...}
}
```
Order rows by `dim_measure.sort_order`, grouped FIXED → VARIABLE → OTHER.

#### GET `/api/headcount`
```json
{
  "meta": {...},
  "cards": {
    "state":{"total":409205,"direct_pct":60.3,"vs_py_pct":0.6},
    "avg":  {"total":407979,"vs_py_pct":...},
    "pc_fte":{"total":379420,"direct_pct":...,"vs_py_pct":...,"vs_cmp_pct":...}
  },
  "trend": [
    {"period":202306,"label":"Jun 23","hc_state":...,"pc_fte":...}, ... 12 rolling months up to selected ...
  ]
}
```

#### GET `/api/nwc`
```json
{
  "meta": {...},
  "balances": [
    {"measure":"AR","label":"Accounts Receivable","value":11576.3,"vs_py_pct":-5.0,
     "spark":[{"period":202306,"value":...}, ...12m...]},
    ... AP, INVENTORY ...
  ],
  "flows": [
    {"measure":"CAPEX","label":"CAPEX","is_cost":true,"month":432.8,"ytd":2079.9,"vs_py_pct":...,"spark":[...]},
    {"measure":"IFCF","label":"iFCF","month":274.1,"ytd":1778.2,"vs_py_pct":...,"spark":[...]}
  ]
}
```

#### GET `/api/summary`
```json
{
  "meta": {...},
  "mbr_status": {"APPROVED":8,"SUBMITTED":3,"DRAFT":4},
  "anomalies": [
    {"severity":"CRITICAL","rule":"NEG_EBIT","message":"...","entity":"...","measure":"EBIT"}, ...OPEN only...
  ],
  "ai_summaries": [{"entity":"Robert Bosch GmbH","status":"DRAFT","text":"Auto-generated MBR draft ..."}],
  "bullets": ["..."]
}
```
`bullets` are computed in Python (no LLM): TNS vs PY direction, best/worst sector, EBIT vs CF, open-anomaly count. The LLM-generated summary comes from `/api/assistant/generate-summary`.

#### POST `/api/assistant/chat`
Request: `{"messages":[{"role":"user","content":"Why did TNS grow vs PY?"}], "filters":{...same keys as query params...}}`
Response: **SSE stream** (`text/event-stream`): `data: {"delta":"..."}` chunks, terminated by `data: {"done":true}`. On missing Azure config: single event `data: {"error":"AI layer not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, MODEL_DEPLOYMENT_NAME."}`.

#### POST `/api/assistant/generate-summary`
Request: `{"filters":{...}}`. Runs the data → sanity-check → narrative workflow (Section 5) and streams the executive-summary draft the same SSE way.

### 4.4 Error handling & conventions
- All endpoints are read-only; open SQLite with `mode=ro` URI; one connection per request (SQLite is fine for this load).
- Validate params with Pydantic; invalid enum values → 422.
- Unknown/empty result sets return zeros/nulls, not 500s.
- Run with `uvicorn backend.main:app --reload --port 8000`; resolve the db path relative to the backend package location so the working directory doesn't matter.

---

## 5. AI Layer — Microsoft Agent Framework

### 5.1 Configuration (`agents/config.py`)
Env vars (loaded once; expose `is_configured()`):
- `AZURE_OPENAI_ENDPOINT` (or `AZURE_AI_PROJECT_ENDPOINT` if using a Foundry project client)
- `AZURE_OPENAI_API_KEY` — optional if using `azure-identity` `DefaultAzureCredential`
- `MODEL_DEPLOYMENT_NAME` — the chat deployment to use (could be a Claude Sonnet 4.6 deployment in Foundry, or a GPT deployment; the code must not assume a vendor)
- `AZURE_OPENAI_API_VERSION` — optional override

Factory returns a MAF chat client (`agent_framework.azure` — e.g. `AzureOpenAIChatClient(endpoint=..., api_key=..., deployment_name=...)`). **Implementation note for the code generator:** verify exact class/parameter names against the installed `agent-framework` package version (the package is in public preview and APIs move); do not invent method names — check the installed package / its docs at build time.

### 5.2 Function tools (`agents/tools.py`)
Plain typed Python functions (annotated for MAF tool registration), all delegating to `backend/queries.py` so REST and agents share one query implementation. All return compact JSON-serializable dicts.

| Tool | Signature | Returns |
|---|---|---|
| `get_kpi_snapshot` | `(year:int, month:int, sector:str='ALL') -> dict` | sales KPIs + EBIT + margin + vs PY/CF/BP for the filter |
| `get_sga_breakdown` | `(year:int, month:int, sector:str='ALL') -> dict` | SG&A rows YTD vs PY |
| `get_headcount` | `(year:int, month:int, sector:str='ALL') -> dict` | HC/PC cards |
| `get_nwc` | `(year:int, month:int, sector:str='ALL') -> dict` | balances + flows |
| `get_open_anomalies` | `(period_id:int) -> list[dict]` | OPEN anomaly_flags with severity/message/entity |
| `get_controller_comments` | `(sector:str, entity_id:int|None, limit:int=6) -> list[dict]` | most recent comments (text, author, month) |
| `get_mbr_status` | `(period_id:int) -> dict` | status counts + ai_summary drafts |

### 5.3 Agents (`agents/prompts.py` + `orchestrator.py`)
Three `ChatAgent`s on the shared chat client, each with scoped tools:

1. **data_agent** — instructions: senior financial analyst for the Bosch management dashboard; answer quantitative questions ONLY using tool results; report figures in € millions with vs-PY/CF/BP context; never invent numbers. Tools: kpi_snapshot, sga, headcount, nwc.
2. **sanity_agent** — instructions: pre-submission sanity checker for the MBR; review open anomalies, assess severity, state which items block submission and why. Tools: get_open_anomalies, get_kpi_snapshot, get_mbr_status.
3. **narrative_agent** — instructions: drafts MBR executive commentary in the established controller style (concise, factual, variance-led, e.g. "Net sales of EUR 1219m (+6.9% vs PY) supported by new product ramp-ups; CF for FY confirmed."); uses recent controller comments as style examples; outputs 4–6 bullet executive summary. Tools: get_controller_comments (plus receives upstream agents' outputs as context).

### 5.4 Orchestration
- **`generate_summary(filters)`** — MAF **sequential workflow**: data_agent ("summarize the period's KPI picture") → sanity_agent ("list open issues") → narrative_agent ("write the executive summary using both"). Stream final agent output token-wise.
- **`chat(messages, filters)`** — single routed assistant: data_agent with ALL tools attached plus a short routing instruction (answer data questions via tools; for anomaly/sanity questions consult anomalies; keep answers under ~150 words unless asked). Multi-turn: pass prior messages as MAF thread/history. Stream responses.
- Both wrapped in `async` generators consumed by FastAPI `StreamingResponse(media_type="text/event-stream")`.

---

## 6. Frontend Specification

### 6.1 State & data flow
`App.jsx` owns a single `filters` state object `{year, month, sector, area, subregion, country, entity_id, division, currency, view, cmp}` (defaults: 2024/5/ALL/EUR/NOM/CF). Any change triggers refetch of all five section endpoints + summary (use a small `useFetch(url, filters)` hook; serialize filters → query string, skip nulls). `meta/filters` fetched once at mount. Cascading dropdowns: subregion options filtered by selected area, countries by subregion, entities by country; division options filtered by active sector tab; changing a parent resets children.

### 6.2 Layout (one-page landscape grid)

```
┌────────────────────────────────────────────────────────────────────┐
│ HEADER: [BOSCH·red] | Management Dashboard      Year▾ Month▾ CF/BP │
├────────────────────────────────────────────────────────────────────┤
│ SECTOR TABS:  [Group] [BBM Mobility] [BBI Industrial] [BBG] [BBE]  │
├────────────────────────────────────────────────────────────────────┤
│ FILTERS: Area▾ Subregion▾ Country▾ Entity▾ Division▾ │ EUR/Local │ Real/Nominal │
├──────────────────────────────────┬─────────────────────────────────┤
│ SALES PERFORMANCE                │ HEADCOUNT & PERSONNEL           │
│  [TGS][TNS][STP][IntSales] cards │  [Total HC][PC FTE] cards       │
│  sector-breakdown bar chart      │  12-month trend bar/line chart  │
├──────────────────────────────────┼─────────────────────────────────┤
│ P&L HIGHLIGHTS (EBIT table)      │ NWC                             │
│  month/YTD × vsPY/vsCF/vsBP      │  [AR][AP][Inventory]            │
│  EBIT % of TNS row               │  [CAPEX][iFCF] w/ sparklines    │
├──────────────────────────────────┼─────────────────────────────────┤
│ SG&A COST BREAKDOWN (table)      │ EXECUTIVE SUMMARY               │
│  Fixed: R&D/Sales/Admin          │  bullets + anomaly badges       │
│  Variable · Other Op Inc/Exp     │  [AI Assistant chat panel]      │
└──────────────────────────────────┴─────────────────────────────────┘
```
CSS grid, two columns (≈55%/45%), white cards (`border-radius 8px`, subtle shadow) on light-gray page.

### 6.3 Design tokens (`styles.css`)
```
--bosch-red:    #E20015;   /* brand accent, BOSCH wordmark */
--bosch-blue:   #007BC0;   /* primary accent, active tab, links */
--bosch-darkblue:#005691;  /* section titles */
--bg-page:      #F2F4F7;
--bg-card:      #FFFFFF;
--border:       #E0E4E8;
--text-main:    #1F2937;
--text-muted:   #6B7280;
--pos-green:    #00884A;
--neg-red:      #D32F2F;
font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
```
- Header: white bg, "BOSCH" in bold red letters + gray divider + "Management Dashboard" in dark gray. (Text wordmark only — no logo asset.)
- Active sector tab: bosch-blue background, white text; inactive: light gray.
- KPI cards: big value (24–28px semibold), small unit "€ m", variance line with TrendArrow.

### 6.4 Variance display rules (`TrendArrow.jsx`)
- ▲ + green when variance is **favorable**, ▼ + red when **unfavorable**.
- Favorability inverts for cost measures (`is_cost=true` from API: SGA_*, CAPEX): a **negative** vs-PY % is favorable (simplest rule: color by favorability, arrow direction by sign).
- Format: `+4.0% vs PY`, percentage-points as `+0.1pp` for margin rows.
- Show `Real (woc)` vs `Nominal` mini-comparison in sales cards footer when view data present.

### 6.5 Charts (Recharts)
- Sector breakdown: `BarChart` (x: sector code, y: TNS € m, fill bosch-blue, active sector highlighted bosch-darkblue; tooltip shows name + vs PY).
- Headcount trend: `ComposedChart` — bars = HC state, line = PC FTE, 12 rolling months.
- NWC sparklines: tiny `AreaChart` (60×28px) per card, stroke green if last vs-PY favorable else red.

### 6.6 AI Assistant panel (`Assistant.jsx`)
- Collapsible card "AI Assistant" with message list + input ("Ask about the numbers…").
- POSTs to `/api/assistant/chat` with current `filters`; reads the SSE stream via `fetch` + `ReadableStream` reader, appending `delta`s live.
- "Generate executive summary" button → `/api/assistant/generate-summary`, streams into the Executive Summary card.
- Renders the configured-error event as a muted inline notice.

---

## 7. Implementation Order

1. `backend/db.py`, `filters.py`, `queries.py`, `routers/meta.py` — verify `/api/meta/filters` with curl.
2. Section routers (sales → pnl → sga → headcount → nwc → summary). After each, curl with no filters and check against §2.5 benchmarks.
3. Filter correctness pass: sector=BBM TNS=4,974.5; entity/country filter + currency=LOCAL returns LC and `currency_used:"LOCAL"`; view=REAL Group TNS=7,828.3; cmp=BP changes the vs-forecast columns.
4. AI layer: `pip install agent-framework azure-identity`; confirm actual MAF API surface from installed package; implement tools → agents → orchestrator → assistant router. Without Azure env vars the endpoints must return the friendly not-configured event (test this path too).
5. Frontend scaffold: `npm create vite@latest frontend -- --template react`; `npm i recharts`; vite proxy `/api` → 8000.
6. Components: Header/SectorTabs/FilterBar + state plumbing → KpiCard/TrendArrow → sections in layout order → Assistant last.
7. Styling pass against §6.2/§6.3; verify responsive at 1366×768 and 1920×1080.

## 8. End-to-End Verification

1. `uvicorn backend.main:app --port 8000` then curl each endpoint; values must match §2.5.
2. `npm run dev` in `frontend/`; open http://localhost:5173:
   - Default view shows Group, May 2024; TNS card reads €7,847.7m +4.0% vs PY.
   - Click BBM tab → TNS 4,974.5, breakdown chart highlights BBM; BBI tab shows negative vs PY (≈ −5.5% storyline).
   - Germany country filter + Currency=Local works (EUR country → identical values, `currency_used:"LOCAL"`); a CNY entity (Bosch (China) Investment Ltd.) shows LC ≠ EUR and Real ≠ Nominal.
   - Toggle CF↔BP changes forecast-comparison columns.
3. With Azure env vars set: ask the assistant "Why did TNS grow vs PY?" → streamed answer citing tool-derived figures; "Generate executive summary" → data→sanity→narrative output referencing the open CRITICAL anomaly.
4. Without Azure env vars: assistant shows the not-configured notice; rest of dashboard unaffected.

## 9. Out of Scope (for now)
- Authentication/authorization, deployment packaging, write operations (MBR submit/approve workflow buttons), multi-language UI, export to PPT/PDF. The data model supports these later.
