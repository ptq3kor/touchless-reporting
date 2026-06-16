"""
Touchless Reporting — Management Dashboard Database Generator
=============================================================
Generates a SQLite database (star schema) with realistic, Bosch-scale
financial data supporting the Management Dashboard:

  - 4 Business Sectors (BBM, BBI, BBG, BBE), consolidation = sum of sectors
  - Geography: Area -> Subregion -> Country -> Legal Entity
  - Divisions per sector
  - Scenarios: ACT (actuals), CF (current forecast), BP (business plan)
    (Prior Year = ACT of previous year, derived at query time)
  - Currency: local currency + EUR nominal + EUR real (woc, at plan FX rates)
  - Measures: Sales (TGS, TNS, Internal, STP-in-region), EBIT,
    SG&A breakdown, Other Op Inc/Exp, NWC (AR/AP/Inventory/CAPEX/iFCF)
  - Headcount & Personnel Capacity (state/average, direct/indirect)
  - AI layer: controller comments, anomaly flags, MBR submission workflow

All financial values are in EUR millions (value_eur_*) / LC millions (value_lc).
Time coverage: ACT 2023-01 .. 2024-05, CF 2024-01..12, BP 2024-01..12.
"""

import sqlite3
import random
import math
import os
from datetime import datetime, timedelta

random.seed(42)

DB_PATH = "/home/claude/touchless/touchless_reporting.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("PRAGMA journal_mode=WAL;")

# ----------------------------------------------------------------------------
# 1. SCHEMA
# ----------------------------------------------------------------------------
cur.executescript("""
-- ===================== DIMENSIONS =====================

CREATE TABLE dim_business_sector (
    sector_code   TEXT PRIMARY KEY,          -- BBM / BBI / BBG / BBE
    sector_name   TEXT NOT NULL,
    sort_order    INTEGER NOT NULL
);

CREATE TABLE dim_country (
    country_code  TEXT PRIMARY KEY,          -- ISO-2
    country_name  TEXT NOT NULL,
    subregion     TEXT NOT NULL,             -- e.g. Western Europe
    area          TEXT NOT NULL,             -- Europe / Americas / Asia Pacific
    currency_code TEXT NOT NULL              -- local currency
);

CREATE TABLE dim_legal_entity (
    entity_id     INTEGER PRIMARY KEY,
    entity_code   TEXT UNIQUE NOT NULL,
    entity_name   TEXT NOT NULL,
    country_code  TEXT NOT NULL REFERENCES dim_country(country_code)
);

CREATE TABLE dim_division (
    division_code TEXT PRIMARY KEY,
    division_name TEXT NOT NULL,
    sector_code   TEXT NOT NULL REFERENCES dim_business_sector(sector_code)
);

CREATE TABLE dim_period (
    period_id     INTEGER PRIMARY KEY,       -- YYYYMM
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    TEXT NOT NULL,
    quarter       TEXT NOT NULL,             -- Q1..Q4
    period_start  TEXT NOT NULL,             -- ISO date
    period_end    TEXT NOT NULL
);

CREATE TABLE dim_scenario (
    scenario_code TEXT PRIMARY KEY,          -- ACT / CF / BP
    scenario_name TEXT NOT NULL,
    description   TEXT
);

CREATE TABLE dim_measure (
    measure_code  TEXT PRIMARY KEY,
    measure_name  TEXT NOT NULL,
    category      TEXT NOT NULL,             -- SALES / PNL / SGA / NWC
    sub_category  TEXT,                      -- e.g. FIXED / VARIABLE for SG&A
    unit          TEXT NOT NULL,             -- 'EUR m' or 'LC m'
    is_cost       INTEGER NOT NULL DEFAULT 0,-- 1 = cost (positive = expense)
    is_balance    INTEGER NOT NULL DEFAULT 0,-- 1 = month-end balance (AR/AP/INV)
    sort_order    INTEGER NOT NULL
);

-- ===================== REFERENCE =====================

CREATE TABLE fx_rates (
    currency_code     TEXT NOT NULL,
    period_id         INTEGER NOT NULL REFERENCES dim_period(period_id),
    rate_to_eur       REAL NOT NULL,         -- 1 EUR = X LC (monthly avg)
    plan_rate_to_eur  REAL NOT NULL,         -- budget/plan FX rate (constant per year)
    PRIMARY KEY (currency_code, period_id)
);

-- ===================== FACTS =====================

CREATE TABLE fact_financials (
    fact_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id      INTEGER NOT NULL REFERENCES dim_period(period_id),
    scenario_code  TEXT    NOT NULL REFERENCES dim_scenario(scenario_code),
    entity_id      INTEGER NOT NULL REFERENCES dim_legal_entity(entity_id),
    sector_code    TEXT    NOT NULL REFERENCES dim_business_sector(sector_code),
    division_code  TEXT    NOT NULL REFERENCES dim_division(division_code),
    measure_code   TEXT    NOT NULL REFERENCES dim_measure(measure_code),
    currency_code  TEXT    NOT NULL,
    value_lc       REAL    NOT NULL,          -- local currency, millions
    value_eur_nom  REAL    NOT NULL,          -- EUR m, nominal (actual FX)
    value_eur_real REAL    NOT NULL           -- EUR m, real / woc (plan FX)
);

CREATE TABLE fact_headcount (
    fact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id        INTEGER NOT NULL REFERENCES dim_period(period_id),
    scenario_code    TEXT    NOT NULL REFERENCES dim_scenario(scenario_code),
    entity_id        INTEGER NOT NULL REFERENCES dim_legal_entity(entity_id),
    sector_code      TEXT    NOT NULL REFERENCES dim_business_sector(sector_code),
    division_code    TEXT    NOT NULL REFERENCES dim_division(division_code),
    hc_state_direct    REAL NOT NULL,         -- headcount at month end
    hc_state_indirect  REAL NOT NULL,
    hc_avg_direct      REAL NOT NULL,         -- average headcount in month
    hc_avg_indirect    REAL NOT NULL,
    pc_fte_direct      REAL NOT NULL,         -- personnel capacity (FTE)
    pc_fte_indirect    REAL NOT NULL
);

-- ===================== AI / WORKFLOW LAYER =====================

CREATE TABLE controller_comments (
    comment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id     INTEGER NOT NULL REFERENCES dim_period(period_id),
    entity_id     INTEGER NOT NULL REFERENCES dim_legal_entity(entity_id),
    sector_code   TEXT    NOT NULL REFERENCES dim_business_sector(sector_code),
    measure_code  TEXT    NOT NULL REFERENCES dim_measure(measure_code),
    comment_text  TEXT    NOT NULL,
    author        TEXT    NOT NULL,
    language      TEXT    NOT NULL DEFAULT 'EN',
    created_at    TEXT    NOT NULL
);

CREATE TABLE anomaly_flags (
    anomaly_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id     INTEGER NOT NULL REFERENCES dim_period(period_id),
    entity_id     INTEGER NOT NULL REFERENCES dim_legal_entity(entity_id),
    sector_code   TEXT    NOT NULL,
    measure_code  TEXT    NOT NULL REFERENCES dim_measure(measure_code),
    rule_code     TEXT    NOT NULL,           -- e.g. MOM_SWING / NEG_EBIT / PY_DEVIATION
    severity      TEXT    NOT NULL,           -- INFO / WARNING / CRITICAL
    message       TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'OPEN',  -- OPEN / REVIEWED / RESOLVED
    detected_at   TEXT    NOT NULL
);

CREATE TABLE mbr_submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id     INTEGER NOT NULL REFERENCES dim_period(period_id),
    entity_id     INTEGER NOT NULL REFERENCES dim_legal_entity(entity_id),
    status        TEXT    NOT NULL,           -- DRAFT / SUBMITTED / APPROVED
    submitted_by  TEXT,
    submitted_at  TEXT,
    approved_by   TEXT,
    approved_at   TEXT,
    sanity_check_passed INTEGER,              -- 1/0/NULL
    ai_summary    TEXT                        -- AI-generated exec summary draft
);

-- ===================== INDEXES =====================
CREATE INDEX ix_fin_main ON fact_financials(period_id, scenario_code, sector_code, measure_code);
CREATE INDEX ix_fin_entity ON fact_financials(entity_id, division_code);
CREATE INDEX ix_hc_main  ON fact_headcount(period_id, scenario_code, sector_code);
CREATE INDEX ix_cc_main  ON controller_comments(period_id, entity_id, sector_code);
""")

# ----------------------------------------------------------------------------
# 2. DIMENSION DATA
# ----------------------------------------------------------------------------
sectors = [
    ("BBM", "Mobility Solutions", 1),
    ("BBI", "Industrial Technology", 2),
    ("BBG", "Consumer Goods", 3),
    ("BBE", "Energy and Building Technology", 4),
]
cur.executemany("INSERT INTO dim_business_sector VALUES (?,?,?)", sectors)

countries = [
    # code, name, subregion, area, currency
    ("DE", "Germany",        "Western Europe",        "Europe",       "EUR"),
    ("FR", "France",         "Western Europe",        "Europe",       "EUR"),
    ("HU", "Hungary",        "Central Eastern Europe","Europe",       "HUF"),
    ("CZ", "Czechia",        "Central Eastern Europe","Europe",       "CZK"),
    ("US", "United States",  "North America",         "Americas",     "USD"),
    ("MX", "Mexico",         "North America",         "Americas",     "MXN"),
    ("BR", "Brazil",         "South America",         "Americas",     "BRL"),
    ("CN", "China",          "Greater China",         "Asia Pacific", "CNY"),
    ("IN", "India",          "South Asia",            "Asia Pacific", "INR"),
    ("JP", "Japan",          "Northeast Asia",        "Asia Pacific", "JPY"),
    ("SG", "Singapore",      "Southeast Asia",        "Asia Pacific", "SGD"),
]
cur.executemany("INSERT INTO dim_country VALUES (?,?,?,?,?)", countries)

entities = [
    # id, code, name, country
    (1,  "RBDE", "Robert Bosch GmbH",                   "DE"),
    (2,  "BRDE", "Bosch Rexroth AG",                    "DE"),
    (3,  "BSHD", "BSH Hausgeraete GmbH",                "DE"),
    (4,  "PTDE", "Robert Bosch Power Tools GmbH",       "DE"),
    (5,  "TTDE", "Bosch Thermotechnik GmbH",            "DE"),
    (6,  "RBHU", "Robert Bosch Elektronika Kft.",       "HU"),
    (7,  "BDCZ", "Bosch Diesel s.r.o.",                 "CZ"),
    (8,  "RBFR", "Robert Bosch France S.A.S.",          "FR"),
    (9,  "RBUS", "Robert Bosch LLC",                    "US"),
    (10, "RBMX", "Robert Bosch Mexico S.A. de C.V.",    "MX"),
    (11, "RBBR", "Robert Bosch Ltda.",                  "BR"),
    (12, "RBCN", "Bosch (China) Investment Ltd.",       "CN"),
    (13, "RBIN", "Bosch Limited",                       "IN"),
    (14, "RBJP", "Bosch Corporation",                   "JP"),
    (15, "RBSG", "Robert Bosch (SEA) Pte Ltd",          "SG"),
]
cur.executemany("INSERT INTO dim_legal_entity VALUES (?,?,?,?)", entities)
entity_country = {e[0]: e[3] for e in entities}
country_ccy = {c[0]: c[4] for c in countries}

divisions = [
    ("PS", "Powertrain Solutions",        "BBM"),
    ("CC", "Chassis Systems Control",     "BBM"),
    ("ED", "Electrical Drives",           "BBM"),
    ("AE", "Automotive Electronics",      "BBM"),
    ("MA", "Mobility Aftermarket",        "BBM"),
    ("XC", "Cross-Domain Computing",      "BBM"),
    ("DC", "Drive and Control Technology","BBI"),
    ("CI", "Connected Industry",          "BBI"),
    ("PT", "Power Tools",                 "BBG"),
    ("BS", "BSH Home Appliances",         "BBG"),
    ("BT", "Building Technologies",       "BBE"),
    ("HC", "Home Comfort",                "BBE"),
    ("SO", "Global Service Solutions",    "BBE"),
]
cur.executemany("INSERT INTO dim_division VALUES (?,?,?)", divisions)
sector_divisions = {}
for d, n, s in divisions:
    sector_divisions.setdefault(s, []).append(d)

scenarios = [
    ("ACT", "Actual",           "Actuals from SAP / SAC live connection"),
    ("CF",  "Current Forecast", "Rolling current forecast for the fiscal year"),
    ("BP",  "Business Plan",    "Annual business plan (budget), frozen at year start"),
]
cur.executemany("INSERT INTO dim_scenario VALUES (?,?,?)", scenarios)

measures = [
    # code, name, category, sub_category, unit, is_cost, is_balance, sort
    ("TGS",         "Total Gross Sales",            "SALES", None,       "EUR m", 0, 0, 10),
    ("TNS",         "Total Net Sales",              "SALES", None,       "EUR m", 0, 0, 20),
    ("INT_SALES",   "Internal Sales",               "SALES", None,       "EUR m", 0, 0, 30),
    ("STP_REGION",  "Sales to Third Parties in Region","SALES", None,    "EUR m", 0, 0, 40),
    ("EBIT",        "EBIT",                         "PNL",   None,       "EUR m", 0, 0, 50),
    ("SGA_RD",      "R&D Cost",                     "SGA",   "FIXED",    "EUR m", 1, 0, 60),
    ("SGA_SALES",   "Sales Cost",                   "SGA",   "FIXED",    "EUR m", 1, 0, 70),
    ("SGA_ADMIN",   "Administration Cost",          "SGA",   "FIXED",    "EUR m", 1, 0, 80),
    ("SGA_VAR",     "Variable SG&A",                "SGA",   "VARIABLE", "EUR m", 1, 0, 90),
    ("OTHER_OPINC", "Other Operating Income/Expense","SGA",  "OTHER",    "EUR m", 0, 0, 100),
    ("AR",          "Accounts Receivable",          "NWC",   None,       "EUR m", 0, 1, 110),
    ("AP",          "Accounts Payable",             "NWC",   None,       "EUR m", 0, 1, 120),
    ("INVENTORY",   "Inventory",                    "NWC",   None,       "EUR m", 0, 1, 130),
    ("CAPEX",       "Capital Expenditure",          "NWC",   None,       "EUR m", 1, 0, 140),
    ("IFCF",        "Internal Free Cash Flow",      "NWC",   None,       "EUR m", 0, 0, 150),
]
cur.executemany("INSERT INTO dim_measure VALUES (?,?,?,?,?,?,?,?)", measures)

# Periods: 2023-01 .. 2024-12
month_names = ["January","February","March","April","May","June","July",
               "August","September","October","November","December"]
periods = []
for y in (2023, 2024):
    for m in range(1, 13):
        pid = y * 100 + m
        q = f"Q{(m-1)//3 + 1}"
        start = f"{y}-{m:02d}-01"
        end_day = [31,28,31,30,31,30,31,31,30,31,30,31][m-1] + (1 if (m == 2 and y % 4 == 0) else 0)
        periods.append((pid, y, m, month_names[m-1], q, start, f"{y}-{m:02d}-{end_day:02d}"))
cur.executemany("INSERT INTO dim_period VALUES (?,?,?,?,?,?,?)", periods)

# ----------------------------------------------------------------------------
# 3. FX RATES (monthly random walk; plan rate = Jan rate of the year)
# ----------------------------------------------------------------------------
base_rates = {"EUR": 1.0, "USD": 1.09, "CNY": 7.80, "INR": 90.5, "HUF": 385.0,
              "CZK": 24.6, "BRL": 5.40, "JPY": 158.0, "MXN": 18.6, "SGD": 1.46}
fx_rows = []
fx_lookup = {}   # (ccy, pid) -> (rate, plan_rate)
for ccy, base in base_rates.items():
    rate = base
    plan_rate_by_year = {}
    for (pid, y, m, *_rest) in periods:
        if ccy == "EUR":
            rate_m, plan = 1.0, 1.0
        else:
            rate *= (1 + random.gauss(0, 0.008))
            rate_m = round(rate, 4)
            if m == 1:
                plan_rate_by_year[y] = rate_m
            plan = plan_rate_by_year[y]
        fx_rows.append((ccy, pid, rate_m, plan))
        fx_lookup[(ccy, pid)] = (rate_m, plan)
cur.executemany("INSERT INTO fx_rates VALUES (?,?,?,?)", fx_rows)

# ----------------------------------------------------------------------------
# 4. BUSINESS ASSUMPTIONS
# ----------------------------------------------------------------------------
# Annual TNS 2023 per sector (EUR m) — Bosch-scale
sector_tns_2023 = {"BBM": 56200.0, "BBI": 7100.0, "BBG": 19900.0, "BBE": 7600.0}
# YoY growth ACT 2024
sector_growth   = {"BBM": 0.065, "BBI": -0.055, "BBG": -0.015, "BBE": 0.030}
# BP growth (plan set slightly optimistic vs what actually happens)
sector_bp_growth= {"BBM": 0.055, "BBI": 0.010, "BBG": 0.010, "BBE": 0.040}

# Entity weights per sector (sum to 1.0)
entity_weights = {
    "BBM": {1: .26, 6: .07, 7: .05, 8: .05, 9: .14, 10: .05, 11: .04, 12: .18, 13: .05, 14: .08, 15: .03},
    "BBI": {2: .52, 9: .16, 12: .24, 15: .08},
    "BBG": {3: .46, 4: .22, 11: .06, 12: .20, 15: .06},
    "BBE": {1: .20, 5: .34, 8: .10, 12: .16, 13: .12, 15: .08},
}

# Division shares per sector (global)
division_shares = {
    "BBM": {"PS": .30, "CC": .17, "ED": .10, "AE": .15, "MA": .18, "XC": .10},
    "BBI": {"DC": .80, "CI": .20},
    "BBG": {"PT": .35, "BS": .65},
    "BBE": {"BT": .35, "HC": .45, "SO": .20},
}

# Per-sector financial ratios (of TNS)
ratios = {
    #          int_sales  stp   ebit   rd     salescost admin  var    other
    "BBM": dict(internal=.050, stp=.62, ebit=.048, rd=.095, sc=.050, adm=.028, var=.040, oth=.002),
    "BBI": dict(internal=.040, stp=.58, ebit=.088, rd=.055, sc=.070, adm=.035, var=.030, oth=.002),
    "BBG": dict(internal=.030, stp=.66, ebit=.047, rd=.040, sc=.090, adm=.032, var=.050, oth=.002),
    "BBE": dict(internal=.040, stp=.60, ebit=.062, rd=.050, sc=.080, adm=.034, var=.045, oth=.002),
}

# Headcount totals per sector (year-end 2023)
sector_hc_2023 = {"BBM": 230000, "BBI": 32000, "BBG": 86000, "BBE": 61000}
sector_hc_growth = {"BBM": -0.020, "BBI": -0.030, "BBG": -0.010, "BBE": 0.015}
direct_share = {"BBM": .62, "BBI": .55, "BBG": .65, "BBE": .50}
# Labor intensity multiplier by country (headcount per EUR of sales)
labor_factor = {"DE": 0.85, "FR": 0.9, "HU": 1.6, "CZ": 1.6, "US": 0.8, "MX": 1.5,
                "BR": 1.3, "CN": 1.1, "IN": 1.8, "JP": 0.9, "SG": 0.7}

seasonality = [1.02, 0.98, 1.10, 1.00, 0.99, 1.04, 0.96, 0.86, 1.06, 1.07, 1.00, 0.92]
s_sum = sum(seasonality)
seasonality = [s * 12 / s_sum for s in seasonality]

# Per (sector, entity) division split: perturbed global shares
ent_div_share = {}
for sec, ents in entity_weights.items():
    for ent in ents:
        shares = {}
        for d, w in division_shares[sec].items():
            shares[d] = max(0.01, w * random.uniform(0.6, 1.4))
        tot = sum(shares.values())
        ent_div_share[(sec, ent)] = {d: v / tot for d, v in shares.items()}

# Stable per-(sector, entity) performance tilt so entities differ consistently
ent_perf = {(sec, ent): random.uniform(0.92, 1.08)
            for sec, ents in entity_weights.items() for ent in ents}

# ----------------------------------------------------------------------------
# 5. FACT GENERATION
# ----------------------------------------------------------------------------
ACT_PERIODS_2023 = [202301 + i for i in range(12)]
ACT_PERIODS_2024 = [202401 + i for i in range(5)]          # Jan..May 2024
CF_PERIODS_2024  = [202401 + i for i in range(12)]
BP_PERIODS_2024  = CF_PERIODS_2024

fin_rows = []
hc_rows = []

def month_of(pid): return pid % 100
def year_of(pid): return pid // 100

def to_currencies(eur_val, ccy, pid):
    """returns (value_lc, value_eur_nom, value_eur_real)"""
    rate, plan = fx_lookup[(ccy, pid)]
    lc = eur_val * rate
    eur_real = lc / plan if plan else eur_val
    return (round(lc, 3), round(eur_val, 3), round(eur_real, 3))

# Cache of generated ACT monthly TNS at grain (sector, entity, division, pid)
tns_cache = {}

def gen_block(scenario, sec, ent, div, pid, tns_eur, noise_scale):
    """Generate all measures for one grain/month and append rows."""
    r = ratios[sec]
    ccy = country_ccy[entity_country[ent]]
    n = lambda s=noise_scale: (1 + random.gauss(0, s))

    tgs = tns_eur / (1 - r["internal"])
    int_sales = tgs - tns_eur
    stp = tns_eur * r["stp"] * n(0.02 * noise_scale * 10 if noise_scale else 0)

    ebit = tns_eur * r["ebit"] * n(noise_scale * 4)
    rd   = tns_eur * r["rd"]   * n(noise_scale * 1.5)
    sc   = tns_eur * r["sc"]   * n(noise_scale * 1.5)
    adm  = tns_eur * r["adm"]  * n(noise_scale * 1.5)
    var  = tns_eur * r["var"]  * n(noise_scale * 2)
    oth  = tns_eur * (r["oth"] + (random.gauss(0, 0.004) if noise_scale else 0))

    ar  = tns_eur * 12 * 45 / 365 * n(noise_scale)
    ap  = tns_eur * 12 * 38 / 365 * n(noise_scale)
    inv = tns_eur * 12 * (60 if sec == "BBM" else 52) / 365 * n(noise_scale)
    m = month_of(pid)
    capex_season = 1.35 if m in (10, 11, 12) else (0.85 if m in (1, 2) else 1.0)
    capex = tns_eur * 0.055 * capex_season * n(noise_scale * 2)
    deprec = tns_eur * 0.042
    ifcf = ebit + deprec - capex + (random.gauss(0, tns_eur * 0.025) if noise_scale else 0)

    vals = [("TGS", tgs), ("TNS", tns_eur), ("INT_SALES", int_sales),
            ("STP_REGION", stp), ("EBIT", ebit), ("SGA_RD", rd),
            ("SGA_SALES", sc), ("SGA_ADMIN", adm), ("SGA_VAR", var),
            ("OTHER_OPINC", oth), ("AR", ar), ("AP", ap),
            ("INVENTORY", inv), ("CAPEX", capex), ("IFCF", ifcf)]
    for mcode, v in vals:
        lc, nom, real = to_currencies(v, ccy, pid)
        fin_rows.append((pid, scenario, ent, sec, div, mcode, ccy, lc, nom, real))

# ---- ACT 2023 + 2024 ----
for sec, ents in entity_weights.items():
    annual_23 = sector_tns_2023[sec]
    g = sector_growth[sec]
    for ent, w in ents.items():
        perf = ent_perf[(sec, ent)]
        for div, ds in ent_div_share[(sec, ent)].items():
            base_month = annual_23 * w * ds / 12.0
            # 2023 actuals
            for pid in ACT_PERIODS_2023:
                m = month_of(pid)
                tns = base_month * seasonality[m-1] * perf * (1 + random.gauss(0, 0.03))
                tns_cache[(sec, ent, div, pid)] = tns
                gen_block("ACT", sec, ent, div, pid, tns, 0.015)
            # 2024 actuals Jan..May (vs same month PY, with entity-level dispersion)
            for pid in ACT_PERIODS_2024:
                m = month_of(pid)
                py = tns_cache[(sec, ent, div, 202300 + m)]
                tns = py * (1 + g + random.gauss(0, 0.035))
                tns_cache[(sec, ent, div, pid)] = tns
                gen_block("ACT", sec, ent, div, pid, tns, 0.015)

# ---- BP 2024 (smooth, frozen plan) ----
for sec, ents in entity_weights.items():
    bg = sector_bp_growth[sec]
    for ent, w in ents.items():
        for div, ds in ent_div_share[(sec, ent)].items():
            for pid in BP_PERIODS_2024:
                m = month_of(pid)
                py = tns_cache[(sec, ent, div, 202300 + m)]
                tns = py * (1 + bg)
                gen_block("BP", sec, ent, div, pid, tns, 0.0)

# ---- CF 2024 (Jan..May ~= ACT; Jun..Dec = trend-adjusted plan) ----
for sec, ents in entity_weights.items():
    g = sector_growth[sec]
    bg = sector_bp_growth[sec]
    for ent, w in ents.items():
        for div, ds in ent_div_share[(sec, ent)].items():
            # YTD performance vs plan drives the forecast adjustment
            ytd_act = sum(tns_cache[(sec, ent, div, p)] for p in ACT_PERIODS_2024)
            ytd_py  = sum(tns_cache[(sec, ent, div, 202300 + month_of(p))] for p in ACT_PERIODS_2024)
            run_rate = ytd_act / ytd_py - 1
            for pid in CF_PERIODS_2024:
                m = month_of(pid)
                if pid in ACT_PERIODS_2024:
                    tns = tns_cache[(sec, ent, div, pid)] * (1 + random.gauss(0, 0.004))
                else:
                    py = tns_cache[(sec, ent, div, 202300 + m)]
                    blended = 0.6 * run_rate + 0.4 * bg
                    tns = py * (1 + blended)
                gen_block("CF", sec, ent, div, pid, tns, 0.004)

cur.executemany("""INSERT INTO fact_financials
    (period_id, scenario_code, entity_id, sector_code, division_code,
     measure_code, currency_code, value_lc, value_eur_nom, value_eur_real)
    VALUES (?,?,?,?,?,?,?,?,?,?)""", fin_rows)

# ---- Headcount ----
# weight = sales weight * labor factor, renormalized per sector
for sec, ents in entity_weights.items():
    raw = {ent: w * labor_factor[entity_country[ent]] for ent, w in ents.items()}
    tot = sum(raw.values())
    hw = {ent: v / tot for ent, v in raw.items()}
    base_hc = sector_hc_2023[sec]
    hg = sector_hc_growth[sec]
    ds_dir = direct_share[sec]
    for ent in ents:
        for div, dsh in ent_div_share[(sec, ent)].items():
            hc0 = base_hc * hw[ent] * dsh
            for scen, plist in (("ACT", ACT_PERIODS_2023 + ACT_PERIODS_2024),
                                ("CF", CF_PERIODS_2024), ("BP", BP_PERIODS_2024)):
                for pid in plist:
                    y, m = year_of(pid), month_of(pid)
                    # linear drift across months
                    t = (m - 1) / 11
                    if y == 2023:
                        level = hc0 * (1 - 0.5 * -hg * 0)  # flat-ish 2023
                        level = hc0 * (1 + random.gauss(0, 0.004))
                    else:
                        target = hc0 * (1 + (hg if scen != "BP" else hg * 0.4))
                        level = hc0 + (target - hc0) * t
                        if scen == "ACT":
                            level *= (1 + random.gauss(0, 0.004))
                    avg = level * (1 - 0.003)
                    pc = avg * 0.93          # PC FTE < headcount (part-time, absence)
                    rows = (round(level * ds_dir, 1), round(level * (1 - ds_dir), 1),
                            round(avg * ds_dir, 1),   round(avg * (1 - ds_dir), 1),
                            round(pc * ds_dir, 1),    round(pc * (1 - ds_dir), 1))
                    hc_rows.append((pid, scen, ent, sec, div) + rows)

cur.executemany("""INSERT INTO fact_headcount
    (period_id, scenario_code, entity_id, sector_code, division_code,
     hc_state_direct, hc_state_indirect, hc_avg_direct, hc_avg_indirect,
     pc_fte_direct, pc_fte_indirect) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", hc_rows)
con.commit()

# ----------------------------------------------------------------------------
# 6. AI LAYER: controller comments, anomaly flags, MBR submissions
# ----------------------------------------------------------------------------
controllers = {
    1: "M. Keller", 2: "S. Brandt", 3: "A. Vogel", 4: "C. Winter", 5: "J. Hoffmann",
    6: "K. Nagy", 7: "P. Novak", 8: "L. Moreau", 9: "R. Thompson", 10: "D. Ramirez",
    11: "F. Oliveira", 12: "W. Chen", 13: "A. Sharma", 14: "T. Sato", 15: "G. Lim",
}
entity_name = {e[0]: e[2] for e in entities}

def q(sql, params=()):
    return cur.execute(sql, params).fetchall()

# Aggregate entity/sector monthly TNS & EBIT (ACT, EUR nominal)
agg = {}
for pid, sec, ent, mcode, v in q("""
    SELECT period_id, sector_code, entity_id, measure_code, SUM(value_eur_nom)
    FROM fact_financials
    WHERE scenario_code='ACT' AND measure_code IN ('TNS','EBIT','SGA_RD','INVENTORY','CAPEX')
    GROUP BY 1,2,3,4"""):
    agg[(pid, sec, ent, mcode)] = v

comment_rows = []
pos_templates = [
    "TNS at EUR {v:.0f}m, up {d:+.1f}% vs PY, driven by strong order intake in {div} and positive price effects.",
    "Sales exceed prior year by {d:+.1f}% (EUR {v:.0f}m); volume recovery in key accounts, FX tailwind approx. 0.8pp.",
    "Net sales of EUR {v:.0f}m ({d:+.1f}% vs PY) supported by new product ramp-ups; CF for FY confirmed.",
]
neg_templates = [
    "TNS at EUR {v:.0f}m, {d:+.1f}% below PY due to softer market demand and customer destocking; countermeasures initiated.",
    "Sales decline of {d:+.1f}% vs PY (EUR {v:.0f}m); FX headwind approx. 1.5pp, underlying volume stable.",
    "Net sales EUR {v:.0f}m ({d:+.1f}% vs PY); weakness concentrated in {div}; pricing actions under review for H2.",
]
ebit_pos = [
    "EBIT of EUR {v:.0f}m ({m:.1f}% of TNS), {d:+.1f}% vs PY; favorable mix and fixed cost discipline.",
    "EBIT margin at {m:.1f}%, improving vs PY on productivity gains and lower material cost.",
]
ebit_neg = [
    "EBIT at EUR {v:.0f}m ({m:.1f}% of TNS), below PY; under-absorption from lower volumes, ramp-up costs in {div}.",
    "EBIT margin {m:.1f}%, pressured by wage inflation and negative mix; recovery plan agreed with GM.",
]

div_by_sec_ent = {k: max(v, key=v.get) for k, v in ent_div_share.items()}

cc_periods = [202401 + i for i in range(5)] + [202310, 202311, 202312]
for pid in cc_periods:
    m = month_of(pid)
    py_pid = (year_of(pid) - 1) * 100 + m
    for sec, ents in entity_weights.items():
        for ent in ents:
            tns = agg.get((pid, sec, ent, "TNS"))
            tns_py = agg.get((py_pid, sec, ent, "TNS"))
            if not tns:
                continue
            created = f"{year_of(pid)}-{m:02d}-{random.randint(3, 9):02d} {random.randint(8,17):02d}:{random.randint(0,59):02d}:00"
            div_name = dict([(d[0], d[1]) for d in divisions])[div_by_sec_ent[(sec, ent)]]
            if tns_py:
                d = (tns / tns_py - 1) * 100
                tmpl = random.choice(pos_templates if d >= 0 else neg_templates)
                comment_rows.append((pid, ent, sec, "TNS",
                                     tmpl.format(v=tns, d=d, div=div_name),
                                     controllers[ent], "EN", created))
            ebit = agg.get((pid, sec, ent, "EBIT"))
            ebit_py = agg.get((py_pid, sec, ent, "EBIT"))
            if ebit and tns and random.random() < 0.75:
                margin = ebit / tns * 100
                d = ((ebit / ebit_py - 1) * 100) if ebit_py else 0
                tmpl = random.choice(ebit_pos if (ebit_py and ebit >= ebit_py) else ebit_neg)
                comment_rows.append((pid, ent, sec, "EBIT",
                                     tmpl.format(v=ebit, m=margin, d=d, div=div_name),
                                     controllers[ent], "EN", created))

cur.executemany("""INSERT INTO controller_comments
    (period_id, entity_id, sector_code, measure_code, comment_text, author, language, created_at)
    VALUES (?,?,?,?,?,?,?,?)""", comment_rows)

# ---- Anomaly flags: MoM swing > 18% on TNS, EBIT < 0, inventory build-up ----
anom_rows = []
all_pids_act = ACT_PERIODS_2023 + ACT_PERIODS_2024
for sec, ents in entity_weights.items():
    for ent in ents:
        prev = None
        for pid in all_pids_act:
            tns = agg.get((pid, sec, ent, "TNS"))
            if tns is None:
                continue
            if prev and abs(tns / prev - 1) > 0.18:
                sev = "CRITICAL" if abs(tns / prev - 1) > 0.25 else "WARNING"
                anom_rows.append((pid, ent, sec, "TNS", "MOM_SWING", sev,
                    f"TNS month-over-month change of {((tns/prev)-1)*100:+.1f}% exceeds 18% threshold "
                    f"({entity_name[ent]}, {sec}). Verify postings and one-off effects before MBR submission.",
                    "OPEN" if pid >= 202404 else "RESOLVED",
                    f"{year_of(pid)}-{month_of(pid):02d}-03 06:00:00"))
            prev = tns
            ebit = agg.get((pid, sec, ent, "EBIT"))
            if ebit is not None and ebit < 0:
                anom_rows.append((pid, ent, sec, "EBIT", "NEG_EBIT", "CRITICAL",
                    f"Negative EBIT of EUR {ebit:.1f}m detected for {entity_name[ent]} ({sec}). "
                    f"Sanity check required: review one-time charges and accrual postings.",
                    "OPEN" if pid >= 202404 else "REVIEWED",
                    f"{year_of(pid)}-{month_of(pid):02d}-03 06:05:00"))
            inv = agg.get((pid, sec, ent, "INVENTORY"))
            if inv and tns and inv / (tns * 12 / 365) > 75 and random.random() < 0.12:
                anom_rows.append((pid, ent, sec, "INVENTORY", "INV_DOH", "WARNING",
                    f"Inventory days-on-hand above 75 days for {entity_name[ent]} ({sec}); "
                    f"early warning for NWC target deviation.",
                    "OPEN" if pid >= 202404 else "RESOLVED",
                    f"{year_of(pid)}-{month_of(pid):02d}-04 06:00:00"))

cur.executemany("""INSERT INTO anomaly_flags
    (period_id, entity_id, sector_code, measure_code, rule_code, severity,
     message, status, detected_at) VALUES (?,?,?,?,?,?,?,?,?)""", anom_rows)

# ---- MBR submissions: 2024 Jan..May per entity ----
sub_rows = []
gm_approvers = ["Dr. H. Schneider", "M. Yamamoto", "S. Patel", "E. Garcia", "C. Mueller"]
for pid in ACT_PERIODS_2024:
    m = month_of(pid)
    for ent in range(1, 16):
        ctrl = controllers[ent]
        if pid <= 202404:
            status = "APPROVED"
            sub_at = f"2024-{m:02d}-{random.randint(4, 7):02d} {random.randint(9,16):02d}:30:00"
            app_at = f"2024-{m:02d}-{random.randint(8, 11):02d} {random.randint(9,16):02d}:00:00"
            appr = random.choice(gm_approvers)
            sanity = 1
        else:  # May: in flight
            status = random.choices(["APPROVED", "SUBMITTED", "DRAFT"], [0.4, 0.4, 0.2])[0]
            sub_at = f"2024-06-{random.randint(3, 6):02d} {random.randint(9,16):02d}:30:00" if status != "DRAFT" else None
            app_at = f"2024-06-{random.randint(7, 9):02d} 10:00:00" if status == "APPROVED" else None
            appr = random.choice(gm_approvers) if status == "APPROVED" else None
            sanity = 1 if status == "APPROVED" else (random.choice([1, 0]) if status == "SUBMITTED" else None)
        ai_sum = (f"Auto-generated MBR draft for {entity_name[ent]} {month_names[m-1]} {year_of(pid)}: "
                  f"performance vs PY and CF consolidated across sectors; "
                  f"{'no open anomalies' if sanity else 'open anomalies pending review'}.")
        sub_rows.append((pid, ent, status, ctrl if status != "DRAFT" else None,
                         sub_at, appr, app_at, sanity, ai_sum))

cur.executemany("""INSERT INTO mbr_submissions
    (period_id, entity_id, status, submitted_by, submitted_at,
     approved_by, approved_at, sanity_check_passed, ai_summary)
    VALUES (?,?,?,?,?,?,?,?,?)""", sub_rows)

con.commit()

# ----------------------------------------------------------------------------
# 7. SUMMARY
# ----------------------------------------------------------------------------
for t in ["dim_business_sector","dim_country","dim_legal_entity","dim_division",
          "dim_period","dim_scenario","dim_measure","fx_rates","fact_financials",
          "fact_headcount","controller_comments","anomaly_flags","mbr_submissions"]:
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:25s} {n:>8,}")

print("\n--- Sanity: 2024 YTD (Jan-May) TNS by sector, EUR m (ACT nominal) ---")
for row in q("""SELECT sector_code, ROUND(SUM(value_eur_nom),0)
                FROM fact_financials
                WHERE scenario_code='ACT' AND measure_code='TNS' AND period_id BETWEEN 202401 AND 202405
                GROUP BY 1 ORDER BY 1"""):
    print(row)

print("\n--- Sanity: May 2024 EBIT % of TNS by sector ---")
for row in q("""SELECT sector_code,
                ROUND(SUM(CASE WHEN measure_code='EBIT' THEN value_eur_nom END) /
                      SUM(CASE WHEN measure_code='TNS' THEN value_eur_nom END) * 100, 2)
                FROM fact_financials
                WHERE scenario_code='ACT' AND period_id=202405
                GROUP BY 1 ORDER BY 1"""):
    print(row)

con.close()
print("\nDatabase written to", DB_PATH)
