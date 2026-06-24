"""Reusable query functions shared by the REST routers and the AI agent tools."""
from typing import Optional

from .db import get_conn
from .filters import FilterParams, Resolved, resolve

SALES_MEASURES = ["TGS", "TNS", "INT_SALES", "STP_REGION"]
SGA_MEASURES = ["SGA_RD", "SGA_SALES", "SGA_ADMIN", "SGA_VAR", "OTHER_OPINC"]
BALANCE_MEASURES = ["AR", "AP", "INVENTORY"]
FLOW_NWC_MEASURES = ["CAPEX", "IFCF"]


def pct(cur, base, digits=1):
    if cur is None or base is None or abs(base) < 1e-9:
        return None
    return round((cur / base - 1) * 100, digits)


def rnd(v, digits=1):
    return None if v is None else round(v, digits)


def measure_labels(conn) -> dict:
    rows = conn.execute(
        "SELECT measure_code, measure_name, is_cost, is_balance, sort_order FROM dim_measure"
    ).fetchall()
    return {r["measure_code"]: dict(r) for r in rows}


def agg(conn, rf: Resolved, measures, scenario, p_lo, p_hi, val_col=None) -> dict:
    """SUM values per measure over a period range. Returns {measure: {v, nom, real}}."""
    val_col = val_col or rf.val_col
    mkeys = {f"m{i}": m for i, m in enumerate(measures)}
    sql = f"""
        SELECT f.measure_code,
               SUM(f.{val_col})        AS v,
               SUM(f.value_eur_nom)    AS v_nom,
               SUM(f.value_eur_real)   AS v_real
        FROM fact_financials f
        WHERE f.scenario_code = :scenario
          AND f.period_id BETWEEN :p_lo AND :p_hi
          AND f.measure_code IN ({', '.join(':' + k for k in mkeys)})
          {rf.where}
        GROUP BY f.measure_code
    """
    params = {**rf.params, **mkeys, "scenario": scenario, "p_lo": p_lo, "p_hi": p_hi}
    out = {m: {"v": None, "nom": None, "real": None} for m in measures}
    for r in conn.execute(sql, params):
        out[r["measure_code"]] = {"v": r["v"], "nom": r["v_nom"], "real": r["v_real"]}
    return out


def month_agg(conn, rf, measures, scenario, pid=None):
    pid = pid or rf.period_id
    return agg(conn, rf, measures, scenario, pid, pid)


def series(conn, rf: Resolved, measure, n_months=12, scenario="ACT") -> list:
    """Monthly values for the n rolling months ending at the selected period."""
    periods = [r["period_id"] for r in conn.execute(
        "SELECT period_id FROM dim_period WHERE period_id <= ? ORDER BY period_id DESC LIMIT ?",
        (rf.period_id, n_months),
    )][::-1]
    if not periods:
        return []
    sql = f"""
        SELECT f.period_id, SUM(f.{rf.val_col}) AS v
        FROM fact_financials f
        WHERE f.scenario_code = :scenario AND f.measure_code = :measure
          AND f.period_id BETWEEN :lo AND :hi {rf.where}
        GROUP BY f.period_id
    """
    rows = conn.execute(sql, {**rf.params, "scenario": scenario, "measure": measure,
                              "lo": periods[0], "hi": periods[-1]}).fetchall()
    by_pid = {r["period_id"]: r["v"] for r in rows}
    return [{"period": p, "value": rnd(by_pid.get(p))} for p in periods if p in by_pid]


# ---------------------------------------------------------------- sections

def sales_data(conn, rf: Resolved) -> dict:
    cmp_sc = rf.fp.cmp
    cur_m = month_agg(conn, rf, SALES_MEASURES, "ACT")
    py_m = month_agg(conn, rf, SALES_MEASURES, "ACT", rf.py_period_id)
    cmp_m = month_agg(conn, rf, SALES_MEASURES, cmp_sc)
    cur_y = agg(conn, rf, SALES_MEASURES, "ACT", rf.ytd_start, rf.period_id)
    py_y = agg(conn, rf, SALES_MEASURES, "ACT", rf.py_ytd_start, rf.py_period_id)
    cmp_y = agg(conn, rf, SALES_MEASURES, cmp_sc, rf.ytd_start, rf.period_id)
    labels = measure_labels(conn)

    kpis = []
    for m in SALES_MEASURES:
        kpis.append({
            "measure": m,
            "label": labels.get(m, {}).get("measure_name", m),
            "month": {
                "value": rnd(cur_m[m]["v"]),
                "vs_py_pct": pct(cur_m[m]["v"], py_m[m]["v"]),
                "vs_cmp_pct": pct(cur_m[m]["v"], cmp_m[m]["v"]),
            },
            "ytd": {
                "value": rnd(cur_y[m]["v"]),
                "vs_py_pct": pct(cur_y[m]["v"], py_y[m]["v"]),
                "vs_cmp_pct": pct(cur_y[m]["v"], cmp_y[m]["v"]),
            },
            "real_nominal": {"nom": rnd(cur_m[m]["nom"]), "real": rnd(cur_m[m]["real"])},
        })

    # Breakdown always spans all sectors (powers the sector chart) but keeps geo/division filters.
    rf_all = resolve(conn, rf.fp, sector_filter=False)
    sql = f"""
        SELECT f.sector_code, s.sector_name, s.sort_order,
               SUM(CASE WHEN f.period_id = :pid THEN f.{rf.val_col} END) AS cur,
               SUM(CASE WHEN f.period_id = :py_pid THEN f.{rf.val_col} END) AS py
        FROM fact_financials f JOIN dim_business_sector s ON s.sector_code = f.sector_code
        WHERE f.scenario_code = 'ACT' AND f.measure_code = 'TNS'
          AND f.period_id IN (:pid, :py_pid) {rf_all.where}
        GROUP BY f.sector_code, s.sector_name, s.sort_order ORDER BY s.sort_order
    """
    breakdown = [
        {"sector": r["sector_code"], "name": r["sector_name"],
         "tns": rnd(r["cur"]), "vs_py_pct": pct(r["cur"], r["py"])}
        for r in conn.execute(sql, {**rf_all.params, "pid": rf.period_id, "py_pid": rf.py_period_id})
    ]
    return {"meta": rf.meta(), "kpis": kpis, "sector_breakdown": breakdown}


def pnl_data(conn, rf: Resolved) -> dict:
    ms = ["EBIT", "TNS"]
    act_m = month_agg(conn, rf, ms, "ACT")
    py_m = month_agg(conn, rf, ms, "ACT", rf.py_period_id)
    cf_m = month_agg(conn, rf, ms, "CF")
    bp_m = month_agg(conn, rf, ms, "BP")
    act_y = agg(conn, rf, ms, "ACT", rf.ytd_start, rf.period_id)
    py_y = agg(conn, rf, ms, "ACT", rf.py_ytd_start, rf.py_period_id)
    cf_y = agg(conn, rf, ms, "CF", rf.ytd_start, rf.period_id)
    bp_y = agg(conn, rf, ms, "BP", rf.ytd_start, rf.period_id)

    def margin(block):
        e, t = block["EBIT"]["v"], block["TNS"]["v"]
        if e is None or t is None or abs(t) < 1e-9:
            return None
        return round(e / t * 100, 2)

    def pp(a, b):
        return None if a is None or b is None else round(a - b, 2)

    m_act, m_py, m_cf, m_bp = margin(act_m), margin(py_m), margin(cf_m), margin(bp_m)
    y_act, y_py = margin(act_y), margin(py_y)

    return {"meta": rf.meta(), "ebit": {
        "month": {
            "act": rnd(act_m["EBIT"]["v"]), "py": rnd(py_m["EBIT"]["v"]),
            "cf": rnd(cf_m["EBIT"]["v"]), "bp": rnd(bp_m["EBIT"]["v"]),
            "vs_py_pct": pct(act_m["EBIT"]["v"], py_m["EBIT"]["v"]),
            "vs_cf_pct": pct(act_m["EBIT"]["v"], cf_m["EBIT"]["v"]),
            "vs_bp_pct": pct(act_m["EBIT"]["v"], bp_m["EBIT"]["v"]),
        },
        "ytd": {
            "act": rnd(act_y["EBIT"]["v"]), "py": rnd(py_y["EBIT"]["v"]),
            "cf": rnd(cf_y["EBIT"]["v"]), "bp": rnd(bp_y["EBIT"]["v"]),
            "vs_py_pct": pct(act_y["EBIT"]["v"], py_y["EBIT"]["v"]),
            "vs_cf_pct": pct(act_y["EBIT"]["v"], cf_y["EBIT"]["v"]),
            "vs_bp_pct": pct(act_y["EBIT"]["v"], bp_y["EBIT"]["v"]),
        },
        "pct_of_tns": {
            "month_act": m_act, "month_py": m_py, "month_cf": m_cf, "month_bp": m_bp,
            "ytd_act": y_act, "ytd_py": y_py,
            "vs_py_pp": pp(m_act, m_py), "vs_cf_pp": pp(m_act, m_cf), "vs_bp_pp": pp(m_act, m_bp),
        },
    }}


def sga_data(conn, rf: Resolved) -> dict:
    cmp_sc = rf.fp.cmp
    cur_m = month_agg(conn, rf, SGA_MEASURES, "ACT")
    py_m = month_agg(conn, rf, SGA_MEASURES, "ACT", rf.py_period_id)
    cmp_m = month_agg(conn, rf, SGA_MEASURES, cmp_sc)
    cur_y = agg(conn, rf, SGA_MEASURES, "ACT", rf.ytd_start, rf.period_id)
    py_y = agg(conn, rf, SGA_MEASURES, "ACT", rf.py_ytd_start, rf.py_period_id)
    cmp_y = agg(conn, rf, SGA_MEASURES, cmp_sc, rf.ytd_start, rf.period_id)
    labels = measure_labels(conn)

    meta_rows = conn.execute(
        "SELECT measure_code, sub_category FROM dim_measure WHERE category='SGA' OR measure_code='OTHER_OPINC'"
    ).fetchall()
    group_of = {r["measure_code"]: (r["sub_category"] or "OTHER") for r in meta_rows}

    rows = []
    for m in SGA_MEASURES:
        rows.append({
            "group": group_of.get(m, "OTHER"),
            "measure": m,
            "label": labels.get(m, {}).get("measure_name", m),
            "is_cost": bool(labels.get(m, {}).get("is_cost")),
            "month": {"value": rnd(cur_m[m]["v"]), "vs_py_pct": pct(cur_m[m]["v"], py_m[m]["v"]),
                      "vs_cmp_pct": pct(cur_m[m]["v"], cmp_m[m]["v"])},
            "ytd": {"value": rnd(cur_y[m]["v"]), "py": rnd(py_y[m]["v"]),
                    "vs_py_pct": pct(cur_y[m]["v"], py_y[m]["v"]),
                    "vs_cmp_pct": pct(cur_y[m]["v"], cmp_y[m]["v"])},
        })

    fixed = sum(cur_y[m]["v"] or 0 for m in ("SGA_RD", "SGA_SALES", "SGA_ADMIN"))
    fixed_py = sum(py_y[m]["v"] or 0 for m in ("SGA_RD", "SGA_SALES", "SGA_ADMIN"))
    var = cur_y["SGA_VAR"]["v"] or 0
    var_py = py_y["SGA_VAR"]["v"] or 0
    return {"meta": rf.meta(), "rows": rows, "totals": {
        "fixed_ytd": rnd(fixed), "variable_ytd": rnd(var),
        "sga_total_ytd": rnd(fixed + var), "vs_py_pct": pct(fixed + var, fixed_py + var_py),
    }}


def _hc_agg(conn, rf: Resolved, scenario, pid):
    sql = f"""
        SELECT SUM(hc_state_direct) sd, SUM(hc_state_indirect) si,
               SUM(hc_avg_direct) ad, SUM(hc_avg_indirect) ai,
               SUM(pc_fte_direct) pd, SUM(pc_fte_indirect) pi
        FROM fact_headcount f
        WHERE f.scenario_code = :scenario AND f.period_id = :pid {rf.where}
    """
    return conn.execute(sql, {**rf.params, "scenario": scenario, "pid": pid}).fetchone()


def headcount_data(conn, rf: Resolved) -> dict:
    cur = _hc_agg(conn, rf, "ACT", rf.period_id)
    py = _hc_agg(conn, rf, "ACT", rf.py_period_id)
    cmp_r = _hc_agg(conn, rf, rf.fp.cmp, rf.period_id)

    def tot(r, a, b):
        if r is None or r[a] is None:
            return None
        return (r[a] or 0) + (r[b] or 0)

    def dpct(r, a, b):
        t = tot(r, a, b)
        if not t:
            return None
        return round((r[a] or 0) / t * 100, 1)

    state, state_py = tot(cur, "sd", "si"), tot(py, "sd", "si")
    avg, avg_py = tot(cur, "ad", "ai"), tot(py, "ad", "ai")
    pc, pc_py, pc_cmp = tot(cur, "pd", "pi"), tot(py, "pd", "pi"), tot(cmp_r, "pd", "pi")

    periods = [r["period_id"] for r in conn.execute(
        "SELECT period_id FROM dim_period WHERE period_id <= ? ORDER BY period_id DESC LIMIT 12",
        (rf.period_id,))][::-1]
    trend = []
    if periods:
        sql = f"""
            SELECT f.period_id, p.month_name, p.year,
                   SUM(hc_state_direct + hc_state_indirect) hc_state,
                   SUM(pc_fte_direct + pc_fte_indirect) pc_fte
            FROM fact_headcount f JOIN dim_period p ON p.period_id = f.period_id
            WHERE f.scenario_code = 'ACT' AND f.period_id BETWEEN :lo AND :hi {rf.where}
            GROUP BY f.period_id, p.month_name, p.year ORDER BY f.period_id
        """
        for r in conn.execute(sql, {**rf.params, "lo": periods[0], "hi": periods[-1]}):
            trend.append({"period": r["period_id"],
                          "label": f"{r['month_name'][:3]} {str(r['year'])[2:]}",
                          "hc_state": round(r["hc_state"]) if r["hc_state"] is not None else None,
                          "pc_fte": round(r["pc_fte"]) if r["pc_fte"] is not None else None})

    return {"meta": rf.meta(), "cards": {
        "state": {"total": round(state) if state else None, "direct_pct": dpct(cur, "sd", "si"),
                  "vs_py_pct": pct(state, state_py)},
        "avg": {"total": round(avg) if avg else None, "vs_py_pct": pct(avg, avg_py)},
        "pc_fte": {"total": round(pc) if pc else None, "direct_pct": dpct(cur, "pd", "pi"),
                   "vs_py_pct": pct(pc, pc_py), "vs_cmp_pct": pct(pc, pc_cmp)},
    }, "trend": trend}


def nwc_data(conn, rf: Resolved) -> dict:
    labels = measure_labels(conn)
    all_m = BALANCE_MEASURES + FLOW_NWC_MEASURES
    cur_m = month_agg(conn, rf, all_m, "ACT")
    py_m = month_agg(conn, rf, all_m, "ACT", rf.py_period_id)
    cur_y = agg(conn, rf, FLOW_NWC_MEASURES, "ACT", rf.ytd_start, rf.period_id)
    py_y = agg(conn, rf, FLOW_NWC_MEASURES, "ACT", rf.py_ytd_start, rf.py_period_id)

    balances = [{
        "measure": m, "label": labels.get(m, {}).get("measure_name", m),
        "value": rnd(cur_m[m]["v"]), "vs_py_pct": pct(cur_m[m]["v"], py_m[m]["v"]),
        "spark": series(conn, rf, m),
    } for m in BALANCE_MEASURES]

    flows = [{
        "measure": m, "label": labels.get(m, {}).get("measure_name", m),
        "is_cost": bool(labels.get(m, {}).get("is_cost")),
        "month": rnd(cur_m[m]["v"]), "ytd": rnd(cur_y[m]["v"]),
        "vs_py_pct": pct(cur_m[m]["v"], py_m[m]["v"]),
        "ytd_vs_py_pct": pct(cur_y[m]["v"], py_y[m]["v"]),
        "spark": series(conn, rf, m),
    } for m in FLOW_NWC_MEASURES]

    return {"meta": rf.meta(), "balances": balances, "flows": flows}


def summary_data(conn, rf: Resolved) -> dict:
    pid = rf.period_id
    mbr = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) n FROM mbr_submissions WHERE period_id=? GROUP BY status", (pid,))}

    anomalies = [{
        "severity": r["severity"], "rule": r["rule_code"], "message": r["message"],
        "entity": r["entity_name"], "sector": r["sector_code"], "measure": r["measure_code"],
    } for r in conn.execute("""
        SELECT a.severity, a.rule_code, a.message, a.sector_code, a.measure_code, e.entity_name
        FROM anomaly_flags a LEFT JOIN dim_legal_entity e ON e.entity_id = a.entity_id
        WHERE a.period_id = ? AND a.status = 'OPEN'
        ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END
    """, (pid,))]

    ai_summaries = [{
        "entity": r["entity_name"], "status": r["status"], "text": r["ai_summary"],
    } for r in conn.execute("""
        SELECT e.entity_name, s.status, s.ai_summary
        FROM mbr_submissions s JOIN dim_legal_entity e ON e.entity_id = s.entity_id
        WHERE s.period_id = ? AND s.ai_summary IS NOT NULL AND s.ai_summary != ''
        ORDER BY s.status LIMIT 5
    """, (pid,))]

    # Deterministic bullets (no LLM)
    sales = sales_data(conn, rf)
    pnl = pnl_data(conn, rf)
    bullets = []
    tns = next((k for k in sales["kpis"] if k["measure"] == "TNS"), None)
    if tns and tns["month"]["value"] is not None:
        v, d = tns["month"]["value"], tns["month"]["vs_py_pct"]
        direction = "up" if (d or 0) >= 0 else "down"
        bullets.append(f"Total net sales of €{v:,.1f}m, {direction} {abs(d or 0):.1f}% vs PY.")
    bd = [b for b in sales["sector_breakdown"] if b["vs_py_pct"] is not None]
    if bd:
        best = max(bd, key=lambda b: b["vs_py_pct"])
        worst = min(bd, key=lambda b: b["vs_py_pct"])
        bullets.append(f"Strongest sector {best['name']} ({best['vs_py_pct']:+.1f}% vs PY); "
                       f"weakest {worst['name']} ({worst['vs_py_pct']:+.1f}%).")
    e = pnl["ebit"]
    if e["month"]["act"] is not None and e["month"]["cf"] is not None:
        rel = "ahead of" if e["month"]["act"] >= e["month"]["cf"] else "behind"
        bullets.append(f"EBIT of €{e['month']['act']:,.1f}m ({e['pct_of_tns']['month_act']:.2f}% of TNS), "
                       f"{rel} CF (€{e['month']['cf']:,.1f}m).")
    n_crit = sum(1 for a in anomalies if a["severity"] == "CRITICAL")
    if anomalies:
        bullets.append(f"{len(anomalies)} open anomaly flag(s)"
                       + (f", {n_crit} critical" if n_crit else "") + " — review before MBR submission.")
    else:
        bullets.append("No open anomaly flags for the period.")

    return {"meta": rf.meta(), "mbr_status": mbr, "anomalies": anomalies,
            "ai_summaries": ai_summaries, "bullets": bullets}


# ------------------------------------------------- helpers for agent tools

def _rf_for(conn, year: int, month: int, sector: str = "ALL") -> Resolved:
    return resolve(conn, FilterParams(year=year, month=month, sector=sector))


def kpi_snapshot(year: int, month: int, sector: str = "ALL") -> dict:
    conn = get_conn()
    try:
        rf = _rf_for(conn, year, month, sector)
        sales = sales_data(conn, rf)
        pnl = pnl_data(conn, rf)
        return {"period": rf.period_id, "sector": sector,
                "sales_kpis": [{k: v for k, v in kpi.items() if k != "real_nominal"}
                               for kpi in sales["kpis"]],
                "sector_breakdown": sales["sector_breakdown"],
                "ebit": pnl["ebit"]}
    finally:
        conn.close()


def sga_breakdown(year: int, month: int, sector: str = "ALL") -> dict:
    conn = get_conn()
    try:
        return sga_data(conn, _rf_for(conn, year, month, sector))
    finally:
        conn.close()


def headcount_snapshot(year: int, month: int, sector: str = "ALL") -> dict:
    conn = get_conn()
    try:
        d = headcount_data(conn, _rf_for(conn, year, month, sector))
        return {"period": d["meta"]["period_id"], "cards": d["cards"]}
    finally:
        conn.close()


def nwc_snapshot(year: int, month: int, sector: str = "ALL") -> dict:
    conn = get_conn()
    try:
        d = nwc_data(conn, _rf_for(conn, year, month, sector))
        for b in d["balances"]:
            b.pop("spark", None)
        for f in d["flows"]:
            f.pop("spark", None)
        return {"period": d["meta"]["period_id"], "balances": d["balances"], "flows": d["flows"]}
    finally:
        conn.close()


def open_anomalies(period_id: int) -> list:
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT a.severity, a.rule_code, a.message, a.sector_code, a.measure_code, e.entity_name
            FROM anomaly_flags a LEFT JOIN dim_legal_entity e ON e.entity_id = a.entity_id
            WHERE a.period_id = ? AND a.status = 'OPEN'
            ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END
        """, (period_id,))]
    finally:
        conn.close()


def controller_comments(sector: str = "ALL", entity_id: Optional[int] = None, limit: int = 6) -> list:
    conn = get_conn()
    try:
        sql = """SELECT c.comment_text, c.author, c.language, c.period_id, c.measure_code
                 FROM controller_comments c WHERE 1=1"""
        params: list = []
        if sector and sector != "ALL":
            sql += " AND c.sector_code = ?"
            params.append(sector)
        if entity_id is not None:
            sql += " AND c.entity_id = ?"
            params.append(entity_id)
        sql += " ORDER BY c.period_id DESC, c.created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def mbr_status(period_id: int) -> dict:
    conn = get_conn()
    try:
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) n FROM mbr_submissions WHERE period_id=? GROUP BY status",
            (period_id,))}
        drafts = [dict(r) for r in conn.execute("""
            SELECT e.entity_name, s.status, s.sanity_check_passed, s.ai_summary
            FROM mbr_submissions s JOIN dim_legal_entity e ON e.entity_id = s.entity_id
            WHERE s.period_id = ? AND s.ai_summary IS NOT NULL LIMIT 8
        """, (period_id,))]
        return {"period": period_id, "status_counts": counts, "summaries": drafts}
    finally:
        conn.close()
