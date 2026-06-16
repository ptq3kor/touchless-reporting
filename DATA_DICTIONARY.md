# Touchless Reporting — Management Dashboard Database

**File:** `touchless_reporting.db` (SQLite) · All financial values in **millions** · Reporting currency EUR

Supports the Bosch-style Management Dashboard: 4 business-sector tabs, geography/entity/division filters, Local/EUR currency toggle, Real (woc) vs Nominal view, and Actual / Prior Year / Current Forecast / Business Plan comparisons — plus the AI layer (controller comments, anomaly sanity checks, MBR workflow) from the Touchless Reporting use case.

---

## 1. Model Overview (Star Schema)

```
                          dim_period (24 months: 2023-01 .. 2024-12)
                          dim_scenario (ACT / CF / BP)
                          dim_measure (15 KPIs)
                                 |
 dim_business_sector ----+       |
 dim_division -----------+-- fact_financials (62.7k rows)
 dim_legal_entity -------+-- fact_headcount  (4.2k rows)
        |                        |
 dim_country (area/subregion/ccy)|
                          fx_rates (nominal + plan rates)

 AI / workflow layer:
   controller_comments   (historical commentary -> narrative generation)
   anomaly_flags         (sanity checks / early warnings)
   mbr_submissions       (DRAFT -> SUBMITTED -> APPROVED workflow + AI summary)
```

**Grain of `fact_financials`:** period × scenario × legal entity × sector × division × measure.
Every higher level on the dashboard (sector tab, country, area, "Legal Entity = BBM+BBI+BBG+BBE") is a **SUM over this grain**.

---

## 2. Key Modeling Decisions (read before building the backend)

| Dashboard feature | How the model supports it |
|---|---|
| Sector tabs BBM/BBI/BBG/BBE + consolidated | `sector_code` on every fact row; consolidation = no sector filter |
| Area → Subregion → Country filters | `dim_legal_entity.country_code → dim_country (subregion, area)` |
| Currency toggle Local / EUR | `value_lc` (entity's local currency) vs `value_eur_nom` |
| View toggle Real (nom) / Nominal (woc) | `value_eur_nom` (actual FX) vs `value_eur_real` (translated at frozen plan FX rates → "without currency effect") |
| vs PY | **Not stored as a scenario.** Join ACT rows of `period_id - 100` (same month, prior year) |
| vs CF / vs BP | Scenario codes `CF` and `BP`; CF Jan–May ≈ ACT (locked), Jun–Dec is forecast |
| YTD | `period_id BETWEEN <year>01 AND <selected period>` — flows (sales, costs, CAPEX, iFCF) are summed; **balances (AR/AP/Inventory, `dim_measure.is_balance=1`) take the latest month, never sum** |
| EBIT % of TNS | Ratio of two measures at query time (never pre-aggregated) |
| Headcount state vs average, direct/indirect, PC | Dedicated columns in `fact_headcount` |

Current reporting month in the data: **May 2024** (ACT available 2023-01 → 2024-05).

---

## 3. Tables

### Dimensions
| Table | Contents |
|---|---|
| `dim_business_sector` | BBM Mobility Solutions, BBI Industrial Technology, BBG Consumer Goods, BBE Energy and Building Technology |
| `dim_country` | 11 countries with `subregion`, `area` (Europe / Americas / Asia Pacific), local `currency_code` |
| `dim_legal_entity` | 15 legal entities (Robert Bosch GmbH, Bosch Rexroth AG, BSH Hausgeraete GmbH, Bosch (China) Investment Ltd., …) |
| `dim_division` | 13 divisions mapped to sectors (PS, CC, ED, AE, MA, XC / DC, CI / PT, BS / BT, HC, SO) |
| `dim_period` | `period_id = YYYYMM`, plus year, month, quarter, month name, start/end dates |
| `dim_scenario` | `ACT`, `CF`, `BP` |
| `dim_measure` | KPI catalog incl. `category` (SALES/PNL/SGA/NWC), `sub_category` (FIXED/VARIABLE/OTHER for SG&A), `is_cost`, `is_balance` |

### Measures (`dim_measure`)
| Code | Name | Section on dashboard |
|---|---|---|
| TGS, TNS, INT_SALES, STP_REGION | Total Gross/Net Sales, Internal Sales, Sales to 3rd Parties in Region | Sales Performance |
| EBIT | EBIT | P&L Highlights (EBIT % of TNS computed) |
| SGA_RD, SGA_SALES, SGA_ADMIN | Fixed SG&A: R&D / Sales / Admin | SG&A Cost Breakdown |
| SGA_VAR | Variable SG&A | SG&A Cost Breakdown |
| OTHER_OPINC | Other Operating Income/Expense (signed) | SG&A Cost Breakdown |
| AR, AP, INVENTORY | Month-end balances (`is_balance=1`) | NWC |
| CAPEX, IFCF | CAPEX (flow), internal Free Cash Flow (signed, can be negative) | NWC |

Costs (`is_cost=1`) are stored as **positive expense amounts**.

### Facts
**`fact_financials`** — `value_lc` (local ccy m), `value_eur_nom` (EUR m at actual monthly FX), `value_eur_real` (EUR m at plan FX = "woc"). For EUR-country entities all three EUR-relevant values coincide.

**`fact_headcount`** — `hc_state_*` (month-end headcount), `hc_avg_*` (monthly average), `pc_fte_*` (Personnel Capacity in FTE, ≈ 93% of average HC), each split `_direct` / `_indirect`.

**`fx_rates`** — monthly average `rate_to_eur` (1 EUR = X LC) and frozen `plan_rate_to_eur` per year (used for the Real/woc translation).

### AI / Workflow layer
| Table | Purpose in the use case |
|---|---|
| `controller_comments` | 283 historical comments (TNS/EBIT, per entity·sector·month, with author/controller) — the corpus for AI narrative generation and RAG |
| `anomaly_flags` | Sanity-check results: rule_code (MOM_SWING, NEG_EBIT, INV_DOH, PY_DEVIATION, MARGIN_DROP, COST_OVERRUN, ONE_OFF…), severity, status OPEN/REVIEWED/RESOLVED. 6 OPEN items in the current cycle |
| `mbr_submissions` | MBR workflow per entity·month: DRAFT/SUBMITTED/APPROVED, controller, GM approver, `sanity_check_passed`, `ai_summary` draft. May 2024 deliberately in-flight (mixed statuses) |

---

## 4. Canonical Query Patterns

**KPI card: TNS current month vs PY (sector tab = BBM, EUR nominal)**
```sql
SELECT SUM(f.value_eur_nom)                              AS tns_cur,
       SUM(py.value_eur_nom)                             AS tns_py,
       (SUM(f.value_eur_nom)/SUM(py.value_eur_nom)-1)*100 AS vs_py_pct
FROM fact_financials f
LEFT JOIN fact_financials py
       ON py.scenario_code = 'ACT'
      AND py.period_id     = f.period_id - 100      -- same month, prior year
      AND py.entity_id     = f.entity_id
      AND py.sector_code   = f.sector_code
      AND py.division_code = f.division_code
      AND py.measure_code  = f.measure_code
WHERE f.scenario_code='ACT' AND f.period_id=202405
  AND f.sector_code='BBM' AND f.measure_code='TNS';
```

**EBIT % of TNS — current month, vs CF and BP**
```sql
SELECT scenario_code,
       SUM(CASE WHEN measure_code='EBIT' THEN value_eur_nom END) AS ebit,
       SUM(CASE WHEN measure_code='EBIT' THEN value_eur_nom END)
     / SUM(CASE WHEN measure_code='TNS'  THEN value_eur_nom END) * 100 AS ebit_pct
FROM fact_financials
WHERE period_id=202405 AND sector_code='BBM'
GROUP BY scenario_code;        -- ACT vs CF vs BP side by side
```

**SG&A breakdown YTD vs PY**
```sql
SELECT m.sub_category, m.measure_name,
       SUM(CASE WHEN f.period_id BETWEEN 202401 AND 202405 THEN f.value_eur_nom END) AS ytd_2024,
       SUM(CASE WHEN f.period_id BETWEEN 202301 AND 202305 THEN f.value_eur_nom END) AS ytd_py
FROM fact_financials f JOIN dim_measure m USING (measure_code)
WHERE f.scenario_code='ACT' AND m.category='SGA' AND f.sector_code='BBM'
GROUP BY 1,2 ORDER BY m.sort_order;
```

**Currency / view toggles** — select the column:
`value_lc` (Local) · `value_eur_nom` (EUR, Nominal) · `value_eur_real` (EUR, Real/woc).
*Caveat: only aggregate `value_lc` when the filter pins a single local currency (e.g., one country/entity).*

**Headcount card (state, direct/indirect, PC)**
```sql
SELECT SUM(hc_state_direct+hc_state_indirect)               AS total_hc,
       SUM(hc_state_direct)*100.0/SUM(hc_state_direct+hc_state_indirect) AS direct_pct,
       SUM(pc_fte_direct+pc_fte_indirect)                   AS pc_fte
FROM fact_headcount
WHERE scenario_code='ACT' AND period_id=202405;
```

**NWC balances — latest month, never summed over time**
```sql
SELECT measure_code, SUM(value_eur_nom)
FROM fact_financials
WHERE scenario_code='ACT' AND period_id=202405      -- balance: pick the month
  AND measure_code IN ('AR','AP','INVENTORY')
GROUP BY 1;
```

**AI assistant context for an entity's MBR**
```sql
SELECT c.comment_text, c.author, p.month_name, p.year
FROM controller_comments c JOIN dim_period p USING (period_id)
WHERE c.entity_id=12 AND c.sector_code='BBM'
ORDER BY c.period_id DESC LIMIT 6;

SELECT message, severity FROM anomaly_flags
WHERE status='OPEN' AND period_id=202405;
```

---

## 5. Built-in Realism (for demo storytelling)

- **Sector trajectories 2024 vs PY:** BBM ≈ +6.5% (growth), BBI ≈ −5.5% (industrial downturn), BBG ≈ −1.5% (soft consumer demand), BBE ≈ +3% — so each sector tab tells a different story, with sector-typical EBIT margins (BBI highest ~8.8%, BBM ~4.8%).
- **CF vs BP tension:** BP was set optimistically (e.g., BBI planned +1% but is running −5.5%), so the CF deviates from BP in H2 — visible in forecast-comparison columns.
- **FX effects:** non-EUR entities (CNY, HUF, USD, INR, …) show Real ≠ Nominal; FX rates follow a monthly random walk against frozen plan rates.
- **Seasonality:** August trough, March/October peaks; CAPEX loaded into Q4.
- **In-flight reporting cycle:** May 2024 MBRs are mixed DRAFT/SUBMITTED/APPROVED with 6 open anomaly flags (1 CRITICAL) — exactly the pre-submission sanity-check moment the use case targets.
- Deterministic generation (seed 42) — regenerating with `generate_db.py` reproduces identical data.
