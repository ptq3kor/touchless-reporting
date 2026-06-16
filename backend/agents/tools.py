"""Function tools exposed to the MAF agents. All delegate to backend.queries
so the REST API and the agents share a single query implementation."""
from typing import Annotated, Optional

from pydantic import Field

from .. import queries


def get_kpi_snapshot(
    year: Annotated[int, Field(description="Reporting year, e.g. 2024")],
    month: Annotated[int, Field(description="Reporting month 1-12", ge=1, le=12)],
    sector: Annotated[str, Field(description="Sector code BBM/BBI/BBG/BBE or ALL for Group")] = "ALL",
) -> dict:
    """Sales KPIs (TGS/TNS/Int.Sales/STP), EBIT and EBIT margin with vs PY/CF/BP variances."""
    return queries.kpi_snapshot(year, month, sector)


def get_sga_breakdown(
    year: Annotated[int, Field(description="Reporting year")],
    month: Annotated[int, Field(description="Reporting month 1-12", ge=1, le=12)],
    sector: Annotated[str, Field(description="Sector code or ALL")] = "ALL",
) -> dict:
    """SG&A cost rows (R&D, Sales, Admin, Variable, Other Op Inc/Exp) YTD vs PY."""
    return queries.sga_breakdown(year, month, sector)


def get_headcount(
    year: Annotated[int, Field(description="Reporting year")],
    month: Annotated[int, Field(description="Reporting month 1-12", ge=1, le=12)],
    sector: Annotated[str, Field(description="Sector code or ALL")] = "ALL",
) -> dict:
    """Headcount state/average and Personnel Capacity (PC FTE) cards with vs PY."""
    return queries.headcount_snapshot(year, month, sector)


def get_nwc(
    year: Annotated[int, Field(description="Reporting year")],
    month: Annotated[int, Field(description="Reporting month 1-12", ge=1, le=12)],
    sector: Annotated[str, Field(description="Sector code or ALL")] = "ALL",
) -> dict:
    """Net working capital balances (AR/AP/Inventory) and flows (CAPEX, iFCF)."""
    return queries.nwc_snapshot(year, month, sector)


def get_open_anomalies(
    period_id: Annotated[int, Field(description="Period as YYYYMM, e.g. 202405")],
) -> list:
    """OPEN anomaly flags for the period with severity, rule, message and entity."""
    return queries.open_anomalies(period_id)


def get_controller_comments(
    sector: Annotated[str, Field(description="Sector code or ALL")] = "ALL",
    entity_id: Annotated[Optional[int], Field(description="Optional legal entity id")] = None,
    limit: Annotated[int, Field(description="Max comments to return")] = 6,
) -> list:
    """Most recent controller comments (text, author, month) — style examples for narratives."""
    return queries.controller_comments(sector, entity_id, limit)


def get_mbr_status(
    period_id: Annotated[int, Field(description="Period as YYYYMM, e.g. 202405")],
) -> dict:
    """MBR submission status counts and existing AI summary drafts for the period."""
    return queries.mbr_status(period_id)


DATA_TOOLS = [get_kpi_snapshot, get_sga_breakdown, get_headcount, get_nwc]
SANITY_TOOLS = [get_open_anomalies, get_kpi_snapshot, get_mbr_status]
NARRATIVE_TOOLS = [get_controller_comments]
ALL_TOOLS = [get_kpi_snapshot, get_sga_breakdown, get_headcount, get_nwc,
             get_open_anomalies, get_controller_comments, get_mbr_status]
