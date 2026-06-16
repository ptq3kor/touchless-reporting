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

CREATE TABLE dim_division (
    division_code TEXT PRIMARY KEY,
    division_name TEXT NOT NULL,
    sector_code   TEXT NOT NULL REFERENCES dim_business_sector(sector_code)
);

CREATE TABLE dim_legal_entity (
    entity_id     INTEGER PRIMARY KEY,
    entity_code   TEXT UNIQUE NOT NULL,
    entity_name   TEXT NOT NULL,
    country_code  TEXT NOT NULL REFERENCES dim_country(country_code)
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

CREATE TABLE fx_rates (
    currency_code     TEXT NOT NULL,
    period_id         INTEGER NOT NULL REFERENCES dim_period(period_id),
    rate_to_eur       REAL NOT NULL,         -- 1 EUR = X LC (monthly avg)
    plan_rate_to_eur  REAL NOT NULL,         -- budget/plan FX rate (constant per year)
    PRIMARY KEY (currency_code, period_id)
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

CREATE TABLE sqlite_sequence(name,seq);

CREATE INDEX ix_cc_main  ON controller_comments(period_id, entity_id, sector_code);

CREATE INDEX ix_fin_entity ON fact_financials(entity_id, division_code);

CREATE INDEX ix_fin_main ON fact_financials(period_id, scenario_code, sector_code, measure_code);

CREATE INDEX ix_hc_main  ON fact_headcount(period_id, scenario_code, sector_code);

