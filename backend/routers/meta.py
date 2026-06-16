from fastapi import APIRouter

from ..db import get_conn

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/filters")
def get_filters():
    conn = get_conn()
    try:
        sectors = [{"code": r["sector_code"], "name": r["sector_name"]}
                   for r in conn.execute(
                       "SELECT sector_code, sector_name FROM dim_business_sector ORDER BY sort_order")]
        areas = [r["area"] for r in conn.execute(
            "SELECT DISTINCT area FROM dim_country ORDER BY area")]
        subregions = [{"name": r["subregion"], "area": r["area"]} for r in conn.execute(
            "SELECT DISTINCT subregion, area FROM dim_country ORDER BY area, subregion")]
        countries = [{"code": r["country_code"], "name": r["country_name"],
                      "subregion": r["subregion"], "area": r["area"],
                      "currency": r["currency_code"]}
                     for r in conn.execute("SELECT * FROM dim_country ORDER BY country_name")]
        entities = [{"id": r["entity_id"], "code": r["entity_code"], "name": r["entity_name"],
                     "country": r["country_code"]}
                    for r in conn.execute("SELECT * FROM dim_legal_entity ORDER BY entity_name")]
        divisions = [{"code": r["division_code"], "name": r["division_name"],
                      "sector": r["sector_code"]}
                     for r in conn.execute("SELECT * FROM dim_division ORDER BY sector_code, division_code")]

        act_max = conn.execute(
            "SELECT MAX(period_id) m FROM fact_financials WHERE scenario_code='ACT'").fetchone()["m"]
        years = [r["year"] for r in conn.execute("SELECT DISTINCT year FROM dim_period ORDER BY year")]
        months_by_year = {}
        for y in years:
            rows = conn.execute(
                "SELECT month FROM dim_period WHERE year=? AND period_id<=? ORDER BY month",
                (y, act_max)).fetchall()
            months_by_year[str(y)] = [r["month"] for r in rows]
        scenarios = [r["scenario_code"] for r in conn.execute("SELECT scenario_code FROM dim_scenario")]

        return {"sectors": sectors, "areas": areas, "subregions": subregions,
                "countries": countries, "entities": entities, "divisions": divisions,
                "periods": {"act_max": act_max, "years": years, "months_by_year": months_by_year},
                "scenarios": scenarios}
    finally:
        conn.close()
